from __future__ import annotations

from dataclasses import dataclass
import re
import uuid
from typing import Any, Mapping, Protocol

from .hermes_deals_origin_adapter import (
    ADAPTER_ID,
    INVOCATION_BUDGET,
    OPERATION_ID,
    REQUIRED_DEPENDENCIES,
    REQUIRED_EXCLUSIONS,
    ROLLBACK_POLICY,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)
from .hermes_deals_origin_dispatch_request import (
    HermesDealsOriginDispatchRequest,
    parse_hermes_deals_origin_dispatch_request,
)

HOST_EVIDENCE_SCHEMA = "rozkalns.hermes-deals.origin-host-evidence.v1"
AUTHORIZATION_CLASS = "STRICT"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_HOST_EVIDENCE_FIELDS = frozenset(
    {
        "schema",
        "evidence_id",
        "operation_id",
        "registered_source_sha",
        "registration_name",
        "registration_owner_root",
        "registration_mode_0600",
        "dispatcher_identity_match",
        "probe_identity_match",
        "workflow_identity_match",
        "evidence_read_only",
        "protected_values_included",
    }
)


class HermesDealsOriginPrivilegedConsumerError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalHermesOriginEvidence:
    authorization_issue_number: int
    request_id: str
    queue_issue: int
    source_repository: str
    source_sha: str
    current_main_sha: str
    source_ci_run_id: int
    operation_id: str
    adapter_id: str
    target_alias: str
    authorization_class: str
    ordinary_live_all_eligible: bool
    rollback_policy: str
    mutation_budget: tuple[tuple[str, int], ...]
    exclusions: tuple[str, ...]
    dependencies: tuple[str, ...]
    authorization_owner_verified: bool
    authorization_ttl_valid: bool
    authorization_body_unchanged: bool
    queue_ready: bool
    registry_execution_enabled: bool
    source_reachable_from_main: bool
    source_ci_success: bool
    baseline_matched: bool
    prepared_execution_enabled: bool
    adapter_preflight_read_only: bool
    adapter_preflight_privileged_dispatch_ready: bool


@dataclass(frozen=True)
class SanitizedHermesOriginHostEvidence:
    evidence_id: str
    registered_source_sha: str


@dataclass(frozen=True)
class HermesDealsOriginPrivilegedConsumerReady:
    result: str
    authorization_issue_number: int
    request_id: str
    queue_issue: int
    source_repository: str
    source_sha: str
    current_main_sha: str
    source_ci_run_id: int
    operation_id: str
    target_alias: str
    host_evidence_id: str
    privileged_consumer_implemented: bool = True
    privileged_dispatch_enabled: bool = False
    host_wiring_enabled: bool = False
    genuine_hermes_audit_authorized: bool = False
    runner_retirement_eligible: bool = False
    production_mutation_started: bool = False


class CanonicalHermesOriginRevalidator(Protocol):
    def revalidate(
        self,
        authorization_issue_number: int,
    ) -> CanonicalHermesOriginEvidence: ...

    def verify_unchanged(
        self,
        evidence: CanonicalHermesOriginEvidence,
    ) -> None: ...


class SanitizedHermesOriginHostEvidenceResolver(Protocol):
    def resolve(
        self,
        *,
        source_sha: str,
    ) -> Mapping[str, Any]: ...


def _fail(message: str) -> None:
    raise HermesDealsOriginPrivilegedConsumerError(message)


def _positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        _fail(f"{where} must be a positive integer")
    return value


def _canonical_uuid4(value: Any, where: str) -> str:
    if type(value) is not str:
        _fail(f"{where} must be a canonical lowercase UUIDv4")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise HermesDealsOriginPrivilegedConsumerError(
            f"{where} must be a canonical lowercase UUIDv4"
        ) from exc
    if parsed.version != 4 or str(parsed) != value:
        _fail(f"{where} must be a canonical lowercase UUIDv4")
    return value


def _require_bool(value: Any, expected: bool, where: str) -> None:
    if type(value) is not bool or value is not expected:
        _fail(f"{where} must be {str(expected).lower()}")


def _require_source_sha(value: Any, where: str) -> str:
    if type(value) is not str or SHA_RE.fullmatch(value) is None:
        _fail(f"{where} must be a 40-character lowercase Git SHA")
    return value


def _validate_canonical_evidence(
    request: HermesDealsOriginDispatchRequest,
    evidence: CanonicalHermesOriginEvidence,
) -> None:
    if not isinstance(evidence, CanonicalHermesOriginEvidence):
        _fail("canonical revalidator returned unsupported evidence")
    if evidence.authorization_issue_number != request.authorization_issue_number:
        _fail("canonical authorization issue identity drifted")
    _canonical_uuid4(evidence.request_id, "canonical request_id")
    _positive_int(evidence.queue_issue, "canonical queue_issue")
    _positive_int(evidence.source_ci_run_id, "canonical source_ci_run_id")
    _require_source_sha(evidence.source_sha, "canonical source_sha")
    _require_source_sha(evidence.current_main_sha, "canonical current_main_sha")

    expected_strings = {
        "source_repository": (evidence.source_repository, SOURCE_REPOSITORY),
        "operation_id": (evidence.operation_id, OPERATION_ID),
        "adapter_id": (evidence.adapter_id, ADAPTER_ID),
        "target_alias": (evidence.target_alias, TARGET_ALIAS),
        "authorization_class": (evidence.authorization_class, AUTHORIZATION_CLASS),
        "rollback_policy": (evidence.rollback_policy, ROLLBACK_POLICY),
    }
    for name, (actual, expected) in expected_strings.items():
        if actual != expected:
            _fail(f"canonical {name} drifted")

    if evidence.mutation_budget != INVOCATION_BUDGET:
        _fail("canonical Hermes invocation budget drifted")
    if not REQUIRED_EXCLUSIONS.issubset(set(evidence.exclusions)):
        _fail("canonical Hermes exclusions are incomplete")
    if not REQUIRED_DEPENDENCIES.issubset(set(evidence.dependencies)):
        _fail("canonical Hermes provenance/dependencies are incomplete")

    required_true = {
        "authorization_owner_verified": evidence.authorization_owner_verified,
        "authorization_ttl_valid": evidence.authorization_ttl_valid,
        "authorization_body_unchanged": evidence.authorization_body_unchanged,
        "queue_ready": evidence.queue_ready,
        "source_reachable_from_main": evidence.source_reachable_from_main,
        "source_ci_success": evidence.source_ci_success,
        "baseline_matched": evidence.baseline_matched,
        "adapter_preflight_read_only": evidence.adapter_preflight_read_only,
    }
    for name, value in required_true.items():
        _require_bool(value, True, f"canonical {name}")

    required_false = {
        "ordinary_live_all_eligible": evidence.ordinary_live_all_eligible,
        "registry_execution_enabled": evidence.registry_execution_enabled,
        "prepared_execution_enabled": evidence.prepared_execution_enabled,
        "adapter_preflight_privileged_dispatch_ready": (
            evidence.adapter_preflight_privileged_dispatch_ready
        ),
    }
    for name, value in required_false.items():
        _require_bool(value, False, f"canonical {name}")


def parse_sanitized_hermes_origin_host_evidence(
    value: Mapping[str, Any],
    *,
    expected_source_sha: str,
) -> SanitizedHermesOriginHostEvidence:
    if type(value) is not dict:
        _fail("sanitized host evidence must be an object")
    actual = frozenset(value)
    if actual != _HOST_EVIDENCE_FIELDS:
        missing = sorted(_HOST_EVIDENCE_FIELDS - actual)
        extra = sorted(actual - _HOST_EVIDENCE_FIELDS)
        _fail(f"sanitized host evidence keys mismatch; missing={missing}, extra={extra}")
    if value["schema"] != HOST_EVIDENCE_SCHEMA:
        _fail("sanitized host evidence schema mismatch")
    evidence_id = value["evidence_id"]
    if type(evidence_id) is not str or EVIDENCE_ID_RE.fullmatch(evidence_id) is None:
        _fail("sanitized host evidence_id is invalid")
    if value["operation_id"] != OPERATION_ID:
        _fail("sanitized host operation identity drifted")
    registered_source_sha = _require_source_sha(
        value["registered_source_sha"],
        "sanitized host registered_source_sha",
    )
    if registered_source_sha != expected_source_sha:
        _fail("sanitized host registered source SHA drifted")
    if value["registration_name"] != "origin-path-audit":
        _fail("sanitized host registration name drifted")

    for field in (
        "registration_owner_root",
        "registration_mode_0600",
        "dispatcher_identity_match",
        "probe_identity_match",
        "workflow_identity_match",
        "evidence_read_only",
    ):
        _require_bool(value[field], True, f"sanitized host {field}")
    _require_bool(
        value["protected_values_included"],
        False,
        "sanitized host protected_values_included",
    )

    return SanitizedHermesOriginHostEvidence(
        evidence_id=evidence_id,
        registered_source_sha=registered_source_sha,
    )


def evaluate_hermes_deals_origin_privileged_consumer(
    request_payload: Mapping[str, Any],
    *,
    canonical_revalidator: CanonicalHermesOriginRevalidator,
    host_evidence_resolver: SanitizedHermesOriginHostEvidenceResolver,
) -> HermesDealsOriginPrivilegedConsumerReady:
    """Independently revalidate one Hermes origin request without dispatching it.

    The only caller-controlled authority is the identity-only request. All source,
    queue, authorization and host evidence is re-derived through capability-specific
    read-only interfaces. This function has no execution or host-mutation surface.
    """

    request = parse_hermes_deals_origin_dispatch_request(request_payload)
    evidence = canonical_revalidator.revalidate(
        request.authorization_issue_number,
    )
    _validate_canonical_evidence(request, evidence)

    host_evidence = parse_sanitized_hermes_origin_host_evidence(
        host_evidence_resolver.resolve(source_sha=evidence.source_sha),
        expected_source_sha=evidence.source_sha,
    )

    # Final authority revalidation occurs after host evidence resolution and before
    # the source-only readiness result is emitted.
    canonical_revalidator.verify_unchanged(evidence)

    return HermesDealsOriginPrivilegedConsumerReady(
        result="PRIVILEGED_CONSUMER_READY",
        authorization_issue_number=request.authorization_issue_number,
        request_id=evidence.request_id,
        queue_issue=evidence.queue_issue,
        source_repository=evidence.source_repository,
        source_sha=evidence.source_sha,
        current_main_sha=evidence.current_main_sha,
        source_ci_run_id=evidence.source_ci_run_id,
        operation_id=evidence.operation_id,
        target_alias=evidence.target_alias,
        host_evidence_id=host_evidence.evidence_id,
    )


def source_readiness() -> Mapping[str, Any]:
    return {
        "privileged_consumer_implemented": True,
        "privileged_dispatch_enabled": False,
        "host_wiring_enabled": False,
        "genuine_hermes_audit_authorized": False,
        "runner_retirement_eligible": False,
        "production_mutation_started": False,
        "request_authority": ("authorization_issue_number",),
        "host_evidence_schema": HOST_EVIDENCE_SCHEMA,
    }
