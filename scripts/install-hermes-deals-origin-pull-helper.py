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
SCRIPT_RELATIVE = "scripts/install-hermes-deals-origin-pull-helper.py"
IMMUTABLE_RPI_BASELINE = "e23234f7a9308211a0d964a791e2b0f70b587818"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ROOT_UID = 0
ROOT_GID = 0

HERMES_SOURCE_ROOT = ROOT.parent / "hermes-deals-origin-pull-trusted"
HERMES_ORIGIN = "https://github.com/rozkalnsandris/hermes-deals.git"
HERMES_SOURCE_SHA = "2f47f64ab15e767f4e53ad182326e64e313d5094"
HELPER_SOURCE = "tools/runner/origin_path_rpi5_pull_helper.py"
HELPER_BLOB = "51bb23cc6c2083ab7c8b4e81ba82dd880e46d673"
HELPER_SHA256 = "f2f6e4ca823eb6c0872de0a5e92531ebacb076c48934c80654d84f3ef6f7e625"
PROBE_SOURCE = "tools/hermes_deals_origin_probe.py"
PROBE_BLOB = "2362e8eb578a7279c38fe4ed2a7d1edd05df891a"
PROBE_SHA256 = "96a8b5819ec85f27095c535f1a3be6cba7bac0e2a40a1132869fb39dc669ad43"

HELPER_TARGET = Path("/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch")
PROBE_TARGET = Path("/usr/local/libexec/hermes-deals-audits/origin-path-probe.py")
REGISTRATION_TARGET = Path("/etc/hermes-deals-audits.d/origin-path-rpi5-pull.json")
REGISTRATION_SCHEMA = "rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1"
CAPABILITY = "origin-path-audit"

DIR_TARGETS = (
    Path("/var/lib/hermes-deals-audits"),
    Path("/var/lib/hermes-deals-audits/origin-path-audit"),
    Path("/var/lib/hermes-deals-audits/origin-path-audit/evidence"),
    Path("/var/lib/hermes-deals-audits/origin-path-audit/evidence/rpi5"),
)
DIR_MODE = 0o700
SHARED_PARENTS = (
    (Path("/usr/local/sbin"), 0o755),
    (Path("/usr/local/libexec/hermes-deals-audits"), 0o755),
    (Path("/etc/hermes-deals-audits.d"), 0o755),
    (Path("/var/lib"), 0o755),
)
INSTALL_MUTATION_BUDGET = (
    ("trusted-directory-materialization", 4),
    ("trusted-file-materialization", 3),
)


class HermesOriginPullHelperInstallerError(RuntimeError):
    pass


@dataclass
class Progress:
    mutation_started: bool = False
    directories_materialized: int = 0
    files_materialized: int = 0


class ApplyFailure(HermesOriginPullHelperInstallerError):
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


FILE_TARGETS = (
    FileTarget(HELPER_TARGET, 0o755, HELPER_SOURCE, HELPER_BLOB, HELPER_SHA256),
    FileTarget(PROBE_TARGET, 0o755, PROBE_SOURCE, PROBE_BLOB, PROBE_SHA256),
)


def _fail(message: str) -> None:
    raise HermesOriginPullHelperInstallerError(message)


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _run(argv: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, shell=False,
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
    if not HERMES_SOURCE_ROOT.is_absolute():
        _fail("fixed Hermes source root must be absolute")
    try:
        resolved = Path(_git_stdout(HERMES_SOURCE_ROOT, "rev-parse", "--show-toplevel").decode().strip())
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
    if symbolic.returncode not in (0, 1):
        _fail("unable to prove detached Hermes trusted source checkout")
    if _git_stdout(HERMES_SOURCE_ROOT, "status", "--porcelain=v1", "--untracked-files=all"):
        _fail("Hermes trusted source checkout is not clean")
    origin = _git_stdout(HERMES_SOURCE_ROOT, "remote", "get-url", "origin").decode().strip()
    if origin != HERMES_ORIGIN:
        _fail("Hermes trusted source origin drifted")
    if _git(HERMES_SOURCE_ROOT, "merge-base", "--is-ancestor", HERMES_SOURCE_SHA, "origin/main").returncode != 0:
        _fail("reviewed Hermes helper source is not reachable from local origin/main")


def _source_bytes(target: FileTarget) -> bytes:
    if target.source_path is None:
        _fail("generated target cannot be loaded from Hermes source")
    data = _git_stdout(HERMES_SOURCE_ROOT, "show", f"{HERMES_SOURCE_SHA}:{target.source_path}")
    if _git_blob(data) != target.expected_blob:
        _fail(f"reviewed Hermes Git blob drifted: {target.source_path}")
    if hashlib.sha256(data).hexdigest() != target.expected_sha256:
        _fail(f"reviewed Hermes SHA-256 drifted: {target.source_path}")
    worktree_path = HERMES_SOURCE_ROOT / target.source_path
    try:
        info = os.lstat(worktree_path)
    except OSError as exc:
        _fail(f"Hermes source path cannot be inspected safely: {target.source_path}: {exc.strerror}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail(f"Hermes source path is not a regular non-symlink file: {target.source_path}")
    if worktree_path.read_bytes() != data:
        _fail(f"Hermes worktree bytes differ from reviewed commit: {target.source_path}")
    return data


def _registration_bytes() -> bytes:
    value = {
        "schema": REGISTRATION_SCHEMA,
        "capability": CAPABILITY,
        "registered_source_sha": HERMES_SOURCE_SHA,
        "helper_sha256": HELPER_SHA256,
        "probe_sha256": PROBE_SHA256,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _require_directory(path: Path, mode: int) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required shared parent is absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(f"required shared parent is not a real directory: {path}")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or stat.S_IMODE(info.st_mode) != mode:
        _fail(f"required shared parent metadata drifted: {path}")


def _require_absent(path: Path) -> None:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    _fail(f"first-install target already exists and requires separate reconciliation: {path}")


def _prepared_files() -> tuple[tuple[FileTarget, bytes], ...]:
    source_files = [(target, _source_bytes(target)) for target in FILE_TARGETS]
    registration = _registration_bytes()
    reg_target = FileTarget(
        REGISTRATION_TARGET, 0o600, None, _git_blob(registration), hashlib.sha256(registration).hexdigest()
    )
    return tuple(source_files + [(reg_target, registration)])


def _preflight(expected_sha: str) -> tuple[tuple[FileTarget, bytes], ...]:
    _require_rpi_checkout(expected_sha)
    _require_hermes_checkout()
    for path, mode in SHARED_PARENTS:
        _require_directory(path, mode)
    prepared = _prepared_files()
    for path in DIR_TARGETS:
        _require_absent(path)
    for target, _ in prepared:
        _require_absent(target.path)
    return prepared


def _create_directory(path: Path) -> None:
    _require_directory(path.parent, 0o700 if path.parent in DIR_TARGETS else 0o755)
    try:
        os.mkdir(path, DIR_MODE)
        os.chown(path, ROOT_UID, ROOT_GID)
        os.chmod(path, DIR_MODE)
        info = os.lstat(path)
    except OSError as exc:
        _fail(f"directory materialization failed: {path}: {exc.strerror}")
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or stat.S_IMODE(info.st_mode) != DIR_MODE:
        _fail(f"post-create directory metadata drifted: {path}")


def _write_file(target: FileTarget, desired: bytes) -> None:
    parent_modes = {path: mode for path, mode in SHARED_PARENTS}
    expected_parent_mode = parent_modes.get(target.path.parent)
    if expected_parent_mode is None:
        _fail(f"file target parent is outside the fixed shared-parent set: {target.path}")
    _require_directory(target.path.parent, expected_parent_mode)
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
        if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or stat.S_IMODE(info.st_mode) != target.mode:
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
    if before.st_uid != ROOT_UID or before.st_gid != ROOT_GID or stat.S_IMODE(before.st_mode) != target.mode:
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
        try:
            now = os.stat(target.path, follow_symlinks=False)
        except OSError as exc:
            _fail(f"post-install target path changed during validation: {target.path}: {exc.strerror}")
        if (now.st_dev, now.st_ino) != (opened.st_dev, opened.st_ino):
            _fail(f"post-install target changed during descriptor validation: {target.path}")
    finally:
        os.close(fd)
    if data != desired or _git_blob(data) != target.expected_blob or hashlib.sha256(data).hexdigest() != target.expected_sha256:
        _fail(f"post-install target content drifted: {target.path}")


def _receipt(result: str, expected_sha: str, progress: Progress, *, reason: str | None = None) -> str:
    value = {
        "schema": "rozkalns.hermes-deals.origin-pull-helper-install-receipt.v1",
        "result": result,
        "source_sha": expected_sha,
        "hermes_source_sha": HERMES_SOURCE_SHA,
        "hermes_source_root": str(HERMES_SOURCE_ROOT),
        "directory_target_count": len(DIR_TARGETS),
        "file_target_count": 3,
        "directories_materialized": progress.directories_materialized,
        "files_materialized": progress.files_materialized,
        "mutation_started": progress.mutation_started,
        "mutation_budget": [list(item) for item in INSTALL_MUTATION_BUDGET],
        "credential_content_read": False,
        "credential_mutated": False,
        "github_api_request": False,
        "helper_executed": False,
        "genuine_audit_authorized": False,
        "socket_request_sent": False,
        "systemd_mutation": False,
        "broker_dispatch_enabled": False,
        "production_mutation_started": progress.mutation_started,
        "automatic_retry": False,
        "automatic_rollback": False,
        "automatic_cleanup": False,
    }
    if reason is not None:
        value["reason"] = reason
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def preflight(expected_sha: str) -> str:
    _preflight(expected_sha)
    return _receipt("HERMES_ORIGIN_PULL_HELPER_INSTALL_PREFLIGHT_READY", expected_sha, Progress())


def apply(expected_sha: str) -> str:
    if os.geteuid() != ROOT_UID:
        _fail("--apply requires root and separate explicit LIVE authorization")
    prepared = _preflight(expected_sha)
    progress = Progress()
    try:
        for path in DIR_TARGETS:
            progress.mutation_started = True
            _create_directory(path)
            progress.directories_materialized += 1
        for target, desired in prepared:
            progress.mutation_started = True
            _write_file(target, desired)
            progress.files_materialized += 1
        for path in DIR_TARGETS:
            _require_directory(path, DIR_MODE)
        for target, desired in prepared:
            _verify_file(target, desired)
    except HermesOriginPullHelperInstallerError as exc:
        raise ApplyFailure(str(exc), progress) from exc
    return _receipt("HERMES_ORIGIN_PULL_HELPER_INSTALLED_FAIL_CLOSED", expected_sha, progress)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed first installer for the Hermes origin pull helper prerequisite bundle")
    parser.add_argument("expected_source_sha")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = apply(args.expected_source_sha) if args.apply else preflight(args.expected_source_sha)
    except ApplyFailure as exc:
        print(_receipt("FAIL_CLOSED", args.expected_source_sha, exc.progress, reason=str(exc)), file=sys.stderr)
        return 1
    except HermesOriginPullHelperInstallerError as exc:
        print(_receipt("FAIL_CLOSED", args.expected_source_sha, Progress(), reason=str(exc)), file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
