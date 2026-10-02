from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

CONTRACT_ID = "rozkalns-weather.weathernext-private-gcs-first-access.v1"
PUBLIC_RUNTIME_OPERATION_ID = "rozkalns-weather.public-runtime-release.v1"
SOURCE_REPOSITORY = "rozkalnsandris/rozkalns_weather"
UPSTREAM_CONTRACT_PATH = "deploy/weathernext-gcs-private-readonly-gate.json"
WEATHER_ENTRYPOINT = "rozkalns_weather.weathernext_gcs_transport.read_private_first_access_gcs"

MODEL_PROVIDER = "Google DeepMind"
MODEL_NAME = "WeatherNext 3"
MODEL_VERSION_CONTRACT = "3.0.0"
INITIAL_LOCATION_ID = "station_05480"
INITIAL_FORECAST_HOURS = 6
STATISTICS_BUCKET = "weathernext3_statistics_spatial"
REQUIRED_GCS_PERMISSIONS = ("storage.objects.list", "storage.objects.get")
MATERIALIZED_SCALAR_CEILING = 288

PRIVATE_APPLICATION_STAGING = "weathernext_private_application_staging"
GCS_RUNTIME_MATERIALIZATION = "weathernext_private_gcs_runtime_materialization"
GOOGLE_AUTH_BINDING = "google_auth_binding"
READ_ONLY_PRIVATE_GCS = "read_only_private_gcs"

AUTHORIZED_STAGE_SEQUENCE = (
    PRIVATE_APPLICATION_STAGING,
    GCS_RUNTIME_MATERIALIZATION,
    GOOGLE_AUTH_BINDING,
    READ_ONLY_PRIVATE_GCS,
)


class WeatherNextPrivateGCSContractError(ValueError):
    """Raised when source planning attempts to widen the private GCS capability."""


@dataclass(frozen=True)
class GCSFirstAccessScope:
    selected_init_utc: datetime
    location_id: str = INITIAL_LOCATION_ID
    forecast_hours: int = INITIAL_FORECAST_HOURS
    bucket: str = STATISTICS_BUCKET
    required_permissions: tuple[str, ...] = REQUIRED_GCS_PERMISSIONS
    materialized_scalar_ceiling: int = MATERIALIZED_SCALAR_CEILING
    requester_pays: bool = False
    billing_project_header_required: bool = False
    home_scope_enabled: bool = False
    sqlite_write_enabled: bool = False
    automatic_retry_allowed: bool = False
    alternate_fallback_allowed: bool = False
    full_ensemble_allowed: bool = False


def _validate_init(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise WeatherNextPrivateGCSContractError("selected init must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    if normalized.minute or normalized.second or normalized.microsecond:
        raise WeatherNextPrivateGCSContractError("selected init must be an exact UTC hour")
    if normalized.year < 2026:
        raise WeatherNextPrivateGCSContractError("selected init is outside the operational GCS era")
    return normalized


def validate_first_access_scope(scope: GCSFirstAccessScope) -> Mapping[str, Any]:
    selected_init = _validate_init(scope.selected_init_utc)
    if scope.location_id != INITIAL_LOCATION_ID:
        raise WeatherNextPrivateGCSContractError("initial GCS location must remain station_05480")
    if scope.forecast_hours != INITIAL_FORECAST_HOURS:
        raise WeatherNextPrivateGCSContractError("initial GCS forecast window must remain exactly 6h")
    if scope.bucket != STATISTICS_BUCKET:
        raise WeatherNextPrivateGCSContractError("statistics bucket identity changed")
    if tuple(scope.required_permissions) != REQUIRED_GCS_PERMISSIONS:
        raise WeatherNextPrivateGCSContractError("GCS permission surface changed")
    if scope.materialized_scalar_ceiling != MATERIALIZED_SCALAR_CEILING:
        raise WeatherNextPrivateGCSContractError("materialized scalar ceiling changed")
    if scope.requester_pays:
        raise WeatherNextPrivateGCSContractError("statistics bucket must not require Requester Pays")
    if scope.billing_project_header_required:
        raise WeatherNextPrivateGCSContractError("billing-project header is forbidden for first GCS access")
    if scope.home_scope_enabled:
        raise WeatherNextPrivateGCSContractError("private home scope is disabled for first GCS access")
    if scope.sqlite_write_enabled:
        raise WeatherNextPrivateGCSContractError("first GCS access does not authorize SQLite writes")
    if scope.automatic_retry_allowed:
        raise WeatherNextPrivateGCSContractError("automatic retry is forbidden")
    if scope.alternate_fallback_allowed:
        raise WeatherNextPrivateGCSContractError("alternate source/init fallback is forbidden")
    if scope.full_ensemble_allowed:
        raise WeatherNextPrivateGCSContractError("full-ensemble bucket fallback is forbidden")
    return {
        "selected_init_utc": selected_init.isoformat().replace("+00:00", "Z"),
        "location_id": INITIAL_LOCATION_ID,
        "forecast_hours": INITIAL_FORECAST_HOURS,
        "bucket": STATISTICS_BUCKET,
        "required_permissions": REQUIRED_GCS_PERMISSIONS,
        "materialized_scalar_ceiling": MATERIALIZED_SCALAR_CEILING,
        "requester_pays": False,
        "billing_project_header_required": False,
        "home_scope_enabled": False,
        "sqlite_write_enabled": False,
        "automatic_retry_allowed": False,
        "alternate_fallback_allowed": False,
        "full_ensemble_allowed": False,
    }


def source_contract_summary() -> Mapping[str, Any]:
    return {
        "contract_id": CONTRACT_ID,
        "source_repository": SOURCE_REPOSITORY,
        "upstream_contract_path": UPSTREAM_CONTRACT_PATH,
        "weather_entrypoint": WEATHER_ENTRYPOINT,
        "model_provider": MODEL_PROVIDER,
        "model_name": MODEL_NAME,
        "model_version_contract": MODEL_VERSION_CONTRACT,
        "authorized_stage_sequence": AUTHORIZED_STAGE_SEQUENCE,
        "project_binding_required": False,
        "dataset_binding_required": False,
        "analytics_hub_link_required": False,
        "billing_project_header_required": False,
        "bigquery_authorized": False,
        "full_ensemble_authorized": False,
        "home_scope_authorized": False,
        "sqlite_write_authorized": False,
        "credential_material_in_github": False,
        "caller_private_identity_allowed": False,
        "execution_enabled": False,
        "source_merge_authorizes_live": False,
    }
