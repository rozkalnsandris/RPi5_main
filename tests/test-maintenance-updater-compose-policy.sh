#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-compose-policy.sh
source "$repo/ops/lib/rpi5-update-compose-policy.sh"

assert_safe() {
    local rollback="$1"
    local token
    rpi5_build_compose_up_args 240 "$rollback"

    local joined=" ${RPI5_COMPOSE_UP_ARGS[*]} "
    [[ "$joined" == *" --pull never "* ]]
    [[ "$joined" == *" --no-build "* ]]
    [[ "$joined" == *" --wait "* ]]
    [[ "$joined" == *" --wait-timeout 240 "* ]]
    [[ "$joined" != *" --remove-orphans "* ]]
    [[ "$joined" != *" --build "* ]]

    if [[ "$rollback" == "true" ]]; then
        [[ "$joined" == *" --force-recreate "* ]]
    else
        [[ "$joined" != *" --force-recreate "* ]]
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
