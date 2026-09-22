from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

CONTRACT_ID = "rozkalns-weather.weathernext-private-bigquery-first-access.v1"
PUBLIC_RUNTIME_OPERATION_ID = "rozkalns-weather.public-runtime-release.v1"
SOURCE_REPOSITORY = "rozkalnsandris/rozkalns_weather"
UPSTREAM_CONTRACT_PATH = "deploy/weathernext-first-access.json"
UPSTREAM_RUNBOOK_PATH = "docs/WEATHERNEXT_FIRST_ACCESS.md"
MODEL_PROVIDER = "Google DeepMind"
MODEL_NAME = "WeatherNext 3"
MODEL_VERSION_CONTRACT = "3.0.0"
EXPECTED_TABLES = (
    "weathernext_3_0_0_0p05deg",
    "weathernext_3_0_0_0p1deg",
)
REQUIRED_SURFACES = ("0p05_station", "0p1_surface")
INITIAL_LOCATION_ID = "station_05480"
INITIAL_FORECAST_HOURS = 6
MAX_BYTES_BILLED_PER_QUERY = 1_073_741_824
BIGQUERY_DEPENDENCY = "google-cloud-bigquery>=3.36,<4"
RUNTIME_STRATEGY = "isolated-reviewed-python-closure"

FIRST_ACCESS_STAGES = (
    "linked_dataset_probe",
    "schema_fingerprint",
    "dry_run_cost_guard",
    "bounded_canary_query",
    "provenance_validate",
)

PRIVATE_RUNTIME_MATERIALIZATION = "weathernext_private_runtime_materialization"
GOOGLE_AUTH_BINDING = "google_auth_binding"
GOOGLE_PROJECT_BINDING = "google_project_binding"
ANALYTICS_HUB_LINK_CREATE = "analytics_hub_link_create"
READ_ONLY_PRIVATE_BIGQUERY = "read_only_private_bigquery"
PRODUCTION_SQLITE_SNAPSHOT_WRITE = "production_sqlite_forecast_snapshot_write"

PRIVATE_MUTATION_CLASSES = (
    PRIVATE_RUNTIME_MATERIALIZATION,
    GOOGLE_AUTH_BINDING,
    GOOGLE_PROJECT_BINDING,
    ANALYTICS_HUB_LINK_CREATE,
    READ_ONLY_PRIVATE_BIGQUERY,
)

OWNER_GATE_SEQUENCE = (
    "private_runtime_materialization_if_absent",
    "google_auth_and_project_binding_if_absent",
    "analytics_hub_link_create_if_absent",
    "read_only_private_bigquery_first_access",
    "production_sqlite_forecast_snapshot_write_separate_later_gate",
)


class WeatherNextPrivateContractError(ValueError):
    """Raised when source planning attempts to widen the private capability."""


@dataclass(frozen=True)
class FirstAccessScope:
    location_id: str = INITIAL_LOCATION_ID
    forecast_hours: int = INITIAL_FORECAST_HOURS
    max_bytes_billed_per_query: int = MAX_BYTES_BILLED_PER_QUERY
    dry_run_required: bool = True
    home_scope_enabled: bool = False
    sqlite_write_enabled: bool = False
    required_surfaces: tuple[str, ...] = REQUIRED_SURFACES
    model_version_contract: str = MODEL_VERSION_CONTRACT
    table_names: tuple[str, ...] = EXPECTED_TABLES


@dataclass(frozen=True)
class PrivateRuntimeReadiness:
    isolated_runtime_present: bool
    auth_binding_present: bool
    project_binding_present: bool
    linked_dataset_present: bool
    access_permission_granted: bool | None = None


def validate_first_access_scope(scope: FirstAccessScope) -> Mapping[str, Any]:
    if scope.location_id != INITIAL_LOCATION_ID:
        raise WeatherNextPrivateContractError("initial canary location must remain station_05480")
    if scope.forecast_hours != INITIAL_FORECAST_HOURS:
        raise WeatherNextPrivateContractError("initial canary forecast window must remain exactly 6h")
    if not scope.dry_run_required:
        raise WeatherNextPrivateContractError("BigQuery dry-run is mandatory before a real canary")
    if scope.max_bytes_billed_per_query <= 0:
        raise WeatherNextPrivateContractError("maximum bytes billed must be positive")
    if scope.max_bytes_billed_per_query > MAX_BYTES_BILLED_PER_QUERY:
        raise WeatherNextPrivateContractError("maximum bytes billed exceeds the 1 GiB/query hard ceiling")
    if scope.home_scope_enabled:
        raise WeatherNextPrivateContractError("private home scope is disabled for first access")
    if scope.sqlite_write_enabled:
        raise WeatherNextPrivateContractError("first-access contract does not authorize SQLite writes")
    if scope.required_surfaces != REQUIRED_SURFACES:
        raise WeatherNextPrivateContractError("required WeatherNext product surfaces changed")
    if scope.model_version_contract != MODEL_VERSION_CONTRACT:
        raise WeatherNextPrivateContractError("WeatherNext model-version contract changed")
    if scope.table_names != EXPECTED_TABLES:
        raise WeatherNextPrivateContractError("WeatherNext table identity changed")
    return {
        "location_id": INITIAL_LOCATION_ID,
        "forecast_hours": INITIAL_FORECAST_HOURS,
        "max_bytes_billed_per_query": scope.max_bytes_billed_per_query,
        "maximum_allowed_bytes_billed_per_query": MAX_BYTES_BILLED_PER_QUERY,
        "dry_run_required": True,
        "home_scope_enabled": False,
        "sqlite_write_enabled": False,
        "required_surfaces": REQUIRED_SURFACES,
        "model_version_contract": MODEL_VERSION_CONTRACT,
        "table_names": EXPECTED_TABLES,
    }


def classify_runtime_readiness(evidence: PrivateRuntimeReadiness) -> str:
    """Classify only sanitized present/absent evidence; never inspect secret material."""
    if not evidence.isolated_runtime_present:
        return "private_runtime_required"
    if not evidence.auth_binding_present:
        return "credential_binding_required"
    if not evidence.project_binding_present:
        return "google_project_binding_required"
    if not evidence.linked_dataset_present:
        return "analytics_hub_link_required"
    if evidence.access_permission_granted is False:
        return "permission_denied"
    if evidence.access_permission_granted is None:
        return "read_only_access_probe_required"
    return "ready_for_read_only_first_access"


def plan_later_owner_gate(authority_id: str, mutation_class: str) -> Mapping[str, Any]:
    """Describe a later gate without granting or executing it."""
    if mutation_class == PRODUCTION_SQLITE_SNAPSHOT_WRITE:
        if authority_id == PUBLIC_RUNTIME_OPERATION_ID:
            raise WeatherNextPrivateContractError("public Weather authority cannot authorize SQLite snapshot writes")
        return {
            "mutation_class": mutation_class,
            "requires_explicit_owner_gate": True,
            "separate_from_first_access": True,
            "execution_enabled": False,
        }
    if mutation_class not in PRIVATE_MUTATION_CLASSES:
        raise WeatherNextPrivateContractError("unknown or unbounded private mutation class")
    if authority_id == PUBLIC_RUNTIME_OPERATION_ID:
        raise WeatherNextPrivateContractError("public Weather authority cannot authorize private BigQuery classes")
    if authority_id != CONTRACT_ID:
        raise WeatherNextPrivateContractError("private WeatherNext authority identity mismatch")
    return {
        "mutation_class": mutation_class,
        "requires_explicit_owner_gate": True,
        "execution_enabled": False,
        "source_contract_only": True,
    }


def source_contract_summary() -> Mapping[str, Any]:
    """Return public-safe source metadata only; never private Google identifiers."""
    return {
        "contract_id": CONTRACT_ID,
        "source_repository": SOURCE_REPOSITORY,
        "upstream_contract_path": UPSTREAM_CONTRACT_PATH,
        "upstream_runbook_path": UPSTREAM_RUNBOOK_PATH,
        "jit_weather_source_sha_required": True,
        "model_provider": MODEL_PROVIDER,
        "model_name": MODEL_NAME,
        "model_version_contract": MODEL_VERSION_CONTRACT,
        "expected_tables": EXPECTED_TABLES,
        "first_access_stages": FIRST_ACCESS_STAGES,
        "runtime_strategy": RUNTIME_STRATEGY,
        "runtime_dependency": BIGQUERY_DEPENDENCY,
        "private_mutation_classes": PRIVATE_MUTATION_CLASSES,
        "owner_gate_sequence": OWNER_GATE_SEQUENCE,
        "project_identity_in_github": False,
        "dataset_identity_in_github": False,
        "credential_material_in_github": False,
        "home_coordinates_in_github": False,
        "generic_shell_or_package_authority": False,
        "public_runtime_authority_reusable": False,
        "execution_enabled": False,
        "google_control_plane_mutation_authorized": False,
        "credential_mutation_authorized": False,
        "read_only_bigquery_authorized": False,
        "sqlite_write_authorized": False,
    }
