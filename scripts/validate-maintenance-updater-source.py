#!/usr/bin/env python3
"""Validate safety properties required of the reviewed RPi5 updater successor."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED_MARKERS = (
    "set -Eeuo pipefail",
    "umask 077",
    "/etc/rpi-update.conf",
    "/run/lock/rpi5-update.lock",
    "/run/lock/rpi5-maintenance-exclusive.lock",
    "/usr/local/lib/rpi5-maintenance",
    "MAINTENANCE_LOCK_TIMEOUT",
    "rpi5-maintenance-locks.sh",
    "rpi5-update-apt-policy.sh",
    "rpi5_acquire_exclusive_lock",
    "RPI5_LOCK_CONFLICT_RC",
    "rpi5_prepare_apt_metadata",
    'HOST_IPV4="${HOST_IPV4:-}"',
    'MAIN_COMPOSE_DIR="${MAIN_COMPOSE_DIR:-${UPDATE_HOME}/docker}"',
    'HERMES_BIN="${HERMES_BIN:-${UPDATE_HOME}/.local/bin/hermes}"',
    "rpi5_classify_hermes_update_check",
    'CURRENT_PHASE="Hermes update check"',
    '"$HERMES_BIN" update --check',
    "rpi5_applied_packages_require_reboot",
    "rpi5_find_missing_compose_services",
    "rpi5_build_compose_up_args",
    "rpi5_enforce_normal_space_gate",
    "rpi5_application_local_health_targets",
    "rpi5_request_code_with_retry",
    "rpi5-update-telegram.py",
    "--check",
    "--no-reboot",
    "--cleanup-only",
)

SAFE_COMPOSE_UP = 'docker compose up "${RPI5_COMPOSE_UP_ARGS[@]}"'
FORBIDDEN_LOCAL_LIBEXEC = "/usr/local/libexec/rpi5-maintenance"
FORBIDDEN_HERMES_FATAL_PREFLIGHT = 'require_help_flag "hermes update" "--check"'
FORBIDDEN_HERMES_AUTOMATION_MARKERS = (
    "HERMES_UPDATE",
    "HERMES_BACKUP",
    "HERMES_STATUS",
    "update --yes",
    "systemctl stop hermes-dashboard.service",
    "systemctl restart hermes-dashboard.service",
    '"$HERMES_BIN" doctor',
)
PRIVATE_IPV4_PATTERNS = (
    r"(?<![0-9])10(?:\.[0-9]{1,3}){3}(?![0-9])",
    r"(?<![0-9])192\.168(?:\.[0-9]{1,3}){2}(?![0-9])",
    r"(?<![0-9])172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2}(?![0-9])",
)


def validate(text: str) -> list[str]:
    errors: list[str] = []

    for marker in REQUIRED_MARKERS:
        if marker not in text:
            errors.append(f"missing required marker: {marker}")

    normalized = re.sub(r"\\\n[ \t]*", " ", text)

    if FORBIDDEN_LOCAL_LIBEXEC in text:
        errors.append("tracked updater uses non-FHS /usr/local/libexec maintenance path")
    if re.search(r"/home/[A-Za-z0-9._-]+/", text):
        errors.append("tracked updater contains a concrete user-home path")
    if any(re.search(pattern, text) for pattern in PRIVATE_IPV4_PATTERNS):
        errors.append("tracked updater contains a concrete RFC1918 IPv4 address")

    for marker in FORBIDDEN_HERMES_AUTOMATION_MARKERS:
        if marker in text:
            errors.append(f"weekly updater contains forbidden Hermes mutation marker: {marker}")

    if FORBIDDEN_HERMES_FATAL_PREFLIGHT in text:
        errors.append(
            "Hermes advisory update check must not have a fatal capability preflight gate"
        )

    health_phase = text.find('CURRENT_PHASE="veselības pārbaudes"')
    hermes_phase = text.find('CURRENT_PHASE="Hermes update check"')
    hermes_check = text.find('"$HERMES_BIN" update --check')
    final_phase = text.find('CURRENT_PHASE="gala atskaite"')
    if not (
        health_phase >= 0
        and hermes_phase > health_phase
        and hermes_check > hermes_phase
        and final_phase > hermes_check
    ):
        errors.append(
            "Hermes update check must be read-only and ordered after health checks and before final report"
        )

    if "/run/lock/rpi5-backup.lock" in text:
        errors.append("updater still depends on backup-private lock instead of shared maintenance lock")
    if "rpi5_wait_for_lock_available" in text:
        errors.append("updater still uses legacy backup-lock probe semantics")

    if text.count(SAFE_COMPOSE_UP) < 2:
        errors.append("Compose recreate/rollback are not both routed through the reviewed argument helper")

    image_prune_commands = re.findall(
        r"docker\s+image\s+prune\b[^\n;]*", normalized, flags=re.IGNORECASE
    )
    for command in image_prune_commands:
        tokens = command.split()
        if "-a" in tokens or "--all" in tokens:
            errors.append("unattended docker image prune uses -a/--all")
            break

    if re.search(r"\bdocker\s+network\s+prune\b", normalized):
        errors.append("unattended docker network prune is forbidden")

    if 'require_help_flag "docker image prune" "--all"' in text:
        errors.append("obsolete docker image prune --all capability gate remains")
    if 'require_help_flag "docker network prune"' in text:
        errors.append("obsolete docker network prune capability gate remains")

    if "--remove-orphans" in normalized:
        errors.append("unattended Compose --remove-orphans is forbidden")
    if re.search(r"\bdocker\s+compose\s+up\b[^\n;]*--build\b", normalized):
        errors.append("generic host maintenance may not build application images")

    if re.search(r"\bpgrep\b[^\n]*(backup\\?\.sh|rpi5[^\n]*backup)", normalized):
        errors.append("backup overlap still depends on process-name matching")

    if re.search(r"HOST_IPV4[^\n]*:8088", normalized):
        errors.append("CV local health regressed from loopback to HOST_IPV4")
    if re.search(r"HOST_IPV4[^\n]*:8089", normalized):
        errors.append("Hermes Tech local health regressed from loopback to HOST_IPV4")

    if re.search(
        r"(?m)^\s*TELEGRAM_(?:TOKEN|CHAT_ID)=[^\n]*\$TELEGRAM_(?:TOKEN|CHAT_ID)",
        text,
    ):
        errors.append("Telegram credential is exported through a child process environment")

    if "--error-on=any update" in text:
        errors.append("APT metadata refresh bypasses the reviewed APT policy helper")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()

    candidate = args.candidate
    if candidate.is_symlink() or not candidate.is_file():
        print(f"ERROR unsafe or missing candidate: {candidate}")
        return 2

    text = candidate.read_text(encoding="utf-8")
    errors = validate(text)
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1

    print("Maintenance updater source policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
