from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.github_app_auth import RawResponse
from deploy_executor.p9_runtime import (
    EXECUTOR_APP_ID,
    EXECUTOR_INSTALLATION_ID,
    OWNER_TYPE,
    P9ExecutorInstallationTokenProvider,
    P9RuntimeError,
    build_p9_read_clients,
)
from deploy_executor.protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    OWNER_USER_ID,
    QUEUE_REPOSITORY,
    QUEUE_REPOSITORY_ID,
)
from deploy_executor.transport import API_VERSION


SERVER_TIME = datetime(2026, 8, 31, 16, 0, tzinfo=timezone.utc)
DATE_HEADER = "Mon, 31 Aug 2026 16:00:00 GMT"


def _surface():
    return SimpleNamespace(
        authorization_repository=AUTHORIZATION_REPOSITORY,
        authorization_repository_id=AUTHORIZATION_REPOSITORY_ID,
        accepted_repository_id=AUTHORIZATION_REPOSITORY_ID,
        queue_repository=QUEUE_REPOSITORY,
        queue_repository_id=QUEUE_REPOSITORY_ID,
        owner_user_id=OWNER_USER_ID,
        activation_enabled=False,
        runtime_binding_ready=False,
        host_wiring_enabled=False,
        production_mutation_enabled=False,
    )


class Requester:
    def __init__(
        self,
        *,
        repository: str,
        repository_id: int,
        date_header: str | None = DATE_HEADER,
        installation_id: int = EXECUTOR_INSTALLATION_ID,
        app_id: int = EXECUTOR_APP_ID,
        owner_id: int = OWNER_USER_ID,
        target_type: str = OWNER_TYPE,
        account_type: str = OWNER_TYPE,
        permission: str = "read",
        token_repository_id: int | None = None,
    ):
        self.repository = repository
        self.repository_id = repository_id
        self.date_header = date_header
        self.installation_id = installation_id
        self.app_id = app_id
        self.owner_id = owner_id
        self.target_type = target_type
        self.account_type = account_type
        self.permission = permission
        self.token_repository_id = (
            repository_id if token_repository_id is None else token_repository_id
        )
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path, dict(headers), body))
        owner, name = self.repository.split("/", 1)
        if method == "GET" and path == f"/repos/{owner}/{name}/installation":
            response_headers = {}
            if self.date_header is not None:
                response_headers["date"] = self.date_header
            return RawResponse(
                200,
                response_headers,
                {
                    "id": self.installation_id,
                    "app_id": self.app_id,
                    "target_id": self.owner_id,
                    "target_type": self.target_type,
                    "repository_selection": "selected",
                    "account": {
                        "id": self.owner_id,
                        "login": "rozkalnsandris",
                        "type": self.account_type,
                    },
                    "permissions": {
                        "issues": self.permission,
                        "metadata": "read",
                    },
                },
            )
        if (
            method == "POST"
            and path == f"/app/installations/{EXECUTOR_INSTALLATION_ID}/access_tokens"
        ):
            return RawResponse(
                201,
                {"date": DATE_HEADER},
                {
                    "token": "ghs_" + "x" * 80,
                    "expires_at": "2026-08-31T17:00:00Z",
                    "permissions": {
                        "issues": "read",
                        "metadata": "read",
                    },
                    "repositories": [
                        {
                            "id": self.token_repository_id,
                            "full_name": self.repository,
                        }
                    ],
                },
            )
        raise AssertionError((method, path))


class P9ExecutorAuthRepairTests(unittest.TestCase):
    def _key(self, directory: str) -> Path:
        key = Path(directory) / "executor.pem"
        key.write_bytes(b"x" * 512)
        key.chmod(0o600)
        return key

    def _provider(self, directory: str, requester: Requester):
        return P9ExecutorInstallationTokenProvider(
            repository=requester.repository,
            private_key=self._key(directory),
            requester=requester,
            signer=lambda _payload, _path: b"signature",
            clock=lambda: SERVER_TIME,
        )

    def test_authorization_token_uses_exact_repository_probe_and_is_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester(
                repository=AUTHORIZATION_REPOSITORY,
                repository_id=AUTHORIZATION_REPOSITORY_ID,
            )
            provider = self._provider(tmp, requester)

            first = provider.get_installation_token()
            second = provider.get_installation_token()

            self.assertIs(first, second)
            self.assertEqual(len(requester.calls), 2)
            self.assertFalse(any(path == "/" for _, path, _, _ in requester.calls))
            self.assertEqual(
                requester.calls[0][0:2],
                (
                    "GET",
                    f"/repos/{AUTHORIZATION_REPOSITORY}/installation",
                ),
            )
            self.assertEqual(
                requester.calls[1][0:2],
                (
                    "POST",
                    f"/app/installations/{EXECUTOR_INSTALLATION_ID}/access_tokens",
                ),
            )
            self.assertEqual(
                requester.calls[0][2]["X-GitHub-Api-Version"],
                API_VERSION,
            )
            mint = json.loads(requester.calls[1][3].decode("utf-8"))
            self.assertEqual(mint["repository_ids"], [AUTHORIZATION_REPOSITORY_ID])
            self.assertEqual(mint["permissions"], {"issues": "read"})

    def test_queue_token_uses_exact_repository_probe_and_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester(
                repository=QUEUE_REPOSITORY,
                repository_id=QUEUE_REPOSITORY_ID,
            )
            provider = self._provider(tmp, requester)

            provider.get_installation_token()

            self.assertEqual(
                requester.calls[0][0:2],
                ("GET", f"/repos/{QUEUE_REPOSITORY}/installation"),
            )
            mint = json.loads(requester.calls[1][3].decode("utf-8"))
            self.assertEqual(mint["repository_ids"], [QUEUE_REPOSITORY_ID])
            self.assertEqual(mint["permissions"], {"issues": "read"})

    def test_missing_authenticated_date_fails_before_mint(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester(
                repository=AUTHORIZATION_REPOSITORY,
                repository_id=AUTHORIZATION_REPOSITORY_ID,
                date_header=None,
            )
            provider = self._provider(tmp, requester)

            with self.assertRaises(P9RuntimeError):
                provider.get_installation_token()

            self.assertEqual(len(requester.calls), 1)
            self.assertEqual(requester.calls[0][0], "GET")

    def test_installation_identity_and_permission_drift_fail_before_mint(self):
        cases = (
            {"installation_id": EXECUTOR_INSTALLATION_ID + 1},
            {"app_id": EXECUTOR_APP_ID + 1},
            {"owner_id": OWNER_USER_ID + 1},
            {"target_type": "Organization"},
            {"account_type": "Bot"},
            {"permission": "write"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as tmp:
                requester = Requester(
                    repository=AUTHORIZATION_REPOSITORY,
                    repository_id=AUTHORIZATION_REPOSITORY_ID,
                    **overrides,
                )
                provider = self._provider(tmp, requester)

                with self.assertRaises(Exception):
                    provider.get_installation_token()

                self.assertEqual(len(requester.calls), 1)
                self.assertEqual(requester.calls[0][0], "GET")

    def test_token_repository_scope_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester(
                repository=AUTHORIZATION_REPOSITORY,
                repository_id=AUTHORIZATION_REPOSITORY_ID,
                token_repository_id=QUEUE_REPOSITORY_ID,
            )
            provider = self._provider(tmp, requester)

            with self.assertRaises(Exception):
                provider.get_installation_token()

            self.assertEqual(len(requester.calls), 2)

    def test_unknown_executor_repository_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            requester = Requester(
                repository="rozkalnsandris/RPi5_main",
                repository_id=1323383044,
            )
            with self.assertRaises(P9RuntimeError):
                self._provider(tmp, requester)
            self.assertEqual(requester.calls, [])

    def test_build_p9_clients_uses_distinct_cached_capability_providers(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._key(tmp)

            def should_not_request(*_args, **_kwargs):
                raise AssertionError("network is not part of this construction test")

            clients = build_p9_read_clients(
                auth_surface=_surface(),
                private_key=key,
                requester=should_not_request,
                signer=lambda _payload, _path: b"signature",
            )

            auth_provider = clients.authorization.token_provider
            queue_provider = clients.queue.token_provider
            self.assertIsInstance(auth_provider, P9ExecutorInstallationTokenProvider)
            self.assertIsInstance(queue_provider, P9ExecutorInstallationTokenProvider)
            self.assertIsNot(auth_provider, queue_provider)
            self.assertEqual(auth_provider.repository, AUTHORIZATION_REPOSITORY)
            self.assertEqual(queue_provider.repository, QUEUE_REPOSITORY)


if __name__ == "__main__":
    unittest.main()
