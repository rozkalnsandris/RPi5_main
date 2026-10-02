#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import grp
import json
import os
from pathlib import Path
import pwd
import stat
import sys
from typing import Iterable


SOURCE_ENV_RELATIVE = Path("docker/cv/bot/.env")
SOURCE_DATA_RELATIVE = Path("docker/cv/bot/data")
DESTINATION_PARENT = Path("/etc/rozkalns-simple-deployer/private")
DESTINATION_ENV = DESTINATION_PARENT / "rozkalns-cv.env"
PENDING_ENV = DESTINATION_PARENT / ".rozkalns-cv.env.pending"
DEPLOYER_ROOT = Path("/etc/rozkalns-simple-deployer")
RUNTIME_GROUP = "rozkalns-simple-deployer"
PARENT_MODE = 0o750
DESTINATION_MODE = 0o640
SOURCE_MAX_PERMISSIONS = 0o600
COPY_CHUNK_BYTES = 64 * 1024


class BoundaryError(RuntimeError):
    def __init__(self, code: str, *, mutation_started: bool = False):
        super().__init__(code)
        self.code = code
        self.mutation_started = mutation_started


@dataclass(frozen=True)
class RuntimeInputs:
    private_env: Path
    persistent_data: Path


def _fail(code: str, *, mutation_started: bool = False) -> None:
    raise BoundaryError(code, mutation_started=mutation_started)


def _lstat(path: Path):
    try:
        return os.lstat(path)
    except OSError:
        return None


def _real_regular(path: Path):
    info = _lstat(path)
    return info if info is not None and stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) else None


def _real_directory(path: Path):
    info = _lstat(path)
    return info if info is not None and stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) else None


def discover_runtime_inputs(entries: Iterable[pwd.struct_passwd] | None = None) -> RuntimeInputs:
    candidates: list[RuntimeInputs] = []
    for entry in tuple(entries) if entries is not None else pwd.getpwall():
        home_text = getattr(entry, "pw_dir", "")
        if not isinstance(home_text, str) or not home_text.startswith("/"):
            continue
        home = Path(home_text)
        private_env = home / SOURCE_ENV_RELATIVE
        persistent_data = home / SOURCE_DATA_RELATIVE
        env_info = _real_regular(private_env)
        data_info = _real_directory(persistent_data)
        if env_info is None or data_info is None:
            continue
        if stat.S_IMODE(env_info.st_mode) & ~SOURCE_MAX_PERMISSIONS:
            _fail("SOURCE_ENV_PERMISSIONS_TOO_BROAD")
        candidates.append(RuntimeInputs(private_env=private_env, persistent_data=persistent_data))
    if len(candidates) != 1:
        _fail("SOURCE_RUNTIME_INPUTS_NOT_UNIQUE")
    return candidates[0]


def _runtime_group_gid() -> int:
    try:
        return grp.getgrnam(RUNTIME_GROUP).gr_gid
    except KeyError:
        _fail("RUNTIME_GROUP_MISSING")
    raise AssertionError("unreachable")


def _require_root_owned_directory(path: Path, mode: int, gid: int) -> None:
    info = _real_directory(path)
    if info is None:
        _fail("DESTINATION_PARENT_INVALID")
    if info.st_uid != 0 or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
        _fail("DESTINATION_PARENT_METADATA_DRIFT")


def _preflight_destination(gid: int) -> bool:
    root_info = _real_directory(DEPLOYER_ROOT)
    if root_info is None or root_info.st_uid != 0:
        _fail("DEPLOYER_ROOT_INVALID")
    parent_info = _lstat(DESTINATION_PARENT)
    parent_exists = parent_info is not None
    if parent_exists:
        _require_root_owned_directory(DESTINATION_PARENT, PARENT_MODE, gid)
    if _lstat(DESTINATION_ENV) is not None:
        _fail("DESTINATION_ENV_ALREADY_EXISTS")
    if _lstat(PENDING_ENV) is not None:
        _fail("PENDING_ENV_ALREADY_EXISTS")
    return parent_exists


def preflight() -> RuntimeInputs:
    if os.geteuid() != 0:
        _fail("ROOT_REQUIRED")
    runtime = discover_runtime_inputs()
    gid = _runtime_group_gid()
    _preflight_destination(gid)
    return runtime


def _write_private_copy(source: Path, gid: int) -> None:
    flags_in = os.O_RDONLY
    flags_out = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags_in |= os.O_NOFOLLOW
        flags_out |= os.O_NOFOLLOW

    try:
        source_fd = os.open(source, flags_in)
    except OSError:
        _fail("SOURCE_ENV_OPEN_FAILED")
    try:
        try:
            pending_fd = os.open(PENDING_ENV, flags_out, 0o600)
        except OSError:
            _fail("PENDING_ENV_CREATE_FAILED", mutation_started=True)
        try:
            while True:
                chunk = os.read(source_fd, COPY_CHUNK_BYTES)
                if not chunk:
                    break
                view = memoryview(chunk)
                offset = 0
                while offset < len(view):
                    written = os.write(pending_fd, view[offset:])
                    if written <= 0:
                        _fail("PENDING_ENV_SHORT_WRITE", mutation_started=True)
                    offset += written
            os.fsync(pending_fd)
            os.fchown(pending_fd, 0, gid)
            os.fchmod(pending_fd, DESTINATION_MODE)
            pending_info = os.fstat(pending_fd)
            if pending_info.st_uid != 0 or pending_info.st_gid != gid:
                _fail("PENDING_ENV_OWNER_DRIFT", mutation_started=True)
            if stat.S_IMODE(pending_info.st_mode) != DESTINATION_MODE:
                _fail("PENDING_ENV_MODE_DRIFT", mutation_started=True)
        except OSError:
            _fail("PENDING_ENV_WRITE_FAILED", mutation_started=True)
        finally:
            os.close(pending_fd)
    finally:
        os.close(source_fd)


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        _fail("DESTINATION_PARENT_FSYNC_OPEN_FAILED", mutation_started=True)
    try:
        os.fsync(fd)
    except OSError:
        _fail("DESTINATION_PARENT_FSYNC_FAILED", mutation_started=True)
    finally:
        os.close(fd)


def apply() -> None:
    runtime = preflight()
    gid = _runtime_group_gid()
    parent_existed = _lstat(DESTINATION_PARENT) is not None

    if not parent_existed:
        try:
            os.mkdir(DESTINATION_PARENT, PARENT_MODE)
            os.chown(DESTINATION_PARENT, 0, gid)
            os.chmod(DESTINATION_PARENT, PARENT_MODE)
        except OSError:
            _fail("DESTINATION_PARENT_CREATE_FAILED", mutation_started=True)
        _require_root_owned_directory(DESTINATION_PARENT, PARENT_MODE, gid)

    source_before = os.lstat(runtime.private_env)
    _write_private_copy(runtime.private_env, gid)

    try:
        os.link(PENDING_ENV, DESTINATION_ENV, follow_symlinks=False)
    except OSError:
        _fail("DESTINATION_ENV_LINK_FAILED", mutation_started=True)
    _fsync_directory(DESTINATION_PARENT)

    try:
        os.unlink(PENDING_ENV)
    except OSError:
        _fail("PENDING_ENV_FINALIZE_FAILED", mutation_started=True)
    _fsync_directory(DESTINATION_PARENT)

    dest_info = _real_regular(DESTINATION_ENV)
    if dest_info is None:
        _fail("DESTINATION_ENV_VERIFY_FAILED", mutation_started=True)
    if dest_info.st_uid != 0 or dest_info.st_gid != gid or stat.S_IMODE(dest_info.st_mode) != DESTINATION_MODE:
        _fail("DESTINATION_ENV_METADATA_DRIFT", mutation_started=True)

    source_after = os.lstat(runtime.private_env)
    before_identity = (
        source_before.st_dev,
        source_before.st_ino,
        source_before.st_size,
        source_before.st_mtime_ns,
        source_before.st_mode,
        source_before.st_uid,
        source_before.st_gid,
    )
    after_identity = (
        source_after.st_dev,
        source_after.st_ino,
        source_after.st_size,
        source_after.st_mtime_ns,
        source_after.st_mode,
        source_after.st_uid,
        source_after.st_gid,
    )
    if before_identity != after_identity:
        _fail("SOURCE_ENV_CHANGED_DURING_COPY", mutation_started=True)


def _result(result: str, *, mutation_started: bool, error_code: str | None = None) -> str:
    value = {
        "schema": "rozkalns.rpi5-main.rozkalns-cv-private-env-boundary.v1",
        "result": result,
        "mutation_started": mutation_started,
        "secret_content_emitted": False,
        "source_modified": False,
        "automatic_cleanup": False,
        "automatic_retry": False,
        "automatic_rollback": False,
    }
    if error_code is not None:
        value["error_code"] = error_code
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize the fixed CV private env boundary")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.preflight:
            preflight()
            print(_result("PREFLIGHT_READY", mutation_started=False))
        else:
            apply()
            print(_result("MATERIALIZED", mutation_started=True))
    except BoundaryError as exc:
        print(
            _result(
                "STOP_ERROR" if exc.mutation_started else "PRE_MUTATION_FAILURE",
                mutation_started=exc.mutation_started,
                error_code=exc.code,
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
