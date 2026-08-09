#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-compose-policy.sh
source "$repo/ops/lib/rpi5-update-compose-policy.sh"

contains_arg() {
    local wanted="$1"
    shift
    local arg
    for arg in "$@"; do
        [[ "$arg" == "$wanted" ]] && return 0
    done
    return 1
}

assert_pair() {
    local key="$1" value="$2"
    shift 2
    local -a args=("$@")
    local i
    for ((i = 0; i + 1 < ${#args[@]}; i++)); do
        if [[ "${args[$i]}" == "$key" && "${args[$((i + 1))]}" == "$value" ]]; then
            return 0
        fi
    done
    return 1
}

assert_safe() {
    local rollback="$1"
    local token
    rpi5_build_compose_up_args 240 "$rollback"

    contains_arg -d "${RPI5_COMPOSE_UP_ARGS[@]}"
    assert_pair --pull never "${RPI5_COMPOSE_UP_ARGS[@]}"
    contains_arg --no-build "${RPI5_COMPOSE_UP_ARGS[@]}"
    contains_arg --wait "${RPI5_COMPOSE_UP_ARGS[@]}"
    assert_pair --wait-timeout 240 "${RPI5_COMPOSE_UP_ARGS[@]}"
    ! contains_arg --remove-orphans "${RPI5_COMPOSE_UP_ARGS[@]}"
    ! contains_arg --build "${RPI5_COMPOSE_UP_ARGS[@]}"

    if [[ "$rollback" == "true" ]]; then
        contains_arg --force-recreate "${RPI5_COMPOSE_UP_ARGS[@]}"
    else
        ! contains_arg --force-recreate "${RPI5_COMPOSE_UP_ARGS[@]}"
    fi

    for token in "${RPI5_COMPOSE_UP_ARGS[@]}"; do
        [[ -n "$token" ]]
    done
}

assert_safe false
assert_safe true

if rpi5_build_compose_up_args not-a-number false; then
    echo "invalid timeout unexpectedly accepted" >&2
    exit 1
fi
if rpi5_build_compose_up_args 240 maybe; then
    echo "invalid rollback flag unexpectedly accepted" >&2
    exit 1
fi

printf '%s\n' 'Maintenance updater Compose policy tests: PASS'
