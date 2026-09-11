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


class HermesDealsPhase4ClosureError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimePreflightEvidence:
    source_sha: str
    exact_sha_ci_success: bool
    helper_source_path: str
    helper_source_blob: str
    registration_identity_matches: bool
    execution_identity_matches: bool


@dataclass(frozen=True)
class RetirementEvidence:
    replacement_source_ready: bool
    runtime_wiring_proven: bool
    genuine_canary_or_e2e_proven: bool
    legacy_fallback_dependency_removed: bool
    fresh_final_runner_inventory: bool


def validate_contract(contract: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "contract",
        "implementation_issue",
        "status",
        "source_anchors",
        "source_path_drift",
        "predecessor",
        "jobs",
        "residual_capabilities",
        "canary_readiness",
        "source_sync_readiness",
        "production_release_readiness",
        "netto_identity_supersession",
        "runtime_preflight_operators",
        "runner_retirement_graph",
        "auto_live_scale_out",
        "phase4_closure",
        "mutation",
    }
    if set(contract) != expected:
        raise HermesDealsPhase4ClosureError("top-level contract field drift")
    if contract["schema_version"] != 1 or contract["implementation_issue"] != 467:
        raise HermesDealsPhase4ClosureError("contract identity mismatch")
    if contract["status"] != "SOURCE_ONLY_BUNDLE_READY_LIVE_DISABLED":
        raise HermesDealsPhase4ClosureError("contract status mismatch")
    if contract["source_anchors"]["source_runtime_state_inferred"] is not False:
        raise HermesDealsPhase4ClosureError("repository source must not assert runtime state")

    predecessor = contract["predecessor"]
    if predecessor["canonical_pr"] != 468:
        raise HermesDealsPhase4ClosureError("predecessor canonical PR drift")
    if SHA_RE.fullmatch(predecessor["canonical_pr_head"]) is None:
        raise HermesDealsPhase4ClosureError("predecessor canonical head is not exact")
    if predecessor["terminal_exact_head_ci_success"] is not True:
        raise HermesDealsPhase4ClosureError("predecessor exact-head CI is not terminal success")
    if len(predecessor["terminal_results"]) != 10:
        raise HermesDealsPhase4ClosureError("predecessor terminal result set is incomplete")

    jobs = contract["jobs"]
    if type(jobs) is not list or [row.get("job") for row in jobs] != list(range(1, 11)):
        raise HermesDealsPhase4ClosureError("jobs must be exactly 1..10")
    if any(row.get("result") not in ALLOWED_JOB_RESULTS for row in jobs):
        raise HermesDealsPhase4ClosureError("unsupported job result")

    drift = contract["source_path_drift"]
    if drift["stale_path"] != "tools/install-hermes-deals-audit-runner.sh":
        raise HermesDealsPhase4ClosureError("unexpected stale path identity")
    if drift["stale_path_is_current_authority"] is not False:
        raise HermesDealsPhase4ClosureError("stale source path cannot be authority")
    if drift["resolution"] != "CAPABILITY_SPECIFIC_TOOLS_RUNNER_PATHS":
        raise HermesDealsPhase4ClosureError("source-path drift is unresolved")
    for row in drift["current_paths"]:
        if not row["path"].startswith("tools/runner/"):
            raise HermesDealsPhase4ClosureError("current capability path escaped tools/runner")
        if SHA_RE.fullmatch(row["blob"]) is None:
            raise HermesDealsPhase4ClosureError("current capability blob must be exact")

    capabilities = contract["residual_capabilities"]
    if [row["capability_id"] for row in capabilities] != [
        "origin_path_audit",
        "approved_audit_command",
        "source_sync",
        "production_release",
    ]:
        raise HermesDealsPhase4ClosureError("residual capability set drift")
    for row in capabilities:
        if SHA_RE.fullmatch(row["workflow_blob"]) is None:
            raise HermesDealsPhase4ClosureError("workflow blob must be exact")
        if SHA_RE.fullmatch(row["helper_source_blob"]) is None:
            raise HermesDealsPhase4ClosureError("helper source blob must be exact")
        if row["source_replacement_ready"] is not True:
            raise HermesDealsPhase4ClosureError("residual source replacement not ready")
        if row["runtime_wiring_asserted_by_bundle"] is not False:
            raise HermesDealsPhase4ClosureError("source bundle cannot assert runtime wiring")

    canary = contract["canary_readiness"]
    if canary["operation_id"] != "hermes-deals.runner-smoke-audit.v1":
        raise HermesDealsPhase4ClosureError("canary must use the lowest-risk fixed audit operation")
    if canary["caller_command_path_argv_environment_authority"] is not False:
        raise HermesDealsPhase4ClosureError("canary widens caller authority")
    if canary["ready_or_live_auth_created"] is not False or canary["genuine_canary_performed"] is not False:
        raise HermesDealsPhase4ClosureError("source package cannot create canary authority/evidence")
    if canary["expected_receipt"]["production_mutation_started"] is not False:
        raise HermesDealsPhase4ClosureError("read-only canary receipt must remain pre-production")

    sync = contract["source_sync_readiness"]
    if sync["source_checkout_path"] != "/home/andris/hermes-deals":
        raise HermesDealsPhase4ClosureError("source-sync target path drift")
    if sync["allowed_future_mutation"] != "FAST_FORWARD_TO_EXACT_MERGED_REACHABLE_SHA":
        raise HermesDealsPhase4ClosureError("source-sync mutation class drift")
    if sync["generic_checkout_path_authority"] is not False or sync["generic_git_subcommand_authority"] is not False:
        raise HermesDealsPhase4ClosureError("source-sync generic authority widened")
    if sync["runtime_execution_enabled"] is not False:
        raise HermesDealsPhase4ClosureError("source-sync runtime execution must remain disabled")

    release = contract["production_release_readiness"]
    if release["future_auto_live_candidate_class"] != "AUTO_DEPLOY_SAFE":
        raise HermesDealsPhase4ClosureError("release auto-live class drift")
    if release["manifest_indexed"] is not False or release["static_operation_registered"] is not False:
        raise HermesDealsPhase4ClosureError("bundle must not activate release Auto-Live")
    if release["automatic_mutation_enabled"] is not False:
        raise HermesDealsPhase4ClosureError("release mutation must remain disabled")

    netto = contract["netto_identity_supersession"]
    if netto["authoritative_issue"] != 425 or netto["superseded_issue"] != 424:
        raise HermesDealsPhase4ClosureError("Netto supersession drift")
    if netto["model"] != "DEDICATED_NON_LOGIN_NON_ROOT_NO_DOCKER":
        raise HermesDealsPhase4ClosureError("Netto identity model weakened")
    if netto["supplementary_groups"] != [] or "docker" not in netto["forbidden_groups"]:
        raise HermesDealsPhase4ClosureError("Netto supplementary-group boundary weakened")
    if {"root", "andris", "github-runner"} - set(netto["forbidden_accounts"]):
        raise HermesDealsPhase4ClosureError("Netto forbidden-account boundary weakened")
    if netto["caller_selectable_identity"] is not False:
        raise HermesDealsPhase4ClosureError("Netto identity became caller-selectable")

    operators = contract["runtime_preflight_operators"]
    if len(operators) != len(capabilities):
        raise HermesDealsPhase4ClosureError("each residual capability needs one preflight")
    if {row["capability_id"] for row in operators} != {row["capability_id"] for row in capabilities}:
        raise HermesDealsPhase4ClosureError("preflight capability set mismatch")
    for row in operators:
        for field in (
            "read_only",
            "helper_execution_enabled",
            "protected_credential_reads_enabled",
            "host_writes_enabled",
        ):
            expected_value = field == "read_only"
            if row[field] is not expected_value:
                raise HermesDealsPhase4ClosureError(f"preflight boundary drift: {field}")

    graph = contract["runner_retirement_graph"]
    if graph["unknown_or_missing_evidence_result"] != "NOT_ELIGIBLE":
        raise HermesDealsPhase4ClosureError("retirement graph must fail closed")
    if graph["runner_deregistration_authorized"] is not False:
        raise HermesDealsPhase4ClosureError("source graph cannot authorize deregistration")

    auto = contract["auto_live_scale_out"]
    if auto["auto_live_eligible_classes"] != ["AUTO_DEPLOY_SAFE"]:
        raise HermesDealsPhase4ClosureError("Auto-Live safe class drift")
    if auto["post_mutation_automatic_retry"] is not False:
        raise HermesDealsPhase4ClosureError("post-mutation automatic retry widened")
    if auto["auto_run_full_merge_authority_is_live_authority"] is not False:
        raise HermesDealsPhase4ClosureError("merge authority cannot become LIVE authority")
    if any(row["automatic_mutation_enabled"] is not False for row in auto["capabilities"].values()):
        raise HermesDealsPhase4ClosureError("scale-out source bundle must stay mutation-disabled")

    closure = contract["phase4_closure"]
    if closure["source_evidence_alone_can_close_phase4"] is not False:
        raise HermesDealsPhase4ClosureError("Phase 4 cannot close from source alone")
    if closure["current_phase4_state"] != "NOT_CLOSED_LIVE_EVIDENCE_REQUIRED":
        raise HermesDealsPhase4ClosureError("Phase 4 source closure state drift")

    if any(value is not False for value in contract["mutation"].values()):
        raise HermesDealsPhase4ClosureError("all runtime mutation flags must remain false")


def _capability(contract: Mapping[str, Any], capability_id: str) -> Mapping[str, Any]:
    rows = [row for row in contract["residual_capabilities"] if row["capability_id"] == capability_id]
    if len(rows) != 1:
        raise HermesDealsPhase4ClosureError("unknown or ambiguous capability")
    return rows[0]


def _preflight(contract: Mapping[str, Any], capability_id: str) -> Mapping[str, Any]:
    rows = [row for row in contract["runtime_preflight_operators"] if row["capability_id"] == capability_id]
    if len(rows) != 1:
        raise HermesDealsPhase4ClosureError("unknown or ambiguous preflight")
    return rows[0]


def evaluate_runtime_preflight(
    contract: Mapping[str, Any],
    capability_id: str,
    evidence: RuntimePreflightEvidence,
) -> Mapping[str, Any]:
    validate_contract(contract)
    capability = _capability(contract, capability_id)
    preflight = _preflight(contract, capability_id)
    missing: list[str] = []
    if SHA_RE.fullmatch(evidence.source_sha) is None:
        missing.append("exact_source_sha_invalid")
    elif evidence.source_sha != contract["source_anchors"]["hermes_deals_main_sha"]:
        missing.append("source_sha_mismatch")
    if evidence.exact_sha_ci_success is not True:
        missing.append("exact_sha_ci_missing")
    if evidence.helper_source_path != preflight["helper_source_path"]:
        missing.append("helper_source_path_mismatch")
    if evidence.helper_source_blob != preflight["helper_source_blob"]:
        missing.append("helper_source_blob_mismatch")
    if evidence.registration_identity_matches is not True:
        missing.append("registration_identity_unproven")
    if evidence.execution_identity_matches is not True:
        missing.append("execution_identity_unproven")
    return {
        "decision": "SOURCE_PREFLIGHT_READY" if not missing else "BLOCKED",
        "capability_id": capability["capability_id"],
        "missing": tuple(missing),
        "helper_execution_allowed": False,
        "host_write_allowed": False,
        "runtime_live_authority": False,
    }


def evaluate_runner_retirement(
    contract: Mapping[str, Any],
    runner_label: str,
    evidence_by_capability: Mapping[str, RetirementEvidence],
) -> Mapping[str, Any]:
    validate_contract(contract)
    labels = contract["runner_retirement_graph"]["runner_labels"]
    if runner_label not in labels:
        return {"decision": "NOT_ELIGIBLE", "missing": ("unknown_runner_label",), "runner_deregistration_authorized": False}
    missing: list[str] = []
    for capability_id in labels[runner_label]["capabilities"]:
        evidence = evidence_by_capability.get(capability_id)
        if evidence is None:
            missing.append(f"{capability_id}:missing_evidence")
            continue
        for field in contract["runner_retirement_graph"]["required_evidence"]:
            if getattr(evidence, field) is not True:
                missing.append(f"{capability_id}:{field}")
    return {
        "decision": "ELIGIBLE_FOR_SEPARATE_OWNER_RETIREMENT_GATE" if not missing else "NOT_ELIGIBLE",
        "runner_label": runner_label,
        "missing": tuple(missing),
        "runner_deregistration_authorized": False,
    }


def reconcile_auto_live_scale_out(
    contract: Mapping[str, Any],
    capability_id: str,
    deploy_class: str,
    *,
    exact_sha_ci_success: bool,
    full_range_complete: bool,
    stable_concurrency: bool,
    helper_identity_matches: bool,
) -> Mapping[str, Any]:
    validate_contract(contract)
    auto = contract["auto_live_scale_out"]
    if capability_id not in auto["capabilities"]:
        return _auto_result("BLOCKED", "unknown_capability")
    if deploy_class not in ALLOWED_DEPLOY_CLASSES:
        return _auto_result("BLOCKED", "unknown_deploy_class")
    configured = auto["capabilities"][capability_id]["deploy_class"]
    if deploy_class != configured:
        return _auto_result("BLOCKED", "deploy_class_mismatch")
    if deploy_class == "NO_DEPLOY":
        return _auto_result("RECONCILE_ONLY", "no_deploy")
    if deploy_class in auto["owner_required_classes"]:
        return _auto_result("OWNER_REQUIRED", "sensitive_class")
    if not exact_sha_ci_success:
        return _auto_result("BLOCKED", "exact_sha_ci_missing")
    if not full_range_complete:
        return _auto_result("BLOCKED", "full_range_incomplete")
    if not stable_concurrency:
        return _auto_result("BLOCKED", "stable_concurrency_missing")
    if not helper_identity_matches:
        return _auto_result("BLOCKED", "helper_identity_mismatch")
    return _auto_result("SOURCE_ELIGIBLE_LIVE_STILL_DISABLED", "source_policy_pass")


def _auto_result(decision: str, reason: str) -> Mapping[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "automatic_mutation_allowed": False,
        "runtime_live_authority": False,
        "production_mutation_started": False,
    }


def evaluate_phase4_closure(
    contract: Mapping[str, Any],
    *,
    fresh_final_inventory: bool,
    runner_count: int,
    residual_runner_owner_acceptance: bool,
    all_required_capability_evidence_complete: bool,
) -> Mapping[str, Any]:
    validate_contract(contract)
    missing: list[str] = []
    if fresh_final_inventory is not True:
        missing.append("fresh_final_inventory_missing")
    if all_required_capability_evidence_complete is not True:
        missing.append("capability_replacement_or_canary_evidence_incomplete")
    if runner_count < 0:
        missing.append("runner_count_invalid")
    elif runner_count > 0 and residual_runner_owner_acceptance is not True:
        missing.append("runner_count_nonzero_without_owner_acceptance")
    return {
        "decision": "ELIGIBLE_FOR_EXPLICIT_OWNER_PHASE4_CLOSURE_DECISION" if not missing else "NOT_CLOSED",
        "missing": tuple(missing),
        "phase4_closed": False,
        "runtime_live_authority": False,
    }
