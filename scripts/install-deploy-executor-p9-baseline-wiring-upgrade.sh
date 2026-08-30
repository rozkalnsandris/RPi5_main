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

SERVICE_GROUP="rozkalns-deploy-executor"
INSTALL_ROOT="/usr/local/lib/rozkalns-deploy-executor"
PACKAGE_ROOT="$INSTALL_ROOT/deploy_executor"
PRODUCER="$PACKAGE_ROOT/p9_control_postcanary_producer.py"
COLLECTOR="$PACKAGE_ROOT/p9_control_postcanary_collector.py"
P9_BIN="/usr/local/sbin/rozkalns-deploy-p9"
BASELINE_BIN="/usr/local/sbin/rozkalns-deploy-p9-control-baseline"
P9_CONFIG_ROOT="/etc/rozkalns-deploy-executor-p9"
P9_REGISTRY="$P9_CONFIG_ROOT/executor-operations.json"
P9_ISOLATED_AUTH="$P9_CONFIG_ROOT/executor-p9-isolated-auth-surface.json"
STATE_ROOT="/var/lib/rozkalns-deploy-executor-p9"
STATE_DB="$STATE_ROOT/state.sqlite3"
EVIDENCE_ROOT="/run/rozkalns-deploy-executor-evidence"

BASELINE_PACKAGE_FILES=(
  __init__.py
  adapters.py
  control_center_postcanary_adapter.py
  github_app_auth.py
  p9_canary.py
  p9_evidence.py
  p9_host_runtime.py
  p9_isolated_auth_surface.py
  p9_provenance.py
  p9_runtime.py
  p9_source_auth.py
  protocol.py
  queue_normalizer.py
  registry.py
  source_evidence.py
  state.py
  transport.py
)
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

require_directory_metadata() {
  local target="$1"
  local expected="$2"
  [[ -d "$target" && ! -L "$target" ]] || {
    echo "required installed P9 directory missing or symlink: $target" >&2
    exit 1
  }
  [[ "$(/usr/bin/stat -c '%u:%g:%a' -- "$target")" == "$expected" ]] || {
    echo "installed P9 directory ownership/mode mismatch: $target" >&2
    exit 1
  }
}

verify_installed_baseline_file() {
  local source_path="$1"
  local target="$2"
  local expected_mode="$3"
  [[ -f "$target" && ! -L "$target" ]] || {
    echo "required reviewed P9 baseline file missing or symlink: $target" >&2
    exit 1
  }
  [[ "$(/usr/bin/stat -c '%u:%g:%a' -- "$target")" == "0:0:$expected_mode" ]] || {
    echo "reviewed P9 baseline file ownership/mode mismatch: $target" >&2
    exit 1
  }
  /usr/bin/git -C "$ROOT" cat-file -e "$BASELINE_SOURCE_SHA:$source_path" || {
    echo "reviewed P9 baseline source object unavailable: $source_path" >&2
    exit 1
  }
  /usr/bin/cmp -s "$target" <(/usr/bin/git -C "$ROOT" show "$BASELINE_SOURCE_SHA:$source_path") || {
    echo "installed P9 baseline file differs from reviewed source: $target" >&2
    exit 1
  }
}

require_directory_metadata "$PACKAGE_ROOT" "0:0:755"
require_directory_metadata "$P9_CONFIG_ROOT" "0:0:755"
require_directory_metadata "$STATE_ROOT" "0:0:700"
SERVICE_GID="$(/usr/bin/getent group "$SERVICE_GROUP" | /usr/bin/cut -d: -f3)"
[[ "$SERVICE_GID" =~ ^[0-9]+$ ]] || { echo "executor service group is unavailable" >&2; exit 1; }
require_directory_metadata "$EVIDENCE_ROOT" "0:$SERVICE_GID:750"
[[ -f "$STATE_DB" && ! -L "$STATE_DB" ]] || { echo "required P9 state database missing or symlink" >&2; exit 1; }
[[ "$(/usr/bin/stat -c '%u:%g:%a' -- "$STATE_DB")" == "0:0:600" ]] || {
  echo "P9 state database ownership/mode mismatch" >&2
  exit 1
}

for name in "${BASELINE_PACKAGE_FILES[@]}"; do
  verify_installed_baseline_file \
    "ops/lib/deploy_executor/$name" "$PACKAGE_ROOT/$name" 644
done
verify_installed_baseline_file "ops/bin/rozkalns-deploy-p9" "$P9_BIN" 755
verify_installed_baseline_file "ops/deploy/executor-operations.json" "$P9_REGISTRY" 644
verify_installed_baseline_file \
  "ops/deploy/executor-p9-isolated-auth-surface.json" "$P9_ISOLATED_AUTH" 644

for target in "$PRODUCER" "$COLLECTOR" "$BASELINE_BIN"; do
  [[ ! -e "$target" ]] || {
    echo "baseline wiring target already exists; refusing ambiguous upgrade: $target" >&2
    exit 1
  }
done

# Authorized post-install P9 baseline wiring mutation begins here. Any later error is STOP/no retry.
/usr/bin/install -o root -g root -m 0644 \
  "$ROOT/ops/lib/deploy_executor/p9_control_postcanary_producer.py" "$PRODUCER"
/usr/bin/install -o root -g root -m 0644 \
  "$ROOT/ops/lib/deploy_executor/p9_control_postcanary_collector.py" "$COLLECTOR"
/usr/bin/install -o root -g root -m 0755 \
  "$ROOT/ops/bin/rozkalns-deploy-p9-control-baseline" "$BASELINE_BIN"

echo "P9_BASELINE_WIRING_UPGRADE=PASS source_sha=$EXPECTED_SHA baseline_source_sha=$BASELINE_SOURCE_SHA"
echo "P9_RUNTIME_ACTIVE=NO"
echo "P9_EVIDENCE_PRODUCED=NO"
echo "P9_CREDENTIAL_MUTATION=NO"
echo "P9_RUN_AUTHORIZED=NO"
