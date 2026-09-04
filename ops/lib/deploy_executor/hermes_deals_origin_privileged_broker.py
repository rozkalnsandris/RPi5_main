from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from .hermes_deals_origin_adapter import (
    OPERATION_ID,
    PULL_HELPER_ARGUMENTS,
    PULL_HELPER_CAPABILITY,
    PULL_HELPER_SOURCE_BLOB,
    SOURCE_REPOSITORY,
)
from .hermes_deals_origin_dispatch_request import (
    HermesDealsOriginDispatchRequest,
    HermesDealsOriginDispatchRequestError,
    parse_hermes_deals_origin_dispatch_request,
)
from .hermes_deals_origin_privileged_consumer import (
    CanonicalHermesOriginRevalidator,
    HermesOriginHostEvidenceResolver,
)
from .hermes_deals_origin_privileged_dispatcher import (
    INSTALLED_HELPER_PATH,
    HermesDealsOriginPrivilegedDispatchPlan,
    prepare_hermes_deals_origin_privileged_dispatch,
)

BROKER_REQUEST_MAX_BYTES = 256
BROKER_SOCKET_PATH = "/run/rozkalns-hermes-deals-origin-broker/request.sock"
BROKER_SOCKET_UNIT = "rozkalns-hermes-deals-origin-broker.socket"
BROKER_SERVICE_UNIT = "rozkalns-hermes-deals-origin-broker@.service"
BROKER_INSTALL_PATH = "/usr/local/libexec/rozkalns-hermes-deals-origin-broker"
SOURCE_READ_AUTHORITY_PROVEN = False
HELPER_PROCESS_LAUNCH_IMPLEMENTED = False
PRIVILEGED_DISPATCH_ENABLED = False
HOST_WIRING_ENABLED = False
GENUINE_HERMES_AUDIT_AUTHORIZED = False
RUNNER_RETIREMENT_ELIGIBLE = False
PRODUCTION_MUTATION_STARTED = False
LIVE_INSTALL_ELIGIBLE = False


class HermesDealsOriginPrivilegedBrokerError(RuntimeError):
    pass


@dataclass(frozen=True)
class HermesDealsOriginBrokerEnvelope:
    """Source-only broker envelope produced after mandatory canonical revalidation.

    This value is not execution authority. It intentionally has no callable,
    command, environment, UID/GID, unit selector, output path or arbitrary argv.
    """

    authorization_issue_number: int
    operation_id: str
    source_repository: str
    capability: str
    helper_source_blob: str
    installed_helper_path: str
    helper_argument_names: tuple[str, str]
    helper_arguments: tuple[str, str]
    process_launch_implemented: bool
    privileged_dispatch_enabled: bool
    host_wiring_enabled: bool
    genuine_hermes_audit_authorized: bool
    runner_retirement_eligible: bool
    production_mutation_started: bool


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HermesDealsOriginPrivilegedBrokerError(
                f"duplicate JSON field is forbidden: {key}"
            )
        result[key] = value
    return result


def parse_broker_transport_request(raw: bytes) -> HermesDealsOriginDispatchRequest:
    """Parse one bounded newline-framed identity-only socket request."""

    if type(raw) is not bytes:
        raise HermesDealsOriginPrivilegedBrokerError("broker request must be bytes")
    if not raw or len(raw) > BROKER_REQUEST_MAX_BYTES:
        raise HermesDealsOriginPrivilegedBrokerError("broker request size is invalid")
    if b"\x00" in raw or b"\r" in raw:
        raise HermesDealsOriginPrivilegedBrokerError("broker request contains forbidden framing")
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise HermesDealsOriginPrivilegedBrokerError(
            "broker request must be exactly one newline-terminated frame"
        )
    try:
        decoded = raw[:-1].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HermesDealsOriginPrivilegedBrokerError("broker request is not UTF-8") from exc
    try:
        value = json.loads(decoded, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise HermesDealsOriginPrivilegedBrokerError("broker request is not valid JSON") from exc
    try:
        return parse_hermes_deals_origin_dispatch_request(value)
    except HermesDealsOriginDispatchRequestError as exc:
        raise HermesDealsOriginPrivilegedBrokerError(str(exc)) from exc


def _validate_dispatch_plan(plan: HermesDealsOriginPrivilegedDispatchPlan) -> None:
    if plan.operation_id != OPERATION_ID:
        raise HermesDealsOriginPrivilegedBrokerError("operation identity drift")
    if plan.source_repository != SOURCE_REPOSITORY:
        raise HermesDealsOriginPrivilegedBrokerError("source repository drift")
    if plan.capability != PULL_HELPER_CAPABILITY:
        raise HermesDealsOriginPrivilegedBrokerError("capability identity drift")
    if plan.helper_source_blob != PULL_HELPER_SOURCE_BLOB:
        raise HermesDealsOriginPrivilegedBrokerError("helper source identity drift")
    if plan.installed_helper_path != INSTALLED_HELPER_PATH:
        raise HermesDealsOriginPrivilegedBrokerError("installed helper path drift")
    if plan.helper_argument_names != PULL_HELPER_ARGUMENTS:
        raise HermesDealsOriginPrivilegedBrokerError("helper interface drift")
    if plan.helper_arguments != (plan.registered_source_sha, plan.canonical_as_of):
        raise HermesDealsOriginPrivilegedBrokerError("helper argument derivation drift")
    if (
        plan.privileged_dispatch_enabled
        or plan.host_wiring_enabled
        or plan.genuine_hermes_audit_authorized
        or plan.runner_retirement_eligible
        or plan.production_mutation_started
    ):
        raise HermesDealsOriginPrivilegedBrokerError("live authority entered source-only broker")


def prepare_hermes_deals_origin_broker_envelope(
    raw_request: bytes,
    *,
    canonical_revalidator: CanonicalHermesOriginRevalidator,
    host_evidence_resolver: HermesOriginHostEvidenceResolver,
) -> HermesDealsOriginBrokerEnvelope:
    """Prepare the exact capability envelope; never launch a process.

    The broker parses only the issue identity, then invokes the already-reviewed
    dispatcher preparation path itself. A caller cannot supply or reconstruct a
    dispatch plan and cannot bypass the double canonical revalidation boundary.
    """

    request = parse_broker_transport_request(raw_request)
    plan = prepare_hermes_deals_origin_privileged_dispatch(
        {
            "schema": "rozkalns.hermes-deals.origin-dispatch-request.v1",
            "authorization_issue_number": request.authorization_issue_number,
        },
        canonical_revalidator=canonical_revalidator,
        host_evidence_resolver=host_evidence_resolver,
    )
    _validate_dispatch_plan(plan)
    return HermesDealsOriginBrokerEnvelope(
        authorization_issue_number=plan.authorization_issue_number,
        operation_id=plan.operation_id,
        source_repository=plan.source_repository,
        capability=plan.capability,
        helper_source_blob=plan.helper_source_blob,
        installed_helper_path=plan.installed_helper_path,
        helper_argument_names=plan.helper_argument_names,
        helper_arguments=plan.helper_arguments,
        process_launch_implemented=HELPER_PROCESS_LAUNCH_IMPLEMENTED,
        privileged_dispatch_enabled=PRIVILEGED_DISPATCH_ENABLED,
        host_wiring_enabled=HOST_WIRING_ENABLED,
        genuine_hermes_audit_authorized=GENUINE_HERMES_AUDIT_AUTHORIZED,
        runner_retirement_eligible=RUNNER_RETIREMENT_ELIGIBLE,
        production_mutation_started=PRODUCTION_MUTATION_STARTED,
    )


def source_readiness() -> Mapping[str, Any]:
    return {
        "broker_boundary_implemented": True,
        "transport": "systemd-unix-stream-socket",
        "socket_path": BROKER_SOCKET_PATH,
        "socket_unit": BROKER_SOCKET_UNIT,
        "service_unit": BROKER_SERVICE_UNIT,
        "broker_install_path": BROKER_INSTALL_PATH,
        "caller_authority": ("authorization_issue_number",),
        "source_read_authority_proven": SOURCE_READ_AUTHORITY_PROVEN,
        "process_launch_surface": HELPER_PROCESS_LAUNCH_IMPLEMENTED,
        "privileged_dispatch_enabled": PRIVILEGED_DISPATCH_ENABLED,
        "host_wiring_enabled": HOST_WIRING_ENABLED,
        "genuine_hermes_audit_authorized": GENUINE_HERMES_AUDIT_AUTHORIZED,
        "runner_retirement_eligible": RUNNER_RETIREMENT_ELIGIBLE,
        "production_mutation_started": PRODUCTION_MUTATION_STARTED,
        "live_install_eligible": LIVE_INSTALL_ELIGIBLE,
        "blocking_prerequisite": "prove exact authenticated Hermes GitHub source-read/revalidation authority",
    }
