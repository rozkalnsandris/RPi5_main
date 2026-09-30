#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v9-dispatch-caller-installer.json"
PACKAGE_ROOT = Path("/usr/local/libexec/rozkalns-weather-operator-v9-capability/deploy_executor")
BROKER_TARGET = Path("/usr/local/libexec/rozkalns-weather-operator-v9-privileged-broker")
CALLER_TARGET = Path("/usr/local/libexec/rozkalns-weather-operator-v9-dispatch-caller")
REGISTRATION = Path("/etc/rozkalns-weather-operator-v9-capability/registration.json")
SYSTEMD_ROOT = Path("/etc/systemd/system")
BROKER_SOCKET_NAME = "rozkalns-weather-operator-v9-privileged-broker.socket"
BROKER_SERVICE_NAME = "rozkalns-weather-operator-v9-privileged-broker@.service"
CALLER_SERVICE_NAME = "rozkalns-weather-operator-v9-dispatch-caller.service"
CALLER_TIMER_NAME = "rozkalns-weather-operator-v9-dispatch-caller.timer"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v9-host-capability-registration.v1"

ARTIFACTS = (
    ("ops/lib/deploy_executor/weather_operator_upgrade_v9_dispatch_caller.py",
     PACKAGE_ROOT / "weather_operator_upgrade_v9_dispatch_caller.py", 0o644),
    ("ops/bin/rozkalns-weather-operator-v9-dispatch-caller", CALLER_TARGET, 0o755),
    ("ops/systemd/rozkalns-weather-operator-v9-dispatch-caller.service",
     SYSTEMD_ROOT / CALLER_SERVICE_NAME, 0o644),
    ("ops/systemd/rozkalns-weather-operator-v9-dispatch-caller.timer",
     SYSTEMD_ROOT / CALLER_TIMER_NAME, 0o644),
)
PREREQUISITES = (
    ("ops/lib/deploy_executor/__init__.py", PACKAGE_ROOT / "__init__.py", 0o644),
    ("ops/lib/deploy_executor/dispatch_contract.py", PACKAGE_ROOT / "dispatch_contract.py", 0o644),
    ("ops/lib/deploy_executor/github_app_auth.py", PACKAGE_ROOT / "github_app_auth.py", 0o644),
    ("ops/lib/deploy_executor/p9_canary.py", PACKAGE_ROOT / "p9_canary.py", 0o644),
    ("ops/lib/deploy_executor/p9_isolated_auth_surface.py",
     PACKAGE_ROOT / "p9_isolated_auth_surface.py", 0o644),
    ("ops/lib/deploy_executor/p9_runtime.py", PACKAGE_ROOT / "p9_runtime.py", 0o644),
    ("ops/lib/deploy_executor/protocol.py", PACKAGE_ROOT / "protocol.py", 0o644),
    ("ops/lib/deploy_executor/queue_normalizer.py", PACKAGE_ROOT / "queue_normalizer.py", 0o644),
    ("ops/lib/deploy_executor/registry.py", PACKAGE_ROOT / "registry.py", 0o644),
    ("ops/lib/deploy_executor/state.py", PACKAGE_ROOT / "state.py", 0o644),
    ("ops/lib/deploy_executor/transport.py", PACKAGE_ROOT / "transport.py", 0o644),
    ("ops/lib/deploy_executor/weather_operator_upgrade_v9_host_capability.py",
     PACKAGE_ROOT / "weather_operator_upgrade_v9_host_capability.py", 0o644),
    ("ops/bin/rozkalns-weather-operator-v9-privileged-broker", BROKER_TARGET, 0o755),
    ("ops/systemd/rozkalns-weather-operator-v9-privileged-broker.socket",
     SYSTEMD_ROOT / BROKER_SOCKET_NAME, 0o644),
)


class InstallError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise InstallError(message)


def git_environment() -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
    if os.geteuid() == 0 and os.environ.get("SUDO_UID"):
        env["SUDO_UID"] = str(os.environ["SUDO_UID"])
    return env


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["/usr/bin/git", "-C", str(ROOT), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=git_environment(),
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise InstallError(f"git source preflight failed: {args[0] if args else 'git'}") from exc


def source_sha() -> str:
    sha = run_git("rev-parse", "HEAD").stdout.strip()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        fail("source HEAD is not exact lowercase SHA")
    if run_git("remote", "get-url", "origin").stdout.strip() != ORIGIN:
        fail("source origin drifted")
    if run_git("status", "--porcelain", "--untracked-files=all").stdout != "":
        fail("source checkout must be clean")
    return sha


def source_bytes(path: str) -> bytes:
    candidate = ROOT / path
    if not candidate.is_file():
        fail(f"required source artifact is absent: {path}")
    data = candidate.read_bytes()
    if not data:
        fail(f"required source artifact is empty: {path}")
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixed_file(path: Path, *, mode: int, expected: bytes | None = None, expected_sha: str | None = None) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise InstallError(f"required installed prerequisite is absent: {path}") from exc
    if not path.is_file() or path.is_symlink():
        fail(f"required installed prerequisite is not a regular file: {path}")
    if info.st_uid != 0 or info.st_gid != 0 or (info.st_mode & 0o777) != mode:
        fail(f"required installed prerequisite ownership/mode drifted: {path}")
    observed = sha256(path.read_bytes())
    if expected is not None and observed != sha256(expected):
        fail(f"required installed prerequisite hash drifted: {path}")
    if expected_sha is not None and observed != expected_sha:
        fail(f"required installed prerequisite registered hash drifted: {path}")


def load_registration(expected_source_sha: str) -> dict[str, object]:
    try:
        info = REGISTRATION.lstat()
        raw = REGISTRATION.read_bytes()
    except OSError as exc:
        raise InstallError("Weather v9 capability registration is unavailable") from exc
    if not REGISTRATION.is_file() or REGISTRATION.is_symlink():
        fail("Weather v9 capability registration is not a regular file")
    if info.st_uid != 0 or info.st_gid != 0 or (info.st_mode & 0o777) != 0o600:
        fail("Weather v9 capability registration metadata drifted")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstallError("Weather v9 capability registration is malformed") from exc
    required = {
        "schema", "capability_source_sha", "manager_checkout", "manager_uid", "manager_gid",
        "artifact_count", "module_sha256", "broker_sha256", "socket_sha256", "service_sha256",
    }
    if type(value) is not dict or set(value) != required:
        fail("Weather v9 capability registration fields drifted")
    if value["schema"] != REGISTRATION_SCHEMA or value["capability_source_sha"] != expected_source_sha:
        fail("Weather v9 capability registration source identity drifted")
    if value["artifact_count"] != 15:
        fail("Weather v9 capability registration artifact count drifted")
    return value


def systemctl_read(*args: str) -> str:
    result = subprocess.run(
        ["/usr/bin/systemctl", *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        check=False,
    )
    if result.returncode != 0:
        fail(f"systemd prerequisite check failed: {args[0] if args else 'systemctl'}")
    return result.stdout.strip()


def preflight() -> dict[str, object]:
    sha = source_sha()
    registration = load_registration(sha)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("schema") != "rozkalns.rpi5-main.weather-v9-dispatch-caller-installer.v1":
        fail("installer contract schema drifted")
    fixed_targets = contract.get("fixed_targets")
    if type(fixed_targets) is not dict or len(fixed_targets) != len(ARTIFACTS):
        fail("installer fixed target contract drifted")
    if not PACKAGE_ROOT.is_dir() or PACKAGE_ROOT.is_symlink():
        fail("installed Weather v9 capability package root is unavailable")

    for source, target, mode in PREREQUISITES:
        if source.endswith("weather_operator_upgrade_v9_host_capability.py"):
            fixed_file(target, mode=mode, expected_sha=str(registration["module_sha256"]))
        elif source.endswith("rozkalns-weather-operator-v9-privileged-broker"):
            fixed_file(target, mode=mode, expected_sha=str(registration["broker_sha256"]))
        elif source.endswith("privileged-broker.socket"):
            fixed_file(target, mode=mode, expected_sha=str(registration["socket_sha256"]))
        else:
            fixed_file(target, mode=mode, expected=source_bytes(source))

    fixed_file(
        SYSTEMD_ROOT / BROKER_SERVICE_NAME,
        mode=0o644,
        expected_sha=str(registration["service_sha256"]),
    )
    if systemctl_read("is-enabled", BROKER_SOCKET_NAME) != "enabled":
        fail("Weather v9 broker socket is not enabled")
    if systemctl_read("is-active", BROKER_SOCKET_NAME) != "active":
        fail("Weather v9 broker socket is not active")

    for source, target, mode in ARTIFACTS:
        source_bytes(source)
        if fixed_targets.get(str(target)) != format(mode, "04o"):
            fail(f"contract target/mode drifted: {target}")
        if target.exists() or target.is_symlink():
            fail(f"first-install caller target already exists: {target}")

    return {
        "schema": "rozkalns.rpi5-main.weather-v9-dispatch-caller-installer-preflight.v1",
        "result": "PASS",
        "source_sha": sha,
        "artifact_count": len(ARTIFACTS),
        "verified_prerequisite_artifact_count": len(PREREQUISITES) + 1,
        "broker_socket_enabled": True,
        "broker_socket_active": True,
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
                fail("caller installer write made no progress")
            view = view[written:]
        os.fsync(fd)
        os.fchmod(fd, mode)
        os.fchown(fd, 0, 0)
    finally:
        os.close(fd)


def systemctl_mutate(*args: str) -> None:
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
    mutation_started = False
    try:
        for source, target, mode in ARTIFACTS:
            write_exclusive(target, source_bytes(source), mode)
            mutation_started = True
        systemctl_mutate("daemon-reload")
        systemctl_mutate("enable", "--now", CALLER_TIMER_NAME)
    except Exception as exc:
        raise InstallError(
            "caller installation failed closed after mutation; no retry/cleanup/rollback is authorized"
        ) from exc
    return {
        "schema": "rozkalns.rpi5-main.weather-v9-dispatch-caller-install-receipt.v1",
        "result": "PASS",
        "source_sha": evidence["source_sha"],
        "artifact_count": len(ARTIFACTS),
        "verified_prerequisite_artifact_count": evidence["verified_prerequisite_artifact_count"],
        "host_mutation_started": mutation_started,
        "caller_installed": True,
        "caller_timer_enabled": True,
        "v7_capability_mutated": False,
        "broker_replaced": False,
        "socket_permissions_mutated": False,
        "operator_replaced": False,
        "v9_operator_checkout_created": False,
        "p8_mutation_dispatch_enabled": False,
        "global_executor_execution_enabled": False,
        "weather_runtime_mutated": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the fixed Weather v9 identity-only dispatch caller")
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
