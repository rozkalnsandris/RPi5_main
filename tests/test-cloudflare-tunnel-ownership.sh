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
grep -Fqx 'AssertFileIsExecutable=/usr/local/libexec/cloudflared/2026.7.3/cloudflared' "$unit" || fail "missing exact binary assertion"
grep -Fqx 'AssertFileNotEmpty=/etc/cloudflared/rpi5-tunnel.token' "$unit" || fail "missing non-empty token assertion"
grep -Fqx 'LoadCredential=tunnel-token:/etc/cloudflared/rpi5-tunnel.token' "$unit" || fail "missing LoadCredential"
grep -Fq 'ExecStart=/usr/local/libexec/cloudflared/2026.7.3/cloudflared tunnel --no-autoupdate --metrics 127.0.0.1:20241 run --token-file ${CREDENTIALS_DIRECTORY}/tunnel-token' "$unit" || fail "ExecStart contract drift"

# Validate actual systemd syntax, but substitute CI-safe existing files so verify
# checks syntax/directives without requiring production binaries or credentials.
command -v systemd-analyze >/dev/null 2>&1 || fail "systemd-analyze is required"
tmp_unit="$(mktemp --suffix=.service)"
trap 'rm -f "$tmp_unit"' EXIT
sed \
  -e 's#AssertFileIsExecutable=/usr/local/libexec/cloudflared/2026.7.3/cloudflared#AssertFileIsExecutable=/usr/bin/true#' \
  -e 's#AssertFileNotEmpty=/etc/cloudflared/rpi5-tunnel.token#AssertFileNotEmpty=/etc/hosts#' \
  -e 's#/usr/local/libexec/cloudflared/2026.7.3/cloudflared#/usr/bin/true#g' \
  -e 's#LoadCredential=tunnel-token:/etc/cloudflared/rpi5-tunnel.token#LoadCredential=tunnel-token:/etc/hosts#' \
  "$unit" > "$tmp_unit"
systemd-analyze verify "$tmp_unit" >/dev/null || fail "systemd-analyze verify rejected unit"

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

# The contract must describe the completed host-owned architecture, not the
# retired CV-owned migration path.
grep -Fq '**Migration complete — 2026-08-07.**' "$contract" || fail "migration is not marked complete"
grep -Fq 'Application repositories may verify their own local and public endpoints' "$contract" || fail "missing ownership invariant"
grep -Fq '`rozkalns.net` | `http://127.0.0.1:8088` | public' "$contract" || fail "missing stable loopback apex origin"
grep -Fq '`RPi5_main` is the only repository that owns the shared RPi5 Cloudflare' "$contract" || fail "missing authoritative host owner"
grep -Fq 'Cloudflare Tunnel itself is outbound-only.' "$contract" || fail "missing outbound-only firewall boundary"
grep -Fq 'Docker-published ports must not rely on UFW as their primary exposure control.' "$contract" || fail "missing Docker/UFW boundary"
grep -Fq 'Do **not** protect all `*.rozkalns.net` with one broad wildcard Access policy.' "$contract" || fail "missing Access wildcard safety rule"

# Retired migration-era CV connector references must not reappear in the final
# ownership contract. Build strings in pieces so this test does not itself
# preserve the retired exact paths as searchable documentation.
legacy_apex='http://172.19.0.'"10:80"
legacy_container='cv-'"cloudflared"
legacy_env='/home/andris/docker/cv/cloudflared.'"env"
for legacy in "$legacy_apex" "$legacy_container" "$legacy_env"; do
  if grep -Fq "$legacy" "$contract"; then
    fail "retired CV-owned tunnel reference reintroduced"
  fi
done

# No local ingress config.yml is part of the remotely-managed design.
if find ops -type f \( -name 'config.yml' -o -name 'config.yaml' \) -print | grep -q .; then
  fail "unexpected tracked Cloudflare-style local config file"
fi

echo "Cloudflare ownership test: PASS"
