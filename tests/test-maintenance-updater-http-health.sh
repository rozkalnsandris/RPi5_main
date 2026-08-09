#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-http-health.sh
source "$repo/ops/lib/rpi5-update-http-health.sh"

bash -n "$repo/ops/lib/rpi5-update-http-health.sh"

tmp="$(mktemp -d)"
cleanup() { rm -rf -- "$tmp"; }
trap cleanup EXIT

# curl commonly prints HTTP 000 and also returns a transport error. The helper
# must normalize that to exactly one three-digit code, never `000000`.
curl() {
    printf '000'
    return 7
}
normalized="$(rpi5_request_code 'https://example.invalid/')"
[[ "$normalized" == "000" ]]
unset -f curl
printf '%s\n' 'PASS curl-failure-normalized-to-000'

# First request fails, second succeeds. The mock counter is file-backed because
# rpi5_request_code is intentionally invoked inside command substitution.
counter="$tmp/request-count"
printf '0\n' >"$counter"
rpi5_request_code() {
    local n
    n="$(<"$counter")"
    n=$((n + 1))
    printf '%s\n' "$n" >"$counter"
    if [[ "$n" -eq 1 ]]; then
        printf '530'
    else
        printf '200'
    fi
}

captured="$(rpi5_request_code_with_retry 'https://example.invalid/' 2 0 2>"$tmp/retry.err")"
[[ "$captured" == "200" ]]
[[ "$(<"$counter")" -eq 2 ]]
[[ -s "$tmp/retry.err" ]]
grep -Fq 'HTTP 530' "$tmp/retry.err"
printf '%s\n' 'PASS retry-success-clean-stdout'

# Exhaustion must be usable in an if-condition under set -e so callers can
# record health failure instead of aborting before updating status fields.
rpi5_request_code() { printf '530'; }
exhausted=""
if exhausted="$(rpi5_request_code_with_retry 'https://example.invalid/' 2 0 2>"$tmp/exhaust.err")"; then
    echo 'retry exhaustion unexpectedly succeeded' >&2
    exit 1
fi
[[ "$exhausted" == "530" ]]
grep -Fq 'HTTP 530' "$tmp/exhaust.err"
printf '%s\n' 'PASS retry-exhaustion-controlled'

rpi5_code_is_reachable 200
rpi5_code_is_reachable 302
rpi5_code_is_reachable 401
rpi5_code_is_reachable 403
! rpi5_code_is_reachable 404
! rpi5_code_is_reachable 000
printf '%s\n' 'PASS reachable-code-policy'

rc=0
rpi5_request_code_with_retry 'https://example.invalid/' 0 0 >/dev/null 2>&1 || rc=$?
[[ "$rc" -eq 2 ]]
printf '%s\n' 'PASS invalid-attempt-count'

printf '%s\n' 'Maintenance updater HTTP health tests: PASS (5 cases)'
