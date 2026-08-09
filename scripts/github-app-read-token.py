#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request

API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
APP_ID = 4537106
INSTALLATION_ID = 152422751
KEY_FILE = Path("/root/.config/rozkalns-automation/github-app.pem")
ALLOWED_REPOSITORIES = frozenset(
    {
        "rozkalnsandris/RPi5_main",
        "rozkalnsandris/hermes-tech",
        "rozkalnsandris/rozkalns-cv",
        "rozkalnsandris/hermes-deals",
    }
)
REQUIRED_PERMISSIONS = {"actions": "read", "contents": "read"}
ALLOWED_PERMISSION_KEYS = frozenset({"actions", "contents", "metadata"})


class TokenBrokerError(RuntimeError):
    pass


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def require_private_key(path: Path) -> None:
    if not path.is_absolute():
        raise TokenBrokerError("private key path must be absolute")
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise TokenBrokerError("private key file is missing") from exc
    if stat.S_ISLNK(info.st_mode):
        raise TokenBrokerError("private key file must not be a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise TokenBrokerError("private key path is not a regular file")
    if info.st_uid != 0:
        raise TokenBrokerError("private key must be root-owned")
    if info.st_mode & 0o077:
        raise TokenBrokerError("private key must not be group/world accessible")


def build_app_jwt(*, now: int | None = None) -> str:
    require_private_key(KEY_FILE)
    issued = int(time.time() if now is None else now)
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {"iat": issued - 60, "exp": issued + 540, "iss": str(APP_ID)}
    encoded_header = b64url(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = b64url(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    try:
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(KEY_FILE)],
            input=signing_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise TokenBrokerError("openssl is required") from exc
    if proc.returncode != 0 or not proc.stdout:
        raise TokenBrokerError("openssl failed to sign GitHub App JWT")
    return f"{encoded_header}.{encoded_payload}.{b64url(proc.stdout)}"


def request_json(
    url: str,
    *,
    authorization: str,
    method: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {authorization}",
        "Content-Type": "application/json",
        "User-Agent": "rozkalns-automation-read-token/1",
        "X-GitHub-Api-Version": API_VERSION,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status not in {200, 201}:
                raise TokenBrokerError(
                    f"GitHub API returned unexpected HTTP {response.status}"
                )
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise TokenBrokerError(f"GitHub API request failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise TokenBrokerError("GitHub API request failed") from exc
    if not isinstance(payload, dict):
        raise TokenBrokerError("GitHub API returned a non-object payload")
    return payload


def parse_github_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TokenBrokerError("installation token expiry is invalid") from exc
    if parsed.tzinfo is None:
        raise TokenBrokerError("installation token expiry has no timezone")
    return parsed.astimezone(timezone.utc)


def validate_token_payload(
    payload: dict[str, Any],
    *,
    repository: str,
    now: datetime | None = None,
) -> str:
    token = payload.get("token")
    if not isinstance(token, str) or len(token) < 20 or any(char.isspace() for char in token):
        raise TokenBrokerError("installation token is missing or malformed")

    expires_at = payload.get("expires_at")
    if not isinstance(expires_at, str):
        raise TokenBrokerError("installation token expiry is missing")
    current = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
    remaining = int((parse_github_time(expires_at) - current).total_seconds())
    if not 3000 <= remaining <= 3700:
        raise TokenBrokerError("installation token lifetime is outside the expected window")

    permissions = payload.get("permissions")
    if not isinstance(permissions, dict):
        raise TokenBrokerError("installation token permissions are missing")
    normalized = {str(key): str(value) for key, value in permissions.items()}
    for key, value in REQUIRED_PERMISSIONS.items():
        if normalized.get(key) != value:
            raise TokenBrokerError("installation token is missing required read permissions")
    if set(normalized) - ALLOWED_PERMISSION_KEYS:
        raise TokenBrokerError("installation token contains unexpected permissions")
    if any(value != "read" for value in normalized.values()):
        raise TokenBrokerError("installation token contains a non-read permission")

    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        raise TokenBrokerError("installation token repository scope is missing")
    observed = {
        str(row.get("full_name"))
        for row in repositories
        if isinstance(row, dict) and isinstance(row.get("full_name"), str)
    }
    if observed != {repository}:
        raise TokenBrokerError("installation token repository scope mismatch")
    return token


def mint_repository_token(repository: str) -> str:
    if repository not in ALLOWED_REPOSITORIES:
        raise TokenBrokerError("repository is not approved for automation token access")
    jwt = build_app_jwt()
    payload = request_json(
        f"{API_ROOT}/app/installations/{INSTALLATION_ID}/access_tokens",
        authorization=jwt,
        method="POST",
        body={
            "repositories": [repository],
            "permissions": REQUIRED_PERMISSIONS,
        },
    )
    return validate_token_payload(payload, repository=repository)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mint one repository-scoped read-only Rozkalns Automation token"
    )
    parser.add_argument("--repository", required=True, choices=sorted(ALLOWED_REPOSITORIES))
    return parser.parse_args()


def main() -> int:
    if os.geteuid() != 0:
        raise TokenBrokerError("token broker must run as root")
    args = parse_args()
    token = mint_repository_token(args.repository)
    # Credential output is intentionally the only stdout emitted by this helper.
    # Callers must capture it directly and must never log or persist it.
    sys.stdout.write(token)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TokenBrokerError as exc:
        print(f"GITHUB_APP_READ_TOKEN=FAIL reason={exc}", file=sys.stderr)
        raise SystemExit(1)
