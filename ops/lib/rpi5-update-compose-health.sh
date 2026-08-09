#!/usr/bin/env bash
# Compose health helpers for the weekly updater.

# Compare newline-separated expected service names from
# `docker compose config --services` with the newline-separated service names
# that currently have containers according to `docker compose ps --all --services`.
# Sets RPI5_MISSING_COMPOSE_SERVICES to a newline-separated list in expected
# configuration order. Service names produced by Compose cannot contain spaces.
rpi5_find_missing_compose_services() {
    local expected="${1-}"
    local actual="${2-}"
    local service
    local -A actual_services=()
    local -a missing=()

    while IFS= read -r service; do
        [[ -n "$service" ]] || continue
        actual_services["$service"]=1
    done <<<"$actual"

    while IFS= read -r service; do
        [[ -n "$service" ]] || continue
        [[ -n "${actual_services[$service]:-}" ]] || missing+=("$service")
    done <<<"$expected"

    RPI5_MISSING_COMPOSE_SERVICES="$(printf '%s\n' "${missing[@]:-}")"
    RPI5_MISSING_COMPOSE_SERVICES="${RPI5_MISSING_COMPOSE_SERVICES%$'\n'}"

    (( ${#missing[@]} == 0 ))
}
