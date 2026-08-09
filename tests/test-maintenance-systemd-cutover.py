#!/usr/bin/env python3
from __future__ import annotations

import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/rpi5-maintenance-systemd-cutover"
text = SCRIPT.read_text(encoding="utf-8")

assert text.startswith("#!/usr/bin/env bash\n")
assert SCRIPT.stat().st_mode & stat.S_IXUSR, "systemd cutover operator must be executable"
assert "set -Eeuo pipefail" in text
assert "EXPECTED_LIVE_V17_SHA256=\"bd0afe74dea18742a002c852d59fc67ec848a032116d2adc314c24848895e24c\"" in text
assert "--allow-persistent-catchup" in text
assert "REFUSED: --activate requires --allow-persistent-catchup" in text
assert "/etc/rpi5-maintenance/required-containers" in text
assert 'MAINTENANCE_LIB_DIR="/usr/local/lib/rpi5-maintenance"' in text
assert text.count("/usr/local/lib/rpi5-maintenance") == 1
assert "/usr/local/libexec/rpi5-maintenance" not in text
assert 'CREDSTORE_DIR="/etc/credstore"' in text
assert 'TOKEN_CREDENTIAL="${CREDSTORE_DIR}/rpi5-maintenance-telegram-token"' in text
assert 'CHAT_CREDENTIAL="${CREDSTORE_DIR}/rpi5-maintenance-telegram-chat-id"' in text

# Public source must derive the maintenance user's home instead of embedding a
# concrete host home path or RFC1918 address.
assert not re.search(r"/home/[A-Za-z0-9._-]+/", text)
assert not re.search(r"(?<![0-9])192\.168(?:\.[0-9]{1,3}){2}(?![0-9])", text)
assert "UPDATE_HOME=\"$(getent passwd \"$UPDATE_USER\"" in text

install_start = text.index("install_reviewed_files() {")
install_end = text.index("\nbackup_and_remove_legacy_cron() {", install_start)
install_body = text[install_start:install_end]
assert "systemctl enable" not in install_body
assert "systemctl start" not in install_body
assert "systemctl daemon-reload" in install_body
assert "systemd-analyze verify" in install_body
assert 'install -d -o root -g root -m 0755 "$MAINTENANCE_LIB_DIR"' in install_body
assert '"${MAINTENANCE_LIB_DIR}/$name"' in install_body

validate_start = text.index("validate_installed_targets() {")
validate_end = text.index("\ninstall_reviewed_files() {", validate_start)
validate_body = text[validate_start:validate_end]
assert '"${MAINTENANCE_LIB_DIR}/rpi5-update-hermes-status.sh"' in validate_body
assert '"${MAINTENANCE_LIB_DIR}/rpi5-maintenance-telegram.py"' in validate_body

activate_start = text.index("activate_systemd_scheduler() {")
activate_end = text.index("\nverify_scheduler() {", activate_start)
activate = text[activate_start:activate_end]

catchup = activate.index('[[ "$ALLOW_PERSISTENT_CATCHUP" -eq 1 ]]')
preflight = activate.index("legacy_cron_preflight")
backup = activate.index("backup_and_remove_legacy_cron")
enable_post = activate.index("systemctl enable rpi5-post-reboot.service")
enable_timers = activate.index("systemctl enable --now rpi5-update.timer rpi5-monitor.timer")
marker = activate.index(': >"$ACTIVE_MARKER"')
assert catchup < preflight < backup < enable_post < enable_timers < marker
assert "restore_legacy_cron" in activate
assert "systemctl disable --now rpi5-update.timer rpi5-monitor.timer" in activate

rollback_start = text.index("rollback_scheduler() {")
rollback_end = text.index("\ncase \"$MODE\" in", rollback_start)
rollback = text[rollback_start:rollback_end]
assert rollback.index("systemctl disable --now") < rollback.index("restore_legacy_cron")
assert "legacy_cron_preflight" in rollback

# Never test the full updater by starting the mutating systemd service as part
# of migration. A later explicit production run is a separate decision.
assert "systemctl start rpi5-update.service" not in text
assert "systemctl restart rpi5-update.service" not in text

print("Maintenance systemd cutover transaction tests: PASS")
