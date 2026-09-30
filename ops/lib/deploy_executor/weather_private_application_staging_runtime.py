from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Mapping

from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    QUEUE_REPOSITORY,
    QUEUE_REPOSITORY_ID,
    AcceptedAuthorization,
    accept_issue,
    validate_queue_binding,
    verify_authorization_unchanged,
)
from .queue_normalizer import normalize_ready_queue
from .registry import BaselineContract, MutationBudget, OperationRegistry, OperationSpec, QueueMatch
from .weather_private_application_staging import (
    MUTATION_BUDGET,
    OPERATION_ID,
    REQUIRED_EXCLUSIONS,
    ROLLBACK_POLICY,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
    ApplicationStagePlan,
    PosixApplicationStageBackend,
    WeatherNextPrivateApplicationStageError,
    build_stage_plan,
    public_plan,
)
from .weather_private_bigquery_host_bindings import (
    FixedPublicGitHubReadClient,
    PublicExactSourceEvidenceProvider,
)
from .weather_private_bigquery_host_installer_runtime import DurableInstallReplayAuthority
from .weather_private_bigquery_host_runtime import (
    RPI5_MAIN_REPOSITORY,
    RPI5_MAIN_REPOSITORY_ID,
    WEATHER_REPOSITORY_ID,
)

IMPLEMENTATION_ISSUE = 702
AUTH_SURFACE = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_PRIVATE_KEY = Path("/etc/rozkalns-deploy-executor/github-app.pem")
TRUSTED_BOUNDARY = Path("/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted")
REVIEWED_RPI5_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
EXECUTION_LOCATION_CLASS = "trusted-home-host"
DEPLOY_CLASS = "STRICT_LIVE_AUTH_REQUIRED"
ADAPTER_ID = "rpi5.weathernext-private-application-stage.fixed-v1"
BASELINE_RESOLVER_ID = "rpi5.weathernext-private-application-stage.fixed-state-v1"
DEPENDENCIES = (
    "source-contract:RPi5_main#702",
    "host-capability:rpi5.weathernext-private-backend.v1",
    "global-executor-execution:disabled",
)


@dataclass(frozen=True)
class CanonicalApplicationStageEvidence:
    authorization_issue_number: int
    authorization_issue_id: int
    authorization_created_at: str
    github_server_time: str
    request_id: str
    request_body_sha256: str
    weather_source_sha: str
    rpi5_main_sha: str
    queue_issue_number: int


class WeatherNextPrivateApplicationStageRuntimeError(WeatherNextPrivateApplicationStageError):
    pass


def _fail(message: str) -> None:
    raise WeatherNextPrivateApplicationStageRuntimeError(message)


def _fixed_registry() -> OperationRegistry:
    operation = OperationSpec(
        operation_id=OPERATION_ID,
        source_repository=SOURCE_REPOSITORY,
        queue_match=QueueMatch(
            target_alias=TARGET_ALIAS,
            execution_location_class=EXECUTION_LOCATION_CLASS,
            repository_entrypoint="ops/bin/rpi5-weathernext-private-host-privileged-install",
            deploy_class=DEPLOY_CLASS,
        ),
        target_alias=TARGET_ALIAS,
        adapter_id=ADAPTER_ID,
        authorization_class="STRICT",
        ordinary_live_all_eligible=False,
        baseline=BaselineContract(kind="resolver", resolver_id=BASELINE_RESOLVER_ID),
        mutation_budget=tuple(
            MutationBudget(category=category, max_operations=maximum)
            for category, maximum in MUTATION_BUDGET
        ),
        rollback_policy=ROLLBACK_POLICY,
        exclusions=REQUIRED_EXCLUSIONS,
        dependencies=DEPENDENCIES,
        preflight=(
            "owner LIVE-AUTH and READY Queue are independently revalidated",
            "Weather source is exact current main with required exact-SHA CI",
            "installed privileged boundary is exact current RPi5_main",
            "fixed application stage state is absent or exact without conflict",
        ),
        postconditions=(
            "fixed Weather application stage is exact source and public-safe marker identity",
            "no runtime Google BigQuery SQLite Docker systemd or network-control stage executes",
        ),
        required_github_evidence=(
            "owner-authored non-App LIVE-AUTH",
            "READY Queue exact operation target source and mutation budget binding",
            "current Weather exact-main required CI",
            "current RPi5_main exact-main required CI",
        ),
    )
    return OperationRegistry(schema_version=1, execution_enabled=False, operations=(operation,))


def _server_time(response: Any) -> datetime:
    value = getattr(response, "server_time", None)
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fail("GitHub server time is unavailable")
    return value.astimezone(timezone.utc)


def _require_live_authority(accepted: AcceptedAuthorization) -> Mapping[str, Any]:
    payload = accepted.payload
    expected = {
        "queue_repository": QUEUE_REPOSITORY,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "expected_baseline": {"kind": "resolver", "value": BASELINE_RESOLVER_ID},
        "mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in MUTATION_BUDGET
        ],
        "rollback_policy": ROLLBACK_POLICY,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            _fail(f"canonical application-stage LIVE-AUTH {field} drifted")
    exclusions = payload.get("exclusions")
    if type(exclusions) is not list or not set(REQUIRED_EXCLUSIONS).issubset(set(exclusions)):
        _fail("canonical application-stage LIVE-AUTH exclusions drifted")
    return payload


def _require_queue(normalized: Any) -> Mapping[str, Any]:
    if getattr(normalized, "execution_enabled", None) is not False:
        _fail("private application-stage registry unexpectedly enables execution")
    operation = getattr(normalized, "operation", None)
    expected = {
        "operation_id": OPERATION_ID,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "adapter_id": ADAPTER_ID,
        "authorization_class": "STRICT",
        "ordinary_live_all_eligible": False,
        "rollback_policy": ROLLBACK_POLICY,
    }
    for field, value in expected.items():
        if getattr(operation, field, None) != value:
            _fail(f"private application-stage Queue {field} drifted")
    observed_budget = tuple(
        (item.category, item.max_operations)
        for item in getattr(operation, "mutation_budget", ())
    )
    if observed_budget != MUTATION_BUDGET:
        _fail("private application-stage Queue mutation budget drifted")
    baseline = getattr(operation, "baseline", None)
    if getattr(baseline, "kind", None) != "resolver" or getattr(baseline, "resolver_id", None) != BASELINE_RESOLVER_ID:
        _fail("private application-stage Queue baseline drifted")
    return normalized.as_protocol_queue()


def _require_trusted_boundary_exact(rpi5_main_sha: str) -> None:
    module_path = Path(__file__).resolve()
    expected_lib = TRUSTED_BOUNDARY / "ops/lib/deploy_executor"
    try:
        module_path.relative_to(expected_lib)
    except ValueError:
        _fail("application-stage runtime is outside fixed trusted installer boundary")
    from .weather_private_application_staging import _default_runner, _fixed_git_prefix, _run

    prefix = _fixed_git_prefix()
    origin = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "config", "--get", "remote.origin.url"),
        "trusted boundary origin",
    ).strip()
    head = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "rev-parse", "HEAD"),
        "trusted boundary HEAD",
    ).strip()
    branch = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "rev-parse", "--abbrev-ref", "HEAD"),
        "trusted boundary detached state",
    ).strip()
    tracked = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "status", "--porcelain", "--untracked-files=no"),
        "trusted boundary clean state",
    )
    if origin != REVIEWED_RPI5_ORIGIN or head != rpi5_main_sha or branch != "HEAD" or tracked != "":
        _fail("installed privileged boundary is not exact current RPi5_main")


class ConcreteApplicationStageRevalidator:
    def __init__(
        self,
        *,
        authorization_client: Any,
        queue_client: Any,
        sources: PublicExactSourceEvidenceProvider,
        auth_surface: Any,
        replay: DurableInstallReplayAuthority,
    ):
        require_isolated_auth_surface(auth_surface)
        self._authorization_client = authorization_client
        self._queue_client = queue_client
        self._sources = sources
        self._auth_surface = auth_surface
        self._replay = replay
        self._registry = _fixed_registry()
        self.accepted: AcceptedAuthorization | None = None

    def revalidate(self, issue_number: int) -> CanonicalApplicationStageEvidence:
        if type(issue_number) is not int or not 1 <= issue_number <= 2_147_483_647:
            _fail("authorization issue number is invalid")
        require_isolated_auth_surface(self._auth_surface)
        issue_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        accepted = accept_issue(
            issue_response.value,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=_server_time(issue_response),
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        payload = _require_live_authority(accepted)
        queue_issue_number = payload.get("queue_issue")
        if type(queue_issue_number) is not int or queue_issue_number < 1:
            _fail("application-stage Queue issue number is invalid")
        queue_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue_number}"
        )
        normalized = normalize_ready_queue(
            queue_response.value,
            repository_full_name=QUEUE_REPOSITORY,
            registry=self._registry,
        )
        validate_queue_binding(accepted, _require_queue(normalized))

        weather = self._sources.load_exact_source(SOURCE_REPOSITORY, WEATHER_REPOSITORY_ID)
        rpi = self._sources.load_exact_source(RPI5_MAIN_REPOSITORY, RPI5_MAIN_REPOSITORY_ID)
        if payload.get("source_sha") != weather.source_sha or weather.current_main_sha != weather.source_sha:
            _fail("Weather application-stage source is not exact current main")
        _require_trusted_boundary_exact(rpi.source_sha)
        if self._replay.is_available(accepted) is not True:
            _fail("application-stage LIVE-AUTH is unavailable for one-shot consume")

        final = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        verify_authorization_unchanged(
            accepted,
            final.value,
            server_time=_server_time(final),
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        if self._replay.is_available(accepted) is not True:
            _fail("application-stage LIVE-AUTH replay state drifted")
        self.accepted = accepted
        return CanonicalApplicationStageEvidence(
            authorization_issue_number=issue_number,
            authorization_issue_id=accepted.issue_id,
            authorization_created_at=accepted.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            github_server_time=_server_time(final).strftime("%Y-%m-%dT%H:%M:%SZ"),
            request_id=accepted.request_id,
            request_body_sha256=accepted.raw_body_sha256,
            weather_source_sha=weather.source_sha,
            rpi5_main_sha=rpi.source_sha,
            queue_issue_number=queue_issue_number,
        )


def _stable(first: CanonicalApplicationStageEvidence, final: CanonicalApplicationStageEvidence) -> None:
    for field in (
        "authorization_issue_number",
        "authorization_issue_id",
        "authorization_created_at",
        "request_id",
        "request_body_sha256",
        "weather_source_sha",
        "rpi5_main_sha",
        "queue_issue_number",
    ):
        if getattr(first, field) != getattr(final, field):
            _fail(f"canonical application-stage evidence drifted: {field}")


def _plan_for(evidence: CanonicalApplicationStageEvidence, backend: PosixApplicationStageBackend) -> ApplicationStagePlan:
    observed = backend.observe(
        evidence.weather_source_sha,
        current_main_sha=evidence.weather_source_sha,
        exact_main_ci_success=True,
    )
    return build_stage_plan(observed)


def run_privileged_application_stage(authorization_issue_number: int) -> Mapping[str, object]:
    if os.geteuid() != 0:
        _fail("private application-stage boundary must run as root")
    replay = DurableInstallReplayAuthority()
    try:
        auth_surface = load_contract(AUTH_SURFACE)
        require_isolated_auth_surface(auth_surface)
        clients = build_p9_read_clients(auth_surface=auth_surface, private_key=EXECUTOR_PRIVATE_KEY)
        sources = PublicExactSourceEvidenceProvider(client=FixedPublicGitHubReadClient())
        revalidator = ConcreteApplicationStageRevalidator(
            authorization_client=clients.authorization,
            queue_client=clients.queue,
            sources=sources,
            auth_surface=auth_surface,
            replay=replay,
        )
        backend = PosixApplicationStageBackend()
        first = revalidator.revalidate(authorization_issue_number)
        final = revalidator.revalidate(authorization_issue_number)
        _stable(first, final)
        plan = _plan_for(final, backend)
        if plan.prior_state == "EXACT":
            return {
                "status": "ALREADY_EXACT",
                "operation_id": OPERATION_ID,
                "target_alias": TARGET_ALIAS,
                "source_sha": final.weather_source_sha,
                "authorization_consumed": False,
                "production_mutation_started": False,
                "mutation_categories": [],
                "rollback_policy": ROLLBACK_POLICY,
            }

        preconsume = revalidator.revalidate(authorization_issue_number)
        _stable(final, preconsume)
        preconsume_plan = _plan_for(preconsume, backend)
        if public_plan(preconsume_plan) != public_plan(plan):
            _fail("application-stage plan drifted immediately before consume")
        accepted = revalidator.accepted
        if accepted is None or accepted.request_id != preconsume.request_id:
            _fail("application-stage accepted authorization identity drifted")
        replay.consume(accepted.request_id)
        receipt = dict(backend.apply(preconsume_plan))
        replay.mark_succeeded(accepted.request_id)
        return {
            "status": receipt["status"],
            "operation_id": OPERATION_ID,
            "target_alias": TARGET_ALIAS,
            "source_sha": preconsume.weather_source_sha,
            "authorization_consumed": True,
            "production_mutation_started": receipt["production_mutation_started"],
            "mutation_categories": receipt["mutation_categories"],
            "rollback_policy": ROLLBACK_POLICY,
        }
    except WeatherNextPrivateApplicationStageRuntimeError:
        raise
    except WeatherNextPrivateApplicationStageError as exc:
        raise WeatherNextPrivateApplicationStageRuntimeError(str(exc)) from exc
    except Exception:
        raise WeatherNextPrivateApplicationStageRuntimeError(
            "WeatherNext private application staging failed closed"
        ) from None


def source_readiness() -> Mapping[str, object]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_repository": SOURCE_REPOSITORY,
        "caller_authority": ("authorization_issue_number",),
        "mutation_budget": MUTATION_BUDGET,
        "rollback_policy": ROLLBACK_POLICY,
        "privileged_boundary_reused": True,
        "global_executor_execution_enabled": False,
        "source_merge_authorizes_live": False,
        "runtime_materialization_allowed": False,
        "google_action_allowed": False,
        "bigquery_action_allowed": False,
        "sqlite_write_allowed": False,
        "production_mutation_started": False,
    }
