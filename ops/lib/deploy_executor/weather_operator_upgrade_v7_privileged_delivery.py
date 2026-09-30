from __future__ import annotations

from dataclasses import dataclass, fields
import re
from typing import Any, Mapping, Protocol

from .dispatch_contract import DispatchRequest, parse_dispatch_request

ISSUE = 543
OPERATION_ID = "rpi5-main.weather-operator-upgrade-v7.v1"
ADAPTER_ID = OPERATION_ID
SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
TARGET_ALIAS = "rpi5-main-weather-operator-upgrade-v7"
ENTRYPOINT = "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v7"
TARGET_PATH = "/usr/local/sbin/rozkalns-weather-public-runtime-operator"
TRUSTED_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v7-trusted"
PRESERVED_V6_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v6-trusted"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
OLD_SHA256 = "4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f"
NEW_SHA256 = "f6255bf1e80d2918555b0814b0690add739041ac11512297d904fce5e8fc0cf1"
AUTHORIZATION_CLASS = "STRICT"
ROLLBACK_POLICY = "NONE"
MUTATION_BUDGET = (
    ("git.weather-operator-upgrade-v7-checkout-fetch", 1),
    ("git.weather-operator-upgrade-v7-checkout-worktree-add", 1),
    ("filesystem.weather-operator-upgrade-v7-atomic-replace", 1),
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class WeatherOperatorV7DeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalWeatherV7Evidence:
    authorization_issue_number: int
    request_id: str
    source_repository: str
    source_sha: str
    current_main_sha: str
    operation_id: str
    adapter_id: str
    target_alias: str
    authorization_class: str
    rollback_policy: str
    mutation_budget: tuple[tuple[str, int], ...]
    owner_verified: bool
    authorization_ttl_valid: bool
    authorization_body_unchanged: bool
    replay_available: bool
    queue_ready: bool
    queue_binding_valid: bool
    source_reachable_from_main: bool
    source_ci_success: bool
    registry_execution_enabled: bool
    p8_mutation_dispatch_enabled: bool


@dataclass(frozen=True)
class SanitizedWeatherV7HostEvidence:
    evidence_id: str
    host_capability_installed: bool
    trusted_checkout_name: str
    trusted_checkout_state: str
    trusted_checkout_origin: str
    trusted_checkout_source_sha: str
    v6_checkout_preserved: bool
    predecessor_sha256: str
    predecessor_owner_uid: int
    predecessor_owner_gid: int
    predecessor_mode: str
    target_source_sha256: str
    protected_values_included: bool


@dataclass(frozen=True)
class WeatherV7PrivilegedDeliveryPlan:
    result: str
    authorization_issue_number: int
    request_id: str
    source_sha: str
    operation_id: str = OPERATION_ID
    target_alias: str = TARGET_ALIAS
    entrypoint: str = ENTRYPOINT
    target_path: str = TARGET_PATH
    trusted_checkout_name: str = TRUSTED_CHECKOUT_NAME
    preserved_v6_checkout_name: str = PRESERVED_V6_CHECKOUT_NAME
    mutation_budget: tuple[tuple[str, int], ...] = MUTATION_BUDGET
    rollback_policy: str = ROLLBACK_POLICY
    privileged_dispatch_implemented: bool = True
    privileged_dispatch_enabled: bool = False
    host_capability_installed: bool = False
    global_executor_execution_enabled: bool = False
    source_merge_authorizes_live: bool = False
    production_mutation_started: bool = False


class CanonicalWeatherV7Revalidator(Protocol):
    def revalidate(self, authorization_issue_number: int) -> CanonicalWeatherV7Evidence: ...


class SanitizedWeatherV7HostEvidenceResolver(Protocol):
    def resolve(self, *, source_sha: str) -> Mapping[str, Any]: ...


def _fail(message: str) -> None:
    raise WeatherOperatorV7DeliveryError(message)


def _require_bool(value: Any, expected: bool, where: str) -> None:
    if type(value) is not bool or value is not expected:
        _fail(f"{where} must be {str(expected).lower()}")


def _validate_canonical(request: DispatchRequest, evidence: CanonicalWeatherV7Evidence) -> None:
    if not isinstance(evidence, CanonicalWeatherV7Evidence):
        _fail("canonical revalidator returned unsupported evidence")
    if evidence.authorization_issue_number != request.authorization_issue_number:
        _fail("authorization issue identity drifted")
    if evidence.request_id != request.request_id:
        _fail("request identity drifted")
    if evidence.source_repository != SOURCE_REPOSITORY:
        _fail("source repository drifted")
    if SHA_RE.fullmatch(evidence.source_sha) is None:
        _fail("source SHA is invalid")
    if SHA_RE.fullmatch(evidence.current_main_sha) is None:
        _fail("current main SHA is invalid")
    expected = {
        "operation_id": (evidence.operation_id, OPERATION_ID),
        "adapter_id": (evidence.adapter_id, ADAPTER_ID),
        "target_alias": (evidence.target_alias, TARGET_ALIAS),
        "authorization_class": (evidence.authorization_class, AUTHORIZATION_CLASS),
        "rollback_policy": (evidence.rollback_policy, ROLLBACK_POLICY),
    }
    for name, (actual, wanted) in expected.items():
        if actual != wanted:
            _fail(f"canonical {name} drifted")
    if evidence.mutation_budget != MUTATION_BUDGET:
        _fail("mutation budget drifted")
    for name in (
        "owner_verified",
        "authorization_ttl_valid",
        "authorization_body_unchanged",
        "replay_available",
        "queue_ready",
        "queue_binding_valid",
        "source_reachable_from_main",
        "source_ci_success",
    ):
        _require_bool(getattr(evidence, name), True, name)
    _require_bool(evidence.registry_execution_enabled, False, "registry_execution_enabled")
    _require_bool(evidence.p8_mutation_dispatch_enabled, False, "p8_mutation_dispatch_enabled")


def parse_sanitized_host_evidence(
    value: Mapping[str, Any], *, expected_source_sha: str
) -> SanitizedWeatherV7HostEvidence:
    expected_fields = {field.name for field in fields(SanitizedWeatherV7HostEvidence)}
    if type(value) is not dict or set(value) != expected_fields:
        _fail("sanitized host evidence schema drifted")
    evidence = SanitizedWeatherV7HostEvidence(**value)
    if evidence.trusted_checkout_name != TRUSTED_CHECKOUT_NAME:
        _fail("trusted checkout name drifted")
    if evidence.trusted_checkout_state not in {"ABSENT", "EXACT_SHA_DETACHED_CLEAN"}:
        _fail("trusted checkout state is unsupported")
    if evidence.trusted_checkout_origin != REVIEWED_ORIGIN:
        _fail("trusted checkout origin drifted")
    if evidence.trusted_checkout_state == "ABSENT":
        if evidence.trusted_checkout_source_sha != "":
            _fail("absent trusted checkout must not claim a source SHA")
    elif evidence.trusted_checkout_source_sha != expected_source_sha:
        _fail("trusted checkout source SHA drifted")
    _require_bool(evidence.v6_checkout_preserved, True, "v6_checkout_preserved")
    if evidence.predecessor_sha256 != OLD_SHA256:
        _fail("predecessor SHA-256 drifted")
    if (evidence.predecessor_owner_uid, evidence.predecessor_owner_gid, evidence.predecessor_mode) != (0, 0, "0755"):
        _fail("predecessor owner/mode drifted")
    if evidence.target_source_sha256 != NEW_SHA256:
        _fail("target source SHA-256 drifted")
    _require_bool(evidence.protected_values_included, False, "protected_values_included")
    return evidence


def prepare_privileged_delivery(
    request_payload: Mapping[str, Any],
    *,
    canonical_revalidator: CanonicalWeatherV7Revalidator,
    host_evidence_resolver: SanitizedWeatherV7HostEvidenceResolver,
    consumed_request_ids: frozenset[str] = frozenset(),
) -> WeatherV7PrivilegedDeliveryPlan:
    """Prepare the fixed Weather v7 capability without dispatching or mutating.

    Only the identity-only dispatch request is caller authority. Source, target,
    mutation budget and execution identity are source constants. The function has
    no subprocess, filesystem mutation, sudo/root, systemd or Docker surface.
    """

    request = parse_dispatch_request(request_payload)
    if request.request_id in consumed_request_ids:
        _fail("request identity has already been consumed")
    first = canonical_revalidator.revalidate(request.authorization_issue_number)
    _validate_canonical(request, first)
    host = parse_sanitized_host_evidence(
        host_evidence_resolver.resolve(source_sha=first.source_sha),
        expected_source_sha=first.source_sha,
    )
    final = canonical_revalidator.revalidate(request.authorization_issue_number)
    _validate_canonical(request, final)
    stable = tuple(field.name for field in fields(CanonicalWeatherV7Evidence))
    if any(getattr(first, name) != getattr(final, name) for name in stable):
        _fail("canonical evidence drifted during privileged revalidation")

    if not host.host_capability_installed:
        result = "HOST_CAPABILITY_INSTALL_REQUIRED"
    elif host.trusted_checkout_state == "ABSENT":
        result = "FUTURE_LIVE_CHECKOUT_BOOTSTRAP_READY"
    else:
        result = "FUTURE_LIVE_FIXED_OPERATOR_READY"

    return WeatherV7PrivilegedDeliveryPlan(
        result=result,
        authorization_issue_number=request.authorization_issue_number,
        request_id=request.request_id,
        source_sha=final.source_sha,
        host_capability_installed=host.host_capability_installed,
    )


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": "rozkalns.rpi5-main.weather-operator-upgrade-v7-privileged-delivery.v1",
        "issue": ISSUE,
        "result": "SOURCE_READY",
        "operation_id": OPERATION_ID,
        "authorization_class": AUTHORIZATION_CLASS,
        "ordinary_live_all_eligible": False,
        "identity_only_dispatch_schema": "rozkalns.deploy-dispatch-request.v1",
        "request_authority": (
            "authorization_repository",
            "authorization_repository_id",
            "authorization_issue_id",
            "authorization_issue_number",
            "request_id",
        ),
        "fixed_entrypoint": ENTRYPOINT,
        "fixed_target_path": TARGET_PATH,
        "mutation_budget": MUTATION_BUDGET,
        "privileged_dispatch_implemented": True,
        "privileged_dispatch_enabled": False,
        "host_capability_installed": False,
        "p8_mutation_dispatch_enabled": False,
        "global_executor_execution_enabled": False,
        "source_merge_authorizes_live": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "caller_source_sha_allowed": False,
        "caller_target_allowed": False,
        "caller_mutation_budget_allowed": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "production_mutation_started": False,
    }
