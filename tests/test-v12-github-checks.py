#!/usr/bin/env python3
"""Regression coverage for GitHub check-run terminal conclusions used by V12."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / "scripts"))

import rpi5_deploy_lib as deploy_lib

COMMIT = "a" * 40


def response(checks: list[dict[str, object]]) -> SimpleNamespace:
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"check_runs": checks}),
        stderr="",
    )


def check_run(name: str, status: str, conclusion: str | None) -> dict[str, object]:
    return {"name": name, "status": status, "conclusion": conclusion}


def evaluate(checks: list[dict[str, object]]) -> dict[str, object]:
    original_run = deploy_lib.run
    original_which = deploy_lib.shutil.which
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return response(checks)

    deploy_lib.run = fake_run
    deploy_lib.shutil.which = lambda name: "/usr/bin/gh" if name == "gh" else original_which(name)
    try:
        result = deploy_lib.github_checks(COMMIT)
    finally:
        deploy_lib.run = original_run
        deploy_lib.shutil.which = original_which

    assert calls == [[
        "gh",
        "api",
        f"repos/{deploy_lib.EXPECTED_REPOSITORY}/commits/{COMMIT}/check-runs?per_page=100",
    ]]
    return result


def expect_failure(checks: list[dict[str, object]]) -> None:
    try:
        evaluate(checks)
    except deploy_lib.DeployError as exc:
        assert "exact-commit GitHub checks are not all successful" in str(exc), str(exc)
    else:
        raise AssertionError("expected fail-closed GitHub check rejection")


# GitHub documents success, skipped, and neutral as successful terminal
# conclusions for required status-check purposes. Conditional skipped jobs must
# therefore not veto an otherwise valid exact-commit gate.
accepted = [
    check_run("validate", "completed", "success"),
    check_run("conditional-route", "completed", "skipped"),
    check_run("advisory", "completed", "neutral"),
]
result = evaluate(accepted)
assert result["count"] == 3
assert result["names"] == ["advisory", "conditional-route", "validate"]

# Non-terminal checks and non-successful terminal conclusions remain fail-closed.
expect_failure([check_run("validate", "in_progress", None)])
for conclusion in (
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
):
    expect_failure([check_run("validate", "completed", conclusion)])

print("V12 GitHub check conclusion regression: PASS")
