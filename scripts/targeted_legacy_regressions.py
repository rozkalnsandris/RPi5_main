#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RUNNER_SMOKE_TESTS = (
    "tests/test-hermes-deals-runner-smoke-systemctl-state.py",
)
WEATHER_LEGACY_TESTS = (
    "tests/test-v12-weathernext-bootstrap.py",
    "tests/test-weather-operator-v7-host-capability-installer.py",
    "tests/test-weather-v7-host-capability-sudo-git-trust.py",
    "tests/test-weather-v7-host-capability-installer-source-delivery.py",
    "tests/test-weather-operator-v7-dispatch-caller.py",
    "tests/test-weather-v7-host-capability-registration-repair.py",
    "tests/test-weather-v7-host-capability-home-access-repair.py",
    "tests/test-weather-operator-v9-privileged-delivery.py",
    "tests/test-weather-operator-v9-canonical-operation.py",
    "tests/test-weather-v9-capability-state-bootstrap.py",
    "tests/test-weather-v9-predecessor-state-bootstrap.py",
    "tests/test-weather-v9-predecessor-bootstrap-privileged.py",
    "tests/test-weather-v9-predecessor-bootstrap-preflight-diagnostic.py",
    "tests/test-weather-v9-predecessor-bootstrap-release-imports.py",
    "tests/test-weather-v9-predecessor-bootstrap-capability-repair.py",
    "tests/test-weather-v9-predecessor-bootstrap-installer-identity.py",
    "tests/test-weather-operator-v10-successor-broker.py",
    "tests/test-weather-v10-post-consume-failure-codes.py",
    "tests/test-weather-operator-v10-successor-dispatch-caller.py",
    "tests/test-weather-operator-v10-successor-dispatch-caller-refresh.py",
)


def normalize_base(value: str | None) -> str | None:
    if not value or re.fullmatch(r"0+", value):
        return None
    return value


def select_groups(changed: list[str] | None) -> tuple[bool, bool]:
    if changed is None:
        return True, True

    runner = any(
        re.search(r"(^|/)(hermes-deals-runner-smoke|runner_smoke)", path)
        or path.startswith("ops/lib/deploy_executor/")
        or path == ".github/workflows/validate.yml"
        for path in changed
    )
    weather = any(
        re.search(r"(^|/)(weather|weathernext)", path, flags=re.IGNORECASE)
        or path.startswith("ops/lib/deploy_executor/")
        or path == "scripts/rpi5_deploy.py"
        or path == ".github/workflows/validate.yml"
        for path in changed
    )
    return runner, weather


def changed_files(base: str | None) -> list[str] | None:
    if base is None:
        return None
    subprocess.run(
        ["git", "cat-file", "-e", f"{base}^{{commit}}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def run_tests(paths: tuple[str, ...]) -> None:
    for path in paths:
        print(f"legacy regression: python3 ./{path}", flush=True)
        subprocess.run(["python3", f"./{path}"], cwd=ROOT, check=True)


def main() -> int:
    base = normalize_base(os.environ.get("VALIDATE_BASE"))
    changed = changed_files(base)
    run_runner_smoke, run_weather_legacy = select_groups(changed)

    if run_runner_smoke:
        run_tests(RUNNER_SMOKE_TESTS)
    else:
        print("runner-smoke legacy regression: not affected")

    if run_weather_legacy:
        run_tests(WEATHER_LEGACY_TESTS)
    else:
        print("Weather legacy regressions: not affected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
