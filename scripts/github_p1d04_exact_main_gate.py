#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

REPOSITORY = "rozkalnsandris/RPi5_main"
DEFAULT_BRANCH = "main"
REQUIRED_WORKFLOWS = (
    "Validate",
    "FAST-LANE policy drift",
    "GITHUB-ONLY policy drift",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class GateError(RuntimeError):
    pass


def validate_gate_payloads(
    branch_payload: dict[str, Any],
    runs_payload: dict[str, Any],
    *,
    expected_sha: str,
    github_sha: str,
    run_attempt: str,
) -> dict[str, Any]:
    if run_attempt != "1":
        raise GateError("workflow_rerun_forbidden")
    if not SHA_RE.fullmatch(expected_sha):
        raise GateError("expected_sha_invalid")
    if github_sha != expected_sha:
        raise GateError("workflow_sha_mismatch")

    if branch_payload.get("name") != DEFAULT_BRANCH:
        raise GateError("default_branch_name_mismatch")
    commit = branch_payload.get("commit") or {}
    if commit.get("sha") != expected_sha:
        raise GateError("current_main_drifted")

    runs = runs_payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise GateError("workflow_runs_shape_invalid")

    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        if (
            run.get("head_sha") != expected_sha
            or run.get("head_branch") != DEFAULT_BRANCH
            or run.get("event") != "push"
            or run.get("name") not in REQUIRED_WORKFLOWS
        ):
            continue
        name = str(run["name"])
        previous = latest.get(name)
        if previous is None or int(run.get("id") or 0) > int(previous.get("id") or 0):
            latest[name] = run

    missing = [name for name in REQUIRED_WORKFLOWS if name not in latest]
    if missing:
        raise GateError("required_exact_main_workflow_missing")
    for name in REQUIRED_WORKFLOWS:
        run = latest[name]
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise GateError("required_exact_main_workflow_not_green")

    return {
        "main_sha": expected_sha,
        "required_workflows": list(REQUIRED_WORKFLOWS),
        "all_required_workflows_green": True,
    }


def _github_get(token: str, path: str) -> dict[str, Any]:
    if len(token) < 20 or any(ch.isspace() for ch in token):
        raise GateError("github_token_missing_or_invalid")
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "rpi5-main-p1d04-exact-main-gate",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, UnicodeDecodeError) as exc:
        raise GateError("github_gate_request_failed") from exc
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise GateError("github_gate_response_invalid") from exc
    if not isinstance(decoded, dict):
        raise GateError("github_gate_response_shape_invalid")
    return decoded


def fetch_and_validate_exact_main(
    *,
    repository: str,
    expected_sha: str,
    github_sha: str,
    run_attempt: str,
    github_token: str,
) -> dict[str, Any]:
    if repository != REPOSITORY:
        raise GateError("repository_mismatch")
    branch = _github_get(github_token, f"/repos/{repository}/branches/{DEFAULT_BRANCH}")
    query = urllib.parse.urlencode(
        {
            "branch": DEFAULT_BRANCH,
            "event": "push",
            "head_sha": expected_sha,
            "per_page": "100",
        }
    )
    runs = _github_get(github_token, f"/repos/{repository}/actions/runs?{query}")
    return validate_gate_payloads(
        branch,
        runs,
        expected_sha=expected_sha,
        github_sha=github_sha,
        run_attempt=run_attempt,
    )


def main() -> int:
    try:
        result = fetch_and_validate_exact_main(
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            expected_sha=os.environ.get("P1D04_EXPECTED_SHA", ""),
            github_sha=os.environ.get("GITHUB_SHA", ""),
            run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
        )
    except GateError as exc:
        print(f"P1D04_EXACT_MAIN_GATE=BLOCKED:{exc}")
        return 1
    print("P1D04_EXACT_MAIN_GATE=PASS")
    print("P1D04_REQUIRED_WORKFLOWS_GREEN=true")
    print(f"P1D04_REQUIRED_WORKFLOW_COUNT={len(result['required_workflows'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
