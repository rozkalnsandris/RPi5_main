from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date
import hashlib
import json
import re
from typing import Any

from .weather_public_runtime_adapter import (
    BASELINE_RESOLVER_ID,
    OPERATION_ID,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)
from .weather_public_runtime_bootstrap import (
    FORECAST_MODELS,
    MAX_BACKFILL_DAYS,
    RECOVERY_DECISIONS,
    RUN_HOURS,
    TRUTH_STATION_ID,
)
from .weather_public_runtime_preactivation import (
    ENVELOPE_SCHEMA as PREACTIVATION_ENVELOPE_SCHEMA,
    RESULT as PREACTIVATION_RESULT,
    WeatherPreactivationEnvelope,
)

HOST_WIRING_SCHEMA = "rozkalns-weather.public-runtime-host-wiring.v1"
RESULT = "WEATHER_PUBLIC_RUNTIME_HOST_WIRING_READY_SOURCE_ONLY"
AUTHORIZATION_CLASS = "STRICT"
ORDINARY_LIVE_ALL_ELIGIBLE = False

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_EXPECTED_PREACTIVATION_FIELDS = (
    "schema",
    "result",
    "authorization_issue_number",
    "authorization_issue_id",
    "request_id",
    "authorization_payload_sha256",
    "authorization_raw_body_sha256",
    "queue_repository",
    "queue_issue_number",
    "queue_contract_sha256",
    "source_repository",
    "source_sha",
    "target_alias",
    "release_operation_id",
    "release_baseline_resolver_id",
    "bootstrap_baseline_token",
    "start_date",
    "end_date",
    "recovery_decision",
    "truth_station_id",
    "forecast_models",
    "run_hours",
    "stages",
    "caller_authority",
    "privileged_dispatch_implemented",
    "privileged_dispatch_enabled",
    "host_wiring_enabled",
    "production_mutation_enabled",
    "production_mutation_started",
    "process_launch_surface",
    "separate_mutation_gates_required",
    "automatic_retry_cleanup_rollback",
    "weather_next_required",
    "home_coordinates_required",
)

_EXPECTED_HELPERS = (
    (
        "application_release",
        "rozkalns-weather.host-helper.application-release.v1",
        OPERATION_ID,
        "application-release",
        1,
        False,
    ),
    (
        "persistent_volume_ensure",
        "rozkalns-weather.host-helper.volume-ensure.v1",
        "rozkalns-weather.public-runtime-volume.v1",
        "docker.named-volume-ensure",
        1,
        False,
    ),
    (
        "explicit_schema_init",
        "rozkalns-weather.host-helper.schema-init.v1",
        "rozkalns-weather.public-runtime-schema-init.v1",
        "sqlite.schema-init",
        1,
        False,
    ),
    (
        "readiness_schema_privacy",
        "rozkalns-weather.host-helper.readiness.v1",
        "rozkalns-weather.public-runtime-readiness.v1",
        None,
        1,
        True,
    ),
    (
        "public_smoke_read_only",
        "rozkalns-weather.host-helper.public-smoke.v1",
        "rozkalns-weather.public-runtime-smoke.v1",
        None,
        1,
        True,
    ),
    (
        "bounded_dwd_truth_backfill",
        "rozkalns-weather.host-helper.truth-backfill.v1",
        "rozkalns-weather.public-runtime-truth-backfill.v1",
        "sqlite.corpus-truth-backfill",
        1,
        False,
    ),
    (
        "bounded_deterministic_forecast_backfill",
        "rozkalns-weather.host-helper.forecast-backfill.v1",
        "rozkalns-weather.public-runtime-forecast-backfill.v1",
        "sqlite.corpus-forecast-backfill",
        3,
        False,
    ),
    (
        "corpus_integrity_check",
        "rozkalns-weather.host-helper.integrity.v1",
        "rozkalns-weather.public-runtime-integrity.v1",
        None,
        3,
        True,
    ),
    (
        "recurring_public_ingest_schedule",
        "rozkalns-weather.host-helper.ingest-schedule.v1",
        "rozkalns-weather.public-runtime-ingest-schedule.v1",
        "systemd.public-ingest-schedule-install-or-update",
        1,
        False,
    ),
)


class WeatherHostWiringError(ValueError):
    pass


@dataclass(frozen=True)
class WeatherHostHelperBinding:
    stage_id: str
    helper_id: str
    capability_id: str
    mutation_class: str | None
    max_operations: int
    read_only: bool


@dataclass(frozen=True)
class WeatherHostWiringPlan:
    schema: str
    result: str
    preactivation_sha256: str
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
    helpers: tuple[WeatherHostHelperBinding, ...]
    authorization_class: str = AUTHORIZATION_CLASS
    ordinary_live_all_eligible: bool = ORDINARY_LIVE_ALL_ELIGIBLE
    helper_interface_source_present: bool = True
    privileged_dispatch_enabled: bool = False
    host_wiring_enabled: bool = False
    helper_installation_enabled: bool = False
    helper_invocation_enabled: bool = False
    production_mutation_enabled: bool = False
    production_mutation_started: bool = False
    process_launch_surface: bool = False
    generic_shell_authority: bool = False
    runtime_live_authority: bool = False
    automatic_retry_cleanup_rollback: bool = False
    weather_next_required: bool = False
    home_coordinates_required: bool = False


def _fail(message: str) -> None:
    raise WeatherHostWiringError(message)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise WeatherHostWiringError("preactivation envelope cannot be canonically hashed") from exc


def canonical_preactivation_sha256(envelope: WeatherPreactivationEnvelope) -> str:
    """Hash every field of the already-validated preactivation envelope."""

    if not isinstance(envelope, WeatherPreactivationEnvelope):
        _fail("preactivation envelope type is invalid")
    return hashlib.sha256(_canonical_json(asdict(envelope))).hexdigest()


def _validate_preactivation(envelope: WeatherPreactivationEnvelope) -> None:
    if not isinstance(envelope, WeatherPreactivationEnvelope):
        _fail("preactivation envelope type is invalid")
    if tuple(field.name for field in fields(WeatherPreactivationEnvelope)) != _EXPECTED_PREACTIVATION_FIELDS:
        _fail("preactivation envelope field surface drifted")
    if envelope.schema != PREACTIVATION_ENVELOPE_SCHEMA or envelope.result != PREACTIVATION_RESULT:
        _fail("preactivation envelope identity drifted")
    if envelope.source_repository != SOURCE_REPOSITORY:
        _fail("weather source repository drifted")
    if not _SHA40_RE.fullmatch(envelope.source_sha):
        _fail("weather source SHA is invalid")
    if envelope.target_alias != TARGET_ALIAS:
        _fail("weather target alias drifted")
    if envelope.release_operation_id != OPERATION_ID:
        _fail("weather release operation drifted")
    if envelope.release_baseline_resolver_id != BASELINE_RESOLVER_ID:
        _fail("weather release baseline resolver drifted")
    for name, value in (
        ("authorization payload", envelope.authorization_payload_sha256),
        ("authorization raw body", envelope.authorization_raw_body_sha256),
        ("queue contract", envelope.queue_contract_sha256),
    ):
        if not _SHA256_RE.fullmatch(value):
            _fail(f"{name} SHA-256 is invalid")
    if envelope.caller_authority != ("authorization_issue_number",):
        _fail("preactivation caller authority drifted")
    if not envelope.privileged_dispatch_implemented:
        _fail("preactivation dispatch source is missing")
    if envelope.privileged_dispatch_enabled or envelope.host_wiring_enabled:
        _fail("preactivation execution is unexpectedly enabled")
    if envelope.production_mutation_enabled or envelope.production_mutation_started:
        _fail("preactivation production mutation is unexpectedly enabled")
    if envelope.process_launch_surface:
        _fail("preactivation process launch surface is unexpectedly enabled")
    if not envelope.separate_mutation_gates_required:
        _fail("preactivation mutation gates were weakened")
    if envelope.automatic_retry_cleanup_rollback:
        _fail("preactivation automatic recovery is unexpectedly enabled")
    if envelope.weather_next_required or envelope.home_coordinates_required:
        _fail("public-only preactivation unexpectedly requires private inputs")
    if envelope.truth_station_id != TRUTH_STATION_ID:
        _fail("weather truth station drifted")
    if envelope.forecast_models != FORECAST_MODELS:
        _fail("weather forecast model set drifted")
    if envelope.run_hours != RUN_HOURS:
        _fail("weather run-hour set drifted")
    if envelope.recovery_decision not in RECOVERY_DECISIONS:
        _fail("weather recovery decision drifted")
    if not isinstance(envelope.bootstrap_baseline_token, str) or not (1 <= len(envelope.bootstrap_baseline_token) <= 512):
        _fail("weather bootstrap baseline token is invalid")
    if "\n" in envelope.bootstrap_baseline_token or "\r" in envelope.bootstrap_baseline_token:
        _fail("weather bootstrap baseline token is invalid")
    try:
        start = date.fromisoformat(envelope.start_date)
        end = date.fromisoformat(envelope.end_date)
    except ValueError as exc:
        raise WeatherHostWiringError("weather date bounds are invalid") from exc
    if end < start or (end - start).days + 1 > MAX_BACKFILL_DAYS:
        _fail("weather date bounds exceed the reviewed window")

    observed_stages = tuple(
        (
            stage.stage_id,
            stage.capability_id,
            stage.mutation_class,
            stage.max_operations,
            stage.read_only,
        )
        for stage in envelope.stages
    )
    expected_stages = tuple(
        (stage_id, capability_id, mutation_class, max_operations, read_only)
        for stage_id, _helper_id, capability_id, mutation_class, max_operations, read_only in _EXPECTED_HELPERS
    )
    if observed_stages != expected_stages:
        _fail("preactivation stage/capability mapping drifted")


def expected_helper_bindings() -> tuple[WeatherHostHelperBinding, ...]:
    return tuple(WeatherHostHelperBinding(*row) for row in _EXPECTED_HELPERS)


def build_weather_host_wiring_plan(envelope: WeatherPreactivationEnvelope) -> WeatherHostWiringPlan:
    """Bind validated preactivation evidence to fixed helper identities without executing anything."""

    _validate_preactivation(envelope)
    return WeatherHostWiringPlan(
        schema=HOST_WIRING_SCHEMA,
        result=RESULT,
        preactivation_sha256=canonical_preactivation_sha256(envelope),
        authorization_issue_number=envelope.authorization_issue_number,
        authorization_issue_id=envelope.authorization_issue_id,
        request_id=envelope.request_id,
        authorization_payload_sha256=envelope.authorization_payload_sha256,
        authorization_raw_body_sha256=envelope.authorization_raw_body_sha256,
        queue_repository=envelope.queue_repository,
        queue_issue_number=envelope.queue_issue_number,
        queue_contract_sha256=envelope.queue_contract_sha256,
        source_repository=envelope.source_repository,
        source_sha=envelope.source_sha,
        target_alias=envelope.target_alias,
        release_operation_id=envelope.release_operation_id,
        release_baseline_resolver_id=envelope.release_baseline_resolver_id,
        bootstrap_baseline_token=envelope.bootstrap_baseline_token,
        start_date=envelope.start_date,
        end_date=envelope.end_date,
        recovery_decision=envelope.recovery_decision,
        truth_station_id=envelope.truth_station_id,
        forecast_models=envelope.forecast_models,
        run_hours=envelope.run_hours,
        helpers=expected_helper_bindings(),
    )


def validate_weather_host_wiring_plan(
    plan: WeatherHostWiringPlan,
    envelope: WeatherPreactivationEnvelope,
) -> WeatherHostWiringPlan:
    """Fail closed if either the immutable envelope or the source plan changed after binding."""

    if not isinstance(plan, WeatherHostWiringPlan):
        _fail("host-wiring plan type is invalid")
    expected = build_weather_host_wiring_plan(envelope)
    if plan != expected:
        _fail("host-wiring plan or preactivation envelope drifted")
    if not _SHA256_RE.fullmatch(plan.preactivation_sha256):
        _fail("preactivation SHA-256 binding is invalid")
    return plan


def source_readiness() -> dict[str, object]:
    return {
        "schema": HOST_WIRING_SCHEMA,
        "result": RESULT,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "release_operation_id": OPERATION_ID,
        "authorization_class": AUTHORIZATION_CLASS,
        "ordinary_live_all_eligible": ORDINARY_LIVE_ALL_ELIGIBLE,
        "helper_interface_source_present": True,
        "helper_ids": tuple(binding.helper_id for binding in expected_helper_bindings()),
        "privileged_dispatch_enabled": False,
        "host_wiring_enabled": False,
        "helper_installation_enabled": False,
        "helper_invocation_enabled": False,
        "production_mutation_enabled": False,
        "production_mutation_started": False,
        "process_launch_surface": False,
        "generic_shell_authority": False,
        "runtime_live_authority": False,
        "automatic_retry_cleanup_rollback": False,
        "weather_next_required": False,
        "home_coordinates_required": False,
    }
