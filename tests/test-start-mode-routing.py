#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

routing = json.loads((ROOT / ".github/start-mode-routing.json").read_text())
manifest = json.loads((ROOT / ".github/start-github-only.json").read_text())
agents = (ROOT / "AGENTS.md").read_text()
fast = (ROOT / "docs/FAST_LANE_V2_2.md").read_text()

assert routing["repository"] == "rozkalnsandris/RPi5_main"
assert routing["default_continuation_mode"] == "FAST-LANE v2.2"
assert routing["bare_continuation_result"] == "FAST-LANE v2.2"
assert routing["examples"]["START RPi5_main"] == "FAST-LANE v2.2"
assert routing["examples"]["turpini"] == "FAST-LANE v2.2"
assert routing["examples"]["START RPi5_main GITHUB-ONLY"] == "GITHUB-ONLY"

for mode in ("GITHUB-ONLY", "LIVE-ALL"):
    contract = routing["explicit_modes"][mode]
    assert contract["requires_explicit_current_command_token"] is True
    assert contract["may_be_inferred_from_context"] is False

for source in (
    ".github/start-github-only.json existence",
    "deploy-queue state",
    "handoff or issue continuity",
    "executor availability or unavailability",
    "historical chat mode",
    "prior authorization receipt",
):
    assert source in routing["forbidden_mode_inference_sources"]

assert manifest["shared_policy"]["startup_contract"] == "START GITHUB-ONLY v1"
assert "Bare `START`, `START RPi5_main`, `turpini`" in agents
assert "It is not `GITHUB-ONLY`" in agents
assert "Never infer either explicit mode" in agents
assert "Bare `START`, `START RPi5_main`, `turpini`" in fast
assert "It does **not** select `GITHUB-ONLY`" in fast
assert "Never infer either explicit mode" in fast
assert "safe Git-only" not in fast

print("START mode routing regression: PASS")
