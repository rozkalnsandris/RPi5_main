from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Protocol

from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    QUEUE_REPOSITORY,
    AcceptedAuthorization,
    accept_issue,
    validate_queue_binding,
    verify_authorization_unchanged,
)
from .weather_public_runtime_adapter import (
    BASELINE_RESOLVER_ID as RELEASE_BASELINE_RESOLVER_ID,
    OPERATION_ID,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)
from .weather_public_runtime_bootstrap import (
    REQUEST_SCHEMA,
    CanonicalWeatherBootstrapRevalidator,
    SanitizedWeatherBootstrapBaselineResolver,
    WeatherBootstrapDispatchPlan,
    prepare_weather_bootstrap_dispatch,
)

ENVELOPE_SCHEMA = "rozkalns-weather.public-runtime-preactivation-envelope.v1"
RESULT = "WEATHER_PUBLIC_RUNTIME_PREACTIVATION_READY_SOURCE_ONLY"


class WeatherPreactivationError(ValueError):
    pass


class CanonicalAuthorizationIssueResolver(Protocol):
    def resolve(self, issue_number: int) -> Mapping[str, Any]: ...


class CanonicalReadyQueueResolver(Protocol):
    def resolve(self, *, repository_full_name: str, issue_number: int) -> Mapping[str, Any]: ...


class AuthorizationReplayGuard(Protocol):
    def assert_unconsumed(self, *, issue_id: int, request_id: str) -> None: ...


@dataclass(frozen=True)
class WeatherPreactivationStageBinding:
    stage_id: str
    capability_id: str
    mutation_class: str | None
    max_operations: int
    read_only: bool


@dataclass(frozen=True)
class WeatherPreactivationEnvelope:
    schema: str
    result: str
    authorization_issue_number: int
    authorization_issue_id: int
    request_id: str
    authorization_payload_sha256: str
    authorization_raw_body_sha256: str
    queue_repository: str
    queue_issue_number: int
    queue_contract_sha256: str
    source_repository: str
    source_sha: str
    target_alias: str
    release_operation_id: str
    release_baseline_resolver_id: str
    bootstrap_baseline_token: str
    start_date: str
    end_date: str
    recovery_decision: str
    truth_station_id: str
    forecast_models: tuple[str, ...]
    run_hours: tuple[int, ...]
    stages: tuple[WeatherPreactivationStageBinding, ...]
    caller_authority: tuple[str, ...] = ("authorization_issue_number",)
    privileged_dispatch_implemented: bool = True
    privileged_dispatch_enabled: bool = False
    host_wiring_enabled: bool = False
    production_mutation_enabled: bool = False
    production_mutation_started: bool = False
    process_launch_surface: bool = False
    separate_mutation_gates_required: bool = True
    automatic_retry_cleanup_rollback: bool = False
    weather_next_required: bool = False
    home_coordinates_required: bool = False


_EXPECTED_STAGE_BINDINGS = (
    ("application_release", OPERATION_ID, "application-release", 1, False),
    (
        "persistent_volume_ensure",
        "rozkalns-weather.public-runtime-volume.v1",
        "docker.named-volume-ensure",
        1,
        False,
    ),
    (
        "explicit_schema_init",
        "rozkalns-weather.public-runtime-schema-init.v1",
        "sqlite.schema-init",
        1,
        False,
    ),
    (
        "readiness_schema_privacy",
        "rozkalns-weather.public-runtime-readiness.v1",
        None,
        1,
        True,
    ),
    (
        "public_smoke_read_only",
        "rozkalns-weather.public-runtime-smoke.v1",
        None,
        1,
        True,
    ),
    (
        "bounded_dwd_truth_backfill",
        "rozkalns-weather.public-runtime-truth-backfill.v1",
        "sqlite.corpus-truth-backfill",
        1,
        False,
    ),
    (
        "bounded_deterministic_forecast_backfill",
        "rozkalns-weather.public-runtime-forecast-backfill.v1",
        "sqlite.corpus-forecast-backfill",
        3,
        False,
    ),
    (
        "corpus_integrity_check",
        "rozkalns-weather.public-runtime-integrity.v1",
        None,
        3,
        True,
    ),
    (
        "recurring_public_ingest_schedule",
        "rozkalns-weather.public-runtime-ingest-schedule.v1",
        "systemd.public-ingest-schedule-install-or-update",
        1,
        False,
    ),
)


def _fail(message: str) -> None:
    raise WeatherPreactivationError(message)


def _canonical_queue_hash(queue: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            queue,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise WeatherPreactivationError("queue cannot be canonically hashed") from exc
    return hashlib.sha256(encoded).hexdigest()


def _validate_weather_authority(accepted: AcceptedAuthorization) -> None:
    payload = accepted.payload
    if payload["queue_repository"] != QUEUE_REPOSITORY:
        _fail("weather queue repository drifted")
    if payload["source_repository"] != SOURCE_REPOSITORY:
        _fail("weather source repository drifted")
    if payload["target_alias"] != TARGET_ALIAS:
        _fail("weather target alias drifted")
    if payload["operation_id"] != OPERATION_ID:
        _fail("weather release operation drifted")
    if payload["expected_baseline"] != {
        "kind": "resolver",
        "value": RELEASE_BASELINE_RESOLVER_ID,
    }:
        _fail("weather release baseline resolver drifted")


def _validate_plan_binding(
    accepted: AcceptedAuthorization,
    plan: WeatherBootstrapDispatchPlan,
) -> tuple[WeatherPreactivationStageBinding, ...]:
    payload = accepted.payload
    if plan.source_sha != payload["source_sha"]:
        _fail("weather bootstrap source SHA does not match accepted LIVE-AUTH")
    if plan.target_alias != payload["target_alias"]:
        _fail("weather bootstrap target does not match accepted LIVE-AUTH")
    observed = tuple(
        (
            stage.stage_id,
            stage.capability_class,
            stage.mutation_class,
            stage.max_operations,
            stage.read_only,
        )
        for stage in plan.stages
    )
    if observed != _EXPECTED_STAGE_BINDINGS:
        _fail("weather bootstrap stage/capability mapping drifted")
    if plan.privileged_dispatch_enabled:
        _fail("weather bootstrap privileged dispatch unexpectedly enabled")
    if plan.host_wiring_enabled:
        _fail("weather bootstrap host wiring unexpectedly enabled")
    if plan.production_mutation_started:
        _fail("weather bootstrap production mutation already started")
    if plan.automatic_retry_cleanup_rollback:
        _fail("weather bootstrap automatic recovery unexpectedly enabled")
    if plan.sqlite_rollback_delete_restore:
        _fail("weather bootstrap SQLite destructive recovery unexpectedly enabled")
    if plan.weather_next_required or plan.home_coordinates_required:
        _fail("weather public bootstrap unexpectedly requires private inputs")
    return tuple(WeatherPreactivationStageBinding(*row) for row in observed)


def prepare_weather_preactivation_envelope(
    authorization_issue_number: int,
    *,
    server_time: datetime,
    governance_ok: bool,
    authorization_resolver: CanonicalAuthorizationIssueResolver,
    queue_resolver: CanonicalReadyQueueResolver,
    replay_guard: AuthorizationReplayGuard,
    canonical_revalidator: CanonicalWeatherBootstrapRevalidator,
    baseline_resolver: SanitizedWeatherBootstrapBaselineResolver,
) -> WeatherPreactivationEnvelope:
    """Compose reviewed authorization and weather plans without launching or mutating anything."""

    if type(authorization_issue_number) is not int or authorization_issue_number < 1:
        _fail("authorization_issue_number must be a positive integer")

    initial_issue = authorization_resolver.resolve(authorization_issue_number)
    accepted = accept_issue(
        initial_issue,
        repository_id=AUTHORIZATION_REPOSITORY_ID,
        repository_full_name=AUTHORIZATION_REPOSITORY,
        server_time=server_time,
        governance_ok=governance_ok,
    )
    if accepted.issue_number != authorization_issue_number:
        _fail("authorization issue identity drifted")
    _validate_weather_authority(accepted)

    queue_issue_number = accepted.payload["queue_issue"]
    initial_queue = queue_resolver.resolve(
        repository_full_name=QUEUE_REPOSITORY,
        issue_number=queue_issue_number,
    )
    validate_queue_binding(accepted, initial_queue)
    queue_hash = _canonical_queue_hash(initial_queue)
    replay_guard.assert_unconsumed(issue_id=accepted.issue_id, request_id=accepted.request_id)

    verify_authorization_unchanged(
        accepted,
        authorization_resolver.resolve(authorization_issue_number),
        server_time=server_time,
        governance_ok=governance_ok,
    )

    plan = prepare_weather_bootstrap_dispatch(
        {
            "schema": REQUEST_SCHEMA,
            "authorization_issue_number": authorization_issue_number,
        },
        canonical_revalidator=canonical_revalidator,
        baseline_resolver=baseline_resolver,
    )
    stages = _validate_plan_binding(accepted, plan)

    final_issue = authorization_resolver.resolve(authorization_issue_number)
    verify_authorization_unchanged(
        accepted,
        final_issue,
        server_time=server_time,
        governance_ok=governance_ok,
    )
    final_queue = queue_resolver.resolve(
        repository_full_name=QUEUE_REPOSITORY,
        issue_number=queue_issue_number,
    )
    validate_queue_binding(accepted, final_queue)
    if _canonical_queue_hash(final_queue) != queue_hash:
        _fail("weather READY queue drifted during preactivation revalidation")
    replay_guard.assert_unconsumed(issue_id=accepted.issue_id, request_id=accepted.request_id)

    return WeatherPreactivationEnvelope(
        schema=ENVELOPE_SCHEMA,
        result=RESULT,
        authorization_issue_number=accepted.issue_number,
        authorization_issue_id=accepted.issue_id,
        request_id=accepted.request_id,
        authorization_payload_sha256=accepted.canonical_payload_sha256,
        authorization_raw_body_sha256=accepted.raw_body_sha256,
        queue_repository=QUEUE_REPOSITORY,
        queue_issue_number=queue_issue_number,
        queue_contract_sha256=queue_hash,
        source_repository=SOURCE_REPOSITORY,
        source_sha=plan.source_sha,
        target_alias=TARGET_ALIAS,
        release_operation_id=OPERATION_ID,
        release_baseline_resolver_id=RELEASE_BASELINE_RESOLVER_ID,
        bootstrap_baseline_token=plan.baseline_token,
        start_date=plan.start_date,
        end_date=plan.end_date,
        recovery_decision=plan.recovery_decision,
        truth_station_id=plan.truth_station_id,
        forecast_models=plan.forecast_models,
        run_hours=plan.run_hours,
        stages=stages,
    )


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": ENVELOPE_SCHEMA,
        "result": RESULT,
        "authorization_protocol": "deploy_executor.protocol",
        "authorization_repository": AUTHORIZATION_REPOSITORY,
        "queue_repository": QUEUE_REPOSITORY,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "release_operation_id": OPERATION_ID,
        "caller_authority": ("authorization_issue_number",),
        "privileged_dispatch_implemented": True,
        "privileged_dispatch_enabled": False,
        "host_wiring_enabled": False,
        "production_mutation_enabled": False,
        "production_mutation_started": False,
        "process_launch_surface": False,
        "separate_mutation_gates_required": True,
        "automatic_retry_cleanup_rollback": False,
        "weather_next_required": False,
        "home_coordinates_required": False,
    }
