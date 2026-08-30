from __future__ import annotations

import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.github_app_auth import RawResponse
from deploy_executor.p9_control_postcanary_collector import (
    AUDIT_SQL,
    TARGET_SQL,
    ControlPostCanaryCollectionRequest,
    ControlPostCanaryCollectorError,
    FixedD1ReadClient,
    PINNED_CANARY_SOURCE_SHA,
    validate_collection_request,
)
from deploy_executor.p9_host_runtime import (
    DEFAULT_ISOLATED_AUTH,
    DEFAULT_REGISTRY,
    LazyP9StateStore,
    P9HostRuntimeError,
)
from deploy_executor.p9_source_auth import (
    CONTROL_SOURCE_REPOSITORY,
    P9SourceAuthError,
    P9SourceInstallationTokenProvider,
    SOURCE_APP_ID,
    SOURCE_INSTALLATION_ID,
)

CURRENT_READY_SOURCE_SHA = "f9b900a884bffda993197fc7fa9223c886e11a90"


def _d1_payload(*, changed_db=False, rows_written=0, changes=0) -> bytes:
    return json.dumps(
        {
            "success": True,
            "result": [
                {
                    "success": True,
                    "meta": {
                        "changed_db": changed_db,
                        "rows_written": rows_written,
                        "changes": changes,
                    },
                    "results": [],
                }
            ],
        }
    ).encode("utf-8")


class Requester:
    def __init__(self, *, permission="read", repository_id=1329279953):
        self.permission = permission
        self.repository_id = repository_id
        self.calls = []

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path, dict(headers), body))
        date = "Sun, 30 Aug 2026 11:00:00 GMT"
        if method == "GET" and path == "/":
            return RawResponse(200, {"date": date}, {})
        if method == "GET" and path == f"/app/installations/{SOURCE_INSTALLATION_ID}":
            return RawResponse(200, {"date": date}, {
                "id": SOURCE_INSTALLATION_ID,
                "repository_selection": "selected",
                "account": {"id": 277435981, "login": "rozkalnsandris"},
                "permissions": {"actions": self.permission, "contents": "read", "metadata": "read"},
            })
        if method == "POST" and path == f"/app/installations/{SOURCE_INSTALLATION_ID}/access_tokens":
            request = json.loads(body.decode("utf-8"))
            self.request = request
            return RawResponse(201, {"date": date}, {
                "token": "ghs_" + "x" * 80,
                "expires_at": "2026-08-30T12:00:00Z",
                "permissions": {"actions": "read", "contents": "read", "metadata": "read"},
                "repositories": [{"id": self.repository_id, "full_name": CONTROL_SOURCE_REPOSITORY}],
            })
        raise AssertionError((method, path))


class P9HostWiringTests(unittest.TestCase):
    def test_source_app_token_is_exact_repo_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "key.pem"
            key.write_bytes(b"x" * 512)
            key.chmod(0o600)
            requester = Requester()
            provider = P9SourceInstallationTokenProvider(
                repository=CONTROL_SOURCE_REPOSITORY,
                private_key=key,
                requester=requester,
                signer=lambda payload, path: b"signature",
            )
            token = provider.get_installation_token()
            self.assertTrue(token.value.startswith("ghs_"))
            self.assertEqual(provider.repository_id, 1329279953)
            self.assertEqual(requester.request["repository_ids"], [1329279953])
            self.assertEqual(requester.request["permissions"], {"actions": "read", "contents": "read"})
            self.assertEqual(SOURCE_APP_ID, 4537106)

    def test_source_app_rejects_write_permission_before_token_mint(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "key.pem"
            key.write_bytes(b"x" * 512)
            key.chmod(0o600)
            requester = Requester(permission="write")
            provider = P9SourceInstallationTokenProvider(
                repository=CONTROL_SOURCE_REPOSITORY,
                private_key=key,
                requester=requester,
                signer=lambda payload, path: b"signature",
            )
            with self.assertRaises(P9SourceAuthError):
                provider.get_installation_token()
            self.assertFalse(any(method == "POST" for method, *_ in requester.calls))

    def test_source_app_rejects_unknown_repository_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "key.pem"
            key.write_bytes(b"x" * 512)
            key.chmod(0o600)
            with self.assertRaises(P9SourceAuthError):
                P9SourceInstallationTokenProvider(
                    repository="rozkalnsandris/ops-workflows",
                    private_key=key,
                    requester=Requester(),
                )

    def test_host_source_contains_no_dispatch_or_apply_path(self):
        source = (ROOT / "ops" / "lib" / "deploy_executor" / "p9_host_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn(".apply(", source)
        self.assertNotIn("Dispatcher", source)
        self.assertNotIn("ResultWriter", source)
        self.assertIn("load_control_postcanary_baseline_evidence", source)
        self.assertIn("LazyP9StateStore(state_db)", source)
        self.assertNotIn("state_store = StateStore(state_db)", source)

    def test_p9_config_is_isolated_from_active_p8_config(self):
        self.assertEqual(
            DEFAULT_ISOLATED_AUTH,
            Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json"),
        )
        self.assertEqual(
            DEFAULT_REGISTRY,
            Path("/etc/rozkalns-deploy-executor-p9/executor-operations.json"),
        )

    def test_lazy_state_store_opens_only_inside_discover_boundary(self):
        created = []

        class FakeStateStore:
            def __init__(self, path):
                created.append(path)

            def discover(self, **kwargs):
                return ("DISCOVERED", kwargs)

            def transition(self, request_id, new_state):
                return (request_id, new_state)

            def close(self):
                return None

        with patch("deploy_executor.p9_host_runtime.StateStore", FakeStateStore):
            state = LazyP9StateStore("/tmp/p9-state.sqlite3")
            self.assertEqual(created, [])
            discovered = state.discover(request_id="request")
            self.assertEqual(created, ["/tmp/p9-state.sqlite3"])
            self.assertEqual(discovered[0], "DISCOVERED")
            self.assertEqual(state.transition("request", "VALIDATING"), ("request", "VALIDATING"))
            with self.assertRaises(P9HostRuntimeError):
                state.discover(request_id="again")
            state.close()

    def test_control_baseline_keeps_current_source_separate_from_historical_canary(self):
        request = validate_collection_request(
            ControlPostCanaryCollectionRequest(source_sha=CURRENT_READY_SOURCE_SHA)
        )
        self.assertEqual(request.source_sha, CURRENT_READY_SOURCE_SHA)
        self.assertNotEqual(request.source_sha, PINNED_CANARY_SOURCE_SHA)

        collector_source = (
            ROOT / "ops/lib/deploy_executor/p9_control_postcanary_collector.py"
        ).read_text(encoding="utf-8")
        self.assertIn("source_sha=request.source_sha", collector_source)
        self.assertIn("canary_source_sha=PINNED_CANARY_SOURCE_SHA", collector_source)

    def test_control_baseline_d1_reader_is_select_only_and_zero_write(self):
        calls = []

        def requester(url, headers, body):
            payload = json.loads(body.decode("utf-8"))
            calls.append((url, dict(headers), payload))
            self.assertIn(payload["sql"], {AUDIT_SQL, TARGET_SQL})
            self.assertTrue(payload["sql"].startswith("SELECT "))
            return 200, _d1_payload()

        client = FixedD1ReadClient(api_token="x" * 32, requester=requester)
        audit = client.select_pinned_request()
        target = client.select_pinned_target()

        for result in (audit, target):
            self.assertFalse(result.changed_db)
            self.assertEqual(result.rows_written, 0)
            self.assertEqual(result.changes, 0)
        self.assertEqual(len(calls), 2)
        with self.assertRaises(ControlPostCanaryCollectorError):
            client._query("DELETE FROM merge_decisions", ())

    def test_control_baseline_d1_reader_rejects_write_semantics(self):
        def requester(_url, _headers, _body):
            return 200, _d1_payload(changed_db=True, rows_written=1, changes=1)

        client = FixedD1ReadClient(api_token="x" * 32, requester=requester)
        with self.assertRaises(ControlPostCanaryCollectorError):
            client.select_pinned_request()

    def test_installer_preserves_p8_and_binds_exact_reviewed_bytes(self):
        installer = (ROOT / "scripts" / "install-deploy-executor-p9-runtime.sh").read_text(encoding="utf-8")
        self.assertNotIn("systemctl", installer)
        self.assertNotIn("useradd", installer)
        self.assertNotIn("groupadd", installer)
        self.assertIn('P8_CONFIG_ROOT="/etc/rozkalns-deploy-executor"', installer)
        self.assertIn('P9_CONFIG_ROOT="/etc/rozkalns-deploy-executor-p9"', installer)
        self.assertIn('"$P9_CONFIG_ROOT/executor-operations.json"', installer)
        self.assertNotIn('"$P8_CONFIG_ROOT/executor-operations.json"', installer)
        self.assertIn(
            '/usr/bin/git -C "$ROOT" diff --quiet "$EXPECTED_SHA" -- "${SOURCE_PATHS[@]}"',
            installer,
        )
        self.assertIn("reviewed source differs from exact expected SHA", installer)
        self.assertIn(
            '"$INSTALL_ROOT" "$BIN" "$BASELINE_BIN" "$P9_CONFIG_ROOT" "$STATE_ROOT" "$EVIDENCE_ROOT"',
            installer,
        )
        self.assertIn("p9_control_postcanary_collector.py", installer)
        self.assertIn("p9_control_postcanary_producer.py", installer)
        self.assertIn("ops/bin/rozkalns-deploy-p9-control-baseline", installer)
        self.assertIn(
            'BASELINE_BIN="/usr/local/sbin/rozkalns-deploy-p9-control-baseline"',
            installer,
        )
        self.assertIn(
            '"$ROOT/ops/bin/rozkalns-deploy-p9-control-baseline" "$BASELINE_BIN"',
            installer,
        )
        self.assertNotIn("control-d1-read-token", installer)
        self.assertIn("P9_RUNTIME_ACTIVE=NO", installer)
        self.assertIn("P9_EVIDENCE_PRESENT=NO", installer)
        self.assertLess(
            installer.index("diff --quiet"),
            installer.index("Authorized P9 host installation mutation begins here"),
        )

    def test_control_baseline_operator_is_executable_source(self):
        operator = ROOT / "ops/bin/rozkalns-deploy-p9-control-baseline"
        self.assertEqual(stat.S_IMODE(operator.stat().st_mode), 0o755)


if __name__ == "__main__":
    unittest.main()
