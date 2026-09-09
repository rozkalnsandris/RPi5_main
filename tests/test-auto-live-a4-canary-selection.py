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
assert contract["status"] == "A4_SOURCE_SELECTION_ONLY_LIVE_DISABLED"
assert contract["roadmap_issue"] == 421
assert contract["source_main_at_reconciliation"] == "9621c601f9bf94c4a29fad76afbdec250557d293"
assert contract["shared_policy_commit_sha"] == "f2aeb5152371a876268bb116bb98806cddbc8e15"

selection = contract["selection"]
assert selection["source_repository"] == dashboard["source_repository"] == "rozkalnsandris/dashboard_RPi5"
assert selection["target_alias"] == dashboard["target_alias"] == "dashboard-rpi5-production-release"
assert selection["manifest_path"] == "ops/deploy/auto-live-manifests/dashboard-rpi5.json"
assert selection["static_operation_id"] == dashboard["static_operation_id"] == "dashboard-rpi5.production-release.v1"
assert selection["eligible_class"] == "AUTO_DEPLOY_SAFE"
assert selection["eligible_path_prefixes"] == dashboard["classifier"]["rules"]["AUTO_DEPLOY_SAFE"]["path_prefixes"] == ["apps/web/"]
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


evidence = contract["github_evidence"]
assert evidence["observed_dashboard_main_sha"] == "20e47ff7ba808f183db56e347d4fde3e1d6a129f"
assert evidence["reviewed_frozen_candidate_sha"] == "343366427441811a22739b05b04d069c10905805"
assert evidence["observed_dashboard_main_sha"] != evidence["reviewed_frozen_candidate_sha"]
assert evidence["relation"] == "DIRECT_CHILD"
assert evidence["observed_main_delta_paths"] == ["AGENTS.md"]
assert evidence["observed_main_delta_classification"] == "NO_DEPLOY"
assert classify(dashboard, "AGENTS.md") == "NO_DEPLOY"
assert evidence["point_in_time_only"] is True

live_gate = contract["live_gate"]
assert live_gate["candidate_selection_is_live_authority"] is False
assert live_gate["observed_dashboard_main_is_automatic_live_target"] is False
assert live_gate["reviewed_frozen_candidate_is_reusable_live_authorization"] is False
for key in {
    "fresh_trusted_production_baseline_required",
    "full_baseline_to_target_reclassification_required",
    "fresh_exact_target_ci_required",
    "fresh_static_operation_identity_required",
    "fresh_host_provenance_required",
    "separate_owner_live_authorization_required",
}:
    assert live_gate[key] is True

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
assert "Current supersession — Auto-Live A4 candidate-selection source reconciliation (2026-09-09)" in master
assert "AUTO_LIVE_TRACK_Y_CURRENT=A4_SOURCE_RECONCILIATION" in master
assert "A4_FIRST_ACTIVATION_AUTHORIZED=false" in master
assert "A4 SOURCE SELECTION ONLY / LIVE DISABLED" in doc
assert "Current Dashboard `main` is not automatically promoted into a live target" in doc
assert "Merge of this source gate is not LIVE authority" in doc

print("AUTO-LIVE v1 A4 candidate-selection source contract: PASS")
