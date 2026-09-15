from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .weather_private_bigquery_contract import (
    ANALYTICS_HUB_LINK_CREATE,
    CONTRACT_ID,
    GOOGLE_AUTH_BINDING,
    GOOGLE_PROJECT_BINDING,
    INITIAL_FORECAST_HOURS,
    INITIAL_LOCATION_ID,
    MAX_BYTES_BILLED_PER_QUERY,
    PRIVATE_RUNTIME_MATERIALIZATION,
    PUBLIC_RUNTIME_OPERATION_ID,
    READ_ONLY_PRIVATE_BIGQUERY,
    REQUIRED_SURFACES,
    FirstAccessScope,
    validate_first_access_scope,
)

BRIDGE_OPERATION_ID = "rozkalns-weather.weathernext-private-execution-bridge.v1"
TARGET_ALIAS = "rpi5"
PRIVATE_APPLICATION_STAGING = "weathernext_private_application_staging"
AUTHORIZED_STAGE_SEQUENCE = (
    PRIVATE_APPLICATION_STAGING,
    PRIVATE_RUNTIME_MATERIALIZATION,
    GOOGLE_AUTH_BINDING,
    GOOGLE_PROJECT_BINDING,
    ANALYTICS_HUB_LINK_CREATE,
    READ_ONLY_PRIVATE_BIGQUERY,
)


class WeatherNextPrivateExecutionBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class PrivateExecutionBaseline:
    application_staged: bool
    runtime_present: bool
    auth_binding_present: bool
    project_binding_present: bool
    linked_dataset_present: bool


@dataclass(frozen=True)
class PrivateExecutionEnvelope:
    authorization_issue_number: int
    rpi5_main_source_sha: str
    weather_source_sha: str
    baseline: PrivateExecutionBaseline
    operation_id: str = BRIDGE_OPERATION_ID
    contract_id: str = CONTRACT_ID
    target_alias: str = TARGET_ALIAS
    location_id: str = INITIAL_LOCATION_ID
    forecast_hours: int = INITIAL_FORECAST_HOURS
    max_bytes_billed_per_query: int = MAX_BYTES_BILLED_PER_QUERY
    dry_run_required: bool = True
    home_scope_enabled: bool = False
    sqlite_write_enabled: bool = False
    required_surfaces: tuple[str, ...] = REQUIRED_SURFACES
    authorized_stages: tuple[str, ...] = AUTHORIZED_STAGE_SEQUENCE


@dataclass(frozen=True)
class StageReceipt:
    stage: str
    status: str
    mutation_performed: bool
    sanitized: bool = True
    retry_performed: bool = False
    cleanup_performed: bool = False
    rollback_performed: bool = False


class CanonicalPrivateAuthorizationRevalidator(Protocol):
    def prepare_private_execution(self, authorization_issue_number: int) -> PrivateExecutionEnvelope: ...


class AuthorizationConsumer(Protocol):
    def consume_once(self, authorization_issue_number: int, *, first_stage: str) -> None: ...


class PrivateExecutionBackend(Protocol):
    def stage_application(self, envelope: PrivateExecutionEnvelope) -> StageReceipt: ...
    def materialize_runtime(self, envelope: PrivateExecutionEnvelope) -> StageReceipt: ...
    def bind_google_auth(self, envelope: PrivateExecutionEnvelope) -> StageReceipt: ...
    def bind_google_project(self, envelope: PrivateExecutionEnvelope) -> StageReceipt: ...
    def create_analytics_hub_link(self, envelope: PrivateExecutionEnvelope) -> StageReceipt: ...
    def run_read_only_first_access(self, envelope: PrivateExecutionEnvelope) -> StageReceipt: ...


def _is_git_sha(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def validate_private_execution_envelope(envelope: PrivateExecutionEnvelope) -> Mapping[str, Any]:
    if envelope.authorization_issue_number <= 0:
        raise WeatherNextPrivateExecutionBridgeError("authorization issue number must be positive")
    if envelope.operation_id != BRIDGE_OPERATION_ID:
        raise WeatherNextPrivateExecutionBridgeError("private execution bridge operation mismatch")
    if envelope.contract_id == PUBLIC_RUNTIME_OPERATION_ID:
        raise WeatherNextPrivateExecutionBridgeError("public Weather authority cannot dispatch private execution")
    if envelope.contract_id != CONTRACT_ID:
        raise WeatherNextPrivateExecutionBridgeError("private WeatherNext contract identity mismatch")
    if envelope.target_alias != TARGET_ALIAS:
        raise WeatherNextPrivateExecutionBridgeError("private WeatherNext target must remain rpi5")
    if not _is_git_sha(envelope.rpi5_main_source_sha):
        raise WeatherNextPrivateExecutionBridgeError("RPi5_main source SHA must be exact")
    if not _is_git_sha(envelope.weather_source_sha):
        raise WeatherNextPrivateExecutionBridgeError("Weather source SHA must be exact")
    if envelope.authorized_stages != AUTHORIZED_STAGE_SEQUENCE:
        raise WeatherNextPrivateExecutionBridgeError("private execution stage sequence mismatch")
    scope = FirstAccessScope(
        location_id=envelope.location_id,
        forecast_hours=envelope.forecast_hours,
        max_bytes_billed_per_query=envelope.max_bytes_billed_per_query,
        dry_run_required=envelope.dry_run_required,
        home_scope_enabled=envelope.home_scope_enabled,
        sqlite_write_enabled=envelope.sqlite_write_enabled,
        required_surfaces=envelope.required_surfaces,
    )
    validated_scope = validate_first_access_scope(scope)
    return {
        "operation_id": BRIDGE_OPERATION_ID,
        "contract_id": CONTRACT_ID,
        "target_alias": TARGET_ALIAS,
        "authorization_issue_number": envelope.authorization_issue_number,
        "rpi5_main_source_sha": envelope.rpi5_main_source_sha,
        "weather_source_sha": envelope.weather_source_sha,
        "authorized_stages": AUTHORIZED_STAGE_SEQUENCE,
        "scope": dict(validated_scope),
        "sqlite_write_authorized": False,
        "home_scope_enabled": False,
    }


def _already_present(stage: str) -> StageReceipt:
    return StageReceipt(stage=stage, status="already_present", mutation_performed=False)


def _validate_receipt(receipt: StageReceipt, expected_stage: str) -> StageReceipt:
    if receipt.stage != expected_stage:
        raise WeatherNextPrivateExecutionBridgeError("backend receipt stage mismatch")
    if receipt.status not in {"completed", "already_present"}:
        raise WeatherNextPrivateExecutionBridgeError("backend receipt status rejected")
    if not receipt.sanitized:
        raise WeatherNextPrivateExecutionBridgeError("backend receipt must be sanitized")
    if receipt.retry_performed or receipt.cleanup_performed or receipt.rollback_performed:
        raise WeatherNextPrivateExecutionBridgeError("automatic retry cleanup or rollback is forbidden")
    return receipt


def _pending_stages(envelope: PrivateExecutionEnvelope) -> tuple[str, ...]:
    b = envelope.baseline
    stages: list[str] = []
    if not b.application_staged:
        stages.append(PRIVATE_APPLICATION_STAGING)
    if not b.runtime_present:
        stages.append(PRIVATE_RUNTIME_MATERIALIZATION)
    if not b.auth_binding_present:
        stages.append(GOOGLE_AUTH_BINDING)
    if not b.project_binding_present:
        stages.append(GOOGLE_PROJECT_BINDING)
    if not b.linked_dataset_present:
        stages.append(ANALYTICS_HUB_LINK_CREATE)
    stages.append(READ_ONLY_PRIVATE_BIGQUERY)
    return tuple(stages)


def execute_private_execution_for_authorization(
    authorization_issue_number: int,
    *,
    canonical_revalidator: CanonicalPrivateAuthorizationRevalidator,
    authorization_consumer: AuthorizationConsumer,
    backend: PrivateExecutionBackend,
) -> Mapping[str, Any]:
    """Drive only the canonical private sequence; caller controls only the issue identity."""
    if authorization_issue_number <= 0:
        raise WeatherNextPrivateExecutionBridgeError("authorization issue number must be positive")
    envelope = canonical_revalidator.prepare_private_execution(authorization_issue_number)
    validate_private_execution_envelope(envelope)
    if envelope.authorization_issue_number != authorization_issue_number:
        raise WeatherNextPrivateExecutionBridgeError("authorization issue identity mismatch")

    pending = _pending_stages(envelope)
    authorization_consumer.consume_once(authorization_issue_number, first_stage=pending[0])
    b = envelope.baseline
    receipts = [
        _validate_receipt(backend.stage_application(envelope) if not b.application_staged else _already_present(PRIVATE_APPLICATION_STAGING), PRIVATE_APPLICATION_STAGING),
        _validate_receipt(backend.materialize_runtime(envelope) if not b.runtime_present else _already_present(PRIVATE_RUNTIME_MATERIALIZATION), PRIVATE_RUNTIME_MATERIALIZATION),
        _validate_receipt(backend.bind_google_auth(envelope) if not b.auth_binding_present else _already_present(GOOGLE_AUTH_BINDING), GOOGLE_AUTH_BINDING),
        _validate_receipt(backend.bind_google_project(envelope) if not b.project_binding_present else _already_present(GOOGLE_PROJECT_BINDING), GOOGLE_PROJECT_BINDING),
        _validate_receipt(backend.create_analytics_hub_link(envelope) if not b.linked_dataset_present else _already_present(ANALYTICS_HUB_LINK_CREATE), ANALYTICS_HUB_LINK_CREATE),
        _validate_receipt(backend.run_read_only_first_access(envelope), READ_ONLY_PRIVATE_BIGQUERY),
    ]
    return {
        "status": "private_execution_sequence_completed",
        "operation_id": BRIDGE_OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "authorization_issue_number": authorization_issue_number,
        "rpi5_main_source_sha": envelope.rpi5_main_source_sha,
        "weather_source_sha": envelope.weather_source_sha,
        "stage_receipts": tuple(receipts),
        "sqlite_write_performed": False,
        "home_scope_enabled": False,
        "automatic_retry_performed": False,
        "automatic_cleanup_performed": False,
        "automatic_rollback_performed": False,
    }


def source_readiness() -> Mapping[str, Any]:
    return {
        "operation_id": BRIDGE_OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "authorization_class": "STRICT",
        "bridge_source_implemented": True,
        "authorized_stage_sequence": AUTHORIZED_STAGE_SEQUENCE,
        "request_authority": ("authorization_issue_number",),
        "canonical_revalidation_required_immediately_before_execution": True,
        "host_capability_installed": False,
        "external_entrypoint_enabled": False,
        "runtime_activation_enabled": False,
        "global_executor_execution_enabled": False,
        "google_control_plane_execution_enabled": False,
        "credential_binding_execution_enabled": False,
        "read_only_bigquery_execution_enabled": False,
        "sqlite_write_execution_enabled": False,
        "public_runtime_authority_reusable": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "caller_private_identity_allowed": False,
        "caller_source_sha_allowed": False,
        "caller_target_allowed": False,
        "caller_mutation_sequence_allowed": False,
        "automatic_retry_allowed": False,
        "automatic_cleanup_allowed": False,
        "automatic_rollback_allowed": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
