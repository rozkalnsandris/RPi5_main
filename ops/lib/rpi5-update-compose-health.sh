#!/usr/bin/env bash
# Compose health helpers for the weekly updater.

# Compare newline-separated expected service names from
# `docker compose config --services` with the newline-separated service names
# that currently have containers according to `docker compose ps --all --services`.
# Sets RPI5_MISSING_COMPOSE_SERVICES to a newline-separated sorted list.
rpi5_find_missing_compose_services() {
    local expected="${1-}"
    local actual="${2-}"
    local expected_file actual_file

    expected_file="$(mktemp)" || return 2
    actual_file="$(mktemp)" || {
        rm -f -- "$expected_file"
        return 2
    }

    printf '%s\n' "$expected" | sed '/^[[:space:]]*$/d' | sort -u >"$expected_file"
    printf '%s\n' "$actual" | sed '/^[[:space:]]*$/d' | sort -u >"$actual_file"

    RPI5_MISSING_COMPOSE_SERVICES="$(comm -23 "$expected_file" "$actual_file")"
    rm -f -- "$expected_file" "$actual_file"

    [[ -z "$RPI5_MISSING_COMPOSE_SERVICES" ]]
}
