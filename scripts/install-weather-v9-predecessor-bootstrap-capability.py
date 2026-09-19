#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
RELEASE_ROOT = Path("/usr/local/libexec/rozkalns-weather-v9-predecessor-bootstrap/current")
CAPABILITY_ROOT = RELEASE_ROOT.parent
CONFIG_ROOT = Path("/etc/rozkalns-weather-v9-predecessor-bootstrap")
REGISTRATION = CONFIG_ROOT / "registration.json"
REPLAY_ROOT = Path("/var/lib/rozkalns-weather-v9-predecessor-bootstrap")
SOCKET_TARGET = Path("/etc/systemd/system/rozkalns-weather-v9-predecessor-bootstrap.socket")
SERVICE_TARGET = Path("/etc/systemd/system/rozkalns-weather-v9-predecessor-bootstrap@.service")
SOCKET_SOURCE = ROOT / "ops/systemd/rozkalns-weather-v9-predecessor-bootstrap.socket"
SERVICE_SOURCE = ROOT / "ops/systemd/rozkalns-weather-v9-predecessor-bootstrap@.service"
REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-capability-registration.v1"
ROOT_UID = 0
ROOT_GID = 0
MAX_UID = (1 << 32) - 2

RELEASE_FILES = {
    "ops/bin/rozkalns-weather-v9-predecessor-bootstrap-broker": 0o755,
    "ops/lib/deploy_executor/__init__.py": 0o644,
    "ops/lib/deploy_executor/state.py": 0o644,
    "ops/lib/deploy_executor/weather_v9_predecessor_bootstrap_privileged.py": 0o644,
    "ops/recovery/weather_v9_capability_state_bootstrap.py": 0o644,
    "ops/recovery/weather_v9_capability_state_bootstrap.contract.json": 0o644,
    "ops/recovery/weather_v9_predecessor_state_bootstrap.py": 0o644,
    "ops/recovery/weather_v9_predecessor_state_bootstrap.contract.json": 0o644,
    "scripts/install-weather-operator-v9-host-capability.py": 0o755,
}

class InstallError(RuntimeError):
    pass

def fail(message: str) -> None:
    raise InstallError(message)

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _source_owner() -> tuple[int, int]:
    meta = ROOT.lstat()
    if not stat.S_ISDIR(meta.st_mode) or ROOT.is_symlink():
        fail("source checkout must be a real directory")
    if not (0 < meta.st_uid <= MAX_UID) or not (0 < meta.st_gid <= MAX_UID):
        fail("source checkout owner identity is invalid")
    return meta.st_uid, meta.st_gid

def _git(uid: int, gid: int, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    allowed = (
        args == ("rev-parse", "HEAD")
        or args == ("remote", "get-url", "origin")
        or args == ("status", "--porcelain", "--untracked-files=all")
        or args == ("rev-parse", "--path-format=absolute", "--git-common-dir")
    )
    if not allowed:
        fail("installer Git argv escaped fixed allowlist")
    try:
        return subprocess.run(
            ["/usr/bin/git", "-C", str(ROOT), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            user=uid,
            group=gid,
            extra_groups=(),
            shell=False,
            close_fds=True,
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        raise InstallError("installer source Git preflight failed") from exc

def source_identity() -> tuple[str, Path, int, int]:
    uid, gid = _source_owner()
    source_sha = _git(uid, gid, "rev-parse", "HEAD").stdout.strip()
    if len(source_sha) != 40 or any(c not in "0123456789abcdef" for c in source_sha):
        fail("source HEAD is not an exact lowercase SHA")
    if _git(uid, gid, "remote", "get-url", "origin").stdout.strip() != ORIGIN:
        fail("source origin drifted")
    if _git(uid, gid, "status", "--porcelain", "--untracked-files=all").stdout != "":
        fail("source checkout must be clean")
    common = Path(
        _git(uid, gid, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    ).resolve()
    if common.name != ".git":
        fail("source checkout is not linked to canonical manager Git directory")
    manager = common.parent
    manager_meta = manager.lstat()
    if (
        manager.name != "RPi5_main"
        or not stat.S_ISDIR(manager_meta.st_mode)
        or manager.is_symlink()
        or manager_meta.st_uid != uid
        or manager_meta.st_gid != gid
    ):
        fail("canonical manager filesystem identity drifted")
    if ROOT.parent != manager.parent or ROOT == manager:
        fail("source checkout is outside canonical manager parent")
    return source_sha, manager, uid, gid

def _source_bytes(relative: str) -> bytes:
    path = ROOT / relative
    try:
        meta = path.lstat()
        data = path.read_bytes()
    except OSError as exc:
        raise InstallError(f"required source file unavailable: {relative}") from exc
    if not stat.S_ISREG(meta.st_mode) or stat.S_ISLNK(meta.st_mode) or meta.st_nlink != 1 or not data:
        fail(f"required source file metadata drifted: {relative}")
    return data

def preflight() -> dict[str, object]:
    source_sha, manager, uid, gid = source_identity()
    for relative in RELEASE_FILES:
        _source_bytes(relative)
    socket_bytes = _source_bytes("ops/systemd/rozkalns-weather-v9-predecessor-bootstrap.socket")
    service_bytes = _source_bytes("ops/systemd/rozkalns-weather-v9-predecessor-bootstrap@.service")
    targets = (CAPABILITY_ROOT, CONFIG_ROOT, REPLAY_ROOT, SOCKET_TARGET, SERVICE_TARGET)
    existing = [str(path) for path in targets if path.exists() or path.is_symlink()]
    if existing:
        fail("bootstrap capability install baseline is not fully absent")
    return {
        "schema": "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-install-preflight.v1",
        "result": "PASS",
        "source_sha": source_sha,
        "manager_checkout": str(manager),
        "manager_uid": uid,
        "manager_gid": gid,
        "release_file_count": len(RELEASE_FILES),
        "socket_sha256": sha256(socket_bytes),
        "service_sha256": sha256(service_bytes),
        "systemd_activation": False,
        "mutation_started": False,
        "source_merge_authorizes_live": False,
    }

def _mkdir_exact(path: Path, mode: int) -> None:
    path.mkdir(mode=mode, parents=False, exist_ok=False)
    os.chown(path, ROOT_UID, ROOT_GID)
    os.chmod(path, mode)

def _write_exclusive(path: Path, data: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(path, ROOT_UID, ROOT_GID)
        os.chmod(path, mode)
    except Exception:
        raise

def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def apply() -> dict[str, object]:
    if os.geteuid() != 0:
        fail("--apply requires a separately owner-authorized root process")
    plan = preflight()
    source_sha = str(plan["source_sha"])
    manager = Path(str(plan["manager_checkout"]))
    uid = int(plan["manager_uid"])
    gid = int(plan["manager_gid"])
    release_hashes: dict[str, str] = {}
    mutation_started = False
    try:
        _mkdir_exact(CAPABILITY_ROOT, 0o755)
        mutation_started = True
        _mkdir_exact(RELEASE_ROOT, 0o755)
        for relative, mode in RELEASE_FILES.items():
            destination = RELEASE_ROOT / relative
            parents = list(destination.parents)
            stop = RELEASE_ROOT
            chain = []
            for parent in parents:
                if parent == stop:
                    break
                chain.append(parent)
            for parent in reversed(chain):
                if not parent.exists():
                    _mkdir_exact(parent, 0o755)
            data = _source_bytes(relative)
            _write_exclusive(destination, data, mode)
            release_hashes[relative] = sha256(data)

        _mkdir_exact(CONFIG_ROOT, 0o700)
        _mkdir_exact(REPLAY_ROOT, 0o700)

        socket_bytes = _source_bytes("ops/systemd/rozkalns-weather-v9-predecessor-bootstrap.socket")
        service_bytes = _source_bytes("ops/systemd/rozkalns-weather-v9-predecessor-bootstrap@.service")
        _write_exclusive(SOCKET_TARGET, socket_bytes, 0o644)
        _write_exclusive(SERVICE_TARGET, service_bytes, 0o644)

        registration = {
            "schema": REGISTRATION_SCHEMA,
            "source_sha": source_sha,
            "source_checkout": str(ROOT),
            "manager_checkout": str(manager),
            "manager_uid": uid,
            "manager_gid": gid,
            "release_files": release_hashes,
            "socket_sha256": sha256(socket_bytes),
            "service_sha256": sha256(service_bytes),
        }
        raw = (json.dumps(registration, sort_keys=True, separators=(",", ":")) + "\n").encode()
        _write_exclusive(REGISTRATION, raw, 0o600)
        _fsync_dir(CONFIG_ROOT)
        _fsync_dir(REPLAY_ROOT)
        _fsync_dir(RELEASE_ROOT)
    except Exception as exc:
        raise InstallError(
            "bootstrap capability installation failed closed after mutation; "
            "no retry/cleanup/rollback is authorized"
        ) from exc
    return {
        "schema": "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-install-receipt.v1",
        "result": "PASS",
        "source_sha": source_sha,
        "mutation_started": mutation_started,
        "release_file_count": len(release_hashes),
        "registration_published": True,
        "systemd_units_installed": True,
        "systemd_activation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = apply() if args.apply else preflight()
    except InstallError as exc:
        print(
            json.dumps(
                {
                    "schema": "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-install-failure.v1",
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
