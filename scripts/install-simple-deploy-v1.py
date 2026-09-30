#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
from typing import Sequence

GIT = Path("/usr/bin/git")
SYSUSERS = Path("/usr/bin/systemd-sysusers")
NOLOGIN = Path("/usr/sbin/nologin")
ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
INSTALLER_RELATIVE = "scripts/install-simple-deploy-v1.py"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ROOT_UID = 0
ROOT_GID = 0
RUNTIME_USER = "rozkalns-simple-deployer"
RUNTIME_GROUP = "rozkalns-simple-deployer"
DOCKER_GROUP = "docker"
RUNTIME_HOME = "/var/lib/rozkalns-simple-deployer"
RUNTIME_SHELL = "/usr/sbin/nologin"
IDENTITY_SCHEMA = "rozkalns.rpi5-main.simple-deploy.identity.v1"
PHASE_B_REPAIR_BASE_SHA = "b57ed42d5eb01f15b62c1f53459ffe0539a57d9c"
PHASE_B_STATE_ROOT = Path("/var/lib/rozkalns-simple-deployer")
PHASE_B_DOCKER_CONFIG = PHASE_B_STATE_ROOT / "docker-anonymous"
PHASE_B_SCHEMA_MODULE_TARGET = Path("/usr/local/libexec/rozkalns-simple-deployer/simple_deploy_weather_schema_init_v1.py")

SHARED_PARENTS = (
    (Path("/usr/local/lib"), 0o755),
    (Path("/usr/local/libexec"), 0o755),
    (Path("/etc"), 0o755),
    (Path("/etc/systemd/system"), 0o755),
)
DIRECTORY_TARGETS = (
    (Path("/usr/local/lib/sysusers.d"), 0o755),
    (Path("/usr/local/libexec/rozkalns-simple-deployer"), 0o755),
    (Path("/etc/rozkalns-simple-deployer"), 0o755),
    (Path("/etc/rozkalns-simple-deployer/compose"), 0o755),
    (Path("/etc/rozkalns-simple-deployer/docker-anonymous"), 0o755),
)
INSTALL_MUTATION_BUDGET = (
    ("filesystem.simple-deploy-directory-materialization", 5),
    ("filesystem.simple-deploy-file-materialization", 10),
    ("identity.simple-deploy-system-user-group-provision", 1),
)


class SimpleDeployInstallerError(RuntimeError):
    pass


@dataclass
class Progress:
    mutation_started: bool = False
    directories_materialized: int = 0
    files_materialized: int = 0
    principal_provisioning_started: bool = False


class ApplyFailure(SimpleDeployInstallerError):
    def __init__(self, message: str, progress: Progress):
        super().__init__(message)
        self.progress = progress


@dataclass(frozen=True)
class FileTarget:
    source_path: str | None
    target: Path
    mode: int


TRACKED_FILES = (
    FileTarget("ops/sysusers/rozkalns-simple-deployer.conf", Path("/usr/local/lib/sysusers.d/rozkalns-simple-deployer.conf"), 0o644),
    FileTarget("ops/bin/rozkalns-simple-deployer", Path("/usr/local/libexec/rozkalns-simple-deployer/rozkalns-simple-deployer"), 0o555),
    FileTarget("ops/lib/deploy_executor/simple_deploy_v1.py", Path("/usr/local/libexec/rozkalns-simple-deployer/simple_deploy_v1.py"), 0o444),
    FileTarget("ops/bin/rozkalns-simple-deploy-weather-schema-init", Path("/usr/local/libexec/rozkalns-simple-deployer/rozkalns-simple-deploy-weather-schema-init"), 0o555),
    FileTarget("ops/lib/deploy_executor/simple_deploy_weather_schema_init_v1.py", Path("/usr/local/libexec/rozkalns-simple-deployer/simple_deploy_weather_schema_init_v1.py"), 0o444),
    FileTarget("ops/deploy/simple-deploy-targets-v1.json", Path("/etc/rozkalns-simple-deployer/targets.json"), 0o444),
    FileTarget(None, Path("/etc/rozkalns-simple-deployer/identity.json"), 0o444),
    FileTarget("ops/deploy/simple-deploy-compose/rozkalns-weather-public.yml", Path("/etc/rozkalns-simple-deployer/compose/rozkalns-weather-public.yml"), 0o444),
    FileTarget("ops/systemd/rozkalns-simple-deployer.service", Path("/etc/systemd/system/rozkalns-simple-deployer.service"), 0o644),
    FileTarget("ops/systemd/rozkalns-simple-deployer.timer", Path("/etc/systemd/system/rozkalns-simple-deployer.timer"), 0o644),
)


def _fail(message: str) -> None:
    raise SimpleDeployInstallerError(message)


def _run(argv: Sequence[str], *, cwd: Path, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv),
        cwd=cwd,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return _run((str(GIT), "-c", f"safe.directory={ROOT}", "-C", str(ROOT), *args), cwd=ROOT)


def _git_stdout(*args: str) -> bytes:
    result = _git(*args)
    if result.returncode != 0:
        _fail("Git source validation failed")
    return result.stdout


def _require_source_checkout(expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail("expected source SHA must be lowercase 40-character hex")
    head = _git_stdout("rev-parse", "HEAD").decode("ascii").strip()
    if head != expected_sha:
        _fail("checkout HEAD does not match expected source SHA")
    origin = _git_stdout("remote", "get-url", "origin").decode("utf-8").strip()
    if origin != ORIGIN:
        _fail("checkout origin drifted")
    if _git_stdout("status", "--porcelain=v1", "--untracked-files=all"):
        _fail("source checkout must be clean")
    tracked_installer = _git_stdout("show", f"{expected_sha}:{INSTALLER_RELATIVE}")
    if tracked_installer != Path(__file__).read_bytes():
        _fail("installer working-tree bytes differ from expected source")


def _require_directory(path: Path, mode: int) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required parent is absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(f"required parent is not a real directory: {path}")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or stat.S_IMODE(info.st_mode) != mode:
        _fail(f"required parent metadata drifted: {path}")


def _require_absent(path: Path) -> None:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    _fail(f"first-install target already exists and needs separate reconciliation: {path}")


def _source_bytes_at(source_sha: str, target: FileTarget) -> bytes:
    if target.source_path is None:
        return _identity_bytes(source_sha)
    if FULL_SHA.fullmatch(source_sha) is None:
        _fail("source SHA must be lowercase 40-character hex")
    return _git_stdout("show", f"{source_sha}:{target.source_path}")


def _source_bytes(expected_sha: str, target: FileTarget) -> bytes:
    return _source_bytes_at(expected_sha, target)


def _identity_bytes(expected_sha: str) -> bytes:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail("identity source SHA must be lowercase 40-character hex")
    value = {
        "schema": IDENTITY_SCHEMA,
        "repository": "rozkalnsandris/RPi5_main",
        "source_sha": expected_sha,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sysusers_bytes(expected_sha: str) -> bytes:
    for target in TRACKED_FILES:
        if target.source_path == "ops/sysusers/rozkalns-simple-deployer.conf":
            return _source_bytes(expected_sha, target)
    raise AssertionError("sysusers source target missing")


def _require_principal_preflight(expected_sha: str) -> None:
    try:
        pwd.getpwnam(RUNTIME_USER)
    except KeyError:
        pass
    else:
        _fail("runtime user already exists and requires separate reconciliation")
    try:
        grp.getgrnam(RUNTIME_GROUP)
    except KeyError:
        pass
    else:
        _fail("runtime primary group already exists and requires separate reconciliation")
    try:
        grp.getgrnam(DOCKER_GROUP)
    except KeyError:
        _fail("required existing docker group is absent")
    for tool in (GIT, SYSUSERS, NOLOGIN):
        try:
            info = os.stat(tool, follow_symlinks=False)
        except OSError:
            _fail(f"required fixed host tool is unavailable: {tool}")
        if not stat.S_ISREG(info.st_mode) or (info.st_mode & 0o111) == 0:
            _fail(f"required fixed host tool is not executable: {tool}")
    dry_run = _run((str(SYSUSERS), "--dry-run", "-"), cwd=ROOT, stdin=_sysusers_bytes(expected_sha))
    if dry_run.returncode != 0:
        _fail("systemd-sysusers dry-run rejected the reviewed principal declaration")


def _prepared_files(expected_sha: str) -> tuple[tuple[FileTarget, bytes], ...]:
    return tuple((target, _source_bytes(expected_sha, target)) for target in TRACKED_FILES)


def _preflight(expected_sha: str) -> tuple[tuple[FileTarget, bytes], ...]:
    _require_source_checkout(expected_sha)
    for path, mode in SHARED_PARENTS:
        _require_directory(path, mode)
    for path, _mode in DIRECTORY_TARGETS:
        _require_absent(path)
    prepared = _prepared_files(expected_sha)
    for target, _desired in prepared:
        _require_absent(target.target)
    _require_principal_preflight(expected_sha)
    return prepared


def _parent_mode(path: Path) -> int:
    for candidate, mode in SHARED_PARENTS + DIRECTORY_TARGETS:
        if candidate == path:
            return mode
    _fail(f"path parent is outside fixed installer set: {path}")
    raise AssertionError("unreachable")


def _create_directory(path: Path, mode: int) -> None:
    _require_directory(path.parent, _parent_mode(path.parent))
    try:
        os.mkdir(path, mode)
        os.chown(path, ROOT_UID, ROOT_GID)
        os.chmod(path, mode)
        info = os.lstat(path)
    except OSError as exc:
        _fail(f"directory materialization failed: {path}: {exc.strerror}")
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or stat.S_IMODE(info.st_mode) != mode:
        _fail(f"post-create directory metadata drifted: {path}")


def _write_file(target: FileTarget, desired: bytes) -> None:
    _require_directory(target.target.parent, _parent_mode(target.target.parent))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target.target, flags, 0o600)
    except OSError as exc:
        _fail(f"exclusive file materialization failed: {target.target}: {exc.strerror}")
    try:
        offset = 0
        view = memoryview(desired)
        while offset < len(desired):
            written = os.write(fd, view[offset:])
            if written <= 0:
                _fail(f"short write while materializing {target.target}")
            offset += written
        os.fsync(fd)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fchmod(fd, target.mode)
        info = os.fstat(fd)
        if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or stat.S_IMODE(info.st_mode) != target.mode:
            _fail(f"post-write metadata drifted: {target.target}")
    except OSError as exc:
        _fail(f"file finalization failed: {target.target}: {exc.strerror}")
    finally:
        os.close(fd)


def _verify_file(target: FileTarget, desired: bytes) -> None:
    try:
        before = os.lstat(target.target)
    except OSError as exc:
        _fail(f"installed target cannot be inspected: {target.target}: {exc.strerror}")
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        _fail(f"installed target type drifted: {target.target}")
    if before.st_uid != ROOT_UID or before.st_gid != ROOT_GID or stat.S_IMODE(before.st_mode) != target.mode:
        _fail(f"installed target metadata drifted: {target.target}")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_CLOEXEC"):
        _fail("required descriptor guards are unavailable")
    fd = os.open(target.target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            _fail(f"installed target changed before validation: {target.target}")
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
            _fail(f"installed target exceeds reviewed size: {target.target}")
        try:
            now = os.stat(target.target, follow_symlinks=False)
        except OSError as exc:
            _fail(f"installed target cannot be re-inspected safely: {target.target}: {exc.strerror}")
        if (now.st_dev, now.st_ino) != (opened.st_dev, opened.st_ino):
            _fail(f"installed target changed during validation: {target.target}")
    finally:
        os.close(fd)
    if data != desired or hashlib.sha256(data).digest() != hashlib.sha256(desired).digest():
        _fail(f"installed target content drifted: {target.target}")


def _verify_principal() -> None:
    try:
        user = pwd.getpwnam(RUNTIME_USER)
        primary = grp.getgrnam(RUNTIME_GROUP)
        docker = grp.getgrnam(DOCKER_GROUP)
    except KeyError:
        _fail("runtime principal provisioning did not materialize the expected account/groups")
    if user.pw_gid != primary.gr_gid or user.pw_dir != RUNTIME_HOME or user.pw_shell != RUNTIME_SHELL:
        _fail("runtime principal metadata drifted after provisioning")
    if RUNTIME_USER not in docker.gr_mem:
        _fail("runtime principal is not a member of the fixed docker group")


def _provision_principal() -> None:
    result = _run((str(SYSUSERS), str(TRACKED_FILES[0].target)), cwd=ROOT)
    if result.returncode != 0:
        _fail("systemd-sysusers principal provisioning failed")
    _verify_principal()


def _receipt(result: str, expected_sha: str, progress: Progress, *, reason: str | None = None) -> str:
    value = {
        "schema": "rozkalns.rpi5-main.simple-deploy.install-receipt.v1",
        "result": result,
        "source_sha": expected_sha,
        "directory_target_count": len(DIRECTORY_TARGETS),
        "file_target_count": len(TRACKED_FILES),
        "directories_materialized": progress.directories_materialized,
        "files_materialized": progress.files_materialized,
        "principal_provisioning_started": progress.principal_provisioning_started,
        "mutation_started": progress.mutation_started,
        "mutation_budget": [list(item) for item in INSTALL_MUTATION_BUDGET],
        "systemd_sysusers": str(SYSUSERS),
        "runtime_user": RUNTIME_USER,
        "runtime_group": RUNTIME_GROUP,
        "supplementary_group": DOCKER_GROUP,
        "daemon_reload_performed": False,
        "service_started": False,
        "timer_enabled_or_started": False,
        "docker_command_executed": False,
        "target_reconciliation_executed": False,
        "database_or_data_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }
    if reason is not None:
        value["reason"] = reason
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def preflight(expected_sha: str) -> str:
    _preflight(expected_sha)
    return _receipt("SIMPLE_DEPLOY_INSTALL_PREFLIGHT_READY", expected_sha, Progress())


def apply(expected_sha: str) -> str:
    if os.geteuid() != ROOT_UID:
        _fail("--apply requires root and a separate exact LIVE authorization")
    prepared = _preflight(expected_sha)
    progress = Progress()
    try:
        for path, mode in DIRECTORY_TARGETS:
            progress.mutation_started = True
            _create_directory(path, mode)
            progress.directories_materialized += 1
        for target, desired in prepared:
            progress.mutation_started = True
            _write_file(target, desired)
            progress.files_materialized += 1
        progress.mutation_started = True
        progress.principal_provisioning_started = True
        _provision_principal()
        for target, desired in prepared:
            _verify_file(target, desired)
    except SimpleDeployInstallerError as exc:
        raise ApplyFailure(str(exc), progress) from exc
    return _receipt("SIMPLE_DEPLOY_INSTALLED_NOT_ACTIVATED", expected_sha, progress)


def _phase_b_runtime_ids() -> tuple[int, int]:
    _verify_principal()
    user = pwd.getpwnam(RUNTIME_USER)
    primary = grp.getgrnam(RUNTIME_GROUP)
    return user.pw_uid, primary.gr_gid


def _require_phase_b_state_absent() -> None:
    for path in (PHASE_B_DOCKER_CONFIG, PHASE_B_STATE_ROOT):
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        _fail(f"Phase-B runtime state target already exists and requires separate reconciliation: {path}")


def _phase_b_changed_targets(expected_sha: str) -> tuple[tuple[FileTarget, bytes], ...]:
    changed: list[tuple[FileTarget, bytes]] = []
    for target in TRACKED_FILES:
        if target.source_path is None:
            continue
        before = _source_bytes_at(PHASE_B_REPAIR_BASE_SHA, target)
        after = _source_bytes_at(expected_sha, target)
        if before != after:
            if target.target != PHASE_B_SCHEMA_MODULE_TARGET:
                _fail(f"Phase-B repair scope would change an unauthorized installed target: {target.target}")
            changed.append((target, after))
    if tuple(target.target for target, _ in changed) != (PHASE_B_SCHEMA_MODULE_TARGET,):
        _fail("Phase-B repair requires exactly the reviewed schema-init module delta")
    return tuple(changed)


def _phase_b_repair_preflight(expected_sha: str) -> tuple[tuple[FileTarget, bytes], ...]:
    _require_source_checkout(expected_sha)
    if expected_sha == PHASE_B_REPAIR_BASE_SHA:
        _fail("Phase-B repair target source must advance beyond the installed Phase-A base")
    for path, mode in SHARED_PARENTS + DIRECTORY_TARGETS:
        _require_directory(path, mode)
    _phase_b_runtime_ids()
    for target in TRACKED_FILES:
        _verify_file(target, _source_bytes_at(PHASE_B_REPAIR_BASE_SHA, target))
    _require_phase_b_state_absent()
    return _phase_b_changed_targets(expected_sha)


def _create_phase_b_state_directory(path: Path, *, uid: int, gid: int) -> None:
    parent = path.parent
    if path == PHASE_B_STATE_ROOT:
        _require_directory(parent, 0o755)
    else:
        info = os.lstat(parent)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            _fail(f"Phase-B state parent is not a real directory: {parent}")
        if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != 0o700:
            _fail(f"Phase-B state parent metadata drifted: {parent}")
    try:
        os.mkdir(path, 0o700)
        os.chown(path, uid, gid)
        os.chmod(path, 0o700)
        info = os.lstat(path)
    except OSError as exc:
        _fail(f"Phase-B state directory materialization failed: {path}: {exc.strerror}")
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != 0o700:
        _fail(f"Phase-B state directory metadata drifted after materialization: {path}")


def _atomic_replace_file(target: FileTarget, desired: bytes) -> None:
    _require_directory(target.target.parent, _parent_mode(target.target.parent))
    temp = target.target.parent / f".{target.target.name}.phase-b-repair"
    _require_absent(temp)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(temp, flags, 0o600)
        try:
            view = memoryview(desired)
            offset = 0
            while offset < len(desired):
                written = os.write(fd, view[offset:])
                if written <= 0:
                    _fail(f"short write while reconciling {target.target}")
                offset += written
            os.fsync(fd)
            os.fchown(fd, ROOT_UID, ROOT_GID)
            os.fchmod(fd, target.mode)
        finally:
            os.close(fd)
        os.replace(temp, target.target)
        parent_fd = os.open(target.target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        _fail(f"Phase-B file reconciliation failed: {target.target}: {exc.strerror}")


def _phase_b_receipt(result: str, expected_sha: str, progress: Progress, *, reason: str | None = None) -> str:
    value = {
        "schema": "rozkalns.rpi5-main.simple-deploy.phase-b-repair.v1",
        "result": result,
        "base_source_sha": PHASE_B_REPAIR_BASE_SHA,
        "source_sha": expected_sha,
        "state_directories_materialized": progress.directories_materialized,
        "files_reconciled": progress.files_materialized,
        "mutation_started": progress.mutation_started,
        "runtime_user": RUNTIME_USER,
        "runtime_group": RUNTIME_GROUP,
        "docker_state_root": str(PHASE_B_STATE_ROOT),
        "docker_config": str(PHASE_B_DOCKER_CONFIG),
        "daemon_reload_performed": False,
        "service_started": False,
        "timer_enabled_or_started": False,
        "docker_command_executed": False,
        "target_reconciliation_executed": False,
        "database_or_data_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }
    if reason is not None:
        value["reason"] = reason
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def phase_b_repair_preflight(expected_sha: str) -> str:
    _phase_b_repair_preflight(expected_sha)
    return _phase_b_receipt("SIMPLE_DEPLOY_PHASE_B_REPAIR_PREFLIGHT_READY", expected_sha, Progress())


def phase_b_repair_apply(expected_sha: str) -> str:
    if os.geteuid() != ROOT_UID:
        _fail("Phase-B repair --apply requires root and a separate exact LIVE authorization")
    changed = _phase_b_repair_preflight(expected_sha)
    uid, gid = _phase_b_runtime_ids()
    progress = Progress()
    try:
        for path in (PHASE_B_STATE_ROOT, PHASE_B_DOCKER_CONFIG):
            progress.mutation_started = True
            _create_phase_b_state_directory(path, uid=uid, gid=gid)
            progress.directories_materialized += 1
        for target, desired in changed:
            progress.mutation_started = True
            _atomic_replace_file(target, desired)
            progress.files_materialized += 1
            _verify_file(target, desired)
        identity_target = next(target for target in TRACKED_FILES if target.source_path is None)
        progress.mutation_started = True
        _atomic_replace_file(identity_target, _identity_bytes(expected_sha))
        progress.files_materialized += 1
        for target in TRACKED_FILES:
            _verify_file(target, _source_bytes(expected_sha, target))
    except SimpleDeployInstallerError as exc:
        raise ApplyFailure(str(exc), progress) from exc
    return _phase_b_receipt("SIMPLE_DEPLOY_PHASE_B_REPAIRED_NOT_EXECUTED", expected_sha, progress)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed installer/reconciler for SIMPLE-DEPLOY v1")
    parser.add_argument("expected_source_sha")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--phase-b-repair", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.phase_b_repair:
            output = phase_b_repair_apply(args.expected_source_sha) if args.apply else phase_b_repair_preflight(args.expected_source_sha)
        else:
            output = apply(args.expected_source_sha) if args.apply else preflight(args.expected_source_sha)
    except ApplyFailure as exc:
        receipt = _phase_b_receipt if args.phase_b_repair else _receipt
        print(receipt("FAIL_CLOSED", args.expected_source_sha, exc.progress, reason=str(exc)), file=sys.stderr)
        return 1
    except SimpleDeployInstallerError as exc:
        receipt = _phase_b_receipt if args.phase_b_repair else _receipt
        print(receipt("FAIL_CLOSED", args.expected_source_sha, Progress(), reason=str(exc)), file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
