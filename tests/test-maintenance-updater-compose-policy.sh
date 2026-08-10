#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
helper="$repo/ops/lib/rpi5-update-compose-policy.sh"
updater="$repo/ops/bin/rpi5-update"
# shellcheck source=../ops/lib/rpi5-update-compose-policy.sh
source "$helper"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
mkdir -p "$project"

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

assert_common_safe_args() {
    contains_arg -d "${RPI5_COMPOSE_UP_ARGS[@]}"
    assert_pair --pull never "${RPI5_COMPOSE_UP_ARGS[@]}"
    contains_arg --no-build "${RPI5_COMPOSE_UP_ARGS[@]}"
    contains_arg --wait "${RPI5_COMPOSE_UP_ARGS[@]}"
    assert_pair --wait-timeout 240 "${RPI5_COMPOSE_UP_ARGS[@]}"
    contains_arg --no-deps "${RPI5_COMPOSE_UP_ARGS[@]}"
    ! contains_arg --remove-orphans "${RPI5_COMPOSE_UP_ARGS[@]}"
    ! contains_arg --build "${RPI5_COMPOSE_UP_ARGS[@]}"
}

SCENARIO=''

rpi5_compose_service_inventory() {
    case "$SCENARIO" in
        mixed-changed|mixed-unchanged|mixed-drift|mixed-rollback)
            printf '%s\n' \
                $'cv\tregistry\tnginx:stable' \
                $'cvbot\tbuildable\trozkalns-cv-cvbot:local'
            ;;
        all-buildable)
            printf '%s\n' \
                $'cvbot\tbuildable\trozkalns-cv-cvbot:local'
            ;;
        *)
            return 2
            ;;
    esac
}

rpi5_compose_service_container_id() {
    printf 'container-%s\n' "$2"
}

rpi5_container_image_id() {
    case "$SCENARIO:$1" in
        mixed-changed:container-cv|mixed-drift:container-cv|mixed-rollback:container-cv)
            printf '%s\n' 'sha256:old-registry-image'
            ;;
        mixed-unchanged:container-cv)
            printf '%s\n' 'sha256:new-registry-image'
            ;;
        *)
            return 2
            ;;
    esac
}

rpi5_local_image_id() {
    [[ "$1" == 'nginx:stable' ]] || return 2
    printf '%s\n' 'sha256:new-registry-image'
}

rpi5_container_compose_config_hash() {
    case "$SCENARIO" in
        mixed-drift)
            printf '%s\n' 'old-config-hash'
            ;;
        *)
            printf '%s\n' 'same-config-hash'
            ;;
    esac
}

rpi5_compose_service_config_hash() {
    case "$SCENARIO" in
        mixed-drift)
            printf '%s\n' 'new-config-hash'
            ;;
        *)
            printf '%s\n' 'same-config-hash'
            ;;
    esac
}

SCENARIO='mixed-changed'
rpi5_build_compose_up_args 240 false "$project"
assert_common_safe_args
contains_arg cv "${RPI5_COMPOSE_UP_ARGS[@]}"
! contains_arg cvbot "${RPI5_COMPOSE_UP_ARGS[@]}"
! contains_arg --no-recreate "${RPI5_COMPOSE_UP_ARGS[@]}"
! contains_arg --force-recreate "${RPI5_COMPOSE_UP_ARGS[@]}"
[[ "$RPI5_COMPOSE_UPDATE_MODE" == 'changed-registry-images' ]]
[[ "${RPI5_COMPOSE_CHANGED_REGISTRY_SERVICES[*]}" == 'cv' ]]
[[ "${RPI5_COMPOSE_BUILDABLE_SERVICES[*]}" == 'cvbot' ]]

SCENARIO='mixed-rollback'
rpi5_build_compose_up_args 240 true "$project"
assert_common_safe_args
contains_arg --force-recreate "${RPI5_COMPOSE_UP_ARGS[@]}"
contains_arg cv "${RPI5_COMPOSE_UP_ARGS[@]}"
! contains_arg cvbot "${RPI5_COMPOSE_UP_ARGS[@]}"

SCENARIO='mixed-unchanged'
rpi5_build_compose_up_args 240 false "$project"
assert_common_safe_args
contains_arg --no-recreate "${RPI5_COMPOSE_UP_ARGS[@]}"
contains_arg cv "${RPI5_COMPOSE_UP_ARGS[@]}"
contains_arg cvbot "${RPI5_COMPOSE_UP_ARGS[@]}"
! contains_arg --force-recreate "${RPI5_COMPOSE_UP_ARGS[@]}"
[[ "$RPI5_COMPOSE_UPDATE_MODE" == 'no-image-change-no-recreate' ]]

SCENARIO='all-buildable'
rpi5_build_compose_up_args 240 false "$project"
assert_common_safe_args
contains_arg --no-recreate "${RPI5_COMPOSE_UP_ARGS[@]}"
contains_arg cvbot "${RPI5_COMPOSE_UP_ARGS[@]}"
! contains_arg --force-recreate "${RPI5_COMPOSE_UP_ARGS[@]}"
[[ "${#RPI5_COMPOSE_CHANGED_REGISTRY_SERVICES[@]}" -eq 0 ]]

SCENARIO='mixed-drift'
if rpi5_build_compose_up_args 240 false "$project"; then
    echo 'registry image change with Compose config drift unexpectedly accepted' >&2
    exit 1
else
    rc=$?
fi
[[ "$rc" -eq 3 ]]
[[ "$RPI5_COMPOSE_CONFIG_DRIFT_SERVICE" == 'cv' ]]

# Lock the real updater call shape: update_compose_project owns local
# project_dir and calls the policy with two arguments. Bash dynamic scoping then
# supplies that path to the helper without changing the provenance-bound V25
# updater source.
grep -Fq 'local project_name="$1"' "$updater"
grep -Fq 'local project_dir="$2"' "$updater"
grep -Fq 'rpi5_build_compose_up_args "$COMPOSE_WAIT_TIMEOUT" false' "$updater"
grep -Fq 'rpi5_build_compose_up_args "$COMPOSE_WAIT_TIMEOUT" true' "$updater"

SCENARIO='mixed-changed'
call_like_updater() {
    local project_dir="$project"
    rpi5_build_compose_up_args 240 false
}
call_like_updater
contains_arg cv "${RPI5_COMPOSE_UP_ARGS[@]}"
! contains_arg cvbot "${RPI5_COMPOSE_UP_ARGS[@]}"

if rpi5_build_compose_up_args not-a-number false "$project"; then
    echo 'invalid timeout unexpectedly accepted' >&2
    exit 1
fi
if rpi5_build_compose_up_args 240 maybe "$project"; then
    echo 'invalid rollback flag unexpectedly accepted' >&2
    exit 1
fi
if rpi5_build_compose_up_args 240 false "$tmp/missing-project"; then
    echo 'missing Compose project unexpectedly accepted' >&2
    exit 1
fi

bash -n "$helper"

printf '%s\n' 'Maintenance updater Compose policy tests: PASS'
