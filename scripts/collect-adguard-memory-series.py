#!/usr/bin/env python3
"""Collect four spaced, individually verified V11 AdGuard memory bundles."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

from adguard_memory_core import canonical_json
from adguard_memory_safety import (
    CollectionEnvironment,
    SafetyError,
    collection_environment,
    effective_uid,
    test_override,
)
from adguard_memory_series_core import (
    SERIES_SAMPLE_COUNT,
    build_series,
    render_series_markdown,
)

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
COLLECTOR = HERE / "collect-adguard-memory-attribution.py"
SAMPLE_VERIFIER = HERE / "verify-adguard-memory-attribution.py"
SERIES_VERIFIER = HERE / "verify-adguard-memory-series.py"


def fail(message: str) -> None:
    raise SystemExit(f"collect-adguard-memory-series: {message}")


def runtime_environment() -> CollectionEnvironment:
    try:
        return collection_environment(REPO)
    except SafetyError as exc:
        fail(str(exc))


def no_symlink_components(path: pathlib.Path) -> None:
    current = pathlib.Path(path.anchor or "/") if path.is_absolute() else pathlib.Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            fail("symlink path component rejected")


def allowed_output(path: pathlib.Path) -> pathlib.Path:
    requested = path if path.is_absolute() else pathlib.Path.cwd() / path
    no_symlink_components(requested)
    parent = requested.parent.resolve(strict=True)
    target = parent / requested.name
    if target.exists() or target.is_symlink():
        fail("output already exists")
    for name in ("evidence", "exports"):
        try:
            target.relative_to((REPO / name).resolve())
            return target
        except ValueError:
            continue
    fail("output is outside repository evidence/exports")


def run_checked(args: list[str], *, env: dict[str, str], timeout: int = 90) -> None:
    completed = subprocess.run(
        args,
        cwd=REPO,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = f": {detail[-1][:300]}" if detail else ""
        fail(f"command failed ({pathlib.Path(args[1]).name}){suffix}")


def fixture_times(environment: CollectionEnvironment) -> list[str] | None:
    try:
        raw = test_override("ADGUARD_ATTR_FIXED_UTC", environment)
    except SafetyError as exc:
        fail(str(exc))
    if not raw:
        return None
    try:
        base = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        fail("invalid ADGUARD_ATTR_FIXED_UTC")
    return [
        (base + timedelta(seconds=index)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for index in range(SERIES_SAMPLE_COUNT)
    ]


def no_sleep(environment: CollectionEnvironment) -> bool:
    try:
        raw = test_override("ADGUARD_ATTR_TEST_NO_SLEEP", environment)
    except SafetyError as exc:
        fail(str(exc))
    return raw == "1"


def write_checksums(stage: pathlib.Path) -> None:
    relative_paths = ["series.json", "series.md"]
    relative_paths.extend(
        f"samples/{index:02d}/report.json"
        for index in range(1, SERIES_SAMPLE_COUNT + 1)
    )
    (stage / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((stage / relative).read_bytes()).hexdigest()}  {relative}\n"
            for relative in relative_paths
        ),
        encoding="utf-8",
    )


def collect(target: pathlib.Path, interval_seconds: int, environment: CollectionEnvironment) -> pathlib.Path:
    skip_sleep = no_sleep(environment)
    if skip_sleep:
        fixed_times = fixture_times(environment)
        if fixed_times is None:
            fail("no-sleep fixture mode requires ADGUARD_ATTR_FIXED_UTC")
    else:
        fixed_times = None
        if not 60 <= interval_seconds <= 1800:
            fail("production interval must be between 60 and 1800 seconds")

    stage = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=str(target.parent))
    )
    try:
        samples_dir = stage / "samples"
        samples_dir.mkdir(mode=0o700)
        reports: list[dict] = []
        for index in range(1, SERIES_SAMPLE_COUNT + 1):
            sample = samples_dir / f"{index:02d}"
            child_env = os.environ.copy()
            if fixed_times is not None:
                child_env["ADGUARD_ATTR_FIXED_UTC"] = fixed_times[index - 1]
            run_checked(
                [sys.executable, str(COLLECTOR), "--output", str(sample)],
                env=child_env,
            )
            run_checked(
                [sys.executable, str(SAMPLE_VERIFIER), str(sample)],
                env=child_env,
            )
            reports.append(json.loads((sample / "report.json").read_text(encoding="utf-8")))
            print(
                f"V11 sample {index}/{SERIES_SAMPLE_COUNT} verified: "
                f"dominant={reports[-1]['attribution']['dominant_component']} "
                f"container_kib={reports[-1]['container']['usage_kib']}"
            )
            if index < SERIES_SAMPLE_COUNT and not skip_sleep:
                time.sleep(interval_seconds)

        series = build_series(reports)
        (stage / "series.json").write_text(canonical_json(series), encoding="utf-8")
        (stage / "series.md").write_text(render_series_markdown(series), encoding="utf-8")
        write_checksums(stage)
        for path in stage.rglob("*"):
            if path.is_file():
                os.chmod(path, 0o600)
            elif path.is_dir():
                os.chmod(path, 0o700)
        os.chmod(stage, 0o700)
        stage.rename(target)
        try:
            run_checked(
                [sys.executable, str(SERIES_VERIFIER), str(target)],
                env=os.environ.copy(),
                timeout=180,
            )
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return target
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args()
    environment = runtime_environment()
    try:
        uid = effective_uid(environment)
    except SafetyError as exc:
        fail(str(exc))
    if uid == 0:
        fail("root execution rejected")
    target = allowed_output(pathlib.Path(args.output))
    result = collect(target, args.interval_seconds, environment)
    series = json.loads((result / "series.json").read_text(encoding="utf-8"))
    print(f"AdGuard memory series: {result}")
    print(f"Stable dominant component: {series['stable_dominant_component']}")
    print(f"Container change KiB: {series['container_usage_change_kib']}")


if __name__ == "__main__":
    main()
