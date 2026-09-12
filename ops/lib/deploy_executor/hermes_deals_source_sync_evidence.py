from __future__ import annotations

import re
from typing import Any, Mapping

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REASON_RE = re.compile(r"^[A-Z0-9_]{1,96}$")

OPERATION_ID = "hermes-deals.source-sync.v1"
LIVE_GATE_ID = "hermes-deals.source-sync.sync.v1"
TARGET_ALIAS = "hermes-deals-source-sync"
POSTCONDITION = "HEAD_EQUALS_EXACT_TARGET_AND_CLEAN_MAIN_CHECKOUT"
ALLOWED_CI_MODES = frozenset({"EXACT_TARGET_SHA_CI", "TREE_EQUIVALENT_PR_HEAD_CI"})

PREFLIGHT_FIELDS = frozenset({
    "target_sha", "current_head_sha", "repository", "repository_id", "remote_url",
    "checkout_identity", "branch", "ref", "upstream", "worktree", "clean",
    "merged_same_repository_pr", "target_reachable_from_current_main", "ci_mode",
    "ci_proof_valid", "workflow_blob", "target_is_fast_forward_descendant",
})
POSTCONDITION_FIELDS = frozenset({
    "head_after", "repository", "repository_id", "remote_url", "checkout_identity",
    "branch", "ref", "upstream", "clean",
})
RECEIPT_FIELDS = frozenset({
    "schema", "status", "reason_code", "operation_id", "future_live_gate_id",
    "target_alias", "source_repository", "source_repository_id", "rpi5_source_sha",
    "target_sha", "authorization_issue_number", "request_body_sha256", "head_before",
    "head_after", "preflight_decision", "fast_forward_proven", "mutation_capable_entry",
    "network_fetch_attempted", "source_checkout_head_changed", "postcondition_result",
    "production_deploy_performed", "database_write_performed", "review_write_performed",
    "publication_write_performed", "evidence_store_write_performed", "scheduler_change_performed",
    "systemd_change_performed", "docker_mutation_performed", "network_mutation_performed",
    "package_mutation_performed", "user_group_acl_mutation_performed",
    "credential_permission_mutation_performed", "runner_settings_mutation_performed",
    "protected_runtime_inspection_performed", "sanitized", "runtime_observation",
})
FORBIDDEN_MUTATION_FIELDS = (
    "production_deploy_performed", "database_write_performed", "review_write_performed",
    "publication_write_performed", "evidence_store_write_performed", "scheduler_change_performed",
    "systemd_change_performed", "docker_mutation_performed", "network_mutation_performed",
    "package_mutation_performed", "user_group_acl_mutation_performed",
    "credential_permission_mutation_performed", "runner_settings_mutation_performed",
    "protected_runtime_inspection_performed",
)

class HermesDealsSourceSyncEvidenceError(ValueError):
    pass


def _closed_fields(payload: Mapping[str, Any], expected: frozenset[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    actual = set(payload)
    return tuple(sorted(expected - actual)), tuple(sorted(actual - expected))


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def validate_contract(contract: Mapping[str, Any]) -> None:
    expected_top = {"schema_version", "contract", "implementation_issue", "status", "source_anchors", "operation", "fixed_identity", "preflight", "postcondition", "canary_evidence", "future_owner_gate", "replay_failure", "job_boundary"}
    if set(contract) != expected_top:
        raise HermesDealsSourceSyncEvidenceError("top-level contract field drift")
    if contract["schema_version"] != 1 or contract["implementation_issue"] != 490:
        raise HermesDealsSourceSyncEvidenceError("contract identity mismatch")
    if contract["status"] != "SOURCE_READY_LIVE_LATER":
        raise HermesDealsSourceSyncEvidenceError("contract status mismatch")
    operation = contract["operation"]
    if operation != {"operation_id": OPERATION_ID, "future_live_gate_id": LIVE_GATE_ID, "target_alias": TARGET_ALIAS, "authorization_class": "STRICT", "global_execution_enabled": False, "external_apply_entrypoint_enabled": False, "rollback_policy": "NONE"}:
        raise HermesDealsSourceSyncEvidenceError("operation identity drift")
    fixed = contract["fixed_identity"]
    expected_fixed = {"checkout_identity": "HERMES_DEALS_CANONICAL_SOURCE_CHECKOUT", "path": "RPi5_CHECKOUT_PARENT/hermes-deals", "repository": "rozkalnsandris/hermes-deals", "repository_id": 1317143994, "remote_url": "https://github.com/rozkalnsandris/hermes-deals.git", "branch": "main", "ref": "refs/heads/main", "upstream": "origin/main", "caller_selectable": False}
    if fixed != expected_fixed:
        raise HermesDealsSourceSyncEvidenceError("fixed identity drift")
    if set(contract["preflight"]["required_fields"]) != PREFLIGHT_FIELDS:
        raise HermesDealsSourceSyncEvidenceError("preflight field contract drift")
    if set(contract["postcondition"]["required_fields"]) != POSTCONDITION_FIELDS:
        raise HermesDealsSourceSyncEvidenceError("postcondition field contract drift")
    if set(contract["canary_evidence"]["required_fields"]) != RECEIPT_FIELDS:
        raise HermesDealsSourceSyncEvidenceError("receipt field contract drift")
    if contract["postcondition"]["success_predicate"] != POSTCONDITION:
        raise HermesDealsSourceSyncEvidenceError("postcondition identity drift")
    if contract["future_owner_gate"]["allowed_mutation"] != "FAST_FORWARD_TO_EXACT_AUTHORIZED_SHA_ONLY":
        raise HermesDealsSourceSyncEvidenceError("future mutation boundary drift")
    if contract["future_owner_gate"]["max_operations"] != 1 or contract["future_owner_gate"]["rollback_policy"] != "NONE":
        raise HermesDealsSourceSyncEvidenceError("future mutation budget drift")
    if contract["job_boundary"]["runtime_live_authority"] is not False or contract["job_boundary"]["source_sync_executed"] is not False:
        raise HermesDealsSourceSyncEvidenceError("Job 7 live boundary widened")


def evaluate_preflight(contract: Mapping[str, Any], authorized_target_sha: str, observed: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_contract(contract)
    missing, unexpected = _closed_fields(observed, PREFLIGHT_FIELDS)
    if missing or unexpected:
        return {"decision": "BLOCKED", "reason_codes": ("FIELD_DRIFT",), "missing": missing, "unexpected": unexpected, "source_sync_execution_allowed": False}
    reasons: list[str] = []
    if not _valid_sha(authorized_target_sha) or observed["target_sha"] != authorized_target_sha:
        reasons.append("TARGET_SHA_MISMATCH")
    if not _valid_sha(observed["current_head_sha"]):
        reasons.append("CURRENT_HEAD_INVALID")
    fixed = contract["fixed_identity"]
    checks = {
        "REPOSITORY_IDENTITY_DRIFT": observed["repository"] == fixed["repository"] and observed["repository_id"] == fixed["repository_id"],
        "REMOTE_IDENTITY_DRIFT": observed["remote_url"] == fixed["remote_url"],
        "CHECKOUT_IDENTITY_DRIFT": observed["checkout_identity"] == fixed["checkout_identity"],
        "BRANCH_REF_UPSTREAM_DRIFT": observed["branch"] == fixed["branch"] and observed["ref"] == fixed["ref"] and observed["upstream"] == fixed["upstream"],
        "NOT_A_WORKTREE": observed["worktree"] is True,
        "DIRTY_CHECKOUT": observed["clean"] is True,
        "MERGED_PR_PROVENANCE_MISSING": observed["merged_same_repository_pr"] is True,
        "TARGET_NOT_REACHABLE_FROM_MAIN": observed["target_reachable_from_current_main"] is True,
        "CI_PROOF_INVALID": observed["ci_mode"] in ALLOWED_CI_MODES and observed["ci_proof_valid"] is True,
        "WORKFLOW_BLOB_DRIFT": observed["workflow_blob"] == contract["source_anchors"]["workflow_blob"],
        "NON_FAST_FORWARD_TARGET": observed["target_is_fast_forward_descendant"] is True,
    }
    reasons.extend(code for code, ok in checks.items() if not ok)
    return {"decision": "PASS" if not reasons else "BLOCKED", "reason_codes": tuple(sorted(reasons)), "missing": (), "unexpected": (), "head_before": observed["current_head_sha"], "authorized_target_sha": authorized_target_sha, "fast_forward_proven": observed["target_is_fast_forward_descendant"] is True and not reasons, "source_sync_execution_allowed": False}


def evaluate_postcondition(contract: Mapping[str, Any], authorized_target_sha: str, observed: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_contract(contract)
    missing, unexpected = _closed_fields(observed, POSTCONDITION_FIELDS)
    if missing or unexpected:
        return {"decision": "BLOCKED", "reason_codes": ("FIELD_DRIFT",), "missing": missing, "unexpected": unexpected, "predicate": POSTCONDITION}
    fixed = contract["fixed_identity"]
    reasons: list[str] = []
    if not _valid_sha(authorized_target_sha) or observed["head_after"] != authorized_target_sha:
        reasons.append("HEAD_NOT_EXACT_TARGET")
    if observed["clean"] is not True:
        reasons.append("CHECKOUT_NOT_CLEAN")
    if observed["repository"] != fixed["repository"] or observed["repository_id"] != fixed["repository_id"]:
        reasons.append("REPOSITORY_IDENTITY_DRIFT")
    if observed["remote_url"] != fixed["remote_url"]:
        reasons.append("REMOTE_IDENTITY_DRIFT")
    if observed["checkout_identity"] != fixed["checkout_identity"]:
        reasons.append("CHECKOUT_IDENTITY_DRIFT")
    if observed["branch"] != fixed["branch"] or observed["ref"] != fixed["ref"] or observed["upstream"] != fixed["upstream"]:
        reasons.append("BRANCH_REF_UPSTREAM_DRIFT")
    return {"decision": "PASS" if not reasons else "BLOCKED", "reason_codes": tuple(sorted(reasons)), "missing": (), "unexpected": (), "predicate": POSTCONDITION, "source_sync_execution_allowed": False}


def validate_canary_receipt(contract: Mapping[str, Any], authorized_rpi5_sha: str, authorized_target_sha: str, receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_contract(contract)
    missing, unexpected = _closed_fields(receipt, RECEIPT_FIELDS)
    if missing or unexpected:
        return {"decision": "BLOCKED", "reason": "FIELD_DRIFT", "missing": missing, "unexpected": unexpected}
    if not _valid_sha(authorized_rpi5_sha) or receipt["rpi5_source_sha"] != authorized_rpi5_sha:
        return {"decision": "BLOCKED", "reason": "RPI5_SOURCE_SHA_MISMATCH"}
    if not _valid_sha(authorized_target_sha) or receipt["target_sha"] != authorized_target_sha:
        return {"decision": "BLOCKED", "reason": "TARGET_SHA_MISMATCH"}
    fixed = contract["fixed_identity"]
    identity = (receipt["schema"] == contract["canary_evidence"]["schema"] and receipt["operation_id"] == OPERATION_ID and receipt["future_live_gate_id"] == LIVE_GATE_ID and receipt["target_alias"] == TARGET_ALIAS and receipt["source_repository"] == fixed["repository"] and receipt["source_repository_id"] == fixed["repository_id"])
    if not identity:
        return {"decision": "BLOCKED", "reason": "IDENTITY_DRIFT"}
    if receipt["status"] not in contract["canary_evidence"]["allowed_status"]:
        return {"decision": "BLOCKED", "reason": "STATUS_INVALID"}
    reason = receipt["reason_code"]
    if receipt["status"] == "PASS":
        if reason is not None:
            return {"decision": "BLOCKED", "reason": "PASS_REASON_MUST_BE_NULL"}
    elif not isinstance(reason, str) or REASON_RE.fullmatch(reason) is None:
        return {"decision": "BLOCKED", "reason": "REASON_CODE_INVALID"}
    if type(receipt["authorization_issue_number"]) is not int or receipt["authorization_issue_number"] <= 0:
        return {"decision": "BLOCKED", "reason": "AUTHORIZATION_ISSUE_INVALID"}
    if not isinstance(receipt["request_body_sha256"], str) or SHA256_RE.fullmatch(receipt["request_body_sha256"]) is None:
        return {"decision": "BLOCKED", "reason": "REQUEST_HASH_INVALID"}
    if not _valid_sha(receipt["head_before"]) or not _valid_sha(receipt["head_after"]):
        return {"decision": "BLOCKED", "reason": "HEAD_SHA_INVALID"}
    if any(receipt[field] is not False for field in FORBIDDEN_MUTATION_FIELDS):
        return {"decision": "BLOCKED", "reason": "FORBIDDEN_MUTATION_ATTESTED"}
    if receipt["sanitized"] is not True or receipt["runtime_observation"] is not True:
        return {"decision": "BLOCKED", "reason": "UNSANITIZED_OR_SYNTHETIC"}
    if receipt["status"] == "PASS":
        required_pass = (receipt["preflight_decision"] == "PASS" and receipt["fast_forward_proven"] is True and receipt["mutation_capable_entry"] is True and receipt["network_fetch_attempted"] is True and receipt["source_checkout_head_changed"] is True and receipt["head_after"] == authorized_target_sha and receipt["postcondition_result"] == POSTCONDITION)
        if not required_pass:
            return {"decision": "BLOCKED", "reason": "PASS_POSTCONDITION_MISMATCH"}
        return {"decision": "VALID_PASS", "reason": None}
    if receipt["postcondition_result"] not in {POSTCONDITION, "NOT_EVALUATED", "BLOCKED"}:
        return {"decision": "BLOCKED", "reason": "BLOCKED_POSTCONDITION_INVALID"}
    return {"decision": "VALID_BLOCKED", "reason": receipt["reason_code"]}
