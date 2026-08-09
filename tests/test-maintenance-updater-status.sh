#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-hermes-status.sh
source "$repo/ops/lib/rpi5-update-hermes-status.sh"

pass=0
run_case() {
    local name="$1" rc="$2" expected_state="$3" expected_behind="$4" text="$5"
    HERMES_CHECK_STATE=""
    HERMES_CHECK_BEHIND=""

    local classifier_rc=0
    rpi5_classify_hermes_update_check "$rc" "$text" || classifier_rc=$?

    case "$expected_state" in
        error)
            [[ "$classifier_rc" -ne 0 ]]
            ;;
        *)
            [[ "$classifier_rc" -eq 0 ]]
            ;;
    esac
    [[ "$HERMES_CHECK_STATE" == "$expected_state" ]]
    [[ "$HERMES_CHECK_BEHIND" == "$expected_behind" ]]
    printf 'PASS %s\n' "$name"
    pass=$((pass + 1))
}

run_case current-zero 0 current '' '✓ Up to date.'
run_case behind-documented-exit1 1 available 1371 '⚕ Update available: 1371 commits behind origin/main.'
run_case behind-observed-exit0 0 available 1371 '⚕ Update available: 1371 commits behind origin/main.'
run_case behind-singular 1 available 1 'Update available: 1 commit behind origin/main.'
run_case real-command-failure 2 error '' 'fatal: unable to access remote repository'

[[ "$pass" -eq 5 ]]
printf 'Maintenance updater Hermes status tests: PASS (%d cases)\n' "$pass"
