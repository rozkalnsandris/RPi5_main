from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
import json
import re
from typing import Any, Mapping, Protocol

from .weather_public_runtime_adapter import (
    COMPOSE_PUBLIC_BLOB,
    HANDOFF_DOC_BLOB,
    OPERATION_ID,
    PERSISTENT_VOLUME,
    PUBLIC_INGEST_SCHEDULE_BLOB,
    READINESS_ENDPOINT,
    RUNTIME_DESCRIPTOR_BLOB,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)

REQUEST_SCHEMA = "rozkalns-weather.public-runtime-bootstrap-request.v1"
BASELINE_EVIDENCE_SCHEMA = "rozkalns-weather.public-runtime-bootstrap-baseline-evidence.v1"
BASELINE_RESOLVER_ID = "rozkalns-weather.public-runtime-bootstrap-baseline.v1"
BOOTSTRAP_CAPABILITY_ID = "rozkalns-weather.public-runtime-bootstrap.v1"
DISPATCH_PLAN_SCHEMA = "rozkalns-weather.public-runtime-bootstrap-plan.v1"
RUNTIME_CLASS = "public-only-rpi5"
TRUTH_PROVIDER = "dwd_observations"
TRUTH_STATION_ID = "10416"
FORECAST_MODELS = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")
RUN_HOURS = (0, 6, 12, 18)
TRUTH_CHUNK_DAYS = 14
PUBLIC_INGEST_CADENCE = "PT30M"
SCHEMA_VERSION = 1
MAX_BACKFILL_DAYS = 180
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

RECOVERY_DECISIONS = frozenset(
    {
        "verified-backup-available",
        "owner-accepted-no-prewrite-backup",
    }
)

_REQUEST_FIELDS = frozenset({"schema", "authorization_issue_number"})
_BASELINE_FIELDS = frozenset(
    {
        "schema",
        "target_alias",
        "deployment_state",
        "current_source_sha",
        "persistent_volume_state",
        "schema_state",
        "schema_version",
        "public_ingest_schedule_state",
        "bootstrap_stage_state",
        "privacy_safe",
    }
)

DEPLOYMENT_STATES = frozenset({"not_deployed", "deployed"})
VOLUME_STATES = frozenset({"absent", "present", "unknown"})
SCHEMA_STATES = frozenset({"absent", "ready", "unknown"})
SCHEDULE_STATES = frozenset({"absent", "installed", "enabled", "unknown"})
BOOTSTRAP_STAGE_STATES = frozenset(
    {
        "not_started",
        "application_ready",
        "schema_ready",
        "backfill_complete",
        "recurring_ingest_enabled",
        "unknown",
    }
)


class WeatherBootstrapError(ValueError):
    pass


@dataclass(frozen=True)
class WeatherBootstrapRequest:
    """Identity-only request for the future privileged bootstrap boundary."""

    authorization_issue_number: int


@dataclass(frozen=True)
class WeatherBootstrapBaseline:
    deployment_state: str
    current_source_sha: str | None
    persistent_volume_state: str
    schema_state: str
    schema_version: int | None
    public_ingest_schedule_state: str
    bootstrap_stage_state: str

    @property
    def canonical_token(self) -> str:
        return ";".join(
            (
                f"deployment={self.deployment_state}",
                f"source={self.current_source_sha or 'none'}",
                f"volume={self.persistent_volume_state}",
                f"schema={self.schema_state}:{self.schema_version if self.schema_version is not None else 'none'}",
                f"schedule={self.public_ingest_schedule_state}",
                f"stage={self.bootstrap_stage_state}",
            )
        )

    def canonical_json(self) -> str:
        return json.dumps(
            {
                "resolver_id": BASELINE_RESOLVER_ID,
                "deployment_state": self.deployment_state,
                "current_source_sha": self.current_source_sha,
                "persistent_volume_state": self.persistent_volume_state,
                "schema_state": self.schema_state,
                "schema_version": self.schema_version,
                "public_ingest_schedule_state": self.public_ingest_schedule_state,
                "bootstrap_stage_state": self.bootstrap_stage_state,
                "canonical_token": self.canonical_token,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class CanonicalWeatherBootstrapEvidence:
    authorization_issue_number: int
    source_repository: str
    source_sha: str
    current_main_sha: str
    target_alias: str
    operation_id: str
    capability_id: str
    runtime_class: str
    source_reachable_from_main: bool
    source_ci_success: bool
    handoff_identity_match: bool
    static_registry_contract_match: bool
    registry_execution_enabled: bool
    release_adapter_execution_enabled: bool
    public_only_private_inputs_absent: bool
    start_date: str
    end_date: str
    truth_provider: str
    truth_station_id: str
    forecast_models: tuple[str, ...]
    run_hours: tuple[int, ...]
    truth_chunk_days: int
    recovery_decision: str
    backup_restore_authorized: bool
    public_ingest_cadence: str


@dataclass(frozen=True)
class WeatherBootstrapConsumerReady:
    authorization_issue_number: int
    source_sha: str
    target_alias: str
    baseline_token: str
    start_date: str
    end_date: str
    recovery_decision: str
    forecast_models: tuple[str, ...]
    run_hours: tuple[int, ...]
    privileged_dispatch_enabled: bool = False
    host_wiring_enabled: bool = False
    production_mutation_started: bool = False


@dataclass(frozen=True)
class WeatherBootstrapStage:
    stage_id: str
    capability_class: str
    mutation_class: str | None
    max_operations: int
    read_only: bool


@dataclass(frozen=True)
class WeatherBootstrapDispatchPlan:
    schema: str
    result: str
    source_sha: str
    target_alias: str
    baseline_token: str
    start_date: str
    end_date: str
    recovery_decision: str
    truth_provider: str
    truth_station_id: str
    forecast_models: tuple[str, ...]
    run_hours: tuple[int, ...]
    truth_chunk_days: int
    public_ingest_cadence: str
    persistent_volume: str
    readiness_endpoint: str
    stages: tuple[WeatherBootstrapStage, ...]
    privileged_dispatch_implemented: bool = True
    privileged_dispatch_enabled: bool = False
    host_wiring_enabled: bool = False
    production_mutation_started: bool = False
    weather_next_required: bool = False
    home_coordinates_required: bool = False
    automatic_retry_cleanup_rollback: bool = False
    sqlite_rollback_delete_restore: bool = False


class CanonicalWeatherBootstrapRevalidator(Protocol):
    def revalidate(self, authorization_issue_number: int) -> CanonicalWeatherBootstrapEvidence: ...


class SanitizedWeatherBootstrapBaselineResolver(Protocol):
    def resolve(self, *, source_sha: str, target_alias: str) -> Mapping[str, Any]: ...


def _fail(message: str) -> None:
    raise WeatherBootstrapError(message)


def parse_weather_bootstrap_request(value: Mapping[str, Any]) -> WeatherBootstrapRequest:
    if type(value) is not dict:
        _fail("bootstrap request must be an object")
    actual = frozenset(value)
    if actual != _REQUEST_FIELDS:
        _fail("identity-only bootstrap request shape mismatch")
    if value["schema"] != REQUEST_SCHEMA:
        _fail("bootstrap request schema mismatch")
    issue_number = value["authorization_issue_number"]
    if type(issue_number) is not int or not 1 <= issue_number <= 2_147_483_647:
        _fail("authorization_issue_number is outside the supported range")
    return WeatherBootstrapRequest(authorization_issue_number=issue_number)


def parse_weather_bootstrap_baseline(value: Mapping[str, Any]) -> WeatherBootstrapBaseline:
    if type(value) is not dict:
        _fail("bootstrap baseline evidence must be an object")
    actual = frozenset(value)
    if actual != _BASELINE_FIELDS:
        _fail("bootstrap baseline evidence keys mismatch")
    if value["schema"] != BASELINE_EVIDENCE_SCHEMA:
        _fail("bootstrap baseline evidence schema mismatch")
    if value["target_alias"] != TARGET_ALIAS:
        _fail("bootstrap baseline target alias mismatch")
    if value["privacy_safe"] is not True:
        _fail("bootstrap baseline must be explicitly privacy-safe")

    deployment_state = value["deployment_state"]
    if deployment_state not in DEPLOYMENT_STATES:
        _fail("bootstrap deployment state is invalid")
    current_source_sha = value["current_source_sha"]
    if deployment_state == "not_deployed":
        if current_source_sha is not None:
            _fail("not_deployed bootstrap baseline must not claim a source SHA")
    elif type(current_source_sha) is not str or SHA_RE.fullmatch(current_source_sha) is None:
        _fail("deployed bootstrap baseline requires exact lowercase source SHA")

    volume_state = value["persistent_volume_state"]
    if volume_state not in VOLUME_STATES:
        _fail("bootstrap persistent volume state is invalid")
    schema_state = value["schema_state"]
    if schema_state not in SCHEMA_STATES:
        _fail("bootstrap schema state is invalid")
    schema_version = value["schema_version"]
    if schema_state == "ready":
        if schema_version != SCHEMA_VERSION:
            _fail("ready bootstrap schema must match reviewed schema version")
    elif schema_version is not None:
        _fail("non-ready bootstrap schema must not claim a schema version")
    schedule_state = value["public_ingest_schedule_state"]
    if schedule_state not in SCHEDULE_STATES:
        _fail("bootstrap public-ingest schedule state is invalid")
    stage_state = value["bootstrap_stage_state"]
    if stage_state not in BOOTSTRAP_STAGE_STATES:
        _fail("bootstrap stage state is invalid")

    return WeatherBootstrapBaseline(
        deployment_state=deployment_state,
        current_source_sha=current_source_sha,
        persistent_volume_state=volume_state,
        schema_state=schema_state,
        schema_version=schema_version,
        public_ingest_schedule_state=schedule_state,
        bootstrap_stage_state=stage_state,
    )


def _parse_iso_date(value: Any, where: str) -> date:
    if type(value) is not str:
        _fail(f"{where} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise WeatherBootstrapError(f"{where} must be an ISO date") from exc
    if parsed.isoformat() != value:
        _fail(f"{where} must be canonical ISO date")
    return parsed


def _validate_canonical_evidence(
    request: WeatherBootstrapRequest,
    evidence: CanonicalWeatherBootstrapEvidence,
) -> None:
    if not isinstance(evidence, CanonicalWeatherBootstrapEvidence):
        _fail("canonical bootstrap revalidator returned unsupported evidence")
    if evidence.authorization_issue_number != request.authorization_issue_number:
        _fail("canonical bootstrap authorization issue drifted")
    if evidence.source_repository != SOURCE_REPOSITORY:
        _fail("canonical bootstrap source repository drifted")
    for value, name in (
        (evidence.source_sha, "source_sha"),
        (evidence.current_main_sha, "current_main_sha"),
    ):
        if type(value) is not str or SHA_RE.fullmatch(value) is None:
            _fail(f"canonical bootstrap {name} must be exact lowercase Git SHA")
    if evidence.target_alias != TARGET_ALIAS:
        _fail("canonical bootstrap target alias drifted")
    if evidence.operation_id != OPERATION_ID:
        _fail("canonical bootstrap release operation drifted")
    if evidence.capability_id != BOOTSTRAP_CAPABILITY_ID:
        _fail("canonical bootstrap capability identity drifted")
    if evidence.runtime_class != RUNTIME_CLASS:
        _fail("canonical bootstrap runtime class drifted")

    required_true = {
        "source_reachable_from_main": evidence.source_reachable_from_main,
        "source_ci_success": evidence.source_ci_success,
        "handoff_identity_match": evidence.handoff_identity_match,
        "static_registry_contract_match": evidence.static_registry_contract_match,
        "public_only_private_inputs_absent": evidence.public_only_private_inputs_absent,
    }
    for name, value in required_true.items():
        if type(value) is not bool or value is not True:
            _fail(f"canonical bootstrap {name} must be true")
    required_false = {
        "registry_execution_enabled": evidence.registry_execution_enabled,
        "release_adapter_execution_enabled": evidence.release_adapter_execution_enabled,
        "backup_restore_authorized": evidence.backup_restore_authorized,
    }
    for name, value in required_false.items():
        if type(value) is not bool or value is not False:
            _fail(f"canonical bootstrap {name} must be false")

    start = _parse_iso_date(evidence.start_date, "canonical bootstrap start_date")
    end = _parse_iso_date(evidence.end_date, "canonical bootstrap end_date")
    if end < start:
        _fail("canonical bootstrap end_date precedes start_date")
    if (end - start).days + 1 > MAX_BACKFILL_DAYS:
        _fail("canonical bootstrap backfill window exceeds maximum")
    if evidence.truth_provider != TRUTH_PROVIDER:
        _fail("canonical bootstrap truth provider drifted")
    if evidence.truth_station_id != TRUTH_STATION_ID:
        _fail("canonical bootstrap truth station drifted")
    if evidence.forecast_models != FORECAST_MODELS:
        _fail("canonical bootstrap deterministic forecast model scope drifted")
    if evidence.run_hours != RUN_HOURS:
        _fail("canonical bootstrap forecast run-hour scope drifted")
    if evidence.truth_chunk_days != TRUTH_CHUNK_DAYS:
        _fail("canonical bootstrap truth chunk budget drifted")
    if evidence.recovery_decision not in RECOVERY_DECISIONS:
        _fail("canonical bootstrap recovery decision is not explicit/reviewed")
    if evidence.public_ingest_cadence != PUBLIC_INGEST_CADENCE:
        _fail("canonical bootstrap public-ingest cadence drifted")


def consume_weather_bootstrap_request(
    request_payload: Mapping[str, Any],
    *,
    canonical_revalidator: CanonicalWeatherBootstrapRevalidator,
    baseline_resolver: SanitizedWeatherBootstrapBaselineResolver,
) -> WeatherBootstrapConsumerReady:
    """Revalidate one identity-only request without dispatching or mutating a host."""

    request = parse_weather_bootstrap_request(request_payload)
    evidence = canonical_revalidator.revalidate(request.authorization_issue_number)
    _validate_canonical_evidence(request, evidence)
    baseline = parse_weather_bootstrap_baseline(
        baseline_resolver.resolve(
            source_sha=evidence.source_sha,
            target_alias=evidence.target_alias,
        )
    )

    final_evidence = canonical_revalidator.revalidate(request.authorization_issue_number)
    _validate_canonical_evidence(request, final_evidence)
    if any(
        getattr(final_evidence, field.name) != getattr(evidence, field.name)
        for field in fields(CanonicalWeatherBootstrapEvidence)
    ):
        _fail("canonical bootstrap evidence drifted during revalidation")

    return WeatherBootstrapConsumerReady(
        authorization_issue_number=request.authorization_issue_number,
        source_sha=final_evidence.source_sha,
        target_alias=final_evidence.target_alias,
        baseline_token=baseline.canonical_token,
        start_date=final_evidence.start_date,
        end_date=final_evidence.end_date,
        recovery_decision=final_evidence.recovery_decision,
        forecast_models=final_evidence.forecast_models,
        run_hours=final_evidence.run_hours,
    )


def _stages() -> tuple[WeatherBootstrapStage, ...]:
    return (
        WeatherBootstrapStage(
            "application_release",
            OPERATION_ID,
            "application-release",
            1,
            False,
        ),
        WeatherBootstrapStage(
            "persistent_volume_ensure",
            "rozkalns-weather.public-runtime-volume.v1",
            "docker.named-volume-ensure",
            1,
            False,
        ),
        WeatherBootstrapStage(
            "explicit_schema_init",
            "rozkalns-weather.public-runtime-schema-init.v1",
            "sqlite.schema-init",
            1,
            False,
        ),
        WeatherBootstrapStage(
            "readiness_schema_privacy",
            "rozkalns-weather.public-runtime-readiness.v1",
            None,
            1,
            True,
        ),
        WeatherBootstrapStage(
            "public_smoke_read_only",
            "rozkalns-weather.public-runtime-smoke.v1",
            None,
            1,
            True,
        ),
        WeatherBootstrapStage(
            "bounded_dwd_truth_backfill",
            "rozkalns-weather.public-runtime-truth-backfill.v1",
            "sqlite.corpus-truth-backfill",
            1,
            False,
        ),
        WeatherBootstrapStage(
            "bounded_deterministic_forecast_backfill",
            "rozkalns-weather.public-runtime-forecast-backfill.v1",
            "sqlite.corpus-forecast-backfill",
            len(FORECAST_MODELS),
            False,
        ),
        WeatherBootstrapStage(
            "corpus_integrity_check",
            "rozkalns-weather.public-runtime-integrity.v1",
            None,
            len(FORECAST_MODELS),
            True,
        ),
        WeatherBootstrapStage(
            "recurring_public_ingest_schedule",
            "rozkalns-weather.public-runtime-ingest-schedule.v1",
            "systemd.public-ingest-schedule-install-or-update",
            1,
            False,
        ),
    )


def prepare_weather_bootstrap_dispatch(
    request_payload: Mapping[str, Any],
    *,
    canonical_revalidator: CanonicalWeatherBootstrapRevalidator,
    baseline_resolver: SanitizedWeatherBootstrapBaselineResolver,
) -> WeatherBootstrapDispatchPlan:
    """Build one immutable source-only rollout plan; never launch a process."""

    ready = consume_weather_bootstrap_request(
        request_payload,
        canonical_revalidator=canonical_revalidator,
        baseline_resolver=baseline_resolver,
    )
    return WeatherBootstrapDispatchPlan(
        schema=DISPATCH_PLAN_SCHEMA,
        result="WEATHER_BOOTSTRAP_SOURCE_READY",
        source_sha=ready.source_sha,
        target_alias=ready.target_alias,
        baseline_token=ready.baseline_token,
        start_date=ready.start_date,
        end_date=ready.end_date,
        recovery_decision=ready.recovery_decision,
        truth_provider=TRUTH_PROVIDER,
        truth_station_id=TRUTH_STATION_ID,
        forecast_models=ready.forecast_models,
        run_hours=ready.run_hours,
        truth_chunk_days=TRUTH_CHUNK_DAYS,
        public_ingest_cadence=PUBLIC_INGEST_CADENCE,
        persistent_volume=PERSISTENT_VOLUME,
        readiness_endpoint=READINESS_ENDPOINT,
        stages=_stages(),
    )


def source_readiness() -> Mapping[str, Any]:
    return {
        "request_schema": REQUEST_SCHEMA,
        "baseline_resolver_id": BASELINE_RESOLVER_ID,
        "bootstrap_capability_id": BOOTSTRAP_CAPABILITY_ID,
        "dispatch_plan_schema": DISPATCH_PLAN_SCHEMA,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "runtime_descriptor_blob": RUNTIME_DESCRIPTOR_BLOB,
        "compose_public_blob": COMPOSE_PUBLIC_BLOB,
        "public_ingest_schedule_blob": PUBLIC_INGEST_SCHEDULE_BLOB,
        "handoff_doc_blob": HANDOFF_DOC_BLOB,
        "privileged_dispatch_implemented": True,
        "privileged_dispatch_enabled": False,
        "host_wiring_enabled": False,
        "production_mutation_started": False,
        "caller_authority": ("authorization_issue_number",),
        "process_launch_surface": False,
        "weather_next_required": False,
        "home_coordinates_required": False,
        "max_backfill_days": MAX_BACKFILL_DAYS,
    }
