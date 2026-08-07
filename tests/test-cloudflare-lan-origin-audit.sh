#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

script="ops/bin/audit-cloudflare-lan-origins"
contract="docs/V18_CLOUDFLARE_LAN_ORIGIN_AUDIT_CONTRACT.md"

fail() {
  echo "Cloudflare LAN-origin audit test: FAIL: $*" >&2
  exit 1
}

[[ -f "$script" ]] || fail "missing V18 audit operator"
[[ -f "$contract" ]] || fail "missing V18 contract"
bash -n "$script" || fail "audit operator shell syntax invalid"

# Exact reviewed route scope.
for expected in \
  'deals.rozkalns.net|9128|private-application' \
  'hermes.rozkalns.net|9119|admin-private' \
  'portainer.rozkalns.net|9000|admin' \
  'grafana.rozkalns.net|3030|admin' \
  'ha.rozkalns.net|8123|admin' \
  'adguard.rozkalns.net|3080|admin' \
  'kuma.rozkalns.net|3001|admin' \
  'prometheus.rozkalns.net|9090|admin'; do
  grep -Fq "\"$expected\"" "$script" || fail "missing reviewed origin: $expected"
done

origin_count="$(grep -Ec '^  "[^|]+\|[0-9]+\|[^|]+"$' "$script")"
[[ "$origin_count" == "8" ]] || fail "expected exactly eight reviewed origins"

grep -Fq 'HOST_IP="192.168.0.180"' "$script" || fail "host IP invariant missing"
grep -Fq 'LAN_CIDR="192.168.0.0/24"' "$script" || fail "LAN CIDR invariant missing"
grep -Fq 'ss -H -lntp' "$script" || fail "listener inventory missing"
grep -Fq "docker ps --format '{{.Names}}'" "$script" || fail "Docker owner inventory missing"
grep -Fq 'docker port "$name"' "$script" || fail "Docker published-port inventory missing"
grep -Fq 'ufw status numbered' "$script" || fail "UFW inventory missing"
grep -Fq '/dev/tcp/${host}/${port}' "$script" || fail "TCP-only reachability probe missing"
grep -Fq 'cloudflared_tunnel_ha_connections' "$script" || fail "Cloudflare HA evidence missing"
grep -Fq 'V18_CLOUDFLARE_LAN_ORIGIN_AUDIT=PASS' "$script" || fail "V18 PASS marker missing"

# No Docker mutation. Read-only ps/port are the only Docker commands permitted.
if grep -Eq '(^|[[:space:]])docker[[:space:]]+(run|create|start|stop|restart|rm|rename|pull|rmi|exec|cp|update|kill|pause|unpause)([[:space:]]|$)' "$script"; then
  fail "Docker mutation or intrusive command is forbidden"
fi
if grep -Eq 'docker[[:space:]]+(image|system|container|volume|network)[[:space:]]+(rm|prune|create|connect|disconnect)' "$script"; then
  fail "Docker resource mutation is forbidden"
fi

# No systemd, firewall, Cloudflare or host-power mutation.
if grep -Eq 'systemctl[[:space:]]+(start|stop|restart|try-restart|reload|enable|disable|mask|unmask|edit|reboot|poweroff)' "$script"; then
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

# Avoid secret-bearing or application-content reads.
if grep -Eq 'docker[[:space:]]+inspect|docker[[:space:]]+logs|journalctl|printenv|/proc/.*/environ|(^|[[:space:]])env([[:space:]]|$)' "$script"; then
  fail "secret-bearing/runtime-content read is forbidden"
fi
if grep -Fq '.env' "$script"; then
  fail "environment-file access is forbidden"
fi

# Contract must preserve the read-only and human-policy boundaries.
grep -Fq '**Source review in progress; production audit not yet executed.**' "$contract" || fail "V18 status missing"
grep -Fq 'Merging V18 performs no production mutation.' "$contract" || fail "source-only boundary missing"
grep -Fq 'The operator prints its result to stdout only.' "$contract" || fail "stdout-only boundary missing"
grep -Fq 'It cannot infer a human policy requirement merely from host state.' "$contract" || fail "policy inference boundary missing"
grep -Fq '**keep LAN break-glass**' "$contract" || fail "keep classification missing"
grep -Fq '**loopback migration candidate**' "$contract" || fail "candidate classification missing"
grep -Fq '**application-specific investigation required**' "$contract" || fail "investigation classification missing"
grep -Fq 'Any actual origin change is outside V18.' "$contract" || fail "migration boundary missing"

echo "Cloudflare LAN-origin audit test: PASS"
