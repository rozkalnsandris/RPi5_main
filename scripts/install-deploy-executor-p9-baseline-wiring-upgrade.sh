#!/usr/bin/env bash
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <exact-reviewed-rpi5-main-sha>" >&2
  exit 2
fi
EXPECTED_SHA="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTUAL_SHA="$(/usr/bin/git -C "$ROOT" rev-parse --verify HEAD)"
BASELINE_SOURCE_SHA="416860795831203e1670cb383c527bd212614a1d"
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "expected SHA must be lowercase 40-char hex" >&2; exit 2; }
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || { echo "source SHA mismatch" >&2; exit 1; }
[[ "$(/usr/bin/id -u)" -eq 0 ]] || { echo "P9 baseline wiring upgrade requires root" >&2; exit 1; }

INSTALL_ROOT="/usr/local/lib/rozkalns-deploy-executor"
PACKAGE_ROOT="$INSTALL_ROOT/deploy_executor"
PRODUCER="$PACKAGE_ROOT/p9_control_postcanary_producer.py"
COLLECTOR="$PACKAGE_ROOT/p9_control_postcanary_collector.py"
P9_BIN="/usr/local/sbin/rozkalns-deploy-p9"
BASELINE_BIN="/usr/local/sbin/rozkalns-deploy-p9-control-baseline"
P9_CONFIG_ROOT="/etc/rozkalns-deploy-executor-p9"
STATE_ROOT="/var/lib/rozkalns-deploy-executor-p9"
EVIDENCE_ROOT="/run/rozkalns-deploy-executor-evidence"

SOURCE_PATHS=(
  scripts/install-deploy-executor-p9-baseline-wiring-upgrade.sh
  ops/bin/rozkalns-deploy-p9-control-baseline
  ops/lib/deploy_executor/p9_control_postcanary_collector.py
  ops/lib/deploy_executor/p9_control_postcanary_producer.py
)
for path in "${SOURCE_PATHS[@]}"; do
  [[ -f "$ROOT/$path" && ! -L "$ROOT/$path" ]] || {
    echo "reviewed source path missing or symlink: $path" >&2
    exit 1
  }
done
/usr/bin/git -C "$ROOT" diff --quiet "$EXPECTED_SHA" -- "${SOURCE_PATHS[@]}" || {
  echo "reviewed upgrade source differs from exact expected SHA" >&2
  exit 1
}

for directory in "$PACKAGE_ROOT" "$P9_CONFIG_ROOT" "$STATE_ROOT" "$EVIDENCE_ROOT"; do
  [[ -d "$directory" && ! -L "$directory" ]] || {
    echo "required installed P9 directory missing or symlink: $directory" >&2
    exit 1
  }
done
[[ -f "$P9_BIN" && ! -L "$P9_BIN" ]] || { echo "required installed P9 operator missing or symlink" >&2; exit 1; }
[[ -f "$PRODUCER" && ! -L "$PRODUCER" ]] || { echo "installed Control producer missing or symlink" >&2; exit 1; }
[[ "$(/usr/bin/stat -c '%u:%g:%a' -- "$PRODUCER")" == "0:0:644" ]] || {
  echo "installed Control producer ownership/mode mismatch" >&2
  exit 1
}
/usr/bin/git -C "$ROOT" cat-file -e "$BASELINE_SOURCE_SHA:ops/lib/deploy_executor/p9_control_postcanary_producer.py" || {
  echo "reviewed baseline producer object is unavailable" >&2
  exit 1
}
/usr/bin/cmp -s "$PRODUCER" <(/usr/bin/git -C "$ROOT" show "$BASELINE_SOURCE_SHA:ops/lib/deploy_executor/p9_control_postcanary_producer.py") || {
  echo "installed Control producer does not match reviewed P9 runtime baseline" >&2
  exit 1
}
for target in "$COLLECTOR" "$BASELINE_BIN"; do
  [[ ! -e "$target" ]] || {
    echo "baseline wiring target already exists; refusing ambiguous upgrade: $target" >&2
    exit 1
  }
done

# Authorized post-install P9 baseline wiring mutation begins here. Any later error is STOP/no retry.
/usr/bin/install -o root -g root -m 0644 \
  "$ROOT/ops/lib/deploy_executor/p9_control_postcanary_collector.py" "$COLLECTOR"
/usr/bin/install -o root -g root -m 0755 \
  "$ROOT/ops/bin/rozkalns-deploy-p9-control-baseline" "$BASELINE_BIN"
/usr/bin/install -o root -g root -m 0644 \
  "$ROOT/ops/lib/deploy_executor/p9_control_postcanary_producer.py" "$PRODUCER"

echo "P9_BASELINE_WIRING_UPGRADE=PASS source_sha=$EXPECTED_SHA baseline_source_sha=$BASELINE_SOURCE_SHA"
echo "P9_RUNTIME_ACTIVE=NO"
echo "P9_EVIDENCE_PRODUCED=NO"
echo "P9_CREDENTIAL_MUTATION=NO"
echo "P9_RUN_AUTHORIZED=NO"
