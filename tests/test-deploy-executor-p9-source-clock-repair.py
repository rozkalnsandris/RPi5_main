from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.github_app_auth import RawResponse
from deploy_executor.p9_source_auth import (
    CONTROL_SOURCE_REPOSITORY,
    P9SourceInstallationTokenProvider,
    P9SourceTokenStageError,
    SOURCE_APP_ID,
    SOURCE_INSTALLATION_ID,
)

SOURCE_AUTH = ROOT / "ops" / "lib" / "deploy_executor" / "p9_source_auth.py"
UPGRADE_OPERATOR = (
    ROOT / "scripts" / "install-deploy-executor-p9-gate-d-source-clock-upgrade.py"
)
REPOSITORY_INSTALLATION_PATH = (
    "/repos/rozkalnsandris/rozkalns-control-center/installation"
)
TOKEN_PATH = f"/app/installations/{SOURCE_INSTALLATION_ID}/access_tokens"
SERVER_DATE = "Mon, 31 Aug 2026 15:00:00 GMT"


class Requester:
    def __init__(self, *, installation_headers: dict[str, str] | None = None):
        self.installation_headers = (
            {"date": SERVER_DATE}
            if installation_headers is None
            else installation_headers
        )
        self.calls: list[tuple[str, str]] = []
        self.token_requests = 0
        self.token_request_body: dict | None = None

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path))
        if path == "/":
            raise AssertionError("unauthenticated GitHub root clock probe must not occur")
        if method == "GET" and path == REPOSITORY_INSTALLATION_PATH:
            return RawResponse(
                200,
                self.installation_headers,
                {
                    "id": SOURCE_INSTALLATION_ID,
                    "app_id": SOURCE_APP_ID,
                    "target_id": 277435981,
                    "target_type": "User",
                    "repository_selection": "selected",
                    "account": {
                        "id": 277435981,
                        "login": "rozkalnsandris",
                        "type": "User",
                    },
                    "permissions": {
                        "actions": "read",
                        "contents": "read",
                        "metadata": "read",
                    },
                },
            )
        if method == "POST" and path == TOKEN_PATH:
            self.token_requests += 1
            self.token_request_body = json.loads(body.decode("utf-8"))
            return RawResponse(
                201,
                {"date": SERVER_DATE},
                {
                    "token": "ghs_" + "x" * 80,
                    "expires_at": "2026-08-31T16:00:00Z",
                    "repository_selection": "selected",
                    "permissions": {
                        "actions": "read",
                        "contents": "read",
                        "metadata": "read",
                    },
                    "repositories": [
                        {
                            "id": 1329279953,
                            "full_name": CONTROL_SOURCE_REPOSITORY,
                        }
                    ],
                },
            )
        raise AssertionError((method, path))


def _provider(tmp: str, requester: Requester) -> P9SourceInstallationTokenProvider:
    key = Path(tmp) / "key.pem"
    key.write_bytes(b"x" * 512)
    key.chmod(0o600)
    return P9SourceInstallationTokenProvider(
        repository=CONTROL_SOURCE_REPOSITORY,
        private_key=key,
        requester=requester,
        signer=lambda payload, path: b"signature",
    )


class P9SourceClockRepairTests(unittest.TestCase):
    def test_provider_has_no_unauthenticated_root_probe_and_mints_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester()
            provider = _provider(tmp, requester)
            first = provider.get_installation_token()
            second = provider.get_installation_token()

        self.assertIs(first, second)
        self.assertEqual(
            requester.calls,
            [
                ("GET", REPOSITORY_INSTALLATION_PATH),
                ("POST", TOKEN_PATH),
            ],
        )
        self.assertEqual(requester.token_requests, 1)
        self.assertEqual(
            requester.token_request_body,
            {
                "repository_ids": [1329279953],
                "permissions": {"actions": "read", "contents": "read"},
            },
        )

    def test_authenticated_installation_date_is_required_before_mint(self):
        for headers in ({}, {"date": "not-a-date"}):
            with self.subTest(headers=headers):
                with tempfile.TemporaryDirectory() as tmp:
                    requester = Requester(installation_headers=headers)
                    provider = _provider(tmp, requester)
                    with self.assertRaises(P9SourceTokenStageError) as raised:
                        provider.get_installation_token()
                self.assertEqual(raised.exception.stage, "installation_clock")
                self.assertEqual(requester.token_requests, 0)
                self.assertEqual(
                    requester.calls,
                    [("GET", REPOSITORY_INSTALLATION_PATH)],
                )

    def test_source_contract_uses_local_utc_only_for_jwt_then_server_date_for_token(self):
        source = SOURCE_AUTH.read_text(encoding="utf-8")
        provider_fn = source[source.index("    def get_installation_token(self)") :]
        self.assertIn("local_now = datetime.now(timezone.utc)", provider_fn)
        self.assertIn("server_time=local_now", provider_fn)
        self.assertNotIn('self.requester("GET", "/"', provider_fn)
        self.assertIn("server_now = _server_time(installation_response.headers)", provider_fn)
        self.assertIn('P9SourceTokenStageError("installation_clock")', provider_fn)
        self.assertIn("now=server_now", provider_fn)
        stage_block = source[
            source.index("SOURCE_TOKEN_SAFE_STAGES") : source.index("class P9SourceAuthError")
        ]
        self.assertNotIn('"clock_request"', stage_block)
        self.assertNotIn('"clock_response"', stage_block)
        self.assertIn('"installation_clock"', stage_block)

    def test_one_target_upgrade_contract_is_fail_closed(self):
        namespace = runpy.run_path(str(UPGRADE_OPERATOR))
        target = namespace["TARGET"]
        self.assertEqual(
            target.source_path,
            "ops/lib/deploy_executor/p9_source_auth.py",
        )
        self.assertEqual(
            str(target.target_path),
            "/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py",
        )
        self.assertEqual(
            target.old_blob_sha,
            "1ad70a5c462bce8284eacd50d9af92b5786fa778",
        )
        self.assertEqual(target.mode, 0o644)

        source = UPGRADE_OPERATOR.read_text(encoding="utf-8")
        self.assertEqual(source.count("reviewed = _preflight(args.expected_sha)"), 2)
        self.assertIn("os.O_NOFOLLOW", source)
        self.assertIn("path_now.st_dev, path_now.st_ino", source)
        self.assertLess(source.index("path_now.st_dev"), source.index("os.ftruncate(fd, 0)"))
        self.assertIn('print("TARGETS_REPLACED=1")', source)
        self.assertIn('print("SOURCE_AUTH_TOUCHED=YES")', source)
        self.assertIn('print("CREDENTIAL_READ=NO")', source)
        self.assertIn('print("BASELINE_COLLECTION=NO")', source)
        self.assertIn('print("P9_EXECUTION=NO")', source)
        self.assertIn('print("ROLLBACK_PATH=NO")', source)
        self.assertIn('print("RETRY_PATH=NO")', source)


if __name__ == "__main__":
    unittest.main()
