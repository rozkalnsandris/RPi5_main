#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

policy = json.loads((ROOT / ".github/auto-run-full-v2.json").read_text())
routing = json.loads((ROOT / ".github/start-mode-routing.json").read_text())
doc = (ROOT / "docs/AUTO_RUN_FULL_V2.md").read_text()
fast = (ROOT / "docs/FAST_LANE_V2_2.md").read_text()

assert policy["schema_version"] == 2
assert policy["policy"] == "AUTO-RUN FULL v2"
assert policy["repository"] == "rozkalnsandris/RPi5_main"
assert policy["roadmap_issue"] == 315
assert policy["controller_issue"] == 295

lane = policy["lane_role"]
assert lane["normal_implementation_lane"] == "AUTO-RUN FULL"
assert lane["safe_discovery_lane"] == "FAST-LANE v2.2"
assert lane["fast_lane_may_infer_auto_run_full"] is False

command = policy["command"]
assert command["syntax"] == "AUTO-RUN FULL RPi5_main #<issue>"
assert command["requires_explicit_current_command"] is True
assert command["requires_exact_open_issue"] is True
assert command["may_be_inferred_from_context"] is False
assert command["single_command_is_owner_authorization"] is True

mode = routing["explicit_modes"]["AUTO-RUN-FULL"]
assert mode["canonical_prefix"] == "AUTO-RUN FULL"
assert mode["requires_repository_argument"] == "RPi5_main"
assert mode["requires_issue_argument"] is True
assert mode["controller_issue"] == 295
assert mode["policy"] == ".github/auto-run-full-v2.json"
assert mode["preferred_resume"] == "GITHUB_EVENT_TRIGGERED_WORK"
assert mode["fallback_resume"] == "HOURLY_SCHEDULED_WATCHDOG"
assert mode["preferred_merge"] == "GITHUB_AUTO_MERGE_AFTER_FINAL_EXACT_HEAD_READINESS"
assert mode["may_be_inferred_from_context"] is False
assert routing["examples"]["AUTO-RUN FULL RPi5_main #301"] == "AUTO-RUN-FULL"

execution = policy["execution_model"]
assert execution["canonical_state"] == "GITHUB"
assert execution["one_active_issue_at_a_time"] is True
assert execution["chat_history_is_authority"] is False
assert execution["primary_resume"] == "CHATGPT_WORK_GITHUB_EVENT_TRIGGERED_TASK"
assert execution["fallback_watchdog"] == "CHATGPT_PLUS_SCHEDULED_TASK"
assert execution["event_triggered_work_primary"] is True
assert execution["event_triggered_work_required_for_correctness"] is False
assert execution["scheduled_watchdog_max_frequency"] == "PT1H"
assert execution["event_triggered_task_max_runs_per_hour"] == 30
assert execution["session_end_is_resumable"] is True
assert execution["manual_turpini_is_resume_only"] is True

merge = policy["merge"]
assert merge["auto_run_full_command_is_explicit_owner_merge_authority_for_the_frozen_issue"] is True
assert merge["preferred_merge_mechanism"] == "GITHUB_AUTO_MERGE"
assert merge["repository_auto_merge_capability_required_for_preferred_mechanism"] is True
assert merge["canonical_pr_only"] is True
assert merge["auto_merge_enable_only_after_final_exact_head_ready"] is True
assert merge["fresh_exact_head_revalidation_required"] is True
assert merge["final_diff_scope_review_required"] is True
assert merge["required_ci_must_pass"] is True
assert merge["unresolved_actionable_review_findings_must_be_zero"] is True
assert merge["changed_head_invalidates_previous_merge_readiness"] is True
assert merge["changed_head_requires_fresh_review_and_checks_before_auto_merge_reenable"] is True
assert merge["repository_ruleset_bypass"] is False
assert merge["force_merge"] is False
assert merge["direct_merge_fallback_allowed_only_after_same_final_readiness_gate"] is True

live = policy["live"]
assert live["auto_run_full_command_may_be_up_front_live_authority_only_for_frozen_predeclared_mutation_classes"] is True
assert live["exact_target_and_operation_identity_required_before_first_live_mutation"] is True
assert live["use_existing_236_live_auth_protocol_when_applicable"] is True
assert live["new_mutation_class_after_activation"] == "STOP_SCOPE_OR_RISK"

billing = policy["billing"]
assert billing["primary_product"] == "CHATGPT_PLUS"
assert billing["provider_api_keys_allowed"] is False
assert billing["automatic_paid_credits_allowed"] is False
assert billing["codex_required"] is False
assert billing["copilot_required"] is False

continuation = policy["continuation"]
assert continuation["routine_ci_failure_is_owner_gate"] is False
assert continuation["review_finding_is_owner_gate"] is False
assert continuation["ordinary_merge_conflict_is_owner_gate"] is False
assert continuation["session_or_turn_end_is_owner_gate"] is False
assert continuation["event_triggered_run_reconstructs_from_github"] is True
assert continuation["scheduled_watchdog_reconstructs_from_github"] is True
assert continuation["identical_failure_retry_ceiling"] == 3

states = set(policy["states"])
for required in {
    "IDLE",
    "WORKING",
    "WAITING_EVENT_RESUME",
    "WAITING_WATCHDOG_RESUME",
    "PAUSED_USAGE",
    "PAUSED_PLATFORM_APPROVAL",
    "DONE",
    "STOP_SCOPE_OR_RISK",
    "STOP_ERROR",
}:
    assert required in states

never = set(policy["never_implied"])
for forbidden in {
    "PROVIDER_API_KEY",
    "TOKEN_BILLED_LLM_FALLBACK",
    "AUTOMATIC_PAID_CREDIT_PURCHASE",
    "RESET_REBASE_FORCE_OR_HISTORY_REWRITE",
    "NEW_PERMISSION_OR_TRUST_BOUNDARY",
}:
    assert forbidden in never

platform = policy["platform_constraints"]
assert platform["scheduled_tasks_paid_plan_max_frequency"] == "PT1H"
assert platform["event_triggered_tasks_max_runs_per_hour"] == 30
assert platform["github_event_triggered_work_supported_for_pull_request_activity"] is True
assert platform["repository_allow_auto_merge_setting_must_be_enabled_out_of_band_when_not_exposed_by_the_connected_app"] is True

assert "AUTO-RUN FULL RPi5_main #<issue>" in doc
assert "normal implementation lane" in doc
assert "GitHub event-triggered ChatGPT Work task" in doc
assert "hourly ChatGPT Scheduled watchdog" in doc
assert "Guarded GitHub auto-merge" in doc
assert "does not arm it early" in doc
assert "no `OPENAI_API_KEY`" in doc
assert "safe discovery, audit and non-FULL continuation lane" in fast
assert "prefer switching to `AUTO-RUN FULL <repo> #<issue>`" in fast

print("AUTO-RUN FULL v2 contract regression: PASS")
