#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

script="ops/bin/quarantine-hermes-tech-legacy-runtime"
contract="docs/V15_HERMES_TECH_LEGACY_RUNTIME_RETIREMENT_CONTRACT.md"

fail() {
  echo "Hermes Tech legacy runtime retirement test: FAIL: $*" >&2
  exit 1
}

[[ -f "$script" ]] || fail "missing $script"
[[ -f "$contract" ]] || fail "missing $contract"

bash -n "$script" || fail "operator shell syntax invalid"

grep -Fq 'MODE="${1:-check}"' "$script" || fail "check must be default mode"
grep -Fq '[[ "$MODE" == "check" || "$MODE" == "apply" ]]' "$script" || fail "unexpected mutation mode contract"

for exact in \
  '/home/andris/hermes-tech-phase3/setup3.sh' \
  '7a1455e938354871b46a91dc00bccb6679ad5c2799f1368e7d5b829190604226' \
  '/home/andris/_home_cleanup_20260804-221307/fix-port.sh' \
  '115566b8f432863370bd4945f960a8f587f8041df7512bb81174388d42210c98' \
  '/home/andris/.quarantine/hermes-tech-v14-legacy-runtime-20260807' \
  'hermes-blog-legacy-v14' \
  '127.0.0.1:8089'; do
  grep -Fq "$exact" "$script" || fail "missing exact quarantine invariant: $exact"
done

# Only filesystem quarantine is allowed. Runtime mutation must never creep into this operator.
if grep -Eq '(^|[[:space:]])docker[[:space:]]+(rm|run|create|start|stop|restart|rename)([[:space:]]|$)' "$script"; then
  fail "Docker mutation is forbidden"
fi
if grep -Eq 'systemctl[[:space:]]+(start|stop|restart|disable|enable|mask|unmask|daemon-reload)' "$script"; then
  fail "systemd mutation is forbidden"
fi
if grep -Eq '(^|[[:space:]])ufw([[:space:]]|$)' "$script"; then
  fail "UFW mutation/reference is forbidden"
fi
if grep -Eq 'cloudflared[^\n]*(tunnel|route|access)[^\n]*(create|delete|update|run)' "$script"; then
  fail "Cloudflare control-plane mutation is forbidden"
fi

# Quarantine must be reversible evidence retention, not deletion.
grep -Fq 'mv -- "$SETUP_SRC" "$SETUP_DST"' "$script" || fail "setup script is not moved to quarantine"
grep -Fq 'mv -- "$FIX_SRC" "$FIX_DST"' "$script" || fail "fix script is not moved to quarantine"
grep -Fq 'chmod 0400 "$SETUP_DST" "$FIX_DST"' "$script" || fail "quarantine files must be non-executable"
grep -Fq 'MANIFEST.tsv' "$script" || fail "quarantine manifest missing"

if grep -Eq '(^|[[:space:]])rm[[:space:]].*(SETUP|FIX|hermes-tech-phase3|fix-port\.sh)' "$script"; then
  fail "legacy script deletion is forbidden"
fi

# Production safety gates are mandatory before and after any apply.
grep -Fq 'runtime_gate' "$script" || fail "runtime gate missing"
grep -Fq 'cloudflared HA is not 4' "$script" || fail "Cloudflare HA preflight missing"
grep -Fq 'cloudflared PID changed' "$script" || fail "Cloudflare PID stability gate missing"
grep -Fq 'rollback container identity drift' "$script" || fail "rollback asset identity gate missing"

# Contract records the completed host cleanup while preserving source-vs-production boundaries.
grep -Fq '**Production host quarantine complete — 2026-08-07.**' "$contract" || fail "V15 completed status missing"
grep -Fq 'Merging V15 performed no production mutation.' "$contract" || fail "merge/no-mutation history missing"
grep -Fq 'The later explicit `apply` invocation was the separately confirmed host cleanup change and is now complete.' "$contract" || fail "explicit apply completion boundary missing"
grep -Fq 'V15 does **not** remove `hermes-blog-legacy-v14`' "$contract" || fail "rollback retention boundary missing"
grep -Fq 'direct LAN `192.168.0.180:8089` remained blocked (`curl` rc 7)' "$contract" || fail "direct LAN verification evidence missing"
grep -Fq 'Cloudflare connector PID remained unchanged at `423466` and HA readiness remained 4/4' "$contract" || fail "Cloudflare verification evidence missing"

echo "Hermes Tech legacy runtime retirement test: PASS"
