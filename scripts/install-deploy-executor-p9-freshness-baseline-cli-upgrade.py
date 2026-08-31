#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

GIT = Path("/usr/bin/git")
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/install-deploy-executor-p9-freshness-baseline-cli-upgrade.py"
OLD_INSTALLED_BLOB_SHA = "0afad9d93dd74570aeed31ccfdb8c5c7419ddcd8"
REPAIRED_SOURCE_BLOB_SHA = "8dc38e4d224373925483a45b782f04e0aa27a8bd"


class UpgradeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetSpec:
    source_path: str
    target_path: Path
    old_blob_sha: str
    new_blob_sha: str
    mode: int


TARGET = TargetSpec(
    source_path="ops/bin/rozkalns-deploy-p9-control-baseline",
    target_path=Path("/usr/local/sbin/rozkalns-deploy-p9-control-baseline"),
    old_blob_sha=OLD_INSTALLED_BLOB_SHA,
    new_blob_sha=REPAIRED_SOURCE_BLOB_SHA,
    mode=0o755,
)


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _run_git(*args: str, capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(GIT), "-C", str(ROOT), *args],
        check=False,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _require_exact_source(expected_sha: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        raise UpgradeError("expected SHA must be lowercase 40-char hex")
    actual = _run_git("rev-parse", "--verify", "HEAD", capture=True)
    if actual.returncode != 0:
        raise UpgradeError("unable to resolve local source HEAD")
    if actual.stdout.decode("ascii").strip() != expected_sha:
        raise UpgradeError("source SHA mismatch")
    clean = _run_git(
        "diff",
        "--quiet",
        "--no-ext-diff",
        expected_sha,
        "--",
        SCRIPT_RELATIVE,
    )
    if clean.returncode != 0:
        raise UpgradeError("reviewed upgrade operator differs from exact expected SHA")


def _reviewed_bytes(expected_sha: str) -> bytes:
    result = _run_git("show", f"{expected_sha}:{TARGET.source_path}", capture=True)
    if result.returncode != 0:
        raise UpgradeError(f"reviewed source object unavailable: {TARGET.source_path}")
    reviewed = result.stdout
    if _git_blob_sha(reviewed) != TARGET.new_blob_sha:
        raise UpgradeError("reviewed repaired baseline CLI blob mismatch")
    return reviewed


def _target_metadata(st: os.stat_result) -> tuple[int, int, int]:
    return (st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode))


def _require_parent_chain_safe(path: Path) -> None:
    for parent in reversed(path.parents):
        st = os.lstat(parent)
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
            raise UpgradeError(f"installed target parent is not a real directory: {parent}")
        if st.st_uid != 0 or st.st_gid != 0 or stat.S_IMODE(st.st_mode) & 0o022:
            raise UpgradeError(f"installed target parent ownership/mode is unsafe: {parent}")


def _require_target_prestate() -> None:
    _require_parent_chain_safe(TARGET.target_path)
    try:
        st = os.lstat(TARGET.target_path)
    except FileNotFoundError as exc:
        raise UpgradeError(f"required installed target missing: {TARGET.target_path}") from exc
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise UpgradeError(f"installed target is not a regular non-symlink file: {TARGET.target_path}")
    if _target_metadata(st) != (0, 0, TARGET.mode):
        raise UpgradeError(f"installed target ownership/mode mismatch: {TARGET.target_path}")
    try:
        data = TARGET.target_path.read_bytes()
    except OSError as exc:
        raise UpgradeError(f"unable to read installed target: {TARGET.target_path}") from exc
    if _git_blob_sha(data) != TARGET.old_blob_sha:
        raise UpgradeError(f"installed target differs from reviewed old source: {TARGET.target_path}")


def _preflight(expected_sha: str) -> bytes:
    _require_exact_source(expected_sha)
    if os.geteuid() != 0:
        raise UpgradeError("P9 freshness baseline CLI upgrade requires root")
    if not hasattr(os, "O_NOFOLLOW"):
        raise UpgradeError("O_NOFOLLOW is required for the reviewed host convergence")
    reviewed = _reviewed_bytes(expected_sha)
    _require_target_prestate()
    return reviewed


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
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise UpgradeError("short write while replacing reviewed baseline CLI")
        written += count


def _replace_exact_target(reviewed_bytes: bytes) -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        raise UpgradeError("O_NOFOLLOW is required for the reviewed host convergence")
    flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        fd = os.open(TARGET.target_path, flags)
    except OSError as exc:
        raise UpgradeError(f"unable to open installed target for replacement: {TARGET.target_path}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise UpgradeError(f"opened target is not regular: {TARGET.target_path}")
        if _target_metadata(opened) != (0, 0, TARGET.mode):
            raise UpgradeError(f"opened target ownership/mode mismatch: {TARGET.target_path}")
        current = _read_fd_all(fd)
        if _git_blob_sha(current) != TARGET.old_blob_sha:
            raise UpgradeError(f"opened target differs from reviewed old source: {TARGET.target_path}")
        path_now = os.stat(TARGET.target_path, follow_symlinks=False)
        if not stat.S_ISREG(path_now.st_mode) or stat.S_ISLNK(path_now.st_mode):
            raise UpgradeError(f"installed target changed type during preflight: {TARGET.target_path}")
        if _target_metadata(path_now) != (0, 0, TARGET.mode):
            raise UpgradeError(f"installed target metadata changed during preflight: {TARGET.target_path}")
        if (path_now.st_dev, path_now.st_ino) != (opened.st_dev, opened.st_ino):
            raise UpgradeError(f"installed target changed during preflight: {TARGET.target_path}")

        # Authorized one-target host mutation begins at this ftruncate.
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        _write_fd_all(fd, reviewed_bytes)
        os.fsync(fd)

        after = os.fstat(fd)
        if _target_metadata(after) != (0, 0, TARGET.mode):
            raise UpgradeError(f"installed target metadata changed after write: {TARGET.target_path}")
        installed = _read_fd_all(fd)
        if installed != reviewed_bytes:
            raise UpgradeError(f"installed target byte verification failed: {TARGET.target_path}")
        if _git_blob_sha(installed) != TARGET.new_blob_sha:
            raise UpgradeError(f"installed target blob verification failed: {TARGET.target_path}")
    finally:
        os.close(fd)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight, and only with --apply replace, the one reviewed P9 freshness "
            "baseline CLI target. Source merge alone never authorizes --apply."
        )
    )
    parser.add_argument("expected_sha", help="exact reviewed RPi5_main commit SHA")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the separately owner-authorized one-target host mutation",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        reviewed = _preflight(args.expected_sha)
        if not args.apply:
            print(f"P9_FRESHNESS_BASELINE_CLI_UPGRADE_PREFLIGHT=PASS source_sha={args.expected_sha}")
            print(f"TARGET={TARGET.target_path}")
            print(f"OLD_BLOB={TARGET.old_blob_sha}")
            print(f"NEW_BLOB={TARGET.new_blob_sha}")
            print("P9_FRESHNESS_BASELINE_CLI_MUTATION=NO")
            return 0

        # Final duplicate complete gate immediately before the first host mutation.
        reviewed = _preflight(args.expected_sha)
        _replace_exact_target(reviewed)
    except UpgradeError as exc:
        print(f"P9 freshness baseline CLI upgrade refused: {exc}", file=sys.stderr)
        return 1

    print(f"P9_FRESHNESS_BASELINE_CLI_UPGRADE=PASS source_sha={args.expected_sha}")
    print("TARGETS_REPLACED=1")
    print(f"TARGET={TARGET.target_path}")
    print(f"OLD_BLOB={TARGET.old_blob_sha}")
    print(f"NEW_BLOB={TARGET.new_blob_sha}")
    print("BASELINE_CLI_TOUCHED=YES")
    print("SOURCE_AUTH_TOUCHED=NO")
    print("ADAPTER_TOUCHED=NO")
    print("PRODUCER_TOUCHED=NO")
    print("COLLECTOR_TOUCHED=NO")
    print("CONFIG_REGISTRY_MUTATION=NO")
    print("SYSTEMD_MUTATION=NO")
    print("NETWORK_REQUEST=NO")
    print("CREDENTIAL_READ=NO")
    print("D1_REQUEST=NO")
    print("BASELINE_COLLECTION=NO")
    print("LIVE_AUTH_MUTATION=NO")
    print("P9_EXECUTION=NO")
    print("P10_EXECUTION=NO")
    print("STATE_STORE_TOUCHED=NO")
    print("ROLLBACK_PATH=NO")
    print("RETRY_PATH=NO")
    print("CLEANUP_PATH=NO")
    print("ALTERNATE_MUTATION_PATH=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
