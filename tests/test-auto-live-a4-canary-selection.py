#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
contract = json.loads((ROOT / "ops/deploy/auto-live-a4-canary-selection.json").read_text())
manifests_index = json.loads((ROOT / "ops/deploy/auto-live-manifests.json").read_text())
dashboard = json.loads((ROOT / "ops/deploy/auto-live-manifests/dashboard-rpi5.json").read_text())
weather = json.loads((ROOT / "ops/deploy/auto-live-manifests/rozkalns-weather.json").read_text())
executor = json.loads((ROOT / "ops/deploy/executor-operations.json").read_text())
master = (ROOT / "docs/AUTOMATION_MASTER_PLAN.md").read_text()
doc = (ROOT / "docs/AUTO_LIVE_V1_A4_CANARY_SELECTION.md").read_text()

assert contract["schema_version"] == 1
assert contract["contract"] == "AUTO-LIVE v1 A4 canary candidate selection"
assert contract["status"] == "A4_OWNER_REQUIRED_LIVE_DISABLED"
assert contract["roadmap_issue"] == 421
assert contract["source_main_at_reconciliation"] == "9b92b08aa5a9c7f2691ff092ca7099c9dd918900"
assert contract["shared_policy_commit_sha"] == "f2aeb5152371a876268bb116bb98806cddbc8e15"

selection = contract["selection"]
assert selection["source_repository"] == dashboard["source_repository"] == "rozkalnsandris/dashboard_RPi5"
assert selection["target_alias"] == dashboard["target_alias"] == "dashboard-rpi5-production-release"
assert selection["manifest_path"] == "ops/deploy/auto-live-manifests/dashboard-rpi5.json"
assert selection["static_operation_id"] == dashboard["static_operation_id"] == "dashboard-rpi5.production-release.v1"
assert selection["eligible_class"] == "AUTO_DEPLOY_SAFE"
assert selection["eligible_path_prefixes"] == dashboard["classifier"]["rules"]["AUTO_DEPLOY_SAFE"]["path_prefixes"] == ["apps/web/"]
assert selection["selection_status"] == "SOURCE_LEVEL_CANDIDATE_ONLY"
assert dashboard["automatic_eligibility"]["eligible_classes"] == ["AUTO_DEPLOY_SAFE"]
assert weather["automatic_eligibility"]["eligible_classes"] == []
assert selection["weather_not_selected_reason"] == "NO_AUTOMATIC_ELIGIBLE_CLASS"

operations = {item["operation_id"]: item for item in executor["operations"]}
dashboard_operation = operations[selection["static_operation_id"]]
weather_operation = operations[weather["static_operation_id"]]
assert executor["execution_enabled"] is False
assert dashboard_operation["source_repository"] == selection["source_repository"]
assert dashboard_operation["target_alias"] == selection["target_alias"]
assert dashboard_operation["queue_match"]["deploy_class"] == "AUTO_DEPLOY_SAFE"
assert dashboard_operation["ordinary_live_all_eligible"] is True
assert weather_operation["authorization_class"] == "STRICT"
assert weather_operation["ordinary_live_all_eligible"] is False


def classify(manifest, path):
    matched = []
    for class_name, rule in manifest["classifier"]["rules"].items():
        if path in rule["exact_paths"] or any(path.startswith(prefix) for prefix in rule["path_prefixes"]):
            matched.append(class_name)
    if not matched:
        return manifest["classifier"]["unmatched_path_result"]
    for class_name in manifest["classifier"]["precedence"]:
        if class_name in matched:
            return class_name
    return "BLOCKED"


def classify_range(manifest, paths):
    classes = {classify(manifest, path) for path in paths}
    if "BLOCKED" in classes:
        return "BLOCKED"
    for class_name in manifest["classifier"]["precedence"]:
        if class_name in classes:
            return class_name
    return "BLOCKED"


evidence = contract["github_evidence"]
assert evidence["observed_dashboard_main_sha"] == "20e47ff7ba808f183db56e347d4fde3e1d6a129f"
assert evidence["reviewed_frozen_candidate_sha"] == "343366427441811a22739b05b04d069c10905805"
assert evidence["observed_dashboard_main_sha"] != evidence["reviewed_frozen_candidate_sha"]
assert evidence["relation"] == "DIRECT_CHILD"
assert evidence["observed_main_delta_paths"] == ["AGENTS.md"]
assert evidence["observed_main_delta_classification"] == "NO_DEPLOY"
assert classify(dashboard, "AGENTS.md") == "NO_DEPLOY"
assert evidence["point_in_time_only"] is True

production = contract["production_evidence"]
assert production["trusted_production_baseline_sha"] == "066b9a24008dd57439f9e66eae198416c4dfc590"
assert production["reviewed_frozen_candidate_sha"] == evidence["reviewed_frozen_candidate_sha"]
assert production["observed_dashboard_main_sha"] == evidence["observed_dashboard_main_sha"]
assert production["baseline_to_frozen_relation"] == "DIRECT_CHILD"
assert classify(dashboard, "package-lock.json") == "MANUAL_ROLLOUT_REQUIRED"
assert classify_range(dashboard, production["baseline_to_frozen_paths"]) == "MANUAL_ROLLOUT_REQUIRED"
assert classify_range(dashboard, production["baseline_to_current_paths"]) == "MANUAL_ROLLOUT_REQUIRED"
assert production["baseline_to_frozen_classification"] == "MANUAL_ROLLOUT_REQUIRED"
assert production["baseline_to_current_classification"] == "MANUAL_ROLLOUT_REQUIRED"
assert production["blocking_paths"] == ["package-lock.json"]
assert production["point_in_time_only"] is True

decision = contract["canary_decision"]
assert decision["decision"] == "OWNER_REQUIRED"
assert decision["reason"] == "FULL_PRODUCTION_RANGE_MANUAL_ROLLOUT_REQUIRED"
assert decision["canary_selected"] is False
assert decision["selected_target_sha"] is None
assert decision["automatic_live_eligible"] is False
assert decision["future_auto_live_canary_requires_new_auto_deploy_safe_range_or_reviewed_policy_change"] is True

live_gate = contract["live_gate"]
assert live_gate["candidate_selection_is_live_authority"] is False
assert live_gate["observed_dashboard_main_is_automatic_live_target"] is False
assert live_gate["reviewed_frozen_candidate_is_reusable_live_authorization"] is False
assert live_gate["trusted_production_baseline_observed_for_this_reconciliation"] is True
assert live_gate["full_baseline_to_target_reclassification_complete"] is True
assert live_gate["full_range_result_must_be_auto_deploy_safe"] is True
assert live_gate["current_full_range_result"] == "MANUAL_ROLLOUT_REQUIRED"
assert live_gate["canary_blocked"] is True
assert live_gate["future_canary_requires_fresh_trusted_production_baseline"] is True
assert live_gate["future_canary_requires_fresh_exact_target_ci"] is True
assert live_gate["future_canary_requires_fresh_static_operation_identity"] is True
assert live_gate["future_canary_requires_fresh_host_provenance"] is True
assert live_gate["separate_owner_live_authorization_required"] is True
assert live_gate["owner_live_authorization_alone_overrides_classification"] is False

assert contract["mutation"] == {
    "execution_enabled": False,
    "manifest_activation_enabled": False,
    "automatic_mutation_enabled": False,
    "mutation_dispatch_enabled": False,
    "adapter_apply_invocation": False,
    "systemd_or_timer_mutation": False,
    "credential_or_permission_mutation": False,
    "production_deploy": False,
    "production_mutation_started": False,
}

assert manifests_index["status"] == "A2_SOURCE_ONLY_INACTIVE"
assert manifests_index["execution_enabled"] is False
assert manifests_index["activation"]["automatic_mutation_enabled"] is False
assert "Current supersession — Auto-Live A4 production-baseline fail-closed reconciliation (2026-09-09)" in master
assert "AUTO_LIVE_TRACK_Y_CURRENT=A4_OWNER_REQUIRED_RECONCILIATION" in master
assert "A4_TRUSTED_PRODUCTION_BASELINE=066b9a24008dd57439f9e66eae198416c4dfc590" in master
assert "A4_FULL_RANGE_CLASSIFICATION=MANUAL_ROLLOUT_REQUIRED" in master
assert "A4_CANARY_SELECTED=false" in master
assert "A4 OWNER REQUIRED / NO CANARY SELECTED / LIVE DISABLED" in doc
assert "No A4 Auto-Live canary is selected." in doc
assert "LIVE authorization alone cannot override the source classification." in doc

print("AUTO-LIVE v1 A4 production-baseline fail-closed contract: PASS")
