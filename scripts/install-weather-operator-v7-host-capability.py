#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v7-host-capability-installer.json"
TARGET_ROOT = Path("/usr/local/libexec/rozkalns-weather-operator-v7-capability")
PACKAGE_ROOT = TARGET_ROOT / "deploy_executor"
BROKER_TARGET = Path("/usr/local/libexec/rozkalns-weather-operator-v7-privileged-broker")
CONFIG_ROOT = Path("/etc/rozkalns-weather-operator-v7-capability")
REGISTRATION = CONFIG_ROOT / "registration.json"
STATE_ROOT = Path("/var/lib/rozkalns-weather-operator-v7-capability")
STATE_DB = STATE_ROOT / "state.sqlite3"
SYSTEMD_ROOT = Path("/etc/systemd/system")
SOCKET_NAME = "rozkalns-weather-operator-v7-privileged-broker.socket"
SERVICE_NAME = "rozkalns-weather-operator-v7-privileged-broker@.service"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
MAX_UID = (1 << 32) - 2
REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-registration.v2"
ARTIFACTS = (
    ("ops/lib/deploy_executor/__init__.py", PACKAGE_ROOT / "__init__.py", 0o644),
    ("ops/lib/deploy_executor/dispatch_contract.py", PACKAGE_ROOT / "dispatch_contract.py", 0o644),
    ("ops/lib/deploy_executor/github_app_auth.py", PACKAGE_ROOT / "github_app_auth.py", 0o644),
    ("ops/lib/deploy_executor/p9_canary.py", PACKAGE_ROOT / "p9_canary.py", 0o644),
    ("ops/lib/deploy_executor/p9_isolated_auth_surface.py", PACKAGE_ROOT / "p9_isolated_auth_surface.py", 0o644),
    ("ops/lib/deploy_executor/p9_runtime.py", PACKAGE_ROOT / "p9_runtime.py", 0o644),
    ("ops/lib/deploy_executor/protocol.py", PACKAGE_ROOT / "protocol.py", 0o644),
    ("ops/lib/deploy_executor/queue_normalizer.py", PACKAGE_ROOT / "queue_normalizer.py", 0o644),
    ("ops/lib/deploy_executor/registry.py", PACKAGE_ROOT / "registry.py", 0o644),
    ("ops/lib/deploy_executor/state.py", PACKAGE_ROOT / "state.py", 0o644),
    ("ops/lib/deploy_executor/transport.py", PACKAGE_ROOT / "transport.py", 0o644),
    ("ops/lib/deploy_executor/weather_operator_upgrade_v7_host_capability.py", PACKAGE_ROOT / "weather_operator_upgrade_v7_host_capability.py", 0o644),
    ("ops/bin/rozkalns-weather-operator-v7-privileged-broker", BROKER_TARGET, 0o755),
    ("ops/systemd/rozkalns-weather-operator-v7-privileged-broker.socket", SYSTEMD_ROOT / SOCKET_NAME, 0o644),
    ("ops/systemd/rozkalns-weather-operator-v7-privileged-broker@.service", SYSTEMD_ROOT / SERVICE_NAME, 0o644),
)


class InstallError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise InstallError(message)


def git_environment() -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
    if os.geteuid() != 0:
        return env
    sudo_uid = os.environ.get("SUDO_UID")
    if sudo_uid is None:
        return env
    if not sudo_uid.isascii() or not sudo_uid.isdecimal():
        fail("SUDO_UID must be an ASCII decimal UID")
    uid = int(sudo_uid, 10)
    if uid > MAX_UID:
        fail("SUDO_UID is outside the supported uid_t range")
    env["SUDO_UID"] = str(uid)
    return env


def run_git_at(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["/usr/bin/git", "-C", str(repo), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=git_environment(),
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        command = args[0] if args else "git"
        raise InstallError(f"git source preflight failed: {command}") from exc


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_git_at(ROOT, *args, check=check)


def canonical_manager_checkout() -> Path:
    raw = run_git("rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    if not raw.startswith("/"):
        fail("Git common directory is not absolute")
    try:
        common = Path(raw).resolve(strict=True)
    except OSError as exc:
        raise InstallError("Git common directory cannot be resolved") from exc
    if common.name != ".git":
        fail("Git common directory is not the primary RPi5_main .git directory")
    manager = common.parent
    if manager.name != "RPi5_main" or not manager.is_dir():
        fail("canonical RPi5_main manager checkout identity drifted")
    manager_common_raw = run_git_at(
        manager, "rev-parse", "--path-format=absolute", "--git-common-dir"
    ).stdout.strip()
    try:
        manager_common = Path(manager_common_raw).resolve(strict=True)
    except OSError as exc:
        raise InstallError("canonical manager Git directory cannot be resolved") from exc
    if manager_common != common:
        fail("linked worktree does not resolve to the canonical RPi5_main manager checkout")
    origin = run_git_at(manager, "remote", "get-url", "origin").stdout.strip()
    if origin != ORIGIN:
        fail("canonical manager checkout origin drifted")
    return manager


def manager_identity(manager: Path) -> tuple[int, int]:
    try:
        info = manager.lstat()
    except OSError as exc:
        raise InstallError("canonical manager checkout metadata is unavailable") from exc
    if not stat.S_ISDIR(info.st_mode) or manager.is_symlink():
        fail("canonical manager checkout must be a real directory")
    uid = info.st_uid
    gid = info.st_gid
    if type(uid) is not int or type(gid) is not int or not (0 < uid <= MAX_UID) or not (0 < gid <= MAX_UID):
        fail("canonical manager checkout owner identity is invalid")
    home = manager.parent
    try:
        home_info = home.lstat()
    except OSError as exc:
        raise InstallError("canonical manager home metadata is unavailable") from exc
    if not stat.S_ISDIR(home_info.st_mode) or home.is_symlink() or home_info.st_uid != uid:
        fail("canonical manager home owner identity drifted")
    return uid, gid


def source_sha() -> str:
    sha = run_git("rev-parse", "HEAD").stdout.strip()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        fail("source HEAD is not exact lowercase SHA")
    origin = run_git("remote", "get-url", "origin").stdout.strip()
    if origin != ORIGIN:
        fail("source origin drifted")
    if run_git("status", "--porcelain", "--untracked-files=all").stdout != "":
        fail("source checkout must be clean")
    return sha


def source_bytes(path: str) -> bytes:
    source = ROOT / path
    if not source.is_file():
        fail(f"required source artifact is absent: {path}")
    data = source.read_bytes()
    if not data:
        fail(f"required source artifact is empty: {path}")
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def preflight() -> dict[str, object]:
    sha = source_sha()
    manager = canonical_manager_checkout()
    manager_uid, manager_gid = manager_identity(manager)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("schema") != "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-installer.v1":
        fail("installer contract schema drifted")
    if contract.get("artifact_count") != len(ARTIFACTS):
        fail("installer artifact count drifted")
    for source, target, mode in ARTIFACTS:
        source_bytes(source)
        if str(target) not in contract["fixed_targets"]:
            fail(f"contract does not bind fixed target: {target}")
        if contract["fixed_targets"][str(target)] != format(mode, "04o"):
            fail(f"contract mode drifted for {target}")
    for target in [
        TARGET_ROOT,
        BROKER_TARGET,
        CONFIG_ROOT,
        REGISTRATION,
        SYSTEMD_ROOT / SOCKET_NAME,
        SYSTEMD_ROOT / SERVICE_NAME,
        STATE_ROOT,
        STATE_DB,
    ]:
        if target.exists():
            fail(f"first-install target already exists: {target}")
    return {
        "schema": "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-installer-preflight.v2",
        "result": "PASS",
        "source_sha": sha,
        "manager_checkout": str(manager),
        "manager_uid": manager_uid,
        "manager_gid": manager_gid,
        "artifact_count": len(ARTIFACTS),
        "host_mutation_started": False,
        "source_merge_authorizes_live": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def write_exclusive(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                fail("installer write made no progress")
            view = view[written:]
        os.fsync(fd)
        os.fchmod(fd, mode)
        os.fchown(fd, 0, 0)
    finally:
        os.close(fd)


def bootstrap_state() -> None:
    sys.path.insert(0, str(ROOT / "ops/lib"))
    from deploy_executor.state import StateStore

    STATE_ROOT.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chown(STATE_ROOT, 0, 0)
    with StateStore(STATE_DB, bootstrap=True):
        pass
    os.chown(STATE_DB, 0, 0)
    os.chmod(STATE_DB, 0o600)


def systemctl(*args: str) -> None:
    subprocess.run(
        ["/usr/bin/systemctl", *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        check=True,
    )


def apply() -> dict[str, object]:
    if os.geteuid() != 0:
        fail("--apply requires an owner-authorized root process")
    evidence = preflight()
    sha = str(evidence["source_sha"])
    manager = str(evidence["manager_checkout"])
    manager_uid = int(evidence["manager_uid"])
    manager_gid = int(evidence["manager_gid"])
    mutation_started = False
    try:
        TARGET_ROOT.mkdir(parents=True, exist_ok=False, mode=0o755)
        os.chown(TARGET_ROOT, 0, 0)
        PACKAGE_ROOT.mkdir(parents=True, exist_ok=False, mode=0o755)
        os.chown(PACKAGE_ROOT, 0, 0)
        CONFIG_ROOT.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chown(CONFIG_ROOT, 0, 0)
        mutation_started = True

        hashes: dict[str, str] = {}
        for source, target, mode in ARTIFACTS:
            data = source_bytes(source)
            write_exclusive(target, data, mode)
            hashes[str(target)] = sha256(data)

        bootstrap_state()
        registration = {
            "schema": REGISTRATION_SCHEMA,
            "capability_source_sha": sha,
            "manager_checkout": manager,
            "manager_uid": manager_uid,
            "manager_gid": manager_gid,
            "artifact_count": len(ARTIFACTS),
            "module_sha256": hashes[str(PACKAGE_ROOT / "weather_operator_upgrade_v7_host_capability.py")],
            "broker_sha256": hashes[str(BROKER_TARGET)],
            "socket_sha256": hashes[str(SYSTEMD_ROOT / SOCKET_NAME)],
            "service_sha256": hashes[str(SYSTEMD_ROOT / SERVICE_NAME)],
        }
        write_exclusive(
            REGISTRATION,
            json.dumps(registration, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
            0o600,
        )
        systemctl("daemon-reload")
        systemctl("enable", "--now", SOCKET_NAME)
    except Exception as exc:
        raise InstallError(
            "host-capability installation failed closed after mutation; no retry/cleanup/rollback is authorized"
        ) from exc

    return {
        "schema": "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-install-receipt.v2",
        "result": "PASS",
        "source_sha": sha,
        "manager_checkout": manager,
        "manager_uid": manager_uid,
        "manager_gid": manager_gid,
        "artifact_count": len(ARTIFACTS),
        "host_mutation_started": mutation_started,
        "capability_installed": True,
        "socket_enabled": True,
        "p8_mutation_dispatch_enabled": False,
        "global_executor_execution_enabled": False,
        "weather_runtime_mutated": False,
        "operator_replaced": False,
        "v7_checkout_created": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the fixed Weather v7 privileged host capability")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = apply() if args.apply else preflight()
    except InstallError as exc:
        print(json.dumps({"result": "FAIL_CLOSED", "reason": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 78
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
