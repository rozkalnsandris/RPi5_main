#!/usr/bin/env python3
"""Shared safety gates for the RPi5_main controlled deploy command."""
from __future__ import annotations

import datetime as dt
import fcntl
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
REMOTE_RE = re.compile(r"(?:github\.com[:/])rozkalnsandris/RPi5_main(?:\.git)?$")
PLAN_SCHEMA = "rpi5.controlled-deploy-plan.v1"
TRANSACTION_SCHEMA = "rpi5.controlled-deploy-transaction.v1"


class DeployError(RuntimeError):
    pass


def _inside(path: pathlib.Path, parent: pathlib.Path) -> bool:
    return path == parent or parent in path.parents


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
        self.repo = pathlib.Path(__file__).resolve().parents[1]
        requested_test = os.environ.get("RPI5_DEPLOY_TEST_MODE") == "1"
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
        repo_uid = self.repo.stat().st_uid
        self.deploy_user = pwd.getpwuid(repo_uid).pw_name
        if not self.test_mode and repo_uid == 0:
            raise DeployError("production repository must be owned by a non-root operator")
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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fsync_dir(path: pathlib.Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def secure_dir(path: pathlib.Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise DeployError(f"unsafe directory: {path}")
    if not CTX.test_mode and info.st_uid != 0:
        raise DeployError(f"deployment state directory is not root-owned: {path}")
    os.chmod(path, mode)


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
    secure_dir(CTX.log_file.parent, 0o755)
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
                   "PATH=/usr/local/bin:/usr/bin:/bin", *command]
    result = subprocess.run(command, cwd=cwd, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None,
                            timeout=timeout, check=False)
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise DeployError(f"command failed ({args[0]}): {detail[:1000]}")
    return result


def git(*args: str) -> str:
    return run(["git", *args], cwd=CTX.repo, as_user=True).stdout.strip()


def require_root() -> None:
    if os.geteuid() != 0 and not CTX.test_mode:
        raise DeployError("this command requires root; run it with sudo")


def require_normal_user() -> None:
    if os.geteuid() == 0 and not CTX.test_mode:
        raise DeployError("sync/test must run as the normal repository user")


def operation_lock() -> Any:
    secure_dir(CTX.state_dir)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(CTX.lock_path, flags, 0o600)
    handle = os.fdopen(descriptor, "a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise DeployError("another RPi5 deploy operation is active") from exc
    return handle


def read_manifest() -> tuple[list[Target], str]:
    safe_file(CTX.manifest_path)
    raw = CTX.manifest_path.read_bytes()
    data = json.loads(raw)
    if data.get("schema") != "rpi5.controlled-deploy-targets.v1":
        raise DeployError("unsupported target manifest schema")
    guards = data.get("reference_only", [])
    if not guards or guards[0].get("production_target") != "/etc/rpi5-backup.conf":
        raise DeployError("reference-only production configuration guard is missing")
    allowed = {"bash-n", "cron-contract", "logrotate-debug"}
    targets: list[Target] = []
    for item in data.get("targets", []):
        target = Target(item["id"], item["source"], item["target"], item["owner"],
                        item["group"], int(item["mode"], 8), tuple(item["validators"]))
        if pathlib.PurePosixPath(target.source).is_absolute() or ".." in pathlib.PurePosixPath(target.source).parts:
            raise DeployError(f"unsafe source path: {target.source}")
        if not target.target.startswith("/") or ".." in pathlib.PurePosixPath(target.target).parts:
            raise DeployError(f"unsafe target path: {target.target}")
        if not target.validators or not set(target.validators) <= allowed:
            raise DeployError(f"unsupported validator for {target.id}")
        if target.target == "/etc/rpi5-backup.conf":
            raise DeployError("production backup configuration is reference-only")
        targets.append(target)
    if len({t.id for t in targets}) != len(targets) or len({t.target for t in targets}) != len(targets):
        raise DeployError("duplicate target id or path")
    if {t.id for t in targets} != {"backup-runner", "backup-cron", "backup-logrotate"}:
        raise DeployError("V12 target set must remain exactly the approved V10 files")
    return targets, hashlib.sha256(raw).hexdigest()


def safe_file(path: pathlib.Path) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise DeployError(f"unsafe file: {path}")
    return info


def fingerprint(path: pathlib.Path) -> dict[str, Any]:
    try:
        info = safe_file(path)
    except FileNotFoundError:
        return {"exists": False, "sha256": None, "uid": None, "gid": None, "mode": None}
    return {"exists": True, "sha256": sha256_file(path), "uid": info.st_uid,
            "gid": info.st_gid, "mode": f"{stat.S_IMODE(info.st_mode):04o}"}


def validate_cron(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "\r" in text or not text.endswith("\n"):
        raise DeployError("cron file must use LF and end with newline")
    active = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    expected = ["SHELL=/bin/bash", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                'MAILTO=""', "0 2 * * * root /usr/local/sbin/rpi5-backup"]
    if active != expected:
        raise DeployError("cron file does not match the approved nightly backup contract")


def validate_target(target: Target, path: pathlib.Path) -> None:
    for validator in target.validators:
        if validator == "bash-n":
            run(["bash", "-n", str(path)])
        elif validator == "cron-contract":
            validate_cron(path)
        elif validator == "logrotate-debug":
            if not (CTX.test_mode and not shutil.which("logrotate")):
                run(["logrotate", "-d", str(path)], timeout=60)


def repository_preflight(*, validate: bool = True) -> dict[str, Any]:
    if CTX.test_mode:
        return {"branch": git("branch", "--show-current"), "head": git("rev-parse", "HEAD"), "remote": "test"}
    remote = git("remote", "get-url", "origin")
    if not REMOTE_RE.search(remote):
        raise DeployError(f"unexpected origin remote: {remote}")
    branch = git("branch", "--show-current")
    if branch != "main":
        raise DeployError(f"production plan requires branch main, found {branch or 'detached'}")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        raise DeployError("repository working tree is not clean")
    git("fetch", "--prune", "origin", "main")
    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    if head != origin:
        raise DeployError("local HEAD does not equal origin/main")
    if validate:
        run(["make", "validate"], cwd=CTX.repo, capture=False, timeout=1200, as_user=True)
    return {"branch": branch, "head": head, "origin_main": origin, "remote": remote}


def github_checks(commit: str) -> dict[str, Any]:
    if CTX.test_mode:
        return {"skipped": True, "reason": "sandbox test"}
    if not shutil.which("gh"):
        raise DeployError("GitHub CLI is required to verify exact-commit checks")
    endpoint = f"repos/{EXPECTED_REPOSITORY}/commits/{commit}/check-runs?per_page=100"
    data = json.loads(run(["gh", "api", endpoint], cwd=CTX.repo, timeout=120, as_user=True).stdout)
    checks = data.get("check_runs", [])
    if not checks:
        raise DeployError("no GitHub check runs found for exact commit")
    bad = [{"name": c.get("name"), "status": c.get("status"), "conclusion": c.get("conclusion")}
           for c in checks if c.get("status") != "completed" or c.get("conclusion") != "success"]
    if bad:
        raise DeployError(f"exact-commit GitHub checks are not all successful: {bad}")
    return {"count": len(checks), "names": sorted(str(c.get("name")) for c in checks)}


def ensure_no_conflicts() -> None:
    for pattern in (r"(^|/)(rpi5-backup|backup\.sh)( |$)", r"(^|/)(update\.sh|rpi5-update)( |$)",
                    r"apt-get|apt |dpkg|unattended-upgrade"):
        result = run(["pgrep", "-af", pattern], check=False)
        lines = [line for line in result.stdout.splitlines() if not line.startswith(f"{os.getpid()} ")]
        if lines:
            raise DeployError(f"conflicting maintenance process is active ({pattern})")
    if shutil.which("fuser"):
        for name in ("/var/lib/dpkg/lock-frontend", "/var/lib/dpkg/lock", "/var/cache/apt/archives/lock"):
            path = CTX.rooted(name)
            if path.exists() and run(["fuser", str(path)], check=False).returncode == 0:
                raise DeployError(f"package-manager lock is active: {name}")


def backup_age() -> int:
    pattern = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] Backup veiksmīgs:")
    stamp: dt.datetime | None = None
    path = CTX.rooted("/var/log/rpi5-backup.log")
    info = safe_file(path)
    with path.open("rb") as handle:
        handle.seek(max(0, info.st_size - 4 * 1024 * 1024))
        text = handle.read().decode("utf-8", "replace")
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            stamp = dt.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
    if stamp is None:
        raise DeployError("no recent sanitized successful backup marker found")
    return max(0, int((dt.datetime.now().astimezone() - stamp).total_seconds()))


def docker_health() -> dict[str, int]:
    baseline = CTX.repo / "baselines/runtime/current.json"
    safe_file(baseline)
    data = json.loads(baseline.read_text(encoding="utf-8"))
    expected = {c["name"]: c for c in data.get("docker", {}).get("containers", []) if c.get("state") == "running"}
    actual: dict[str, str] = {}
    for line in run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"], timeout=60).stdout.splitlines():
        name, separator, status_text = line.partition("\t")
        if not name or not separator:
            raise DeployError("unexpected docker ps health projection")
        actual[name] = status_text
    missing = sorted(set(expected) - set(actual))
    unhealthy = sorted(name for name, item in expected.items()
                       if item.get("health") == "healthy" and "(healthy)" not in actual.get(name, ""))
    if missing or unhealthy:
        raise DeployError(f"runtime baseline mismatch: missing={missing}, unhealthy={unhealthy}")
    return {"expected_running": len(expected), "observed_running": len(actual)}


def host_preflight() -> dict[str, Any]:
    if CTX.test_mode:
        return {"skipped": True, "reason": "sandbox test"}
    require_root()
    if os.uname().nodename != "rpi5":
        raise DeployError(f"unexpected hostname: {os.uname().nodename}")
    model = pathlib.Path("/proc/device-tree/model").read_bytes().rstrip(b"\0").decode("utf-8", "replace")
    release = pathlib.Path("/etc/os-release").read_text(encoding="utf-8")
    if "Raspberry Pi 5" not in model or 'ID=debian' not in release or 'VERSION_ID="12"' not in release:
        raise DeployError("expected Raspberry Pi 5 with Debian 12")
    if os.uname().machine not in {"aarch64", "arm64"}:
        raise DeployError(f"unexpected architecture: {os.uname().machine}")
    root_mount = next((line.split()[3] for line in pathlib.Path("/proc/mounts").read_text().splitlines()
                       if len(line.split()) >= 4 and line.split()[1] == "/"), "")
    if "rw" not in root_mount.split(","):
        raise DeployError("root filesystem is not read-write")
    usage, vfs = shutil.disk_usage("/"), os.statvfs("/")
    inode_pct = vfs.f_favail / vfs.f_files * 100 if vfs.f_files else 0
    mem_kib = next((int(line.split()[1]) for line in pathlib.Path("/proc/meminfo").read_text().splitlines()
                    if line.startswith("MemAvailable:")), 0)
    if usage.free < 2 * 1024**3 or inode_pct < 5 or mem_kib < 256 * 1024:
        raise DeployError("disk, inode or MemAvailable safety threshold failed")
    load1, limit = os.getloadavg()[0], max(4.0, (os.cpu_count() or 1) * 2.0)
    if load1 > limit:
        raise DeployError(f"load average is too high: {load1:.2f} > {limit:.2f}")
    temps = []
    for path in pathlib.Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            temps.append(int(path.read_text().strip()))
        except (OSError, ValueError):
            pass
    if temps and max(temps) > 80_000:
        raise DeployError(f"temperature is too high: {max(temps) / 1000:.1f} C")
    throttled = None
    if shutil.which("vcgencmd"):
        throttled = run(["vcgencmd", "get_throttled"], check=False).stdout.strip()
        if throttled and throttled != "throttled=0x0":
            raise DeployError(f"RPi throttling flag is not clear: {throttled}")
    ensure_no_conflicts()
    failed = run(["systemctl", "--failed", "--no-legend", "--plain"], check=False, timeout=30).stdout.strip()
    if failed:
        units = [line.split()[0].lstrip("●") for line in failed.splitlines() if line.split()]
        raise DeployError(f"failed systemd units present: {units}")
    if run(["systemctl", "is-active", "cron.service"], check=False).returncode:
        raise DeployError("cron.service is not active")
    age = backup_age()
    if age > 36 * 3600:
        raise DeployError(f"last successful encrypted backup is too old ({age // 3600}h)")
    return {"hostname": "rpi5", "model": model, "architecture": os.uname().machine,
            "disk_free_bytes": usage.free, "free_inode_percent": round(inode_pct, 2),
            "mem_available_kib": mem_kib, "load1": round(load1, 2),
            "temperature_millic": max(temps) if temps else None, "throttled": throttled,
            "backup_age_seconds": age, "runtime": docker_health()}


def target_plan(targets: Iterable[Target]) -> list[dict[str, Any]]:
    rows = []
    for target in targets:
        source = (CTX.repo / target.source).resolve()
        if CTX.repo not in source.parents:
            raise DeployError(f"source escapes repository: {target.source}")
        safe_file(source)
        if not CTX.test_mode:
            git("ls-files", "--error-unmatch", "--", target.source)
        validate_target(target, source)
        before, source_sha = fingerprint(CTX.rooted(target.target)), sha256_file(source)
        rows.append({"id": target.id, "source": target.source, "target": target.target,
                     "source_sha256": source_sha, "before": before, "owner": target.owner,
                     "group": target.group, "mode": f"{target.mode:04o}",
                     "validators": list(target.validators),
                     "action": "unchanged" if before["sha256"] == source_sha else "replace"})
    return rows


def build_plan(*, write: bool) -> dict[str, Any]:
    targets, manifest_sha = read_manifest()
    repo = repository_preflight(validate=True)
    created_epoch = int(time.time())
    payload = {"schema": PLAN_SCHEMA, "repository": EXPECTED_REPOSITORY, "commit": repo["head"],
               "short_commit": repo["head"][:12], "created_at": now_iso(),
               "created_epoch": created_epoch, "expires_epoch": created_epoch + CTX.max_plan_age,
               "manifest_sha256": manifest_sha, "repository_preflight": repo,
               "github_checks": github_checks(repo["head"]), "host_preflight": host_preflight(),
               "targets": target_plan(targets)}
    if write:
        atomic_json(CTX.plan_path, payload)
        append_log(f"PLAN PASS commit={payload['short_commit']} changed={sum(r['action'] == 'replace' for r in payload['targets'])} plan={CTX.plan_path}")
    return payload


def load_plan() -> dict[str, Any]:
    safe_file(CTX.plan_path)
    data = json.loads(CTX.plan_path.read_text(encoding="utf-8"))
    if data.get("schema") != PLAN_SCHEMA or data.get("repository") != EXPECTED_REPOSITORY:
        raise DeployError("invalid deploy plan")
    if int(data.get("expires_epoch", 0)) < int(time.time()):
        raise DeployError("deploy plan expired; run plan again and review it")
    return data


def verify_plan_targets(plan: dict[str, Any]) -> None:
    targets, manifest_sha = read_manifest()
    if plan.get("manifest_sha256") != manifest_sha:
        raise DeployError("manifest changed after plan creation")
    planned = {row["id"]: row for row in plan["targets"]}
    if set(planned) != {target.id for target in targets}:
        raise DeployError("planned target set does not equal the manifest")
    for target in targets:
        row = planned[target.id]
        if sha256_file(CTX.repo / target.source) != row["source_sha256"]:
            raise DeployError(f"source changed after plan: {target.id}")
        if fingerprint(CTX.rooted(target.target)) != row["before"]:
            raise DeployError(f"live target changed after plan: {target.id}")
