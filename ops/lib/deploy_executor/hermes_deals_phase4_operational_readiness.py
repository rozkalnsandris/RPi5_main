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


class HermesDealsOperationalReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class SelectedAuditPreflightEvidence:
    source_sha: str
    exact_sha_ci_success: bool
    helper_identity_matches: bool
    registration_identity_matches: bool
    execution_identity_matches: bool
    helper_owner_mode_matches: bool
    registration_owner_mode_matches: bool
    expected_inert_state: bool


@dataclass(frozen=True)
class RetirementEvidence:
    source_replacement_ready: bool
    host_wiring_proven: bool
    installed_identity_verified: bool
    genuine_canary_or_e2e_proven: bool
    fallback_dependency_removed: bool
    fresh_final_runner_inventory: bool


def validate_contract(contract: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "contract",
        "implementation_issue",
        "status",
        "source_anchors",
        "predecessor",
        "jobs",
        "residual_capabilities",
        "selected_audit_capability",
        "host_wiring_source_contract",
        "runtime_preflight_operator",
        "genuine_canary_package",
        "source_sync_operational_readiness",
        "auto_live_a5_bridge",
        "runtime_evidence_ledger",
        "runner_retirement_graph",
        "netto_identity_guard",
        "operational_handoff",
        "mutation",
    }
    if set(contract) != expected:
        raise HermesDealsOperationalReadinessError("top-level contract field drift")
    if contract["schema_version"] != 1 or contract["implementation_issue"] != 470:
        raise HermesDealsOperationalReadinessError("contract identity mismatch")
    if contract["status"] != "SOURCE_ONLY_OPERATIONAL_READINESS_READY_LIVE_DISABLED":
        raise HermesDealsOperationalReadinessError("contract status mismatch")

    anchors = contract["source_anchors"]
    for field in ("rpi5_main_activation_sha", "predecessor_merge_sha", "hermes_deals_main_sha"):
        if SHA_RE.fullmatch(str(anchors[field])) is None:
            raise HermesDealsOperationalReadinessError(f"invalid exact SHA: {field}")
    if anchors["source_runtime_state_inferred"] is not False:
        raise HermesDealsOperationalReadinessError("source must not infer runtime state")
    if anchors["phase4_current_work_item"] != "HERMES_POSTCANARY_INCREMENTAL_CAPABILITY_MIGRATION_SOURCE":
        raise HermesDealsOperationalReadinessError("Phase 4 lane drift")

    predecessor = contract["predecessor"]
    if predecessor["canonical_pr"] != 469:
        raise HermesDealsOperationalReadinessError("predecessor PR drift")
    if SHA_RE.fullmatch(predecessor["canonical_pr_head"]) is None:
        raise HermesDealsOperationalReadinessError("predecessor head is not exact")
    if predecessor["terminal_exact_main_ci_success"] is not True:
        raise HermesDealsOperationalReadinessError("predecessor merged-main CI is not successful")
    if len(predecessor["terminal_results"]) != 10:
        raise HermesDealsOperationalReadinessError("predecessor results incomplete")

    jobs = contract["jobs"]
    if type(jobs) is not list or [row.get("job") for row in jobs] != list(range(1, 11)):
        raise HermesDealsOperationalReadinessError("jobs must be exactly 1..10")
    if any(row.get("result") not in ALLOWED_JOB_RESULTS for row in jobs):
        raise HermesDealsOperationalReadinessError("unsupported job result")

    capabilities = contract["residual_capabilities"]
    expected_ids = ["origin_path_audit", "approved_audit_command", "source_sync", "production_release"]
    if [row.get("capability_id") for row in capabilities] != expected_ids:
        raise HermesDealsOperationalReadinessError("residual capability set drift")
    for row in capabilities:
        if SHA_RE.fullmatch(row["workflow_blob"]) is None:
            raise HermesDealsOperationalReadinessError("workflow blob must be exact")
        if row["source_replacement_ready"] is not True:
            raise HermesDealsOperationalReadinessError("source replacement not ready")
        if row["current_runtime_state_asserted"] is not False:
            raise HermesDealsOperationalReadinessError("source contract asserted runtime state")

    selected = contract["selected_audit_capability"]
    if selected["capability_id"] != "approved_audit_command" or selected["selected_audit"] != "runner-smoke":
        raise HermesDealsOperationalReadinessError("lowest-risk selected capability drift")
    if selected["future_operation_id"] != "hermes-deals.runner-smoke-audit.v1":
        raise HermesDealsOperationalReadinessError("selected operation drift")
    if selected["read_only"] is not True:
        raise HermesDealsOperationalReadinessError("selected capability is not read-only")
    if selected["legacy_path_runner_coupled"] is not True or selected["legacy_path_live_reuse_allowed"] is not False:
        raise HermesDealsOperationalReadinessError("legacy runner coupling was hidden or reused")
    if selected["runner_independent_design_required"] is not True:
        raise HermesDealsOperationalReadinessError("runner-independent design requirement missing")
    if selected["caller_command_path_argv_environment_authority"] is not False:
        raise HermesDealsOperationalReadinessError("caller authority widened")
    if selected["generic_privileged_execution"] is not False:
        raise HermesDealsOperationalReadinessError("generic privileged execution enabled")

    wiring = contract["host_wiring_source_contract"]
    identity = wiring["execution_identity"]
    if identity != {
        "account": "hermes-deals-audit-canary",
        "login_shell": "/usr/sbin/nologin",
        "root": False,
        "docker_group": False,
        "supplementary_groups": [],
        "caller_selectable": False,
    }:
        raise HermesDealsOperationalReadinessError("selected execution identity drift")
    if wiring["privileged_boundary_input"] != ["authorization_issue_number"]:
        raise HermesDealsOperationalReadinessError("privileged boundary input widened")
    if wiring["no_overwrite"] is not True or wiring["nofollow_required"] is not True:
        raise HermesDealsOperationalReadinessError("safe installation primitive weakened")
    for field in (
        "caller_command_path_argv_environment_authority",
        "generic_sudo_or_root_shell",
        "runtime_installation_performed",
        "credential_read_or_change_performed",
        "service_or_runner_mutation_performed",
    ):
        if wiring[field] is not False:
            raise HermesDealsOperationalReadinessError(f"host-wiring boundary widened: {field}")

    preflight = contract["runtime_preflight_operator"]
    if preflight["default_read_only"] is not True:
        raise HermesDealsOperationalReadinessError("preflight is not default read-only")
    for field in (
        "protected_credential_reads_enabled",
        "helper_execution_enabled",
        "host_writes_enabled",
        "live_authorization_consumption_enabled",
        "runtime_observation_performed_by_bundle",
    ):
        if preflight[field] is not False:
            raise HermesDealsOperationalReadinessError(f"preflight boundary widened: {field}")

    canary = contract["genuine_canary_package"]
    if canary["authorization_protocol"] != "RPi5_main#236":
        raise HermesDealsOperationalReadinessError("canary authorization protocol drift")
    if canary["owner_numeric_id_required"] != OWNER_NUMERIC_ID:
        raise HermesDealsOperationalReadinessError("canary owner identity drift")
    if canary["canonical_body_hash_required"] is not True or canary["identical_body_refetch_before_helper"] is not True:
        raise HermesDealsOperationalReadinessError("canary body-hash boundary weakened")
    if canary["durable_one_shot_replay_required"] is not True or canary["consume_immediately_before_first_helper_invocation"] is not True:
        raise HermesDealsOperationalReadinessError("canary replay boundary weakened")
    for field in (
        "production_mutation_started",
        "database_write_performed",
        "deployment_performed",
        "runner_mutation_performed",
        "credential_read_performed",
        "automatic_retry_after_helper_start",
        "automatic_cleanup_after_helper_start",
        "automatic_rollback_after_helper_start",
        "ready_queue_created",
        "live_auth_created",
        "genuine_canary_performed",
    ):
        if canary[field] is not False:
            raise HermesDealsOperationalReadinessError(f"source canary package fabricated authority/evidence: {field}")

    sync = contract["source_sync_operational_readiness"]
    if sync["canonical_checkout_identity"] != "HERMES_DEALS_CANONICAL_SOURCE_CHECKOUT":
        raise HermesDealsOperationalReadinessError("source-sync checkout identity drift")
    if sync["allowed_future_mutation"] != "FAST_FORWARD_TO_EXACT_MERGED_REACHABLE_SHA":
        raise HermesDealsOperationalReadinessError("source-sync mutation class drift")
    if sync["caller_selectable_checkout_path"] is not False:
        raise HermesDealsOperationalReadinessError("source-sync path became caller-selectable")
    if sync["generic_git_subcommand_authority"] is not False or sync["generic_checkout_path_authority"] is not False:
        raise HermesDealsOperationalReadinessError("source-sync generic authority widened")
    if sync["runtime_execution_enabled"] is not False or sync["host_mutation_performed"] is not False:
        raise HermesDealsOperationalReadinessError("source-sync runtime mutation enabled")

    bridge = contract["auto_live_a5_bridge"]
    if bridge["registration_state"] != "SOURCE_DESCRIPTOR_ONLY_NOT_ACTIVE":
        raise HermesDealsOperationalReadinessError("Auto-Live source descriptor unexpectedly active")
    if bridge["eligible_classes"] != ["AUTO_DEPLOY_SAFE"]:
        raise HermesDealsOperationalReadinessError("Auto-Live eligible class widened")
    if bridge["unknown_or_ambiguous_result"] != "BLOCKED":
        raise HermesDealsOperationalReadinessError("Auto-Live unknown state must fail closed")
    for field in (
        "global_registry_mutated",
        "manifest_index_mutated",
        "automatic_mutation_enabled",
        "post_mutation_automatic_retry",
        "post_mutation_automatic_cleanup",
        "post_mutation_automatic_rollback",
        "execution_enabled",
    ):
        if bridge[field] is not False:
            raise HermesDealsOperationalReadinessError(f"Auto-Live source bridge activated: {field}")

    ledger = contract["runtime_evidence_ledger"]
    if ledger["source_defines_schema_only"] is not True or ledger["current_runtime_state_asserted"] is not False:
        raise HermesDealsOperationalReadinessError("runtime evidence ledger crossed source/runtime boundary")

    graph = contract["runner_retirement_graph"]
    if graph["unknown_or_missing_evidence_result"] != "NOT_ELIGIBLE":
        raise HermesDealsOperationalReadinessError("retirement graph must fail closed")
    if graph["current_decision"] != "NOT_ELIGIBLE":
        raise HermesDealsOperationalReadinessError("runner retirement was prematurely advanced")
    if graph["runner_deregistration_authorized"] is not False or graph["repository_settings_mutation_authorized"] is not False:
        raise HermesDealsOperationalReadinessError("source graph authorized runner/settings mutation")

    netto = contract["netto_identity_guard"]
    if netto["authoritative_issue"] != 425 or netto["model"] != "DEDICATED_NON_LOGIN_NON_ROOT_NO_DOCKER":
        raise HermesDealsOperationalReadinessError("Netto #425 identity guard regressed")
    if netto["supplementary_groups"] != [] or "docker" not in netto["forbidden_groups"]:
        raise HermesDealsOperationalReadinessError("Netto group boundary regressed")
    if {"root", "andris", "github-runner"} - set(netto["forbidden_accounts"]):
        raise HermesDealsOperationalReadinessError("Netto forbidden account set regressed")

    handoff = contract["operational_handoff"]
    if handoff["phase4_state"] != "NOT_CLOSED_LIVE_EVIDENCE_REQUIRED":
        raise HermesDealsOperationalReadinessError("Phase 4 closure state drift")
    if handoff["source_evidence_alone_can_close_phase4"] is not False:
        raise HermesDealsOperationalReadinessError("source evidence cannot close Phase 4")
    if handoff["merge_authorizes_live"] is not False or handoff["runner_retirement_eligible"] is not False:
        raise HermesDealsOperationalReadinessError("handoff widened merge/LIVE authority")

    if any(value is not False for value in contract["mutation"].values()):
        raise HermesDealsOperationalReadinessError("runtime mutation flag enabled in source bundle")


def evaluate_selected_audit_preflight(
    contract: Mapping[str, Any], evidence: SelectedAuditPreflightEvidence
) -> Mapping[str, Any]:
    validate_contract(contract)
    missing: list[str] = []
    expected_sha = contract["source_anchors"]["hermes_deals_main_sha"]
    if SHA_RE.fullmatch(evidence.source_sha) is None:
        missing.append("exact_source_sha_invalid")
    elif evidence.source_sha != expected_sha:
        missing.append("source_sha_mismatch")
    checks = {
        "exact_sha_ci_missing": evidence.exact_sha_ci_success,
        "helper_identity_unproven": evidence.helper_identity_matches,
        "registration_identity_unproven": evidence.registration_identity_matches,
        "execution_identity_unproven": evidence.execution_identity_matches,
        "helper_owner_mode_unproven": evidence.helper_owner_mode_matches,
        "registration_owner_mode_unproven": evidence.registration_owner_mode_matches,
        "inert_state_unproven": evidence.expected_inert_state,
    }
    missing.extend(name for name, passed in checks.items() if passed is not True)
    return {
        "decision": "SOURCE_PREFLIGHT_READY" if not missing else "BLOCKED",
        "missing": tuple(missing),
        "helper_execution_allowed": False,
        "host_write_allowed": False,
        "protected_credential_read_allowed": False,
        "live_authorization_consumed": False,
    }


def evaluate_runner_retirement(
    contract: Mapping[str, Any],
    runner_label: str,
    evidence_by_capability: Mapping[str, RetirementEvidence],
) -> Mapping[str, Any]:
    validate_contract(contract)
    graph = contract["runner_retirement_graph"]
    capabilities = graph["runner_labels"].get(runner_label)
    if capabilities is None:
        return {
            "decision": "NOT_ELIGIBLE",
            "missing": ("unknown_runner_label",),
            "runner_deregistration_authorized": False,
        }
    missing: list[str] = []
    required = contract["runtime_evidence_ledger"]["evidence_slots"]
    for capability_id in capabilities:
        evidence = evidence_by_capability.get(capability_id)
        if evidence is None:
            missing.append(f"{capability_id}:missing_evidence")
            continue
        for field in required:
            if getattr(evidence, field) is not True:
                missing.append(f"{capability_id}:{field}")
    return {
        "decision": "ELIGIBLE_FOR_SEPARATE_OWNER_RETIREMENT_GATE" if not missing else "NOT_ELIGIBLE",
        "runner_label": runner_label,
        "missing": tuple(missing),
        "runner_deregistration_authorized": False,
        "repository_settings_mutation_authorized": False,
    }


def evaluate_auto_live_a5(
    contract: Mapping[str, Any],
    deploy_class: str,
    *,
    exact_sha_ci_success: bool,
    full_range_complete: bool,
    helper_identity_matches: bool,
    production_baseline_matches: bool,
) -> Mapping[str, Any]:
    validate_contract(contract)
    bridge = contract["auto_live_a5_bridge"]
    if deploy_class not in ALLOWED_DEPLOY_CLASSES:
        return _auto_result("BLOCKED", "unknown_deploy_class")
    if deploy_class == "NO_DEPLOY":
        return _auto_result("RECONCILE_ONLY", "no_deploy")
    if deploy_class in bridge["owner_required_classes"]:
        return _auto_result("OWNER_REQUIRED", "sensitive_class")
    if deploy_class not in bridge["eligible_classes"]:
        return _auto_result("BLOCKED", "class_not_auto_live_eligible")
    if not exact_sha_ci_success:
        return _auto_result("BLOCKED", "exact_sha_ci_missing")
    if not full_range_complete:
        return _auto_result("BLOCKED", "full_range_incomplete")
    if not helper_identity_matches:
        return _auto_result("BLOCKED", "helper_identity_mismatch")
    if not production_baseline_matches:
        return _auto_result("BLOCKED", "production_baseline_mismatch")
    return _auto_result("SOURCE_DESCRIPTOR_ELIGIBLE_EXECUTION_DISABLED", "source_policy_pass")


def _auto_result(decision: str, reason: str) -> Mapping[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "automatic_mutation_allowed": False,
        "runtime_live_authority": False,
        "production_mutation_started": False,
    }


def evaluate_phase4_handoff(
    contract: Mapping[str, Any],
    *,
    selected_capability_host_wiring_proven: bool,
    selected_capability_canary_proven: bool,
    all_residual_capabilities_proven: bool,
    fresh_final_runner_inventory: bool,
) -> Mapping[str, Any]:
    validate_contract(contract)
    complete = all(
        (
            selected_capability_host_wiring_proven,
            selected_capability_canary_proven,
            all_residual_capabilities_proven,
            fresh_final_runner_inventory,
        )
    )
    return {
        "decision": (
            "ELIGIBLE_FOR_EXPLICIT_OWNER_PHASE4_CLOSURE_DECISION"
            if complete
            else "NOT_CLOSED_LIVE_EVIDENCE_REQUIRED"
        ),
        "phase4_closed": False,
        "runtime_live_authority": False,
        "runner_retirement_authorized": False,
    }
