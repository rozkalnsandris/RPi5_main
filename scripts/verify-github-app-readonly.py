#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
EXPECTED_REPOS = {
    "rozkalnsandris/RPi5_main": "validate.yml",
    "rozkalnsandris/hermes-tech": "ci.yml",
    "rozkalnsandris/rozkalns-cv": "ci.yml",
    "rozkalnsandris/hermes-deals": "ci.yml",
}
ALLOWED_PERMISSION_KEYS = {"actions", "contents", "metadata"}
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class VerificationError(RuntimeError):
    pass


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def require_private_key(path: Path) -> None:
    if not path.is_absolute():
        raise VerificationError("private key path must be absolute")
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise VerificationError("private key file is missing") from exc
    if stat.S_ISLNK(info.st_mode):
        raise VerificationError("private key file must not be a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise VerificationError("private key path is not a regular file")
    if info.st_mode & 0o077:
        raise VerificationError("private key file must not be group/world accessible")


def build_app_jwt(app_id: int, key_file: Path, *, now: int | None = None) -> str:
    if app_id <= 0:
        raise VerificationError("app id must be positive")
    require_private_key(key_file)
    issued = int(time.time() if now is None else now)
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iat": issued - 60,
        "exp": issued + 540,
        "iss": str(app_id),
    }
    encoded_header = b64url(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = b64url(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    try:
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(key_file)],
            input=signing_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise VerificationError("openssl is required") from exc
    if proc.returncode != 0 or not proc.stdout:
        raise VerificationError("openssl failed to sign GitHub App JWT")
    return f"{encoded_header}.{encoded_payload}.{b64url(proc.stdout)}"


def request_json(
    url: str,
    *,
    authorization: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {authorization}",
        "User-Agent": "rozkalns-automation-readonly-canary/1",
        "X-GitHub-Api-Version": API_VERSION,
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status not in {200, 201}:
                raise VerificationError(f"GitHub API returned unexpected HTTP {response.status}")
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise VerificationError(f"GitHub API request failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise VerificationError("GitHub API request failed") from exc
    if not isinstance(payload, dict):
        raise VerificationError("GitHub API returned a non-object payload")
    return payload


def parse_github_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerificationError("installation token expiry is invalid") from exc
    if parsed.tzinfo is None:
        raise VerificationError("installation token expiry has no timezone")
    return parsed.astimezone(timezone.utc)


def validate_token_payload(payload: dict[str, Any], *, now: datetime | None = None) -> tuple[str, int]:
    token = payload.get("token")
    if not isinstance(token, str) or len(token) < 20 or any(char.isspace() for char in token):
        raise VerificationError("installation token is missing or malformed")

    expires_at = payload.get("expires_at")
    if not isinstance(expires_at, str):
        raise VerificationError("installation token expiry is missing")
    current = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
    expiry = parse_github_time(expires_at)
    remaining = int((expiry - current).total_seconds())
    if not 3000 <= remaining <= 3700:
        raise VerificationError("installation token lifetime is outside the expected one-hour window")

    permissions = payload.get("permissions")
    if not isinstance(permissions, dict):
        raise VerificationError("installation token permissions are missing")
    normalized = {str(key): str(value) for key, value in permissions.items()}
    if normalized.get("actions") != "read" or normalized.get("contents") != "read":
        raise VerificationError("installation token is missing required read permissions")
    unexpected = set(normalized) - ALLOWED_PERMISSION_KEYS
    if unexpected:
        raise VerificationError("installation token contains unexpected repository permissions")
    if any(value != "read" for value in normalized.values()):
        raise VerificationError("installation token contains a non-read repository permission")

    selection = payload.get("repository_selection")
    if selection not in {None, "selected"}:
        raise VerificationError("GitHub App installation is not restricted to selected repositories")

    return token, remaining


def validate_repository_scope(payload: dict[str, Any]) -> None:
    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        raise VerificationError("installation repository list is missing")
    observed: set[str] = set()
    for row in repositories:
        if not isinstance(row, dict) or not isinstance(row.get("full_name"), str):
            raise VerificationError("installation repository list is malformed")
        observed.add(row["full_name"])
    expected = set(EXPECTED_REPOS)
    if observed != expected:
        raise VerificationError(
            "installation repository scope mismatch: "
            f"expected={','.join(sorted(expected))} observed={','.join(sorted(observed))}"
        )


def verify_repo(token: str, repo: str, workflow: str) -> tuple[str, int]:
    encoded_repo = "/".join(urllib.parse.quote(part, safe="") for part in repo.split("/", 1))
    branch = request_json(
        f"{API_ROOT}/repos/{encoded_repo}/branches/main",
        authorization=token,
    )
    sha = str((branch.get("commit") or {}).get("sha") or "")
    if not FULL_SHA.fullmatch(sha):
        raise VerificationError(f"{repo}: main SHA is invalid")

    query = urllib.parse.urlencode(
        {
            "branch": "main",
            "head_sha": sha,
            "status": "completed",
            "per_page": 100,
        }
    )
    runs = request_json(
        f"{API_ROOT}/repos/{encoded_repo}/actions/workflows/{urllib.parse.quote(workflow, safe='')}/runs?{query}",
        authorization=token,
    ).get("workflow_runs")
    if not isinstance(runs, list):
        raise VerificationError(f"{repo}: workflow run list is malformed")
    successful = [
        row
        for row in runs
        if isinstance(row, dict)
        and row.get("head_sha") == sha
        and row.get("head_branch") == "main"
        and row.get("status") == "completed"
        and row.get("conclusion") == "success"
    ]
    if not successful:
        raise VerificationError(f"{repo}: exact main SHA has no successful completed CI run")
    run_id = max(int(row.get("id") or 0) for row in successful)
    if run_id <= 0:
        raise VerificationError(f"{repo}: successful workflow run id is invalid")

    jobs = request_json(
        f"{API_ROOT}/repos/{encoded_repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100",
        authorization=token,
    ).get("jobs")
    if not isinstance(jobs, list) or not any(
        isinstance(job, dict)
        and job.get("status") == "completed"
        and job.get("conclusion") == "success"
        for job in jobs
    ):
        raise VerificationError(f"{repo}: successful exact-SHA workflow has no successful job")
    return sha, run_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the read-only Rozkalns Automation GitHub App installation from RPi5"
    )
    parser.add_argument("--app-id", required=True, type=int)
    parser.add_argument("--installation-id", required=True, type=int)
    parser.add_argument("--key-file", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.installation_id <= 0:
        raise VerificationError("installation id must be positive")

    jwt = build_app_jwt(args.app_id, args.key_file)
    token_payload = request_json(
        f"{API_ROOT}/app/installations/{args.installation_id}/access_tokens",
        authorization=jwt,
        method="POST",
        body={},
    )
    token, remaining = validate_token_payload(token_payload)

    scope = request_json(
        f"{API_ROOT}/installation/repositories?per_page=100",
        authorization=token,
    )
    validate_repository_scope(scope)

    results: list[tuple[str, str, int]] = []
    for repo, workflow in EXPECTED_REPOS.items():
        sha, run_id = verify_repo(token, repo, workflow)
        results.append((repo, sha, run_id))

    print("GITHUB_APP_READONLY_CANARY=PASS")
    print(f"TOKEN_EXPIRES_IN_SECONDS={remaining}")
    print("PERMISSIONS=actions:read,contents:read")
    print("REPOSITORY_SCOPE=" + ",".join(sorted(EXPECTED_REPOS)))
    for repo, sha, run_id in results:
        print(f"REPO_PASS={repo} MAIN_SHA={sha} CI_RUN_ID={run_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(f"GITHUB_APP_READONLY_CANARY=FAIL reason={exc}", file=sys.stderr)
        raise SystemExit(1)
