#!/usr/bin/env bash
# Safe Docker Compose argument policy for the weekly RPi5 updater.

# Sets RPI5_COMPOSE_UP_ARGS to the reviewed unattended-maintenance arguments.
# rollback=true additionally forces recreation from the restored image tags.
rpi5_build_compose_up_args() {
    local wait_timeout="${1:?missing compose wait timeout}"
    local rollback="${2:-false}"

    [[ "$wait_timeout" =~ ^[0-9]+$ ]] || return 2
    [[ "$rollback" == "true" || "$rollback" == "false" ]] || return 2

    RPI5_COMPOSE_UP_ARGS=(
        -d
        --pull never
        --no-build
        --wait
        --wait-timeout "$wait_timeout"
    )

    if [[ "$rollback" == "true" ]]; then
        RPI5_COMPOSE_UP_ARGS+=(--force-recreate)
    fi
}
