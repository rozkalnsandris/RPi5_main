#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

unit="ops/systemd/hermes-tech-web.service"
contract="docs/V14_HERMES_TECH_WEB_RUNTIME_CONTRACT.md"
image="sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa"

fail() {
  echo "Hermes Tech web runtime test: FAIL: $*" >&2
  exit 1
}

[[ -f "$unit" ]] || fail "missing $unit"
[[ -f "$contract" ]] || fail "missing $contract"

# Exact immutable local image and no implicit image update during the network/lifecycle migration.
grep -Fq -- "--pull=never" "$unit" || fail "missing --pull=never"
grep -Fq -- "$image" "$unit" || fail "missing exact running image ID"
if grep -Fq 'nginx:alpine' "$unit"; then
  fail "mutable nginx:alpine reference is forbidden"
fi

# Loopback-only origin contract. Wildcard, LAN and shorthand publishes are forbidden.
grep -Fq -- '--publish 127.0.0.1:8089:80' "$unit" || fail "missing exact loopback publish"
if grep -Eq -- '--publish[ =](8089:80|0\.0\.0\.0:8089:80|\[::\]:8089:80|192\.168\.0\.180:8089:80)' "$unit"; then
  fail "8089 publish is broader than loopback"
fi

# Preserve the verified static content and logging contract.
grep -Fq -- '--mount type=bind,src=/home/andris/hermes-tech/site/public,dst=/usr/share/nginx/html,readonly' "$unit" || fail "static-site read-only bind drift"
grep -Fq -- '--log-driver=json-file' "$unit" || fail "json-file logging missing"
grep -Fq -- '--log-opt max-size=10m' "$unit" || fail "max-size logging contract drift"
grep -Fq -- '--log-opt max-file=3' "$unit" || fail "max-file logging contract drift"

# Exactly one restart supervisor: systemd. Docker restart policy remains disabled.
grep -Fq -- '--restart=no' "$unit" || fail "Docker restart policy must be no"
grep -Fqx 'Restart=on-failure' "$unit" || fail "systemd restart supervision missing"
grep -Fqx 'ExecStart=/usr/bin/docker start --attach hermes-blog' "$unit" || fail "systemd must supervise attached container"

# Starting the reviewed unit while the legacy wildcard container still runs must not forcibly remove it.
if grep -Eq '^ExecStartPre=.*docker rm -f([[:space:]]|$)' "$unit"; then
  fail "ExecStartPre must not force-remove a running legacy container"
fi
if grep -Eq '^ExecStopPost=.*docker rm -f([[:space:]]|$)' "$unit"; then
  fail "ExecStopPost must not force-remove a container it may not own"
fi

# Basic service containment that remains compatible with Docker socket access.
for line in \
  'NoNewPrivileges=yes' \
  'PrivateTmp=yes' \
  'ProtectSystem=full' \
  'ProtectHome=read-only' \
  'CapabilityBoundingSet=' \
  'AmbientCapabilities='; do
  grep -Fqx "$line" "$unit" || fail "missing hardening line: $line"
done

# Validate systemd syntax in CI without requiring Docker or the production content path.
command -v systemd-analyze >/dev/null 2>&1 || fail "systemd-analyze is required"
tmp_unit="$(mktemp --suffix=.service)"
trap 'rm -f "$tmp_unit"' EXIT
sed \
  -e 's#Requires=docker.service#Requires=#' \
  -e 's#After=docker.service network-online.target#After=network-online.target#' \
  -e 's#ConditionPathExists=/home/andris/hermes-tech/site/public#ConditionPathExists=/etc/hosts#' \
  -e 's#/usr/bin/docker#/usr/bin/true#g' \
  "$unit" > "$tmp_unit"
systemd-analyze verify "$tmp_unit" >/dev/null || fail "systemd-analyze verify rejected unit"

# Contract must keep ownership and production-apply boundaries explicit.
grep -Fq 'Hermes Tech application deployment owns content generation and publication files only.' "$contract" || fail "missing app ownership boundary"
grep -Fq '`RPi5_main` owns the `hermes-blog` container lifecycle.' "$contract" || fail "missing host runtime ownership boundary"
grep -Fq 'Merging V14 performs no production mutation.' "$contract" || fail "missing merge/no-mutation boundary"
grep -Fq 'http://127.0.0.1:8089' "$contract" || fail "missing final loopback origin"

echo "Hermes Tech web runtime test: PASS"
