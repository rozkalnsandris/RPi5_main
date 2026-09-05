#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Sequence

GIT = Path("/usr/bin/git")
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/install-deploy-executor-p9-hermes-source-auth-upgrade.py"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
TEMP_NAME = ".p9_source_auth.py.hermes-source-auth-upgrade.tmp"
RECEIPT_SCHEMA = "rozkalns.p9-source-auth-hermes-runtime-upgrade-receipt.v1"


class UpgradeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetSpec:
    source_path: str
    target_path: Path
    old_blob_sha: str
    new_blob_sha: str
    uid: int
    gid: int
    mode: int


TARGET = TargetSpec(
    source_path="ops/lib/deploy_executor/p9_source_auth.py",
    target_path=Path("/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py"),
    old_blob_sha="4cb441873df8245387f06ee55d637a9f7b11cdc8",
    new_blob_sha="130fc36a22bb4ace500b022c3defcccbf0893012",
    uid=0,
    gid=0,
    mode=0o644,
)


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _run(argv: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return _run(
        (
            str(GIT),
            "-c",
            f"safe.directory={ROOT}",
            "-C",
            str(ROOT),
            *args,
        )
    )


def _git_stdout(*args: str) -> bytes:
    result = _git(*args)
    if result.returncode != 0:
        raise UpgradeError("reviewed Git source validation failed")
    return result.stdout


def _require_exact_source(expected_sha: str) -> str:
    if FULL_SHA.fullmatch(expected_sha) is None:
        raise UpgradeError("expected SHA must be lowercase 40-character hex")
    head = _git_stdout("rev-parse", "HEAD").decode("ascii", "strict").strip()
    if head != expected_sha:
        raise UpgradeError("source SHA mismatch")
    clean = _git(
        "diff",
        "--quiet",
        "--no-ext-diff",
        expected_sha,
        "--",
        SCRIPT_RELATIVE,
        TARGET.source_path,
    )
    if clean.returncode != 0:
        raise UpgradeError("reviewed upgrade source differs from exact expected SHA")
    return expected_sha


def _reviewed_bytes(expected_sha: str) -> bytes:
    data = _git_stdout("show", f"{expected_sha}:{TARGET.source_path}")
    if _git_blob_sha(data) != TARGET.new_blob_sha:
        raise UpgradeError("reviewed new source blob differs from frozen upgrade target")
    return data


def _metadata(st: os.stat_result) -> tuple[int, int, int]:
    return st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)


def _require_parent_chain_safe(path: Path) -> None:
    for parent in reversed(path.parents):
        st = os.lstat(parent)
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
            raise UpgradeError(f"target parent is not a real directory: {parent}")
        if st.st_uid != 0 or st.st_gid != 0 or stat.S_IMODE(st.st_mode) & 0o022:
            raise UpgradeError(f"target parent ownership/mode is unsafe: {parent}")


def _open_parent_fd() -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(TARGET.target_path.parent, flags)
    except OSError as exc:
        raise UpgradeError("unable to open fixed target parent directory") from exc
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode):
        os.close(fd)
        raise UpgradeError("opened target parent is not a directory")
    if st.st_uid != 0 or st.st_gid != 0 or stat.S_IMODE(st.st_mode) & 0o022:
        os.close(fd)
        raise UpgradeError("opened target parent ownership/mode is unsafe")
    return fd


def _open_target_fd(parent_fd: int) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(TARGET.target_path.name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise UpgradeError("unable to open installed shared P9 source-auth target") from exc


def _read_fd_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _write_fd_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        count = os.write(fd, view[offset:])
        if count <= 0:
            raise UpgradeError("short write while preparing reviewed P9 source-auth replacement")
        offset += count


def _require_target_old(parent_fd: int, fd: int) -> os.stat_result:
    opened = os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
        raise UpgradeError("installed shared P9 source-auth target is not a single-link regular file")
    if _metadata(opened) != (TARGET.uid, TARGET.gid, TARGET.mode):
        raise UpgradeError("installed shared P9 source-auth ownership/mode mismatch")
    if _git_blob_sha(_read_fd_all(fd)) != TARGET.old_blob_sha:
        raise UpgradeError("installed shared P9 source-auth differs from reviewed old source")
    path_now = os.stat(TARGET.target_path.name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(path_now.st_mode) or stat.S_ISLNK(path_now.st_mode):
        raise UpgradeError("installed shared P9 source-auth path is no longer a regular file")
    if (path_now.st_dev, path_now.st_ino) != (opened.st_dev, opened.st_ino):
        raise UpgradeError("installed shared P9 source-auth path changed during validation")
    return opened


def _require_temp_absent(parent_fd: int) -> None:
    try:
        os.stat(TEMP_NAME, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise UpgradeError("fixed upgrade temporary target already exists")


def _preflight(expected_sha: str) -> bytes:
    _require_exact_source(expected_sha)
    if os.geteuid() != 0:
        raise UpgradeError("P9 Hermes source-auth runtime upgrade requires root")
    reviewed = _reviewed_bytes(expected_sha)
    _require_parent_chain_safe(TARGET.target_path)
    parent_fd = _open_parent_fd()
    try:
        target_fd = _open_target_fd(parent_fd)
        try:
            _require_target_old(parent_fd, target_fd)
        finally:
            os.close(target_fd)
        _require_temp_absent(parent_fd)
    finally:
        os.close(parent_fd)
    return reviewed


def _replace_exact_target(reviewed: bytes, state: dict[str, bool]) -> None:
    parent_fd = _open_parent_fd()
    target_fd = -1
    temp_fd = -1
    try:
        target_fd = _open_target_fd(parent_fd)
        opened = _require_target_old(parent_fd, target_fd)
        _require_temp_absent(parent_fd)

        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        state["mutation_started"] = True
        try:
            temp_fd = os.open(TEMP_NAME, flags, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            raise UpgradeError("unable to create fixed reviewed replacement target") from exc

        temp_st = os.fstat(temp_fd)
        if not stat.S_ISREG(temp_st.st_mode) or temp_st.st_nlink != 1:
            raise UpgradeError("created replacement target is not a single-link regular file")
        _write_fd_all(temp_fd, reviewed)
        os.fchown(temp_fd, TARGET.uid, TARGET.gid)
        os.fchmod(temp_fd, TARGET.mode)
        os.fsync(temp_fd)
        if _git_blob_sha(_read_fd_all(temp_fd)) != TARGET.new_blob_sha:
            raise UpgradeError("prepared replacement content verification failed")
        if _metadata(os.fstat(temp_fd)) != (TARGET.uid, TARGET.gid, TARGET.mode):
            raise UpgradeError("prepared replacement ownership/mode verification failed")

        # Revalidate the old inode and bytes after preparation and immediately before replace.
        current = _require_target_old(parent_fd, target_fd)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise UpgradeError("installed shared P9 source-auth inode changed before replacement")

        os.replace(
            TEMP_NAME,
            TARGET.target_path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        state["target_replaced"] = True
        os.fsync(parent_fd)

        verified_fd = _open_target_fd(parent_fd)
        try:
            verified = os.fstat(verified_fd)
            if not stat.S_ISREG(verified.st_mode) or verified.st_nlink != 1:
                raise UpgradeError("post-replace target is not a single-link regular file")
            if _metadata(verified) != (TARGET.uid, TARGET.gid, TARGET.mode):
                raise UpgradeError("post-replace target ownership/mode verification failed")
            if _git_blob_sha(_read_fd_all(verified_fd)) != TARGET.new_blob_sha:
                raise UpgradeError("post-replace target content verification failed")
        finally:
            os.close(verified_fd)
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if target_fd >= 0:
            os.close(target_fd)
        os.close(parent_fd)


def _receipt(*, result: str, source_sha: str, state: dict[str, bool], reason: str | None = None) -> str:
    payload = {
        "schema": RECEIPT_SCHEMA,
        "result": result,
        "source_sha": source_sha,
        "old_blob": TARGET.old_blob_sha,
        "new_blob": TARGET.new_blob_sha,
        "mutation_started": state["mutation_started"],
        "target_replaced": state["target_replaced"],
        "credential_content_read": False,
        "github_api_request": False,
        "helper_executed": False,
        "systemd_mutation": False,
        "automatic_retry": False,
        "automatic_rollback": False,
        "automatic_cleanup": False,
    }
    if reason is not None:
        payload["reason"] = reason
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight, and only with --apply atomically replace, the one reviewed P9 "
            "source-App auth module from the pre-Hermes allowlist blob to the exact "
            "Hermes-capable reviewed blob. Source merge never authorizes --apply."
        )
    )
    parser.add_argument("expected_sha", help="exact reviewed RPi5_main commit SHA")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the separately owner-authorized one-target live mutation",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    state = {"mutation_started": False, "target_replaced": False}
    source_sha = args.expected_sha
    try:
        reviewed = _preflight(source_sha)
        if not args.apply:
            print(_receipt(result="PREFLIGHT_PASS", source_sha=source_sha, state=state))
            return 0

        # Duplicate the complete read-only gate immediately before the first mutation.
        reviewed = _preflight(source_sha)
        _replace_exact_target(reviewed, state)
    except (UpgradeError, OSError) as exc:
        print(
            _receipt(
                result="FAIL_CLOSED",
                source_sha=source_sha,
                state=state,
                reason=str(exc),
            )
        )
        return 1

    print(_receipt(result="PASS", source_sha=source_sha, state=state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
