#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "ops/bin/rpi5-maintenance-lock-cutover"
BACKUP = ROOT / "ops/bin/rpi5-backup"
WRAPPER = ROOT / "ops/bin/rpi5-backup-serialized"
LOCK_LIB = ROOT / "ops/lib/rpi5-maintenance-locks.sh"

text = OPERATOR.read_text(encoding="utf-8")
wrapper = WRAPPER.read_text(encoding="utf-8")
lock_lib = LOCK_LIB.read_text(encoding="utf-8")

assert OPERATOR.stat().st_mode & 0o100, "lock cutover operator must be owner-executable after checkout"

backup_sha = hashlib.sha256(BACKUP.read_bytes()).hexdigest()
assert backup_sha == "5ca85ae53bdf4fa3b99e21e1a30ddaa077d9e1791505b1e8389ee8587d011735"
assert "# RPi5 šifrētais backup runneris V12." in BACKUP.read_text(encoding="utf-8")

assert "set -Eeuo pipefail" in text
assert "v25-shared-maintenance-lock-public-safe" in text
assert '/usr/local/lib/rpi5-maintenance' in text
assert '/usr/local/libexec/rpi5-maintenance' not in text
assert 'BACKUP_OWNERSHIP_SNAPSHOT="V10"' in text
assert 'BACKUP_RUNTIME_VERSION=12' in text
assert backup_sha in text

# Quiescent migration must use the nonblocking shared helper with reserved
# contention code; no bounded wait is allowed while a subset of locks is held.
assert "rpi5_try_exclusive_lock" in text
assert "RPI5_LOCK_CONFLICT_RC" in text
assert "migration contention" in text
assert "lock acquisition error" in text
assert "--timeout" not in text
assert "RPI5_LOCK_CONFLICT_RC=200" in lock_lib

install_start = text.index("install_wrapper() {")
verify_start = text.index("\nverify_wrapper() {", install_start)
install = text[install_start:verify_start]
assert install.index("validate_installed_updater") < install.index("validate_v10_live_backup")
assert install.index("validate_v10_live_backup") < install.index("acquire_quiescent_window")
assert install.index("acquire_quiescent_window") < install.index('install -o root -g root -m 0750 "$LIVE_BACKUP" "$SAVED_BACKUP"')
assert install.index('install -o root -g root -m 0750 "$REPO_BACKUP" "$BACKUP_CORE"') < install.index('install -o root -g root -m 0644 "$REPO_LOCK_LIB" "$LOCK_LIB"')
assert install.index('install -o root -g root -m 0644 "$REPO_LOCK_LIB" "$LOCK_LIB"') < install.index('mv -f -- "$wrapper_tmp" "$LIVE_BACKUP"')
assert "restoring ownership snapshot" in install
assert ': >"$ACTIVE_MARKER"' in install

rollback_start = text.index("rollback_wrapper() {")
case_start = text.index("\ncase \"$MODE\" in", rollback_start)
rollback = text[rollback_start:case_start]
assert rollback.index("acquire_quiescent_window") < rollback.index('mv -f -- "$rollback_tmp" "$LIVE_BACKUP"')
assert rollback.index('mv -f -- "$rollback_tmp" "$LIVE_BACKUP"') < rollback.index("validate_v10_live_backup")
assert 'rm -f -- "$ACTIVE_MARKER"' in rollback

# Canonical wrapper holds shared before invoking exact immutable core.
assert 'MAINTENANCE_LIB_DIR="/usr/local/lib/rpi5-maintenance"' in wrapper
assert 'BACKUP_CORE="${MAINTENANCE_LIB_DIR}/rpi5-backup-v10-core"' in wrapper
assert 'MAINTENANCE_LOCK_FILE="/run/lock/rpi5-maintenance-exclusive.lock"' in wrapper
assert wrapper.index("rpi5_acquire_exclusive_lock") < wrapper.index('"$BACKUP_CORE" "$@"')
assert "RPI5_LOCK_CONFLICT_RC" in wrapper

# Migration is source/install only; never run backup/update merely to validate.
assert "systemctl start rpi5-update.service" not in text
assert "systemctl restart rpi5-update.service" not in text
assert not re.search(r'(?m)^\s*"\$LIVE_BACKUP"(?:\s|$)', text)
assert '"$LIVE_BACKUP" "$@"' not in text

print("Maintenance shared-lock cutover transaction tests: PASS")
