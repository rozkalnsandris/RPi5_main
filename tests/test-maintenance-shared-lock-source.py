#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "ops/bin/rpi5-update"
WRAPPER = ROOT / "ops/bin/rpi5-backup-serialized"
CORE = ROOT / "ops/bin/rpi5-backup"
CUTOVER = ROOT / "ops/bin/rpi5-maintenance-lock-cutover"
SYSTEMD_CUTOVER = ROOT / "ops/bin/rpi5-maintenance-systemd-cutover"

updater = UPDATER.read_text(encoding="utf-8")
wrapper = WRAPPER.read_text(encoding="utf-8")
core = CORE.read_text(encoding="utf-8")
cutover = CUTOVER.read_text(encoding="utf-8")
systemd_cutover = SYSTEMD_CUTOVER.read_text(encoding="utf-8")

canonical_root = "/usr/local/lib/rpi5-maintenance"
for name, text in {
    "updater": updater,
    "wrapper": wrapper,
    "lock-cutover": cutover,
    "systemd-cutover": systemd_cutover,
}.items():
    assert "/usr/local/libexec/rpi5-maintenance" not in text, name

# Actual updater order: duplicate updater lock first, then shared maintenance.
private_marker = 'LOCK_FILE="/run/lock/rpi5-update.lock"'
shared_marker = 'MAINTENANCE_LOCK_FILE="/run/lock/rpi5-maintenance-exclusive.lock"'
assert private_marker in updater and shared_marker in updater
private_acquire = updater.index('exec 9>"$LOCK_FILE"')
shared_acquire = updater.index("rpi5_acquire_exclusive_lock")
assert private_acquire < shared_acquire
assert "/run/lock/rpi5-backup.lock" not in updater
assert "rpi5_wait_for_lock_available" not in updater
assert "RPI5_LOCK_CONFLICT_RC" in updater
assert canonical_root in updater

# Actual backup order: wrapper acquires shared, invokes exact core, then the
# immutable core itself acquires its private duplicate-backup lock.
assert 'MAINTENANCE_LOCK_FILE="/run/lock/rpi5-maintenance-exclusive.lock"' in wrapper
wrapper_shared = wrapper.index("rpi5_acquire_exclusive_lock")
wrapper_core = wrapper.index('"$BACKUP_CORE" "$@"')
assert wrapper_shared < wrapper_core
assert 'BACKUP_CORE="${MAINTENANCE_LIB_DIR}/rpi5-backup-v10-core"' in wrapper
assert canonical_root in wrapper

assert 'LOCK_FILE="/run/lock/rpi5-backup.lock"' in core
core_private = core.index('exec 9>"$LOCK_FILE"')
assert core_private > 0
assert "rpi5-maintenance-exclusive.lock" not in core

# Migration quiescence is explicitly non-blocking and distinguishes contention
# from genuine flock errors instead of mapping every nonzero status to busy.
assert "rpi5_try_exclusive_lock" in cutover
assert "RPI5_LOCK_CONFLICT_RC" in cutover
assert "migration contention" in cutover
assert "lock acquisition error" in cutover
assert "--timeout" not in cutover
assert canonical_root in cutover

# The scheduler installer must ship/verify the shared helper with the updater.
assert systemd_cutover.count("rpi5-maintenance-locks.sh") == 3
assert 'MAINTENANCE_LIB_DIR="/usr/local/lib/rpi5-maintenance"' in systemd_cutover

print("Maintenance shared-lock source/order contract: PASS")
