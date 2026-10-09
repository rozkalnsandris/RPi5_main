#!/usr/bin/env python3
"""Fixed-target SIMPLE-DEPLOY executor upgrade; no implicit LIVE authority."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess

REPO = Path("/home/andris/RPi5_main")
GIT_PATH = "ops/lib/deploy_executor/simple_deploy_v1.py"
INSTALLED = Path("/usr/local/libexec/rozkalns-simple-deployer/simple_deploy_v1.py")
OPERATOR = Path("/usr/local/sbin/rozkalns-simple-deployer-code-upgrade")
STAGE = ".simple_deploy_v1.py.upgrade-staged"
TIMER = "rozkalns-simple-deployer.timer"
SERVICE = "rozkalns-simple-deployer.service"
SHA = re.compile(r"[a-f0-9]{40}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
LIMIT = 200000
ENV = {
    "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0",
}


class Blocked(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def reject(code: str) -> None:
    raise Blocked(code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_hex(value: str, *, commit: bool = False) -> None:
    if (SHA if commit else SHA256).fullmatch(value) is None:
        reject("SHA_FORMAT_INVALID")


def run(argv: list[str], limit: int = LIMIT) -> bytes:
    try:
        proc = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=15, shell=False, env=ENV,
        )
    except (OSError, subprocess.TimeoutExpired):
        reject("PREFLIGHT_EXEC_UNAVAILABLE")
    if proc.returncode != 0 or len(proc.stdout) > limit:
        reject("PREFLIGHT_EXEC_FAILED")
    return proc.stdout


def immutable_source(commit: str, source_sha256: str) -> bytes:
    require_hex(commit, commit=True)
    require_hex(source_sha256)
    if REPO.is_symlink() or not REPO.is_dir() or REPO.resolve() != REPO:
        reject("CHECKOUT_UNAVAILABLE")
    # Git's SHA-1 commit+blob identity, not a mutable checkout file. No fetch.
    content = run([
        "/usr/bin/git", "-C", str(REPO), "cat-file", "blob",
        f"{commit}:{GIT_PATH}",
    ])
    if not content or digest(content) != source_sha256:
        reject("SOURCE_HASH_DRIFT")
    return content


def read_checked(path: Path, *, uid: int, mode: int) -> tuple[bytes, os.stat_result]:
    fd = None
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
            reject("FILE_TYPE_DRIFT")
        if before.st_uid != uid or stat.S_IMODE(before.st_mode) != mode:
            reject("FILE_METADATA_DRIFT")
        if not 0 < before.st_size <= LIMIT:
            reject("FILE_SIZE_INVALID")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        after = os.fstat(fd)
        if (after.st_dev, after.st_ino, after.st_size) != (
            before.st_dev, before.st_ino, before.st_size
        ):
            reject("FILE_IDENTITY_DRIFT")
        content = bytearray()
        while len(content) <= LIMIT:
            part = os.read(fd, min(16384, LIMIT + 1 - len(content)))
            if not part:
                break
            content.extend(part)
        if len(content) != before.st_size:
            reject("FILE_IDENTITY_DRIFT")
        return bytes(content), before
    except OSError:
        reject("FILE_UNAVAILABLE")
    finally:
        if fd is not None:
            os.close(fd)


def parent_guard() -> os.stat_result:
    try:
        info = INSTALLED.parent.lstat()
    except OSError:
        reject("PARENT_UNAVAILABLE")
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o755):
        reject("PARENT_METADATA_DRIFT")
    return info


def installed_guard(old_sha256: str) -> os.stat_result:
    require_hex(old_sha256)
    parent_guard()
    content, info = read_checked(INSTALLED, uid=0, mode=0o444)
    if digest(content) != old_sha256:
        reject("INSTALLED_SHA_DRIFT")
    return info


def quiescence() -> None:
    """The timer must have been stopped AND disabled under separate LIVE authority."""
    for name in (TIMER, SERVICE):
        payload = run([
            "/usr/bin/systemctl", "show", "--no-pager",
            "--property=LoadState,ActiveState,SubState,UnitFileState", name,
        ], 2048)
        entries = [line.split(b"=", 1) for line in payload.splitlines()]
        if len(entries) != 4 or any(len(x) != 2 for x in entries):
            reject("UNIT_METADATA_UNAVAILABLE")
        values = dict(entries)
        if values.get(b"LoadState") != b"loaded":
            reject("UNIT_METADATA_UNAVAILABLE")
        if name == TIMER:
            if (values.get(b"ActiveState") != b"inactive" or
                    values.get(b"UnitFileState") not in (b"disabled", b"masked")):
                reject("TIMER_NOT_QUIESCED")
        elif values.get(b"ActiveState") not in (b"inactive", b"failed"):
            reject("SERVICE_NOT_QUIESCED")


def identical(a: os.stat_result, b: os.stat_result) -> bool:
    return all(getattr(a, field) == getattr(b, field) for field in (
        "st_dev", "st_ino", "st_size", "st_ctime_ns", "st_mtime_ns",
        "st_mode", "st_uid", "st_gid"
    ))


def operator_guard(operator_sha256: str) -> None:
    require_hex(operator_sha256)
    if os.geteuid() != 0 or Path(__file__).absolute() != OPERATOR:
        reject("TRUSTED_OPERATOR_REQUIRED")
    content, _ = read_checked(OPERATOR, uid=0, mode=0o500)
    if digest(content) != operator_sha256:
        reject("OPERATOR_HASH_DRIFT")


def atomic_upgrade(source: bytes, old_sha256: str, new_sha256: str) -> None:
    """Replace only INSTALLED. Staged files remain after any failure: no cleanup."""
    original = installed_guard(old_sha256)
    quiescence()
    dir_fd = None
    staged_fd = None
    try:
        dir_fd = os.open(
            INSTALLED.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        if not identical(parent_guard(), os.fstat(dir_fd)):
            reject("PARENT_IDENTITY_DRIFT")
        staged_fd = os.open(
            STAGE, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=dir_fd,
        )
        offset = 0
        while offset < len(source):
            written = os.write(staged_fd, source[offset:])
            if written <= 0:
                reject("STAGING_WRITE_FAILED")
            offset += written
        os.fchown(staged_fd, 0, 0)
        os.fchmod(staged_fd, 0o444)
        os.fsync(staged_fd)
        os.close(staged_fd)
        staged_fd = None
        if digest(source) != new_sha256:
            reject("SOURCE_HASH_DRIFT")
        if not identical(original, installed_guard(old_sha256)):
            reject("INSTALLED_IDENTITY_DRIFT")
        quiescence()  # final timer/service race guard immediately before swap
        os.replace(STAGE, INSTALLED.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
        post, _ = read_checked(INSTALLED, uid=0, mode=0o444)
        if digest(post) != new_sha256:
            reject("POST_REPLACE_VERIFICATION_FAILED")
        quiescence()
    except OSError:
        reject("ATOMIC_REPLACEMENT_FAILED")
    finally:
        if staged_fd is not None:
            os.close(staged_fd)
        if dir_fd is not None:
            os.close(dir_fd)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fixed-target SIMPLE-DEPLOY executor source upgrade")
    p.add_argument("--expected-source-commit", required=True)
    p.add_argument("--expected-source-sha256", required=True)
    p.add_argument("--expected-installed-sha256", required=True)
    p.add_argument("--expected-operator-sha256")
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    may_have_mutated = False
    try:
        require_hex(a.expected_source_commit, commit=True)
        require_hex(a.expected_source_sha256)
        require_hex(a.expected_installed_sha256)
        if a.apply:
            if a.expected_operator_sha256 is None:
                reject("TRUSTED_OPERATOR_REQUIRED")
            operator_guard(a.expected_operator_sha256)
        source = immutable_source(a.expected_source_commit, a.expected_source_sha256)
        installed_guard(a.expected_installed_sha256)
        if a.expected_installed_sha256 == a.expected_source_sha256:
            outcome = "ALREADY_CURRENT"
        else:
            quiescence()
            if not a.apply:
                outcome = "PREFLIGHT_READY"
            else:
                # Conservative fail-closed accounting, including staging errors.
                may_have_mutated = True
                atomic_upgrade(source, a.expected_installed_sha256, a.expected_source_sha256)
                outcome = "APPLIED"
        print(f"SIMPLE_DEPLOY_EXECUTOR_UPGRADE result={outcome} "
              f"mutation_started={'true' if may_have_mutated else 'false'}")
        return 0
    except Blocked as exc:
        print(f"SIMPLE_DEPLOY_EXECUTOR_UPGRADE result=BLOCKED error_code={exc.code} "
              f"mutation_started={'true' if may_have_mutated else 'false'}")
        return 1
    except Exception:
        print(f"SIMPLE_DEPLOY_EXECUTOR_UPGRADE result=BLOCKED error_code=UNEXPECTED "
              f"mutation_started={'true' if may_have_mutated else 'false'}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
