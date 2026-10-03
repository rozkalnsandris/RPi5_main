from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from .weather_private_gcs_contract import (
    CONTRACT_ID,
    GCSFirstAccessScope,
    READ_ONLY_PRIVATE_GCS,
    WEATHER_ENTRYPOINT,
)
from .weather_private_gcs_execution_bridge import (
    BRIDGE_OPERATION_ID,
    GCSAuthorizationConsumer,
    GCSStageReceipt,
    TARGET_ALIAS,
)
from .weather_private_gcs_runtime_materialization import (
    TARGET_PIP_PLATFORM,
    TARGET_PYTHON_ABI,
)
from .weather_private_gcs_trusted_backend import (
    APPLICATION_STAGE_ID,
    APPLICATION_STAGE_ROOT,
    GOOGLE_AUTH_MECHANISM,
    GOOGLE_AUTH_SLOT_ID,
    CanonicalGCSFacts,
    CanonicalWeatherNextGCSRevalidator,
    TrustedGCSCapabilitySet,
    TrustedGCSHostEntrypoint,
    TrustedWeatherNextGCSBackend,
    WeatherNextPrivateGCSTrustedBackendError,
)

IMPLEMENTATION_ISSUE = 835
HOST_CAPABILITY_ID = "rpi5.weathernext-private-gcs-backend.v1"
INSTALL_OPERATION_ID = "rpi5.weathernext-private-gcs-backend.install.v1"
INSTALL_TARGET_ALIAS = "rpi5-weathernext-private-gcs-backend-install"
SOURCE_STATUS = "SOURCE_READY_GCS_PREREQUISITE_LIVE_GATE"
RPI5_MAIN_REPOSITORY = "rozkalnsandris/RPi5_main"
RPI5_MAIN_REPOSITORY_ID = 1323383044
WEATHER_REPOSITORY = "rozkalnsandris/rozkalns_weather"
WEATHER_REPOSITORY_ID = 1359499204
TRUSTED_CHECKOUT = Path(
    "/var/lib/rpi5-deploy/RPi5_main-weathernext-private-gcs-host-trusted"
)
OPERATOR_SOURCE = Path("ops/bin/rpi5-weathernext-private-gcs-host")
OPERATOR_DESTINATION = Path("/usr/local/sbin/rpi5-weathernext-private-gcs-host")
ACTIVATION_MARKER = Path(
    "/var/lib/rpi5-deploy/weather-private-gcs-host/capability.json"
)
ROOT_UID = 0
ROOT_GID = 0
TRUSTED_CHECKOUT_MODE = 0o755
OPERATOR_MODE = 0o755
ACTIVATION_MARKER_MODE = 0o644
CONTRACT_SCHEMA = "rozkalns-weather.weathernext-private-gcs-host-runtime-source.v1"
INSTALL_PLAN_SCHEMA = (
    "rozkalns-weather.weathernext-private-gcs-host-install-plan.v1"
)
ACTIVATION_MARKER_SCHEMA = (
    "rozkalns-weather.weathernext-private-gcs-host-capability.v1"
)
EXPECTED_GCS_RUNTIME_CLOSURE_SHA256 = (
    "4ef3d22c8ebc76901c3840d0304124ab390afaf3978883a4ad377a6da4991148"
)
INSTALL_MUTATION_BUDGET = (
    {
        "category": "git.weathernext-private-gcs-host-checkout-fetch",
        "max_operations": 1,
    },
    {
        "category": "git.weathernext-private-gcs-host-checkout-worktree-add",
        "max_operations": 1,
    },
    {
        "category": "filesystem.weathernext-private-gcs-host-operator-install",
        "max_operations": 1,
    },
    {
        "category": "filesystem.weathernext-private-gcs-host-activation-marker-write",
        "max_operations": 1,
    },
)
INSTALL_ROLLBACK_POLICY = "NONE"
_INSTALL_STATES = frozenset({"ABSENT", "EXACT", "CONFLICT"})


class WeatherNextPrivateGCSHostRuntimeError(
    WeatherNextPrivateGCSTrustedBackendError
):
    pass


@dataclass(frozen=True)
class OwnerAuthorizationEvidence:
    authorization_issue_number: int
    owner_authorized: bool
    operation_id: str
    contract_id: str
    target_alias: str
    rpi5_main_source_sha: str
    weather_source_sha: str
    selected_init_utc: datetime


@dataclass(frozen=True)
class ExactSourceEvidence:
    repository: str
    repository_id: int
    source_sha: str
    current_main_sha: str
    merged_reachable: bool
    required_ci_success: bool


@dataclass(frozen=True)
class SanitizedGCSHostEvidence:
    host_capability_installed: bool
    host_capability_source_sha: str | None
    application_staged: bool
    application_source_sha: str | None
    runtime_present: bool
    runtime_source_sha: str | None
    runtime_closure_sha256: str | None
    runtime_python_abi: str | None
    runtime_target_platform: str | None
    host_glibc_compatible: bool
    auth_binding_state: str
    read_only_first_access_authorized: bool = False
    read_only_first_access_executed: bool = False


@dataclass(frozen=True)
class HostInstallObservation:
    trusted_checkout_state: str
    operator_state: str
    activation_marker_state: str


@dataclass(frozen=True)
class HostInstallPlan:
    schema: str
    decision: str
    operation_id: str
    target_alias: str
    exact_rpi5_main_sha: str
    trusted_checkout: str
    operator_destination: str
    activation_marker: str
    trusted_checkout_mode: int
    operator_mode: int
    activation_marker_mode: int
    owner_uid: int
    owner_gid: int
    mutations_required: tuple[str, ...]
    mutation_budget: tuple[Mapping[str, Any], ...]


class OwnerAuthorizationEvidenceProvider(Protocol):
    def load_owner_authorization(
        self, authorization_issue_number: int
    ) -> OwnerAuthorizationEvidence: ...


class ExactSourceEvidenceProvider(Protocol):
    def load_exact_source(
        self, repository: str, repository_id: int
    ) -> ExactSourceEvidence: ...


class SanitizedGCSHostEvidenceProvider(Protocol):
    def load_sanitized_host_evidence(self) -> SanitizedGCSHostEvidence: ...


class PrivateGCSRuntimeBindings(Protocol):
    def stage_exact_weather_application(
        self, weather_source_sha: str
    ) -> GCSStageReceipt: ...

    def materialize_exact_gcs_runtime(
        self, rpi5_main_source_sha: str
    ) -> GCSStageReceipt: ...

    def bind_google_auth_slot(self) -> GCSStageReceipt: ...

    def run_read_only_first_access(
        self,
        weather_source_sha: str,
        scope: GCSFirstAccessScope,
    ) -> GCSStageReceipt: ...


class ConcreteCanonicalGCSFactsProvider:
    def __init__(
        self,
        *,
        authorization: OwnerAuthorizationEvidenceProvider,
        sources: ExactSourceEvidenceProvider,
        host: SanitizedGCSHostEvidenceProvider,
    ):
        self._authorization = authorization
        self._sources = sources
        self._host = host

    @staticmethod
    def _require_sha(value: str, name: str) -> str:
        if (
            type(value) is not str
            or len(value) != 40
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise WeatherNextPrivateGCSHostRuntimeError(f"{name} must be exact")
        return value

    @staticmethod
    def _require_source(
        evidence: ExactSourceEvidence,
        *,
        repository: str,
        repository_id: int,
        expected_sha: str,
    ) -> None:
        if (
            evidence.repository != repository
            or evidence.repository_id != repository_id
            or evidence.source_sha != expected_sha
            or evidence.current_main_sha != expected_sha
            or evidence.merged_reachable is not True
            or evidence.required_ci_success is not True
        ):
            raise WeatherNextPrivateGCSHostRuntimeError(
                "canonical source SHA or CI drifted from owner authorization"
            )

    @staticmethod
    def _require_host_state(host: SanitizedGCSHostEvidence) -> None:
        if host.auth_binding_state not in {"absent", "ready", "mismatch"}:
            raise WeatherNextPrivateGCSHostRuntimeError(
                "GCS auth binding state invalid"
            )
        if host.auth_binding_state == "mismatch":
            raise WeatherNextPrivateGCSHostRuntimeError(
                "GCS auth binding mismatch"
            )
        if host.host_capability_installed:
            if host.host_capability_source_sha is None:
                raise WeatherNextPrivateGCSHostRuntimeError(
                    "GCS host capability source SHA missing"
                )
        elif host.host_capability_source_sha is not None:
            raise WeatherNextPrivateGCSHostRuntimeError(
                "absent GCS host capability cannot expose source SHA"
            )
        if host.application_staged:
            if host.application_source_sha is None:
                raise WeatherNextPrivateGCSHostRuntimeError(
                    "Weather application source SHA missing"
                )
        elif host.application_source_sha is not None:
            raise WeatherNextPrivateGCSHostRuntimeError(
                "absent Weather application cannot expose source SHA"
            )
        runtime_fields = (
            host.runtime_source_sha,
            host.runtime_closure_sha256,
            host.runtime_python_abi,
            host.runtime_target_platform,
        )
        if host.runtime_present:
            if (
                host.runtime_source_sha is None
                or host.runtime_closure_sha256
                != EXPECTED_GCS_RUNTIME_CLOSURE_SHA256
                or host.runtime_python_abi != TARGET_PYTHON_ABI
                or host.runtime_target_platform != TARGET_PIP_PLATFORM
            ):
                raise WeatherNextPrivateGCSHostRuntimeError(
                    "installed GCS runtime identity drifted"
                )
        elif any(value is not None for value in runtime_fields):
            raise WeatherNextPrivateGCSHostRuntimeError(
                "absent GCS runtime cannot expose runtime identity"
            )
        if host.host_glibc_compatible is not True:
            raise WeatherNextPrivateGCSHostRuntimeError(
                "host glibc is incompatible with reviewed GCS runtime floor"
            )

    def load_gcs_facts(self, authorization_issue_number: int) -> CanonicalGCSFacts:
        if (
            type(authorization_issue_number) is not int
            or not 1 <= authorization_issue_number <= 2_147_483_647
        ):
            raise WeatherNextPrivateGCSHostRuntimeError(
                "authorization issue number is invalid"
            )
        auth = self._authorization.load_owner_authorization(
            authorization_issue_number
        )
        if (
            auth.authorization_issue_number != authorization_issue_number
            or auth.owner_authorized is not True
            or auth.operation_id != BRIDGE_OPERATION_ID
            or auth.contract_id != CONTRACT_ID
            or auth.target_alias != TARGET_ALIAS
        ):
            raise WeatherNextPrivateGCSHostRuntimeError(
                "owner authorization GCS identity drifted"
            )
        rpi_sha = self._require_sha(
            auth.rpi5_main_source_sha, "RPi5_main SHA"
        )
        weather_sha = self._require_sha(auth.weather_source_sha, "Weather SHA")
        rpi = self._sources.load_exact_source(
            RPI5_MAIN_REPOSITORY, RPI5_MAIN_REPOSITORY_ID
        )
        weather = self._sources.load_exact_source(
            WEATHER_REPOSITORY, WEATHER_REPOSITORY_ID
        )
        self._require_source(
            rpi,
            repository=RPI5_MAIN_REPOSITORY,
            repository_id=RPI5_MAIN_REPOSITORY_ID,
            expected_sha=rpi_sha,
        )
        self._require_source(
            weather,
            repository=WEATHER_REPOSITORY,
            repository_id=WEATHER_REPOSITORY_ID,
            expected_sha=weather_sha,
        )
        host = self._host.load_sanitized_host_evidence()
        self._require_host_state(host)
        if (
            host.host_capability_installed
            and host.host_capability_source_sha != rpi_sha
        ):
            raise WeatherNextPrivateGCSHostRuntimeError(
                "installed GCS host capability source SHA drifted"
            )
        if (
            host.application_staged
            and host.application_source_sha != weather_sha
        ):
            raise WeatherNextPrivateGCSHostRuntimeError(
                "staged Weather source SHA drifted"
            )
        if host.runtime_present and host.runtime_source_sha != rpi_sha:
            raise WeatherNextPrivateGCSHostRuntimeError(
                "installed GCS runtime source SHA drifted"
            )
        return CanonicalGCSFacts(
            authorization_issue_number=authorization_issue_number,
            owner_authorized=True,
            authorization_operation_id=BRIDGE_OPERATION_ID,
            authorization_contract_id=CONTRACT_ID,
            rpi5_main_source_sha=rpi_sha,
            rpi5_main_ci_success=True,
            weather_source_sha=weather_sha,
            weather_ci_success=True,
            selected_init_utc=auth.selected_init_utc,
            target_alias=TARGET_ALIAS,
            application_staged=host.application_staged,
            gcs_runtime_present=host.runtime_present,
            auth_binding_state=host.auth_binding_state,
            host_capability_installed=host.host_capability_installed,
            read_only_first_access_authorized=(
                host.read_only_first_access_authorized
            ),
            read_only_first_access_executed=(
                host.read_only_first_access_executed
            ),
        )


class FixedApplicationStager:
    def __init__(self, bindings: PrivateGCSRuntimeBindings):
        self._bindings = bindings

    def stage_exact_weather_source(
        self, *, weather_source_sha: str, stage_id: str, stage_root: str
    ) -> GCSStageReceipt:
        if (
            stage_id != APPLICATION_STAGE_ID
            or stage_root != APPLICATION_STAGE_ROOT
        ):
            raise WeatherNextPrivateGCSHostRuntimeError(
                "Weather application staging identity drifted"
            )
        return self._bindings.stage_exact_weather_application(weather_source_sha)


class FixedRuntimeMaterializer:
    def __init__(self, bindings: PrivateGCSRuntimeBindings):
        self._bindings = bindings

    def materialize_exact_gcs_runtime(
        self, *, rpi5_main_source_sha: str
    ) -> GCSStageReceipt:
        return self._bindings.materialize_exact_gcs_runtime(
            rpi5_main_source_sha
        )


class FixedGoogleAuthBinder:
    def __init__(self, bindings: PrivateGCSRuntimeBindings):
        self._bindings = bindings

    def bind_fixed_auth_slot(
        self, *, slot_id: str, mechanism: str
    ) -> GCSStageReceipt:
        if slot_id != GOOGLE_AUTH_SLOT_ID or mechanism != GOOGLE_AUTH_MECHANISM:
            raise WeatherNextPrivateGCSHostRuntimeError(
                "WeatherNext GCS auth binding identity drifted"
            )
        return self._bindings.bind_google_auth_slot()


class FixedFirstAccessRunner:
    def __init__(self, bindings: PrivateGCSRuntimeBindings):
        self._bindings = bindings

    def run_fixed_gcs_first_access(
        self,
        *,
        weather_source_sha: str,
        entrypoint: str,
        scope: GCSFirstAccessScope,
    ) -> GCSStageReceipt:
        if entrypoint != WEATHER_ENTRYPOINT:
            raise WeatherNextPrivateGCSHostRuntimeError(
                "WeatherNext GCS first-access entrypoint drifted"
            )
        return self._bindings.run_read_only_first_access(
            weather_source_sha, scope
        )


def build_trusted_capabilities(
    bindings: PrivateGCSRuntimeBindings,
) -> TrustedGCSCapabilitySet:
    return TrustedGCSCapabilitySet(
        application_stager=FixedApplicationStager(bindings),
        runtime_materializer=FixedRuntimeMaterializer(bindings),
        google_auth=FixedGoogleAuthBinder(bindings),
        first_access=FixedFirstAccessRunner(bindings),
    )


class WeatherNextPrivateGCSHostRuntimeComposition:
    def __init__(
        self,
        *,
        facts: ConcreteCanonicalGCSFactsProvider,
        authorization_consumer: GCSAuthorizationConsumer,
        bindings: PrivateGCSRuntimeBindings,
    ):
        if type(facts) is not ConcreteCanonicalGCSFactsProvider:
            raise TypeError(
                "GCS runtime composition requires concrete facts provider"
            )
        self._entrypoint = TrustedGCSHostEntrypoint(
            canonical_revalidator=CanonicalWeatherNextGCSRevalidator(facts),
            authorization_consumer=authorization_consumer,
            backend=TrustedWeatherNextGCSBackend(
                build_trusted_capabilities(bindings)
            ),
        )

    def execute(self, authorization_issue_number: int) -> Mapping[str, Any]:
        if (
            type(authorization_issue_number) is not int
            or authorization_issue_number <= 0
        ):
            raise WeatherNextPrivateGCSHostRuntimeError(
                "authorization issue number is invalid"
            )
        return self._entrypoint.dispatch(authorization_issue_number)


def build_runtime_composition(
    *,
    authorization: OwnerAuthorizationEvidenceProvider,
    sources: ExactSourceEvidenceProvider,
    host: SanitizedGCSHostEvidenceProvider,
    authorization_consumer: GCSAuthorizationConsumer,
    bindings: PrivateGCSRuntimeBindings,
) -> WeatherNextPrivateGCSHostRuntimeComposition:
    return WeatherNextPrivateGCSHostRuntimeComposition(
        facts=ConcreteCanonicalGCSFactsProvider(
            authorization=authorization,
            sources=sources,
            host=host,
        ),
        authorization_consumer=authorization_consumer,
        bindings=bindings,
    )


def _install_state(value: str, name: str) -> str:
    if value not in _INSTALL_STATES:
        raise WeatherNextPrivateGCSHostRuntimeError(f"{name} is invalid")
    if value == "CONFLICT":
        raise WeatherNextPrivateGCSHostRuntimeError(
            f"{name} conflicts with reviewed install state"
        )
    return value


def build_host_install_plan(
    observation: HostInstallObservation,
    *,
    exact_rpi5_main_sha: str,
) -> HostInstallPlan:
    if (
        type(exact_rpi5_main_sha) is not str
        or len(exact_rpi5_main_sha) != 40
        or any(
            char not in "0123456789abcdef"
            for char in exact_rpi5_main_sha
        )
    ):
        raise WeatherNextPrivateGCSHostRuntimeError(
            "GCS host install requires exact RPi5_main SHA"
        )
    checkout = _install_state(
        observation.trusted_checkout_state, "trusted checkout state"
    )
    operator = _install_state(observation.operator_state, "operator state")
    marker = _install_state(
        observation.activation_marker_state, "activation marker state"
    )
    mutations: list[str] = []
    if checkout == "ABSENT":
        mutations.extend(
            (
                "git.weathernext-private-gcs-host-checkout-fetch",
                "git.weathernext-private-gcs-host-checkout-worktree-add",
            )
        )
    if operator == "ABSENT":
        mutations.append(
            "filesystem.weathernext-private-gcs-host-operator-install"
        )
    if marker == "ABSENT":
        mutations.append(
            "filesystem.weathernext-private-gcs-host-activation-marker-write"
        )
    return HostInstallPlan(
        schema=INSTALL_PLAN_SCHEMA,
        decision="ALREADY_EXACT" if not mutations else "INSTALL_REQUIRED",
        operation_id=INSTALL_OPERATION_ID,
        target_alias=INSTALL_TARGET_ALIAS,
        exact_rpi5_main_sha=exact_rpi5_main_sha,
        trusted_checkout=str(TRUSTED_CHECKOUT),
        operator_destination=str(OPERATOR_DESTINATION),
        activation_marker=str(ACTIVATION_MARKER),
        trusted_checkout_mode=TRUSTED_CHECKOUT_MODE,
        operator_mode=OPERATOR_MODE,
        activation_marker_mode=ACTIVATION_MARKER_MODE,
        owner_uid=ROOT_UID,
        owner_gid=ROOT_GID,
        mutations_required=tuple(mutations),
        mutation_budget=INSTALL_MUTATION_BUDGET,
    )


def validate_activation_marker(
    value: Mapping[str, Any], *, exact_rpi5_main_sha: str
) -> None:
    expected = {
        "schema": ACTIVATION_MARKER_SCHEMA,
        "host_capability_id": HOST_CAPABILITY_ID,
        "operation_id": INSTALL_OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "rpi5_main_source_sha": exact_rpi5_main_sha,
        "trusted_checkout": str(TRUSTED_CHECKOUT),
        "operator_destination": str(OPERATOR_DESTINATION),
        "execution_enabled": True,
    }
    if dict(value) != expected:
        raise WeatherNextPrivateGCSHostRuntimeError(
            "GCS activation marker identity drifted"
        )


def source_readiness() -> Mapping[str, Any]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "schema": CONTRACT_SCHEMA,
        "host_capability_id": HOST_CAPABILITY_ID,
        "install_operation_id": INSTALL_OPERATION_ID,
        "install_target_alias": INSTALL_TARGET_ALIAS,
        "source_status": SOURCE_STATUS,
        "concrete_canonical_facts_provider_implemented": True,
        "fixed_adapter_composition_implemented": True,
        "runtime_composition_implemented": True,
        "source_tree_one_shot_operator_implemented": True,
        "sanitized_host_evidence_implemented": True,
        "gcs_prerequisite_rollout_source_implemented": True,
        "next_gate": "COMPOSITE_STRICT_LIVE_GCS_PREREQUISITE_ROLLOUT",
        "caller_authority": ("authorization_issue_number",),
        "trusted_checkout": str(TRUSTED_CHECKOUT),
        "operator_destination": str(OPERATOR_DESTINATION),
        "activation_marker": str(ACTIVATION_MARKER),
        "expected_runtime_closure_sha256": (
            EXPECTED_GCS_RUNTIME_CLOSURE_SHA256
        ),
        "target_python_abi": TARGET_PYTHON_ABI,
        "target_platform": TARGET_PIP_PLATFORM,
        "host_capability_installed": False,
        "runtime_activation_enabled": False,
        "global_executor_execution_enabled": False,
        "credential_binding_execution_enabled": False,
        "read_only_gcs_execution_enabled": False,
        "project_binding_execution_enabled": False,
        "analytics_hub_execution_enabled": False,
        "bigquery_execution_enabled": False,
        "sqlite_write_execution_enabled": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }


def source_contract_json() -> str:
    return json.dumps(
        dict(source_readiness()),
        sort_keys=True,
        separators=(",", ":"),
    )
