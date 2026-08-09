#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-maintenance-locks.sh
source "$repo/ops/lib/rpi5-maintenance-locks.sh"

bash -n "$repo/ops/lib/rpi5-maintenance-locks.sh"
[[ "$RPI5_LOCK_CONFLICT_RC" -eq 200 ]]

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
shared="$work/shared.lock"
updater_private="$work/updater.lock"
backup_private="$work/backup.lock"

fd=""
rpi5_acquire_exclusive_lock "$shared" 1 fd
[[ "$fd" =~ ^[0-9]+$ ]]
rpi5_release_exclusive_lock "$fd"
printf '%s\n' 'PASS shared-lock-acquire-release'

(
    exec 8>"$shared"
    flock -x 8
    sleep 2
) &
holder=$!
sleep 0.2
rc=0
blocked_fd=""
rpi5_acquire_exclusive_lock "$shared" 1 blocked_fd || rc=$?
[[ "$rc" -eq "$RPI5_LOCK_CONFLICT_RC" ]]
wait "$holder"
printf '%s\n' 'PASS bounded-contention-returns-200'

(
    exec 8>"$shared"
    flock -x 8
    sleep 1
) &
holder=$!
sleep 0.2
rc=0
blocked_fd=""
rpi5_try_exclusive_lock "$shared" blocked_fd || rc=$?
[[ "$rc" -eq "$RPI5_LOCK_CONFLICT_RC" ]]
wait "$holder"
printf '%s\n' 'PASS nonblocking-contention-returns-200'

rc=0
rpi5_acquire_exclusive_lock "$shared" invalid fd || rc=$?
[[ "$rc" -eq 2 ]]
printf '%s\n' 'PASS invalid-timeout-returns-2'

# A genuine flock failure must remain distinguishable from contention. Shell
# function lookup shadows the executable for this focused helper test.
flock() { return 66; }
rc=0
error_fd=""
rpi5_try_exclusive_lock "$work/error.lock" error_fd || rc=$?
[[ "$rc" -eq 66 ]]
unset -f flock
printf '%s\n' 'PASS genuine-flock-error-propagated'

# Runtime model matching the actual repository entrypoints:
#   updater: updater-private -> shared
#   backup:  shared -> backup-private
# Each process writes START/ENTER/EXIT markers. ENTER/EXIT critical sections
# must never overlap and both start orders must complete without deadlock.
run_updater_model() {
    local trace=$1 delay=${2:-0}
    sleep "$delay"
    printf 'U START\n' >>"$trace"
    exec 7>"$updater_private"
    flock -x 7
    exec 8>"$shared"
    flock -x 8
    printf 'U ENTER\n' >>"$trace"
    sleep 0.35
    printf 'U EXIT\n' >>"$trace"
}

run_backup_model() {
    local trace=$1 delay=${2:-0}
    sleep "$delay"
    printf 'B START\n' >>"$trace"
    exec 8>"$shared"
    flock -x 8
    # Exact core acquires its duplicate-backup lock after wrapper shared lock.
    exec 7>"$backup_private"
    flock -x 7
    printf 'B ENTER\n' >>"$trace"
    sleep 0.35
    printf 'B EXIT\n' >>"$trace"
}

assert_serial_trace() {
    local trace=$1
    python3 - "$trace" <<'PY'
import sys
from pathlib import Path
lines=Path(sys.argv[1]).read_text().splitlines()
assert lines.count('U ENTER') == 1 and lines.count('U EXIT') == 1
assert lines.count('B ENTER') == 1 and lines.count('B EXIT') == 1
u1,u2=lines.index('U ENTER'),lines.index('U EXIT')
b1,b2=lines.index('B ENTER'),lines.index('B EXIT')
assert u2 < b1 or b2 < u1, lines
PY
}

trace="$work/backup-first.trace"
run_backup_model "$trace" 0 & bpid=$!
run_updater_model "$trace" 0.05 & upid=$!
wait "$bpid" "$upid"
assert_serial_trace "$trace"
printf '%s\n' 'PASS backup-first-actual-order-serializes'

: >"$shared"
: >"$updater_private"
: >"$backup_private"
trace="$work/updater-first.trace"
run_updater_model "$trace" 0 & upid=$!
run_backup_model "$trace" 0.05 & bpid=$!
wait "$upid" "$bpid"
assert_serial_trace "$trace"
printf '%s\n' 'PASS updater-first-actual-order-serializes'

printf '%s\n' 'Maintenance shared-lock tests: PASS'
