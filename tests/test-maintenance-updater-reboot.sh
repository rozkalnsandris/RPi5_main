#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-reboot.sh
source "$repo/ops/lib/rpi5-update-reboot.sh"

if rpi5_applied_packages_require_reboot check 'raspi-firmware linux-image-rpi-2712'; then
    echo 'check mode incorrectly treated simulated packages as applied' >&2
    exit 1
fi
printf '%s\n' 'PASS simulated-kernel-does-not-require-reboot'

rpi5_applied_packages_require_reboot run 'raspi-firmware linux-image-rpi-2712'
printf '%s\n' 'PASS applied-kernel-requires-reboot'

if rpi5_applied_packages_require_reboot run 'curl git docker-ce'; then
    echo 'ordinary applied packages incorrectly require reboot' >&2
    exit 1
fi
printf '%s\n' 'PASS ordinary-packages-do-not-require-reboot'

printf '%s\n' 'Maintenance updater reboot tests: PASS (3 cases)'
