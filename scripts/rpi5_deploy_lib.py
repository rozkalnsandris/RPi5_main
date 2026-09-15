#!/usr/bin/env python3
"""Shared safety gates for the RPi5_main controlled deploy command."""
from __future__ import annotations

import datetime as dt
import fcntl
import grp
import hashlib
import json
import os
import pathlib
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Iterable

EXPECTED_REPOSITORY = "rozkalnsandris/RPi5_main"
REMOTE_RE = re.compile(
    r"^(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)"
    r"rozkalnsandris/RPi5_main(?:\.git)?$"
)
PLAN_SCHEMA = "rpi5.controlled-deploy-plan.v1"
TRANSACTION_SCHEMA = "rpi5.controlled-deploy-transaction.v1"
ENGINE_SCHEMA = "rpi5.controlled-deploy-engine.v1"
ENGINE_RELEASES = pathlib.Path("/usr/local/libexec/rpi5-deploy/releases")
ENGINE_SOURCE_FILES = (
    "scripts/rpi5-deploy",
    "scripts/rpi5_deploy.py",
    "scripts/rpi5_deploy_lib.py",
    "scripts/rpi5_deploy_tx.py",
    "ops/deploy/targets.json",
)
ENGINE_INSTALLED_FILES = {
    "rpi5_deploy.py": "0500",
    "rpi5_deploy_lib.py": "0400",
    "rpi5_deploy_tx.py": "0400",
}
MAINTENANCE_PROCESS_PATTERNS = (
    r"(^|/)(rpi5-backup|backup\.sh)( |$)",
    r"(^|/)(update\.sh|rpi5-update)( |$)",
    r"(^|/)(apt-get|apt|dpkg)( |$)",
    r"(^|/)(unattended-upgrade|unattended-upgrades)( |$)",
)
PACKAGE_MANAGER_LOCKS = (
    "/var/lib/dpkg/lock-frontend",
    "/var/lib/dpkg/lock",
    "/var/cache/apt/archives/lock",
    "/var/lib/apt/lists/lock",
)
ATTEST_ONLY_TARGET_IDS = frozenset({
    "backup-runner",
    "backup-core",
    "maintenance-lock-lib",
})


class DeployError(RuntimeError):
    pass


def _inside(path: pathlib.Path, parent: pathlib.Path) -> bool:
    return path == parent or parent in path.parents


def _raw_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class Target:
    id: str
    source: str
    target: str
    owner: str
    group: str
    mode: int
    validators: tuple[str, ...]


class Context:
    def __init__(self) -> None:
        code_path = pathlib.Path(__file__).resolve()
        release_dir = code_path.parent
        self.installed_engine = (
            release_dir.parent == ENGINE_RELEASES
            and re.fullmatch(r"[0-9a-f]{40}", release_dir.name) is not None
        )
        self.engine_release = release_dir if self.installed_engine else None
        self.engine_config: dict[str, Any] | None = None
        if self.installed_engine:
            config_path = release_dir / "engine-source.json"
            info = config_path.lstat()
            if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or info.st_nlink != 1 or info.st_uid != 0
                    or stat.S_IMODE(info.st_mode) != 0o400):
                raise DeployError("installed deploy engine metadata is unsafe")
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if (config.get("schema") != ENGINE_SCHEMA
                    or config.get("installed_from_commit") != release_dir.name):
                raise DeployError("installed deploy engine metadata is invalid")
            repo = pathlib.Path(str(config.get("repo_path", "")))
            if not repo.is_absolute() or ".." in repo.parts:
                raise DeployError("installed deploy engine repository path is unsafe")
            self.repo = repo.resolve()
            self.engine_config = config
        else:
            self.repo = code_path.parents[1]

        requested_test = os.environ.get("RPI5_DEPLOY_TEST_MODE") == "1"
        if requested_test and self.installed_engine:
            raise DeployError("installed deploy engine never accepts test mode")
        if requested_test:
            sandbox_raw = os.environ.get("RPI5_DEPLOY_TEST_SANDBOX")
            root_raw = os.environ.get("RPI5_DEPLOY_ROOT")
            if not sandbox_raw or not root_raw:
                raise DeployError("test mode requires an explicit sandbox and fake root")
            sandbox = pathlib.Path(sandbox_raw).resolve()
            fake_root = pathlib.Path(root_raw).resolve()
            if sandbox == pathlib.Path("/") or fake_root == pathlib.Path("/"):
                raise DeployError("test mode may never target the real root filesystem")
            if not sandbox.is_dir() or not fake_root.is_dir():
                raise DeployError("test sandbox and fake root must already exist")
            state_dir = pathlib.Path(
                os.environ.get("RPI5_DEPLOY_STATE_DIR", str(sandbox / "state"))
            ).resolve()
            log_file = pathlib.Path(
                os.environ.get("RPI5_DEPLOY_LOG", str(sandbox / "deploy.log"))
            ).resolve()
            for candidate in (self.repo, fake_root, state_dir, log_file.parent):
                if not _inside(candidate, sandbox):
                    raise DeployError(f"test path escapes sandbox: {candidate}")
            self.test_mode = True
            self.test_sandbox = sandbox
            self.fake_root = fake_root
            self.state_dir = state_dir
            self.log_file = log_file
            self.max_plan_age = int(os.environ.get("RPI5_DEPLOY_MAX_PLAN_AGE", "300"))
        else:
            self.test_mode = False
            self.test_sandbox = None
            self.fake_root = pathlib.Path("/")
            self.state_dir = pathlib.Path("/var/lib/rpi5-deploy")
            self.log_file = pathlib.Path("/var/log/rpi5-deploy.log")
            self.max_plan_age = 1800
        if not 60 <= self.max_plan_age <= 3600:
            raise DeployError("plan lifetime must be between 60 and 3600 seconds")
        self.manifest_path = self.repo / "ops/deploy/targets.json"
        self.plan_path = self.state_dir / "plans/latest.json"
        self.lock_path = self.state_dir / "deploy.lock"
        self.latest_success_path = self.state_dir / "latest-success"
        repo_info = self.repo.stat()
        repo_uid = repo_info.st_uid
        self.deploy_user = pwd.getpwuid(repo_uid).pw_name
        if not self.test_mode and repo_uid == 0:
            raise DeployError("production repository must be owned by a non-root operator")
        if self.installed_engine:
            expected_uid = int(self.engine_config.get("repo_owner_uid", -1))
            if repo_uid != expected_uid:
                raise DeployError("repository owner changed after deploy engine installation")
        sudo_user = os.environ.get("SUDO_USER")
        if not self.test_mode and sudo_user:
            try:
                sudo_uid = pwd.getpwnam(sudo_user).pw_uid
            except KeyError as exc:
                raise DeployError(f"unknown SUDO_USER: {sudo_user}") from exc
            if sudo_uid != repo_uid:
                raise DeployError("SUDO_USER does not own the repository")

    def rooted(self, absolute: str) -> pathlib.Path:
        path = pathlib.PurePosixPath(absolute)
        if not path.is_absolute() or ".." in path.parts:
            raise DeployError(f"unsafe target path: {absolute}")
        return pathlib.Path(absolute) if self.fake_root == pathlib.Path("/") else self.fake_root.joinpath(*path.parts[1:])


CTX = Context()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: pathlib.Path) -> str:
    return _raw_sha256(path)


def fsync_dir(path: pathlib.Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_dir(path: pathlib.Path, *, root_owned: bool) -> os.stat_result:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise DeployError(f"unsafe directory: {path}")
    if root_owned and not CTX.test_mode and info.st_uid != 0:
        raise DeployError(f"directory is not root-owned: {path}")
    return info


def secure_dir(path: pathlib.Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    verify_dir(path, root_owned=True)
    os.chmod(path, mode)


def safe_target_parent(path: pathlib.Path) -> None:
    root = CTX.fake_root
    try:
        relative = path.parent.relative_to(root)
    except ValueError as exc:
        raise DeployError(f"target parent escapes root: {path.parent}") from exc
    current = root
    verify_dir(current, root_owned=not CTX.test_mode)
    for part in relative.parts:
        current = current / part
        verify_dir(current, root_owned=not CTX.test_mode)


def atomic_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    secure_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = pathlib.Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        fsync_dir(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def append_log(message: str) -> None:
    line = f"[{dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S%z')}] {message}"
    print(line)
    CTX.log_file.parent.mkdir(parents=True, exist_ok=True)
    verify_dir(CTX.log_file.parent, root_owned=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(CTX.log_file, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    if shutil.which("logger") and not CTX.test_mode:
        subprocess.run(["logger", "-t", "rpi5-deploy", "--", message], check=False)


def run(args: list[str], *, cwd: pathlib.Path | None = None, check: bool = True,
        capture: bool = True, timeout: int = 300, as_user: bool = False) -> subprocess.CompletedProcess[str]:
    command = list(args)
    if as_user and os.geteuid() == 0 and not CTX.test_mode:
        user = pwd.getpwnam(CTX.deploy_user)
        command = ["runuser", "-u", CTX.deploy_user, "--", "env", f"HOME={user.pw_dir}",
                   f"USER={CTX.deploy_user}", f"LOGNAME={CTX.deploy_user}",
                   "PATH=/usr/local/bin