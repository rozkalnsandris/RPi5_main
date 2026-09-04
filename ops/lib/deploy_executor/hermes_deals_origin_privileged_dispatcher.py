from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .hermes_deals_origin_adapter import (
    OPERATION_ID,
    PULL_HELPER_ARGUMENTS,
    PULL_HELPER_CAPABILITY,
    PULL_HELPER_SOURCE_BLOB,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)
from .hermes_deals_origin_privileged_consumer import (
    CanonicalHermesOriginRevalidator,
    HermesDealsOriginPrivilegedConsumerReady,
    SanitizedHermesOriginHostEvidenceResolver,
    consume_privileged_request,
)

DISPATCH_PLAN_SCHEMA = "rozkalns.hermes-deals.origin-privileged-dispatch-plan.v1"
INSTALLED_HELPER_PATH = "/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch"
PRIVILEGED_DISPATCH_ENABLED = False
HOST_WIRING_ENABLED = False
GENUINE_HERMES_AUDIT_AUTHORIZED = False
RUNNER_RETIREMENT_ELIGIBLE = False
PRODUCTION_MUTATION_STARTED = False


class HermesDealsOriginPrivilegedDispatcherError(RuntimeError):
    pass


@dataclass(frozen=True)
class HermesDealsOriginPrivilegedDispatchPlan:
    """Source-only capability plan; it is intentionally not an execution API."""

    schema: str
    result: str
    authorization_issue_number: int
    request_id: str
    operation_id: str
    target_alias: str
    source_repository: str
    registered_source_sha: str
    canonical_as_of: str
    host_evidence_id: str
    capability: str
    helper_source_blob: str
    installed_helper_path: str
    helper_argument_names: tuple[str, str]
    helper_arguments: tuple[str, str]
    privileged_dispatch_implemented: bool = True
    privileged_dispatch_enabled: bool = False
    host_wiring_enabled: bool = False
    genuine_hermes_audit_authorized: bool = False
    runner_retirement_eligible: bool = False
    production_mutation_started: bool = False


def _require_consumer_ready(
    ready: HermesDealsOriginPrivilegedConsumerReady,
) -> HermesDealsOriginPrivilegedConsumerReady:
    if not isinstance(ready, HermesDealsOriginPrivilegedConsumerReady):
        raise HermesDealsOriginPrivilegedDispatcherError(
            "privileged consumer returned unsupported readiness"
        )
    if ready.result != "PRIVILEGED_CONSUMER_READY":
        raise HermesDealsOriginPrivilegedDispatcherError(
            "privileged consumer readiness result mismatch"
        )
    if ready.source_repository != SOURCE_REPOSITORY:
        raise HermesDealsOriginPrivilegedDispatcherError(
            "privileged consumer source repository drifted"
        )
    if ready.operation_id != OPERATION_ID:
        raise HermesDealsOriginPrivilegedDispatcherError(
            "privileged consumer operation identity drifted"
        )
    if ready.target_alias != TARGET_ALIAS:
        raise HermesDealsOriginPrivilegedDispatcherError(
            "privileged consumer target identity drifted"
        )
    required_false = {
        "privileged_dispatch_enabled": ready.privileged_dispatch_enabled,
        "host_wiring_enabled": ready.host_wiring_enabled,
        "genuine_hermes_audit_authorized": ready.genuine_hermes_audit_authorized,
        "runner_retirement_eligible": ready.runner_retirement_eligible,
        "production_mutation_started": ready.production_mutation_started,
    }
    for name, value in required_false.items():
        if type(value) is not bool or value is not False:
            raise HermesDealsOriginPrivilegedDispatcherError(
                f"privileged consumer {name} must remain false"
            )
    return ready


def prepare_hermes_deals_origin_privileged_dispatch(
    request_payload: Mapping[str, Any],
    *,
    canonical_revalidator: CanonicalHermesOriginRevalidator,
    host_evidence_resolver: SanitizedHermesOriginHostEvidenceResolver,
) -> HermesDealsOriginPrivilegedDispatchPlan:
    """Build one immutable Hermes helper plan without launching a process.

    Caller authority remains the identity-only request. The source SHA and `as_of`
    value come only from `consume_privileged_request()`, after its two complete
    canonical revalidations and sanitized host-evidence check. The executable
    identity and argument shape are source constants, not caller-selected values.
    """

    ready = _require_consumer_ready(
        consume_privileged_request(
            request_payload,
            canonical_revalidator=canonical_revalidator,
            host_evidence_resolver=host_evidence_resolver,
        )
    )
    return HermesDealsOriginPrivilegedDispatchPlan(
        schema=DISPATCH_PLAN_SCHEMA,
        result="PRIVILEGED_DISPATCH_SOURCE_READY",
        authorization_issue_number=ready.authorization_issue_number,
        request_id=ready.request_id,
        operation_id=ready.operation_id,
        target_alias=ready.target_alias,
        source_repository=ready.source_repository,
        registered_source_sha=ready.source_sha,
        canonical_as_of=ready.canonical_as_of,
        host_evidence_id=ready.host_evidence_id,
        capability=PULL_HELPER_CAPABILITY,
        helper_source_blob=PULL_HELPER_SOURCE_BLOB,
        installed_helper_path=INSTALLED_HELPER_PATH,
        helper_argument_names=PULL_HELPER_ARGUMENTS,
        helper_arguments=(ready.source_sha, ready.canonical_as_of),
    )


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": DISPATCH_PLAN_SCHEMA,
        "privileged_dispatch_implemented": True,
        "privileged_dispatch_enabled": PRIVILEGED_DISPATCH_ENABLED,
        "host_wiring_enabled": HOST_WIRING_ENABLED,
        "genuine_hermes_audit_authorized": GENUINE_HERMES_AUDIT_AUTHORIZED,
        "runner_retirement_eligible": RUNNER_RETIREMENT_ELIGIBLE,
        "production_mutation_started": PRODUCTION_MUTATION_STARTED,
        "capability": PULL_HELPER_CAPABILITY,
        "helper_source_blob": PULL_HELPER_SOURCE_BLOB,
        "installed_helper_path": INSTALLED_HELPER_PATH,
        "helper_argument_names": PULL_HELPER_ARGUMENTS,
        "caller_authority": ("authorization_issue_number",),
        "canonical_parameters": ("registered_source_sha", "canonical_as_of"),
        "process_launch_surface": False,
    }
