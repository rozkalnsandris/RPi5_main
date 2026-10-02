from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol

from .weather_private_gcs_contract import (
    CONTRACT_ID,
    GCS_RUNTIME_MATERIALIZATION,
    GOOGLE_AUTH_BINDING,
    PRIVATE_APPLICATION_STAGING,
    READ_ONLY_PRIVATE_GCS,
    WEATHER_ENTRYPOINT,
    GCSFirstAccessScope,
    validate_first_access_scope,
)
from .weather_private_gcs_execution_bridge import (
    BRIDGE_OPERATION_ID,
    TARGET_ALIAS,
    GCSAuthorizationConsumer,
    GCSExecutionBaseline,
    GCSExecutionEnvelope,
    GCSStageReceipt,
    execute_private_gcs_for_authorization,
)

HOST_CAPABILITY_ID = "rpi5.weathernext-private-gcs-backend.v1"
SOURCE_STATUS = "SOURCE_READY_GCS_READONLY_PREFLIGHT"
APPLICATION_STAGE_ID = "rozkalns-weather.weathernext-private-application-stage.v1"
APPLICATION_STAGE_ROOT = "/var/lib/rpi5-deploy/weather-private-application"
GOOGLE_AUTH_SLOT_ID = "weathernext-private-google-auth-v1"
GOOGLE_AUTH_MECHANISM = "root-owned-runtime-credential-reference"
BINDING_STATES = ("absent", "ready", "mismatch")


class WeatherNextPrivateGCSTrustedBackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalGCSFacts:
    authorization_issue_number: int
    owner_authorized: bool
    authorization_operation_id: str
    authorization_contract_id: str
    rpi5_main_source_sha: str
    rpi5_main_ci_success: bool
    weather_source_sha: str
    weather_ci_success: bool
    selected_init_utc: datetime
    target_alias: str
    application_staged: bool
    gcs_runtime_present: bool
    auth_binding_state: str
    host_capability_installed: bool = False
    read_only_first_access_authorized: bool = False
    read_only_first_access_executed: bool = False


class CanonicalGCSFactsProvider(Protocol):
    def load_gcs_facts(self, authorization_issue_number: int) -> CanonicalGCSFacts: ...


class ExactWeatherApplicationStager(Protocol):
    def stage_exact_weather_source(
        self, *, weather_source_sha: str, stage_id: str, stage_root: str
    ) -> GCSStageReceipt: ...


class GCSRuntimeMaterializer(Protocol):
    def materialize_exact_gcs_runtime(self, *, rpi5_main_source_sha: str) -> GCSStageReceipt: ...


class FixedGoogleAuthBinder(Protocol):
    def bind_fixed_auth_slot(self, *, slot_id: str, mechanism: str) -> GCSStageReceipt: ...


class FixedReadOnlyGCSRunner(Protocol):
    def run_fixed_gcs_first_access(
        self,
        *,
        weather_source_sha: str,
        entrypoint: str,
        scope: GCSFirstAccessScope,
    ) -> GCSStageReceipt: ...


@dataclass(frozen=True)
class TrustedGCSCapabilitySet:
    application_stager: ExactWeatherApplicationStager
    runtime_materializer: GCSRuntimeMaterializer
    google_auth: FixedGoogleAuthBinder
    first_access: FixedReadOnlyGCSRunner


def _is_git_sha(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def validate_canonical_gcs_facts(
    facts: CanonicalGCSFacts,
    *,
    requested_issue_number: int,
) -> Mapping[str, Any]:
    if requested_issue_number <= 0 or facts.authorization_issue_number != requested_issue_number:
        raise WeatherNextPrivateGCSTrustedBackendError("owner authorization issue identity mismatch")
    if facts.owner_authorized is not True:
        raise WeatherNextPrivateGCSTrustedBackendError("owner authorization is not active")
    if facts.authorization_operation_id != BRIDGE_OPERATION_ID:
        raise WeatherNextPrivateGCSTrustedBackendError("owner authorization operation identity mismatch")
    if facts.authorization_contract_id != CONTRACT_ID:
        raise WeatherNextPrivateGCSTrustedBackendError("owner authorization contract identity mismatch")
    if facts.target_alias != TARGET_ALIAS:
        raise WeatherNextPrivateGCSTrustedBackendError("private GCS target must remain rpi5")
    if not _is_git_sha(facts.rpi5_main_source_sha):
        raise WeatherNextPrivateGCSTrustedBackendError("RPi5_main source SHA must be exact")
    if not _is_git_sha(facts.weather_source_sha):
        raise WeatherNextPrivateGCSTrustedBackendError("Weather source SHA must be exact")
    if not facts.rpi5_main_ci_success or not facts.weather_ci_success:
        raise WeatherNextPrivateGCSTrustedBackendError("exact-source required CI must be successful")
    if facts.auth_binding_state not in BINDING_STATES:
        raise WeatherNextPrivateGCSTrustedBackendError("Google auth binding state invalid")
    if facts.auth_binding_state == "mismatch":
        raise WeatherNextPrivateGCSTrustedBackendError("Google auth binding mismatch")

    scope = GCSFirstAccessScope(selected_init_utc=facts.selected_init_utc)
    validated_scope = validate_first_access_scope(scope)
    return {
        "host_capability_id": HOST_CAPABILITY_ID,
        "source_status": SOURCE_STATUS,
        "application_staged": facts.application_staged,
        "gcs_runtime_present": facts.gcs_runtime_present,
        "auth_bound": facts.auth_binding_state == "ready",
        "read_only_first_access_authorized": facts.read_only_first_access_authorized,
        "read_only_first_access_executed": facts.read_only_first_access_executed,
        "scope": dict(validated_scope),
    }


class CanonicalWeatherNextGCSRevalidator:
    def __init__(self, provider: CanonicalGCSFactsProvider):
        self._provider = provider

    def prepare_private_gcs_execution(
        self, authorization_issue_number: int
    ) -> GCSExecutionEnvelope:
        if authorization_issue_number <= 0:
            raise WeatherNextPrivateGCSTrustedBackendError(
                "authorization issue number must be positive"
            )
        facts = self._provider.load_gcs_facts(authorization_issue_number)
        validate_canonical_gcs_facts(facts, requested_issue_number=authorization_issue_number)
        return GCSExecutionEnvelope(
            authorization_issue_number=authorization_issue_number,
            rpi5_main_source_sha=facts.rpi5_main_source_sha,
            weather_source_sha=facts.weather_source_sha,
            selected_init_utc=facts.selected_init_utc,
            baseline=GCSExecutionBaseline(
                application_staged=facts.application_staged,
                gcs_runtime_present=facts.gcs_runtime_present,
                auth_binding_present=facts.auth_binding_state == "ready",
            ),
        )


class FixedApplicationStager:
    def __init__(self, delegate: ExactWeatherApplicationStager):
        self._delegate = delegate

    def stage_exact_weather_source(
        self, *, weather_source_sha: str, stage_id: str, stage_root: str
    ) -> GCSStageReceipt:
        if stage_id != APPLICATION_STAGE_ID or stage_root != APPLICATION_STAGE_ROOT:
            raise WeatherNextPrivateGCSTrustedBackendError(
                "Weather application staging identity drifted"
            )
        return self._delegate.stage_exact_weather_source(
            weather_source_sha=weather_source_sha,
            stage_id=stage_id,
            stage_root=stage_root,
        )


class FixedGCSRuntimeMaterializer:
    def __init__(self, delegate: GCSRuntimeMaterializer):
        self._delegate = delegate

    def materialize_exact_gcs_runtime(
        self, *, rpi5_main_source_sha: str
    ) -> GCSStageReceipt:
        return self._delegate.materialize_exact_gcs_runtime(
            rpi5_main_source_sha=rpi5_main_source_sha
        )


class FixedGCSGoogleAuthBinder:
    def __init__(self, delegate: FixedGoogleAuthBinder):
        self._delegate = delegate

    def bind_fixed_auth_slot(
        self, *, slot_id: str, mechanism: str
    ) -> GCSStageReceipt:
        if slot_id != GOOGLE_AUTH_SLOT_ID or mechanism != GOOGLE_AUTH_MECHANISM:
            raise WeatherNextPrivateGCSTrustedBackendError("Google auth binding slot drifted")
        return self._delegate.bind_fixed_auth_slot(slot_id=slot_id, mechanism=mechanism)


class FixedGCSFirstAccessRunner:
    def __init__(self, delegate: FixedReadOnlyGCSRunner):
        self._delegate = delegate

    def run_fixed_gcs_first_access(
        self,
        *,
        weather_source_sha: str,
        entrypoint: str,
        scope: GCSFirstAccessScope,
    ) -> GCSStageReceipt:
        if entrypoint != WEATHER_ENTRYPOINT:
            raise WeatherNextPrivateGCSTrustedBackendError(
                "WeatherNext GCS first-access entrypoint drifted"
            )
        validate_first_access_scope(scope)
        return self._delegate.run_fixed_gcs_first_access(
            weather_source_sha=weather_source_sha,
            entrypoint=entrypoint,
            scope=scope,
        )


class TrustedWeatherNextGCSBackend:
    def __init__(self, capabilities: TrustedGCSCapabilitySet):
        self._capabilities = capabilities

    def stage_application(self, envelope: GCSExecutionEnvelope) -> GCSStageReceipt:
        return self._capabilities.application_stager.stage_exact_weather_source(
            weather_source_sha=envelope.weather_source_sha,
            stage_id=APPLICATION_STAGE_ID,
            stage_root=APPLICATION_STAGE_ROOT,
        )

    def materialize_gcs_runtime(self, envelope: GCSExecutionEnvelope) -> GCSStageReceipt:
        return self._capabilities.runtime_materializer.materialize_exact_gcs_runtime(
            rpi5_main_source_sha=envelope.rpi5_main_source_sha
        )

    def bind_google_auth(self, envelope: GCSExecutionEnvelope) -> GCSStageReceipt:
        return self._capabilities.google_auth.bind_fixed_auth_slot(
            slot_id=GOOGLE_AUTH_SLOT_ID,
            mechanism=GOOGLE_AUTH_MECHANISM,
        )

    def run_read_only_first_access(self, envelope: GCSExecutionEnvelope) -> GCSStageReceipt:
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
        return self._capabilities.first_access.run_fixed_gcs_first_access(
            weather_source_sha=envelope.weather_source_sha,
            entrypoint=WEATHER_ENTRYPOINT,
            scope=scope,
        )


class TrustedGCSHostEntrypoint:
    """Source-only fixed wrapper; no module-level host implementation is installed."""

    def __init__(
        self,
        *,
        canonical_revalidator: CanonicalWeatherNextGCSRevalidator,
        authorization_consumer: GCSAuthorizationConsumer,
        backend: TrustedWeatherNextGCSBackend,
    ):
        self._canonical_revalidator = canonical_revalidator
        self._authorization_consumer = authorization_consumer
        self._backend = backend

    def dispatch(self, authorization_issue_number: int) -> Mapping[str, Any]:
        return execute_private_gcs_for_authorization(
            authorization_issue_number,
            canonical_revalidator=self._canonical_revalidator,
            authorization_consumer=self._authorization_consumer,
            backend=self._backend,
        )


def trusted_backend_source_contract() -> Mapping[str, Any]:
    return {
        "host_capability_id": HOST_CAPABILITY_ID,
        "source_status": SOURCE_STATUS,
        "bridge_operation_id": BRIDGE_OPERATION_ID,
        "contract_id": CONTRACT_ID,
        "target_alias": TARGET_ALIAS,
        "application_stage_id": APPLICATION_STAGE_ID,
        "google_auth_slot_id": GOOGLE_AUTH_SLOT_ID,
        "weather_entrypoint": WEATHER_ENTRYPOINT,
        "canonical_revalidator_implemented": True,
        "fixed_adapter_composition_implemented": True,
        "source_wrapper_implemented": True,
        "gcs_runtime_materializer_implementation_present": True,
        "gcs_runtime_materializer_module": "deploy_executor.weather_private_gcs_runtime_materialization",
        "host_runtime_source_implemented": True,
        "host_runtime_module": "deploy_executor.weather_private_gcs_host_runtime",
        "sanitized_host_evidence_source_implemented": True,
        "host_capability_installed": False,
        "external_entrypoint_enabled": False,
        "global_executor_execution_enabled": False,
        "credential_read_enabled": False,
        "credential_binding_execution_enabled": False,
        "read_only_gcs_execution_enabled": False,
        "project_binding_execution_enabled": False,
        "analytics_hub_execution_enabled": False,
        "bigquery_execution_enabled": False,
        "sqlite_write_execution_enabled": False,
        "docker_or_systemd_mutation_enabled": False,
        "network_mutation_enabled": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
