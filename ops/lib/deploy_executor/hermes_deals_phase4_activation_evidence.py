from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_JOB_RESULTS = frozenset(
    {"DONE", "SOURCE_READY_LIVE_LATER", "NO_OP_ALREADY_RECONCILED"}
)
REQUIRED_RUNTIME_SLOTS = (
    "host_wiring_proven",
    "installed_identity_verified",
    "genuine_canary_or_e2e_proven",
    "fallback_dependency_removed",
    "fresh_final_runner_inventory",
)


class HermesDealsPhase4ActivationEvidenceError(ValueError):
    pass


def _require_sha(value: Any, field: str) -> str:
    text = str(value)
    if SHA_RE.fullmatch(text) is None:
        raise HermesDealsPhase4ActivationEvidenceError(f"invalid exact SHA: {field}")
    return text


def _require_sha256(value: Any, field: str) -> str:
    text = str(value)
    if SHA256_RE.fullmatch(text) is None:
        raise HermesDealsPhase4ActivationEvidenceError(f"invalid SHA-256: {field}")
    return text


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise HermesDealsPhase4ActivationEvidenceError("invalid observed_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise HermesDealsPhase4ActivationEvidenceError("invalid observed_at") from error
    if parsed.tzinfo is None:
        raise HermesDealsPhase4ActivationEvidenceError("observed_at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def validate_contract(contract: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "contract",
        "implementation_issue",
        "status",
        "source_anchors",
        "jobs",
        "predecessor_gate",
        "capability_provenance",
        "runner_smoke_source_package",
        "runner_smoke_install_plan",
        "runner_smoke_verifier",
        "runner_smoke_authorization",
        "runner_smoke_receipt",
        "source_sync_operation",
        "source_sync_evidence",
        "auto_live_a5_registration",
        "runtime_evidence_ingestion",
        "runner_retirement",
        "activation_handoff",
        "mutation",
    }
    if set(contract) != expected:
        raise HermesDealsPhase4ActivationEvidenceError("top-level contract field drift")
    if contract["schema_version"] != 1 or contract["implementation_issue"] != 472:
        raise HermesDealsPhase4ActivationEvidenceError("contract identity mismatch")
    if contract["status"] != "SOURCE_ONLY_ACTIVATION_EVIDENCE_READY_LIVE_DISABLED":
        raise HermesDealsPhase4ActivationEvidenceError("contract status mismatch")

    anchors = contract["source_anchors"]
    for field in ("rpi5_main_activation_sha", "predecessor_merge_sha", "hermes_deals_main_sha"):
        _require_sha(anchors[field], field)
    if anchors["predecessor_issue"] != 470:
        raise HermesDealsPhase4ActivationEvidenceError("predecessor issue drift")
    if anchors["predecessor_terminal_receipt_comment"] != 5638466496:
        raise HermesDealsPhase4ActivationEvidenceError("predecessor receipt drift")
    if anchors["source_runtime_state_inferred"] is not False:
        raise HermesDealsPhase4ActivationEvidenceError("source inferred runtime state")

    jobs = contract["jobs"]
    if not isinstance(jobs, list) or [row.get("job") for row in jobs] != list(range(1, 11)):
        raise HermesDealsPhase4ActivationEvidenceError("jobs must be exactly 1..10")
    if any(row.get("result") not in ALLOWED_JOB_RESULTS for row in jobs):
        raise HermesDealsPhase4ActivationEvidenceError("unsupported terminal source result")

    predecessor = contract["predecessor_gate"]
    if predecessor != {
        "required_issue": 470,
        "required_terminal_receipt_comment": 5638466496,
        "required_merge_sha": "6a1d17614e0dc270de75af0f5a11daa7bb3f6ffb",
        "required_merged_main_source_checks": 6,
        "required_merged_main_source_checks_conclusion": "SUCCESS",
        "activation_receipt_comment": 5638880694,
        "activation_receipt_schema": "rozkalns.auto-run-full-authorization.v2",
    }:
        raise HermesDealsPhase4ActivationEvidenceError("predecessor successor-gate drift")

    provenance = contract["capability_provenance"]
    if provenance["source_repository"] != "rozkalnsandris/hermes-deals":
        raise HermesDealsPhase4ActivationEvidenceError("Hermes repository identity drift")
    if provenance["source_sha"] != anchors["hermes_deals_main_sha"]:
        raise HermesDealsPhase4ActivationEvidenceError("Hermes source anchor drift")
    exact_ci = provenance["exact_sha_ci"]
    if exact_ci != {
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_blob": "89059e310ab3270001daef43fd8f22a38b258c99",
        "workflow_name": "Hermes Deals CI checks",
        "required_gate": "FAST-LANE Merge Gate",
        "required_conclusion": "success",
    }:
        raise HermesDealsPhase4ActivationEvidenceError("exact-SHA CI identity drift")

    capabilities = provenance["capabilities"]
    if set(capabilities) != {
        "origin_path_audit",
        "approved_audit_command",
        "source_sync",
        "production_release",
    }:
        raise HermesDealsPhase4ActivationEvidenceError("capability set drift")
    expected_blobs = {
        "origin_path_audit": ("workflow_blob", "99a18c5f669e7880a8a8288c3f964285df87ae22"),
        "approved_audit_command": ("workflow_blob", "c9107e7597ff3ce1214cb32fb740346fa9d190aa"),
        "source_sync": ("workflow_blob", "b2f4eee1d1c503cf0c47b6099e748d6e6fd6d560"),
        "production_release": ("workflow_blob", "c45e14765881a82eb7e3d1bc3fe2f4f50cb0c38f"),
    }
    for capability_id, (field, expected_blob) in expected_blobs.items():
        if capabilities[capability_id][field] != expected_blob:
            raise HermesDealsPhase4ActivationEvidenceError(
                f"capability provenance drift: {capability_id}"
            )
    if provenance["removed_or_superseded_paths"] != []:
        raise HermesDealsPhase4ActivationEvidenceError("unexpected removed/superseded path claim")

    smoke = contract["runner_smoke_source_package"]
    if smoke["operation_id"] != "hermes-deals.runner-smoke-audit.v1":
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke operation drift")
    if smoke["target_alias"] != "hermes-deals-runner-smoke-audit":
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke target drift")
    if smoke["fixed_source_sha"] != anchors["hermes_deals_main_sha"]:
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke source drift")
    if smoke["execution_identity"] != {
        "account": "hermes-deals-audit-canary",
        "login_shell": "/usr/sbin/nologin",
        "root": False,
        "docker_group": False,
        "supplementary_groups": [],
        "caller_selectable": False,
    }:
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke identity widened")
    for field in (
        "no_overwrite",
        "nofollow_required",
        "regular_file_required",
        "exact_content_identity_required",
    ):
        if smoke[field] is not True:
            raise HermesDealsPhase4ActivationEvidenceError(f"runner-smoke safety weakened: {field}")
    for field in (
        "caller_command_path_argv_environment_authority",
        "generic_sudo_or_root_shell",
        "legacy_generic_dispatcher_reuse_allowed",
        "runtime_installation_performed",
        "helper_execution_performed",
    ):
        if smoke[field] is not False:
            raise HermesDealsPhase4ActivationEvidenceError(f"runner-smoke boundary widened: {field}")
    if smoke["privileged_boundary_input"] != ["authorization_issue_number"]:
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke privileged input widened")

    install = contract["runner_smoke_install_plan"]
    if install["status"] != "SOURCE_PLAN_ONLY_APPLY_DISABLED":
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke install plan activated")
    for field in (
        "apply_entrypoint_present",
        "host_write_enabled",
        "chmod_or_chown_enabled",
        "user_or_group_mutation_enabled",
        "systemd_mutation_enabled",
        "protected_credential_read_enabled",
        "helper_execution_enabled",
        "live_authority_consumption_enabled",
    ):
        if install[field] is not False:
            raise HermesDealsPhase4ActivationEvidenceError(f"install plan mutation enabled: {field}")

    verifier = contract["runner_smoke_verifier"]
    if verifier["default_read_only"] is not True:
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke verifier is not read-only")
    if verifier["unknown_or_missing_decision"] != "BLOCKED":
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke verifier not fail-closed")
    if verifier["helper_execution_allowed"] is not False or verifier["host_write_allowed"] is not False:
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke verifier gained mutation authority")

    auth = contract["runner_smoke_authorization"]
    if auth["authorization_protocol"] != "RPi5_main#236" or auth["owner_numeric_id_required"] != 277435981:
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke authorization identity drift")
    for field in (
        "canonical_body_hash_required",
        "identical_body_refetch_before_helper",
        "short_ttl_required",
        "durable_one_shot_replay_required",
        "consume_immediately_before_first_helper_invocation",
        "merged_reachable_sha_required",
        "exact_sha_ci_required",
    ):
        if auth[field] is not True:
            raise HermesDealsPhase4ActivationEvidenceError(f"runner-smoke auth weakened: {field}")
    for field in ("ready_queue_created", "live_auth_created", "replay_consumed", "helper_invoked"):
        if auth[field] is not False:
            raise HermesDealsPhase4ActivationEvidenceError(f"synthetic authority/evidence created: {field}")

    receipt = contract["runner_smoke_receipt"]
    if receipt["schema"] != "rozkalns.hermes-deals.runner-smoke-canary-evidence.v1":
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke receipt schema drift")
    if receipt["allowed_status"] != ["PASS", "BLOCKED"] or receipt["synthetic_pass_allowed"] is not False:
        raise HermesDealsPhase4ActivationEvidenceError("runner-smoke receipt fail-closed policy drift")

    sync = contract["source_sync_operation"]
    if sync["operation_id"] != "hermes-deals.source-sync.v1":
        raise HermesDealsPhase4ActivationEvidenceError("source-sync operation drift")
    if sync["canonical_checkout_identity"] != "HERMES_DEALS_CANONICAL_SOURCE_CHECKOUT":
        raise HermesDealsPhase4ActivationEvidenceError("source-sync checkout identity drift")
    if sync["fixed_checkout_path"] != "/home/andris/hermes-deals":
        raise HermesDealsPhase4ActivationEvidenceError("source-sync fixed path drift")
    if sync["allowed_future_mutation"] != "FAST_FORWARD_TO_EXACT_MERGED_REACHABLE_SHA":
        raise HermesDealsPhase4ActivationEvidenceError("source-sync mutation class widened")
    for field in (
        "caller_selectable_checkout_path",
        "generic_git_subcommand_authority",
        "caller_command_argv_environment_authority",
        "runtime_execution_enabled",
        "host_mutation_performed",
    ):
        if sync[field] is not False:
            raise HermesDealsPhase4ActivationEvidenceError(f"source-sync boundary widened: {field}")
    if sync["requires_separate_live_authorization"] is not True:
        raise HermesDealsPhase4ActivationEvidenceError("source-sync LIVE gate removed")

    sync_evidence = contract["source_sync_evidence"]
    if sync_evidence["deterministic_postcondition"] != "HEAD_EQUALS_EXACT_TARGET_AND_CLEAN_MAIN_CHECKOUT":
        raise HermesDealsPhase4ActivationEvidenceError("source-sync postcondition drift")
    for field in (
        "automatic_retry_after_mutation_start",
        "automatic_cleanup_after_mutation_start",
        "automatic_rollback_after_mutation_start",
        "alternate_mutation_path_after_mutation_start",
        "ready_queue_created",
        "live_auth_created",
        "source_sync_executed",
    ):
        if sync_evidence[field] is not False:
            raise HermesDealsPhase4ActivationEvidenceError(f"source-sync failure/authority policy widened: {field}")

    a5 = contract["auto_live_a5_registration"]
    if a5["status"] != "INACTIVE_SOURCE_REGISTRATION":
        raise HermesDealsPhase4ActivationEvidenceError("A5 source registration state drift")
    if a5["manifest_activation_state"] != "INACTIVE_SOURCE_ONLY":
        raise HermesDealsPhase4ActivationEvidenceError("A5 manifest activated")
    if a5["eligible_classes"] != ["AUTO_DEPLOY_SAFE"]:
        raise HermesDealsPhase4ActivationEvidenceError("A5 eligible class widened")
    if a5["owner_required_classes"] != ["MANUAL_ROLLOUT_REQUIRED", "DB_HOST_APPLY_REQUIRED"]:
        raise HermesDealsPhase4ActivationEvidenceError("A5 owner-required classes drift")
    if a5["unknown_or_ambiguous_result"] != "BLOCKED":
        raise HermesDealsPhase4ActivationEvidenceError("A5 unknown state not fail-closed")
    for field in (
        "global_execution_enabled",
        "automatic_mutation_enabled",
        "ordinary_auto_live_eligible_now",
        "production_deploy_performed",
    ):
        if a5[field] is not False:
            raise HermesDealsPhase4ActivationEvidenceError(f"A5 unexpectedly active: {field}")

    ingestion = contract["runtime_evidence_ingestion"]
    if tuple(ingestion["required_runtime_slots"]) != REQUIRED_RUNTIME_SLOTS:
        raise HermesDealsPhase4ActivationEvidenceError("runtime evidence slot set drift")
    if ingestion["source_defines_schema_only"] is not True or ingestion["current_runtime_state_asserted"] is not False:
        raise HermesDealsPhase4ActivationEvidenceError("runtime evidence boundary crossed")
    if ingestion["historical_receipt_satisfies_current_slot"] is not False:
        raise HermesDealsPhase4ActivationEvidenceError("historical evidence promoted to current")
    if ingestion["source_state_satisfies_runtime_slot"] is not False:
        raise HermesDealsPhase4ActivationEvidenceError("source state promoted to runtime evidence")
    if ingestion["unknown_or_missing_result"] != "NOT_ELIGIBLE":
        raise HermesDealsPhase4ActivationEvidenceError("runtime evidence missing-state policy drift")

    retirement = contract["runner_retirement"]
    if retirement["current_decision"] != "NOT_ELIGIBLE":
        raise HermesDealsPhase4ActivationEvidenceError("runner retirement prematurely advanced")
    if retirement["runner_deregistration_authorized"] is not False:
        raise HermesDealsPhase4ActivationEvidenceError("runner deregistration authorized")
    if retirement["repository_settings_mutation_authorized"] is not False:
        raise HermesDealsPhase4ActivationEvidenceError("repository settings mutation authorized")

    handoff = contract["activation_handoff"]
    if handoff["phase4_state"] != "NOT_CLOSED_LIVE_EVIDENCE_REQUIRED":
        raise HermesDealsPhase4ActivationEvidenceError("Phase 4 closure state drift")
    if handoff["first_future_live_gate"]["gate_id"] != "hermes-deals.runner-smoke-audit.install.v1":
        raise HermesDealsPhase4ActivationEvidenceError("first future LIVE gate drift")
    if handoff["first_future_live_gate"]["rollback_policy"] != "NONE":
        raise HermesDealsPhase4ActivationEvidenceError("first LIVE gate rollback policy drift")
    for field in ("merge_authorizes_live", "runtime_live_authority", "runner_retirement_authorized"):
        if handoff[field] is not False:
            raise HermesDealsPhase4ActivationEvidenceError(f"handoff authority widened: {field}")

    if any(value is not False for value in contract["mutation"].values()):
        raise HermesDealsPhase4ActivationEvidenceError("source bundle contains runtime mutation")


def evaluate_runner_smoke_preflight(contract: Mapping[str, Any], evidence: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_contract(contract)
    expected_fields = set(contract["runner_smoke_verifier"]["required_metadata"])
    if set(evidence) != expected_fields:
        return {
            "decision": "BLOCKED",
            "missing": tuple(sorted(expected_fields - set(evidence))),
            "unexpected": tuple(sorted(set(evidence) - expected_fields)),
            "helper_execution_allowed": False,
            "host_write_allowed": False,
            "runtime_live_authority": False,
        }
    missing: list[str] = []
    if evidence["source_sha"] != contract["source_anchors"]["hermes_deals_main_sha"]:
        missing.append("source_sha_mismatch")
    for field in expected_fields - {"source_sha"}:
        if evidence[field] is not True:
            missing.append(field)
    return {
        "decision": "SOURCE_PREFLIGHT_READY" if not missing else "BLOCKED",
        "missing": tuple(sorted(missing)),
        "unexpected": (),
        "helper_execution_allowed": False,
        "host_write_allowed": False,
        "runtime_live_authority": False,
    }


def evaluate_source_sync_preflight(contract: Mapping[str, Any], evidence: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_contract(contract)
    required = set(contract["source_sync_evidence"]["preflight_required"])
    if set(evidence) != required:
        return {
            "decision": "BLOCKED",
            "missing": tuple(sorted(required - set(evidence))),
            "unexpected": tuple(sorted(set(evidence) - required)),
            "source_sync_execution_allowed": False,
        }
    missing: list[str] = []
    _require_sha(evidence["exact_target_sha"], "exact_target_sha")
    for field in required - {"exact_target_sha"}:
        if evidence[field] is not True:
            missing.append(field)
    return {
        "decision": "SOURCE_PREFLIGHT_READY" if not missing else "BLOCKED",
        "missing": tuple(sorted(missing)),
        "unexpected": (),
        "source_sync_execution_allowed": False,
    }


def validate_runner_smoke_receipt(contract: Mapping[str, Any], receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_contract(contract)
    spec = contract["runner_smoke_receipt"]
    required = set(spec["required_fields"])
    if set(receipt) != required:
        return {"decision": "BLOCKED", "reason": "receipt_field_drift"}
    if receipt["schema"] != spec["schema"]:
        return {"decision": "BLOCKED", "reason": "receipt_schema_mismatch"}
    if receipt["status"] not in spec["allowed_status"]:
        return {"decision": "BLOCKED", "reason": "receipt_status_invalid"}
    if receipt["operation_id"] != contract["runner_smoke_source_package"]["operation_id"]:
        return {"decision": "BLOCKED", "reason": "operation_id_mismatch"}
    if receipt["target_alias"] != contract["runner_smoke_source_package"]["target_alias"]:
        return {"decision": "BLOCKED", "reason": "target_alias_mismatch"}
    if receipt["source_sha"] != contract["source_anchors"]["hermes_deals_main_sha"]:
        return {"decision": "BLOCKED", "reason": "source_sha_mismatch"}
    if type(receipt["authorization_issue_number"]) is not int or receipt["authorization_issue_number"] <= 0:
        return {"decision": "BLOCKED", "reason": "authorization_issue_invalid"}
    try:
        _require_sha256(receipt["request_body_sha256"], "request_body_sha256")
        _require_sha256(receipt["helper_identity_sha256"], "helper_identity_sha256")
        _require_sha256(receipt["registration_identity_sha256"], "registration_identity_sha256")
        _parse_time(receipt["observed_at"])
    except HermesDealsPhase4ActivationEvidenceError:
        return {"decision": "BLOCKED", "reason": "receipt_identity_or_time_invalid"}
    if receipt["sanitized"] is not True or receipt["runtime_observation"] is not True:
        return {"decision": "BLOCKED", "reason": "receipt_not_authentic_runtime_evidence"}
    return {
        "decision": "VALID_PASS" if receipt["status"] == "PASS" else "VALID_BLOCKED",
        "reason": "validated",
    }


def evaluate_runtime_evidence(
    contract: Mapping[str, Any],
    receipts: Iterable[Mapping[str, Any]],
    *,
    now: datetime,
) -> Mapping[str, Any]:
    validate_contract(contract)
    ingestion = contract["runtime_evidence_ingestion"]
    if now.tzinfo is None:
        raise HermesDealsPhase4ActivationEvidenceError("now must be timezone-aware")
    now_utc = now.astimezone(timezone.utc)
    capability_ids = set(ingestion["capabilities"])
    expected_schema = ingestion["receipt_schema"]
    expected_source_sha = contract["source_anchors"]["hermes_deals_main_sha"]
    max_age = int(ingestion["freshness_max_age_seconds"])
    required_fields = {
        "schema",
        "receipt_id",
        "capability_id",
        "source_sha",
        "slot",
        "observed_at",
        "status",
        "authentic",
        "sanitized",
        "current_runtime_observation",
        "source_generated",
        "conflict",
    }

    accepted: dict[tuple[str, str], str] = {}
    rejected: list[str] = []
    seen_receipt_ids: set[str] = set()
    for index, receipt in enumerate(receipts):
        prefix = f"receipt[{index}]"
        if set(receipt) != required_fields:
            rejected.append(f"{prefix}:field_drift")
            continue
        receipt_id = receipt["receipt_id"]
        if not isinstance(receipt_id, str) or not receipt_id or len(receipt_id) > 128:
            rejected.append(f"{prefix}:receipt_id_invalid")
            continue
        if receipt_id in seen_receipt_ids:
            rejected.append(f"{prefix}:duplicate_receipt_id")
            continue
        seen_receipt_ids.add(receipt_id)
        capability_id = receipt["capability_id"]
        slot = receipt["slot"]
        if receipt["schema"] != expected_schema:
            rejected.append(f"{receipt_id}:schema_mismatch")
            continue
        if capability_id not in capability_ids or slot not in REQUIRED_RUNTIME_SLOTS:
            rejected.append(f"{receipt_id}:unknown_capability_or_slot")
            continue
        if receipt["source_sha"] != expected_source_sha:
            rejected.append(f"{receipt_id}:source_sha_mismatch")
            continue
        try:
            observed_at = _parse_time(receipt["observed_at"])
        except HermesDealsPhase4ActivationEvidenceError:
            rejected.append(f"{receipt_id}:observed_at_invalid")
            continue
        age_seconds = (now_utc - observed_at).total_seconds()
        if age_seconds < 0 or age_seconds > max_age:
            rejected.append(f"{receipt_id}:stale_or_future")
            continue
        if receipt["status"] != "PASS":
            rejected.append(f"{receipt_id}:status_not_pass")
            continue
        if receipt["authentic"] is not True or receipt["sanitized"] is not True:
            rejected.append(f"{receipt_id}:authenticity_or_sanitization_missing")
            continue
        if receipt["current_runtime_observation"] is not True:
            rejected.append(f"{receipt_id}:not_current_runtime_observation")
            continue
        if receipt["source_generated"] is not False:
            rejected.append(f"{receipt_id}:source_generated_forbidden")
            continue
        if receipt["conflict"] is not False:
            rejected.append(f"{receipt_id}:conflict")
            continue
        key = (capability_id, slot)
        if key in accepted:
            rejected.append(f"{receipt_id}:duplicate_capability_slot")
            continue
        accepted[key] = receipt_id

    capability_decisions: dict[str, Mapping[str, Any]] = {}
    for capability_id in sorted(capability_ids):
        missing = [slot for slot in REQUIRED_RUNTIME_SLOTS if (capability_id, slot) not in accepted]
        capability_decisions[capability_id] = {
            "decision": "ELIGIBLE_EVIDENCE_COMPLETE" if not missing else "NOT_ELIGIBLE",
            "missing": tuple(missing),
        }

    runner_decisions: dict[str, Mapping[str, Any]] = {}
    for runner_label, capabilities in contract["runner_retirement"]["runner_labels"].items():
        missing: list[str] = []
        for capability_id in capabilities:
            row = capability_decisions[capability_id]
            missing.extend(f"{capability_id}:{slot}" for slot in row["missing"])
        runner_decisions[runner_label] = {
            "decision": (
                "ELIGIBLE_FOR_SEPARATE_OWNER_RETIREMENT_GATE" if not missing else "NOT_ELIGIBLE"
            ),
            "missing": tuple(missing),
            "runner_deregistration_authorized": False,
            "repository_settings_mutation_authorized": False,
        }

    return {
        "capabilities": capability_decisions,
        "runners": runner_decisions,
        "accepted_receipts": tuple(sorted(accepted.values())),
        "rejected": tuple(rejected),
        "runtime_mutation_authorized": False,
        "runner_deregistration_authorized": False,
    }


def evaluate_activation_handoff(contract: Mapping[str, Any], source_prerequisites_pass: bool) -> Mapping[str, Any]:
    validate_contract(contract)
    handoff = contract["activation_handoff"]
    return {
        "decision": (
            "SOURCE_READY_FOR_EXPLICIT_FIRST_LIVE_GATE"
            if source_prerequisites_pass
            else "BLOCKED"
        ),
        "first_future_live_gate": handoff["first_future_live_gate"]["gate_id"],
        "phase4_state": handoff["phase4_state"],
        "runtime_live_authority": False,
        "phase4_closed": False,
        "runner_retirement_authorized": False,
    }
