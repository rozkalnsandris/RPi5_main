#!/usr/bin/env python3
"""Bounded source/host preflight and separately gated Weather-v7 alert installer.

NO host action is authorized by the presence of this source file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/deploy/weather-v7-failure-telegram-install-v1.json"
ORIGINS = frozenset({
    "https://github.com/rozkalnsandris/RPi5_main.git",
    "git@github.com:rozkalnsandris/RPi5_main.git",
})
CALLER_UNIT = "rozkalns-weather-operator-v7-dispatch-caller.service"
TIMER_UNIT = "rozkalns-weather-operator-v7-dispatch-caller.timer"
NOTIFIER_SOURCE = "ops/bin/rozkalns-weather-v7-failure-telegram"
NOTIFIER_UNIT_SOURCE = "ops/systemd/rozkalns-weather-v7-failure-telegram.service"
CALLER_SOURCE = "ops/systemd/" + CALLER_UNIT
TIMER_SOURCE = "ops/systemd/" + TIMER_UNIT
CALLER_BINARY_SOURCE = "ops/bin/rozkalns-weather-operator-v7-dispatch-caller"
NOTIFIER_TARGET = Path("/usr/local/libexec/rozkalns-weather-v7-failure-telegram")
NOTIFIER_UNIT_TARGET = Path("/etc/systemd/system/rozkalns-weather-v7-failure-telegram.service")
CALLER_TARGET = Path("/etc/systemd/system") / CALLER_UNIT
CALLER_STAGE = Path("/etc/systemd/system/.rozkalns-weather-operator-v7-dispatch-caller.service.1087-candidate")
TIMER_TARGET = Path("/etc/systemd/system") / TIMER_UNIT
CALLER_BINARY_TARGET = Path("/usr/local/libexec/rozkalns-weather-operator-v7-dispatch-caller")
CREDENTIALS = (
    Path("/etc/credstore/weather-v7-failure-telegram-token"),
    Path("/etc/credstore/weather-v7-failure-telegram-chat-id"),
)
ON_FAILURE = b"OnFailure=rozkalns-weather-v7-failure-telegram.service\n"
HISTORIC_EXIT = "Wed 2026-09-30 21:55:22 CEST"
HISTORIC_START = "Wed 2026-09-30 21:55:19 CEST"
ARTIFACTS = (
    (NOTIFIER_SOURCE, NOTIFIER_TARGET, 0o755),
    (NOTIFIER_UNIT_SOURCE, NOTIFIER_UNIT_TARGET, 0o644),
    (CALLER_SOURCE, CALLER_TARGET, 0o644),
)


class InstallFailure(RuntimeError):
    pass


def fail(reason: str) -> None:
    raise InstallFailure(reason)


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def git(*args: str) -> str:
    # Trust is scoped to this exact checkout, not a wildcard/persistent Git config.
    argv = ["/usr/bin/git", "-c", "safe.directory=" + str(ROOT), "-C", str(ROOT), *args]
    try:
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=15, check=True,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError):
        fail("source identity check failed")
    return result.stdout.strip()


def source_file(path: str) -> bytes:
    candidate = ROOT / path
    try:
        info = candidate.lstat()
        if not stat.S_ISREG(info.st_mode):
            fail("source artifact is not a regular tracked file")
        if git("ls-files", "--error-unmatch", "--", path) != path:
            fail("source artifact is not tracked")
        data = candidate.read_bytes()
        if not data or sha256(data) != sha256(bytes.fromhex(git("show", "HEAD:" + path).encode().hex())):
            fail("source artifact does not match Git")
    except OSError:
        fail("source artifact is missing")
    return data


def source_check(expected_sha: str) -> dict[str, object]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        fail("expected main SHA must be exact lowercase 40-hex")
    if ROOT.is_symlink() or not ROOT.is_dir():
        fail("source root unsafe")
    if git("rev-parse", "HEAD") != expected_sha:
        fail("checkout HEAD mismatches owner-bound SHA")
    if git("branch", "--show-current") != "main":
        fail("source checkout must be clean main, not a feature branch")
    if git("remote", "get-url", "origin") not in ORIGINS:
        fail("canonical source origin mismatch")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        fail("source checkout is dirty")
    try:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("invalid source installer contract")
    if contract.get("schema") != "rozkalns.rpi5-main.weather-v7-failure-telegram-install.v1":
        fail("contract schema mismatch")
    expected_targets = {str(dst): format(mode, "04o") for _, dst, mode in ARTIFACTS}
    if contract.get("installed_targets") != expected_targets:
        fail("fixed target/mode contract mismatch")
    candidate = source_file(CALLER_SOURCE)
    if candidate.count(ON_FAILURE) != 1:
        fail("exactly one v7-only OnFailure binding required")
    if b"OnFailure=" in candidate.replace(ON_FAILURE, b""):
        fail("unexpected second failure hook")
    timer = source_file(TIMER_SOURCE)
    if not (b"OnBootSec=2min" in timer and b"Persistent=false" in timer):
        fail("boot-only caller timer contract changed")
    if any(bad in timer for bad in (b"OnUnitInactiveSec=", b"OnUnitActiveSec=", b"OnCalendar=")):
        fail("caller timer must not repeat")
    for p, _, _ in ARTIFACTS:
        source_file(p)
    source_file(CALLER_BINARY_SOURCE)
    # Source-check is offline: it does not inspect a host, secrets or systemd state.
    return {
        "result": "SOURCE_PASS", "source_sha": expected_sha, "artifact_count": len(ARTIFACTS),
        "host_inspected": False, "host_mutation_started": False,
        "live_authorized": False,
    }


def checked_installed(path: Path, expected: bytes, mode: int) -> None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            fail("installed artifact is not a regular file")
        if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != mode:
            fail("installed artifact metadata mismatch")
        if sha256(path.read_bytes()) != sha256(expected):
            fail("installed artifact SHA256 mismatch")
    except FileNotFoundError:
        fail("required installed artifact absent")
    except PermissionError:
        fail("required installed artifact metadata unavailable")


def require_absent(path: Path) -> None:
    if path.exists() or path.is_symlink():
        fail("first-install target or candidate already exists")


def require_directory(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError:
        fail("required target parent directory unavailable")
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0:
        fail("target parent directory identity invalid")
    if stat.S_IMODE(info.st_mode) & 0o022:
        fail("target parent directory is group/world writable")


def credentials_metadata() -> None:
    # Do not open, print, validate or provision credentials. No secret read.
    require_directory(Path("/etc/credstore"))
    for path in CREDENTIALS:
        try:
            meta = path.lstat()
        except OSError:
            fail("separately provisioned notifier credential is unavailable")
        if not stat.S_ISREG(meta.st_mode) or (meta.st_uid, meta.st_gid) != (0, 0):
            fail("credential ownership/type mismatch")
        if stat.S_IMODE(meta.st_mode) != 0o600 or not 1 <= meta.st_size <= 256:
            fail("credential metadata does not match fixed contract")


def systemctl_show(unit: str, keys: tuple[str, ...]) -> dict[str, str]:
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "show", unit, "--no-pager", "--property=" + ",".join(keys)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=8, check=True,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        fail("bounded systemd metadata is unavailable")
    rows: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            fail("invalid systemd metadata")
        key, value = line.split("=", 1)
        if key not in keys or key in rows:
            fail("unrecognized/duplicate systemd metadata")
        rows[key] = value
    if set(rows) != set(keys):
        fail("missing systemd metadata")
    return rows


CALLER_META = (
    "LoadState", "UnitFileState", "ActiveState", "SubState", "Result",
    "ExecMainCode", "ExecMainStatus", "ExecMainStartTimestamp", "ExecMainExitTimestamp",
)
TIMER_META = ("LoadState", "UnitFileState", "ActiveState", "SubState", "Result", "NextElapseUSecMonotonic")


def historic_state() -> None:
    caller = systemctl_show(CALLER_UNIT, CALLER_META)
    expected = {
        "LoadState": "loaded", "UnitFileState": "static",
        "ActiveState": "failed", "SubState": "failed", "Result": "exit-code",
        "ExecMainCode": "1", "ExecMainStatus": "78",
        "ExecMainStartTimestamp": HISTORIC_START,
        "ExecMainExitTimestamp": HISTORIC_EXIT,
    }
    if caller != expected:
        fail("historical failed/78 service state drifted; STOP (no reset-failed)")
    timer = systemctl_show(TIMER_UNIT, TIMER_META)
    if timer != {
        "LoadState": "loaded", "UnitFileState": "enabled",
        "ActiveState": "active", "SubState": "elapsed", "Result": "success",
        "NextElapseUSecMonotonic": "infinity",
    }:
        fail("boot-only elapsed timer metadata drifted")


def host_preflight(expected_sha: str) -> dict[str, object]:
    source_check(expected_sha)
    require_directory(NOTIFIER_TARGET.parent)
    require_directory(CALLER_TARGET.parent)
    for _, target, _ in ARTIFACTS[:2]:
        require_absent(target)
    require_absent(CALLER_STAGE)
    caller_new = source_file(CALLER_SOURCE)
    # Exact previously installed v7 unit is the current source minus one hook.
    old = caller_new.replace(ON_FAILURE, b"")
    checked_installed(CALLER_TARGET, old, 0o644)
    checked_installed(TIMER_TARGET, source_file(TIMER_SOURCE), 0o644)
    checked_installed(CALLER_BINARY_TARGET, source_file(CALLER_BINARY_SOURCE), 0o755)
    credentials_metadata()
    historic_state()
    return {
        "result": "HOST_PREFLIGHT_PASS", "source_sha": expected_sha,
        "historical_failed_78_retained": True, "fixed_targets_absent": 2,
        "existing_caller_unit_old_source_match": True,
        "timer_and_caller_unchanged": True,
        "credentials_metadata_only": True, "credential_values_read": False,
        "host_mutation_started": False,
    }


def exclusive_write(target: Path, data: bytes, mode: int) -> None:
    # No arbitrary staging directories, no overwrites of existing paths.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    try:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, mode)
        if os.write(fd, data) != len(data):
            fail("incomplete artifact write")
        os.fsync(fd)
    finally:
        os.close(fd)


def systemctl_reload() -> None:
    try:
        subprocess.run(
            ["/usr/bin/systemctl", "daemon-reload"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=15,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        fail("systemd reload failed")


def apply(expected_sha: str) -> dict[str, object]:
    if os.geteuid() != 0:
        fail("--apply requires a separately owner-authorized root process")
    host_preflight(expected_sha)
    # First filesystem write CONSUMES the exact separately issued LIVE authorization.
    # No retries, cleanup, restoration, or alternate mutation after uncertainty.
    try:
        exclusive_write(NOTIFIER_TARGET, source_file(NOTIFIER_SOURCE), 0o755)
        exclusive_write(NOTIFIER_UNIT_TARGET, source_file(NOTIFIER_UNIT_SOURCE), 0o644)
        exclusive_write(CALLER_STAGE, source_file(CALLER_SOURCE), 0o644)
        os.replace(CALLER_STAGE, CALLER_TARGET)  # exact single atomic replacement
        systemctl_reload()  # NO start, restart, reset-failed, or timer mutation
        checked_installed(NOTIFIER_TARGET, source_file(NOTIFIER_SOURCE), 0o755)
        checked_installed(NOTIFIER_UNIT_TARGET, source_file(NOTIFIER_UNIT_SOURCE), 0o644)
        checked_installed(CALLER_TARGET, source_file(CALLER_SOURCE), 0o644)
        checked_installed(TIMER_TARGET, source_file(TIMER_SOURCE), 0o644)
        historic_state()  # preserve accepted historical status after daemon-reload
    except Exception:
        fail("STOP: mutation attempted; no retry, rollback, cleanup or alternate mutation authorized")
    return {
        "result": "INSTALL_PASS", "source_sha": expected_sha,
        "files_installed": 2, "old_caller_unit_atomically_replaced": True,
        "daemon_reload": True, "historical_failed_78_retained": True,
        "telegram_sent": False, "caller_executed": False,
        "systemd_service_started": False, "timer_changed": False,
        "credentials_mutated": False, "production_notification_acceptance": False,
        "host_mutation_started": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Source-only Weather-v7 notifier installer candidate")
    parser.add_argument("--expected-main-sha", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--host-preflight", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = apply(args.expected_main_sha) if args.apply else (
            host_preflight(args.expected_main_sha) if args.host_preflight
            else source_check(args.expected_main_sha)
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except InstallFailure as exc:
        print(json.dumps({"result": "FAIL_CLOSED", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 78
    except Exception:
        # Do not leak local runtime/credential/HTTP details on any unexpected error.
        print('{"result":"FAIL_CLOSED","reason":"unexpected failure; STOP without retry"}', file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
