#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
contract = json.loads((ROOT / "ops/deploy/auto-live-a4-canary-selection.json").read_text())
discovery = json.loads((ROOT / "ops/deploy/auto-live-a4-candidate-discovery.json").read_text())
index = json.loads((ROOT / "ops/deploy/auto-live-manifests.json").read_text())
dashboard = json.loads((ROOT / "ops/deploy/auto-live-manifests/dashboard-rpi5.json").read_text())
weather = json.loads((ROOT / "ops/deploy/auto-live-manifests/rozkalns-weather.json").read_text())
executor = json.loads((ROOT / "ops/deploy/executor-operations.json").read_text())
master = (ROOT / "docs/AUTOMATION_MASTER_PLAN.md").read_text()
doc = (ROOT / "docs/AUTO_LIVE_V1_A4_CANARY_SELECTION.md").read_text()

assert contract["schema_version"] == 2
assert contract["status"] == "A4_DISCOVERY_READY_NO_CANARY_SELECTED_LIVE_DISABLED"
assert contract["roadmap_issue"] == 421
assert contract["implementation_issue"] == 459
assert contract["discovery"] == {
    "contract_path": "ops/deploy/auto-live-a4-candidate-discovery.json",
    "engine_path": "ops/lib/deploy_executor/auto_live_a4_discovery.py",
    "candidate_index_path": "ops/deploy/auto-live-manifests.json",
    "decisions": ["ELIGIBLE_CANARY", "NO_ELIGIBLE_CANARY", "NEEDS_FRESH_LIVE_PREFLIGHT", "OWNER_REQUIRED", "BLOCKED"],
    "fresh_evaluation_required": True,
    "volatile_source_sha_persisted_as_current_state": False,
    "production_baseline_inferred_from_source": False,
}
policy = contract["candidate_policy"]
assert policy["dashboard_manifest_path"] == "ops/deploy/auto-live-manifests/dashboard-rpi5.json"
assert policy["dashboard_target_alias"] == dashboard["target_alias"]
assert policy["dashboard_static_operation_id"] == dashboard["static_operation_id"]
assert policy["dashboard_eligible_classes"] == dashboard["automatic_eligibility"]["eligible_classes"] == ["AUTO_DEPLOY_SAFE"]
assert policy["weather_manifest_path"] == "ops/deploy/auto-live-manifests/rozkalns-weather.json"
assert policy["weather_eligible_classes"] == weather["automatic_eligibility"]["eligible_classes"] == []
assert policy["candidate_set_is_manifest_index_derived"] is True
assert policy["undeclared_candidate_result"] == "BLOCKED"

history = contract["historical_evidence"]
assert history["historical_only"] is True
assert history["not_current_runtime_or_source_truth"] is True
assert history["reconciliation_source_sha"] == "c4accd5ea08343f8e4fce30534a6e7734a461e5f"
assert history["github"]["observed_dashboard_main_sha"] == "b5838741d094ad7f70987bf5a5060be11371a6ae"
assert history["github"]["observed_main_delta_classification"] == "DB_HOST_APPLY_REQUIRED"
assert history["github"]["point_in_time_only"] is True
assert history["production"]["trusted_production_baseline_sha"] == "066b9a24008dd57439f9e66eae198416c4dfc590"
assert history["production"]["historical_only"] is True
assert history["production"]["point_in_time_only"] is True

state = contract["canary_state"]
assert state["durable_state"] == "A4_DISCOVERY_READY_NO_CANARY_SELECTED"
assert state["canary_selected"] is False
assert state["selected_target_sha"] is None
assert state["automatic_live_eligible"] is False
assert state["dynamic_decision_must_be_recomputed_from_fresh_evidence"] is True
assert state["safe_source_tip_without_fresh_baseline_result"] == "NEEDS_FRESH_LIVE_PREFLIGHT"
assert state["manual_or_db_host_current_tip_result"] == "OWNER_REQUIRED"
assert state["unknown_missing_or_stale_evidence_result"] == "BLOCKED"

live = contract["live_gate"]
assert live["candidate_discovery_is_live_authority"] is False
assert live["fresh_live_preflight_is_separate_owner_gate"] is True
assert live["full_baseline_to_target_reclassification_required"] is True
assert live["separate_owner_live_authorization_required_for_activation"] is True
assert live["owner_live_authorization_alone_overrides_classification"] is False
assert live["historical_production_baseline_is_reusable_authority"] is False
assert all(value is False for value in contract["mutation"].values())
assert contract["continuity_policy"] == {
    "canonical_gate_is_state_based": True,
    "volatile_candidate_sha_is_current_binding": False,
    "candidate_repository_merge_requires_rpi5_main_continuity_update": False,
    "fresh_candidate_repository_head_required_at_each_evaluation": True,
    "continuity_update_required_only_when_a4_policy_or_durable_state_changes": True,
}

assert discovery["status"] == "A4_DISCOVERY_SOURCE_READY_LIVE_DISABLED"
assert discovery["implementation_issue"] == 459
assert discovery["candidate_source"]["index"] == "ops/deploy/auto-live-manifests.json"
assert discovery["production_baseline_evidence"]["repository_source_may_infer_production_baseline"] is False
assert discovery["production_baseline_evidence"]["missing_result"] == "NEEDS_FRESH_LIVE_PREFLIGHT"
assert discovery["full_range"]["auto_deploy_safe_result"] == "ELIGIBLE_CANARY"
assert discovery["aggregate"]["eligible_candidate_tie_break"] == "target_alias_then_manifest_path"
assert all(value is False for value in discovery["mutation"].values())

manifest_paths = {row["path"] for row in index["manifests"]}
assert manifest_paths == {
    policy["dashboard_manifest_path"],
    "ops/deploy/auto-live-manifests/hermes-deals.json",
    policy["weather_manifest_path"],
}
operations = {row["operation_id"]: row for row in executor["operations"]}
dop = operations[dashboard["static_operation_id"]]
assert dop["authorization_class"] == "ORDINARY"
assert dop["ordinary_live_all_eligible"] is True
assert dop["queue_match"]["deploy_class"] == "AUTO_DEPLOY_SAFE"
wop = operations[weather["static_operation_id"]]
assert wop["authorization_class"] == "STRICT"
assert wop["ordinary_live_all_eligible"] is False
assert executor["execution_enabled"] is False

assert "AUTO_LIVE_TRACK_Y_CURRENT=A4_DISCOVERY_READY_NO_CANARY_SELECTED" in master
assert "A4_DISCOVERY_CONTRACT=ops/deploy/auto-live-a4-candidate-discovery.json" in master
assert "A4_VOLATILE_CANDIDATE_SHA_PERSISTED=false" in master
assert "A4_DISCOVERY_READY_NO_CANARY_SELECTED" in doc
assert "NEEDS_FRESH_LIVE_PREFLIGHT" in doc
assert "No candidate repository SHA is stored as the canonical A4 current state." in doc

print("AUTO-LIVE v1 A4 state-based discovery contract: PASS")
