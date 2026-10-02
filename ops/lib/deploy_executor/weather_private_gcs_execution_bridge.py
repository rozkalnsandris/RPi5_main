from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol

from .weather_private_bigquery_contract import CONTRACT_ID as BIGQUERY_CONTRACT_ID
from .weather_private_gcs_contract import (
    AUTHORIZED_STAGE_SEQUENCE,
    CONTRACT_ID,
    GCS_RUNTIME_MATERIALIZATION,
    GOOGLE_AUTH_BINDING,
    INITIAL_FORECAST_HOURS,
    INITIAL_LOCATION_ID,
    MATERIALIZED_SCALAR_CEILING,
    PRIVATE_APPLICATION_STAGING,
    READ_ONLY_PRIVATE_GCS,
    REQUIRED_GCS_PERMISSIONS,
    STATISTICS_BUCKET,
    GCSFirstAccessScope,
    validate_first_access_scope,
)

BRIDGE_OPERATION_ID = "rozkalns-weather.weathernext-private-gcs-execution-bridge.v1"
TARGET_ALIAS = "rpi5"


class WeatherNextPrivateGCSExecutionBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class GCSExecutionBaseline:
    application_staged: bool
    gcs_runtime_present: bool
    auth_binding_present: bool


@dataclass(frozen=True)
class GCSExecutionEnvelope:
    authorization_issue_number: int
    rpi5_main_source_sha: str
    weather_source_sha: str
    selected_init_utc: datetime
    baseline: GCSExecutionBaseline
    operation_id: str = BRIDGE_OPERATION_ID
    contract_id: str = CONTRACT_ID
    target_alias: str = TARGET_ALIAS
    location_id: str = INITIAL_LOCATION_ID
    forecast_hours: int = INITIAL_FORECAST_HOURS
    bucket: str = STATISTICS_BUCKET
    required_permissions: tuple[str, ...] = REQUIRED_GCS_PERMISSIONS
    materialized_scalar_ceiling: int = MATERIALIZED_SCALAR_CEILING
    home_scope_enabled: bool = False
    sqlite_write_enabled: bool = False
    automatic_retry_allowed: bool = False
    alternate_fallback_allowed: bool = False
    full_ensemble_allowed: bool = False
    authorized_stages: tuple[str, ...] = AUTHORIZED_STAGE_SEQUENCE


@dataclass(frozen=True)
class GCSStageReceipt:
    stage: str
    status: str
    mutation_performed: bool
    sanitized: bool = True
    retry_performed: bool = False
    cleanup_performed: bool = False
    rollback_performed: bool = False


class CanonicalGCSAuthorizationRevalidator(Protocol):
    def prepare_private_gcs_execution(
        self, authorization_issue_number: int
    ) -> GCSExecutionEnvelope: ...


class GCSAuthorizationConsumer(Protocol):
    def consume_once(self, authorization_issue_number: int, *, first_stage: str) -> None: ...


class GCSExecutionBackend(Protocol):
    def stage_application(self, envelope: GCSExecutionEnvelope) -> GCSStageReceipt: ...
    def materialize_gcs_runtime(self, envelope: GCSExecutionEnvelope) -> GCSStageReceipt: ...
    def bind_google_auth(self, envelope: GCSExecutionEnvelope) -> GCSStageReceipt: ...
    def run_read_only_first_access(self, envelope: GCSExecutionEnvelope) -> GCSStageReceipt: ...


def _is_git_sha(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def validate_gcs_execution_envelope(envelope: GCSExecutionEnvelope) -> Mapping[str, Any]:
    if envelope.authorization_issue_number <= 0:
        raise WeatherNextPrivateGCSExecutionBridgeError("authorization issue number must be positive")
    if envelope.operation_id != BRIDGE_OPERATION_ID:
        raise WeatherNextPrivateGCSExecutionBridgeError("GCS execution bridge operation mismatch")
    if envelope.contract_id == BIGQUERY_CONTRACT_ID:
        raise WeatherNextPrivateGCSExecutionBridgeError("BigQuery authority cannot dispatch GCS execution")
    if envelope.contract_id != CONTRACT_ID:
        raise WeatherNextPrivateGCSExecutionBridgeError("private GCS contract identity mismatch")
    if envelope.target_alias != TARGET_ALIAS:
        raise WeatherNextPrivateGCSExecutionBridgeError("private GCS target must remain rpi5")
    if not _is_git_sha(envelope.rpi5_main_source_sha):
        raise WeatherNextPrivateGCSExecutionBridgeError("RPi5_main source SHA must be exact")
    if not _is_git_sha(envelope.weather_source_sha):
        raise WeatherNextPrivateGCSExecutionBridgeError("Weather source SHA must be exact")
    if envelope.authorized_stages != AUTHORIZED_STAGE_SEQUENCE:
        raise WeatherNextPrivateGCSExecutionBridgeError("private GCS stage sequence mismatch")
    scope = GCSFirstAccessScope(
        selected_init_utc=envelope.selected_init_utc,
        location_id=envelope.location_id,
        forecast_hours=envelope.forecast_hours,
        bucket=envelope.bucket,
        required_permissions=envelope.required_permissions,
        materialized_scalar_ceiling=envelope.materialized_scalar_ceiling,
        home_scope_enabled=envelope.home_scope_enabled,
        sqlite_write_enabled=envelope.sqlite_write_enabled,
        automatic_retry_allowed=envelope.automatic_retry_allowed,
        alternate_fallback_allowed=envelope.alternate_fallback_allowed,
        full_ensemble_allowed=envelope.full_ensemble_allowed,
    )
    return {
        "operation_id": BRIDGE_OPERATION_ID,
        "contract_id": CONTRACT_ID,
        "target_alias": TARGET_ALIAS,
        "authorization_issue_number": envelope.authorization_issue_number,
        "rpi5_main_source_sha": envelope.rpi5_main_source_sha,
        "weather_source_sha": envelope.weather_source_sha,
        "authorized_stages": AUTHORIZED_STAGE_SEQUENCE,
        "scope": dict(validate_first_access_scope(scope)),
        "google_project_binding_authorized": False,
        "analytics_hub_link_authorized": False,
        "bigquery_authorized": False,
        "sqlite_write_authorized": False,
    }


def _already_present(stage: str) -> GCSStageReceipt:
    return GCSStageReceipt(stage=stage, status="already_present", mutation_performed=False)


def _validate_receipt(
    receipt: GCSStageReceipt,
    expected_stage: str,
    *,
    expected_mutation: bool,
    allow_already_present: bool = False,
) -> GCSStageReceipt:
    if receipt.stage != expected_stage:
        raise WeatherNextPrivateGCSExecutionBridgeError("backend receipt stage mismatch")
    if receipt.status not in {"completed", "already_present"}:
        raise WeatherNextPrivateGCSExecutionBridgeError("backend receipt status rejected")
    if receipt.status == "already_present":
        if not allow_already_present:
            raise WeatherNextPrivateGCSExecutionBridgeError(
                "backend cannot skip a stage canonical baseline marked required"
            )
        if receipt.mutation_performed:
            raise WeatherNextPrivateGCSExecutionBridgeError(
                "already-present stage cannot report a mutation"
            )
    elif receipt.mutation_performed != expected_mutation:
        raise WeatherNextPrivateGCSExecutionBridgeError(
            "backend receipt mutation classification mismatch"
        )
    if not receipt.sanitized:
        raise WeatherNextPrivateGCSExecutionBridgeError("backend receipt must be sanitized")
    if receipt.retry_performed or receipt.cleanup_performed or receipt.rollback_performed:
        raise WeatherNextPrivateGCSExecutionBridgeError(
            "automatic retry cleanup or rollback is forbidden"
        )
    return receipt


def _pending_stages(envelope: GCSExecutionEnvelope) -> tuple[str, ...]:
    baseline = envelope.baseline
    stages: list[str] = []
    if not baseline.application_staged:
        stages.append(PRIVATE_APPLICATION_STAGING)
    if not baseline.gcs_runtime_present:
        stages.append(GCS_RUNTIME_MATERIALIZATION)
    if not baseline.auth_binding_present:
        stages.append(GOOGLE_AUTH_BINDING)
    stages.append(READ_ONLY_PRIVATE_GCS)
    return tuple(stages)


def execute_private_gcs_for_authorization(
    authorization_issue_number: int,
    *,
    canonical_revalidator: CanonicalGCSAuthorizationRevalidator,
    authorization_consumer: GCSAuthorizationConsumer,
    backend: GCSExecutionBackend,
) -> Mapping[str, Any]:
    if authorization_issue_number <= 0:
        raise WeatherNextPrivateGCSExecutionBridgeError("authorization issue number must be positive")
    envelope = canonical_revalidator.prepare_private_gcs_execution(authorization_issue_number)
    validate_gcs_execution_envelope(envelope)
    if envelope.authorization_issue_number != authorization_issue_number:
        raise WeatherNextPrivateGCSExecutionBridgeError("authorization issue identity mismatch")

    pending = _pending_stages(envelope)
    authorization_consumer.consume_once(authorization_issue_number, first_stage=pending[0])
    baseline = envelope.baseline
    receipts = [
        _validate_receipt(
            backend.stage_application(envelope)
            if not baseline.application_staged
            else _already_present(PRIVATE_APPLICATION_STAGING),
            PRIVATE_APPLICATION_STAGING,
            expected_mutation=not baseline.application_staged,
            allow_already_present=baseline.application_staged,
        ),
        _validate_receipt(
            backend.materialize_gcs_runtime(envelope)
            if not baseline.gcs_runtime_present
            else _already_present(GCS_RUNTIME_MATERIALIZATION),
            GCS_RUNTIME_MATERIALIZATION,
            expected_mutation=not baseline.gcs_runtime_present,
            allow_already_present=baseline.gcs_runtime_present,
        ),
        _validate_receipt(
            backend.bind_google_auth(envelope)
            if not baseline.auth_binding_present
            else _already_present(GOOGLE_AUTH_BINDING),
            GOOGLE_AUTH_BINDING,
            expected_mutation=not baseline.auth_binding_present,
            allow_already_present=baseline.auth_binding_present,
        ),
        _validate_receipt(
            backend.run_read_only_first_access(envelope),
            READ_ONLY_PRIVATE_GCS,
            expected_mutation=False,
        ),
    ]
    return {
        "status": "private_gcs_execution_sequence_completed",
        "operation_id": BRIDGE_OPERATION_ID,
        "contract_id": CONTRACT_ID,
        "target_alias": TARGET_ALIAS,
        "authorization_issue_number": authorization_issue_number,
        "rpi5_main_source_sha": envelope.rpi5_main_source_sha,
        "weather_source_sha": envelope.weather_source_sha,
        "selected_init_utc": validate_gcs_execution_envelope(envelope)["scope"]["selected_init_utc"],
        "stage_receipts": tuple(receipts),
        "google_project_binding_performed": False,
        "analytics_hub_link_performed": False,
        "bigquery_performed": False,
        "sqlite_write_performed": False,
        "home_scope_enabled": False,
        "automatic_retry_performed": False,
        "automatic_cleanup_performed": False,
        "automatic_rollback_performed": False,
    }


def source_readiness() -> Mapping[str, Any]:
    return {
        "operation_id": BRIDGE_OPERATION_ID,
        "contract_id": CONTRACT_ID,
        "target_alias": TARGET_ALIAS,
        "authorization_class": "STRICT",
        "bridge_source_implemented": True,
        "authorized_stage_sequence": AUTHORIZED_STAGE_SEQUENCE,
        "request_authority": ("authorization_issue_number",),
        "selected_init_comes_from_authorization": True,
        "canonical_revalidation_required_immediately_before_execution": True,
        "gcs_runtime_materializer_implemented": True,
        "host_capability_installed": False,
        "external_entrypoint_enabled": False,
        "runtime_activation_enabled": False,
        "global_executor_execution_enabled": False,
        "credential_binding_execution_enabled": False,
        "read_only_gcs_execution_enabled": False,
        "google_project_binding_execution_enabled": False,
        "analytics_hub_link_execution_enabled": False,
        "bigquery_execution_enabled": False,
        "sqlite_write_execution_enabled": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "caller_private_identity_allowed": False,
        "caller_source_sha_allowed": False,
        "caller_target_allowed": False,
        "caller_bucket_or_prefix_allowed": False,
        "caller_coordinates_allowed": False,
        "caller_mutation_sequence_allowed": False,
        "automatic_retry_allowed": False,
        "automatic_cleanup_allowed": False,
        "automatic_rollback_allowed": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
