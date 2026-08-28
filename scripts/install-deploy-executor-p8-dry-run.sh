#!/usr/bin/env bash
set -euo pipefail

EXPECTED_APP_ID=4748870
EXPECTED_INSTALLATION_ID=157217641
EXPECTED_REPOSITORY_ID=1328835922
SERVICE_USER=rozkalns-deploy-executor
SERVICE_GROUP=rozkalns-deploy-executor
INSTALL_ROOT=/usr/local/libexec/rozkalns-deploy-executor
CONFIG_ROOT=/etc/rozkalns-deploy-executor
STATE_ROOT=/var/lib/rozkalns-deploy-executor
SYSTEMD_ROOT=/etc/systemd/system

PRIVATE_KEY_SOURCE=
ACTIVATE=false

usage() {
  cat <<'EOF'
Usage:
  sudo scripts/install-deploy-executor-p8-dry-run.sh \
    --private-key /absolute/path/to/rozkalns-deploy-executor.private-key.pem \
    [--activate]

This installer is P8 read-only/dry-run only. It refuses a non-empty or
execution-enabled production registry. --activate performs one read-only
service probe, then enables the two-minute timer.
EOF
}

while (($#)); do
  case "$1" in
    --private-key)
      [[ $# -ge 2 ]] || { echo "P8_INSTALL=FAIL missing_private_key_value" >&2; exit 64; }
      PRIVATE_KEY_SOURCE=$2
      shift 2
      ;;
    --activate)
      ACTIVATE=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "P8_INSTALL=FAIL unexpected_argument" >&2
      exit 64
      ;;
  esac
done

[[ ${EUID} -eq 0 ]] || { echo "P8_INSTALL=FAIL root_required" >&2; exit 1; }
[[ -n ${PRIVATE_KEY_SOURCE} && ${PRIVATE_KEY_SOURCE} == /* ]] || {
  echo "P8_INSTALL=FAIL private_key_absolute_path_required" >&2
  exit 64
}

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd -P)

CONFIG_SOURCE="${REPO_ROOT}/ops/deploy/executor-p8-dry-run-config.json"
REGISTRY_SOURCE="${REPO_ROOT}/ops/deploy/executor-operations.json"
SERVICE_SOURCE="${REPO_ROOT}/ops/systemd/rozkalns-deploy-executor.service"
TIMER_SOURCE="${REPO_ROOT}/ops/systemd/rozkalns-deploy-executor.timer"
POLLER_SOURCE="${REPO_ROOT}/ops/bin/rozkalns-deploy-poll"
DISPATCH_SOURCE="${REPO_ROOT}/ops/bin/rozkalns-deploy-dispatch"
LIB_SOURCE="${REPO_ROOT}/ops/lib/deploy_executor"

PACKAGE_FILES=(
  __init__.py
  adapters.py
  cv_adapter.py
  dispatch_contract.py
  github_app_auth.py
  hermes_deals_origin_adapter.py
  p8_poller.py
  protocol.py
  queue_normalizer.py
  registry.py
  state.py
  transport.py
)

# ---- Complete preflight: no host mutation above this line. ----

for path in \
  "$CONFIG_SOURCE" "$REGISTRY_SOURCE" "$SERVICE_SOURCE" "$TIMER_SOURCE" \
  "$POLLER_SOURCE" "$DISPATCH_SOURCE"; do
  [[ -f "$path" && ! -L "$path" ]] || {
    echo "P8_INSTALL=FAIL missing_or_symlink_source" >&2
    exit 1
  }
done

for name in "${PACKAGE_FILES[@]}"; do
  [[ -f "${LIB_SOURCE}/${name}" && ! -L "${LIB_SOURCE}/${name}" ]] || {
    echo "P8_INSTALL=FAIL package_source_mismatch" >&2
    exit 1
  }
done

[[ -f "$PRIVATE_KEY_SOURCE" && ! -L "$PRIVATE_KEY_SOURCE" ]] || {
  echo "P8_INSTALL=FAIL private_key_not_regular" >&2
  exit 1
}
key_mode=$(stat -c '%a' -- "$PRIVATE_KEY_SOURCE")
case "$key_mode" in
  400|600) ;;
  *)
    echo "P8_INSTALL=FAIL private_key_mode_must_be_400_or_600" >&2
    exit 1
    ;;
esac
/usr/bin/openssl pkey -in "$PRIVATE_KEY_SOURCE" -check -noout >/dev/null 2>&1 || {
  echo "P8_INSTALL=FAIL private_key_invalid" >&2
  exit 1
}

python3 - "$CONFIG_SOURCE" "$REGISTRY_SOURCE" <<'PY'
import json
import sys

config = json.load(open(sys.argv[1], encoding="utf-8"))
registry = json.load(open(sys.argv[2], encoding="utf-8"))

expected = {
    "schema": "rozkalns.deploy-executor-p8-dry-run-config.v1",
    "mode": "READ_ONLY_DRY_RUN",
    "app_id": 4748870,
    "installation_id": 157217641,
    "authorization_repository": "rozkalnsandris/ops-workflows",
    "authorization_repository_id": 1328835922,
    "owner_login": "rozkalnsandris",
    "owner_id": 277435981,
    "poll_interval_seconds": 120,
    "issue_title_prefix": "[LIVE-AUTH][PENDING] ",
    "mutation_dispatch_enabled": False,
    "result_writer_enabled": False,
}
if config != expected:
    raise SystemExit("P8_INSTALL=FAIL config_contract_mismatch")
if registry != {"schema_version": 1, "execution_enabled": False, "operations": []}:
    raise SystemExit("P8_INSTALL=FAIL production_registry_not_inert")
PY

if getent passwd "$SERVICE_USER" >/dev/null; then
  user_shell=$(getent passwd "$SERVICE_USER" | cut -d: -f7)
  user_group=$(id -gn "$SERVICE_USER")
  [[ "$user_shell" == "/usr/sbin/nologin" || "$user_shell" == "/bin/false" ]] || {
    echo "P8_INSTALL=FAIL existing_service_user_shell_mismatch" >&2
    exit 1
  }
  [[ "$user_group" == "$SERVICE_GROUP" ]] || {
    echo "P8_INSTALL=FAIL existing_service_user_group_mismatch" >&2
    exit 1
  }
fi

for target in \
  "${SYSTEMD_ROOT}/rozkalns-deploy-executor.service" \
  "${SYSTEMD_ROOT}/rozkalns-deploy-executor.timer" \
  "${CONFIG_ROOT}/config.json" \
  "${CONFIG_ROOT}/executor-operations.json" \
  "${CONFIG_ROOT}/github-app.pem" \
  "${INSTALL_ROOT}/poller" \
  "${INSTALL_ROOT}/dispatcher"; do
  [[ ! -e "$target" ]] || {
    echo "P8_INSTALL=FAIL existing_target_requires_fresh_review" >&2
    exit 1
  }
done

echo "P8_INSTALL_PREFLIGHT=PASS"
echo "APP_ID=${EXPECTED_APP_ID}"
echo "INSTALLATION_ID=${EXPECTED_INSTALLATION_ID}"
echo "AUTHORIZATION_REPOSITORY_ID=${EXPECTED_REPOSITORY_ID}"
echo "MUTATION_DISPATCH_ENABLED=false"
echo "RESULT_WRITER_ENABLED=false"

# ---- Authorized P8 host mutation begins here. Errors stop; no auto rollback. ----

if ! getent group "$SERVICE_GROUP" >/dev/null; then
  groupadd --system "$SERVICE_GROUP"
fi
if ! getent passwd "$SERVICE_USER" >/dev/null; then
  useradd \
    --system \
    --gid "$SERVICE_GROUP" \
    --home-dir /nonexistent \
    --no-create-home \
    --shell /usr/sbin/nologin \
    "$SERVICE_USER"
fi

install -d -o root -g root -m 0755 "$INSTALL_ROOT"
install -d -o root -g root -m 0755 "${INSTALL_ROOT}/deploy_executor"
install -d -o root -g root -m 0755 "$CONFIG_ROOT"

for name in "${PACKAGE_FILES[@]}"; do
  install -o root -g root -m 0644 "${LIB_SOURCE}/${name}" "${INSTALL_ROOT}/deploy_executor/${name}"
done
install -o root -g root -m 0755 "$POLLER_SOURCE" "${INSTALL_ROOT}/poller"
install -o root -g root -m 0755 "$DISPATCH_SOURCE" "${INSTALL_ROOT}/dispatcher"
install -o root -g root -m 0644 "$CONFIG_SOURCE" "${CONFIG_ROOT}/config.json"
install -o root -g root -m 0444 "$REGISTRY_SOURCE" "${CONFIG_ROOT}/executor-operations.json"
install -o root -g root -m 0400 "$PRIVATE_KEY_SOURCE" "${CONFIG_ROOT}/github-app.pem"
install -o root -g root -m 0644 "$SERVICE_SOURCE" "${SYSTEMD_ROOT}/rozkalns-deploy-executor.service"
install -o root -g root -m 0644 "$TIMER_SOURCE" "${SYSTEMD_ROOT}/rozkalns-deploy-executor.timer"

systemctl daemon-reload
systemd-analyze verify \
  "${SYSTEMD_ROOT}/rozkalns-deploy-executor.service" \
  "${SYSTEMD_ROOT}/rozkalns-deploy-executor.timer" >/dev/null
systemd-analyze security --offline=yes \
  "${SYSTEMD_ROOT}/rozkalns-deploy-executor.service" >/dev/null

if [[ "$ACTIVATE" == true ]]; then
  systemctl start rozkalns-deploy-executor.service
  systemctl enable --now rozkalns-deploy-executor.timer
fi

echo "P8_INSTALL=PASS"
echo "ACTIVATED=${ACTIVATE}"
echo "MUTATION_DISPATCH_ENABLED=false"
echo "PRODUCTION_MUTATION_STARTED=false"
