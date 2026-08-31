#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

policy = json.loads((ROOT / ".github/auto-run-full-v1.json").read_text())
routing = json.loads((ROOT / ".github/start-mode-routing.json").read_text())
doc = (ROOT / "docs/AUTO_RUN_FULL_V1.md").read_text()

assert policy["schema_version"] == 1
assert policy["policy"] == "AUTO-RUN FULL v1"
assert policy["repository"] == "rozkalnsandris/RPi5_main"
assert policy["roadmap_issue"] == 294
assert policy["controller_issue"] == 295

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
assert mode["may_be_inferred_from_context"] is False
assert routing["examples"]["AUTO-RUN FULL RPi5_main #301"] == "AUTO-RUN-FULL"

execution = policy["execution_model"]
assert execution["canonical_state"] == "GITHUB"
assert execution["one_active_issue_at_a_time"] is True
assert execution["chat_history_is_authority"] is False
assert execution["scheduled_controller"] == "CHATGPT_PLUS_SCHEDULED_TASK"
assert execution["minimum_background_recurrence"] == "PT1H"
assert execution["session_end_is_resumable"] is True
assert execution["manual_turpini_is_resume_only"] is True

merge = policy["merge"]
assert merge["auto_run_full_command_is_explicit_owner_merge_authority_for_the_frozen_issue"] is True
assert merge["fresh_exact_head_revalidation_required"] is True
assert merge["required_ci_must_pass"] is True
assert merge["unresolved_actionable_review_findings_must_be_zero"] is True
assert merge["force_merge"] is False

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
assert continuation["scheduled_run_reconstructs_from_github"] is True
assert continuation["identical_failure_retry_ceiling"] == 3

states = set(policy["states"])
for required in {
    "IDLE",
    "WORKING",
    "WAITING_SCHEDULED_RESUME",
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

assert "AUTO-RUN FULL RPi5_main #301" in doc
assert "GitHub is the durable control plane" in doc
assert "PAUSED_PLATFORM_APPROVAL" in doc
assert "no `OPENAI_API_KEY`" in doc
assert "The explicit command itself is the owner's merge decision" in doc
assert "use information from previous runs" in doc
assert "up to once per hour" in doc

print("AUTO-RUN FULL v1 contract regression: PASS")
