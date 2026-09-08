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
SCRIPT_RELATIVE = "scripts/install-hermes-deals-netto-nonroot-preflight-v2.py"
IMMUTABLE_RPI_BASELINE = "89ff3ad82a2829148789edfbe6fd2b742d38b728"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ROOT_UID = 0
ROOT_GID = 0

HERMES_SOURCE_ROOT = ROOT.parent / "hermes-deals-netto-nonroot-preflight-v2-trusted"
HERMES_ORIGIN = "https://github.com/rozkalnsandris/hermes-deals.git"
HERMES_SOURCE_SHA = "067db7bd4b8057bc16a9bf0ef9ed8487127a0a05"
HELPER_SOURCE = "tools/runner/netto_missing_normal_price_nonroot_preflight_v2.py"
HELPER_BLOB = "0f8b01ed3129323cc59e526262b369cf33346aba"
HELPER_SHA256 = "275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c"

CAPABILITY = "netto-missing-normal-price-nonroot-preflight-v2"
REGISTRATION_SCHEMA = "rozkalns.hermes-deals.netto-nonroot-preflight-v2-registration.v1"
HELPER_DIR = Path(
    "/usr/local/libexec/hermes-deals-audits/netto-missing-normal-price-nonroot-preflight-v2"
)
HELPER_TARGET = HELPER_DIR / "netto_missing_normal_price_nonroot_preflight_v2.py"
REGISTRATION_TARGET = Path(
    "/etc/hermes-deals-audits.d/netto-missing-normal-price-nonroot-preflight-v2.json"
)
DIR_TARGETS = ((HELPER_DIR, 0o755),)
SHARED_PARENTS = (
    (Path("/usr/local/libexec/hermes-deals-audits"), 0o755),
    (Path("/etc/hermes-deals-audits.d"), 0o755),
)
INSTALL_MUTATION_BUDGET = (
    ("trusted-directory-materialization", 1),
    ("trusted-file-materialization", 2),
)


class NettoPreflightV2InstallerError(RuntimeError):
    pass


@dataclass
class Progress:
    mutation_started: bool = False
    directories_materialized: int = 0
    files_materialized: int = 0


class ApplyFailure(NettoPreflightV2InstallerError):
    def __init__(self, message: str, progress: Progress):
        super().__init__(message)
        self.progress = progress


@dataclass(frozen=True)
class FileTarget:
    path: Path
    mode: int
    source_path: str | None
    expected_blob: str
    expected_sha256: str


HELPER_FILE = FileTarget(
    HELPER_TARGET, 0o555, HELPER_SOURCE, HELPER_BLOB, HELPER_SHA256
)


def _fail(message: str) -> None:
    raise NettoPreflightV2InstallerError(message)


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _run(argv: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return _run(
        (str(GIT), "-c", f"safe.directory={repo}", "-C", str(repo), *args),
        cwd=repo,
    )


def _git_stdout(repo: Path, *args: str) -> bytes:
    result = _git(repo, *args)
    if result.returncode != 0:
        _fail(f"Git source validation failed for fixed repository: {repo}")
    return result.stdout


def _require_rpi_checkout(expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail("expected RPi5 source SHA must be lowercase 40-character hex")
    head = _git_stdout(ROOT, "rev-parse", "HEAD").decode("ascii").strip()
    if head != expected_sha:
        _fail("RPi5 checkout HEAD does not match expected source SHA")
    if _git(ROOT, "merge-base", "--is-ancestor", IMMUTABLE_RPI_BASELINE, expected_sha).returncode != 0:
        _fail("RPi5 source is not descended from the reviewed installer baseline")
    tracked = _git_stdout(ROOT, "show", f"{expected_sha}:{SCRIPT_RELATIVE}")
    if tracked != Path(__file__).read_bytes():
        _fail("installer working-tree content differs from expected RPi5 source")


def _require_hermes_checkout() -> None:
    try:
        resolved = Path(
            _git_stdout(HERMES_SOURCE_ROOT, "rev-parse", "--show-toplevel")
            .decode("utf-8")
            .strip()
        )
    except (OSError, UnicodeError):
        _fail("fixed Hermes trusted source checkout is unavailable")
    if resolved != HERMES_SOURCE_ROOT:
        _fail("Hermes trusted source root identity drifted")
    head = _git_stdout(HERMES_SOURCE_ROOT, "rev-parse", "HEAD").decode("ascii").strip()
    if head != HERMES_SOURCE_SHA:
        _fail("Hermes trusted source HEAD differs from reviewed helper source SHA")
    symbolic = _git(HERMES_SOURCE_ROOT, "symbolic-ref", "-q", "HEAD")
    if symbolic.returncode == 0:
        _fail("Hermes trusted source checkout must be detached")
    if symbolic.returncode != 1:
        _fail("unable to prove detached Hermes trusted source checkout")
    if _git_stdout(HERMES_SOURCE_ROOT, "status", "--porcelain=v1", "--untracked-files=all"):
        _fail("Hermes trusted source checkout is not clean")
    origin = _git_stdout(HERMES_SOURCE_ROOT, "remote", "get-url", "origin").decode().strip()
    if origin != HERMES_ORIGIN:
        _fail("Hermes trusted source origin drifted")
    if _git(
        HERMES_SOURCE_ROOT,
        "merge-base",
        "--is-ancestor",
        HERMES_SOURCE_SHA,
        "origin/main",
    ).returncode != 0:
        _fail("reviewed Hermes helper source is not reachable from local origin/main")


def _source_bytes() -> bytes:
    data = _git_stdout(HERMES_SOURCE_ROOT, "show", f"{HERMES_SOURCE_SHA}:{HELPER_SOURCE}")
    if _git_blob(data) != HELPER_BLOB:
        _fail("reviewed Hermes helper Git blob drifted")
    if hashlib.sha256(data).hexdigest() != HELPER_SHA256:
        _fail("reviewed Hermes helper SHA-256 drifted")
    path = HERMES_SOURCE_ROOT / HELPER_SOURCE
    try:
        info = os.lstat(path)
    except OSError as exc:
        _fail(f"Hermes helper source cannot be inspected safely: {exc.strerror}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail("Hermes helper source is not a regular non-symlink file")
    if path.read_bytes() != data:
        _fail("Hermes helper worktree bytes differ from reviewed commit")
    return data


def _registration_bytes() -> bytes:
    value = {
        "schema": REGISTRATION_SCHEMA,
        "capability": CAPABILITY,
        "registered_source_sha": HERMES_SOURCE_SHA,
        "helper_sha256": HELPER_SHA256,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _require_directory(path: Path, mode: int) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required shared parent is absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(f"required path is not a real directory: {path}")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID:
        _fail(f"directory ownership mismatch: {path}")
    if stat.S_IMODE(info.st_mode) != mode:
        _fail(f"directory mode mismatch: {path}")


def _require_absent(path: Path) -> None:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    _fail(f"first-install target already exists and requires separate reconciliation: {path}")


def _registration_target() -> FileTarget:
    data = _registration_bytes()
    return FileTarget(
        REGISTRATION_TARGET,
        0o444,
        None,
        _git_blob(data),
        hashlib.sha256(data).hexdigest(),
    )


def _prepared_files() -> tuple[tuple[FileTarget, bytes], ...]:
    return (
        (HELPER_FILE, _source_bytes()),
        (_registration_target(), _registration_bytes()),
    )


def _preflight(expected_sha: str) -> tuple[tuple[FileTarget, bytes], ...]:
    _require_rpi_checkout(expected_sha)
    _require_hermes_checkout()
    for path, mode in SHARED_PARENTS:
        _require_directory(path, mode)
    prepared = _prepared_files()
    for path, _mode in DIR_TARGETS:
        _require_absent(path)
    for target, _desired in prepared:
        _require_absent(target.path)
    return prepared


def _create_directory(path: Path, mode: int) -> None:
    shared = {candidate: candidate_mode for candidate, candidate_mode in SHARED_PARENTS}
    expected_parent_mode = shared.get(path.parent)
    if expected_parent_mode is None:
        _fail(f"directory parent is outside fixed shared-parent set: {path}")
    _require_directory(path.parent, expected_parent_mode)
    try:
        os.mkdir(path, mode)
        os.chown(path, ROOT_UID, ROOT_GID)
        os.chmod(path, mode)
        info = os.lstat(path)
    except OSError as exc:
        _fail(f"directory materialization failed: {path}: {exc.strerror}")
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or stat.S_IMODE(info.st_mode) != mode
    ):
        _fail(f"post-create directory metadata drifted: {path}")


def _expected_parent_mode(path: Path) -> int:
    for candidate, mode in SHARED_PARENTS + DIR_TARGETS:
        if path == candidate:
            return mode
    _fail(f"file target parent is outside fixed parent set: {path}")
    raise AssertionError("unreachable")


def _write_file(target: FileTarget, desired: bytes) -> None:
    _require_directory(target.path.parent, _expected_parent_mode(target.path.parent))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target.path, flags, 0o600)
    except OSError as exc:
        _fail(f"exclusive file materialization failed: {target.path}: {exc.strerror}")
    try:
        view = memoryview(desired)
        offset = 0
        while offset < len(desired):
            try:
                written = os.write(fd, view[offset:])
            except OSError as exc:
                _fail(f"write failed while materializing {target.path}: {exc.strerror}")
            if written <= 0:
                _fail(f"short write while materializing {target.path}")
            offset += written
        try:
            os.fsync(fd)
            os.fchown(fd, ROOT_UID, ROOT_GID)
            os.fchmod(fd, target.mode)
            info = os.fstat(fd)
        except OSError as exc:
            _fail(f"file finalization failed: {target.path}: {exc.strerror}")
        if (
            info.st_uid != ROOT_UID
            or info.st_gid != ROOT_GID
            or stat.S_IMODE(info.st_mode) != target.mode
        ):
            _fail(f"post-write metadata drifted: {target.path}")
    finally:
        os.close(fd)


def _verify_file(target: FileTarget, desired: bytes) -> None:
    try:
        before = os.lstat(target.path)
    except OSError as exc:
        _fail(f"post-install target cannot be inspected: {target.path}: {exc.strerror}")
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        _fail(f"post-install target type drifted: {target.path}")
    if (
        before.st_uid != ROOT_UID
        or before.st_gid != ROOT_GID
        or stat.S_IMODE(before.st_mode) != target.mode
    ):
        _fail(f"post-install target metadata drifted: {target.path}")
    for required in ("O_NOFOLLOW", "O_CLOEXEC"):
        if not hasattr(os, required):
            _fail(f"required descriptor guard is unavailable: {required}")
    try:
        fd = os.open(target.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        _fail(f"post-install target cannot be opened safely: {target.path}: {exc.strerror}")
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            _fail(f"post-install target changed before descriptor validation: {target.path}")
        chunks: list[bytes] = []
        remaining = len(desired) + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > len(desired):
            _fail(f"post-install target exceeds reviewed size: {target.path}")
        now = os.stat(target.path, follow_symlinks=False)
        if (now.st_dev, now.st_ino) != (opened.st_dev, opened.st_ino):
            _fail(f"post-install target changed during descriptor validation: {target.path}")
    finally:
        os.close(fd)
    if (
        data != desired
        or _git_blob(data) != target.expected_blob
        or hashlib.sha256(data).hexdigest() != target.expected_sha256
    ):
        _fail(f"post-install target content drifted: {target.path}")


def _receipt(
    result: str,
    expected_sha: str,
    progress: Progress,
    *,
    reason: str | None = None,
) -> str:
    value = {
        "schema": "rozkalns.hermes-deals.netto-nonroot-preflight-v2-install-receipt.v1",
        "result": result,
        "source_sha": expected_sha,
        "hermes_source_sha": HERMES_SOURCE_SHA,
        "hermes_source_root": str(HERMES_SOURCE_ROOT),
        "directory_target_count": len(DIR_TARGETS),
        "file_target_count": 2,
        "directories_materialized": progress.directories_materialized,
        "files_materialized": progress.files_materialized,
        "mutation_started": progress.mutation_started,
        "mutation_budget": [list(item) for item in INSTALL_MUTATION_BUDGET],
        "credential_content_read": False,
        "credential_mutated": False,
        "github_api_request": False,
        "helper_executed": False,
        "canary_authorized": False,
        "parser_executed": False,
        "database_write_performed": False,
        "review_write_performed": False,
        "deployment_performed": False,
        "user_group_mutation": False,
        "docker_mutation": False,
        "systemd_mutation": False,
        "execution_wiring_changed": False,
        "automatic_retry": False,
        "automatic_rollback": False,
        "automatic_cleanup": False,
        "host_mutation_started": progress.mutation_started,
    }
    if reason is not None:
        value["reason"] = reason
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def preflight(expected_sha: str) -> str:
    _preflight(expected_sha)
    return _receipt("NETTO_V2_HELPER_INSTALL_PREFLIGHT_READY", expected_sha, Progress())


def apply(expected_sha: str) -> str:
    if os.geteuid() != ROOT_UID:
        _fail("--apply requires root and separate explicit LIVE authorization")
    prepared = _preflight(expected_sha)
    progress = Progress()
    try:
        for path, mode in DIR_TARGETS:
            progress.mutation_started = True
            _create_directory(path, mode)
            progress.directories_materialized += 1
        for target, desired in prepared:
            progress.mutation_started = True
            _write_file(target, desired)
            progress.files_materialized += 1
        for path, mode in DIR_TARGETS:
            _require_directory(path, mode)
        for target, desired in prepared:
            _verify_file(target, desired)
    except NettoPreflightV2InstallerError as exc:
        raise ApplyFailure(str(exc), progress) from exc
    return _receipt("NETTO_V2_HELPER_INSTALLED_FAIL_CLOSED", expected_sha, progress)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed first installer for the Hermes Deals Netto non-root preflight v2 helper"
    )
    parser.add_argument("expected_source_sha")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = apply(args.expected_source_sha) if args.apply else preflight(args.expected_source_sha)
    except ApplyFailure as exc:
        print(
            _receipt("FAIL_CLOSED", args.expected_source_sha, exc.progress, reason=str(exc)),
            file=sys.stderr,
        )
        return 1
    except NettoPreflightV2InstallerError as exc:
        print(
            _receipt("FAIL_CLOSED", args.expected_source_sha, Progress(), reason=str(exc)),
            file=sys.stderr,
        )
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
