from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.github_app_auth import (
    AppAuthError,
    GitHubAppInstallationTokenProvider,
    RawResponse,
    build_app_jwt,
    load_dry_run_config,
)
from deploy_executor.p8_poller import P8PollerError, poll_once
from deploy_executor.transport import HTTPResponse, InstallationToken

FIXTURES = ROOT / "tests" / "fixtures" / "deploy_executor"
CONFIG = ROOT / "ops" / "deploy" / "executor-p8-dry-run-config.json"
REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"
CANARY_REGISTRY = FIXTURES / "operations_control_center_postcanary_canary.json"
SERVICE = ROOT / "ops" / "systemd" / "rozkalns-deploy-executor.service"
TIMER = ROOT / "ops" / "systemd" / "rozkalns-deploy-executor.timer"
POLLER = ROOT / "ops" / "bin" / "rozkalns-deploy-poll"
DISPATCHER = ROOT / "ops" / "bin" / "rozkalns-deploy-dispatch"
INSTALLER = ROOT / "scripts" / "install-deploy-executor-p8-dry-run.sh"
POLLER_SOURCE = ROOT / "ops" / "lib" / "deploy_executor" / "p8_poller.py"


def _decode_segment(segment: str) -> dict:
    segment += "=" * ((4 - len(segment) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(segment.encode("ascii")).decode("utf-8"))


class FakeRequester:
    def __init__(self, *, write_permission: bool = False):
        self.calls = []
        self.write_permission = write_permission

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path, dict(headers), body))
        date = "Fri, 28 Aug 2026 10:00:00 GMT"
        if method == "GET" and path == "/":
            return RawResponse(200, {"date": date}, {})
        if method == "GET" and path == "/app/installations/157217641":
            permissions = {
                "issues": "write" if self.write_permission else "read",
                "metadata": "read",
            }
            return RawResponse(
                200,
                {"date": date},
                {
                    "id": 157217641,
                    "repository_selection": "selected",
                    "account": {"id": 277435981, "login": "rozkalnsandris"},
                    "permissions": permissions,
                },
            )
        if method == "POST" and path == "/app/installations/157217641/access_tokens":
            return RawResponse(
                201,
                {"date": date},
                {
                    "token": "ghs_" + "x" * 40,
                    "expires_at": "2026-08-28T11:00:00Z",
                    "permissions": {"issues": "read", "metadata": "read"},
                    "repositories": [
                        {
                            "id": 1328835922,
                            "full_name": "rozkalnsandris/ops-workflows",
                        }
                    ],
                },
            )
        raise AssertionError((method, path))


class StaticTokenProvider:
    def get_installation_token(self):
        return InstallationToken(
            "ghs_" + "y" * 40,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=50),
        )


class PollSender:
    def __init__(self, *, not_modified: bool = False):
        self.not_modified = not_modified
        self.calls = []

    def send(self, *, method, url, headers):
        self.calls.append((method, url, dict(headers)))
        common = {"date": "Fri, 28 Aug 2026 10:00:00 GMT"}
        if url.endswith("/repos/rozkalnsandris/ops-workflows"):
            return HTTPResponse(
                200,
                common,
                json.dumps(
                    {
                        "id": 1328835922,
                        "full_name": "rozkalnsandris/ops-workflows",
                    }
                ).encode(),
            )
        if "/issues?state=open" in url:
            if self.not_modified and "If-None-Match" in headers:
                return HTTPResponse(304, {**common, "etag": '"p8"'}, b"")
            return HTTPResponse(
                200,
                {**common, "etag": '"p8"'},
                json.dumps(
                    [
                        {
                            "id": 1,
                            "number": 42,
                            "title": "[LIVE-AUTH][PENDING] hermes-deals",
                        },
                        {
                            "id": 2,
                            "number": 43,
                            "title": "ordinary issue",
                        },
                    ]
                ).encode(),
            )
        raise AssertionError(url)


class P8PrepTests(unittest.TestCase):
    def _dummy_key(self, root: Path) -> Path:
        key = root / "key.pem"
        key.write_bytes(b"K" * 512)
        key.chmod(0o600)
        return key

    def test_config_binds_p7_identity_and_keeps_writes_disabled(self):
        config = load_dry_run_config(CONFIG)
        self.assertEqual(config.app_id, 4748870)
        self.assertEqual(config.installation_id, 157217641)
        self.assertEqual(config.authorization_repository, "rozkalnsandris/ops-workflows")
        self.assertEqual(config.authorization_repository_id, 1328835922)
        self.assertEqual(config.owner_id, 277435981)
        self.assertEqual(config.poll_interval_seconds, 120)
        self.assertFalse(config.mutation_dispatch_enabled)
        self.assertFalse(config.result_writer_enabled)

    def test_jwt_uses_server_time_and_five_minute_horizon(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._dummy_key(Path(tmp))
            now = datetime(2026, 8, 28, 10, 0, 0, tzinfo=timezone.utc)
            jwt = build_app_jwt(
                app_id=4748870,
                server_time=now,
                private_key=key,
                signer=lambda payload, _key: b"signature",
            )
        header, payload, _signature = jwt.split(".")
        self.assertEqual(_decode_segment(header), {"alg": "RS256", "typ": "JWT"})
        claims = _decode_segment(payload)
        self.assertEqual(claims["iss"], 4748870)
        self.assertEqual(claims["iat"], int(now.timestamp()) - 60)
        self.assertEqual(claims["exp"], int(now.timestamp()) + 300)

    def test_token_provider_revalidates_installation_and_mints_read_only_single_repo_token(self):
        config = load_dry_run_config(CONFIG)
        requester = FakeRequester()
        with tempfile.TemporaryDirectory() as tmp:
            key = self._dummy_key(Path(tmp))
            provider = GitHubAppInstallationTokenProvider(
                config=config,
                private_key=key,
                requester=requester,
                signer=lambda payload, _key: b"signature",
            )
            token = provider.get_installation_token()
        self.assertTrue(token.value.startswith("ghs_"))
        methods_paths = [(method, path) for method, path, _headers, _body in requester.calls]
        self.assertEqual(
            methods_paths,
            [
                ("GET", "/"),
                ("GET", "/app/installations/157217641"),
                ("POST", "/app/installations/157217641/access_tokens"),
            ],
        )
        body = json.loads(requester.calls[-1][3].decode())
        self.assertEqual(
            body,
            {"repository_ids": [1328835922], "permissions": {"issues": "read"}},
        )
        for _method, _path, headers, _body in requester.calls:
            authorization = headers.get("Authorization", "")
            self.assertNotIn(token.value, authorization)

    def test_installation_write_permission_fails_closed_before_token_mint(self):
        config = load_dry_run_config(CONFIG)
        requester = FakeRequester(write_permission=True)
        with tempfile.TemporaryDirectory() as tmp:
            key = self._dummy_key(Path(tmp))
            provider = GitHubAppInstallationTokenProvider(
                config=config,
                private_key=key,
                requester=requester,
                signer=lambda payload, _key: b"signature",
            )
            with self.assertRaisesRegex(AppAuthError, "write permission|Issues permission"):
                provider.get_installation_token()
        self.assertNotIn(
            ("POST", "/app/installations/157217641/access_tokens"),
            [(method, path) for method, path, _headers, _body in requester.calls],
        )

    def test_poller_reads_repository_and_candidates_but_cannot_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir(mode=0o700)
            result = poll_once(
                config_path=CONFIG,
                registry_path=REGISTRY,
                state_dir=state,
                credential_path="/unused/by/fake/provider",
                token_provider=StaticTokenProvider(),
                sender=PollSender(),
            )
            status = json.loads((state / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(result.result, "POLL_OK")
        self.assertEqual(result.candidate_count, 1)
        self.assertFalse(result.mutation_dispatch_enabled)
        self.assertFalse(result.production_mutation_started)
        self.assertFalse(status["mutation_dispatch_enabled"])
        self.assertFalse(status["result_writer_enabled"])
        self.assertFalse(status["production_mutation_started"])
        self.assertNotIn("body", status)
        self.assertNotIn("token", json.dumps(status).lower())

    def test_poller_conditional_304_remains_non_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir(mode=0o700)
            first = PollSender()
            poll_once(
                config_path=CONFIG,
                registry_path=REGISTRY,
                state_dir=state,
                credential_path="/unused",
                token_provider=StaticTokenProvider(),
                sender=first,
            )
            second = PollSender(not_modified=True)
            result = poll_once(
                config_path=CONFIG,
                registry_path=REGISTRY,
                state_dir=state,
                credential_path="/unused",
                token_provider=StaticTokenProvider(),
                sender=second,
            )
        self.assertEqual(result.result, "POLL_NOT_MODIFIED")
        self.assertIsNone(result.candidate_count)
        issue_call = next(row for row in second.calls if "/issues?state=open" in row[1])
        self.assertEqual(issue_call[2].get("If-None-Match"), '"p8"')

    def test_poller_does_not_parse_or_consume_disabled_registry_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            state.mkdir(mode=0o700)
            registry = root / "registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "execution_enabled": False,
                        "operations": [
                            {
                                "operation_id": "intentionally.invalid.for-p8",
                                "command": "must-never-be-interpreted",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            sender = PollSender()
            result = poll_once(
                config_path=CONFIG,
                registry_path=registry,
                state_dir=state,
                credential_path="/unused",
                token_provider=StaticTokenProvider(),
                sender=sender,
            )
        self.assertEqual(result.result, "POLL_OK")
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(len(sender.calls), 2)
        self.assertFalse(result.mutation_dispatch_enabled)
        self.assertFalse(result.production_mutation_started)

    def test_execution_enabled_registry_is_rejected_before_any_network_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            state.mkdir(mode=0o700)
            registry = root / "registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "execution_enabled": True,
                        "operations": [],
                    }
                ),
                encoding="utf-8",
            )
            sender = PollSender()
            with self.assertRaisesRegex(P8PollerError, "execution-disabled"):
                poll_once(
                    config_path=CONFIG,
                    registry_path=registry,
                    state_dir=state,
                    credential_path="/unused",
                    token_provider=StaticTokenProvider(),
                    sender=sender,
                )
        self.assertEqual(sender.calls, [])

    def test_poller_source_has_no_operation_normalization_or_adapter_bridge(self):
        source = POLLER_SOURCE.read_text(encoding="utf-8")
        for forbidden in (
            "load_registry(",
            "queue_normalizer",
            "normalize_ready_queue",
            "prepare_operation",
            "AdapterCatalog",
            ".exact_match(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_systemd_contract_uses_credential_sandbox_state_directory_and_timer(self):
        service = SERVICE.read_text(encoding="utf-8")
        timer = TIMER.read_text(encoding="utf-8")
        required = (
            "Type=oneshot",
            "User=rozkalns-deploy-executor",
            "Group=rozkalns-deploy-executor",
            "LoadCredential=github-app.pem:/etc/rozkalns-deploy-executor/github-app.pem",
            "StateDirectory=rozkalns-deploy-executor",
            "NoNewPrivileges=true",
            "ProtectSystem=strict",
            "ProtectHome=true",
            "CapabilityBoundingSet=",
            "AmbientCapabilities=",
            "ReadWritePaths=/var/lib/rozkalns-deploy-executor",
            "--credential %d/github-app.pem",
        )
        for marker in required:
            self.assertIn(marker, service)
        self.assertIn("OnUnitInactiveSec=2min", timer)
        self.assertIn("Unit=rozkalns-deploy-executor.service", timer)
        non_comments = "\n".join(
            line.lower() for line in service.splitlines() if not line.lstrip().startswith("#")
        )
        for forbidden in ("sudo", "/var/run/docker.sock", "bash -c", "sh -c"):
            self.assertNotIn(forbidden, non_comments)

    def test_systemd_offline_security_analysis_passes_threshold_when_available(self):
        binary = shutil.which("systemd-analyze")
        if binary is None:
            self.skipTest("systemd-analyze is unavailable")
        proc = subprocess.run(
            [
                binary,
                "security",
                "--offline=yes",
                "--threshold=20",
                "--no-pager",
                str(SERVICE),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Overall exposure level", proc.stdout)

    def test_installer_binds_exact_source_and_requires_clean_first_install(self):
        installer = INSTALLER.read_text(encoding="utf-8")
        required = (
            "--expected-source-sha",
            "EXPECTED_SOURCE_SHA",
            '/usr/bin/git -C "$REPO_ROOT" cat-file -e',
            '/usr/bin/git -C "$REPO_ROOT" rev-parse --verify HEAD',
            '/usr/bin/git -C "$REPO_ROOT" diff --quiet "$EXPECTED_SOURCE_SHA"',
            "existing_service_identity_requires_fresh_review",
            '"$INSTALL_ROOT"',
            '"$CONFIG_ROOT"',
            '"$STATE_ROOT"',
            "--threshold=20",
        )
        for marker in required:
            self.assertIn(marker, installer)

    def test_runtime_entrypoints_and_installer_expose_no_mutation_bridge(self):
        poller = POLLER.read_text(encoding="utf-8").lower()
        dispatcher = DISPATCHER.read_text(encoding="utf-8").lower()
        installer = INSTALLER.read_text(encoding="utf-8").lower()
        self.assertNotIn("subprocess", poller)
        self.assertNotIn("os.system", poller)
        self.assertIn("dispatch=disabled", dispatcher)
        self.assertNotIn("sudo ", installer)
        self.assertNotIn("docker.sock", installer)
        self.assertNotIn("bash -c", installer)
        self.assertNotIn("sh -c", installer)
        self.assertIn("mutation_dispatch_enabled=false", installer)
        self.assertIn("production_mutation_started=false", installer)

    def test_production_registry_matches_reviewed_canary_and_stays_disabled(self):
        production = json.loads(REGISTRY.read_text(encoding="utf-8"))
        reviewed = json.loads(CANARY_REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(production, reviewed)
        self.assertFalse(production["execution_enabled"])
        self.assertEqual(len(production["operations"]), 1)
        self.assertEqual(
            production["operations"][0]["operation_id"],
            "rozkalns-control-center.merge-postcanary-reconcile.v1",
        )


if __name__ == "__main__":
    unittest.main()
