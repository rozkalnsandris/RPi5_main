#!/usr/bin/env bash
# Shared lock primitives for mutually exclusive RPi5 maintenance mutation jobs.

# util-linux flock reserves this application-chosen status exclusively for
# lock contention/timeout via --conflict-exit-code. Other flock failures retain
# their own documented error status and must not be mislabeled as contention.
readonly RPI5_LOCK_CONFLICT_RC=200

# Acquire and keep an exclusive flock open in this shell. The acquired file
# descriptor is written to the caller-named variable and remains held until it
# is explicitly released or the process exits.
#
# Returns:
#   0   acquired
#   2   invalid arguments / lock-file setup error
#   200 timed out waiting for the exclusive lock
#   other nonzero values are propagated genuine flock errors
rpi5_acquire_exclusive_lock() {
    local lock_file="${1:-}"
    local timeout_seconds="${2:-}"
    local result_var="${3:-}"
    local acquired_fd flock_rc=0

    [[ -n "$lock_file" && -n "$result_var" ]] || return 2
    [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || return 2
    [[ "$result_var" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || return 2

    mkdir -p -- "$(dirname -- "$lock_file")" || return 2
    exec {acquired_fd}>"$lock_file" || return 2

    flock \
        --exclusive \
        --timeout "$timeout_seconds" \
        --conflict-exit-code "$RPI5_LOCK_CONFLICT_RC" \
        "$acquired_fd" || flock_rc=$?
    if (( flock_rc != 0 )); then
        exec {acquired_fd}>&-
        return "$flock_rc"
    fi

    # Do not name the internal descriptor `fd`: Bash variables are dynamically
    # scoped, so a local `fd` would shadow a caller output variable named `fd`.
    printf -v "$result_var" '%s' "$acquired_fd"
    return 0
}

# Non-blocking variant used by migration quiescence checks. It has the same
# result contract as the bounded helper, with 200 meaning lock contention.
rpi5_try_exclusive_lock() {
    local lock_file="${1:-}"
    local result_var="${2:-}"
    local acquired_fd flock_rc=0

    [[ -n "$lock_file" && -n "$result_var" ]] || return 2
    [[ "$result_var" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || return 2

    mkdir -p -- "$(dirname -- "$lock_file")" || return 2
    exec {acquired_fd}>"$lock_file" || return 2

    flock \
        --exclusive \
        --nonblock \
        --conflict-exit-code "$RPI5_LOCK_CONFLICT_RC" \
        "$acquired_fd" || flock_rc=$?
    if (( flock_rc != 0 )); then
        exec {acquired_fd}>&-
        return "$flock_rc"
    fi

    printf -v "$result_var" '%s' "$acquired_fd"
    return 0
}

rpi5_release_exclusive_lock() {
    local fd="${1:-}"

    [[ "$fd" =~ ^[0-9]+$ ]] || return 2
    flock --unlock "$fd" 2>/dev/null || true
    eval "exec ${fd}>&-"
}
