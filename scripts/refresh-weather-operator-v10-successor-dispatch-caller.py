#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/deploy/weather-operator-v10-successor-dispatch-caller-refresh.json"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
PREDECESSOR_SOURCE_SHA = "4ed279e04b240858fc8a2ce69e95f9c546e3a26b"
LEGACY_MODULE_SOURCE = "ops/lib/deploy_executor/weather_operator_upgrade_v9_dispatch_caller.py"
LEGACY_MODULE_TARGET = Path("/usr/local/libexec/rozkalns-weather-operator-v9-capability/deploy_executor/weather_operator_upgrade_v9_dispatch_caller.py")
SUCCESSOR_MODULE_SOURCE = "ops/lib/deploy_executor/weather_operator_upgrade_v10_dispatch_caller.py"
SUCCESSOR_MODULE_TARGET = Path("/usr/local/libexec/rozkalns-weather-operator-v9-capability/deploy_executor/weather_operator_upgrade_v10_dispatch_caller.py")
ENTRYPOINT_SOURCE = "ops/bin/rozkalns-weather-operator-v9-dispatch-caller"
ENTRYPOINT_TARGET = Path("/usr/local/libexec/rozkalns-weather-operator-v9-dispatch-caller")
SUCCESSOR_TEMP = SUCCESSOR_MODULE_TARGET.with_name(".weather_operator_upgrade_v10_dispatch_caller.py.refresh.tmp")
ENTRYPOINT_TEMP = ENTRYPOINT_TARGET.with_name(".rozkalns-weather-operator-v9-dispatch-caller.v10-refresh.tmp")
MUTATION_BUDGET = (
    ("filesystem.weather-operator-v10-successor-dispatch-caller-refresh-stage", 2),
    ("filesystem.weather-operator-v10-successor-dispatch-caller-refresh-atomic-replace", 2),
)
_MUTATION_STARTED = False


class CallerRefreshError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise CallerRefreshError(message)


def git_env() -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
    if os.geteuid() == 0 and os.environ.get("SUDO_UID"):
        env["SUDO_UID"] = str(os.environ["SUDO_UID"])
    return env


def run_git(*args: str, text: bool = True, check: bool = True) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            ["/usr/bin/git", "-C", str(ROOT), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            env=git_env(),
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        raise CallerRefreshError(f"git source preflight failed: {args[0] if args else 'git'}") from exc


def source_sha() -> str:
    head = run_git("rev-parse", "HEAD").stdout.strip()
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        fail("source HEAD is not an exact lowercase SHA")
    if run_git("remote", "get-url", "origin").stdout.strip() != ORIGIN:
        fail("source origin drifted")
    if run_git("status", "--porcelain", "--untracked-files=all").stdout != "":
        fail("source checkout must be clean")
    ancestor = run_git("merge-base", "--is-ancestor", PREDECESSOR_SOURCE_SHA, head, check=False)
    if ancestor.returncode != 0:
        fail("source HEAD does not descend from reviewed predecessor")
    origin_main = run_git("rev-parse", "refs/remotes/origin/main").stdout.strip()
    if origin_main != head:
        fail("source HEAD is not exact fetched origin/main")
    return head


def git_blob(commit: str, path: str) -> bytes:
    value = run_git("show", f"{commit}:{path}", text=False).stdout
    if type(value) is not bytes or not value:
        fail(f"reviewed source artifact is unavailable: {path}")
    return value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixed_file(path: Path, *, mode: int, expected: bytes) -> None:
    try:
        info = path.lstat()
        data = path.read_bytes()
    except OSError as exc:
        raise CallerRefreshError(f"required installed artifact is unavailable: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
        fail(f"installed artifact is not a single-link regular file: {path}")
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != mode:
        fail(f"installed artifact metadata drifted: {path}")
    if sha256(data) != sha256(expected):
        fail(f"installed predecessor artifact hash drifted: {path}")


def validate_contract() -> None:
    try:
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CallerRefreshError("caller-refresh contract is unavailable or malformed") from exc
    budget = tuple(
        (item.get("category"), item.get("max_operations"))
        for item in value.get("mutation_budget", [])
        if type(item) is dict
    )
    fixed = value.get("fixed_targets")
    expected_fixed = {
        str(SUCCESSOR_MODULE_TARGET): "0644",
        str(ENTRYPOINT_TARGET): "0755",
    }
    if (
        value.get("schema") != "rozkalns.rpi5-main.weather-operator-v10-successor-dispatch-caller-refresh.v1"
        or value.get("issue") != 650
        or value.get("predecessor_source_sha") != PREDECESSOR_SOURCE_SHA
        or value.get("origin") != ORIGIN
        or fixed != expected_fixed
        or value.get("replacement_order") != ["successor_module", "dispatch_caller_entrypoint"]
        or budget != MUTATION_BUDGET
        or value.get("systemd_mutation") is not False
        or value.get("broker_mutation") is not False
        or value.get("registration_mutation") is not False
        or value.get("replay_state_db_mutation") is not False
        or value.get("weather_runtime_mutation") is not False
        or value.get("queue_or_live_auth_creation") is not False
        or value.get("automatic_retry") is not False
        or value.get("automatic_cleanup") is not False
        or value.get("automatic_rollback") is not False
        or value.get("source_merge_authorizes_live") is not False
    ):
        fail("caller-refresh contract drifted")


def preflight() -> dict[str, object]:
    validate_contract()
    head = source_sha()
    predecessor_legacy = git_blob(PREDECESSOR_SOURCE_SHA, LEGACY_MODULE_SOURCE)
    predecessor_entrypoint = git_blob(PREDECESSOR_SOURCE_SHA, ENTRYPOINT_SOURCE)
    successor_module = git_blob(head, SUCCESSOR_MODULE_SOURCE)
    successor_entrypoint = git_blob(head, ENTRYPOINT_SOURCE)
    fixed_file(LEGACY_MODULE_TARGET, mode=0o644, expected=predecessor_legacy)
    fixed_file(ENTRYPOINT_TARGET, mode=0o755, expected=predecessor_entrypoint)
    if SUCCESSOR_MODULE_TARGET.exists() or SUCCESSOR_MODULE_TARGET.is_symlink():
        fail("successor caller module target already exists")
    if SUCCESSOR_TEMP.exists() or SUCCESSOR_TEMP.is_symlink() or ENTRYPOINT_TEMP.exists() or ENTRYPOINT_TEMP.is_symlink():
        fail("fixed caller-refresh staging path already exists")
    return {
        "schema": "rozkalns.rpi5-main.weather-operator-v10-successor-dispatch-caller-refresh-preflight.v1",
        "result": "PASS",
        "source_sha": head,
        "predecessor_source_sha": PREDECESSOR_SOURCE_SHA,
        "successor_module_sha256": sha256(successor_module),
        "dispatch_caller_entrypoint_sha256": sha256(successor_entrypoint),
        "mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in MUTATION_BUDGET
        ],
        "host_mutation_started": False,
        "systemd_mutation": False,
        "broker_mutation": False,
        "registration_mutation": False,
        "replay_state_db_mutation": False,
        "weather_runtime_mutation": False,
        "queue_or_live_auth_created": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "source_merge_authorizes_live": False,
    }


def stage(path: Path, data: bytes, mode: int) -> None:
    global _MUTATION_STARTED
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
    _MUTATION_STARTED = True
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                fail("caller-refresh staging write made no progress")
            view = view[written:]
        os.fsync(fd)
        os.fchmod(fd, mode)
        os.fchown(fd, 0, 0)
    finally:
        os.close(fd)


def require_target(path: Path, *, mode: int, expected: bytes) -> None:
    fixed_file(path, mode=mode, expected=expected)


def apply() -> dict[str, object]:
    if os.geteuid() != 0:
        fail("--apply requires an owner-authorized root process")
    evidence = preflight()
    head = str(evidence["source_sha"])
    successor_module = git_blob(head, SUCCESSOR_MODULE_SOURCE)
    successor_entrypoint = git_blob(head, ENTRYPOINT_SOURCE)
    try:
        stage(SUCCESSOR_TEMP, successor_module, 0o644)
        stage(ENTRYPOINT_TEMP, successor_entrypoint, 0o755)
        os.replace(SUCCESSOR_TEMP, SUCCESSOR_MODULE_TARGET)
        os.replace(ENTRYPOINT_TEMP, ENTRYPOINT_TARGET)
        require_target(SUCCESSOR_MODULE_TARGET, mode=0o644, expected=successor_module)
        require_target(ENTRYPOINT_TARGET, mode=0o755, expected=successor_entrypoint)
    except Exception as exc:
        raise CallerRefreshError(
            "caller refresh failed closed after mutation; no retry/cleanup/rollback is authorized"
        ) from exc
    return {
        "schema": "rozkalns.rpi5-main.weather-operator-v10-successor-dispatch-caller-refresh-receipt.v1",
        "result": "PASS",
        "source_sha": head,
        "predecessor_source_sha": PREDECESSOR_SOURCE_SHA,
        "successor_module_sha256": evidence["successor_module_sha256"],
        "dispatch_caller_entrypoint_sha256": evidence["dispatch_caller_entrypoint_sha256"],
        "host_mutation_started": _MUTATION_STARTED,
        "successor_module_installed": True,
        "dispatch_caller_entrypoint_replaced": True,
        "systemd_mutation": False,
        "broker_mutation": False,
        "registration_mutation": False,
        "replay_state_db_mutation": False,
        "weather_runtime_mutation": False,
        "queue_or_live_auth_created": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the fixed Weather v10 successor dispatch caller")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = apply() if args.apply else preflight()
    except CallerRefreshError as exc:
        print(json.dumps({
            "schema": "rozkalns.rpi5-main.weather-operator-v10-successor-dispatch-caller-refresh-receipt.v1",
            "result": "FAIL_CLOSED",
            "reason": str(exc),
            "host_mutation_started": _MUTATION_STARTED,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
        }, sort_keys=True, separators=(",", ":")))
        return 78
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
