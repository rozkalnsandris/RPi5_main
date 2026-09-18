#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_v9_capability_refresh as refresh

ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
CONTRACT = ROOT / "ops/deploy/weather-operator-v9-capability-refresh.json"
BROKER_SOURCE = "ops/bin/rozkalns-weather-operator-v9-privileged-broker"
MODULE_SOURCE = "ops/lib/deploy_executor/weather_operator_upgrade_v9_host_capability.py"
SOCKET_SOURCE = "ops/systemd/rozkalns-weather-operator-v9-privileged-broker.socket"
SERVICE_SOURCE = "ops/systemd/rozkalns-weather-operator-v9-privileged-broker@.service"
SERVICE_MANAGER_PARENT_TOKEN = b"@@WEATHER_V9_MANAGER_PARENT@@"
SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-operator-v9-capability")
BROKER_TARGET = Path("/usr/local/libexec/rozkalns-weather-operator-v9-privileged-broker")
REGISTRATION = Path("/etc/rozkalns-weather-operator-v9-capability/registration.json")
STATE_DB = Path("/var/lib/rozkalns-weather-operator-v9-capability/state.sqlite3")
SOCKET_TARGET = Path("/etc/systemd/system/rozkalns-weather-operator-v9-privileged-broker.socket")
SERVICE_TARGET = Path("/etc/systemd/system/rozkalns-weather-operator-v9-privileged-broker@.service")
MODULE_TARGET = SUPPORT_ROOT / "deploy_executor/weather_operator_upgrade_v9_host_capability.py"
BROKER_TEMP = BROKER_TARGET.with_name(".rozkalns-weather-operator-v9-privileged-broker.refresh.tmp")
REGISTRATION_TEMP = REGISTRATION.with_name(".registration.json.refresh.tmp")
GIT_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}


class CapabilityRefreshOperatorError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise CapabilityRefreshOperatorError(message)


def root_git_argv(*args: str) -> list[str]:
    return [
        "/usr/bin/git",
        "-c",
        f"safe.directory={ROOT}",
        "-C",
        str(ROOT),
        *args,
    ]


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            root_git_argv(*args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=GIT_ENV,
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        command = args[0] if args else "git"
        raise CapabilityRefreshOperatorError(f"git source preflight failed: {command}") from exc


def source_sha() -> str:
    sha = run_git("rev-parse", "HEAD").stdout.strip()
    if refresh.SHA40_RE.fullmatch(sha) is None:
        fail("source HEAD is not an exact lowercase SHA")
    if run_git("remote", "get-url", "origin").stdout.strip() != ORIGIN:
        fail("source origin drifted")
    if run_git("status", "--porcelain", "--untracked-files=all").stdout != "":
        fail("source checkout must be clean")
    ancestor = run_git(
        "merge-base", "--is-ancestor", refresh.PREDECESSOR_SOURCE_SHA, sha, check=False
    )
    if ancestor.returncode != 0:
        fail("source no longer descends from the reviewed predecessor")
    return sha


def git_blob(commit: str, path: str) -> bytes:
    if refresh.SHA40_RE.fullmatch(commit) is None:
        fail("fixed source commit is invalid")
    result = subprocess.run(
        root_git_argv("show", f"{commit}:{path}"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=GIT_ENV,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        fail(f"fixed source blob is unavailable: {path}")
    return result.stdout


def require_executable_git_mode(commit: str, path: str) -> None:
    row = run_git("ls-tree", commit, "--", path).stdout.strip()
    if not row.startswith("100755 blob "):
        fail(f"source executable mode drifted: {path}")


def render_service(data: bytes, manager: Path) -> bytes:
    if data.count(SERVICE_MANAGER_PARENT_TOKEN) != 1:
        fail("broker service manager-parent placeholder drifted")
    parent = str(manager.parent)
    if not parent.startswith("/") or any(ch.isspace() for ch in parent):
        fail("registered manager parent cannot be rendered safely")
    if any(ch in parent for ch in ('%', '"', "'", "\\")):
        fail("registered manager parent contains unsupported systemd path characters")
    return data.replace(SERVICE_MANAGER_PARENT_TOKEN, parent.encode("utf-8"), 1)


def safe_file(path: Path, *, mode: int, max_bytes: int) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise CapabilityRefreshOperatorError(f"required target is unavailable: {path.name}") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != 0
        or before.st_gid != 0
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_size < 1
        or before.st_size > max_bytes
    ):
        fail(f"required target metadata drifted: {path.name}")
    data = path.read_bytes()
    after = path.lstat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        fail(f"required target changed while being read: {path.name}")
    return data


def state_snapshot() -> tuple[int, int, int, int, int, int, int, int]:
    try:
        meta = STATE_DB.lstat()
    except OSError as exc:
        raise CapabilityRefreshOperatorError("durable replay/state database is unavailable") from exc
    if (
        not stat.S_ISREG(meta.st_mode)
        or stat.S_ISLNK(meta.st_mode)
        or meta.st_nlink != 1
        or meta.st_uid != 0
        or meta.st_gid != 0
        or stat.S_IMODE(meta.st_mode) != 0o600
    ):
        fail("durable replay/state database metadata drifted")
    return (
        meta.st_dev,
        meta.st_ino,
        meta.st_size,
        meta.st_mtime_ns,
        meta.st_ctime_ns,
        meta.st_uid,
        meta.st_gid,
        stat.S_IMODE(meta.st_mode),
    )


def load_registration() -> dict[str, Any]:
    raw = safe_file(REGISTRATION, mode=0o600, max_bytes=64 * 1024)
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CapabilityRefreshOperatorError("registration JSON is malformed") from exc
    try:
        return refresh.validate_registration(value)
    except refresh.WeatherV9CapabilityRefreshError as exc:
        raise CapabilityRefreshOperatorError(str(exc)) from exc


def artifact_hashes(commit: str, manager: Path) -> dict[str, str]:
    require_executable_git_mode(commit, BROKER_SOURCE)
    return {
        "module_sha256": refresh.sha256(git_blob(commit, MODULE_SOURCE)),
        "broker_sha256": refresh.sha256(git_blob(commit, BROKER_SOURCE)),
        "socket_sha256": refresh.sha256(git_blob(commit, SOCKET_SOURCE)),
        "service_sha256": refresh.sha256(render_service(git_blob(commit, SERVICE_SOURCE), manager)),
    }


def installed_hashes() -> dict[str, str]:
    return {
        "module_sha256": refresh.sha256(safe_file(MODULE_TARGET, mode=0o644, max_bytes=2 * 1024 * 1024)),
        "broker_sha256": refresh.sha256(safe_file(BROKER_TARGET, mode=0o755, max_bytes=2 * 1024 * 1024)),
        "socket_sha256": refresh.sha256(safe_file(SOCKET_TARGET, mode=0o644, max_bytes=256 * 1024)),
        "service_sha256": refresh.sha256(safe_file(SERVICE_TARGET, mode=0o644, max_bytes=256 * 1024)),
    }


def validate_contract() -> None:
    try:
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityRefreshOperatorError("refresh contract is unavailable or malformed") from exc
    expected_targets = {
        "broker": str(BROKER_TARGET),
        "registration": str(REGISTRATION),
        "state_db": str(STATE_DB),
    }
    observed_budget = tuple(
        (item.get("category"), item.get("max_operations"))
        for item in value.get("mutation_budget", [])
        if type(item) is dict
    )
    if (
        value.get("schema") != "rozkalns.rpi5-main.weather-operator-v9-capability-refresh.v1"
        or value.get("predecessor_source_sha") != refresh.PREDECESSOR_SOURCE_SHA
        or value.get("fixed_targets") != expected_targets
        or observed_budget != refresh.MUTATION_BUDGET
        or value.get("state_db_policy") != "PRESERVE_EXISTING_UNCHANGED"
        or value.get("automatic_retry") is not False
        or value.get("automatic_cleanup") is not False
        or value.get("automatic_rollback") is not False
    ):
        fail("refresh contract drifted")


def preflight_material() -> tuple[refresh.RefreshPlan, bytes, bytes, tuple[int, ...]]:
    validate_contract()
    sha = source_sha()
    registration = load_registration()
    manager = Path(str(registration["manager_checkout"]))
    if not manager.is_absolute() or manager.name != "RPi5_main":
        fail("registered manager checkout identity drifted")
    predecessor = artifact_hashes(refresh.PREDECESSOR_SOURCE_SHA, manager)
    target = artifact_hashes(sha, manager)
    installed = installed_hashes()
    before_state = state_snapshot()
    try:
        plan = refresh.build_refresh_plan(
            source_sha=sha,
            registration=registration,
            predecessor_hashes=predecessor,
            installed_hashes=installed,
            target_hashes=target,
            state_db_present=True,
            temp_paths_absent=not (
                BROKER_TEMP.exists()
                or BROKER_TEMP.is_symlink()
                or REGISTRATION_TEMP.exists()
                or REGISTRATION_TEMP.is_symlink()
            ),
        )
    except refresh.WeatherV9CapabilityRefreshError as exc:
        raise CapabilityRefreshOperatorError(str(exc)) from exc
    broker_bytes = git_blob(sha, BROKER_SOURCE)
    registration_bytes = refresh.registration_bytes(plan.new_registration)
    return plan, broker_bytes, registration_bytes, before_state


def preflight() -> dict[str, object]:
    plan, _broker, _registration, _state = preflight_material()
    return {
        "schema": "rozkalns.rpi5-main.weather-operator-v9-capability-refresh-preflight.v1",
        "result": "PASS",
        "source_sha": plan.source_sha,
        "predecessor_source_sha": plan.predecessor_source_sha,
        "mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in plan.mutation_budget
        ],
        "state_db_policy": plan.state_db_policy,
        "host_mutation_started": False,
        "systemd_mutation": False,
        "queue_or_live_auth_created": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def write_stage(path: Path, data: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                fail("refresh staging write made no progress")
            view = view[written:]
        os.fchmod(fd, mode)
        os.fchown(fd, 0, 0)
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def apply() -> dict[str, object]:
    if os.geteuid() != 0:
        fail("--apply requires a separately owner-authorized root process")
    plan, broker_bytes, registration_bytes, before_state = preflight_material()
    mutation_started = False
    try:
        write_stage(BROKER_TEMP, broker_bytes, 0o755)
        mutation_started = True
        write_stage(REGISTRATION_TEMP, registration_bytes, 0o600)
        os.replace(BROKER_TEMP, BROKER_TARGET)
        fsync_directory(BROKER_TARGET.parent)
        os.replace(REGISTRATION_TEMP, REGISTRATION)
        fsync_directory(REGISTRATION.parent)

        observed = installed_hashes()
        for key in refresh.ARTIFACT_KEYS:
            if observed[key] != plan.new_registration[key]:
                fail(f"post-refresh installed identity drifted: {key}")
        if safe_file(REGISTRATION, mode=0o600, max_bytes=64 * 1024) != registration_bytes:
            fail("post-refresh registration identity drifted")
        if state_snapshot() != before_state:
            fail("durable replay/state database changed during capability refresh")
    except Exception as exc:
        raise CapabilityRefreshOperatorError(
            "capability refresh failed closed after mutation; no retry/cleanup/rollback is authorized"
        ) from exc

    return {
        "schema": "rozkalns.rpi5-main.weather-operator-v9-capability-refresh-receipt.v1",
        "result": "PASS",
        "source_sha": plan.source_sha,
        "predecessor_source_sha": plan.predecessor_source_sha,
        "host_mutation_started": mutation_started,
        "broker_replaced": True,
        "registration_rebound": True,
        "state_db_preserved": True,
        "systemd_mutation": False,
        "queue_or_live_auth_created": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Weather v9 post-recovery capability refresh")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = apply() if args.apply else preflight()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CapabilityRefreshOperatorError, refresh.WeatherV9CapabilityRefreshError) as exc:
        print(
            json.dumps(
                {
                    "schema": "rozkalns.rpi5-main.weather-operator-v9-capability-refresh-receipt.v1",
                    "result": "FAIL_CLOSED",
                    "reason": str(exc),
                    "automatic_retry": False,
                    "automatic_cleanup": False,
                    "automatic_rollback": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raise SystemExit(78)
