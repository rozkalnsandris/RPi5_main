#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

unit="ops/systemd/cloudflared.service"
contract="docs/V13_CLOUDFLARE_TUNNEL_OWNERSHIP_CONTRACT.md"

fail() {
  echo "Cloudflare ownership test: FAIL: $*" >&2
  exit 1
}

[[ -f "$unit" ]] || fail "missing $unit"
[[ -f "$contract" ]] || fail "missing $contract"

# Exact reviewed runtime identity and remotely-managed token-file contract.
grep -Fqx 'ConditionPathIsExecutable=/usr/local/libexec/cloudflared/2026.7.3/cloudflared' "$unit" || fail "missing exact binary condition"
grep -Fqx 'ConditionPathExists=/etc/cloudflared/rpi5-tunnel.token' "$unit" || fail "missing token source condition"
grep -Fqx 'LoadCredential=tunnel-token:/etc/cloudflared/rpi5-tunnel.token' "$unit" || fail "missing LoadCredential"
grep -Fq 'ExecStart=/usr/local/libexec/cloudflared/2026.7.3/cloudflared tunnel --no-autoupdate --metrics 127.0.0.1:20241 run --token-file ${CREDENTIALS_DIRECTORY}/tunnel-token' "$unit" || fail "ExecStart contract drift"

# The token must never be embedded in the unit or passed with --token.
if grep -Eq 'eyJ[A-Za-z0-9._-]{20,}' "$unit"; then
  fail "token-like content is tracked in unit"
fi
if grep -Eq '(^|[[:space:]])--token([=[:space:]]|$)' "$unit"; then
  fail "raw --token argument is forbidden"
fi

# Least-privilege and local-only metrics requirements.
for line in \
  'DynamicUser=yes' \
  'NoNewPrivileges=yes' \
  'PrivateTmp=yes' \
  'PrivateDevices=yes' \
  'ProtectSystem=strict' \
  'ProtectHome=yes' \
  'CapabilityBoundingSet=' \
  'AmbientCapabilities=' \
  'TasksMax=64' \
  'MemoryHigh=96M' \
  'MemoryMax=128M'; do
  grep -Fqx "$line" "$unit" || fail "missing hardening/resource line: $line"
done

grep -Fq -- '--metrics 127.0.0.1:20241' "$unit" || fail "metrics must be loopback-only"
if grep -Eq -- '--metrics[[:space:]]+(0\.0\.0\.0|\[::\])' "$unit"; then
  fail "wildcard metrics bind is forbidden"
fi

# The service must retain network access and may not self-update.
if grep -Fqx 'PrivateNetwork=yes' "$unit"; then
  fail "PrivateNetwork would break the tunnel"
fi
grep -Fq -- '--no-autoupdate' "$unit" || fail "automatic updates must be disabled"

# The contract must preserve the migration safety boundary and temporary apex marker.
grep -Fq 'Application repositories deploy only their application.' "$contract" || fail "missing ownership invariant"
grep -Fq '`http://172.19.0.10:80`' "$contract" || fail "missing temporary apex origin record"
grep -Fq 'must be removed after the host connector is established' "$contract" || fail "temporary origin is not marked for removal"
grep -Fq 'old Docker connector remains online' "$contract" || fail "missing no-downtime migration gate"
grep -Fq 'Merging V13 performs no production change.' "$contract" || fail "missing merge/no-deploy boundary"

# No local ingress config.yml is part of the remotely-managed design.
if find ops -type f \( -name 'config.yml' -o -name 'config.yaml' \) -print | grep -q .; then
  fail "unexpected tracked Cloudflare-style local config file"
fi

echo "Cloudflare ownership test: PASS"
