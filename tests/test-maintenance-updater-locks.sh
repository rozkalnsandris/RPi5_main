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

rm -f -- "$ready"
(
    exec 8>"$lock"
    flock 8
    : >"$ready"
    sleep 0.2
) &
holder_pid=$!
for _ in $(seq 1 100); do
    [[ -e "$ready" ]] && break
    sleep 0.02
done
rpi5_wait_for_lock_available "$lock" 2
wait "$holder_pid"
holder_pid=""
printf '%s\n' 'PASS backup-lock-bounded-wait-success'

rm -f -- "$ready"
(
    exec 8>"$lock"
    flock 8
    : >"$ready"
    sleep 5
) &
holder_pid=$!
for _ in $(seq 1 100); do
    [[ -e "$ready" ]] && break
    sleep 0.02
done
rc=0
rpi5_wait_for_lock_available "$lock" 1 || rc=$?
[[ "$rc" -eq 75 ]] || {
    echo "expected lock wait timeout to return 75, got $rc" >&2
    exit 1
}
printf '%s\n' 'PASS backup-lock-bounded-wait-timeout'

kill "$holder_pid" 2>/dev/null || true
wait "$holder_pid" 2>/dev/null || true
holder_pid=""

rc=0
rpi5_wait_for_lock_available "$lock" invalid || rc=$?
[[ "$rc" -eq 2 ]]
printf '%s\n' 'PASS backup-lock-invalid-timeout'

printf '%s\n' 'Maintenance updater backup lock tests: PASS (6 cases)'
