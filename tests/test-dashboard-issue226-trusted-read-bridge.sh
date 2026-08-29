#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

bridge="ops/bin/rpi5-dashboard-issue226-readonly-bridge"
service="ops/systemd/rpi5-dashboard-issue226-readonly-bridge.service"
path_unit="ops/systemd/rpi5-dashboard-issue226-readonly-bridge.path"
doc="docs/DASHBOARD_ISSUE226_TRUSTED_READ_BRIDGE.md"
registry="ops/deploy/executor-operations.json"
target="3fcdd12db07bf2ef5504a3fa8fafe873d5b56c6d"
input_root="/var/cache/dashboard-rpi5-operator/issue226-${target}"

for file in "$bridge" "$service" "$path_unit" "$doc" "$registry"; do
  [[ -f "$file" && ! -L "$file" ]]
done
bash -n "$bridge"

for expected in \
  "$target" \
  "$input_root" \
  'dcfee173c5f62b914428d5bcff1eba410358e626' \
  'bea0f30602d119ae53b81e70ce2d4c283d369ce8' \
  'f37c315dfda4ac00ed7dcf793fa8e2f44bfeff57' \
  'c501bea57c0d5c35e7961ae1f1e5593a02268661' \
  '4b923e2282c6ddd7781495ac7e7ff02bcd09919f' \
  'git hash-object --no-filters' \
  'SOURCE_BUNDLE_PIN=PASS' \
  '/var/lib/dashboard-rpi5/evidence/issue226-recovery-preflight.txt' \
  'copy_manifest_allowlisted_release,write_verified_manifest_marker,atomic_current_symlink_swap'; do
  grep -Fq -- "$expected" "$bridge"
done

for forbidden in \
  --apply \
  'sudo ' \
  'usermod ' \
  'groupmod ' \
  'setfacl ' \
  'systemctl start' \
  'systemctl stop' \
  'systemctl restart' \
  'systemctl reload' \
  'systemctl enable' \
  'systemctl disable' \
  'daemon-reload' \
  'docker.sock' \
  'docker run' \
  'eval ' \
  'bash -c' \
  'sh -c'; do
  if grep -Fq -- "$forbidden" "$bridge"; then
    echo "forbidden bridge surface: $forbidden" >&2
    exit 1
  fi
done

# The staged source is copied to root-private runtime storage before any pinned
# dashboard code is executed, closing the operator-writable source TOCTOU boundary.
grep -Fq 'install -D -m 0600 -- "$staged" "$runtime"' "$bridge"
grep -Fq '/usr/bin/bash "$helper"' "$bridge"
grep -Fq 'unset NODE_OPTIONS NODE_PATH BASH_ENV ENV CDPATH' "$bridge"
grep -Fq "[[ ! -e \"\$RUNTIME_SOURCE_ROOT\" && ! -L \"\$RUNTIME_SOURCE_ROOT\" ]]" "$bridge"

for expected in \
  'User=root' \
  'Group=root' \
  'NoNewPrivileges=yes' \
  'CapabilityBoundingSet=CAP_SYS_PTRACE' \
  'ProtectSystem=strict' \
  'ProtectHome=read-only' \
  'NoExecPaths=/home' \
  'PrivateDevices=yes' \
  'DevicePolicy=closed' \
  'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6' \
  'IPAddressDeny=any' \
  'IPAddressAllow=localhost' \
  'StateDirectory=dashboard-rpi5' \
  'RuntimeDirectory=dashboard-rpi5-issue226' \
  'ReadOnlyPaths=/var/cache/dashboard-rpi5-operator' \
  'ReadWritePaths=/var/lib/dashboard-rpi5/evidence'; do
  grep -Fq -- "$expected" "$service"
done
if grep -Eq '^(SupplementaryGroups|AmbientCapabilities)=.+' "$service"; then
  echo "bridge service must not gain supplementary/ambient authority" >&2
  exit 1
fi

grep -Fq "PathChanged=${input_root}/READY" "$path_unit"
grep -Fq 'Unit=rpi5-dashboard-issue226-readonly-bridge.service' "$path_unit"
if grep -Fq 'PathExists=' "$path_unit"; then
  echo "bridge trigger must require an explicit READY change, not persistent existence" >&2
  exit 1
fi

python3 - <<'PY'
import json
from pathlib import Path
value = json.loads(Path("ops/deploy/executor-operations.json").read_text(encoding="utf-8"))
assert value == {"schema_version": 1, "execution_enabled": False, "operations": []}, value
PY

grep -Fq 'SOURCE ONLY / DORMANT / NOT INSTALLED' "$doc"
grep -Fq "$target" "$doc"
grep -Fq '/var/cache/dashboard-rpi5-operator/' "$doc"
grep -Fq 'does not change' "$doc"
grep -Fq 'executor-operations.json' "$doc"
grep -Fq 'separate exact owner authorization' "$doc"

printf 'dashboard #226 trusted-read bridge source contract: PASS\n'
