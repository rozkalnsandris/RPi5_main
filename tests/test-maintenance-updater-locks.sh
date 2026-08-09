#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-locks.sh
source "$repo/ops/lib/rpi5-update-locks.sh"

tmp="$(mktemp -d)"
holder_pid=""
cleanup() {
    if [[ -n "$holder_pid" ]]; then
        kill "$holder_pid" 2>/dev/null || true
        wait "$holder_pid" 2>/dev/null || true
    fi
    rm -rf -- "$tmp"
}
trap cleanup EXIT

lock="$tmp/rpi5-backup.lock"
ready="$tmp/ready"

rc=0
rpi5_lock_is_held "$lock" || rc=$?
[[ "$rc" -eq 1 ]] || {
    echo "expected an available lock to return 1, got $rc" >&2
    exit 1
}
printf '%s\n' 'PASS backup-lock-available'

(
    exec 8>"$lock"
    flock 8
    : >"$ready"
    sleep 30
) &
holder_pid=$!

for _ in $(seq 1 100); do
    [[ -e "$ready" ]] && break
    sleep 0.02
done
[[ -e "$ready" ]] || {
    echo "synthetic lock holder did not become ready" >&2
    exit 1
}

rpi5_lock_is_held "$lock"
printf '%s\n' 'PASS backup-lock-held'

kill "$holder_pid" 2>/dev/null || true
wait "$holder_pid" 2>/dev/null || true
holder_pid=""

rc=0
rpi5_lock_is_held "$lock" || rc=$?
[[ "$rc" -eq 1 ]] || {
    echo "expected a released lock to return 1, got $rc" >&2
    exit 1
}
printf '%s\n' 'PASS backup-lock-released'

printf '%s\n' 'Maintenance updater backup lock tests: PASS (3 cases)'
