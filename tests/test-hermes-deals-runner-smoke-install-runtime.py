from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_runner_smoke_install import (  # noqa: E402
    HELPER_SHA256,
    INSTALL_TARGET_ALIAS,
    LIVE_GATE_ID,
    OPERATION_ID,
    REGISTRATION_SHA256,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    SOURCE_SHA,
)
from deploy_executor.hermes_deals_runner_smoke_install_consumer import (  # noqa: E402
    prepare_install_live_envelope,
)
from deploy_executor.hermes_deals_runner_smoke_install_runtime import (  # noqa: E402
    INSTALL_BASELINE_RESOLVER_ID,
    INSTALL_DEPENDENCIES,
    INSTALL_EXCLUSIONS,
    INSTALL_MUTATION_BUDGET,
    INSTALL_REPOSITORY_ENTRYPOINT,
    RPI5_MAIN_REPOSITORY,
    RPI5_MAIN_REPOSITORY_ID,
    ConcreteRunnerSmokeInstallReplayAuthority,
    ConcreteRunnerSmokeInstallRevalidator,
    FixedPublicRpi5MainReadClient,
    RunnerSmokeInstallRuntimeComposition,
    RunnerSmokeInstallRuntimeError,
    _fixed_install_registry,
    build_runner_smoke_install_runtime,
    source_readiness,
)
from deploy_executor.p9_isolated_auth_surface import load_contract  # noqa: E402
from deploy_executor.p9_runtime import P9ExecutorInstallationTokenProvider  # noqa: E402
from deploy_executor.p9_source_auth import P9SourceInstallationTokenProvider  # noqa: E402
from deploy_executor.protocol import (  # noqa: E402
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    QUEUE_REPOSITORY,
    QUEUE_REPOSITORY_ID,
)
from deploy_executor.queue_normalizer import normalize_ready_queue  # noqa: E402
from deploy_executor.transport import GitHubRestClient, HTTPResponse, InstallationToken  # noqa: E402

AUTHORIZATION_ISSUE = 73
QUEUE_ISSUE = 91
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"
RPI5_SHA = "a" * 40
SERVER_DATETIME = datetime(2026, 9, 15, 6, 20, tzinfo=timezone.utc)
SERVER_DATE = "Tue, 15 Sep 2026 06:20:00 GMT"
AUTH_CREATED = "2026-09-15T06:19:55Z"
SURFACE_PATH = ROOT / "ops/deploy/executor-p9-isolated-auth-surface.json"


def _queue_issue(*, target_alias: str = INSTALL_TARGET_ALIAS) -> dict[str, object]:
    fields = {
        "source_repository": f"`{SOURCE_REPOSITORY}`",
        "exact_git_sha_or_waiting_merge": f"`{SOURCE_SHA}`",
        "source_pr_or_issue_if_applicable": "`RPi5_main#546`",
        "target_alias": f"`{target_alias}`",
        "execution_location_class": "`trusted-home-host`",
        "repository_entrypoint": f"`{INSTALL_REPOSITORY_ENTRYPOINT}`",
        "expected_baseline_when_observable": f"`{INSTALL_BASELINE_RESOLVER_ID}`",
        "read_only_preflight": "`required` exact source/CI plus host ABSENT/EXACT observation",
        "verification_and_reconciliation": "`fail-closed` exact postcondition only",
        "allowed_mutation_categories_and_limits": "`fixed-install-budget-v1` no caller selectors",
        "explicit_exclusions": "`strict` no helper invocation or unrelated host mutation",
        "dependencies_if_any": "`RPi5_main#546` plus reviewed immutable source identities",
        "deploy_class_and_extra_owner_gate_requirement": "`STRICT_LIVE_AUTH_REQUIRED` owner LIVE-AUTH required",
    }
    body = "## Queue contract\n" + "\n".join(
        f"- **{key}:** {value}" for key, value in fields.items()
    )
    return {
        "id": 7001,
        "number": QUEUE_ISSUE,
        "repository_url": f"https://api.github.com/repos/{QUEUE_REPOSITORY}",
        "state": "open",
        "title": "[DEPLOY-QUEUE][READY] Runner-smoke install fixture",
        "body": body,
        "user": {"id": 277435981, "type": "User"},
        "performed_via_github_app": None,
    }


def _authorization_issue(
    *,
    app_authored: bool = False,
    created_at: str = AUTH_CREATED,
    request_id: str = REQUEST_ID,
    dependency_drift: bool = False,
) -> dict[str, object]:
    normalized = normalize_ready_queue(
        _queue_issue(),
        repository_full_name=QUEUE_REPOSITORY,
        registry=_fixed_install_registry(),
    ).as_protocol_queue()
    payload = {
        "schema": "rozkalns.live-auth.v1",
        "request_id": request_id,
        "queue_repository": normalized["repository"],
        "queue_issue": normalized["issue_number"],
        "source_repository": normalized["source_repository"],
        "source_sha": normalized["source_sha"],
        "target_alias": normalized["target_alias"],
        "operation_id": normalized["operation_id"],
        "expected_baseline": normalized["expected_baseline"],
        "mutation_budget": normalized["mutation_budget"],
        "rollback_policy": normalized["rollback_policy"],
        "exclusions": normalized["exclusions"],
        "dependencies": normalized["dependencies"],
    }
    if dependency_drift:
        payload["dependencies"] = list(payload["dependencies"]) + ["helper-sha256:" + "0" * 64]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "id": 8001,
        "number": AUTHORIZATION_ISSUE,
        "repository_url": f"https://api.github.com/repos/{AUTHORIZATION_REPOSITORY}",
        "state": "open",
        "title": f"[LIVE-AUTH][PENDING] {INSTALL_TARGET_ALIAS}",
        "created_at": created_at,
        "body": (
            "Runner-smoke install fixture.\n\n"
            "<!-- rozkalns-live-auth:v1 -->\n"
            f"```json\n{canonical}\n```\n"
            "<!-- /rozkalns-live-auth:v1 -->"
        ),
        "user": {"id": 277435981, "type": "User", "login": "rozkalnsandris"},
        "performed_via_github_app": (
            {"id": 1144995, "slug": "chatgpt-codex-connector"} if app_authored else None
        ),
    }


class FixtureSender:
    def __init__(
        self,
        *,
        app_authored: bool = False,
        expired: bool = False,
        queue_target_drift: bool = False,
        hermes_ci_success: bool = True,
        rpi5_ci_success: bool = True,
        body_refetch_drift: bool = False,
        dependency_drift: bool = False,
    ):
        self.app_authored = app_authored
        self.expired = expired
        self.queue_target_drift = queue_target_drift
        self.hermes_ci_success = hermes_ci_success
        self.rpi5_ci_success = rpi5_ci_success
        self.body_refetch_drift = body_refetch_drift
        self.dependency_drift = dependency_drift
        self.auth_reads = 0
        self.calls: list[str] = []

    def send(self, *, method: str, url: str, headers: object) -> HTTPResponse:
        if method != "GET":
            raise AssertionError("runtime source validation may issue only GET requests")
        parsed = urlsplit(url)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        self.calls.append(path)
        if path == f"/repos/{AUTHORIZATION_REPOSITORY}":
            value: object = {"id": AUTHORIZATION_REPOSITORY_ID, "full_name": AUTHORIZATION_REPOSITORY}
        elif path == f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{AUTHORIZATION_ISSUE}":
            self.auth_reads += 1
            request_id = REQUEST_ID
            if self.body_refetch_drift and self.auth_reads > 1:
                request_id = "223e4567-e89b-42d3-a456-426614174000"
            created = "2026-09-15T06:00:00Z" if self.expired else AUTH_CREATED
            value = _authorization_issue(
                app_authored=self.app_authored,
                created_at=created,
                request_id=request_id,
                dependency_drift=self.dependency_drift,
            )
        elif path == f"/repos/{QUEUE_REPOSITORY}":
            value = {"id": QUEUE_REPOSITORY_ID, "full_name": QUEUE_REPOSITORY}
        elif path == f"/repos/{QUEUE_REPOSITORY}/issues/{QUEUE_ISSUE}":
            value = _queue_issue(target_alias="wrong-install-target" if self.queue_target_drift else INSTALL_TARGET_ALIAS)
        elif path == f"/repos/{SOURCE_REPOSITORY}":
            value = {"id": SOURCE_REPOSITORY_ID, "full_name": SOURCE_REPOSITORY, "default_branch": "main"}
        elif path == f"/repos/{SOURCE_REPOSITORY}/branches/main":
            value = {"commit": {"sha": SOURCE_SHA}}
        elif path.startswith(f"/repos/{SOURCE_REPOSITORY}/actions/workflows/ci.yml/runs?"):
            value = {"workflow_runs": [{
                "id": 9101,
                "head_sha": SOURCE_SHA,
                "head_branch": "main",
                "status": "completed",
                "conclusion": "success" if self.hermes_ci_success else "failure",
            }]}
        elif path == f"/repos/{SOURCE_REPOSITORY}/actions/runs/9101/jobs?filter=latest&per_page=100":
            value = {"jobs": [{"status": "completed", "conclusion": "success"}]}
        elif path == f"/repos/{RPI5_MAIN_REPOSITORY}":
            value = {"id": RPI5_MAIN_REPOSITORY_ID, "full_name": RPI5_MAIN_REPOSITORY, "default_branch": "main"}
        elif path == f"/repos/{RPI5_MAIN_REPOSITORY}/branches/main":
            value = {"commit": {"sha": RPI5_SHA}}
        elif path.startswith(f"/repos/{RPI5_MAIN_REPOSITORY}/actions/workflows/validate.yml/runs?"):
            value = {"workflow_runs": [{
                "id": 9201,
                "head_sha": RPI5_SHA,
                "head_branch": "main",
                "status": "completed",
                "conclusion": "success" if self.rpi5_ci_success else "failure",
            }]}
        elif path == f"/repos/{RPI5_MAIN_REPOSITORY}/actions/runs/9201/jobs?filter=latest&per_page=100":
            value = {"jobs": [{"status": "completed", "conclusion": "success"}]}
        else:
            raise AssertionError(path)
        return HTTPResponse(
            status=200,
            headers={"date": SERVER_DATE},
            body=json.dumps(value, separators=(",", ":")).encode("utf-8"),
        )


def _executor_provider(repository: str, repository_id: int):
    provider = object.__new__(P9ExecutorInstallationTokenProvider)
    provider.repository = repository
    provider.repository_id = repository_id
    provider._cached_token = InstallationToken(
        "fixture-executor-token", expires_at=SERVER_DATETIME + timedelta(hours=1)
    )
    return provider


def _source_provider():
    provider = object.__new__(P9SourceInstallationTokenProvider)
    provider.repository = SOURCE_REPOSITORY
    provider.repository_id = SOURCE_REPOSITORY_ID
    provider._cached_token = InstallationToken(
        "fixture-source-token", expires_at=SERVER_DATETIME + timedelta(hours=1)
    )
    return provider


def _client(provider: object, sender: FixtureSender) -> GitHubRestClient:
    return GitHubRestClient(token_provider=provider, sender=sender, clock=lambda: SERVER_DATETIME)


class ReplayAvailability:
    def __init__(self, available: bool = True):
        self.available = available
        self.calls: list[str] = []

    def is_available(self, accepted: object) -> bool:
        self.calls.append(accepted.request_id)
        return self.available


def _revalidator(sender: FixtureSender | None = None, replay: ReplayAvailability | None = None):
    sender = sender or FixtureSender()
    replay = replay or ReplayAvailability()
    result = ConcreteRunnerSmokeInstallRevalidator(
        authorization_client=_client(
            _executor_provider(AUTHORIZATION_REPOSITORY, AUTHORIZATION_REPOSITORY_ID), sender
        ),
        queue_client=_client(_executor_provider(QUEUE_REPOSITORY, QUEUE_REPOSITORY_ID), sender),
        hermes_source_client=_client(_source_provider(), sender),
        rpi5_main_client=FixedPublicRpi5MainReadClient(sender=sender),
        auth_surface=load_contract(SURFACE_PATH),
        registry=_fixed_install_registry(),
        replay_availability=replay,
    )
    return result, sender, replay


class RunnerSmokeInstallRuntimeTests(unittest.TestCase):
    def test_revalidator_reconstructs_exact_authority_queue_and_both_source_proofs(self):
        revalidator, sender, replay = _revalidator()
        result = revalidator.revalidate(AUTHORIZATION_ISSUE)
        self.assertEqual(result.authorization_issue_number, AUTHORIZATION_ISSUE)
        self.assertEqual(result.owner_numeric_id, 277435981)
        self.assertEqual(result.owner_type, "User")
        self.assertFalse(result.app_authored)
        self.assertEqual(result.operation_id, OPERATION_ID)
        self.assertEqual(result.live_gate_id, LIVE_GATE_ID)
        self.assertEqual(result.target_alias, INSTALL_TARGET_ALIAS)
        self.assertEqual(result.source_sha, SOURCE_SHA)
        self.assertEqual(result.rpi5_main_sha, RPI5_SHA)
        self.assertEqual(result.helper_sha256, HELPER_SHA256)
        self.assertEqual(result.registration_sha256, REGISTRATION_SHA256)
        self.assertTrue(result.identical_body_refetch)
        self.assertTrue(result.replay_available)
        self.assertEqual(replay.calls, [REQUEST_ID])
        self.assertTrue(all(call.startswith("/repos/") for call in sender.calls))

    def test_existing_consumer_performs_two_full_canonical_passes(self):
        revalidator, _, replay = _revalidator()
        envelope = prepare_install_live_envelope(
            AUTHORIZATION_ISSUE, canonical_revalidator=revalidator
        )
        self.assertEqual(envelope["rpi5_main_sha"], RPI5_SHA)
        self.assertEqual(envelope["target_alias"], INSTALL_TARGET_ALIAS)
        self.assertEqual(replay.calls, [REQUEST_ID, REQUEST_ID])

    def test_rejects_owner_app_ttl_body_queue_dependency_and_ci_drift(self):
        cases = (
            FixtureSender(app_authored=True),
            FixtureSender(expired=True),
            FixtureSender(body_refetch_drift=True),
            FixtureSender(queue_target_drift=True),
            FixtureSender(dependency_drift=True),
            FixtureSender(hermes_ci_success=False),
            FixtureSender(rpi5_ci_success=False),
        )
        for sender in cases:
            with self.subTest(sender=sender.__dict__):
                revalidator, _, _ = _revalidator(sender)
                with self.assertRaises(RunnerSmokeInstallRuntimeError):
                    revalidator.revalidate(AUTHORIZATION_ISSUE)

    def test_rejects_replay_unavailability_and_wrong_source_provider(self):
        revalidator, _, _ = _revalidator(replay=ReplayAvailability(False))
        with self.assertRaises(RunnerSmokeInstallRuntimeError):
            revalidator.revalidate(AUTHORIZATION_ISSUE)

        sender = FixtureSender()
        provider = _source_provider()
        provider.repository = "rozkalnsandris/other"
        with self.assertRaises(RunnerSmokeInstallRuntimeError):
            ConcreteRunnerSmokeInstallRevalidator(
                authorization_client=_client(
                    _executor_provider(AUTHORIZATION_REPOSITORY, AUTHORIZATION_REPOSITORY_ID), sender
                ),
                queue_client=_client(
                    _executor_provider(QUEUE_REPOSITORY, QUEUE_REPOSITORY_ID), sender
                ),
                hermes_source_client=_client(provider, sender),
                rpi5_main_client=FixedPublicRpi5MainReadClient(sender=sender),
                auth_surface=load_contract(SURFACE_PATH),
                registry=_fixed_install_registry(),
                replay_availability=ReplayAvailability(),
            )

    def test_fixed_runtime_registry_is_install_only_and_globally_disabled(self):
        registry = _fixed_install_registry()
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, OPERATION_ID)
        self.assertEqual(operation.source_repository, SOURCE_REPOSITORY)
        self.assertEqual(operation.target_alias, INSTALL_TARGET_ALIAS)
        self.assertEqual(operation.baseline.resolver_id, INSTALL_BASELINE_RESOLVER_ID)
        self.assertEqual(operation.mutation_budget, INSTALL_MUTATION_BUDGET)
        self.assertEqual(operation.exclusions, INSTALL_EXCLUSIONS)
        self.assertEqual(operation.dependencies, INSTALL_DEPENDENCIES)
        self.assertEqual(operation.rollback_policy, "NONE")
        self.assertFalse(operation.ordinary_live_all_eligible)

    def test_public_rpi5_reader_is_one_repository_only(self):
        reader = FixedPublicRpi5MainReadClient(sender=FixtureSender())
        with self.assertRaises(RunnerSmokeInstallRuntimeError):
            reader.get_json(f"/repos/{SOURCE_REPOSITORY}")

    def test_concrete_replay_adapter_binds_issue_body_and_exact_two_check_receipt(self):
        class Delegate:
            def __init__(self):
                self.calls = []

            def is_available(self, accepted):
                self.calls.append(("available", accepted.request_id))
                return True

            def consume(self, request_id):
                self.calls.append(("consume", request_id))
                return SimpleNamespace(
                    request_id=request_id,
                    state="CONSUMED",
                    availability_checks=2,
                    durable_replay_consumed=True,
                    replay_mutation_started=True,
                    production_mutation_started=False,
                )

        delegate = Delegate()
        with patch(
            "deploy_executor.hermes_deals_runner_smoke_install_runtime.ConcreteDurableHermesOriginReplayAuthority",
            return_value=delegate,
        ):
            replay = ConcreteRunnerSmokeInstallReplayAuthority()
        accepted = SimpleNamespace(
            request_id=REQUEST_ID,
            issue_number=AUTHORIZATION_ISSUE,
            raw_body_sha256="b" * 64,
        )
        self.assertTrue(replay.is_available(accepted))
        replay.consume(authorization_issue_number=AUTHORIZATION_ISSUE, body_sha256="b" * 64)
        self.assertEqual(delegate.calls, [("available", REQUEST_ID), ("consume", REQUEST_ID)])
        with self.assertRaises(RunnerSmokeInstallRuntimeError):
            replay.consume(authorization_issue_number=AUTHORIZATION_ISSUE + 1, body_sha256="b" * 64)

    def test_operator_and_runtime_factory_expose_no_generic_caller_authority(self):
        self.assertEqual(tuple(inspect.signature(build_runner_smoke_install_runtime).parameters), ())
        self.assertEqual(
            tuple(inspect.signature(RunnerSmokeInstallRuntimeComposition.execute).parameters),
            ("self", "authorization_issue_number"),
        )
        ready = source_readiness()
        self.assertEqual(ready["caller_authority"], ("authorization_issue_number",))
        self.assertFalse(ready["global_executor_execution_enabled"])
        self.assertFalse(ready["runtime_activation_enabled"])
        self.assertFalse(ready["operator_installed"])
        self.assertFalse(ready["queue_item_created"])
        self.assertFalse(ready["live_auth_created"])
        cli = ROOT / "ops/bin/rpi5-hermes-deals-runner-smoke-install"
        self.assertTrue(cli.exists())
        self.assertEqual(cli.stat().st_mode & 0o777, 0o755)
        text = cli.read_text(encoding="utf-8")
        self.assertIn('argv[1] != "--issue-number"', text)
        self.assertNotIn("subprocess", text)
        self.assertNotIn("sudo", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
