#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
policy = json.loads((ROOT / "ops/deploy/auto-live-v1.json").read_text())
doc = (ROOT / "docs/AUTO_LIVE_V1.md").read_text()
master = (ROOT / "docs/AUTOMATION_MASTER_PLAN.md").read_text()
routing = json.loads((ROOT / ".github/start-mode-routing.json").read_text())
executor = json.loads((ROOT / "ops/deploy/executor-operations.json").read_text())
manifests_index = json.loads((ROOT / "ops/deploy/auto-live-manifests.json").read_text())
a2_doc = (ROOT / "docs/AUTO_LIVE_V1_A2_MANIFESTS.md").read_text()

assert policy["schema_version"] == 1
assert policy["policy"] == "AUTO-LIVE v1"
assert policy["roadmap_issue"] == 421
assert policy["status"] == "A0_SOURCE_CONTRACT_ONLY"
assert policy["execution_enabled"] is False

assert policy["authority"]["merge_is_trigger_not_blanket_live_authority"] is True
assert policy["authority"]["first_host_activation_requires_separate_live_owner_authorization"] is True
assert policy["authority"]["historical_live_authorization_reuse"] is False

steady = policy["steady_state"]
assert steady["merge_detection"] == "TRUSTED_RPI5_OUTBOUND_GITHUB_POLL"
assert steady["reference_poll_interval"] == "PT2M"
assert steady["inbound_public_rpi5_webhook"] is False
assert steady["self_hosted_public_repository_actions_runner"] is False
assert steady["remote_desktop_commander_is_merge_detector"] is False
assert steady["remote_desktop_commander_is_authorization_store"] is False

classes = policy["classes"]
assert classes["NO_DEPLOY"]["automatic_mutation"] is False
assert classes["AUTO_DEPLOY_SAFE"]["automatic_mutation_after_activation"] is True
assert classes["MANUAL_ROLLOUT_REQUIRED"]["automatic_mutation_after_activation"] is False
assert classes["DB_HOST_APPLY_REQUIRED"]["automatic_mutation_after_activation"] is False
assert classes["UNKNOWN"]["result"] == "FAIL_CLOSED"

required = set(policy["automatic_mutation_gates"])
for gate in {
    "EXACT_TARGET_SHA_IS_MERGED_AND_REACHABLE_FROM_CURRENT_MAIN",
    "EXACT_TARGET_SHA_REQUIRED_CI_SUCCESS",
    "FULL_PRODUCTION_BASELINE_TO_TARGET_RANGE_IS_AUTO_DEPLOY_SAFE",
    "REPOSITORY_AUTO_LIVE_MANIFEST_PRESENT_AND_ACTIVE",
    "STATIC_OPERATION_ID_IS_AUTO_LIVE_ELIGIBLE",
    "TARGET_CONCURRENCY_LOCK_ACQUIRED",
    "NO_UNDECLARED_SENSITIVE_MUTATION_CLASS_REQUIRED",
}:
    assert gate in required

concurrency = policy["concurrency"]
assert concurrency["key"] == "PRODUCTION_TARGET_ALIAS"
assert concurrency["max_mutation_capable_deployments_per_target"] == 1
assert concurrency["supersession_requires_full_range_reclassification"] is True
assert concurrency["newer_target_may_supersede_after_mutation_started"] is False

failure = policy["failure"]
assert failure["automatic_retry_after_mutation_start"] is False
assert failure["automatic_cleanup_after_mutation_start"] is False
assert failure["automatic_rollback_after_mutation_start"] is False
assert failure["alternate_mutation_path_after_mutation_start"] is False

creds = policy["credentials"]
assert creds["preferred"] == "LEAST_PRIVILEGE_GITHUB_APP_INSTALLATION_TOKEN"
assert creds["pat_classic"] is False
assert creds["ssh_command_transport"] is False
assert creds["arbitrary_remote_shell_authority"] is False

compat = policy["compatibility"]
assert compat["github_only_currently_explicit_only"] is True
assert compat["a0_removes_existing_command_behavior"] is False
assert compat["historical_queue_evidence_retained"] is True
assert compat["consumer_without_auto_live_manifest"] == "NO_AUTOMATIC_LIVE_MUTATION"

assert routing["explicit_modes"]["GITHUB-ONLY"]["requires_explicit_current_command_token"] is True
assert executor["execution_enabled"] is False
assert policy["a0"] == {
    "source_only": True,
    "host_mutation": False,
    "credential_or_permission_mutation": False,
    "executor_enablement": False,
    "production_deploy": False,
}

assert "Trigger is not authority" in doc
assert "Remote Desktop Commander boundary" in doc
assert "GitHub App installation access tokens" in doc
assert "A0 is source/docs/tests only" in doc
assert "Cross-cutting Track Y — Post-merge Auto-Live v1" in master
assert "Canonical A0 contract: `docs/AUTO_LIVE_V1.md`" in master

SHARED_POLICY_SHA = "f2aeb5152371a876268bb116bb98806cddbc8e15"
assert manifests_index["schema_version"] == 1
assert manifests_index["contract"] == "AUTO-LIVE v1 A2 repository manifests"
assert manifests_index["status"] == "A2_SOURCE_ONLY_INACTIVE"
assert manifests_index["execution_enabled"] is False
assert manifests_index["roadmap_issue"] == 421
assert manifests_index["shared_policy"] == {
    "repository": "rozkalnsandris/ops-workflows",
    "path": "policy/auto-live-v1.json",
    "commit_sha": SHARED_POLICY_SHA,
    "immutable_exact_commit_required": True,
}
assert manifests_index["activation"]["default_state"] == "INACTIVE_SOURCE_ONLY"
assert manifests_index["activation"]["automatic_mutation_enabled"] is False
assert manifests_index["activation"]["first_activation_requires_separate_owner_live_authorization"] is True
assert manifests_index["activation"]["historical_live_authorization_reuse"] is False

expected_manifest_paths = {
    "ops/deploy/auto-live-manifests/dashboard-rpi5.json",
    "ops/deploy/auto-live-manifests/hermes-deals.json",
    "ops/deploy/auto-live-manifests/rozkalns-weather.json",
}
assert {item["path"] for item in manifests_index["manifests"]} == expected_manifest_paths

operations = {item["operation_id"]: item for item in executor["operations"]}
manifests = {}
for item in manifests_index["manifests"]:
    manifest = json.loads((ROOT / item["path"]).read_text())
    manifests[manifest["manifest_id"]] = manifest
    assert manifest["schema_version"] == 1
    assert manifest["schema"] == manifests_index["manifest_schema"]
    assert manifest["source_repository"] == item["source_repository"]
    assert manifest["target_alias"] == item["target_alias"]
    assert manifest["static_operation_id"] == item["static_operation_id"]
    assert manifest["shared_policy_commit_sha"] == SHARED_POLICY_SHA
    assert manifest["activation"]["state"] == "INACTIVE_SOURCE_ONLY"
    assert manifest["activation"]["automatic_mutation_enabled"] is False
    assert manifest["activation"]["first_activation_requires_separate_owner_live_authorization"] is True
    assert manifest["classifier"]["range"] == "FULL_PRODUCTION_BASELINE_TO_TARGET"
    assert manifest["classifier"]["latest_commit_only"] is False
    assert manifest["classifier"]["unmatched_path_result"] == "BLOCKED"
    assert manifest["classifier"]["mixed_range_result"] == "HIGHEST_PRECEDENCE_MATCH"
    assert manifest["required_ci"]["exact_target_sha_required"] is True
    assert manifest["required_ci"]["required_conclusion"] == "success"
    assert manifest["baseline"]["must_match_static_operation"] is True
    assert manifest["baseline"]["production_baseline_to_target_reclassification_required"] is True
    assert manifest["failure_policy"] == {
        "rollback_policy": "NONE",
        "automatic_retry_after_mutation_start": False,
        "automatic_cleanup_after_mutation_start": False,
        "automatic_rollback_after_mutation_start": False,
        "alternate_mutation_path_after_mutation_start": False,
    }
    operation = operations[manifest["static_operation_id"]]
    assert operation["source_repository"] == manifest["source_repository"]
    assert operation["target_alias"] == manifest["target_alias"]
    assert operation["baseline"]["resolver_id"] == manifest["baseline"]["resolver_id"]

dashboard = manifests["dashboard-rpi5.production-release.v1"]
assert dashboard["required_ci"]["workflow_path"] == ".github/workflows/ci.yml"
assert dashboard["required_ci"]["workflow_name"] == "CI"
assert dashboard["required_ci"]["required_gate"] == "FAST-LANE Merge Gate"
assert dashboard["automatic_eligibility"]["eligible_classes"] == ["AUTO_DEPLOY_SAFE"]
assert operations[dashboard["static_operation_id"]]["queue_match"]["deploy_class"] == "AUTO_DEPLOY_SAFE"
assert operations[dashboard["static_operation_id"]]["ordinary_live_all_eligible"] is True

weather = manifests["rozkalns-weather.public-runtime-release.v1"]
assert weather["required_ci"]["workflow_path"] == ".github/workflows/tests.yml"
assert weather["required_ci"]["workflow_name"] == "Backend tests"
assert weather["required_ci"]["required_gate"] == "pytest"
assert weather["automatic_eligibility"]["eligible_classes"] == []
assert operations[weather["static_operation_id"]]["authorization_class"] == "STRICT"
assert operations[weather["static_operation_id"]]["ordinary_live_all_eligible"] is False


def classify(manifest, paths):
    if not paths:
        return "BLOCKED"
    matched = []
    rules = manifest["classifier"]["rules"]
    for path in paths:
        path_classes = []
        for class_name, rule in rules.items():
            if path in rule["exact_paths"] or any(path.startswith(prefix) for prefix in rule["path_prefixes"]):
                path_classes.append(class_name)
        if not path_classes:
            return manifest["classifier"]["unmatched_path_result"]
        matched.extend(path_classes)
    for class_name in manifest["classifier"]["precedence"]:
        if class_name in matched:
            return class_name
    return "BLOCKED"


assert classify(dashboard, ["docs/README.md"]) == "NO_DEPLOY"
assert classify(dashboard, ["apps/web/src/example.tsx"]) == "AUTO_DEPLOY_SAFE"
assert classify(dashboard, ["apps/server/src/example.ts"]) == "MANUAL_ROLLOUT_REQUIRED"
assert classify(dashboard, ["ops/production/example.json"]) == "DB_HOST_APPLY_REQUIRED"
assert classify(dashboard, ["apps/web/src/example.tsx", "ops/production/example.json"]) == "DB_HOST_APPLY_REQUIRED"
assert classify(dashboard, ["unclassified.future"]) == "BLOCKED"

assert classify(weather, ["docs/OPERATIONS.md"]) == "NO_DEPLOY"
assert classify(weather, ["src/rozkalns_weather/app.py"]) == "MANUAL_ROLLOUT_REQUIRED"
assert classify(weather, ["deploy/runtime-descriptor.json"]) == "DB_HOST_APPLY_REQUIRED"
assert classify(weather, ["src/rozkalns_weather/app.py", "deploy/runtime-descriptor.json"]) == "DB_HOST_APPLY_REQUIRED"
assert classify(weather, ["unclassified.future"]) == "BLOCKED"

invariants = manifests_index["invariants"]
assert invariants["full_production_baseline_to_target_range_required"] is True
assert invariants["exact_target_sha_required_ci_success"] is True
assert invariants["only_auto_deploy_safe_may_be_automatic"] is True
assert invariants["unknown_or_ambiguous_path_result"] == "BLOCKED"
assert invariants["per_target_serialization_required"] is True
assert invariants["post_mutation_automatic_retry"] is False
assert invariants["post_mutation_automatic_cleanup"] is False
assert invariants["post_mutation_automatic_rollback"] is False
assert invariants["post_mutation_alternate_mutation_path"] is False

assert manifests_index["a2_scope"] == {
    "source_only": True,
    "host_mutation": False,
    "systemd_or_timer_mutation": False,
    "credential_or_permission_mutation": False,
    "executor_enablement": False,
    "production_deploy": False,
}
assert "A2 SOURCE ONLY / INACTIVE" in a2_doc
assert "No manifest means no automatic live mutation." in a2_doc
assert "INACTIVE_SOURCE_ONLY" in a2_doc
assert "A2 does **not** authorize" in a2_doc

print("AUTO-LIVE v1 A0 + A2 source contract regression: PASS")
