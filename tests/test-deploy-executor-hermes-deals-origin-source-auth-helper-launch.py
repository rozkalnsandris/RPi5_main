from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.github_app_auth import RawResponse
from deploy_executor.hermes_deals_origin_adapter import (
    ADAPTER_ID,
    INVOCATION_BUDGET,
    OPERATION_ID,
    PULL_HELPER_ARGUMENTS,
    PULL_HELPER_CAPABILITY,
    PULL_HELPER_SOURCE_BLOB,
    REQUIRED_DEPENDENCIES,
    REQUIRED_EXCLUSIONS,
    ROLLBACK_POLICY,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)
from deploy_executor.hermes_deals_origin_dispatch_request import SCHEMA as REQUEST_SCHEMA
from deploy_executor.hermes_deals_origin_helper_launch import (
    FIXED_HELPER_ENV,
    HELPER_TIMEOUT_SECONDS,
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    HelperProcessResult,
    HermesDealsOriginHelperLaunchError,
    HermesDealsOriginOneShotHelperLauncher,
    source_readiness as launch_readiness,
)
from deploy_executor.hermes_deals_origin_privileged_consumer import (
    AUTHORIZATION_CLASS,
    HOST_EVIDENCE_SCHEMA,
    CanonicalHermesOriginEvidence,
)
from deploy_executor.hermes_deals_origin_privileged_dispatcher import INSTALLED_HELPER_PATH
from deploy_executor.hermes_deals_origin_source_auth import (
    build_hermes_deals_source_token_provider,
    source_readiness as auth_readiness,
)
from deploy_executor.p9_source_auth import (
    HERMES_DEALS_SOURCE_REPOSITORY,
    HERMES_DEALS_SOURCE_REPOSITORY_ID,
    SOURCE_APP_ID,
    SOURCE_INSTALLATION_ID,
)

SOURCE_SHA = "1" * 40
CURRENT_MAIN_SHA = "2" * 40
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"
AUTHORIZATION_CREATED_AT = "2026-09-04T07:26:48Z"
SERVER_DATE = "Fri, 04 Sep 2026 09:00:00 GMT"


def canonical_evidence() -> CanonicalHermesOriginEvidence:
    return CanonicalHermesOriginEvidence(
        authorization_issue_number=17,
        authorization_created_at=AUTHORIZATION_CREATED_AT,
        request_id=REQUEST_ID,
        queue_issue=41,
        source_repository=SOURCE_REPOSITORY,
        source_sha=SOURCE_SHA,
        current_main_sha=CURRENT_MAIN_SHA,
        source_ci_run_id=9001,
        operation_id=OPERATION_ID,
        adapter_id=ADAPTER_ID,
        target_alias=TARGET_ALIAS,
        authorization_class=AUTHORIZATION_CLASS,
        ordinary_live_all_eligible=False,
        rollback_policy=ROLLBACK_POLICY,
        mutation_budget=INVOCATION_BUDGET,
        exclusions=tuple(sorted(REQUIRED_EXCLUSIONS)),
        dependencies=tuple(sorted(REQUIRED_DEPENDENCIES)),
        isolated_authorization_surface_valid=True,
        authorization_owner_verified=True,
        authorization_ttl_valid=True,
        authorization_body_unchanged=True,
        authorization_replay_available=True,
        queue_ready=True,
        queue_binding_valid=True,
        registry_execution_enabled=False,
        source_reachable_from_main=True,
        source_ci_success=True,
        baseline_matched=True,
        prepared_execution_enabled=False,
        adapter_preflight_read_only=True,
        adapter_preflight_privileged_dispatch_ready=False,
    )


def host_evidence() -> dict[str, object]:
    return {
        "schema": HOST_EVIDENCE_SCHEMA,
        "evidence_id": "host-origin-audit-readonly-1",
        "operation_id": OPERATION_ID,
        "registered_source_sha": SOURCE_SHA,
        "registration_name": "origin-path-audit",
        "registration_owner_root": True,
        "registration_mode_0600": True,
        "dispatcher_identity_match": True,
        "probe_identity_match": True,
        "workflow_identity_match": True,
        "pull_helper_identity_match": True,
        "pull_helper_interface_match": True,
        "evidence_read_only": True,
        "evidence_fresh": True,
        "protected_values_included": False,
    }


class FakeCanonicalRevalidator:
    def __init__(self):
        self.calls: list[int] = []

    def revalidate(self, authorization_issue_number: int) -> CanonicalHermesOriginEvidence:
        self.calls.append(authorization_issue_number)
        return canonical_evidence()


class FakeHostEvidenceResolver:
    def __init__(self):
        self.calls: list[str] = []

    def resolve(self, *, source_sha: str) -> dict[str, object]:
        self.calls.append(source_sha)
        return host_evidence()


class FakeRunner:
    def __init__(self, *, returncode: int = 0, stdout: bytes | None = None, stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[tuple[tuple[str, str, str], dict[str, str], int, int, int]] = []

    def __call__(self, argv, *, env, timeout_seconds, stdout_limit, stderr_limit):
        self.calls.append(
            (argv, dict(env), timeout_seconds, stdout_limit, stderr_limit)
        )
        stdout = self.stdout
        if stdout is None:
            stdout = (
                f"CAPABILITY={PULL_HELPER_CAPABILITY} SOURCE_SHA={SOURCE_SHA} "
                f"AS_OF=2026-09-04 PROBE_EXIT_CODE={self.returncode}\n"
                "PRODUCTION_DATABASE_WRITE=false\n"
                "PRODUCTION_DEPLOYMENT=false\n"
                "RESTART_OR_CONFIGURATION_MUTATION=false\n"
            ).encode("ascii")
        return HelperProcessResult(
            returncode=self.returncode,
            stdout=stdout,
            stderr=self.stderr,
        )


class SourceAuthRequester:
    def __init__(self, *, installation_permissions=None, token_permissions=None, token_repositories=None):
        self.installation_permissions = installation_permissions or {
            "actions": "read",
            "contents": "read",
            "metadata": "read",
        }
        self.token_permissions = token_permissions or {
            "actions": "read",
            "contents": "read",
            "metadata": "read",
        }
        self.token_repositories = token_repositories or [
            {
                "id": HERMES_DEALS_SOURCE_REPOSITORY_ID,
                "full_name": HERMES_DEALS_SOURCE_REPOSITORY,
            }
        ]
        self.calls: list[tuple[str, str]] = []
        self.token_body = None

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path))
        if method == "GET" and path == "/repos/rozkalnsandris/hermes-deals/installation":
            return RawResponse(
                200,
                {"date": SERVER_DATE},
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
                    "permissions": self.installation_permissions,
                },
            )
        if method == "POST" and path == f"/app/installations/{SOURCE_INSTALLATION_ID}/access_tokens":
            self.token_body = json.loads(body.decode("utf-8"))
            return RawResponse(
                201,
                {"date": SERVER_DATE},
                {
                    "token": "ghs_" + "x" * 80,
                    "expires_at": "2026-09-04T10:00:00Z",
                    "repository_selection": "selected",
                    "permissions": self.token_permissions,
                    "repositories": self.token_repositories,
                },
            )
        raise AssertionError((method, path))


def request_payload(**extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "authorization_issue_number": 17,
    }
    value.update(extra)
    return value


class HermesDealsOriginSourceAuthHelperLaunchTests(unittest.TestCase):
    def test_source_provider_is_fixed_to_one_hermes_repository_and_read_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "source.pem"
            key.write_bytes(b"x" * 512)
            key.chmod(0o600)
            requester = SourceAuthRequester()
            provider = build_hermes_deals_source_token_provider(
                private_key=key,
                requester=requester,
                signer=lambda payload, path: b"signature",
            )
            first = provider.get_installation_token()
            second = provider.get_installation_token()

        self.assertIs(first, second)
        self.assertEqual(provider.repository, HERMES_DEALS_SOURCE_REPOSITORY)
        self.assertEqual(provider.repository_id, HERMES_DEALS_SOURCE_REPOSITORY_ID)
        self.assertEqual(
            requester.calls,
            [
                ("GET", "/repos/rozkalnsandris/hermes-deals/installation"),
                ("POST", f"/app/installations/{SOURCE_INSTALLATION_ID}/access_tokens"),
            ],
        )
        self.assertEqual(
            requester.token_body,
            {
                "repository_ids": [HERMES_DEALS_SOURCE_REPOSITORY_ID],
                "permissions": {"actions": "read", "contents": "read"},
            },
        )

    def test_source_provider_rejects_permission_or_repository_widening(self):
        cases = (
            {"installation_permissions": {"actions": "read", "contents": "read", "issues": "read"}},
            {"installation_permissions": {"actions": "write", "contents": "read", "metadata": "read"}},
            {"token_permissions": {"actions": "read", "contents": "write", "metadata": "read"}},
            {"token_permissions": {"actions": "read", "contents": "read", "issues": "read"}},
            {"token_repositories": [{"id": 1, "full_name": HERMES_DEALS_SOURCE_REPOSITORY}]},
            {"token_repositories": [{"id": HERMES_DEALS_SOURCE_REPOSITORY_ID, "full_name": "rozkalnsandris/other"}]},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                key = Path(tmp) / "source.pem"
                key.write_bytes(b"x" * 512)
                key.chmod(0o600)
                provider = build_hermes_deals_source_token_provider(
                    private_key=key,
                    requester=SourceAuthRequester(**kwargs),
                    signer=lambda payload, path: b"signature",
                )
                with self.assertRaises(Exception):
                    provider.get_installation_token()

    def test_launcher_revalidates_twice_then_emits_only_fixed_argv(self):
        canonical = FakeCanonicalRevalidator()
        host = FakeHostEvidenceResolver()
        runner = FakeRunner(returncode=1)
        launcher = HermesDealsOriginOneShotHelperLauncher(runner=runner)
        receipt = launcher.prepare_and_launch(
            request_payload(),
            canonical_revalidator=canonical,
            host_evidence_resolver=host,
        )

        self.assertEqual(canonical.calls, [17, 17])
        self.assertEqual(host.calls, [SOURCE_SHA])
        self.assertEqual(len(runner.calls), 1)
        argv, env, timeout, stdout_limit, stderr_limit = runner.calls[0]
        self.assertEqual(argv, (INSTALLED_HELPER_PATH, SOURCE_SHA, "2026-09-04"))
        self.assertEqual(env, FIXED_HELPER_ENV)
        self.assertEqual(timeout, HELPER_TIMEOUT_SECONDS)
        self.assertEqual(stdout_limit, MAX_STDOUT_BYTES)
        self.assertEqual(stderr_limit, MAX_STDERR_BYTES)
        self.assertEqual(receipt.helper_exit_code, 1)
        self.assertTrue(receipt.stdout_validated)
        self.assertFalse(receipt.production_mutation_started)

    def test_launcher_rejects_second_invocation_and_caller_authority_extensions(self):
        canonical = FakeCanonicalRevalidator()
        host = FakeHostEvidenceResolver()
        runner = FakeRunner()
        launcher = HermesDealsOriginOneShotHelperLauncher(runner=runner)
        launcher.prepare_and_launch(
            request_payload(),
            canonical_revalidator=canonical,
            host_evidence_resolver=host,
        )
        with self.assertRaises(HermesDealsOriginHelperLaunchError):
            launcher.prepare_and_launch(
                request_payload(),
                canonical_revalidator=canonical,
                host_evidence_resolver=host,
            )
        self.assertEqual(len(runner.calls), 1)

        for field in (
            "source_sha",
            "as_of",
            "helper_path",
            "path",
            "argv",
            "environment",
            "uid",
            "gid",
            "unit",
            "capability",
            "command",
            "shell",
            "output_path",
        ):
            with self.subTest(field=field):
                local_runner = FakeRunner()
                local_launcher = HermesDealsOriginOneShotHelperLauncher(runner=local_runner)
                with self.assertRaises(Exception):
                    local_launcher.prepare_and_launch(
                        request_payload(**{field: "untrusted"}),
                        canonical_revalidator=FakeCanonicalRevalidator(),
                        host_evidence_resolver=FakeHostEvidenceResolver(),
                    )
                self.assertEqual(local_runner.calls, [])

    def test_launcher_rejects_timeout_runner_failure_nonzero_and_output_drift(self):
        class RaisingRunner:
            def __call__(self, argv, **kwargs):
                raise TimeoutError("private runner detail")

        with self.assertRaises(HermesDealsOriginHelperLaunchError) as raised:
            HermesDealsOriginOneShotHelperLauncher(runner=RaisingRunner()).prepare_and_launch(
                request_payload(),
                canonical_revalidator=FakeCanonicalRevalidator(),
                host_evidence_resolver=FakeHostEvidenceResolver(),
            )
        self.assertNotIn("private runner detail", str(raised.exception))

        for runner in (
            FakeRunner(returncode=78),
            FakeRunner(stdout=b"x" * (MAX_STDOUT_BYTES + 1)),
            FakeRunner(stderr=b"unexpected"),
            FakeRunner(stdout=b"wrong\n"),
        ):
            with self.subTest(runner=runner):
                with self.assertRaises(HermesDealsOriginHelperLaunchError):
                    HermesDealsOriginOneShotHelperLauncher(runner=runner).prepare_and_launch(
                        request_payload(),
                        canonical_revalidator=FakeCanonicalRevalidator(),
                        host_evidence_resolver=FakeHostEvidenceResolver(),
                    )

    def test_source_contract_has_no_generic_command_or_shell_authority(self):
        source = (
            ROOT / "ops/lib/deploy_executor/hermes_deals_origin_helper_launch.py"
        ).read_text(encoding="utf-8")
        self.assertIn("shell=False", source)
        self.assertIn("INSTALLED_HELPER_PATH", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("bash -c", source)
        self.assertNotIn("sh -c", source)
        self.assertNotIn("os.system(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("sudo ", source)
        self.assertNotIn("systemctl ", source)
        self.assertNotIn("Popen(request", source)
        self.assertNotIn("Popen(plan", source)

    def test_source_readiness_keeps_runtime_and_wiring_unproven(self):
        auth = auth_readiness()
        self.assertTrue(auth["source_auth_composition_implemented"])
        self.assertEqual(auth["repository"], HERMES_DEALS_SOURCE_REPOSITORY)
        self.assertEqual(auth["repository_id"], HERMES_DEALS_SOURCE_REPOSITORY_ID)
        self.assertEqual(auth["requested_permissions"], {"actions": "read", "contents": "read"})
        self.assertEqual(auth["token_repository_count"], 1)
        self.assertFalse(auth["source_runtime_credential_proven"])
        self.assertFalse(auth["source_runtime_installation_proven"])
        self.assertFalse(auth["source_write_permission_required"])
        self.assertFalse(auth["permission_mutation_authorized"])
        self.assertFalse(auth["credential_mutation_authorized"])

        launch = launch_readiness()
        self.assertTrue(launch["helper_process_launch_implemented"])
        self.assertFalse(launch["helper_process_launch_wired"])
        self.assertEqual(launch["executable"], INSTALLED_HELPER_PATH)
        self.assertEqual(launch["argument_names"], PULL_HELPER_ARGUMENTS)
        self.assertFalse(launch["shell"])
        self.assertEqual(launch["invocation_budget"], 1)
        self.assertFalse(launch["caller_plan_authority"])
        self.assertTrue(launch["canonical_revalidation_required"])
        self.assertFalse(launch["production_mutation_started"])


if __name__ == "__main__":
    unittest.main()
