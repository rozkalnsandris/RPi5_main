#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
policy = json.loads((ROOT / "ops/deploy/auto-live-v1.json").read_text())
doc = (ROOT / "docs/AUTO_LIVE_V1.md").read_text()
master = (ROOT / "docs/AUTOMATION_MASTER_PLAN.md").read_text()
routing = json.loads((ROOT / ".github/start-mode-routing.json").read_text())
executor = json.loads((ROOT / "ops/deploy/executor-operations.json").read_text())

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

print("AUTO-LIVE v1 A0 source contract regression: PASS")
