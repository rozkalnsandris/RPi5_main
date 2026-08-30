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
    SOURCE_APP_ID,
    SOURCE_INSTALLATION_ID,
)

BASELINE_CLI = ROOT / "ops" / "bin" / "rozkalns-deploy-p9-control-baseline"
BASELINE_COLLECTOR = (
    ROOT / "ops" / "lib" / "deploy_executor" / "p9_control_postcanary_collector.py"
)
REPOSITORY_INSTALLATION_PATH = (
    "/repos/rozkalnsandris/rozkalns-control-center/installation"
)


class Requester:
    def __init__(
        self,
        *,
        installation_status: int = 200,
        installation_overrides: dict | None = None,
        installation_non_object: bool = False,
        token_status: int = 201,
        token_overrides: dict | None = None,
        fail_install_request: bool = False,
    ):
        self.installation_status = installation_status
        self.installation_overrides = installation_overrides or {}
        self.installation_non_object = installation_non_object
        self.token_status = token_status
        self.token_overrides = token_overrides or {}
        self.fail_install_request = fail_install_request
        self.calls: list[tuple[str, str]] = []
        self.token_requests = 0
        self.request = None

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path))
        date = "Sun, 30 Aug 2026 11:00:00 GMT"
        if method == "GET" and path == "/":
            return RawResponse(200, {"date": date}, {})
        if method == "GET" and path == REPOSITORY_INSTALLATION_PATH:
            if self.fail_install_request:
                raise RuntimeError("private-inner-error-must-not-escape")
            if self.installation_non_object:
                return RawResponse(
                    self.installation_status,
                    {"date": date},
                    ["private-installation-payload-must-not-escape"],
                )
            payload = {
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
            }
            payload.update(self.installation_overrides)
            if self.installation_status != 200:
                payload = {"message": "private-installation-response-must-not-escape"}
            return RawResponse(self.installation_status, {"date": date}, payload)
        if method == "POST" and path == f"/app/installations/{SOURCE_INSTALLATION_ID}/access_tokens":
            self.token_requests += 1
            self.request = json.loads(body.decode("utf-8"))
            payload = {
                "token": "ghs_" + "x" * 80,
                "expires_at": "2026-08-30T12:00:00Z",
                "repository_selection": "selected",
                "permissions": {
                    "actions": "read",
                    "contents": "read",
                    "metadata": "read",
                },
                "repositories": [
                    {"id": 1329279953, "full_name": CONTROL_SOURCE_REPOSITORY}
                ],
            }
            payload.update(self.token_overrides)
            if self.token_status != 201:
                payload = {"message": "private-token-response-must-not-escape"}
            return RawResponse(self.token_status, {"date": date}, payload)
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
    def _assert_stage_before_mint(
        self, requester: Requester, expected_stage: str
    ) -> P9SourceTokenStageError:
        with tempfile.TemporaryDirectory() as tmp:
            provider = _provider(tmp, requester)
            with self.assertRaises(P9SourceTokenStageError) as raised:
                provider.get_installation_token()
            self.assertIsInstance(raised.exception, P9SourceAuthError)
            self.assertEqual(raised.exception.stage, expected_stage)
            self.assertEqual(
                str(raised.exception),
                f"source installation token provider failed stage={expected_stage}",
            )
            if expected_stage.startswith("installation"):
                self.assertEqual(requester.token_requests, 0)
            return raised.exception

    def test_provider_proves_repository_installation_then_mints_once_and_reuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester()
            provider = _provider(tmp, requester)
            first = provider.get_installation_token()
            second = provider.get_installation_token()
            self.assertIs(first, second)
            self.assertEqual(requester.token_requests, 1)
            self.assertIn(("GET", REPOSITORY_INSTALLATION_PATH), requester.calls)
            self.assertNotIn(
                ("GET", f"/app/installations/{SOURCE_INSTALLATION_ID}"),
                requester.calls,
            )
            self.assertLess(
                requester.calls.index(("GET", REPOSITORY_INSTALLATION_PATH)),
                requester.calls.index(
                    ("POST", f"/app/installations/{SOURCE_INSTALLATION_ID}/access_tokens")
                ),
            )
            self.assertEqual(
                requester.request,
                {
                    "repository_ids": [1329279953],
                    "permissions": {"actions": "read", "contents": "read"},
                },
            )

    def test_repository_installation_404_is_public_safe_and_stops_before_mint(self):
        requester = Requester(installation_status=404)
        error = self._assert_stage_before_mint(requester, "installation_not_found")
        self.assertNotIn("private-installation-response", str(error))
        self.assertNotIn("404", str(error))

    def test_repository_installation_other_non_200_is_public_safe(self):
        requester = Requester(installation_status=403)
        error = self._assert_stage_before_mint(requester, "installation_status")
        self.assertNotIn("private-installation-response", str(error))
        self.assertNotIn("403", str(error))

    def test_repository_installation_non_object_is_public_safe(self):
        requester = Requester(installation_non_object=True)
        error = self._assert_stage_before_mint(requester, "installation_payload")
        self.assertNotIn("private-installation-payload", str(error))

    def test_repository_installation_identity_and_scope_fail_closed_before_mint(self):
        invalid_installations = (
            {"id": SOURCE_INSTALLATION_ID + 1},
            {"app_id": SOURCE_APP_ID + 1},
            {"target_id": 1},
            {"target_type": "Organization"},
            {"repository_selection": "all"},
            {"account": {"id": 1, "login": "rozkalnsandris", "type": "User"}},
            {"account": {"id": 277435981, "login": "other", "type": "User"}},
            {"account": {"id": 277435981, "login": "rozkalnsandris", "type": "Bot"}},
            {"permissions": {"contents": "read", "metadata": "read"}},
            {"permissions": {"actions": "write", "contents": "read", "metadata": "read"}},
            {
                "permissions": {
                    "actions": "read",
                    "contents": "read",
                    "metadata": "read",
                    "issues": "read",
                }
            },
        )
        for overrides in invalid_installations:
            with self.subTest(overrides=overrides):
                requester = Requester(installation_overrides=overrides)
                self._assert_stage_before_mint(requester, "installation_scope")

    def test_request_failure_does_not_expose_inner_exception_text(self):
        requester = Requester(fail_install_request=True)
        error = self._assert_stage_before_mint(requester, "installation_request")
        self.assertNotIn("private-inner-error", str(error))

    def test_token_mint_response_failure_is_sanitized(self):
        requester = Requester(token_status=422)
        error = self._assert_stage_before_mint(requester, "token_response")
        self.assertEqual(requester.token_requests, 1)
        self.assertNotIn("private-token-response", str(error))

    def test_token_scope_failures_are_sanitized(self):
        invalid_tokens = (
            {"repository_selection": "all"},
            {"permissions": {"actions": "read", "contents": "write", "metadata": "read"}},
            {
                "permissions": {
                    "actions": "read",
                    "contents": "read",
                    "metadata": "read",
                    "issues": "read",
                }
            },
            {"repositories": []},
            {
                "repositories": [
                    {"id": 1329279953, "full_name": "rozkalnsandris/not-control-center"}
                ]
            },
        )
        for overrides in invalid_tokens:
            with self.subTest(overrides=overrides):
                requester = Requester(token_overrides=overrides)
                self._assert_stage_before_mint(requester, "token_scope")
                self.assertEqual(requester.token_requests, 1)

    def test_arbitrary_failure_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            P9SourceTokenStageError("secret-derived-stage")

    def test_baseline_cli_primes_source_auth_before_failfast_collector_d1_boundary(self):
        cli_source = BASELINE_CLI.read_text(encoding="utf-8")
        build_at = cli_source.index("source_client = build_source_client()")
        prime_at = cli_source.index(
            "source_client.token_provider.get_installation_token()"
        )
        collect_at = cli_source.index("observation = collect_control_postcanary_observation(")
        self.assertLess(build_at, prime_at)
        self.assertLess(prime_at, collect_at)

        collector_source = BASELINE_COLLECTOR.read_text(encoding="utf-8")
        collect_fn = collector_source[
            collector_source.index("def collect_control_postcanary_observation(") :
            collector_source.index("def build_source_client(")
        ]
        target_gate_at = collect_fn.index(
            "target_failure = target_github_evidence_failure_code(target_evidence)"
        )
        d1_at = collect_fn.index(
            "FixedD1ReadClient(api_token=read_fixed_d1_token())"
        )
        self.assertLess(target_gate_at, d1_at)


if __name__ == "__main__":
    unittest.main()
