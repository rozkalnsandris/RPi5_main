#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
SCHEMA = "dashboard-rpi5.handoff-execution-bundle.v1"
CAPABILITY = "dashboard-rpi5.preverified-handoff-materializer.v1"

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
ENTRYPOINT_REPO_PATH = "scripts/dashboard-rpi5-preverified-handoff-materializer.py"
CORE_REPO_PATH = "scripts/dashboard-rpi5-preverified-handoff-materializer-core.py"

BUNDLE_BASE = Path("/var/lib/rozkalns-dashboard-handoff-exec")
BUNDLE_ROOT = BUNDLE_BASE / "v1"
ENTRYPOINT_NAME = "dashboard-rpi5-preverified-handoff-materializer.py"
CORE_NAME = "dashboard-rpi5-preverified-handoff-materializer-core.py"
MANIFEST_NAME = "execution-manifest.json"

ROOT_UID = 0
ROOT_GID = 0
BASE_MODE = 0o755
DIR_MODE = 0o555
FILE_MODE = 0o444
MAX_MANIFEST_BYTES = 64 * 1024
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExecutionBundleProofError(RuntimeError):
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
        raise ExecutionBundleProofError(
            f"git {' '.join(args)} failed with rc={proc.returncode}"
        )
    return proc.stdout.strip()


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data
    ).hexdigest()


def _mode(st: os.stat_result) -> int:
    return stat.S_IMODE(st.st_mode)


def _assert_metadata(
    st: os.stat_result,
    *,
    uid: int,
    gid: int,
    mode: int,
    label: str,
    directory: bool,
) -> None:
    if directory:
        if not stat.S_ISDIR(st.st_mode):
            raise ExecutionBundleProofError(f"{label} is not directory")
    else:
        if not stat.S_ISREG(st.st_mode):
            raise ExecutionBundleProofError(f"{label} is not regular file")
    if st.st_uid != uid or st.st_gid != gid:
        raise ExecutionBundleProofError(f"{label} ownership mismatch")
    if _mode(st) != mode:
        raise ExecutionBundleProofError(f"{label} mode mismatch")


def _read_fd(fd: int, maximum: int, label: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(64 * 1024, maximum + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum:
            raise ExecutionBundleProofError(f"{label} exceeds size bound")
        chunks.append(chunk)
    return b"".join(chunks)


def _strict_json(raw: bytes) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ExecutionBundleProofError(f"duplicate manifest key: {key}")
            out[key] = value
        return out
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=hook)
    except ExecutionBundleProofError:
        raise
    except Exception as exc:
        raise ExecutionBundleProofError("manifest is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise ExecutionBundleProofError("manifest root is not object")
    return value


def _read_root_file(root_fd: int, name: str, label: str) -> bytes:
    fd = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=root_fd,
    )
    try:
        _assert_metadata(
            os.fstat(fd),
            uid=ROOT_UID,
            gid=ROOT_GID,
            mode=FILE_MODE,
            label=label,
            directory=False,
        )
        return _read_fd(fd, 1024 * 1024, label)
    finally:
        os.close(fd)


def main() -> int:
    if os.geteuid() == 0:
        raise ExecutionBundleProofError(
            "read-only execution-bundle proof must run unprivileged"
        )

    if _run_git("symbolic-ref", "--short", "-q", "HEAD") != "main":
        raise ExecutionBundleProofError("proof requires local branch main")
    if _run_git("status", "--porcelain=v1"):
        raise ExecutionBundleProofError("proof requires clean repository")

    head = _run_git("rev-parse", "HEAD")
    tree = _run_git("rev-parse", "HEAD^{tree}")
    entry_blob = _run_git("rev-parse", f"HEAD:{ENTRYPOINT_REPO_PATH}")
    core_blob = _run_git("rev-parse", f"HEAD:{CORE_REPO_PATH}")

    parent_fd = os.open(
        BUNDLE_BASE.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    try:
        _assert_metadata(
            os.fstat(parent_fd),
            uid=ROOT_UID,
            gid=ROOT_GID,
            mode=BASE_MODE,
            label="execution bundle parent",
            directory=True,
        )
    finally:
        os.close(parent_fd)

    base_fd = os.open(
        BUNDLE_BASE,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    try:
        _assert_metadata(
            os.fstat(base_fd),
            uid=ROOT_UID,
            gid=ROOT_GID,
            mode=BASE_MODE,
            label="execution bundle base",
            directory=True,
        )
    finally:
        os.close(base_fd)

    root_fd = os.open(
        BUNDLE_ROOT,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    try:
        _assert_metadata(
            os.fstat(root_fd),
            uid=ROOT_UID,
            gid=ROOT_GID,
            mode=DIR_MODE,
            label="execution bundle root",
            directory=True,
        )
        names = sorted(os.listdir(root_fd))
        if names != sorted([ENTRYPOINT_NAME, CORE_NAME, MANIFEST_NAME]):
            raise ExecutionBundleProofError("execution bundle tree mismatch")

        manifest_raw = _read_root_file(
            root_fd,
            MANIFEST_NAME,
            "execution manifest",
        )
        entrypoint = _read_root_file(
            root_fd,
            ENTRYPOINT_NAME,
            "execution entrypoint",
        )
        core = _read_root_file(root_fd, CORE_NAME, "execution core")
    finally:
        os.close(root_fd)

    manifest = _strict_json(manifest_raw)
    required = {
        "schema",
        "capability",
        "source_repository",
        "source_main_sha",
        "source_tree_sha",
        "entrypoint",
        "core",
    }
    if set(manifest) != required:
        raise ExecutionBundleProofError("execution manifest shape mismatch")
    if manifest["schema"] != SCHEMA or manifest["capability"] != CAPABILITY:
        raise ExecutionBundleProofError("execution manifest identity mismatch")
    if manifest["source_repository"] != SOURCE_REPOSITORY:
        raise ExecutionBundleProofError("execution source repository mismatch")
    if manifest["source_main_sha"] != head or SHA40.fullmatch(head) is None:
        raise ExecutionBundleProofError("execution source main SHA mismatch")
    if manifest["source_tree_sha"] != tree or SHA40.fullmatch(tree) is None:
        raise ExecutionBundleProofError("execution source tree SHA mismatch")

    expected = (
        (
            "entrypoint",
            ENTRYPOINT_REPO_PATH,
            entry_blob,
            entrypoint,
        ),
        ("core", CORE_REPO_PATH, core_blob, core),
    )
    for key, path, git_blob, data in expected:
        item = manifest[key]
        if type(item) is not dict or set(item) != {
            "repo_path",
            "git_blob_sha",
            "sha256",
        }:
            raise ExecutionBundleProofError(f"{key} manifest shape mismatch")
        if item["repo_path"] != path:
            raise ExecutionBundleProofError(f"{key} repo path mismatch")
        if item["git_blob_sha"] != git_blob or SHA40.fullmatch(git_blob) is None:
            raise ExecutionBundleProofError(f"{key} Git blob mismatch")
        if _git_blob_sha(data) != git_blob:
            raise ExecutionBundleProofError(f"{key} root bytes Git blob mismatch")
        digest = hashlib.sha256(data).hexdigest()
        if item["sha256"] != digest or SHA256.fullmatch(digest) is None:
            raise ExecutionBundleProofError(f"{key} SHA-256 mismatch")

    partial = BUNDLE_BASE / ".v1.execution-bundle-partial"
    if partial.exists() or partial.is_symlink():
        raise ExecutionBundleProofError(
            "execution bundle partial remains after publication"
        )

    print("DASHBOARD_HANDOFF_EXECUTION_BUNDLE_PROOF=PASS")
    print(f"sourceMainSha={head}")
    print(f"sourceTreeSha={tree}")
    print(f"entrypointGitBlobSha={entry_blob}")
    print(f"coreGitBlobSha={core_blob}")
    print(f"bundleRoot={BUNDLE_ROOT}")
    print("owner=root:root")
    print("directoryMode=0555")
    print("fileMode=0444")
    print("rootMutation=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"P10_DASHBOARD_HANDOFF_EXEC_BUNDLE_PROOF=STOP "
            f"reason={type(exc).__name__}:{exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
