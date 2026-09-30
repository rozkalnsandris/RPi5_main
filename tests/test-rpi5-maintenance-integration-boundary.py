#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/maintenance/rpi5-maintenance-integration.json"
DEPLOY_TARGETS = ROOT / "ops/deploy/targets.json"

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

removed_source_duplicates = (
    "ops/lib/rpi5-maintenance-health.sh",
    "ops/lib/rpi5-maintenance-telegram.py",
    "ops/lib/rpi5-update-apt-policy.sh",
    "ops/lib/rpi5-update-cleanup-policy.sh",
    "ops/lib/rpi5-update-compose-health.sh",
    "ops/lib/rpi5-update-compose-policy.sh",
    "ops/lib/rpi5-update-hermes-status.sh",
    "ops/lib/rpi5-update-http-health.sh",
    "ops/lib/rpi5-update-locks.sh",
    "ops/lib/rpi5-update-origin-policy.sh",
    "ops/lib/rpi5-update-reboot.sh",
    "ops/lib/rpi5-update-space-policy.sh",
    "ops/lib/rpi5-update-telegram.py",
)
for relative in removed_source_duplicates:
    assert not (ROOT / relative).exists(), relative

removed_implementation_tests = (
    "tests/test-maintenance-updater-status.sh",
    "tests/test-maintenance-updater-locks.sh",
    "tests/test-maintenance-updater-reboot.sh",
    "tests/test-maintenance-updater-compose-health.sh",
    "tests/test-maintenance-updater-compose-policy.sh",
    "tests/test-maintenance-compose-policy-activation.py",
    "tests/test-maintenance-updater-space-policy.sh",
    "tests/test-maintenance-updater-origin-policy.sh",
    "tests/test-maintenance-updater-http-health.sh",
    "tests/test-maintenance-updater-apt-policy.sh",
    "tests/test-maintenance-v27-activation.py",
    "tests/test-maintenance-v27-activation-transaction.py",
    "tests/test-maintenance-updater-provenance.sh",
    "tests/test-maintenance-updater-source.sh",
    "tests/test-maintenance-updater-source-validator.py",
    "tests/test-maintenance-updater-telegram.py",
    "tests/test-maintenance-health.sh",
    "tests/test-maintenance-health-entrypoints.sh",
    "tests/test-maintenance-telegram-credentials.py",
    "tests/test-maintenance-systemd-units.sh",
    "tests/test-maintenance-systemd-cutover.py",
    "tests/test-maintenance-systemd-notify.sh",
    "tests/test-maintenance-cleanup-policy.sh",
    "tests/test-maintenance-cleanup-source.py",
    "tests/test-maintenance-shared-lock.sh",
    "tests/test-maintenance-shared-lock-source.py",
    "tests/test-maintenance-lock-cutover.py",
)
for relative in removed_implementation_tests:
    assert not (ROOT / relative).exists(), relative

# Backup ownership remains intentionally outside the extracted maintenance boundary.
assert (ROOT / "ops/bin/rpi5-backup").is_file()
assert (ROOT / "ops/bin/rpi5-backup-serialized").is_file()

# The shared lock library is an explicit retained backup integration dependency,
# not a general exception allowing predecessor maintenance implementation copies.
expected_exception = [{
    "id": "backup-shared-lock-lib",
    "source": "ops/lib/rpi5-maintenance-locks.sh",
    "consumer": "ops/deploy/targets.json#maintenance-lock-lib",
    "reason": "Backup controlled-deploy still attests and stages the shared lock library as part of the separately retained RPi5_main backup ownership boundary.",
}]
assert contract["retained_source_exceptions"] == expected_exception
assert (ROOT / expected_exception[0]["source"]).is_file()

with DEPLOY_TARGETS.open(encoding="utf-8") as handle:
    deploy_targets = json.load(handle)
by_id = {item["id"]: item for item in deploy_targets["targets"]}
assert by_id["maintenance-lock-lib"]["source"] == expected_exception[0]["source"]
assert by_id["maintenance-lock-lib"]["target"] == "/usr/local/lib/rpi5-maintenance/rpi5-maintenance-locks.sh"

print("RPi5 maintenance integration boundary: PASS")
