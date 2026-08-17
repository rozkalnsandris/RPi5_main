#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

wrapper="ops/bin/cloudflare-zero-trust-reconcile"
runner="scripts/cloudflare_zero_trust_reconcile_stdin.py"
core="scripts/cloudflare_zero_trust_reconcile.py"

fail() {
  echo "Cloudflare Zero Trust wrapper test: FAIL: $*" >&2
  exit 1
}

[[ -f "$wrapper" ]] || fail "wrapper missing"
[[ -f "$runner" ]] || fail "stdin runner missing"
[[ -f "$core" ]] || fail "GET-only core missing"
bash -n "$wrapper" || fail "wrapper shell syntax invalid"
python3 -m py_compile "$runner" "$core" || fail "Python syntax invalid"

grep -Fq 'read -r -s' "$wrapper" || fail "hidden token prompt missing"
grep -Fq '</dev/tty' "$wrapper" || fail "TTY token source missing"
grep -Fq 'unset CLOUDFLARE_API_TOKEN' "$wrapper" || fail "token environment cleanup missing"
grep -Fq "printf '%s\\n' \"\$api_token\" | python3 \"\$RUNNER\"" "$wrapper" ||
  fail "stdin token handoff missing"

if grep -Eq '(^|[[:space:]])export[[:space:]]+CLOUDFLARE_API_TOKEN' "$wrapper"; then
  fail "API token must not be exported to the child environment"
fi
if grep -Eq '(echo|printf)[^\n]*CLOUDFLARE_API_TOKEN' "$wrapper"; then
  fail "API token environment variable must never be printed"
fi
if grep -Fq 'set -x' "$wrapper"; then
  fail "shell tracing is forbidden"
fi

# The normal wrapper path must not expose any Cloudflare write verb or curl command.
if grep -Eqi '(^|[[:space:]])(curl|wget)([[:space:]]|$)|\b(POST|PUT|PATCH|DELETE)\b' "$wrapper"; then
  fail "wrapper contains an unexpected network/write surface"
fi

echo "Cloudflare Zero Trust wrapper test: PASS"
