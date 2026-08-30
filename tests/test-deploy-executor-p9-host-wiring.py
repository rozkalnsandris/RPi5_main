from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.github_app_auth import RawResponse
from deploy_executor.p9_source_auth import (
    CONTROL_SOURCE_REPOSITORY,
    P9SourceAuthError,
    P9SourceInstallationTokenProvider,
    SOURCE_APP_ID,
    SOURCE_INSTALLATION_ID,
)


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
        self.assertIn("StateStore(state_db)", source)

    def test_installer_preserves_p8_service_and_requires_fresh_roots(self):
        installer = (ROOT / "scripts" / "install-deploy-executor-p9-runtime.sh").read_text(encoding="utf-8")
        self.assertNotIn("systemctl", installer)
        self.assertNotIn("useradd", installer)
        self.assertNotIn("groupadd", installer)
        self.assertIn("refusing non-transactional reinstall", installer)
        self.assertIn("P9_RUNTIME_ACTIVE=NO", installer)
        self.assertIn("P9_EVIDENCE_PRESENT=NO", installer)


if __name__ == "__main__":
    unittest.main()
