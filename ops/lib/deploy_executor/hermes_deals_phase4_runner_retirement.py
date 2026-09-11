from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

OWNER_NUMERIC_ID = 277435981
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_JOB_RESULTS = frozenset(
    {"DONE", "SOURCE_READY_LIVE_LATER", "NO_OP_ALREADY_RECONCILED"}
)
ALLOWED_DEPLOY_CLASSES = frozenset(
    {"NO_DEPLOY", "AUTO_DEPLOY_SAFE", "MANUAL_ROLLOUT_REQUIRED", "DB_HOST_APPLY_REQUIRED"}
)


class HermesDealsPhase4ContractError(ValueError):
    pass


@dataclass(frozen=True)
class CapabilityRequest:
    capability_id: str
    operation_id: str
    source_sha: str
    owner_numeric_id: int
    merged_reachable: bool
    exact_ci_success: bool


@dataclass(frozen=True)
class CapabilityRetirementEvidence:
    replacement_source_ready: bool
    runtime_wiring_proven: bool
    genuine_canary_proven: bool
    legacy_fallback_dependency_removed: bool
    fresh_final_runner_inventory: bool


def validate_contract(contract: Mapping[str, Any]) -> None:
    expected_top_level = {
        "schema_version",
        "contract",
        "implementation_issue",
        "status",
        "source_anchors",
        "jobs",
        "residual_runner_paths",
        "capability_classes",
        "approved_audit_operations",
        "source_sync_contract",
        "production_release_contract",
        "netto_identity",
        "public_event_adversarial_matrix",
        "runner_retirement",
        "auto_live_and_full_boundary",
        "mutation",
    }
    if set(contract) != expected_top_level:
        raise HermesDealsPhase4ContractError("top-level contract field drift")
    if contract["schema_version"] != 1 or contract["implementation_issue"] != 466:
        raise HermesDealsPhase4ContractError("contract identity mismatch")
    if contract["status"] != "SOURCE_ONLY_BUNDLE_READY_LIVE_DISABLED":
        raise HermesDealsPhase4ContractError("contract status mismatch")

    jobs = contract["jobs"]
    if type(jobs) is not list or [row.get("job") for row in jobs] != list(range(1, 11)):
        raise HermesDealsPhase4ContractError("jobs must be exactly 1..10")
    if any(row.get("result") not in ALLOWED_JOB_RESULTS for row in jobs):
        raise HermesDealsPhase4ContractError("unsupported job result")

    rows = contract["residual_runner_paths"]
    if type(rows) is not list or len(rows) != 4:
        raise HermesDealsPhase4ContractError("residual runner path inventory must contain four entries")
    ids = [row.get("capability_id") for row in rows]
    if len(set(ids)) != len(ids):
        raise HermesDealsPhase4ContractError("duplicate capability id")
    for row in rows:
        if not row.get("replacement_operation_id"):
            raise HermesDealsPhase4ContractError("replacement operation id is required")
        for field in (
            "public_event_direct_execution",
            "generic_command_authority",
            "generic_path_authority",
            "generic_argv_authority",
            "generic_environment_authority",
        ):
            if row.get(field) is not False:
                raise HermesDealsPhase4ContractError(f"{row.get('capability_id')} widens {field}")

    mutation = contract["mutation"]
    if any(value is not False for value in mutation.values()):
        raise HermesDealsPhase4ContractError("bundle mutation flags must all remain false")


def _capability(contract: Mapping[str, Any], capability_id: str) -> Mapping[str, Any]:
    rows = [
        row
        for row in contract["residual_runner_paths"]
        if row.get("capability_id") == capability_id
    ]
    if len(rows) != 1:
        raise HermesDealsPhase4ContractError("unknown or ambiguous capability id")
    return rows[0]


def validate_capability_request(
    contract: Mapping[str, Any], request: CapabilityRequest
) -> Mapping[str, Any]:
    validate_contract(contract)
    row = _capability(contract, request.capability_id)
    if request.operation_id != row["replacement_operation_id"]:
        raise HermesDealsPhase4ContractError("operation id mismatch")
    if SHA_RE.fullmatch(request.source_sha) is None:
        raise HermesDealsPhase4ContractError("source SHA must be exact lowercase 40-character SHA")
    if row["owner_numeric_id_required"] and request.owner_numeric_id != OWNER_NUMERIC_ID:
        raise HermesDealsPhase4ContractError("owner numeric identity mismatch")
    if row["merged_reachable_sha_required"] and request.merged_reachable is not True:
        raise HermesDealsPhase4ContractError("source SHA is not merged/reachable")
    if row["exact_ci_success_required"] and request.exact_ci_success is not True:
        raise HermesDealsPhase4ContractError("exact-SHA CI is not successful")
    return {
        "decision": "SOURCE_REQUEST_VALIDATED",
        "capability_id": request.capability_id,
        "operation_id": request.operation_id,
        "runtime_live_authority": False,
        "production_mutation_started": False,
    }


def evaluate_runner_retirement(
    contract: Mapping[str, Any],
    runner_label: str,
    evidence_by_capability: Mapping[str, CapabilityRetirementEvidence],
) -> Mapping[str, Any]:
    validate_contract(contract)
    labels = contract["runner_retirement"]["runner_labels"]
    if runner_label not in labels:
        return {"decision": "NOT_ELIGIBLE", "missing": ("unknown_runner_label",)}

    required = tuple(labels[runner_label]["capabilities"])
    missing: list[str] = []
    for capability_id in required:
        evidence = evidence_by_capability.get(capability_id)
        if evidence is None:
            missing.append(f"{capability_id}:missing_evidence")
            continue
        if not evidence.replacement_source_ready:
            missing.append(f"{capability_id}:replacement_source_not_ready")
        if not evidence.runtime_wiring_proven:
            missing.append(f"{capability_id}:runtime_wiring_unproven")
        if not evidence.genuine_canary_proven:
            missing.append(f"{capability_id}:genuine_canary_unproven")
        if not evidence.legacy_fallback_dependency_removed:
            missing.append(f"{capability_id}:legacy_fallback_still_required")
        if not evidence.fresh_final_runner_inventory:
            missing.append(f"{capability_id}:fresh_final_inventory_missing")

    return {
        "decision": "ELIGIBLE" if not missing else "NOT_ELIGIBLE",
        "missing": tuple(missing),
        "runner_label": runner_label,
        "runtime_mutation_authorized": False,
    }


def reconcile_auto_live(
    contract: Mapping[str, Any],
    deploy_class: str,
    *,
    exact_target_sha_ci_success: bool,
    full_range_complete: bool,
    manifest_active: bool,
    static_operation_registered: bool,
) -> Mapping[str, Any]:
    validate_contract(contract)
    policy = contract["auto_live_and_full_boundary"]
    if deploy_class not in ALLOWED_DEPLOY_CLASSES:
        return _auto_live_result("BLOCKED", "unknown_deploy_class")
    if deploy_class == "NO_DEPLOY":
        return _auto_live_result("RECONCILE_ONLY", "no_deploy")
    if deploy_class in set(policy["owner_required_classes"]):
        return _auto_live_result("OWNER_REQUIRED", "sensitive_deploy_class")
    if not exact_target_sha_ci_success:
        return _auto_live_result("BLOCKED", "exact_target_sha_ci_missing")
    if not full_range_complete:
        return _auto_live_result("BLOCKED", "full_baseline_to_target_range_incomplete")
    if not manifest_active:
        return _auto_live_result("BLOCKED", "manifest_inactive")
    if not static_operation_registered:
        return _auto_live_result("BLOCKED", "static_operation_unregistered")
    return _auto_live_result("AUTO_DEPLOY_SAFE_CANDIDATE", "source_policy_pass")


def _auto_live_result(decision: str, reason: str) -> Mapping[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "automatic_mutation_allowed": False,
        "runtime_live_authority": False,
        "production_mutation_started": False,
    }
