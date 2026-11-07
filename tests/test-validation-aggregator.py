#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/require-validation-results.py"
NAMES = (
    "REGRESSIONS_RESULT",
    "API_CONTRACT_RESULT",
    "TARGETED_LEGACY_RESULT",
    "SECRET_SCAN_RESULT",
    "PUBLIC_SAFETY_RESULT",
    "GITLEAKS_RESULT",
    "PUBLIC_AUTOMATION_RESULT",
    "WORKFLOW_SECURITY_RESULT",
)


def run(overrides: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for name in NAMES:
        env[name] = "success"
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return subprocess.run(
        ["python3", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


assert run({}).returncode == 0
assert run({"REGRESSIONS_RESULT": "failure"}).returncode == 1
assert run({"WORKFLOW_SECURITY_RESULT": "cancelled"}).returncode == 1
assert run({"PUBLIC_AUTOMATION_RESULT": "skipped"}).returncode == 1
missing = run({"GITLEAKS_RESULT": None})
assert missing.returncode == 1
assert "GITLEAKS_RESULT=missing" in missing.stdout

print("Validation aggregator: PASS")
