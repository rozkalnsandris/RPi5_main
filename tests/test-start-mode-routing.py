#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

routing = json.loads((ROOT / ".github/start-mode-routing.json").read_text())
manifest = json.loads((ROOT / ".github/start-github-only.json").read_text())
auto_run = json.loads((ROOT / ".github/auto-run-full-v2.json").read_text())
agents = (ROOT / "AGENTS.md").read_text()
fast = (ROOT / "docs/FAST_LANE_V2_2.md").read_text()

assert routing["repository"] == "rozkalnsandris/RPi5_main"
assert routing["schema_version"] == 3
assert routing["default_continuation_mode"] == "FAST-LANE v2.2"
assert routing["bare_continuation_result"] == "FAST-LANE v2.2"
assert routing["lane_roles"]["FAST-LANE v2.2"] == "SAFE_DISCOVERY_AUDIT_AND_NON_FULL_CONTINUATION"
assert routing["lane_roles"]["AUTO-RUN-FULL"] == "NORMAL_ISSUE_SCOPED_IMPLEMENTATION"
assert routing["examples"]["START RPi5_main"] == "FAST-LANE v2.2"
assert routing["examples"]["turpini"] == "FAST-LANE v2.2"
assert routing["examples"]["START RPi5_main GITHUB-ONLY"] == "GITHUB-ONLY"
assert routing["examples"]["AUTO-RUN FULL RPi5_main #301"] == "AUTO-RUN-FULL"

for mode in ("GITHUB-ONLY", "LIVE-ALL", "AUTO-RUN-FULL"):
    contract = routing["explicit_modes"][mode]
    assert contract["requires_explicit_current_command_token"] is True
    assert contract["may_be_inferred_from_context"] is False

full = routing["explicit_modes"]["AUTO-RUN-FULL"]
assert full["canonical_prefix"] == "AUTO-RUN FULL"
assert full["requires_repository_argument"] == "RPi5_main"
assert full["requires_issue_argument"] is True
assert full["issue_argument_pattern"] == "^#[1-9][0-9]*$"
assert full["policy"] == ".github/auto-run-full-v2.json"
assert full["controller_issue"] == 295
assert full["preferred_resume"] == "GITHUB_EVENT_TRIGGERED_WORK"
assert full["fallback_resume"] == "HOURLY_SCHEDULED_WATCHDOG"
assert full["preferred_merge"] == "GITHUB_AUTO_MERGE_AFTER_FINAL_EXACT_HEAD_READINESS"

for source in (
    ".github/start-github-only.json existence",
    "deploy-queue state",
    "handoff or issue continuity",
    "executor availability or unavailability",
    "historical chat mode",
    "prior authorization receipt",
    "AUTO-RUN controller state without a fresh explicit activation command",
    "prior AUTO-RUN authorization receipt",
):
    assert source in routing["forbidden_mode_inference_sources"]

assert manifest["shared_policy"]["startup_contract"] == "START GITHUB-ONLY v1"
assert auto_run["policy"] == "AUTO-RUN FULL v2"
assert auto_run["command"]["syntax"] == "AUTO-RUN FULL RPi5_main #<issue>"
assert auto_run["lane_role"]["normal_implementation_lane"] == "AUTO-RUN FULL"
assert auto_run["lane_role"]["safe_discovery_lane"] == "FAST-LANE v2.2"
assert "FAST is the safe discovery/audit/non-FULL continuation lane" in agents
assert "preferred operator lane" in agents
assert "Activate `AUTO-RUN FULL` only from the exact explicit form" in agents
assert "AUTO-RUN FULL v2" in agents
assert "GitHub native auto-merge" in agents
assert "Bare `START`, `START RPi5_main`, `turpini`" in fast
assert "It does **not** select `GITHUB-ONLY` or `AUTO-RUN FULL`" in fast
assert "Never infer an explicit mode" in fast
assert "AUTO-RUN FULL v2 relationship" in fast
assert "safe Git-only" not in fast

print("START mode routing regression: PASS")
