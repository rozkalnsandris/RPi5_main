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
    "/run/lock/rpi5-backup.lock",
    "/usr/local/libexec/rpi5-maintenance",
    "BACKUP_WAIT_TIMEOUT",
    "rpi5_classify_hermes_update_check",
    "rpi5_wait_for_lock_available",
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


def validate(text: str) -> list[str]:
    errors: list[str] = []

    for marker in REQUIRED_MARKERS:
        if marker not in text:
            errors.append(f"missing required marker: {marker}")

    normalized = re.sub(r"\\\n[ \t]*", " ", text)

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
