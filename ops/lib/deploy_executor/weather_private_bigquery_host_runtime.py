from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from .weather_private_bigquery_contract import CONTRACT_ID, FirstAccessScope, validate_first_access_scope
from .weather_private_bigquery_execution_bridge import (
    BRIDGE_OPERATION_ID,
    TARGET_ALIAS,
    AuthorizationConsumer,
    StageReceipt,
)
from .weather_private_bigquery_runtime_materialization import RuntimeArtifactReceipt, TARGET_PYTHON_ABI
from .weather_private_bigquery_trusted_backend import (
    ANALYTICS_HUB_LINK_SLOT_ID,
    APPLICATION_STAGE_ID,
    APPLICATION_STAGE_ROOT,
    FIRST_ACCESS_ENTRYPOINT,
    GOOGLE_AUTH_MECHANISM,
    GOOGLE_AUTH_SLOT_ID,
    GOOGLE_PROJECT_SLOT_ID,
    HOST_CAPABILITY_ID,
    CanonicalPrivateFacts,
    CanonicalWeatherNextPrivateRevalidator,
    TrustedCapabilitySet,
    TrustedPrivateHostEntrypoint,
    TrustedWeatherNextPrivateBackend,
)

IMPLEMENTATION_ISSUE = 552
INSTALL_OPERATION_ID = "rpi5.weathernext-private-backend.install.v1"
INSTALL_TARGET_ALIAS = "rpi5-weathernext-private-backend-install"
SOURCE_STATUS = "SOURCE_READY_HOST_INSTALL_GATE_REQUIRED"
RPI5_MAIN_REPOSITORY = "rozkalnsandris/RPi5_main"
RPI5_MAIN_REPOSITORY_ID = 1323383044
WEATHER_REPOSITORY = "rozkalnsandris/rozkalns_weather"
WEATHER_REPOSITORY_ID = 1359499204
TRUSTED_CHECKOUT = Path("/var/lib/rpi5-deploy/RPi5_main-weathernext-private-host-trusted")
OPERATOR_SOURCE = Path("ops/bin/rpi5-weathernext-private-host")
OPERATOR_DESTINATION = Path("/usr/local/sbin/rpi5-weathernext-private-host")
ACTIVATION_MARKER = Path("/var/lib/rpi5-deploy/weather-private-host/capability.json")
ROOT_UID = 0
ROOT_GID = 0
TRUSTED_CHECKOUT_MODE = 0o755
OPERATOR_MODE = 0o755
ACTIVATION_MARKER_MODE = 0o644
CONTRACT_SCHEMA = "rozkalns-weather.weathernext-private-host-runtime-source.v1"
INSTALL_PLAN_SCHEMA = "rozkalns-weather.weathernext-private-host-install-plan.v1"
ACTIVATION_MARKER_SCHEMA = "rozkalns-weather.weathernext-private-host-capability.v1"
INSTALL_MUTATION_BUDGET = (
    ("git.weathernext-private-host-checkout-fetch", 1),
    ("git.weathernext-private-host-checkout-worktree-add", 1),
    ("filesystem.weathernext-private-host-operator-install", 1),
    ("filesystem.weathernext-private-host-activation-marker-write", 1),
)
INSTALL_ROLLBACK_POLICY = "NONE"
_SANITIZED_BINDING_STATES = frozenset({"absent", "ready", "mismatch"})
_INSTALL_STATES = frozenset({"ABSENT", "EXACT", "CONFLICT"})


class WeatherNextPrivateHostRuntimeError(RuntimeError):
    """Fail-closed error for the source-only host runtime composition."""


@dataclass(frozen=True)
class OwnerAuthorizationEvidence:
    authorization_issue_number: int
    owner_authorized: bool
    operation_id: str
    contract_id: str
    target_alias: str
    rpi5_main_source_sha: str
    weather_source_sha: str


@dataclass(frozen=True)
class ExactSourceEvidence:
    repository: str
    repository_id: int
    source_sha: str
    current_main_sha: str
    merged_reachable: bool
    required_ci_success: bool


@dataclass(frozen=True)
class SanitizedHostEvidence:
    host_capability_installed: bool
    host_capability_source_sha: str | None
    application_staged: bool
    application_source_sha: str | None
    runtime_present: bool
    runtime_source_sha: str | None
    runtime_python_abi: str | None
    auth_binding_state: str
    project_binding_state: str
    linked_dataset_state: str
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
    mutation_budget: tuple[tuple[str, int], ...]
    rollback_policy: str = INSTALL_ROLLBACK_POLICY
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False


class OwnerAuthorizationEvidenceProvider(Protocol):
    def load_owner_authorization(self, authorization_issue_number: int) -> OwnerAuthorizationEvidence: ...


class ExactSourceEvidenceProvider(Protocol):
    def load_exact_source(self, repository: str, repository_id: int) -> ExactSourceEvidence: ...


class SanitizedHostEvidenceProvider(Protocol):
    def load_sanitized_host_evidence(self) -> SanitizedHostEvidence: ...


class PrivateRuntimeBindings(Protocol):
    """Runtime-only protected provider; private identifiers never cross this interface."""

    def stage_exact_weather_application(self, weather_source_sha: str) -> StageReceipt: ...
    def load_runtime_artifact_receipt(self, rpi5_main_source_sha: str) -> RuntimeArtifactReceipt: ...
    def bind_google_auth_slot(self) -> StageReceipt: ...
    def bind_google_project_slot(self) -> StageReceipt: ...
    def ensure_analytics_hub_link_slot(self) -> StageReceipt: ...
    def run_read_only_first_access(self, weather_source_sha: str, scope: FirstAccessScope) -> StageReceipt: ...


class ConcreteCanonicalPrivateFactsProvider:
    """Derive the merged #549 fact model from fixed canonical evidence providers."""

    def __init__(
        self,
        *,
        authorization: OwnerAuthorizationEvidenceProvider,
        sources: ExactSourceEvidenceProvider,
        host: SanitizedHostEvidenceProvider,
    ):
        self._authorization = authorization
        self._sources = sources
        self._host = host

    @staticmethod
    def _require_sha(value: str, name: str) -> str:
        if type(value) is not str or len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
            raise WeatherNextPrivateHostRuntimeError(f"{name} must be an exact Git SHA")
        return value

    @staticmethod
    def _require_source(
        evidence: ExactSourceEvidence,
        *,
        repository: str,
        repository_id: int,
        expected_sha: str,
    ) -> None:
        if evidence.repository != repository or evidence.repository_id != repository_id:
            raise WeatherNextPrivateHostRuntimeError("canonical source repository identity drifted")
        if evidence.source_sha != expected_sha or evidence.current_main_sha != expected_sha:
            raise WeatherNextPrivateHostRuntimeError("canonical source SHA drifted from owner authorization")
        if evidence.merged_reachable is not True or evidence.required_ci_success is not True:
            raise WeatherNextPrivateHostRuntimeError("canonical source reachability or required CI failed")

    @staticmethod
    def _require_host_state(host: SanitizedHostEvidence) -> None:
        for name, state in (
            ("google auth", host.auth_binding_state),
            ("google project", host.project_binding_state),
            ("Analytics Hub link", host.linked_dataset_state),
        ):
            if state not in _SANITIZED_BINDING_STATES:
                raise WeatherNextPrivateHostRuntimeError(f"{name} state is invalid")
            if state == "mismatch":
                raise WeatherNextPrivateHostRuntimeError(f"{name} state is mismatched")
        if host.runtime_present and host.runtime_python_abi != TARGET_PYTHON_ABI:
            raise WeatherNextPrivateHostRuntimeError("installed WeatherNext runtime is not reviewed cp313")
        if not host.runtime_present and host.runtime_python_abi is not None:
            raise WeatherNextPrivateHostRuntimeError("system Python cannot substitute for absent cp313 runtime")

    def load_private_facts(self, authorization_issue_number: int) -> CanonicalPrivateFacts:
        if type(authorization_issue_number) is not int or not 1 <= authorization_issue_number <= 2_147_483_647:
            raise WeatherNextPrivateHostRuntimeError("authorization issue number is invalid")
        try:
            auth = self._authorization.load_owner_authorization(authorization_issue_number)
            if auth.authorization_issue_number != authorization_issue_number:
                raise WeatherNextPrivateHostRuntimeError("owner authorization issue identity drifted")
            if auth.owner_authorized is not True:
                raise WeatherNextPrivateHostRuntimeError("owner authorization is not active")
            if auth.operation_id != BRIDGE_OPERATION_ID or auth.contract_id != CONTRACT_ID:
                raise WeatherNextPrivateHostRuntimeError("owner authorization private operation or contract drifted")
            if auth.target_alias != TARGET_ALIAS:
                raise WeatherNextPrivateHostRuntimeError("owner authorization target must remain rpi5")
            rpi_sha = self._require_sha(auth.rpi5_main_source_sha, "RPi5_main SHA")
            weather_sha = self._require_sha(auth.weather_source_sha, "Weather SHA")
            rpi = self._sources.load_exact_source(RPI5_MAIN_REPOSITORY, RPI5_MAIN_REPOSITORY_ID)
            weather = self._sources.load_exact_source(WEATHER_REPOSITORY, WEATHER_REPOSITORY_ID)
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
            if host.host_capability_installed and host.host_capability_source_sha != rpi_sha:
                raise WeatherNextPrivateHostRuntimeError("installed host capability source SHA drifted")
            if host.application_staged and host.application_source_sha != weather_sha:
                raise WeatherNextPrivateHostRuntimeError("staged Weather source SHA drifted")
            if host.runtime_present and host.runtime_source_sha != rpi_sha:
                raise WeatherNextPrivateHostRuntimeError("private runtime source SHA drifted")
        except WeatherNextPrivateHostRuntimeError:
            raise
        except Exception:
            raise WeatherNextPrivateHostRuntimeError("canonical WeatherNext private facts failed closed") from None
        return CanonicalPrivateFacts(
            authorization_issue_number=authorization_issue_number,
            owner_authorized=True,
            authorization_operation_id=BRIDGE_OPERATION_ID,
            authorization_contract_id=CONTRACT_ID,
            rpi5_main_source_sha=rpi_sha,
            rpi5_main_ci_success=True,
            weather_source_sha=weather_sha,
            weather_ci_success=True,
            target_alias=TARGET_ALIAS,
            host_capability_installed=host.host_capability_installed,
            application_staged=host.application_staged,
            runtime_present=host.runtime_present,
            runtime_python_abi=host.runtime_python_abi,
            auth_binding_state=host.auth_binding_state,
            project_binding_state=host.project_binding_state,
            linked_dataset_state=host.linked_dataset_state,
            read_only_first_access_authorized=host.read_only_first_access_authorized,
            read_only_first_access_executed=host.read_only_first_access_executed,
        )


class FixedApplicationStager:
    def __init__(self, bindings: PrivateRuntimeBindings):
        self._bindings = bindings

    def stage_exact_weather_source(
        self, *, weather_source_sha: str, stage_id: str, stage_root: str
    ) -> StageReceipt:
        if stage_id != APPLICATION_STAGE_ID or stage_root != APPLICATION_STAGE_ROOT:
            raise WeatherNextPrivateHostRuntimeError("Weather application staging identity drifted")
        return self._bindings.stage_exact_weather_application(weather_source_sha)


class FixedRuntimeReceiptProvider:
    def __init__(self, bindings: PrivateRuntimeBindings):
        self._bindings = bindings

    def load_runtime_artifact_receipt(self, rpi5_main_source_sha: str) -> RuntimeArtifactReceipt:
        return self._bindings.load_runtime_artifact_receipt(rpi5_main_source_sha)


class FixedGoogleAuthBinder:
    def __init__(self, bindings: PrivateRuntimeBindings):
        self._bindings = bindings

    def bind_fixed_auth_slot(self, *, slot_id: str, mechanism: str) -> StageReceipt:
        if slot_id != GOOGLE_AUTH_SLOT_ID or mechanism != GOOGLE_AUTH_MECHANISM:
            raise WeatherNextPrivateHostRuntimeError("Google auth binding slot drifted")
        return self._bindings.bind_google_auth_slot()


class FixedGoogleProjectBinder:
    def __init__(self, bindings: PrivateRuntimeBindings):
        self._bindings = bindings

    def bind_fixed_project_slot(self, *, slot_id: str) -> StageReceipt:
        if slot_id != GOOGLE_PROJECT_SLOT_ID:
            raise WeatherNextPrivateHostRuntimeError("Google project binding slot drifted")
        return self._bindings.bind_google_project_slot()


class FixedAnalyticsHubLinkBinder:
    def __init__(self, bindings: PrivateRuntimeBindings):
        self._bindings = bindings

    def ensure_fixed_link_slot(self, *, slot_id: str) -> StageReceipt:
        if slot_id != ANALYTICS_HUB_LINK_SLOT_ID:
            raise WeatherNextPrivateHostRuntimeError("Analytics Hub linked-dataset slot drifted")
        return self._bindings.ensure_analytics_hub_link_slot()


class FixedFirstAccessRunner:
    def __init__(self, bindings: PrivateRuntimeBindings):
        self._bindings = bindings

    def run_fixed_first_access(
        self, *, weather_source_sha: str, entrypoint: str, scope: FirstAccessScope
    ) -> StageReceipt:
        if entrypoint != FIRST_ACCESS_ENTRYPOINT:
            raise WeatherNextPrivateHostRuntimeError("WeatherNext first-access entrypoint drifted")
        validate_first_access_scope(scope)
        return self._bindings.run_read_only_first_access(weather_source_sha, scope)


def build_trusted_capabilities(bindings: PrivateRuntimeBindings) -> TrustedCapabilitySet:
    return TrustedCapabilitySet(
        application_stager=FixedApplicationStager(bindings),
        runtime_receipts=FixedRuntimeReceiptProvider(bindings),
        google_auth=FixedGoogleAuthBinder(bindings),
        google_project=FixedGoogleProjectBinder(bindings),
        analytics_hub=FixedAnalyticsHubLinkBinder(bindings),
        first_access=FixedFirstAccessRunner(bindings),
    )


class WeatherNextPrivateHostRuntimeComposition:
    """One fixed private composition; conversational caller controls only issue identity."""

    def __init__(
        self,
        *,
        facts: ConcreteCanonicalPrivateFactsProvider,
        authorization_consumer: AuthorizationConsumer,
        bindings: PrivateRuntimeBindings,
    ):
        if type(facts) is not ConcreteCanonicalPrivateFactsProvider:
            raise TypeError("runtime composition requires concrete WeatherNext facts provider")
        self._entrypoint = TrustedPrivateHostEntrypoint(
            canonical_revalidator=CanonicalWeatherNextPrivateRevalidator(facts),
            authorization_consumer=authorization_consumer,
            backend=TrustedWeatherNextPrivateBackend(build_trusted_capabilities(bindings)),
        )

    def execute(self, authorization_issue_number: int) -> Mapping[str, Any]:
        if type(authorization_issue_number) is not int or authorization_issue_number <= 0:
            raise WeatherNextPrivateHostRuntimeError("authorization issue number is invalid")
        try:
            return self._entrypoint.dispatch(authorization_issue_number)
        except Exception:
            raise WeatherNextPrivateHostRuntimeError("WeatherNext private host execution failed closed") from None


def build_runtime_composition(
    *,
    authorization: OwnerAuthorizationEvidenceProvider,
    sources: ExactSourceEvidenceProvider,
    host: SanitizedHostEvidenceProvider,
    authorization_consumer: AuthorizationConsumer,
    bindings: PrivateRuntimeBindings,
) -> WeatherNextPrivateHostRuntimeComposition:
    """Fixed capability factory; dependencies are trusted-host supplied, never caller selectors."""
    facts = ConcreteCanonicalPrivateFactsProvider(
        authorization=authorization,
        sources=sources,
        host=host,
    )
    return WeatherNextPrivateHostRuntimeComposition(
        facts=facts,
        authorization_consumer=authorization_consumer,
        bindings=bindings,
    )


def _install_state(value: str, name: str) -> str:
    if value not in _INSTALL_STATES:
        raise WeatherNextPrivateHostRuntimeError(f"{name} is invalid")
    if value == "CONFLICT":
        raise WeatherNextPrivateHostRuntimeError(f"{name} conflicts with reviewed install state")
    return value


def build_host_install_plan(
    observation: HostInstallObservation,
    *,
    exact_rpi5_main_sha: str,
) -> HostInstallPlan:
    if type(exact_rpi5_main_sha) is not str or len(exact_rpi5_main_sha) != 40 or any(
        c not in "0123456789abcdef" for c in exact_rpi5_main_sha
    ):
        raise WeatherNextPrivateHostRuntimeError("host install requires exact RPi5_main SHA")
    checkout = _install_state(observation.trusted_checkout_state, "trusted checkout state")
    operator = _install_state(observation.operator_state, "operator state")
    marker = _install_state(observation.activation_marker_state, "activation marker state")
    mutations: list[str] = []
    if checkout == "ABSENT":
        mutations.extend(
            (
                "git.weathernext-private-host-checkout-fetch",
                "git.weathernext-private-host-checkout-worktree-add",
            )
        )
    if operator == "ABSENT":
        mutations.append("filesystem.weathernext-private-host-operator-install")
    if marker == "ABSENT":
        mutations.append("filesystem.weathernext-private-host-activation-marker-write")
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


def validate_activation_marker(value: Mapping[str, Any], *, exact_rpi5_main_sha: str) -> None:
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
        raise WeatherNextPrivateHostRuntimeError("activation marker identity drifted")


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
        "caller_authority": ("authorization_issue_number",),
        "trusted_checkout": str(TRUSTED_CHECKOUT),
        "operator_destination": str(OPERATOR_DESTINATION),
        "activation_marker": str(ACTIVATION_MARKER),
        "trusted_checkout_mode": TRUSTED_CHECKOUT_MODE,
        "operator_mode": OPERATOR_MODE,
        "activation_marker_mode": ACTIVATION_MARKER_MODE,
        "owner_uid": ROOT_UID,
        "owner_gid": ROOT_GID,
        "install_mutation_budget": INSTALL_MUTATION_BUDGET,
        "rollback_policy": INSTALL_ROLLBACK_POLICY,
        "host_capability_installed": False,
        "runtime_activation_enabled": False,
        "global_executor_execution_enabled": False,
        "google_control_plane_execution_enabled": False,
        "read_only_bigquery_execution_enabled": False,
        "sqlite_write_execution_enabled": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }


def source_contract_json() -> str:
    return json.dumps(dict(source_readiness()), sort_keys=True, separators=(",", ":"))
