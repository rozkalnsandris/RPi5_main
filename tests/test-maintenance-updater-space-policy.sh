#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-space-policy.sh
source "$repo/ops/lib/rpi5-update-space-policy.sh"

rpi5_enforce_normal_space_gate run
rpi5_enforce_normal_space_gate check

if rpi5_enforce_normal_space_gate cleanup; then
    echo "cleanup mode unexpectedly enforces the normal free-space gate" >&2
    exit 1
else
    rc=$?
    [[ "$rc" -eq 1 ]]
fi

if rpi5_enforce_normal_space_gate invalid; then
    echo "invalid mode unexpectedly accepted" >&2
    exit 1
else
    rc=$?
    [[ "$rc" -eq 2 ]]
fi

printf '%s\n' 'Maintenance updater space policy tests: PASS'
