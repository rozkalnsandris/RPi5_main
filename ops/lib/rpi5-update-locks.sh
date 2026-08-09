#!/usr/bin/env bash
# Lock helpers for the weekly updater.

# Return 0 when another process currently holds an exclusive flock on the
# supplied lock file, 1 when the lock is currently available, and >1 on a
# probe/setup error. The probe releases an acquired lock immediately.
rpi5_lock_is_held() {
    local lock_file="${1:?missing lock file}"
    local fd

    mkdir -p -- "$(dirname -- "$lock_file")" || return 2
    exec {fd}>"$lock_file" || return 2

    if flock -n "$fd"; then
        flock -u "$fd" || true
        exec {fd}>&-
        return 1
    fi

    exec {fd}>&-
    return 0
}

# Wait for the supplied lock to become available, then release the probe lock.
# Return 0 when availability was observed, 75 when the timeout elapsed, and
# >1 for invalid input/setup errors. The weekly updater uses this before any
# mutation so a slightly long nightly backup does not silently skip the week.
rpi5_wait_for_lock_available() {
    local lock_file="${1:?missing lock file}"
    local timeout_seconds="${2:?missing lock wait timeout}"
    local fd rc=0

    [[ "$timeout_seconds" =~ ^[0-9]+$ ]] || return 2
    (( timeout_seconds > 0 )) || return 2

    mkdir -p -- "$(dirname -- "$lock_file")" || return 3
    exec {fd}>"$lock_file" || return 3

    flock -E 75 -w "$timeout_seconds" "$fd" || rc=$?
    if [[ "$rc" -eq 0 ]]; then
        flock -u "$fd" || true
    fi
    exec {fd}>&-

    return "$rc"
}
