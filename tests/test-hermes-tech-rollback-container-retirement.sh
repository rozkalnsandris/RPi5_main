#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

script="ops/bin/retire-hermes-tech-v14-rollback-container"
contract="docs/V17_HERMES_TECH_ROLLBACK_CONTAINER_RETIREMENT_CONTRACT.md"

fail() {
  echo "Hermes Tech rollback container retirement test: FAIL: $*" >&2
  exit 1
}

[[ -f "$script" ]] || fail "missing retirement operator"
[[ -f "$contract" ]] || fail "missing V17 contract"

bash -n "$script" || fail "operator shell syntax invalid"

grep -Fq 'MODE="${1:-check}"' "$script" || fail "check must be default mode"
grep -Fq '[[ "$MODE" == "check" || "$MODE" == "apply" ]]' "$script" || fail "mode contract missing"
grep -Fq 'ROLLBACK="hermes-blog-legacy-v14"' "$script" || fail "rollback name invariant missing"
grep -Fq 'EXPECTED_ROLLBACK_ID="5738272eb00eeffd518a9cb3cb236292a37f44bb360e5a4d703956ce82c50397"' "$script" || fail "rollback ID invariant missing"
grep -Fq 'EXPECTED_IMAGE="sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa"' "$script" || fail "authoritative image invariant missing"
grep -Fq 'docker rm "$ROLLBACK"' "$script" || fail "exact rollback removal missing"
grep -Fq 'HERMES_TECH_V14_ROLLBACK_CONTAINER_RETIREMENT_CHECK=PASS' "$script" || fail "check marker missing"
grep -Fq 'HERMES_TECH_V14_ROLLBACK_CONTAINER_RETIREMENT_APPLY=PASS' "$script" || fail "apply marker missing"

# Force-removal is never allowed.
if grep -Eq 'docker[[:space:]]+rm[[:space:]]+(-[^[:space:]]*f|--force)' "$script"; then
  fail "forced Docker removal is forbidden"
fi

# Remove the single reviewed rollback-container line before scanning for any
# other Docker lifecycle mutation. The live container and image are immutable.
filtered="$(mktemp)"
trap 'rm -f "$filtered"' EXIT
grep -Fv 'docker rm "$ROLLBACK"' "$script" > "$filtered"

if grep -Eq '(^|[[:space:]])docker[[:space:]]+(run|create|start|stop|restart|rm|rename|pull|rmi)([[:space:]]|$)' "$filtered"; then
  fail "unexpected Docker lifecycle mutation"
fi
if grep -Eq 'docker[[:space:]]+image[[:space:]]+(rm|prune)' "$filtered"; then
  fail "authoritative image removal/prune is forbidden"
fi
if grep -Eq 'docker[[:space:]]+system[[:space:]]+prune' "$filtered"; then
  fail "Docker system prune is forbidden"
fi
if grep -Eq 'systemctl[[:space:]]+(start|stop|restart|try-restart|reload|enable|disable|mask|unmask|reboot|poweroff)' "$script"; then
  fail "systemd mutation is forbidden"
fi
if grep -Eq '(^|[[:space:]])ufw[[:space:]]+(allow|deny|reject|delete|insert|reset|disable|enable)([[:space:]]|$)' "$script"; then
  fail "UFW mutation is forbidden"
fi
if grep -Eq 'cloudflared[^\n]*(tunnel|route|access)[^\n]*(create|delete|update|run)' "$script"; then
  fail "Cloudflare control-plane mutation is forbidden"
fi
if grep -Eq '^[[:space:]]*(sudo[[:space:]]+)?(reboot|shutdown|poweroff|halt)([[:space:]]|$)' "$script"; then
  fail "host power mutation is forbidden"
fi

# Evidence and authoritative image retention are mandatory.
grep -Fq 'STATE_FILE="/var/lib/rpi5-main/hermes-tech-reboot-survival.env"' "$script" || fail "V16 baseline retention gate missing"
grep -Fq 'QDIR="/home/andris/.quarantine/hermes-tech-v14-legacy-runtime-20260807"' "$script" || fail "V15 quarantine retention gate missing"
grep -Fq 'authoritative image missing' "$script" || fail "authoritative image preflight missing"
grep -Fq 'authoritative image disappeared' "$script" || fail "authoritative image postflight missing"
grep -Fq 'live container changed during rollback retirement' "$script" || fail "live container identity stability gate missing"
grep -Fq 'cloudflared PID changed during rollback retirement' "$script" || fail "Cloudflare PID stability gate missing"

# Contract must record completed production state while preserving the image and source-vs-production boundary.
grep -Fq '**Production rollback-container retirement complete — 2026-08-07.**' "$contract" || fail "V17 completed status missing"
grep -Fq 'Merging V17 performed no production mutation.' "$contract" || fail "merge/no-mutation boundary missing"
grep -Fq 'is not a disposable rollback artifact.' "$contract" || fail "authoritative image distinction missing"
grep -Fq 'Removing or pruning the image would break a future service restart or host reboot.' "$contract" || fail "image retention rationale missing"
grep -Fq 'The only allowed Docker lifecycle mutation is:' "$contract" || fail "single-mutation boundary missing"
grep -Fq 'HERMES_TECH_V14_ROLLBACK_CONTAINER_RETIREMENT_APPLY=PASS' "$contract" || fail "production apply evidence missing"
grep -Fq 'HERMES_TECH_V17_ROLLBACK_CONTAINER_RETIREMENT=PASS' "$contract" || fail "production wrapper evidence missing"
grep -Fq 'live `hermes-blog` container ID remained unchanged: `9dcf4dbb652aebded7c8454d4c17407573b5d6fa9569823308011551279a8073`' "$contract" || fail "live container production evidence missing"
grep -Fq 'Cloudflare PID remained `878` and HA remained 4/4 during the operation' "$contract" || fail "Cloudflare production evidence missing"
grep -Fq 'The explicit `apply` invocation was the separately confirmed production host cleanup action and is now complete.' "$contract" || fail "completed apply boundary missing"
grep -Fq 'must continue to be retained while `hermes-tech-web.service` references it with `--pull=never`.' "$contract" || fail "ongoing image retention boundary missing"

echo "Hermes Tech rollback container retirement test: PASS"
