#!/usr/bin/env bash
# Shared read-only health classification helpers for RPi5 maintenance checks.

rpi5_container_state_is_healthy() {
    local state="${1:-}"
    local health="${2:-}"

    [[ "$state" == "running" ]] || return 1
    case "$health" in
        ""|none|healthy) return 0 ;;
        *) return 1 ;;
    esac
}

# Input: newline-separated TAB records: name<TAB>state<TAB>health.
# Return 0 when at least one container exists and all are running with either
# no healthcheck or a healthy healthcheck. Return 1 for unhealthy state and 2
# when no container records exist.
rpi5_validate_container_rows() {
    local rows="${1-}"
    local name state health
    local count=0
    local bad=0
    RPI5_BAD_CONTAINERS=""

    while IFS=$'\t' read -r name state health; do
        [[ -n "$name" ]] || continue
        count=$((count + 1))
        health="${health:-none}"
        if ! rpi5_container_state_is_healthy "$state" "$health"; then
            bad=1
            if [[ -n "$RPI5_BAD_CONTAINERS" ]]; then
                RPI5_BAD_CONTAINERS+=$'\n'
            fi
            RPI5_BAD_CONTAINERS+="${name}"$'\t'"${state}"$'\t'"${health}"
        fi
    done <<<"$rows"

    (( count > 0 )) || return 2
    (( bad == 0 ))
}

# Compare an explicit required-container inventory with Docker state rows.
# Required input is one exact container name per line; blank lines and lines
# beginning with # are ignored. Extra historical/stopped containers are ignored.
rpi5_validate_required_container_inventory() {
    local required_names="${1-}"
    local rows="${2-}"
    local name state health required
    local required_count=0
    local bad=0
    declare -A states=()
    declare -A healths=()
    RPI5_BAD_CONTAINERS=""

    while IFS=$'\t' read -r name state health; do
        [[ -n "$name" ]] || continue
        states["$name"]="$state"
        healths["$name"]="${health:-none}"
    done <<<"$rows"

    while IFS= read -r required; do
        [[ -n "$required" ]] || continue
        [[ "$required" == \#* ]] && continue
        required_count=$((required_count + 1))

        if [[ ! -v 'states[$required]' ]]; then
            bad=1
            [[ -z "$RPI5_BAD_CONTAINERS" ]] || RPI5_BAD_CONTAINERS+=$'\n'
            RPI5_BAD_CONTAINERS+="${required}"$'\t'"missing"$'\t'"missing"
            continue
        fi

        state="${states[$required]}"
        health="${healths[$required]}"
        if ! rpi5_container_state_is_healthy "$state" "$health"; then
            bad=1
            [[ -z "$RPI5_BAD_CONTAINERS" ]] || RPI5_BAD_CONTAINERS+=$'\n'
            RPI5_BAD_CONTAINERS+="${required}"$'\t'"${state}"$'\t'"${health}"
        fi
    done <<<"$required_names"

    (( required_count > 0 )) || return 2
    (( bad == 0 ))
}

rpi5_http_code_is_reachable() {
    local code="${1:-000}"
    [[ "$code" =~ ^2[0-9][0-9]$ ||
       "$code" =~ ^3[0-9][0-9]$ ||
       "$code" == "401" ||
       "$code" == "403" ]]
}

rpi5_http_code() {
    local url="${1:?missing URL}"
    local code

    code="$(
        curl -sS -o /dev/null -w '%{http_code}' \
            --connect-timeout 3 --max-time 8 \
            "$url" 2>/dev/null || true
    )"
    [[ "$code" =~ ^[0-9]{3}$ ]] || code="000"
    printf '%s' "$code"
}

rpi5_http_wait_reachable() {
    local url="${1:?missing URL}"
    local attempts="${2:?missing attempts}"
    local delay="${3:?missing delay}"
    local attempt code="000"

    [[ "$attempts" =~ ^[1-9][0-9]*$ ]] || return 2
    [[ "$delay" =~ ^[0-9]+([.][0-9]+)?$ ]] || return 2

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        code="$(rpi5_http_code "$url")"
        if rpi5_http_code_is_reachable "$code"; then
            printf '%s' "$code"
            return 0
        fi
        (( attempt == attempts )) || sleep "$delay"
    done

    printf '%s' "$code"
    return 1
}
