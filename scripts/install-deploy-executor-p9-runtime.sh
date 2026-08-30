#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <exact-reviewed-rpi5-main-sha>" >&2
  exit 2
fi
EXPECTED_SHA="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTUAL_SHA="$(git -C "$ROOT" rev-parse HEAD)"
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "expected SHA must be lowercase 40-char hex" >&2; exit 2; }
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || { echo "source SHA mismatch" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || { echo "P9 runtime installer requires root" >&2; exit 1; }

SERVICE_USER="rozkalns-deploy-executor"
SERVICE_GROUP="rozkalns-deploy-executor"
INSTALL_ROOT="/usr/local/lib/rozkalns-deploy-executor"
BIN="/usr/local/sbin/rozkalns-deploy-p9"
CONFIG_ROOT="/etc/rozkalns-deploy-executor"
STATE_ROOT="/var/lib/rozkalns-deploy-executor-p9"
STATE_DB="$STATE_ROOT/state.sqlite3"
EVIDENCE_ROOT="/run/rozkalns-deploy-executor-evidence"

getent passwd "$SERVICE_USER" >/dev/null || { echo "existing P8 service user is required" >&2; exit 1; }
getent group "$SERVICE_GROUP" >/dev/null || { echo "existing P8 service group is required" >&2; exit 1; }
[[ -d /var/lib/rozkalns-deploy-executor ]] || { echo "existing P8 state directory is required" >&2; exit 1; }
[[ -f "$CONFIG_ROOT/github-app.pem" ]] || { echo "existing Deploy Executor credential is required" >&2; exit 1; }
[[ -f /root/.config/rozkalns-automation/github-app.pem ]] || { echo "existing Rozkalns Automation credential is required" >&2; exit 1; }
[[ ! -e "$STATE_ROOT" ]] || { echo "P9 state root already exists; refusing non-transactional reinstall" >&2; exit 1; }
[[ ! -e "$EVIDENCE_ROOT" ]] || { echo "P9 evidence root already exists; refusing ambiguous ownership" >&2; exit 1; }

install -d -o root -g root -m 0755 "$INSTALL_ROOT/deploy_executor"
for name in \
  __init__.py adapters.py control_center_postcanary_adapter.py github_app_auth.py \
  p9_canary.py p9_evidence.py p9_host_runtime.py p9_isolated_auth_surface.py \
  p9_provenance.py p9_runtime.py p9_source_auth.py protocol.py queue_normalizer.py \
  registry.py source_evidence.py state.py transport.py; do
  install -o root -g root -m 0644 "$ROOT/ops/lib/deploy_executor/$name" "$INSTALL_ROOT/deploy_executor/$name"
done
install -o root -g root -m 0755 "$ROOT/ops/bin/rozkalns-deploy-p9" "$BIN"
install -o root -g root -m 0644 "$ROOT/ops/deploy/executor-operations.json" "$CONFIG_ROOT/executor-operations.json"
install -o root -g root -m 0644 "$ROOT/ops/deploy/executor-p9-isolated-auth-surface.json" "$CONFIG_ROOT/executor-p9-isolated-auth-surface.json"

install -d -o root -g root -m 0700 "$STATE_ROOT"
PYTHONPATH="$INSTALL_ROOT" python3 - <<PY
from deploy_executor.state import StateStore
store = StateStore("$STATE_DB", bootstrap=True)
store.close()
PY
chown root:root "$STATE_DB"
chmod 0600 "$STATE_DB"
install -d -o root -g "$SERVICE_GROUP" -m 0750 "$EVIDENCE_ROOT"

echo "P9_RUNTIME_INSTALL=PASS source_sha=$EXPECTED_SHA"
echo "P9_RUNTIME_ACTIVE=NO"
echo "P9_EVIDENCE_PRESENT=NO"
echo "P9_SOURCE_APP_SCOPE_VERIFIED=NO"
echo "P9_RUN_AUTHORIZED=NO"
