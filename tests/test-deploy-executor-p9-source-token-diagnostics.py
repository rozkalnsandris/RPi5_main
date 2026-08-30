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
    P9SourceTokenStageError,
    SOURCE_INSTALLATION_ID,
)

BASELINE_CLI = ROOT / "ops" / "bin" / "rozkalns-deploy-p9-control-baseline"


class Requester:
    def __init__(self, *, permission: str = "read", fail_install_request: bool = False):
        self.permission = permission
        self.fail_install_request = fail_install_request
        self.calls: list[tuple[str, str]] = []
        self.token_requests = 0

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path))
        date = "Sun, 30 Aug 2026 11:00:00 GMT"
        if method == "GET" and path == "/":
            return RawResponse(200, {"date": date}, {})
        if method == "GET" and path == f"/app/installations/{SOURCE_INSTALLATION_ID}":
            if self.fail_install_request:
                raise RuntimeError("private-inner-error-must-not-escape")
            return RawResponse(
                200,
                {"date": date},
                {
                    "id": SOURCE_INSTALLATION_ID,
                    "repository_selection": "selected",
                    "account": {"id": 277435981, "login": "rozkalnsandris"},
                    "permissions": {
                        "actions": self.permission,
                        "contents": "read",
                        "metadata": "read",
                    },
                },
            )
        if method == "POST" and path == f"/app/installations/{SOURCE_INSTALLATION_ID}/access_tokens":
            self.token_requests += 1
            request = json.loads(body.decode("utf-8"))
            self.request = request
            return RawResponse(
                201,
                {"date": date},
                {
                    "token": "ghs_" + "x" * 80,
                    "expires_at": "2026-08-30T12:00:00Z",
                    "permissions": {
                        "actions": "read",
                        "contents": "read",
                        "metadata": "read",
                    },
                    "repositories": [
                        {"id": 1329279953, "full_name": CONTROL_SOURCE_REPOSITORY}
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


class P9SourceTokenDiagnosticsTests(unittest.TestCase):
    def test_provider_mints_exactly_once_and_reuses_cached_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester()
            provider = _provider(tmp, requester)
            first = provider.get_installation_token()
            second = provider.get_installation_token()
            self.assertIs(first, second)
            self.assertEqual(requester.token_requests, 1)
            self.assertEqual(
                requester.request,
                {
                    "repository_ids": [1329279953],
                    "permissions": {"actions": "read", "contents": "read"},
                },
            )

    def test_installation_scope_failure_is_sanitized_and_stops_before_mint(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester(permission="write")
            provider = _provider(tmp, requester)
            with self.assertRaises(P9SourceTokenStageError) as raised:
                provider.get_installation_token()
            self.assertIsInstance(raised.exception, P9SourceAuthError)
            self.assertEqual(raised.exception.stage, "installation_scope")
            self.assertEqual(
                str(raised.exception),
                "source installation token provider failed stage=installation_scope",
            )
            self.assertEqual(requester.token_requests, 0)

    def test_request_failure_does_not_expose_inner_exception_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester(fail_install_request=True)
            provider = _provider(tmp, requester)
            with self.assertRaises(P9SourceTokenStageError) as raised:
                provider.get_installation_token()
            message = str(raised.exception)
            self.assertEqual(raised.exception.stage, "installation_request")
            self.assertEqual(
                message,
                "source installation token provider failed stage=installation_request",
            )
            self.assertNotIn("private-inner-error", message)
            self.assertEqual(requester.token_requests, 0)

    def test_arbitrary_failure_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            P9SourceTokenStageError("secret-derived-stage")

    def test_baseline_cli_primes_source_auth_before_d1_credential_read(self):
        source = BASELINE_CLI.read_text(encoding="utf-8")
        build_at = source.index("source_client = build_source_client()")
        prime_at = source.index("source_client.token_provider.get_installation_token()")
        d1_at = source.index("read_fixed_d1_token()")
        self.assertLess(build_at, prime_at)
        self.assertLess(prime_at, d1_at)


if __name__ == "__main__":
    unittest.main()
