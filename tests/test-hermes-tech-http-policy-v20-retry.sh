#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
OP="$ROOT/ops/bin/hermes-tech-http-policy-v20-retry"

fail() {
  echo "Hermes Tech V20 retry test: FAIL: $*" >&2
  exit 1
}

[[ -f "$OP" ]] || fail "retry operator missing"
bash -n "$OP"

source_text="$(cat "$OP")"

for required in \
  'check|apply|verify' \
  'FAILED_OPERATOR_SHA="f4c181b37ac67984c8cddd4a8da09454a1a36e88"' \
  '"${PHASE:-}" == "rolled_back"' \
  'SOURCE_CONFIG_SHA' \
  'SOURCE_UNIT_SHA' \
  'BACKUP_UNIT' \
  '[0-9a-f]{96}' \
  'systemctl restart "$SERVICE"' \
  'systemd-analyze verify "$INSTALLED_UNIT"' \
  'HERMES_TECH_V20_RETRY_CHECK=PASS' \
  'HERMES_TECH_V20_RETRY_APPLY=PASS' \
  'HERMES_TECH_V20_RETRY_VERIFY=PASS' \
  'HERMES_TECH_V20_RETRY_AUTOMATIC_ROLLBACK=PASS'
do
  grep -Fq -- "$required" <<<"$source_text" || fail "required contract missing: $required"
done

for forbidden in \
  'docker pull' \
  'docker image prune' \
  'systemctl restart cloudflared' \
  'systemctl reload cloudflared' \
  'ufw allow' \
  'ufw delete' \
  'git push --force' \
  'git rebase' \
  'sqlite3 ' \
  'run_digests.sh' \
  'digest.py'
do
  if grep -Fq -- "$forbidden" <<<"$source_text"; then
    fail "forbidden mutation present: $forbidden"
  fi
done

extract_css() {
  grep -oE 'href=("/css/site\.min\.[0-9a-f]{96}\.css"|/css/site\.min\.[0-9a-f]{96}\.css)' |
    head -n1 | sed -E 's/^href="?([^" ]+)"?$/\1/' || true
}

HASH96="$(printf 'a%.0s' {1..96})"
HASH64="$(printf 'b%.0s' {1..64})"
EXPECTED="/css/site.min.${HASH96}.css"

quoted="<link rel=\"stylesheet\" href=\"${EXPECTED}\" integrity=\"sha384-example\">"
unquoted="<link rel=stylesheet href=${EXPECTED} integrity=sha384-example crossorigin=anonymous>"
wrong_hash="<link rel=stylesheet href=/css/site.min.${HASH64}.css>"
wrong_path="<link rel=stylesheet href=/css/other.min.${HASH96}.css>"

[[ "$(printf '%s\n' "$quoted" | extract_css)" == "$EXPECTED" ]] || fail "quoted Hugo href not parsed"
[[ "$(printf '%s\n' "$unquoted" | extract_css)" == "$EXPECTED" ]] || fail "unquoted minified Hugo href not parsed"
[[ -z "$(printf '%s\n' "$wrong_hash" | extract_css)" ]] || fail "non-SHA384 fingerprint accepted"
[[ -z "$(printf '%s\n' "$wrong_path" | extract_css)" ]] || fail "wrong CSS path accepted"

# Recovery must be bound to the proven original rollback evidence and leave it intact.
grep -Fq 'ORIGINAL_STATE_FILE="$ORIGINAL_STATE_DIR/state.env"' "$OP" || fail "original state file is not explicit"
grep -Fq 'RETRY_STATE="$RETRY_DIR/state.env"' "$OP" || fail "retry state is not separate"
grep -Fq '"$(sha_of "$BACKUP_UNIT")" == "$EXPECTED_V14_UNIT_SHA"' "$OP" || fail "rollback backup checksum is not enforced"
grep -Fq '"${SOURCE_CONFIG_SHA:-}" == "$(sha_of "$SRC_CONFIG")"' "$OP" || fail "source config continuity not enforced"
grep -Fq '"${SOURCE_UNIT_SHA:-}" == "$(sha_of "$SRC_UNIT")"' "$OP" || fail "source unit continuity not enforced"

echo "Hermes Tech V20 minified CSS retry test: PASS"
