#!/usr/bin/env bash
# Safe Docker Compose argument policy for the weekly RPi5 updater.
#
# Generic host maintenance may pull registry-backed images, but it must never
# turn a locally buildable service into an implicit application deployment.
# The updater's update_compose_project() owns a local `project_dir`; Bash local
# variables are dynamically scoped, so the existing two-argument caller is
# supported while tests/operators may pass the project directory explicitly as
# the optional third argument.

rpi5_compose_service_inventory() {
    local project_dir="${1:?missing compose project directory}"
    local rendered

    rendered="$((
        cd "$project_dir"
        docker compose config --format json
    ))" || return 2

    printf '%s' "$rendered" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
services = payload.get("services")
if not isinstance(services, dict) or not services:
    raise SystemExit(2)

for name in sorted(services):
    spec = services[name]
    if not isinstance(spec, dict):
        raise SystemExit(2)
    image = str(spec.get("image") or "")
    if spec.get("build") is not None:
        kind = "buildable"
    elif image:
        kind = "registry"
    else:
        raise SystemExit(2)
    print(f"{name}\t{kind}\t{image}")
' || return 2
}

rpi5_compose_service_container_id() {
    local project_dir="${1:?missing compose project directory}"
    local service="${2:?missing compose service}"
    (
        cd "$project_dir"
        docker compose ps -q "$service"
    ) | awk 'NF {print; exit}'
}

rpi5_compose_service_config_hash() {
    local project_dir="${1:?missing compose project directory}"
    local service="${2:?missing compose service}"
    (
        cd "$project_dir"
        docker compose config --hash "$service"
    ) | awk 'NF {print $NF; exit}'
}

rpi5_container_compose_config_hash() {
    local container_id="${1:?missing container id}"
    docker inspect \
        --format '{{index .Config.Labels "com.docker.compose.config-hash"}}' \
        "$container_id"
}

rpi5_container_image_id() {
    local container_id="${1:?missing container id}"
    docker inspect --format '{{.Image}}' "$container_id"
}

rpi5_local_image_id() {
    local image_ref="${1:?missing image reference}"
    docker image inspect --format '{{.Id}}' "$image_ref"
}

rpi5_select_compose_update_targets() {
    local project_dir="${1:?missing compose project directory}"
    local inventory row service kind image_ref container_id
    local running_image desired_image running_hash desired_hash

    RPI5_COMPOSE_ALL_SERVICES=()
    RPI5_COMPOSE_BUILDABLE_SERVICES=()
    RPI5_COMPOSE_REGISTRY_SERVICES=()
    RPI5_COMPOSE_CHANGED_REGISTRY_SERVICES=()
    RPI5_COMPOSE_CONFIG_DRIFT_SERVICE=''

    inventory="$(rpi5_compose_service_inventory "$project_dir")" || return 2
    [[ -n "$inventory" ]] || return 2

    while IFS=$'\t' read -r service kind image_ref; do
        [[ -n "$service" ]] || return 2
        RPI5_COMPOSE_ALL_SERVICES+=("$service")

        case "$kind" in
            buildable)
                RPI5_COMPOSE_BUILDABLE_SERVICES+=("$service")
                ;;
            registry)
                [[ -n "$image_ref" ]] || return 2
                RPI5_COMPOSE_REGISTRY_SERVICES+=("$service")

                container_id="$(
                    rpi5_compose_service_container_id "$project_dir" "$service"
                )" || return 2
                [[ -n "$container_id" ]] || return 2

                running_image="$(rpi5_container_image_id "$container_id")" \
                    || return 2
                desired_image="$(rpi5_local_image_id "$image_ref")" \
                    || return 2
                [[ -n "$running_image" && -n "$desired_image" ]] || return 2

                if [[ "$running_image" != "$desired_image" ]]; then
                    running_hash="$(
                        rpi5_container_compose_config_hash "$container_id"
                    )" || return 2
                    desired_hash="$(
                        rpi5_compose_service_config_hash "$project_dir" "$service"
                    )" || return 2
                    [[ -n "$running_hash" && -n "$desired_hash" ]] || return 2

                    if [[ "$running_hash" != "$desired_hash" ]]; then
                        RPI5_COMPOSE_CONFIG_DRIFT_SERVICE="$service"
                        return 3
                    fi

                    RPI5_COMPOSE_CHANGED_REGISTRY_SERVICES+=("$service")
                fi
                ;;
            *)
                return 2
                ;;
        esac
    done <<<"$inventory"

    (( ${#RPI5_COMPOSE_ALL_SERVICES[@]} > 0 )) || return 2
}

# Sets RPI5_COMPOSE_UP_ARGS to the reviewed unattended-maintenance arguments.
# rollback=true forces recreation only for registry-backed services whose
# restored image identity differs from the currently running container.
rpi5_build_compose_up_args() {
    local wait_timeout="${1:?missing compose wait timeout}"
    local rollback="${2:-false}"
    local compose_project_dir="${3:-${project_dir:-}}"

    [[ "$wait_timeout" =~ ^[0-9]+$ ]] || return 2
    [[ "$rollback" == "true" || "$rollback" == "false" ]] || return 2
    [[ -n "$compose_project_dir" && -d "$compose_project_dir" ]] || return 2

    rpi5_select_compose_update_targets "$compose_project_dir" || return $?

    RPI5_COMPOSE_UP_ARGS=(
        -d
        --pull never
        --no-build
        --wait
        --wait-timeout "$wait_timeout"
        --no-deps
    )

    if (( ${#RPI5_COMPOSE_CHANGED_REGISTRY_SERVICES[@]} > 0 )); then
        if [[ "$rollback" == "true" ]]; then
            RPI5_COMPOSE_UP_ARGS+=(--force-recreate)
        fi
        RPI5_COMPOSE_UP_ARGS+=("${RPI5_COMPOSE_CHANGED_REGISTRY_SERVICES[@]}")
        RPI5_COMPOSE_UPDATE_MODE='changed-registry-images'
        return 0
    fi

    # Nothing registry-backed changed. Target the already-running project with
    # --no-recreate so Compose cannot apply newer configuration to a stale
    # buildable/local image. The updater's preflight already requires every
    # service to have a running/healthy project container before this point.
    RPI5_COMPOSE_UP_ARGS+=(
        --no-recreate
        "${RPI5_COMPOSE_ALL_SERVICES[@]}"
    )
    RPI5_COMPOSE_UPDATE_MODE='no-image-change-no-recreate'
}
