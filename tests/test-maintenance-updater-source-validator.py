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
BACKUP_LOCK=/run/lock/rpi5-backup.lock
LIBEXEC=/usr/local/libexec/rpi5-maintenance
BACKUP_WAIT_TIMEOUT=1800
# Supported: --check --no-reboot --cleanup-only
source "$LIBEXEC/rpi5-update-hermes-status.sh"
source "$LIBEXEC/rpi5-update-locks.sh"
source "$LIBEXEC/rpi5-update-reboot.sh"
source "$LIBEXEC/rpi5-update-compose-health.sh"
source "$LIBEXEC/rpi5-update-compose-policy.sh"
source "$LIBEXEC/rpi5-update-space-policy.sh"
source "$LIBEXEC/rpi5-update-origin-policy.sh"
source "$LIBEXEC/rpi5-update-http-health.sh"
TELEGRAM_HELPER="$LIBEXEC/rpi5-update-telegram.py"
rpi5_classify_hermes_update_check 0 "Up to date"
rpi5_wait_for_lock_available "$BACKUP_LOCK" "$BACKUP_WAIT_TIMEOUT"
rpi5_applied_packages_require_reboot run "linux-image"
rpi5_find_missing_compose_services "api" "api"
rpi5_build_compose_up_args 240 false
rpi5_enforce_normal_space_gate run
rpi5_application_local_health_targets
rpi5_request_code_with_retry https://example.invalid/ 3 5
printf '%s\0%s\0%s' "$TELEGRAM_TOKEN" "$CHAT_ID" "$text" | python3 "$TELEGRAM_HELPER"
docker compose up "${RPI5_COMPOSE_UP_ARGS[@]}"
rpi5_build_compose_up_args 240 true
docker compose up "${RPI5_COMPOSE_UP_ARGS[@]}"
docker image prune -f --filter until=336h
'''

assert module.validate(GOOD) == [], module.validate(GOOD)

cases = {
    "image-prune-all": GOOD.replace("docker image prune -f", "docker image prune -a -f"),
    "network-prune": GOOD + "\ndocker network prune -f\n",
    "image-prune-all-capability": GOOD + '\nrequire_help_flag "docker image prune" "--all" docker image prune\n',
    "network-prune-capability": GOOD + '\nrequire_help_flag "docker network prune" "--filter" docker network prune\n',
    "remove-orphans": GOOD + "\ndocker compose up --remove-orphans\n",
    "direct-build": GOOD + "\ndocker compose up --build\n",
    "legacy-backup-pgrep": GOOD + "\npgrep -af 'backup.sh'\n",
    "cv-lan": GOOD + "\nprintf '%s' 'http://${HOST_IPV4}:8088/'\n",
    "tech-lan": GOOD + "\nprintf '%s' 'http://${HOST_IPV4}:8089/'\n",
    "missing-compose-helper-routing": GOOD.replace(
        'docker compose up "${RPI5_COMPOSE_UP_ARGS[@]}"',
        'docker compose up -d --pull never',
        1,
    ),
    "missing-origin-helper": GOOD.replace("rpi5_application_local_health_targets", "legacy_origin_list", 1),
    "missing-lock-helper": GOOD.replace("rpi5_wait_for_lock_available", "legacy_wait_for_backup", 1),
    "missing-telegram-helper": GOOD.replace("rpi5-update-telegram.py", "legacy-notifier.py", 1),
    "telegram-child-env": GOOD + '\nTELEGRAM_TOKEN="$TELEGRAM_TOKEN" TELEGRAM_CHAT_ID="$CHAT_ID" python3 notifier.py\n',
}

for name, text in cases.items():
    errors = module.validate(text)
    assert errors, f"{name}: unsafe source unexpectedly passed"
    print(f"PASS {name}: {errors[0]}")

print(f"Maintenance updater source validator tests: PASS ({len(cases) + 1} cases)")
