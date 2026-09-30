#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import pwd
import grp
import re
import stat
import subprocess
import sys
from typing import Sequence

GIT = Path("/usr/bin/git")
ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
INSTALLER_RELATIVE = "scripts/install-simple-deploy-weather-data-v1.py"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ROOT_UID = 0
ROOT_GID = 0
RUNTIME_USER = "rozkalns-simple-deployer"
RUNTIME_GROUP = "rozkalns-simple-deployer"
DOCKER_GROUP = "docker"
RUNTIME_HOME = "/var/lib/rozkalns-simple-deployer"
RUNTIME_SHELL = "/usr/sbin/nologin"
CAPABILITY_IDENTITY_SCHEMA = "rozkalns.rpi5-main.simple-deploy.weather-data.identity.v1"
BASE_LIBEXEC = Path("/usr/local/libexec/rozkalns-simple-deployer")
BASE_ETC = Path("/etc/rozkalns-simple-deployer")
SYSTEMD_DIR = Path("/etc/systemd/system")
BASE_REQUIRED_FILES = (
    (BASE_LIBEXEC / "rozkalns-simple-deployer", 0o555),
    (BASE_LIBEXEC / "simple_deploy_v1.py", 0o444),
    (BASE_LIBEXEC / "simple_deploy_weather_schema_init_v1.py", 0o444),
    (BASE_ETC / "targets.json", 0o444),
    (BASE_ETC / "identity.json", 0o444),
    (BASE_ETC / "compose" / "rozkalns-weather-public.yml", 0o444),
)


class WeatherDataInstallerError(RuntimeError):
    pass


@dataclass
class Progress:
    mutation_started: bool = False
    files_materialized: int = 0


class ApplyFailure(WeatherDataInstallerError):
    def __init__(self, message: str, progress: Progress):
        super().__init__(message)
        self.progress = progress


@dataclass(frozen=True)
class FileTarget:
    source_path: str | None
    target: Path
    mode: int


TRACKED_FILES = (
    FileTarget(
        "ops/bin/rozkalns-simple-deploy-weather-data",
        BASE_LIBEXEC / "rozkalns-simple-deploy-weather-data",
        0o555,
    ),
    FileTarget(
        "ops/lib/deploy_executor/simple_deploy_weather_data_v1.py",
        BASE_LIBEXEC / "simple_deploy_weather_data_v1.py",
        0o444,
    ),
    FileTarget(
        "ops/deploy/simple-deploy-weather-data-v1.json",
        BASE_ETC / "weather-data-v1.json",
        0o444,
    ),
    FileTarget(
        "ops/systemd/rozkalns-weather-public-ingest.service",
        SYSTEMD_DIR / "rozkalns-weather-public-ingest.service",
        0o644,
    ),
    FileTarget(
        "ops/systemd/rozkalns-weather-public-ingest.timer",
        SYSTEMD_DIR / "rozkalns-weather-public-ingest.timer",
        0o644,
    ),
    FileTarget(
        None,
        BASE_ETC / "weather-data-v1.identity.json",
        0o444,
    ),
)


def _fail(message: str) -> None:
    raise WeatherDataInstallerError(message)


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


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return _run((str(GIT), "-c", f"safe.directory={ROOT}", "-C", str(ROOT), *args), cwd=ROOT)


def _git_stdout(*args: str) -> bytes:
    result = _git(*args)
    if result.returncode != 0:
        _fail("Git source validation failed")
    return result.stdout


def _identity_bytes(expected_sha: str) -> bytes:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail("identity source SHA must be lowercase 40-character hex")
    value = {
        "schema": CAPABILITY_IDENTITY_SCHEMA,
        "repository": "rozkalnsandris/RPi5_main",
        "source_sha": expected_sha,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _source_bytes(expected_sha: str, target: FileTarget) -> bytes:
    if target.source_path is None:
        return _identity_bytes(expected_sha)
    return _git_stdout("show", f"{expected_sha}:{target.source_path}")


def _require_source_checkout(expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail("expected source SHA must be lowercase 40-character hex")
    if _git_stdout("rev-parse", "HEAD").decode("ascii").strip() != expected_sha:
        _fail("checkout HEAD does not match expected source SHA")
    if _git_stdout("remote", "get-url", "origin").decode("utf-8").strip() != ORIGIN:
        _fail("checkout origin drifted")
    if _git_stdout("status", "--porcelain=v1", "--untracked-files=all"):
        _fail("source checkout must be clean")
    if _git_stdout("show", f"{expected_sha}:{INSTALLER_RELATIVE}") != Path(__file__).read_bytes():
        _fail("installer working-tree bytes differ from expected source")


def _require_dir(path: Path, *, mode: int, uid: int, gid: int) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required directory absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(f"required path is not a real directory: {path}")
    if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
        _fail(f"required directory metadata drifted: {path}")


def _require_file(path: Path, mode: int) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required SIMPLE-DEPLOY base artifact absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail(f"required SIMPLE-DEPLOY base artifact type drifted: {path}")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or stat.S_IMODE(info.st_mode) != mode:
        _fail(f"required SIMPLE-DEPLOY base artifact metadata drifted: {path}")


def _require_absent(path: Path) -> None:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    _fail(f"Weather data capability target already exists and requires separate reconciliation: {path}")


def _require_principal() -> tuple[int, int]:
    try:
        user = pwd.getpwnam(RUNTIME_USER)
        primary = grp.getgrnam(RUNTIME_GROUP)
        docker = grp.getgrnam(DOCKER_GROUP)
    except KeyError:
        _fail("fixed SIMPLE-DEPLOY runtime principal is missing")
    if user.pw_gid != primary.gr_gid or user.pw_dir != RUNTIME_HOME or user.pw_shell != RUNTIME_SHELL:
        _fail("fixed SIMPLE-DEPLOY runtime principal metadata drifted")
    if RUNTIME_USER not in docker.gr_mem:
        _fail("fixed SIMPLE-DEPLOY runtime principal lacks docker group membership")
    return user.pw_uid, primary.gr_gid


def _prepared(expected_sha: str) -> tuple[tuple[FileTarget, bytes], ...]:
    _require_source_checkout(expected_sha)
    _require_dir(BASE_LIBEXEC, mode=0o755, uid=ROOT_UID, gid=ROOT_GID)
    _require_dir(BASE_ETC, mode=0o755, uid=ROOT_UID, gid=ROOT_GID)
    _require_dir(SYSTEMD_DIR, mode=0o755, uid=ROOT_UID, gid=ROOT_GID)
    _require_principal()
    for required, mode in BASE_REQUIRED_FILES:
        _require_file(required, mode)
    prepared = tuple((target, _source_bytes(expected_sha, target)) for target in TRACKED_FILES)
    for target, _ in prepared:
        _require_absent(target.target)
    return prepared


def _write_file(target: FileTarget, desired: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target.target, flags, 0o600)
    except OSError as exc:
        _fail(f"exclusive file materialization failed: {target.target}: {exc.strerror}")
    try:
        view = memoryview(desired)
        offset = 0
        while offset < len(desired):
            written = os.write(fd, view[offset:])
            if written <= 0:
                _fail(f"short write while materializing {target.target}")
            offset += written
        os.fsync(fd)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fchmod(fd, target.mode)
    except OSError as exc:
        _fail(f"file finalization failed: {target.target}: {exc.strerror}")
    finally:
        os.close(fd)


def _verify_file(target: FileTarget, desired: bytes) -> None:
    info = os.lstat(target.target)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail(f"installed target type drifted: {target.target}")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or stat.S_IMODE(info.st_mode) != target.mode:
        _fail(f"installed target metadata drifted: {target.target}")
    data = target.target.read_bytes()
    if data != desired or hashlib.sha256(data).digest() != hashlib.sha256(desired).digest():
        _fail(f"installed target content drifted: {target.target}")


def _receipt(result: str, source_sha: str, progress: Progress, *, reason: str | None = None) -> str:
    payload: dict[str, object] = {
        "schema": "rozkalns.rpi5-main.simple-deploy.weather-data.install-receipt.v1",
        "result": result,
        "source_sha": source_sha,
        "file_target_count": len(TRACKED_FILES),
        "files_materialized": progress.files_materialized,
        "mutation_started": progress.mutation_started,
        "daemon_reload_performed": False,
        "service_started": False,
        "timer_enabled_or_started": False,
        "docker_command_executed": False,
        "database_or_data_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }
    if reason is not None:
        payload["reason"] = reason
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def preflight(expected_sha: str) -> str:
    _prepared(expected_sha)
    return _receipt("WEATHER_DATA_INSTALL_PREFLIGHT_READY", expected_sha, Progress())


def apply(expected_sha: str) -> str:
    if os.geteuid() != ROOT_UID:
        _fail("--apply requires root and a separate exact LIVE authorization")
    prepared = _prepared(expected_sha)
    progress = Progress()
    try:
        for target, desired in prepared:
            progress.mutation_started = True
            _write_file(target, desired)
            progress.files_materialized += 1
            _verify_file(target, desired)
    except (WeatherDataInstallerError, OSError) as exc:
        raise ApplyFailure(str(exc), progress) from exc
    return _receipt("WEATHER_DATA_INSTALLED_DISABLED_NOT_EXECUTED", expected_sha, progress)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the fixed SIMPLE-DEPLOY Weather data companion without activation")
    parser.add_argument("expected_source_sha")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = apply(args.expected_source_sha) if args.apply else preflight(args.expected_source_sha)
    except ApplyFailure as exc:
        print(_receipt("FAIL_CLOSED", args.expected_source_sha, exc.progress, reason=str(exc)), file=sys.stderr)
        return 1
    except WeatherDataInstallerError as exc:
        print(_receipt("FAIL_CLOSED", args.expected_source_sha, Progress(), reason=str(exc)), file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
