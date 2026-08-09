#!/usr/bin/env bash
# HTTP health helpers for the weekly RPi5 updater.
# Retry diagnostics are written to stderr so callers may safely capture only
# the final HTTP status code from stdout.

rpi5_request_code() {
    local url="${1:?missing URL}"
    local code

    code="$(
        curl -sS -o /dev/null -w '%{http_code}' \
            --connect-timeout 3 \
            --max-time 8 \
            "$url" 2>/dev/null || true
    )"

    [[ "$code" =~ ^[0-9]{3}$ ]] || code="000"
    printf '%s' "$code"
}

rpi5_code_is_reachable() {
    local code="${1:-000}"
    [[ "$code" =~ ^2[0-9][0-9]$ ||
       "$code" =~ ^3[0-9][0-9]$ ||
       "$code" == "401" ||
       "$code" == "403" ]]
}

rpi5_request_code_with_retry() {
    local url="${1:?missing URL}"
    local attempts="${2:?missing attempt count}"
    local delay="${3:?missing retry delay}"
    local attempt code

    [[ "$attempts" =~ ^[1-9][0-9]*$ ]] || return 2
    [[ "$delay" =~ ^[0-9]+([.][0-9]+)?$ ]] || return 2

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        code="$(rpi5_request_code "$url")"
        if rpi5_code_is_reachable "$code"; then
            printf '%s' "$code"
            return 0
        fi

        if (( attempt < attempts )); then
            printf '[health] attempt %d/%d: %s -> HTTP %s; retry in %ss\n' \
                "$attempt" "$attempts" "$url" "$code" "$delay" >&2
            sleep "$delay"
        fi
    done

    printf '%s' "$code"
    return 1
}
