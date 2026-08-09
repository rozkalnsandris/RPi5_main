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
