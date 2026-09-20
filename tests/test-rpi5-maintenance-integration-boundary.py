#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/maintenance/rpi5-maintenance-integration.json"

with CONTRACT.open(encoding="utf-8") as handle:
    contract = json.load(handle)

assert contract["schema"] == "rpi5-main.maintenance-integration.v1"
assert contract["canonical_repository"] == "rozkalnsandris/RPi5-maintenance"
assert contract["stable_release"] == "0.2.0"
assert contract["release_commit"] == "7a5685908e06cc35aa4bb623dd9fa6a3081c4416"
assert contract["runtime_source_model"] == "installed-artifacts-no-checkout-dependency"
assert contract["live_mutation_authorized"] is False

removed_runtime_duplicates = (
    "ops/bin/rpi5-update",
    "ops/bin/rpi5-monitor",
    "ops/bin/rpi5-post-reboot",
    "ops/bin/rpi5-maintenance-notify",
    "ops/systemd/rpi5-update.service",
    "ops/systemd/rpi5-update.timer",
    "ops/systemd/rpi5-monitor.service",
    "ops/systemd/rpi5-monitor.timer",
    "ops/systemd/rpi5-post-reboot.service",
    "ops/systemd/rpi5-maintenance-notify@.service",
    "ops/maintenance/updater-source-provenance.json",
)
for relative in removed_runtime_duplicates:
    assert not (ROOT / relative).exists(), relative

# Backup ownership remains intentionally outside the extracted maintenance boundary.
assert (ROOT / "ops/bin/rpi5-backup").is_file()
assert (ROOT / "ops/bin/rpi5-backup-serialized").is_file()

print("RPi5 maintenance integration boundary: PASS")
