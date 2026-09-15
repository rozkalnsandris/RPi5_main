from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .weather_private_bigquery_contract import (
    ANALYTICS_HUB_LINK_CREATE,
    CONTRACT_ID,
    FIRST_ACCESS_STAGES,
    GOOGLE_AUTH_BINDING,
    GOOGLE_PROJECT_BINDING,
    INITIAL_FORECAST_HOURS,
    INITIAL_LOCATION_ID,
    MAX_BYTES_BILLED_PER_QUERY,
    MODEL_VERSION_CONTRACT,
    PRIVATE_RUNTIME_MATERIALIZATION,
    READ_ONLY_PRIVATE_BIGQUERY,
    REQUIRED_SURFACES,
    FirstAccessScope,
    validate_first_access_scope,
)
from .weather_private_bigquery_execution_bridge import (
    BRIDGE_OPERATION_ID,
    PRIVATE_APPLICATION_STAGING,
    TARGET_ALIAS,
    PrivateExecutionBackend,
    PrivateExecutionBaseline,
    PrivateExecutionEnvelope,
    StageReceipt,
    WeatherNextPrivateExecutionBridgeError,
    execute_private_execution_for_authorization,
)
from .weather_private_bigquery_runtime_materialization import (
    RuntimeArtifactReceipt,
    TARGET_PYTHON_ABI,
    materialize_reviewed_runtime,
)

TRUSTED_BACKEND_OPERATION_ID = "rozkalns-weather.weathernext-private-trusted-backend.v1"
HOST_CAPABILITY_ID = "rpi5.weathernext-private-backend.v1"
SOURCE_STATUS = "SOURCE_READY_HOST_CAPABILITY_INSTALL_REQUIRED"
APPLICATION_STAGE_ID = "rozkalns-weather.weathernext-private-application-stage.v1"
APPLICATION_STAGE_ROOT = "/var/lib/rpi5-deploy/weather-private-application"
GOOGLE_AUTH_SLOT_ID = "weathernext-private-google-auth-v1"
GOOGLE_AUTH_MECHANISM = "root-owned-runtime-credential-reference"
GOOGLE_PROJECT_SLOT_ID = "weathernext-private-google-project-v1"
ANALYTICS_HUB_LINK_SLOT_ID = "weathernext-private-approved-linked-dataset-v1"
FIRST_ACCESS_ENTRYPOINT = "rozkalns_weather.weathernext_access.read_first_access_canary"
FIRST_ACCESS_GATE_ISSUE = 122
BINDING_STATES = ("absent", "ready", "mismatch")
SANITIZED_READINESS_KEYS = (
    "backend_source_implemented",
    "host_capability_installed",
    "application_staged",
    "runtime_materialized",
    "auth_bound",
    "project_bound",
    "linked_dataset_present",
    "read_only_first_access_authorized",
    "read_only_first_access_executed",
)


class WeatherNextPrivateTrustedBackendError(RuntimeError):
    """Raised when the trusted private source contract cannot fail closed."""


def _is_git_sha(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class CanonicalPrivateFacts:
    authorization_issue_number: int
    owner_authorized: bool
    authorization_operation_id: str
    authorization_contract_id: str
    rpi5_main_source_sha: str
    rpi5_main_ci_success: bool
    weather_source_sha: str
    weather_ci_success: bool
    target_alias: str
    host_capability_installed: bool
    application_staged: bool
    runtime_present: bool
    runtime_python_abi: str | None
    auth_binding_state: str
    project_binding_state: str
    linked_dataset_state: str
    read_only_first_access_authorized: bool = False
    read_only_first_access_executed: bool = False


class CanonicalPrivateFactsProvider(Protocol):
    """Trusted provider; the caller supplies only an owner authorization issue identity."""

    def load_private_facts(self, authorization_issue_number: int) -> CanonicalPrivateFacts: ...


class ExactWeatherApplicationStager(Protocol):
    def stage_exact_weather_source(
        self,
        *,
        weather_source_sha: str,
        stage_id: str,
        stage_root: str,
    ) -> StageReceipt: ...


class RuntimeArtifactReceiptProvider(Protocol):
    def load_runtime_artifact_receipt(self, rpi5_main_source_sha: str) -> RuntimeArtifactReceipt: ...


class FixedGoogleAuthBinder(Protocol):
    def bind_fixed_auth_slot(self, *, slot_id: str, mechanism: str) -> StageReceipt: ...


class FixedGoogleProjectBinder(Protocol):
    def bind_fixed_project_slot(self, *, slot_id: str) -> StageReceipt: ...


class FixedAnalyticsHubLinkBinder(Protocol):
    def ensure_fixed_link_slot(self, *, slot_id: str) -> StageReceipt: ...


class FixedReadOnlyFirstAccessRunner(Protocol):
    def run_fixed_first_access(
        self,
        *,
        weather_source_sha: str,
        entrypoint: str,
        scope: FirstAccessScope,
    ) -> StageReceipt: ...


@dataclass(frozen=True)
class TrustedCapabilitySet:
    application_stager: ExactWeatherApplicationStager
    runtime_receipts: RuntimeArtifactReceiptProvider
    google_auth: FixedGoogleAuthBinder
    google_project: FixedGoogleProjectBinder
    analytics_hub: FixedAnalyticsHubLinkBinder
    first_access: FixedReadOnlyFirstAccessRunner


def _validate_binding_state(name: str, value: str) -> bool:
    if value not in BINDING_STATES:
        raise WeatherNextPrivateTrustedBackendError(f"{name} binding state invalid")
    if value == "mismatch":
        raise WeatherNextPrivateTrustedBackendError(f"{name} binding mismatch")
    return value == "ready"


def validate_canonical_private_facts(
    facts: CanonicalPrivateFacts,
    *,
    requested_issue_number: int,
) -> Mapping[str, Any]:
    if requested_issue_number <= 0 or facts.authorization_issue_number != requested_issue_number:
        raise WeatherNextPrivateTrustedBackendError("owner authorization issue identity mismatch")
    if not facts.owner_authorized:
        raise WeatherNextPrivateTrustedBackendError("owner authorization is not active")
    if facts.authorization_operation_id != BRIDGE_OPERATION_ID:
        raise WeatherNextPrivateTrustedBackendError("owner authorization operation identity mismatch")
    if facts.authorization_contract_id != CONTRACT_ID:
        raise WeatherNextPrivateTrustedBackendError("owner authorization contract identity mismatch")
    if facts.target_alias != TARGET_ALIAS:
        raise WeatherNextPrivateTrustedBackendError("private target must remain rpi5")
    if not _is_git_sha(facts.rpi5_main_source_sha):
        raise WeatherNextPrivateTrustedBackendError("RPi5_main source SHA must be exact")
    if not _is_git_sha(facts.weather_source_sha):
        raise WeatherNextPrivateTrustedBackendError("Weather source SHA must be exact")
    if not facts.rpi5_main_ci_success or not facts.weather_ci_success:
        raise WeatherNextPrivateTrustedBackendError("exact-source required CI must be successful")
    if facts.runtime_present:
        if facts.runtime_python_abi != TARGET_PYTHON_ABI:
            raise WeatherNextPrivateTrustedBackendError("reviewed private runtime must remain cp313")
    elif facts.runtime_python_abi is not None:
        raise WeatherNextPrivateTrustedBackendError(
            "system Python cannot substitute for the absent reviewed private runtime"
        )

    auth_ready = _validate_binding_state("google auth", facts.auth_binding_state)
    project_ready = _validate_binding_state("google project", facts.project_binding_state)
    link_ready = _validate_binding_state("Analytics Hub linked dataset", facts.linked_dataset_state)

    readiness = {
        "backend_source_implemented": True,
        "host_capability_installed": facts.host_capability_installed,
        "application_staged": facts.application_staged,
        "runtime_materialized": facts.runtime_present,
        "auth_bound": auth_ready,
        "project_bound": project_ready,
        "linked_dataset_present": link_ready,
        "read_only_first_access_authorized": facts.read_only_first_access_authorized,
        "read_only_first_access_executed": facts.read_only_first_access_executed,
    }
    if tuple(readiness) != SANITIZED_READINESS_KEYS:
        raise WeatherNextPrivateTrustedBackendError("sanitized readiness schema drift")
    return readiness


class CanonicalWeatherNextPrivateRevalidator:
    def __init__(self, provider: CanonicalPrivateFactsProvider):
        self._provider = provider

    def prepare_private_execution(self, authorization_issue_number: int) -> PrivateExecutionEnvelope:
        if authorization_issue_number <= 0:
            raise WeatherNextPrivateTrustedBackendError("authorization issue number must be positive")
        facts = self._provider.load_private_facts(authorization_issue_number)
        validate_canonical_private_facts(facts, requested_issue_number=authorization_issue_number)
        return PrivateExecutionEnvelope(
            authorization_issue_number=authorization_issue_number,
            rpi5_main_source_sha=facts.rpi5_main_source_sha,
            weather_source_sha=facts.weather_source_sha,
            baseline=PrivateExecutionBaseline(
                application_staged=facts.application_staged,
                runtime_present=facts.runtime_present,
                auth_binding_present=facts.auth_binding_state == "ready",
                project_binding_present=facts.project_binding_state == "ready",
                linked_dataset_present=facts.linked_dataset_state == "ready",
            ),
        )


class TrustedWeatherNextPrivateBackend(PrivateExecutionBackend):
    def __init__(self, capabilities: TrustedCapabilitySet):
        self._capabilities = capabilities

    def stage_application(self, envelope: PrivateExecutionEnvelope) -> StageReceipt:
        return self._capabilities.application_stager.stage_exact_weather_source(
            weather_source_sha=envelope.weather_source_sha,
            stage_id=APPLICATION_STAGE_ID,
            stage_root=APPLICATION_STAGE_ROOT,
        )

    def materialize_runtime(self, envelope: PrivateExecutionEnvelope) -> StageReceipt:
        receipt = self._capabilities.runtime_receipts.load_runtime_artifact_receipt(
            envelope.rpi5_main_source_sha
        )
        materialize_reviewed_runtime(
            CONTRACT_ID,
            receipt,
            expected_source_sha=envelope.rpi5_main_source_sha,
        )
        return StageReceipt(
            stage=PRIVATE_RUNTIME_MATERIALIZATION,
            status="completed",
            mutation_performed=True,
        )

    def bind_google_auth(self, envelope: PrivateExecutionEnvelope) -> StageReceipt:
        return self._capabilities.google_auth.bind_fixed_auth_slot(
            slot_id=GOOGLE_AUTH_SLOT_ID,
            mechanism=GOOGLE_AUTH_MECHANISM,
        )

    def bind_google_project(self, envelope: PrivateExecutionEnvelope) -> StageReceipt:
        return self._capabilities.google_project.bind_fixed_project_slot(
            slot_id=GOOGLE_PROJECT_SLOT_ID
        )

    def create_analytics_hub_link(self, envelope: PrivateExecutionEnvelope) -> StageReceipt:
        return self._capabilities.analytics_hub.ensure_fixed_link_slot(
            slot_id=ANALYTICS_HUB_LINK_SLOT_ID
        )

    def run_read_only_first_access(self, envelope: PrivateExecutionEnvelope) -> StageReceipt:
        scope = FirstAccessScope(
            location_id=envelope.location_id,
            forecast_hours=envelope.forecast_hours,
            max_bytes_billed_per_query=envelope.max_bytes_billed_per_query,
            dry_run_required=envelope.dry_run_required,
            home_scope_enabled=envelope.home_scope_enabled,
            sqlite_write_enabled=envelope.sqlite_write_enabled,
            required_surfaces=envelope.required_surfaces,
        )
        validate_first_access_scope(scope)
        return self._capabilities.first_access.run_fixed_first_access(
            weather_source_sha=envelope.weather_source_sha,
            entrypoint=FIRST_ACCESS_ENTRYPOINT,
            scope=scope,
        )


class TrustedPrivateHostEntrypoint:
    """Install-time wiring; there is no module-level live entrypoint or generic dispatcher."""

    def __init__(
        self,
        *,
        canonical_revalidator: CanonicalWeatherNextPrivateRevalidator,
        authorization_consumer: Any,
        backend: TrustedWeatherNextPrivateBackend,
    ):
        self._canonical_revalidator = canonical_revalidator
        self._authorization_consumer = authorization_consumer
        self._backend = backend

    def dispatch(self, authorization_issue_number: int) -> Mapping[str, Any]:
        return execute_private_execution_for_authorization(
            authorization_issue_number,
            canonical_revalidator=self._canonical_revalidator,
            authorization_consumer=self._authorization_consumer,
            backend=self._backend,
        )


def trusted_backend_source_contract() -> Mapping[str, Any]:
    return {
        "operation_id": TRUSTED_BACKEND_OPERATION_ID,
        "bridge_operation_id": BRIDGE_OPERATION_ID,
        "contract_id": CONTRACT_ID,
        "host_capability_id": HOST_CAPABILITY_ID,
        "target_alias": TARGET_ALIAS,
        "status": SOURCE_STATUS,
        "authorization_class": "STRICT",
        "ordinary_live_all_eligible": False,
        "request_authority": ("authorization_issue_number",),
        "canonical_revalidation_required": True,
        "required_exact_source_ci": ("RPi5_main", "rozkalns_weather"),
        "application_stage": {
            "stage_id": APPLICATION_STAGE_ID,
            "fixed_root": APPLICATION_STAGE_ROOT,
            "caller_path_allowed": False,
            "caller_source_sha_allowed": False,
        },
        "runtime": {
            "reviewed_python_abi": TARGET_PYTHON_ABI,
            "system_python_substitution_allowed": False,
            "reviewed_materializer_reused": True,
            "live_network_install_allowed": False,
            "package_manager_allowed": False,
        },
        "binding_slots": {
            "google_auth": GOOGLE_AUTH_SLOT_ID,
            "google_auth_mechanism": GOOGLE_AUTH_MECHANISM,
            "google_project": GOOGLE_PROJECT_SLOT_ID,
            "analytics_hub_link": ANALYTICS_HUB_LINK_SLOT_ID,
        },
        "first_access": {
            "gate_issue": FIRST_ACCESS_GATE_ISSUE,
            "entrypoint": FIRST_ACCESS_ENTRYPOINT,
            "model_version_contract": MODEL_VERSION_CONTRACT,
            "location_id": INITIAL_LOCATION_ID,
            "forecast_hours": INITIAL_FORECAST_HOURS,
            "required_surfaces": REQUIRED_SURFACES,
            "dry_run_required": True,
            "maximum_bytes_billed_per_query_hard_ceiling": MAX_BYTES_BILLED_PER_QUERY,
            "first_access_stages": FIRST_ACCESS_STAGES,
            "home_scope_enabled": False,
            "sqlite_write_enabled": False,
            "caller_query_allowed": False,
        },
        "sanitized_readiness_keys": SANITIZED_READINESS_KEYS,
        "host_capability_installed": False,
        "external_entrypoint_enabled": False,
        "global_executor_execution_enabled": False,
        "credential_binding_execution_enabled": False,
        "google_control_plane_execution_enabled": False,
        "read_only_bigquery_execution_enabled": False,
        "sqlite_write_execution_enabled": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
