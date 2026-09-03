#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import errno
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
from typing import Any

OWNER = "andris"
GROUP = "andris"
SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
SCHEMA = "dashboard-rpi5.handoff-execution-bundle.v1"
CAPABILITY = "dashboard-rpi5.preverified-handoff-materializer.v1"

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
ENTRYPOINT_REPO_PATH = "scripts/dashboard-rpi5-preverified-handoff-materializer.py"
CORE_REPO_PATH = "scripts/dashboard-rpi5-preverified-handoff-materializer-core.py"
ENTRYPOINT = REPO_ROOT / ENTRYPOINT_REPO_PATH
CORE = REPO_ROOT / CORE_REPO_PATH

INGRESS_BASE = Path(pwd.getpwnam(OWNER).pw_dir) / ".cache/rozkalns-dashboard-handoff-exec-ingress"
INGRESS_ROOT = INGRESS_BASE / "v1"
INGRESS_PARTIAL = INGRESS_BASE / ".v1.execution-ingress-partial"
MANIFEST_NAME = "execution-manifest.json"

BASE_MODE = 0o700
DIR_MODE = 0o555
FILE_MODE = 0o444
BUILD_MODE = 0o700
RENAME_NOREPLACE = 1
ACK = "RPi5_main#349:PREPARE-DASHBOARD-HANDOFF-EXECUTION-INGRESS-V1"


class ExecutionIngressError(RuntimeError):
    pass


def _run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(Path.home()),
            "LANG": "C",
            "LC_ALL": "C",
        },
    )
    if proc.returncode != 0:
        raise ExecutionIngressError(
            f"git {' '.join(args)} failed with rc={proc.returncode}"
        )
    return proc.stdout.strip()


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _read_regular_nofollow(path: Path, label: str) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise ExecutionIngressError(f"{label} open failed: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ExecutionIngressError(f"{label} is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def _write_exact_file(dir_fd: int, name: str, data: bytes) -> None:
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o400,
        dir_fd=dir_fd,
    )
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise ExecutionIngressError(f"short write: {name}")
            view = view[written:]
        os.fchmod(fd, FILE_MODE)
        os.fsync(fd)
    finally:
        os.close(fd)


def _rename_noreplace(base_fd: int, source: str, destination: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise ExecutionIngressError("atomic no-replace publish requires renameat2")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        base_fd,
        os.fsencode(source),
        base_fd,
        os.fsencode(destination),
        RENAME_NOREPLACE,
    )
    if result != 0:
        err = ctypes.get_errno()
        if err == errno.EEXIST:
            raise ExecutionIngressError(
                "execution ingress target appeared before atomic publish"
            )
        raise OSError(err, os.strerror(err), destination)


def _path_absent(base_fd: int, name: str, label: str) -> None:
    try:
        os.stat(name, dir_fd=base_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ExecutionIngressError(f"{label} must be absent")



def _verify_final_ingress(
    *,
    expected_entrypoint: bytes,
    expected_core: bytes,
    expected_manifest: bytes,
    uid: int,
    gid: int,
) -> None:
    root_fd = os.open(
        INGRESS_ROOT,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    try:
        st = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(st.st_mode)
            or st.st_uid != uid
            or st.st_gid != gid
            or stat.S_IMODE(st.st_mode) != DIR_MODE
        ):
            raise ExecutionIngressError(
                "published execution ingress root metadata mismatch"
            )

        names = sorted(os.listdir(root_fd))
        expected_names = sorted(
            [TRUSTED_ENTRYPOINT_NAME, TRUSTED_CORE_NAME, MANIFEST_NAME]
        )
        if names != expected_names:
            raise ExecutionIngressError(
                "published execution ingress tree mismatch"
            )

        for name, expected in (
            (TRUSTED_ENTRYPOINT_NAME, expected_entrypoint),
            (TRUSTED_CORE_NAME, expected_core),
            (MANIFEST_NAME, expected_manifest),
        ):
            fd = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=root_fd,
            )
            try:
                st = os.fstat(fd)
                if (
                    not stat.S_ISREG(st.st_mode)
                    or st.st_uid != uid
                    or st.st_gid != gid
                    or stat.S_IMODE(st.st_mode) != FILE_MODE
                ):
                    raise ExecutionIngressError(
                        f"published execution ingress file metadata mismatch: {name}"
                    )
                chunks: list[bytes] = []
                while True:
                    chunk = os.read(fd, 64 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                if b"".join(chunks) != expected:
                    raise ExecutionIngressError(
                        f"published execution ingress bytes mismatch: {name}"
                    )
            finally:
                os.close(fd)
    finally:
        os.close(root_fd)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the exact Dashboard handoff execution ingress"
    )
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--ack", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if os.geteuid() == 0:
        raise ExecutionIngressError("execution ingress preparation must not run as root")
    if not args.prepare:
        raise ExecutionIngressError("execution ingress preparation requires --prepare")
    if args.ack != ACK:
        raise ExecutionIngressError("execution ingress acknowledgement mismatch")

    try:
        uid = pwd.getpwnam(OWNER).pw_uid
        gid = grp.getgrnam(GROUP).gr_gid
    except KeyError as exc:
        raise ExecutionIngressError("fixed execution ingress identity unavailable") from exc
    if os.geteuid() != uid or os.getegid() != gid:
        raise ExecutionIngressError("execution ingress must run as exact andris:andris")

    branch = _run_git("symbolic-ref", "--short", "-q", "HEAD")
    if branch != "main":
        raise ExecutionIngressError("execution ingress preparation requires branch main")
    if _run_git("status", "--porcelain=v1"):
        raise ExecutionIngressError("repository working tree is dirty")

    source_main_sha = _run_git("rev-parse", "HEAD")
    source_tree_sha = _run_git("rev-parse", "HEAD^{tree}")

    entrypoint_committed_blob = _run_git(
        "rev-parse", f"HEAD:{ENTRYPOINT_REPO_PATH}"
    )
    core_committed_blob = _run_git("rev-parse", f"HEAD:{CORE_REPO_PATH}")

    entrypoint_bytes = _read_regular_nofollow(ENTRYPOINT, "execution entrypoint")
    core_bytes = _read_regular_nofollow(CORE, "execution core")

    entrypoint_blob = _git_blob_sha(entrypoint_bytes)
    core_blob = _git_blob_sha(core_bytes)
    if entrypoint_blob != entrypoint_committed_blob:
        raise ExecutionIngressError("entrypoint bytes differ from committed Git blob")
    if core_blob != core_committed_blob:
        raise ExecutionIngressError("core bytes differ from committed Git blob")

    manifest = {
        "schema": SCHEMA,
        "capability": CAPABILITY,
        "source_repository": SOURCE_REPOSITORY,
        "source_main_sha": source_main_sha,
        "source_tree_sha": source_tree_sha,
        "entrypoint": {
            "repo_path": ENTRYPOINT_REPO_PATH,
            "git_blob_sha": entrypoint_blob,
            "sha256": hashlib.sha256(entrypoint_bytes).hexdigest(),
        },
        "core": {
            "repo_path": CORE_REPO_PATH,
            "git_blob_sha": core_blob,
            "sha256": hashlib.sha256(core_bytes).hexdigest(),
        },
    }
    manifest_bytes = _canonical_json(manifest)

    parent = INGRESS_BASE.parent
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        st = os.fstat(parent_fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != uid or st.st_gid != gid:
            raise ExecutionIngressError("execution ingress parent metadata mismatch")

        try:
            os.mkdir(INGRESS_BASE.name, BASE_MODE, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass

        base_fd = os.open(
            INGRESS_BASE.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)

    try:
        st = os.fstat(base_fd)
        if (
            not stat.S_ISDIR(st.st_mode)
            or st.st_uid != uid
            or st.st_gid != gid
            or stat.S_IMODE(st.st_mode) != BASE_MODE
        ):
            raise ExecutionIngressError("execution ingress base metadata mismatch")

        _path_absent(base_fd, INGRESS_ROOT.name, "execution ingress target")
        _path_absent(base_fd, INGRESS_PARTIAL.name, "execution ingress partial")

        os.mkdir(INGRESS_PARTIAL.name, BUILD_MODE, dir_fd=base_fd)
        os.fsync(base_fd)
        partial_fd = os.open(
            INGRESS_PARTIAL.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=base_fd,
        )
        try:
            _write_exact_file(
                partial_fd,
                TRUSTED_ENTRYPOINT_NAME,
                entrypoint_bytes,
            )
            _write_exact_file(partial_fd, TRUSTED_CORE_NAME, core_bytes)
            _write_exact_file(partial_fd, MANIFEST_NAME, manifest_bytes)
            os.fchmod(partial_fd, DIR_MODE)
            os.fsync(partial_fd)
        finally:
            os.close(partial_fd)

        _rename_noreplace(base_fd, INGRESS_PARTIAL.name, INGRESS_ROOT.name)
        os.fsync(base_fd)
    finally:
        os.close(base_fd)

    _verify_final_ingress(
        expected_entrypoint=entrypoint_bytes,
        expected_core=core_bytes,
        expected_manifest=manifest_bytes,
        uid=uid,
        gid=gid,
    )

    receipt = {
        "status": "PREPARED",
        "capability": CAPABILITY,
        "source_main_sha": source_main_sha,
        "source_tree_sha": source_tree_sha,
        "entrypoint_git_blob_sha": entrypoint_blob,
        "core_git_blob_sha": core_blob,
        "ingress_root": str(INGRESS_ROOT),
        "directory_mode": "0555",
        "file_mode": "0444",
        "root_operations": 0,
    }
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


TRUSTED_ENTRYPOINT_NAME = "dashboard-rpi5-preverified-handoff-materializer.py"
TRUSTED_CORE_NAME = "dashboard-rpi5-preverified-handoff-materializer-core.py"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"P10_DASHBOARD_HANDOFF_EXEC_INGRESS=STOP "
            f"reason={type(exc).__name__}:{exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
