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
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "expected SHA must be lowercase 40-char hex" >&2; exit 2; }
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || { echo "source SHA mismatch" >&2; exit 1; }
[[ "$(/usr/bin/id -u)" -eq 0 ]] || { echo "P9 runtime installer requires root" >&2; exit 1; }

SERVICE_USER="rozkalns-deploy-executor"
SERVICE_GROUP="rozkalns-deploy-executor"
INSTALL_ROOT="/usr/local/lib/rozkalns-deploy-executor"
BIN="/usr/local/sbin/rozkalns-deploy-p9"
BASELINE_BIN="/usr/local/sbin/rozkalns-deploy-p9-control-baseline"
P8_CONFIG_ROOT="/etc/rozkalns-deploy-executor"
P9_CONFIG_ROOT="/etc/rozkalns-deploy-executor-p9"
STATE_ROOT="/var/lib/rozkalns-deploy-executor-p9"
STATE_DB="$STATE_ROOT/state.sqlite3"
EVIDENCE_ROOT="/run/rozkalns-deploy-executor-evidence"
EXECUTOR_KEY="$P8_CONFIG_ROOT/github-app.pem"
SOURCE_KEY="/root/.config/rozkalns-automation/github-app.pem"

PACKAGE_FILES=(
  __init__.py
  adapters.py
  control_center_postcanary_adapter.py
  github_app_auth.py
  p9_canary.py
  p9_control_postcanary_collector.py
  p9_control_postcanary_producer.py
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
  scripts/install-deploy-executor-p9-runtime.sh
  ops/bin/rozkalns-deploy-p9
  ops/bin/rozkalns-deploy-p9-control-baseline
  ops/deploy/executor-operations.json
  ops/deploy/executor-p9-isolated-auth-surface.json
)
for name in "${PACKAGE_FILES[@]}"; do
  SOURCE_PATHS+=("ops/lib/deploy_executor/$name")
done

# Complete source/host metadata preflight. No host mutation above or inside this block.
for path in "${SOURCE_PATHS[@]}"; do
  [[ -f "$ROOT/$path" && ! -L "$ROOT/$path" ]] || {
    echo "reviewed source path missing or symlink: $path" >&2
    exit 1
  }
done
/usr/bin/git -C "$ROOT" diff --quiet "$EXPECTED_SHA" -- "${SOURCE_PATHS[@]}" || {
  echo "reviewed source differs from exact expected SHA" >&2
  exit 1
}

/usr/bin/getent passwd "$SERVICE_USER" >/dev/null || { echo "existing P8 service user is required" >&2; exit 1; }
/usr/bin/getent group "$SERVICE_GROUP" >/dev/null || { echo "existing P8 service group is required" >&2; exit 1; }
[[ -d /var/lib/rozkalns-deploy-executor ]] || { echo "existing P8 state directory is required" >&2; exit 1; }

for credential in "$EXECUTOR_KEY" "$SOURCE_KEY"; do
  [[ -f "$credential" && ! -L "$credential" ]] || {
    echo "existing GitHub App credential must be a regular non-symlink file" >&2
    exit 1
  }
  [[ "$(/usr/bin/stat -c '%u' -- "$credential")" -eq 0 ]] || {
    echo "existing GitHub App credential must be root-owned" >&2
    exit 1
  }
  credential_mode="$(/usr/bin/stat -c '%a' -- "$credential")"
  case "$credential_mode" in
    400|600) ;;
    *)
      echo "existing GitHub App credential mode must be 0400 or 0600" >&2
      exit 1
      ;;
  esac
done

for target in "$INSTALL_ROOT" "$BIN" "$BASELINE_BIN" "$P9_CONFIG_ROOT" "$STATE_ROOT" "$EVIDENCE_ROOT"; do
  [[ ! -e "$target" ]] || {
    echo "P9 target already exists; refusing ambiguous or non-transactional reinstall: $target" >&2
    exit 1
  }
done

# Authorized P9 host installation mutation begins here. Any later error is STOP/no retry.
/usr/bin/install -d -o root -g root -m 0755 "$INSTALL_ROOT/deploy_executor"
for name in "${PACKAGE_FILES[@]}"; do
  /usr/bin/install -o root -g root -m 0644 \
    "$ROOT/ops/lib/deploy_executor/$name" "$INSTALL_ROOT/deploy_executor/$name"
done
/usr/bin/install -o root -g root -m 0755 "$ROOT/ops/bin/rozkalns-deploy-p9" "$BIN"
/usr/bin/install -o root -g root -m 0755 \
  "$ROOT/ops/bin/rozkalns-deploy-p9-control-baseline" "$BASELINE_BIN"
/usr/bin/install -d -o root -g root -m 0755 "$P9_CONFIG_ROOT"
/usr/bin/install -o root -g root -m 0644 \
  "$ROOT/ops/deploy/executor-operations.json" "$P9_CONFIG_ROOT/executor-operations.json"
/usr/bin/install -o root -g root -m 0644 \
  "$ROOT/ops/deploy/executor-p9-isolated-auth-surface.json" \
  "$P9_CONFIG_ROOT/executor-p9-isolated-auth-surface.json"

/usr/bin/install -d -o root -g root -m 0700 "$STATE_ROOT"
PYTHONPATH="$INSTALL_ROOT" /usr/bin/python3 - <<PY
from deploy_executor.state import StateStore
store = StateStore("$STATE_DB", bootstrap=True)
store.close()
PY
/usr/bin/chown root:root "$STATE_DB"
/usr/bin/chmod 0600 "$STATE_DB"
/usr/bin/install -d -o root -g "$SERVICE_GROUP" -m 0750 "$EVIDENCE_ROOT"

echo "P9_RUNTIME_INSTALL=PASS source_sha=$EXPECTED_SHA"
echo "P9_RUNTIME_ACTIVE=NO"
echo "P9_EVIDENCE_PRESENT=NO"
echo "P9_SOURCE_APP_SCOPE_VERIFIED=NO"
echo "P9_RUN_AUTHORIZED=NO"
