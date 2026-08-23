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
MAINTENANCE_LOCK=/run/lock/rpi5-maintenance-exclusive.lock
LIBEXEC=/usr/local/lib/rpi5-maintenance
MAINTENANCE_LOCK_TIMEOUT=1800
HOST_IPV4="${HOST_IPV4:-}"
UPDATE_HOME="$(getent passwd "$UPDATE_USER" | awk -F: 'NR==1 {print $6}')"
MAIN_COMPOSE_DIR="${MAIN_COMPOSE_DIR:-${UPDATE_HOME}/docker}"
HERMES_BIN="${HERMES_BIN:-${UPDATE_HOME}/.local/bin/hermes}"
# Supported: --check --no-reboot --cleanup-only
source "$LIBEXEC/rpi5-update-hermes-status.sh"
source "$LIBEXEC/rpi5-update-locks.sh"
source "$LIBEXEC/rpi5-maintenance-locks.sh"
source "$LIBEXEC/rpi5-update-apt-policy.sh"
source "$LIBEXEC/rpi5-update-reboot.sh"
source "$LIBEXEC/rpi5-update-compose-health.sh"
source "$LIBEXEC/rpi5-update-compose-policy.sh"
source "$LIBEXEC/rpi5-update-space-policy.sh"
source "$LIBEXEC/rpi5-update-origin-policy.sh"
source "$LIBEXEC/rpi5-update-http-health.sh"
TELEGRAM_HELPER="$LIBEXEC/rpi5-update-telegram.py"
rpi5_classify_hermes_update_check 0 "Up to date"
RPI5_LOCK_CONFLICT_RC=200
rpi5_acquire_exclusive_lock "$MAINTENANCE_LOCK" "$MAINTENANCE_LOCK_TIMEOUT" MAINTENANCE_LOCK_FD
rpi5_prepare_apt_metadata check -o Acquire::Retries=3
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
CURRENT_PHASE="veselības pārbaudes"
CURRENT_PHASE="Hermes update check"
"$HERMES_BIN" update --check
CURRENT_PHASE="gala atskaite"
'''

assert module.validate(GOOD) == [], module.validate(GOOD)

cases = {
    "forbidden-local-libexec": GOOD + "\nOLD=/usr/local/libexec/rpi5-maintenance\n",
    "forbidden-backup-private-lock": GOOD + "\nOLD=/run/lock/rpi5-backup.lock\n",
    "legacy-backup-lock-helper": GOOD + "\nrpi5_wait_for_lock_available /run/lock/legacy.lock 10\n",
    "concrete-user-home": GOOD + "\nLEGACY=/home/example-user/runtime/\n",
    "private-ipv4-10": GOOD + "\nLEGACY_HOST=10.20.30.40\n",
    "private-ipv4-172": GOOD + "\nLEGACY_HOST=172.20.30.40\n",
    "private-ipv4-192": GOOD + "\nLEGACY_HOST=192.168.50.25\n",
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
    "missing-shared-lock-helper": GOOD.replace("rpi5_acquire_exclusive_lock", "legacy_wait_for_backup", 1),
    "missing-lock-library": GOOD.replace("rpi5-maintenance-locks.sh", "legacy-locks.sh", 1),
    "missing-apt-policy-library": GOOD.replace("rpi5-update-apt-policy.sh", "legacy-apt-policy.sh", 1),
    "missing-apt-policy-routing": GOOD.replace("rpi5_prepare_apt_metadata", "legacy_apt_refresh", 1),
    "direct-apt-metadata-refresh": GOOD + "\napt-get --error-on=any update\n",
    "missing-conflict-code": GOOD.replace("RPI5_LOCK_CONFLICT_RC", "LEGACY_LOCK_RC", 1),
    "missing-telegram-helper": GOOD.replace("rpi5-update-telegram.py", "legacy-notifier.py", 1),
    "telegram-child-env": GOOD + '\nTELEGRAM_TOKEN="$TELEGRAM_TOKEN" TELEGRAM_CHAT_ID="$CHAT_ID" python3 notifier.py\n',
    "hermes-auto-toggle": GOOD + "\nHERMES_UPDATE=yes\n",
    "hermes-backup-toggle": GOOD + "\nHERMES_BACKUP=yes\n",
    "hermes-status-gate": GOOD + "\nHERMES_STATUS=1\n",
    "hermes-unattended-update": GOOD + '\n"$HERMES_BIN" update --yes\n',
    "hermes-dashboard-stop": GOOD + "\nsystemctl stop hermes-dashboard.service\n",
    "hermes-dashboard-restart": GOOD + "\nsystemctl restart hermes-dashboard.service\n",
    "hermes-doctor-in-updater": GOOD + '\n"$HERMES_BIN" doctor\n',
    "hermes-check-before-health": GOOD.replace(
        'CURRENT_PHASE="veselības pārbaudes"\nCURRENT_PHASE="Hermes update check"\n"$HERMES_BIN" update --check',
        'CURRENT_PHASE="Hermes update check"\n"$HERMES_BIN" update --check\nCURRENT_PHASE="veselības pārbaudes"',
        1,
    ),
    "hermes-check-after-report": GOOD.replace(
        'CURRENT_PHASE="Hermes update check"\n"$HERMES_BIN" update --check\nCURRENT_PHASE="gala atskaite"',
        'CURRENT_PHASE="gala atskaite"\nCURRENT_PHASE="Hermes update check"\n"$HERMES_BIN" update --check',
        1,
    ),
}

for name, text in cases.items():
    errors = module.validate(text)
    assert errors, f"{name}: unsafe source unexpectedly passed"
    print(f"PASS {name}: {errors[0]}")

print(f"Maintenance updater source validator tests: PASS ({len(cases) + 1} cases)")
