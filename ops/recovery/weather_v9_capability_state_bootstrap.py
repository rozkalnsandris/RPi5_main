#!/usr/bin/env python3
"""Fail-closed recovery for a Weather v9 partial capability installation.

This script is intentionally bounded to the single state documented in issue #623:
all reviewed capability artifacts are already installed and exact, while both
canonical durable state objects (registration and replay DB) are absent.

It does not replace artifacts, invoke systemd, mutate manager/trusted source,
or repair mixed/already-complete state.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

REGISTRATION_PATH = Path("/etc/rozkalns-weather-operator-v9-capability/registration.json")
STATE_DB_PATH = Path("/var/lib/rozkalns-weather-operator-v9-capability/state.sqlite3")
REGISTRATION_STAGING_PATH = REGISTRATION_PATH.with_name(".registration.json.tmp")
STATE_STAGING_PATH = STATE_DB_PATH.with_name(".state.sqlite3.tmp")

SUPPORT_MODULE_PATH = Path("/usr/local/libexec/rozkalns-weather-public-runtime-operator/weather_operator_upgrade_v9.py")
BROKER_PATH = Path("/usr/local/libexec/rozkalns-weather-public-runtime-operator/weather-operator-v9-capability-broker")
SOCKET_UNIT_PATH = Path("/etc/systemd/system/rozkalns-weather-operator-v9-capability.socket")
SERVICE_UNIT_PATH = Path("/etc/systemd/system/rozkalns-weather-operator-v9-capability.service")

FIXED_ARTIFACTS = {
    SUPPORT_MODULE_PATH: 0o644,
    BROKER_PATH: 0o755,
    SOCKET_UNIT_PATH: 0o644,
    SERVICE_UNIT_PATH: 0o644,
}


def _die(message: str) -> "NoReturn":
    raise SystemExit(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_root_regular(path: Path, expected_mode: int) -> None:
    try:
        st = path.lstat()
    except FileNotFoundError:
        _die(f"required artifact absent: {path}")
    if not stat.S_ISREG(st.st_mode):
        _die(f"required artifact is not a regular file: {path}")
    if st.st_nlink != 1:
        _die(f"required artifact link count is not 1: {path}")
    if st.st_uid != 0 or st.st_gid != 0:
        _die(f"required artifact is not root-owned: {path}")
    if stat.S_IMODE(st.st_mode) != expected_mode:
        _die(f"required artifact has unexpected mode: {path}")


def _require_absent(path: Path) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    _die(f"path must be absent for bounded recovery: {path}")


def _load_support_module():
    spec = importlib.util.spec_from_file_location("weather_operator_upgrade_v9_recovery", SUPPORT_MODULE_PATH)
    if spec is None or spec.loader is None:
        _die("unable to load installed Weather v9 support module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifact_hashes() -> dict[str, str]:
    return {str(path): _sha256(path) for path in FIXED_ARTIFACTS}


def _write_registration(payload: dict[str, object]) -> None:
    REGISTRATION_PATH.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(REGISTRATION_STAGING_PATH, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(REGISTRATION_STAGING_PATH, 0, 0)
        os.chmod(REGISTRATION_STAGING_PATH, 0o600)
        os.replace(REGISTRATION_STAGING_PATH, REGISTRATION_PATH)
    except BaseException:
        raise


def main() -> int:
    if os.geteuid() != 0:
        _die("Weather v9 capability state bootstrap must run as root")

    # The operation is valid only for the exact both-missing partial state.
    registration_exists = REGISTRATION_PATH.exists() or REGISTRATION_PATH.is_symlink()
    state_exists = STATE_DB_PATH.exists() or STATE_DB_PATH.is_symlink()
    if registration_exists or state_exists:
        _die("bounded recovery requires both registration and state DB to be absent")

    _require_absent(REGISTRATION_STAGING_PATH)
    _require_absent(STATE_STAGING_PATH)

    for path, mode in FIXED_ARTIFACTS.items():
        _validate_root_regular(path, mode)

    support = _load_support_module()
    state_store_type = getattr(support, "StateStore", None)
    if state_store_type is None:
        _die("installed support module does not expose StateStore")

    STATE_DB_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Canonical schema bootstrap only; never hand-write SQLite schema.
    state_store_type(STATE_DB_PATH, bootstrap=True)

    if not STATE_DB_PATH.exists() or STATE_DB_PATH.is_symlink():
        _die("StateStore bootstrap did not materialize canonical state DB")
    db_stat = STATE_DB_PATH.lstat()
    if not stat.S_ISREG(db_stat.st_mode) or db_stat.st_uid != 0 or db_stat.st_gid != 0:
        _die("bootstrapped state DB has unexpected identity")

    hashes = _artifact_hashes()
    registration = {
        "schema_version": 1,
        "capability": "weather_operator_v9",
        "state_db": str(STATE_DB_PATH),
        "artifacts": hashes,
    }

    # Registration is the final publication step. If anything failed above,
    # the broker cannot observe a registration claiming a usable capability.
    _write_registration(registration)
    return 0


if __name__ == "__main__":
    sys.exit(main())
