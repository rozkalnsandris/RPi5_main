#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
sys.dont_write_bytecode = True
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
INSTALLER_SOURCE = ROOT / "scripts/install-weather-operator-v9-host-capability.py"
CONTRACT = ROOT / "ops/recovery/weather_v9_capability_state_bootstrap.contract.json"

SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-operator-v9-capability")
PACKAGE_ROOT = SUPPORT_ROOT / "deploy_executor"
BROKER_PATH = Path("/usr/local/libexec/rozkalns-weather-operator-v9-privileged-broker")
CONFIG_ROOT = Path("/etc/rozkalns-weather-operator-v9-capability")
REGISTRATION_PATH = CONFIG_ROOT / "registration.json"
STATE_ROOT = Path("/var/lib/rozkalns-weather-operator-v9-capability")
STATE_DB_PATH = STATE_ROOT / "state.sqlite3"
SYSTEMD_ROOT = Path("/etc/systemd/system")
SOCKET_NAME = "rozkalns-weather-operator-v9-privileged-broker.socket"
SERVICE_NAME = "rozkalns-weather-operator-v9-privileged-broker@.service"
SOCKET_UNIT_PATH = SYSTEMD_ROOT / SOCKET_NAME
SERVICE_UNIT_PATH = SYSTEMD_ROOT / SERVICE_NAME
MODULE_PATH = PACKAGE_ROOT / "weather_operator_upgrade_v9_host_capability.py"

REGISTRATION_TEMP = CONFIG_ROOT / ".registration.json.state-bootstrap.tmp"
KNOWN_STAGING_PATHS = (
    BROKER_PATH.with_name(".rozkalns-weather-operator-v9-privileged-broker.refresh.tmp"),
    CONFIG_ROOT / ".registration.json.refresh.tmp",
    BROKER_PATH.with_name(".rozkalns-weather-operator-v9-privileged-broker.broker-refresh.tmp"),
    CONFIG_ROOT / ".registration.json.broker-refresh.tmp",
    MODULE_PATH.with_name(".weather_operator_upgrade_v9_host_capability.py.module-refresh.tmp"),
    CONFIG_ROOT / ".registration.json.module-refresh.tmp",
    REGISTRATION_TEMP,
    STATE_ROOT / "state.sqlite3-wal",
    STATE_ROOT / "state.sqlite3-shm",
)

REGISTRATION_SCHEMA = (
    "rozkalns.rpi5-main.weather-operator-upgrade-v9-host-capability-registration.v1"
)
REGISTRATION_FIELDS = frozenset(
    {
        "schema",
        "capability_source_sha",
        "manager_checkout",
        "manager_uid",
        "manager_gid",
        "artifact_count",
        "module_sha256",
        "broker_sha256",
        "socket_sha256",
        "service_sha256",
    }
)
ROOT_UID = 0
ROOT_GID = 0
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_REGISTRATION_BYTES = 64 * 1024


class RecoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecoveryPlan:
    source_sha: str
    manager_checkout: Path
    manager_uid: int
    manager_gid: int
    artifact_hashes: Mapping[str, str]
    state_root_present: bool


def fail(message: str) -> None:
    raise RecoveryError(message)


def _load_installer():
    spec = importlib.util.spec_from_file_location("weather_v9_host_capability_installer", INSTALLER_SOURCE)
    if spec is None or spec.loader is None:
        fail("canonical Weather v9 host-capability installer cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_state_store():
    sys.path.insert(0, str(ROOT / "ops/lib"))
    try:
        from deploy_executor.state import StateStore
    except Exception as exc:
        raise RecoveryError("canonical StateStore cannot be loaded") from exc
    return StateStore


def _lstat_optional(path: Path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RecoveryError(f"path metadata is unavailable: {path}") from exc


def _require_absent(path: Path) -> None:
    if _lstat_optional(path) is not None:
        fail(f"path must be absent for bounded recovery: {path}")


def _require_root_directory(path: Path, mode: int, *, allow_absent: bool = False) -> bool:
    meta = _lstat_optional(path)
    if meta is None:
        if allow_absent:
            return False
        fail(f"required directory is absent: {path}")
    if (
        not stat.S_ISDIR(meta.st_mode)
        or stat.S_ISLNK(meta.st_mode)
        or meta.st_uid != ROOT_UID
        or meta.st_gid != ROOT_GID
        or stat.S_IMODE(meta.st_mode) != mode
    ):
        fail(f"required directory metadata drifted: {path}")
    return True


def _safe_regular_bytes(path: Path, *, mode: int, max_bytes: int = MAX_ARTIFACT_BYTES) -> bytes:
    before = _lstat_optional(path)
    if before is None:
        fail(f"required artifact is absent: {path}")
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != ROOT_UID
        or before.st_gid != ROOT_GID
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_size < 1
        or before.st_size > max_bytes
    ):
        fail(f"required artifact metadata drifted: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RecoveryError(f"required artifact cannot be read: {path}") from exc
    after = _lstat_optional(path)
    if after is None or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        fail(f"required artifact changed while being read: {path}")
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_contract(installer: Any) -> None:
    try:
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryError("state-bootstrap contract is unavailable or malformed") from exc

    expected_targets = {
        "support_root": str(SUPPORT_ROOT),
        "broker": str(BROKER_PATH),
        "registration": str(REGISTRATION_PATH),
        "state_root": str(STATE_ROOT),
        "state_db": str(STATE_DB_PATH),
        "socket_unit": str(SOCKET_UNIT_PATH),
        "service_unit": str(SERVICE_UNIT_PATH),
        "module": str(MODULE_PATH),
    }
    if (
        value.get("schema")
        != "rozkalns.rpi5-main.weather-operator-v9-capability-state-bootstrap.v1"
        or value.get("issue") != 623
        or value.get("accepted_baseline")
        != {"registration": "ABSENT", "state_db": "ABSENT"}
        or value.get("fixed_targets") != expected_targets
        or value.get("artifact_count") != 15
        or value.get("registration_schema") != REGISTRATION_SCHEMA
        or value.get("registration_published_last") is not True
        or value.get("systemd_mutation") is not False
        or value.get("automatic_retry") is not False
        or value.get("automatic_cleanup") is not False
        or value.get("automatic_rollback") is not False
        or value.get("source_merge_authorizes_live") is not False
        or value.get("known_staging_paths") != [str(path) for path in KNOWN_STAGING_PATHS]
    ):
        fail("state-bootstrap contract drifted")

    if (
        getattr(installer, "REGISTRATION_SCHEMA", None) != REGISTRATION_SCHEMA
        or getattr(installer, "TARGET_ROOT", None) != SUPPORT_ROOT
        or getattr(installer, "PACKAGE_ROOT", None) != PACKAGE_ROOT
        or getattr(installer, "BROKER_TARGET", None) != BROKER_PATH
        or getattr(installer, "CONFIG_ROOT", None) != CONFIG_ROOT
        or getattr(installer, "REGISTRATION", None) != REGISTRATION_PATH
        or getattr(installer, "STATE_ROOT", None) != STATE_ROOT
        or getattr(installer, "STATE_DB", None) != STATE_DB_PATH
        or getattr(installer, "SYSTEMD_ROOT", None) != SYSTEMD_ROOT
        or getattr(installer, "SOCKET_NAME", None) != SOCKET_NAME
        or getattr(installer, "SERVICE_NAME", None) != SERVICE_NAME
        or len(getattr(installer, "ARTIFACTS", ())) != 15
    ):
        fail("canonical installer binding drifted")


def preflight_material(installer: Any | None = None) -> RecoveryPlan:
    installer = _load_installer() if installer is None else installer
    _validate_contract(installer)

    _require_absent(REGISTRATION_PATH)
    _require_absent(STATE_DB_PATH)
    for path in KNOWN_STAGING_PATHS:
        _require_absent(path)

    _require_root_directory(CONFIG_ROOT, 0o700)
    state_root_present = _require_root_directory(STATE_ROOT, 0o700, allow_absent=True)

    try:
        source_sha = str(installer.source_sha())
        manager = Path(installer.canonical_manager_checkout())
        manager_uid, manager_gid = installer.manager_identity(manager)
    except RecoveryError:
        raise
    except Exception as exc:
        raise RecoveryError("canonical source/manager provenance preflight failed") from exc

    if len(source_sha) != 40 or any(ch not in "0123456789abcdef" for ch in source_sha):
        fail("canonical source SHA is invalid")
    if not manager.is_absolute() or manager.name != "RPi5_main":
        fail("canonical manager checkout identity drifted")
    if type(manager_uid) is not int or type(manager_gid) is not int or manager_uid <= 0 or manager_gid <= 0:
        fail("canonical manager owner identity is invalid")

    artifact_hashes: dict[str, str] = {}
    targets: set[Path] = set()
    for source, target, mode in installer.ARTIFACTS:
        target = Path(target)
        if target in targets:
            fail("canonical installer contains duplicate artifact target")
        targets.add(target)
        try:
            expected = installer.installed_bytes(source, manager)
        except Exception as exc:
            raise RecoveryError(f"canonical expected artifact bytes unavailable: {source}") from exc
        if not isinstance(expected, bytes) or not expected:
            fail(f"canonical expected artifact is empty: {source}")
        observed = _safe_regular_bytes(target, mode=int(mode))
        if observed != expected:
            fail(f"installed artifact bytes drifted from reviewed source: {target}")
        artifact_hashes[str(target)] = _sha256(observed)

    expected_targets = {Path(target) for _source, target, _mode in installer.ARTIFACTS}
    required_identity_targets = {
        MODULE_PATH,
        BROKER_PATH,
        SOCKET_UNIT_PATH,
        SERVICE_UNIT_PATH,
    }
    if not required_identity_targets.issubset(expected_targets):
        fail("canonical installer identity targets drifted")

    return RecoveryPlan(
        source_sha=source_sha,
        manager_checkout=manager,
        manager_uid=manager_uid,
        manager_gid=manager_gid,
        artifact_hashes=artifact_hashes,
        state_root_present=state_root_present,
    )


def _registration(plan: RecoveryPlan) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": REGISTRATION_SCHEMA,
        "capability_source_sha": plan.source_sha,
        "manager_checkout": str(plan.manager_checkout),
        "manager_uid": plan.manager_uid,
        "manager_gid": plan.manager_gid,
        "artifact_count": 15,
        "module_sha256": plan.artifact_hashes[str(MODULE_PATH)],
        "broker_sha256": plan.artifact_hashes[str(BROKER_PATH)],
        "socket_sha256": plan.artifact_hashes[str(SOCKET_UNIT_PATH)],
        "service_sha256": plan.artifact_hashes[str(SERVICE_UNIT_PATH)],
    }
    if frozenset(value) != REGISTRATION_FIELDS:
        fail("registration fields drifted")
    return value


def _registration_bytes(plan: RecoveryPlan) -> bytes:
    return json.dumps(
        _registration(plan),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _write_exclusive(path: Path, data: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, mode)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                fail("state-bootstrap write made no progress")
            view = view[written:]
        os.fchmod(fd, mode)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_state_db(StateStore: Any) -> None:
    raw = _safe_regular_bytes(STATE_DB_PATH, mode=0o600, max_bytes=64 * 1024 * 1024)
    if not raw.startswith(b"SQLite format 3\x00"):
        fail("bootstrapped state database does not have canonical SQLite header")
    try:
        with StateStore(STATE_DB_PATH):
            pass
    except Exception as exc:
        raise RecoveryError("bootstrapped StateStore integrity verification failed") from exc


def preflight() -> dict[str, object]:
    plan = preflight_material()
    return {
        "schema": "rozkalns.rpi5-main.weather-operator-v9-capability-state-bootstrap-preflight.v1",
        "result": "PASS",
        "source_sha": plan.source_sha,
        "manager_checkout": str(plan.manager_checkout),
        "artifact_count": len(plan.artifact_hashes),
        "state_root_action": "PRESERVE" if plan.state_root_present else "CREATE_ROOT_0700",
        "host_mutation_started": False,
        "systemd_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "source_merge_authorizes_live": False,
    }


def apply() -> dict[str, object]:
    if os.geteuid() != 0:
        fail("--apply requires a separately owner-authorized root process")

    plan = preflight_material()
    StateStore = _load_state_store()
    registration_bytes = _registration_bytes(plan)
    mutation_started = False

    try:
        if not plan.state_root_present:
            STATE_ROOT.mkdir(mode=0o700, parents=False, exist_ok=False)
            os.chown(STATE_ROOT, ROOT_UID, ROOT_GID)
            os.chmod(STATE_ROOT, 0o700)
            mutation_started = True

        mutation_started = True
        with StateStore(STATE_DB_PATH, bootstrap=True):
            pass
        os.chown(STATE_DB_PATH, ROOT_UID, ROOT_GID)
        os.chmod(STATE_DB_PATH, 0o600)
        _fsync_directory(STATE_ROOT)
        _verify_state_db(StateStore)

        _write_exclusive(REGISTRATION_TEMP, registration_bytes, 0o600)
        if _safe_regular_bytes(
            REGISTRATION_TEMP, mode=0o600, max_bytes=MAX_REGISTRATION_BYTES
        ) != registration_bytes:
            fail("staged registration identity drifted")
        os.replace(REGISTRATION_TEMP, REGISTRATION_PATH)
        _fsync_directory(CONFIG_ROOT)
        if _safe_regular_bytes(
            REGISTRATION_PATH, mode=0o600, max_bytes=MAX_REGISTRATION_BYTES
        ) != registration_bytes:
            fail("published registration identity drifted")
    except Exception as exc:
        raise RecoveryError(
            "Weather v9 capability state bootstrap failed closed after mutation; "
            "no retry/cleanup/rollback is authorized"
        ) from exc

    return {
        "schema": "rozkalns.rpi5-main.weather-operator-v9-capability-state-bootstrap-receipt.v1",
        "result": "PASS",
        "source_sha": plan.source_sha,
        "artifact_count": len(plan.artifact_hashes),
        "host_mutation_started": mutation_started,
        "state_db_bootstrapped": True,
        "registration_published": True,
        "systemd_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recover only the Weather v9 both-missing registration/replay-state partial install"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = apply() if args.apply else preflight()
    except RecoveryError as exc:
        print(
            json.dumps(
                {
                    "schema": (
                        "rozkalns.rpi5-main.weather-operator-v9-capability-state-bootstrap-receipt.v1"
                        if args.apply
                        else "rozkalns.rpi5-main.weather-operator-v9-capability-state-bootstrap-preflight.v1"
                    ),
                    "result": "FAIL_CLOSED",
                    "reason": str(exc),
                    "automatic_retry": False,
                    "automatic_cleanup": False,
                    "automatic_rollback": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 78
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
