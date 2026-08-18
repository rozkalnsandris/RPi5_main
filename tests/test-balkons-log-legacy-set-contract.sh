#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
addendum="$repo/docs/BALKONS_LOG_MQTT_LEGACY_SET_ADDENDUM.md"

fail() {
    echo "balkons-log legacy-set contract: FAIL: $*" >&2
    exit 1
}

[[ -f "$addendum" ]] || fail "legacy-set addendum missing"

grep -Fq 'supersedes singular wording' "$addendum" || fail "singular-contract precedence missing"
grep -Fq 'LEGACY_EXACT_RUNTIME_PROCESS_COUNT=3' "$addendum" || fail "sanitized three-clone evidence missing"
grep -Fq 'runtime reference, not the raw unit-file `-F` text' "$addendum" || fail "runtime-reference rule missing"
grep -Fq 'legacy subscriber set' "$addendum" || fail "legacy process-set model missing"
grep -Fq '/proc/<pid>/stat' "$addendum" || fail "PID start-time fingerprint missing"
grep -Fq 'byte-identical cmdline fingerprint' "$addendum" || fail "exact cmdline revalidation missing"
grep -Fq 'send `SIGTERM` only to members' "$addendum" || fail "targeted SIGTERM rule missing"
grep -Fq 'zero old-secret argv exposure' "$addendum" || fail "pre-replacement secret-zero gate missing"
grep -Fq 'Generic `pkill`' "$addendum" || fail "generic kill prohibition missing"
grep -Fq 'must **not recreate orphan duplicates**' "$addendum" || fail "rollback duplicate policy missing"
grep -Fq 'fresh explicit owner authorization' "$addendum" || fail "production authorization boundary missing"

if grep -Eq '(^|[^A-Za-z0-9])([0-9]{1,5})[[:space:]]+(/proc|mosquitto_sub)' "$addendum"; then
    fail "public addendum appears to contain a literal runtime PID"
fi

printf '%s\n' 'balkons-log legacy-set contract: PASS'
