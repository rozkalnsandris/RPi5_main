#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "scripts/install-weather-v9-predecessor-bootstrap-capability.py"
CONTRACT_PATH = ROOT / "ops/deploy/weather-v9-predecessor-bootstrap-capability-repair.json"
TRUSTED_SOURCE_CHECKOUT_NAME = "RPi5_main-weather-v9-predecessor-bootstrap-capability-repair-source-trusted"
PREDECESSOR_SOURCE_SHA = "7beb7da3908b3f74ffc96cba6297402523096c2b"
PREDECESSOR_BROKER_SHA256 = "4e484763444027ded541429944ae5a1ebacd3beaf81b00198c7be07954fa2676"
TARGET_BROKER_SHA256 = "f7bcf225166fe1598139abbbaf26c713b81170ef49ccbd94b32d046957c4a892"
BROKER_RELATIVE = "ops/bin/rozkalns-weather-v9-predecessor-bootstrap-broker"
REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-capability-registration.v1"
ROOT_UID = 0
ROOT_GID = 0


class RepairError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise RepairError(message)


def load_installer():
    spec = importlib.util.spec_from_file_location("weather_v9_predecessor_installer_repair", INSTALLER_PATH)
    if spec is None or spec.loader is None:
        fail("bootstrap capability installer module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load_installer()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_bytes(relative: str) -> bytes:
    return installer._source_bytes(relative)


def _run_source_git(uid: int, gid: int, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    allowed_paths = set(installer.RELEASE_FILES) | {
        "ops/systemd/rozkalns-weather-v9-predecessor-bootstrap.socket",
        "ops/systemd/rozkalns-weather-v9-predecessor-bootstrap@.service",
    }
    allowed = args == ("symbolic-ref", "-q", "HEAD") or (
        len(args) == 2
        and args[0] == "show"
        and any(args[1] == f"{PREDECESSOR_SOURCE_SHA}:{path}" for path in allowed_paths)
    )
    if not allowed:
        fail("repair source Git argv escaped fixed allowlist")
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "env": {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        "shell": False,
        "close_fds": True,
        "check": check,
    }
    if os.geteuid() == ROOT_UID:
        kwargs.update(user=uid, group=gid, extra_groups=())
    try:
        return subprocess.run(["/usr/bin/git", "-C", str(ROOT), *args], **kwargs)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RepairError("repair source Git validation failed") from exc


def predecessor_source_bytes(uid: int, gid: int, relative: str) -> bytes:
    result = _run_source_git(uid, gid, "show", f"{PREDECESSOR_SOURCE_SHA}:{relative}")
    data = bytes(result.stdout)
    if not data:
        fail(f"predecessor source artifact is empty: {relative}")
    return data


def _root_dir(path: Path, mode: int) -> None:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise RepairError(f"required repair directory unavailable: {path}") from exc
    if (
        not stat.S_ISDIR(meta.st_mode)
        or path.is_symlink()
        or meta.st_uid != ROOT_UID
        or meta.st_gid != ROOT_GID
        or stat.S_IMODE(meta.st_mode) != mode
    ):
        fail(f"required repair directory metadata drifted: {path}")


def safe_file(path: Path, *, mode: int, max_bytes: int = 2 * 1024 * 1024) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise RepairError(f"required repair file unavailable: {path}") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or path.is_symlink()
        or before.st_nlink != 1
        or before.st_uid != ROOT_UID
        or before.st_gid != ROOT_GID
        or stat.S_IMODE(before.st_mode) != mode
        or not 0 < before.st_size <= max_bytes
    ):
        fail(f"required repair file metadata drifted: {path}")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            fail(f"required repair file changed before open: {path}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) != opened.st_size or len(data) > max_bytes:
            fail(f"required repair file changed while read: {path}")
        return data
    finally:
        os.close(fd)


def repair_source_identity() -> tuple[str, Path, int, int]:
    if os.geteuid() != ROOT_UID:
        fail("repair preflight requires an owner-authorized root process")
    if ROOT.name != TRUSTED_SOURCE_CHECKOUT_NAME:
        fail("repair must run from the dedicated trusted source checkout")
    source_sha, manager, uid, gid = installer.source_identity()
    symbolic = _run_source_git(uid, gid, "symbolic-ref", "-q", "HEAD", check=False)
    if symbolic.returncode == 0:
        fail("repair source checkout must be detached")
    if symbolic.returncode not in (1,):
        fail("repair source detached-state validation failed")
    if source_sha == PREDECESSOR_SOURCE_SHA:
        fail("repair target source must advance beyond predecessor source")
    return source_sha, manager, uid, gid


def require_contract() -> dict[str, object]:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepairError("repair contract cannot be loaded") from exc
    if contract.get("schema") != "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-capability-repair.v1":
        fail("repair contract schema drifted")
    if contract.get("issue") != 634:
        fail("repair contract issue binding drifted")
    repair = contract.get("repair")
    if type(repair) is not dict:
        fail("repair contract section drifted")
    if repair.get("fixed_targets") != {
        str(installer.REGISTRATION): "0600",
        str(installer.RELEASE_ROOT / BROKER_RELATIVE): "0755",
    }:
        fail("repair fixed targets drifted")
    if repair.get("mutation_budget") != [
        {"category": "filesystem.weather-v9-bootstrap-registration-atomic-replace", "max_operations": 1},
        {"category": "filesystem.weather-v9-bootstrap-broker-atomic-replace", "max_operations": 1},
    ]:
        fail("repair mutation budget drifted")
    if repair.get("systemd_mutation") is not False or repair.get("replay_mutation") is not False:
        fail("repair must not mutate systemd or replay state")
    return contract


def load_registration() -> dict[str, object]:
    raw = safe_file(installer.REGISTRATION, mode=0o600, max_bytes=65536)
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RepairError("installed bootstrap registration is malformed") from exc
    fields = {
        "schema",
        "source_sha",
        "source_checkout",
        "manager_checkout",
        "manager_uid",
        "manager_gid",
        "release_files",
        "socket_sha256",
        "service_sha256",
    }
    if type(value) is not dict or set(value) != fields:
        fail("installed bootstrap registration fields drifted")
    if value.get("schema") != REGISTRATION_SCHEMA:
        fail("installed bootstrap registration schema drifted")
    if value.get("source_sha") != PREDECESSOR_SOURCE_SHA:
        fail("installed bootstrap predecessor source drifted")
    releases = value.get("release_files")
    if type(releases) is not dict or set(releases) != set(installer.RELEASE_FILES):
        fail("installed bootstrap release manifest drifted")
    for digest in releases.values():
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            fail("installed bootstrap release digest is invalid")
    return value


def _temp_path(path: Path) -> Path:
    return path.parent / f".{path.name}.repair-634.tmp"


def preflight() -> dict[str, object]:
    source_sha, manager, uid, gid = repair_source_identity()
    require_contract()
    registration = load_registration()
    if registration.get("manager_checkout") != str(manager):
        fail("installed bootstrap manager binding drifted")
    if registration.get("manager_uid") != uid or registration.get("manager_gid") != gid:
        fail("installed bootstrap manager identity drifted")
    source_checkout = Path(str(registration.get("source_checkout")))
    if not source_checkout.is_absolute() or source_checkout.parent != manager.parent or source_checkout == manager:
        fail("installed bootstrap source checkout binding drifted")

    _root_dir(installer.CAPABILITY_ROOT, 0o755)
    _root_dir(installer.RELEASE_ROOT, 0o755)
    _root_dir(installer.CONFIG_ROOT, 0o700)
    _root_dir(installer.REPLAY_ROOT, 0o700)

    target_hashes: dict[str, str] = {}
    installed_hashes: dict[str, str] = {}
    for relative, mode in installer.RELEASE_FILES.items():
        target = source_bytes(relative)
        predecessor = predecessor_source_bytes(uid, gid, relative)
        installed = safe_file(installer.RELEASE_ROOT / relative, mode=mode)
        installed_digest = sha256(installed)
        if relative == BROKER_RELATIVE:
            if sha256(predecessor) != PREDECESSOR_BROKER_SHA256 or installed_digest != PREDECESSOR_BROKER_SHA256:
                fail("installed bootstrap predecessor broker drifted")
            if sha256(target) != TARGET_BROKER_SHA256 or target == predecessor:
                fail("repair target broker identity drifted")
        else:
            if target != predecessor or installed != target:
                fail(f"unchanged bootstrap release file drifted: {relative}")
        if registration["release_files"].get(relative) != installed_digest:
            fail(f"installed bootstrap registration digest drifted: {relative}")
        target_hashes[relative] = sha256(target)
        installed_hashes[relative] = installed_digest

    for relative, target_path, field in (
        ("ops/systemd/rozkalns-weather-v9-predecessor-bootstrap.socket", installer.SOCKET_TARGET, "socket_sha256"),
        ("ops/systemd/rozkalns-weather-v9-predecessor-bootstrap@.service", installer.SERVICE_TARGET, "service_sha256"),
    ):
        target = source_bytes(relative)
        predecessor = predecessor_source_bytes(uid, gid, relative)
        installed = safe_file(target_path, mode=0o644, max_bytes=65536)
        if target != predecessor or installed != target or registration.get(field) != sha256(installed):
            fail(f"bootstrap {field} baseline drifted")

    for target in (installer.REGISTRATION, installer.RELEASE_ROOT / BROKER_RELATIVE):
        if _temp_path(target).exists():
            fail(f"repair temp path already exists: {target.name}")

    return {
        "schema": "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-capability-repair-preflight.v1",
        "result": "PASS",
        "source_sha": source_sha,
        "manager_checkout": str(manager),
        "manager_uid": uid,
        "manager_gid": gid,
        "predecessor_source_sha": PREDECESSOR_SOURCE_SHA,
        "predecessor_broker_sha256": PREDECESSOR_BROKER_SHA256,
        "target_broker_sha256": TARGET_BROKER_SHA256,
        "target_release_hashes": target_hashes,
        "socket_sha256": str(registration["socket_sha256"]),
        "service_sha256": str(registration["service_sha256"]),
        "mutation_started": False,
        "registration_replaced": False,
        "broker_replaced": False,
        "systemd_mutated": False,
        "replay_mutated": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def atomic_replace(path: Path, data: bytes, mode: int) -> None:
    temp = _temp_path(path)
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                fail("repair write made no progress")
            view = view[written:]
        os.fsync(fd)
        os.fchmod(fd, mode)
        os.fchown(fd, ROOT_UID, ROOT_GID)
    finally:
        os.close(fd)
    os.replace(temp, path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def apply() -> dict[str, object]:
    if os.geteuid() != ROOT_UID:
        fail("--apply requires a separately owner-authorized root process")
    evidence = preflight()
    broker_data = source_bytes(BROKER_RELATIVE)
    target_hashes = dict(evidence["target_release_hashes"])
    registration = {
        "schema": REGISTRATION_SCHEMA,
        "source_sha": str(evidence["source_sha"]),
        "source_checkout": str(ROOT),
        "manager_checkout": str(evidence["manager_checkout"]),
        "manager_uid": int(evidence["manager_uid"]),
        "manager_gid": int(evidence["manager_gid"]),
        "release_files": target_hashes,
        "socket_sha256": str(evidence["socket_sha256"]),
        "service_sha256": str(evidence["service_sha256"]),
    }
    registration_data = (
        json.dumps(registration, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")

    mutation_started = True
    try:
        # Registration first keeps the known-broken predecessor broker installed until
        # the final executable replacement. Any concurrent request in the narrow
        # mismatch window fails closed on release-hash validation.
        atomic_replace(installer.REGISTRATION, registration_data, 0o600)
        atomic_replace(installer.RELEASE_ROOT / BROKER_RELATIVE, broker_data, 0o755)
        if safe_file(installer.REGISTRATION, mode=0o600, max_bytes=65536) != registration_data:
            fail("repaired bootstrap registration postcondition failed")
        if safe_file(installer.RELEASE_ROOT / BROKER_RELATIVE, mode=0o755) != broker_data:
            fail("repaired bootstrap broker postcondition failed")
        _root_dir(installer.REPLAY_ROOT, 0o700)
    except Exception as exc:
        raise RepairError(
            "Weather v9 bootstrap capability repair failed closed after mutation; "
            "no retry/cleanup/rollback is authorized"
        ) from exc

    return {
        "schema": "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-capability-repair-receipt.v1",
        "result": "PASS",
        "source_sha": str(evidence["source_sha"]),
        "predecessor_broker_sha256": PREDECESSOR_BROKER_SHA256,
        "target_broker_sha256": TARGET_BROKER_SHA256,
        "mutation_started": mutation_started,
        "registration_replaced": True,
        "broker_replaced": True,
        "systemd_mutated": False,
        "replay_mutated": False,
        "bootstrap_apply_started": False,
        "weather_runtime_mutated": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair the installed Weather v9 predecessor-bootstrap broker closure"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = apply() if args.apply else preflight()
    except RepairError as exc:
        print(
            json.dumps(
                {
                    "schema": "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-capability-repair-failure.v1",
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
