#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-maintenance-updater-source.py"
spec = importlib.util.spec_from_file_location("updater_validator", VALIDATOR)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

GOOD = r'''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
CONFIG=/etc/rpi-update.conf
LOCK=/run/lock/rpi5-update.lock
# Supported: --check --no-reboot --cleanup-only
source /usr/local/libexec/rpi5-maintenance/rpi5-update-hermes-status.sh
source /usr/local/libexec/rpi5-maintenance/rpi5-update-locks.sh
source /usr/local/libexec/rpi5-maintenance/rpi5-update-reboot.sh
source /usr/local/libexec/rpi5-maintenance/rpi5-update-compose-health.sh
source /usr/local/libexec/rpi5-maintenance/rpi5-update-compose-policy.sh
source /usr/local/libexec/rpi5-maintenance/rpi5-update-space-policy.sh
source /usr/local/libexec/rpi5-maintenance/rpi5-update-origin-policy.sh
source /usr/local/libexec/rpi5-maintenance/rpi5-update-http-health.sh
rpi5_classify_hermes_update_check 0 "Up to date"
rpi5_wait_for_lock_available /run/lock/rpi5-backup.lock 1800
rpi5_applied_packages_require_reboot run "linux-image"
rpi5_find_missing_compose_services "api" "api"
rpi5_build_compose_up_args 240 false
rpi5_enforce_normal_space_gate run
rpi5_application_local_health_targets
rpi5_request_code_with_retry http://127.0.0.1:8088/ 3 5
curl http://127.0.0.1:8089/
docker compose up -d --pull never --no-build --wait --wait-timeout 240
docker image prune -f --filter until=336h
'''

assert module.validate(GOOD) == [], module.validate(GOOD)

cases = {
    "image-prune-all": GOOD.replace("docker image prune -f", "docker image prune -a -f"),
    "network-prune": GOOD + "\ndocker network prune -f\n",
    "remove-orphans": GOOD.replace("--no-build", "--no-build --remove-orphans", 1),
    "legacy-backup-pgrep": GOOD + "\npgrep -af 'backup.sh'\n",
    "cv-lan": GOOD.replace("http://127.0.0.1:8088/", "http://${HOST_IPV4}:8088/", 1),
    "tech-lan": GOOD.replace("http://127.0.0.1:8089/", "http://${HOST_IPV4}:8089/", 1),
    "missing-no-build": GOOD.replace(" --no-build", "", 1),
    "missing-lock-helper": GOOD.replace("rpi5_wait_for_lock_available", "legacy_wait_for_backup", 1),
}

for name, text in cases.items():
    errors = module.validate(text)
    assert errors, f"{name}: unsafe source unexpectedly passed"
    print(f"PASS {name}: {errors[0]}")

print(f"Maintenance updater source validator tests: PASS ({len(cases) + 1} cases)")
