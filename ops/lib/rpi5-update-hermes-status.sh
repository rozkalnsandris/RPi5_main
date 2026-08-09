#!/usr/bin/env bash
# Shared status classifier for `hermes update --check` output.
# Sets HERMES_CHECK_STATE to current|available|error and
# HERMES_CHECK_BEHIND to a commit count when the CLI reports one.

rpi5_classify_hermes_update_check() {
    local rc="${1:?missing Hermes check exit code}"
    local output="${2-}"
    local count=""

    HERMES_CHECK_STATE="error"
    HERMES_CHECK_BEHIND=""

    if [[ "$output" =~ ([0-9]+)[[:space:]]+commits?[[:space:]]+behind([[:space:]]+origin/main)? ]]; then
        count="${BASH_REMATCH[1]}"
        HERMES_CHECK_STATE="available"
        HERMES_CHECK_BEHIND="$count"
        return 0
    fi

    if [[ "$output" =~ [Uu]pdate[[:space:]]+available ]]; then
        HERMES_CHECK_STATE="available"
        return 0
    fi

    if [[ "$rc" -eq 0 ]]; then
        HERMES_CHECK_STATE="current"
        return 0
    fi

    return 1
}
