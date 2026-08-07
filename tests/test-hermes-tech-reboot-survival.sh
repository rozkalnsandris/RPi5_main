#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

script="ops/bin/verify-hermes-tech-reboot-survival"
contract="docs/V16_HERMES_TECH_REBOOT_SURVIVAL_CONTRACT.md"

fail() {
  echo "Hermes Tech reboot survival test: FAIL: $*" >&2
  exit 1
}

[[ -f "$script" ]] || fail "missing verifier"
[[ -f "$contract" ]] || fail "missing V16 contract"

bash -n "$script" || fail "verifier shell syntax invalid"

grep -Fq 'MODE="${1:-check}"' "$script" || fail "check must be default mode"
grep -Fq '"check" || "$MODE" == "capture" || "$MODE" == "verify"' "$script" || fail "mode contract missing"
grep -Fq '/proc/sys/kernel/random/boot_id' "$script" || fail "kernel boot ID gate missing"
grep -Fq 'STATE_DIR="/var/lib/rpi5-main"' "$script" || fail "protected baseline directory missing"
grep -Fq 'STATE_FILE="$STATE_DIR/hermes-tech-reboot-survival.env"' "$script" || fail "protected baseline filename missing"
grep -Fq 'ActiveEnterTimestampMonotonic' "$script" || fail "boot-time service evidence missing"
grep -Fq 'EARLY_BOOT_MAX_USEC=600000000' "$script" || fail "early boot window missing"
grep -Fq '127.0.0.1:8089' "$script" || fail "loopback publish invariant missing"
grep -Fq '192.168.0.180:8089' "$script" || fail "direct LAN negative gate missing"
grep -Fq 'cloudflared HA is not 4' "$script" || fail "Cloudflare HA gate missing"
grep -Fq 'hermes-blog-legacy-v14' "$script" || fail "rollback asset gate missing"
grep -Fq '7a1455e938354871b46a91dc00bccb6679ad5c2799f1368e7d5b829190604226' "$script" || fail "setup quarantine checksum missing"
grep -Fq '115566b8f432863370bd4945f960a8f587f8041df7512bb81174388d42210c98' "$script" || fail "fix quarantine checksum missing"
grep -Fq 'HERMES_TECH_REBOOT_SURVIVAL_CAPTURE=PASS' "$script" || fail "capture marker missing"
grep -Fq 'HERMES_TECH_REBOOT_SURVIVAL_VERIFY=PASS' "$script" || fail "verify marker missing"

# The verifier may collect evidence and write its protected baseline only.
# It must never perform lifecycle, firewall, tunnel, image or rollback mutations.
if grep -Eq '^[[:space:]]*(sudo[[:space:]]+)?(reboot|shutdown|poweroff|halt)([[:space:]]|$)' "$script"; then
  fail "host power mutation is forbidden"
fi
if grep -Eq 'systemctl[[:space:]]+(start|stop|restart|try-restart|reload|enable|disable|mask|unmask|reboot|poweroff)' "$script"; then
  fail "systemd mutation is forbidden"
fi
if grep -Eq '(^|[[:space:]])docker[[:space:]]+(run|create|start|stop|restart|rm|rename|pull|image[[:space:]]+prune|system[[:space:]]+prune)([[:space:]]|$)' "$script"; then
  fail "Docker mutation is forbidden"
fi
if grep -Eq '(^|[[:space:]])ufw[[:space:]]+(allow|deny|reject|delete|insert|reset|disable|enable)([[:space:]]|$)' "$script"; then
  fail "UFW mutation is forbidden"
fi
if grep -Eq 'cloudflared[^\n]*(tunnel|route|access)[^\n]*(create|delete|update|run)' "$script"; then
  fail "Cloudflare control-plane mutation is forbidden"
fi

# Contract must preserve the two-stage authorization boundary.
grep -Fq '**Source reviewed in Git; real reboot verification pending.**' "$contract" || fail "V16 status missing"
grep -Fq 'Merging V16 performs no production mutation.' "$contract" || fail "merge boundary missing"
grep -Fq 'The verifier itself never initiates a reboot.' "$contract" || fail "reboot boundary missing"
grep -Fq 'A real RPi5 reboot is a separate production maintenance action.' "$contract" || fail "explicit maintenance boundary missing"
grep -Fq 'A successful reboot-survival verification does not itself remove anything.' "$contract" || fail "rollback retirement boundary missing"

echo "Hermes Tech reboot survival test: PASS"
