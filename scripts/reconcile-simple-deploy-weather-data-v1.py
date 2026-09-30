#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "scripts/install-simple-deploy-weather-data-v1.py"
PREDECESSOR_SOURCE_SHA = "7be2772ca8c0dddefd00181c805bd693bc06a9ed"
ROOT_UID = 0
ROOT_GID = 0
RECONCILER_RELATIVE = "scripts/reconcile-simple-deploy-weather-data-v1.py"

spec = importlib.util.spec_from_file_location("weather_data_installer", INSTALLER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Weather data installer module cannot be loaded")
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


class ReconcileError(RuntimeError):
    pass


@dataclass
class Progress:
    mutation_started: bool = False
    files_replaced: int = 0


class ApplyFailure(ReconcileError):
    def __init__(self, message: str, progress: Progress):
        super().__init__(message)
        self.progress = progress


def _fail(message: str) -> None:
    raise ReconcileError(message)


def _require_source_checkout(expected_sha: str) -> None:
    try:
        installer._require_source_checkout(expected_sha)
    except installer.WeatherDataInstallerError as exc:
        _fail(str(exc))
    result = installer._git_stdout("show", f"{expected_sha}:{RECONCILER_RELATIVE}")
    if result != Path(__file__).read_bytes():
        _fail("reconciler working-tree bytes differ from expected source")


def _source_bytes(source_sha: str, target) -> bytes:
    try:
        return installer._source_bytes(source_sha, target)
    except installer.WeatherDataInstallerError as exc:
        _fail(str(exc))


def _require_metadata(target) -> None:
    try:
        info = os.lstat(target.target)
    except FileNotFoundError:
        _fail(f"tracked Weather data target absent: {target.target}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail(f"tracked Weather data target type drifted: {target.target}")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or stat.S_IMODE(info.st_mode) != target.mode:
        _fail(f"tracked Weather data target metadata drifted: {target.target}")


def _prepared(expected_sha: str):
    _require_source_checkout(expected_sha)
    try:
        installer._require_dir(installer.BASE_LIBEXEC, mode=0o755, uid=ROOT_UID, gid=ROOT_GID)
        installer._require_dir(installer.BASE_ETC, mode=0o755, uid=ROOT_UID, gid=ROOT_GID)
        installer._require_dir(installer.SYSTEMD_DIR, mode=0o755, uid=ROOT_UID, gid=ROOT_GID)
        installer._require_principal()
        for required, mode in installer.BASE_REQUIRED_FILES:
            installer._require_file(required, mode)
    except installer.WeatherDataInstallerError as exc:
        _fail(str(exc))
    prepared = []
    for target in installer.TRACKED_FILES:
        _require_metadata(target)
        current = target.target.read_bytes()
        predecessor = _source_bytes(PREDECESSOR_SOURCE_SHA, target)
        desired = _source_bytes(expected_sha, target)
        if current != predecessor:
            _fail(f"tracked Weather data target preimage drifted: {target.target}")
        prepared.append((target, current, desired))
    return tuple(prepared)


def _atomic_replace(target, desired: bytes) -> None:
    parent = target.target.parent
    temp = parent / f".{target.target.name}.reconcile-{os.getpid()}"
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
        dir_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        raise ReconcileError(f"atomic reconciliation failed: {target.target}: {exc.strerror}") from exc


def _verify(target, desired: bytes) -> None:
    _require_metadata(target)
    actual = target.target.read_bytes()
    if actual != desired or hashlib.sha256(actual).digest() != hashlib.sha256(desired).digest():
        _fail(f"reconciled Weather data target content drifted: {target.target}")


def _receipt(result: str, source_sha: str, progress: Progress, *, reason: str | None = None) -> str:
    payload: dict[str, object] = {
        "schema": "rozkalns.rpi5-main.simple-deploy.weather-data.reconcile-receipt.v1",
        "result": result,
        "source_sha": source_sha,
        "predecessor_source_sha": PREDECESSOR_SOURCE_SHA,
        "file_target_count": len(installer.TRACKED_FILES),
        "files_replaced": progress.files_replaced,
        "mutation_started": progress.mutation_started,
        "daemon_reload_performed": False,
        "service_started": False,
        "timer_enabled_or_started": False,
        "docker_command_executed": False,
        "database_or_data_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "automatic_delete": False,
    }
    if reason is not None:
        payload["reason"] = reason
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def preflight(expected_sha: str) -> str:
    prepared = _prepared(expected_sha)
    replacements = sum(1 for _target, current, desired in prepared if current != desired)
    progress = Progress(files_replaced=0)
    value = json.loads(_receipt("WEATHER_DATA_RECONCILE_PREFLIGHT_READY", expected_sha, progress))
    value["planned_replacements"] = replacements
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def apply(expected_sha: str) -> str:
    if os.geteuid() != ROOT_UID:
        _fail("--apply requires root and a separate exact LIVE authorization")
    prepared = _prepared(expected_sha)
    progress = Progress()
    try:
        for target, current, desired in prepared:
            if current == desired:
                continue
            progress.mutation_started = True
            _atomic_replace(target, desired)
            progress.files_replaced += 1
            _verify(target, desired)
    except (ReconcileError, OSError) as exc:
        raise ApplyFailure(str(exc), progress) from exc
    return _receipt("WEATHER_DATA_RECONCILED_NOT_ACTIVATED", expected_sha, progress)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile the fixed installed Weather data companion without activation")
    parser.add_argument("expected_source_sha")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = apply(args.expected_source_sha) if args.apply else preflight(args.expected_source_sha)
    except ApplyFailure as exc:
        print(_receipt("FAIL_CLOSED", args.expected_source_sha, exc.progress, reason=str(exc)), file=sys.stderr)
        return 1
    except ReconcileError as exc:
        print(_receipt("PRE_MUTATION_FAILURE", args.expected_source_sha, Progress(), reason=str(exc)), file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
