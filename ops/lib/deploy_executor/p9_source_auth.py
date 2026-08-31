from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from .github_app_auth import (
    AppAuthError,
    RawResponse,
    Requester,
    build_app_jwt,
    https_json_request,
    require_private_key,
)
from .transport import API_VERSION, InstallationToken

SOURCE_APP_ID = 4537106
SOURCE_INSTALLATION_ID = 152422751
OWNER_LOGIN = "rozkalnsandris"
OWNER_ID = 277435981
OWNER_TYPE = "User"
CONTROL_SOURCE_REPOSITORY = "rozkalnsandris/rozkalns-control-center"
CONTROL_SOURCE_REPOSITORY_ID = 1329279953
SOURCE_REPOSITORIES = {
    CONTROL_SOURCE_REPOSITORY: CONTROL_SOURCE_REPOSITORY_ID,
}
REQUIRED_PERMISSIONS = {"actions": "read", "contents": "read"}
ALLOWED_PERMISSION_KEYS = frozenset({"actions", "contents", "metadata"})
SOURCE_TOKEN_SAFE_STAGES = frozenset(
    {
        "jwt_sign",
        "installation_request",
        "installation_not_found",
        "installation_status",
        "installation_payload",
        "installation_clock",
        "installation_scope",
        "token_request",
        "token_response",
        "token_scope",
    }
)


class P9SourceAuthError(AppAuthError):
    pass


class P9SourceTokenStageError(P9SourceAuthError):
    """Public-safe source-App token failure with an allowlisted stage only."""

    def __init__(self, stage: str):
        if stage not in SOURCE_TOKEN_SAFE_STAGES:
            raise ValueError("source token failure stage is not allowlisted")
        self.stage = stage
        super().__init__(f"source installation token provider failed stage={stage}")


def _headers(token: str | None = None) -> dict[str, str]:
    result = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "rozkalns-deploy-executor-p9-source/1",
    }
    if token is not None:
        result["Authorization"] = f"Bearer {token}"
    return result


def _server_time(headers: Mapping[str, str]) -> datetime:
    value = next((value for key, value in headers.items() if key.lower() == "date"), None)
    if type(value) is not str:
        raise P9SourceAuthError("GitHub response omitted Date header")
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise P9SourceAuthError("GitHub Date header is invalid") from exc
    if parsed.tzinfo is None:
        raise P9SourceAuthError("GitHub Date header has no timezone")
    return parsed.astimezone(timezone.utc)


def _object(response: RawResponse, status: int, where: str) -> dict[str, Any]:
    if response.status != status:
        raise P9SourceAuthError(f"{where} returned HTTP {response.status}")
    if type(response.value) is not dict:
        raise P9SourceAuthError(f"{where} returned a non-object payload")
    return response.value


def _validate_permissions(value: Any, where: str) -> None:
    if type(value) is not dict:
        raise P9SourceAuthError(f"{where} permissions are missing")
    normalized = {str(key): str(item) for key, item in value.items()}
    for key, expected in REQUIRED_PERMISSIONS.items():
        if normalized.get(key) != expected:
            raise P9SourceAuthError(f"{where} is missing required read permissions")
    if set(normalized) - ALLOWED_PERMISSION_KEYS:
        raise P9SourceAuthError(f"{where} contains unexpected permissions")
    if any(item != "read" for item in normalized.values()):
        raise P9SourceAuthError(f"{where} contains a non-read permission")


def validate_source_installation(payload: Mapping[str, Any]) -> None:
    if payload.get("id") != SOURCE_INSTALLATION_ID:
        raise P9SourceAuthError("source installation id mismatch")
    if payload.get("app_id") != SOURCE_APP_ID:
        raise P9SourceAuthError("source installation app id mismatch")
    if payload.get("target_id") != OWNER_ID or payload.get("target_type") != OWNER_TYPE:
        raise P9SourceAuthError("source installation target mismatch")
    if payload.get("repository_selection") != "selected":
        raise P9SourceAuthError("source installation must use selected repositories")
    account = payload.get("account")
    if (
        type(account) is not dict
        or account.get("id") != OWNER_ID
        or account.get("login") != OWNER_LOGIN
        or account.get("type") != OWNER_TYPE
    ):
        raise P9SourceAuthError("source installation owner mismatch")
    _validate_permissions(payload.get("permissions"), "source installation")


def validate_source_token(
    payload: Mapping[str, Any],
    *,
    repository: str,
    repository_id: int,
    now: datetime,
) -> InstallationToken:
    token = payload.get("token")
    if type(token) is not str or len(token) < 20 or any(char.isspace() for char in token):
        raise P9SourceAuthError("source installation token is malformed")
    expires_at = payload.get("expires_at")
    if type(expires_at) is not str:
        raise P9SourceAuthError("source installation token expiry is missing")
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P9SourceAuthError("source installation token expiry is invalid") from exc
    if expiry.tzinfo is None:
        raise P9SourceAuthError("source installation token expiry has no timezone")
    expiry = expiry.astimezone(timezone.utc)
    remaining = int((expiry - now.astimezone(timezone.utc)).total_seconds())
    if not 3000 <= remaining <= 3700:
        raise P9SourceAuthError("source installation token lifetime is outside expected bounds")
    if payload.get("repository_selection") != "selected":
        raise P9SourceAuthError("source installation token selection posture mismatch")
    _validate_permissions(payload.get("permissions"), "source installation token")
    repositories = payload.get("repositories")
    observed = [
        (row.get("id"), row.get("full_name"))
        for row in repositories
        if type(row) is dict
    ] if type(repositories) is list else []
    if observed != [(repository_id, repository)]:
        raise P9SourceAuthError("source installation token repository scope mismatch")
    return InstallationToken(token, expires_at=expiry)


class P9SourceInstallationTokenProvider:
    """Mint and cache one Actions/Contents read token for one reviewed P9 source repository."""

    def __init__(
        self,
        *,
        repository: str,
        private_key: str | Path,
        requester: Requester = https_json_request,
        signer: Callable[[bytes, Path], bytes] | None = None,
    ):
        try:
            repository_id = SOURCE_REPOSITORIES[repository]
        except KeyError as exc:
            raise P9SourceAuthError("P9 source repository is not allowlisted") from exc
        self.repository = repository
        self.repository_id = repository_id
        self.private_key = require_private_key(private_key)
        if self.private_key.stat().st_uid != os.geteuid():
            raise P9SourceAuthError("source private key owner must match the P9 process identity")
        self.requester = requester
        self.signer = signer
        self._cached_token: InstallationToken | None = None

    def get_installation_token(self) -> InstallationToken:
        if self._cached_token is not None:
            return self._cached_token

        local_now = datetime.now(timezone.utc)
        try:
            jwt = build_app_jwt(
                app_id=SOURCE_APP_ID,
                server_time=local_now,
                private_key=self.private_key,
                signer=self.signer,
            )
        except Exception:
            raise P9SourceTokenStageError("jwt_sign") from None

        owner, repository_name = self.repository.split("/", 1)
        try:
            installation_response = self.requester(
                "GET",
                f"/repos/{owner}/{repository_name}/installation",
                _headers(jwt),
                None,
            )
        except Exception:
            raise P9SourceTokenStageError("installation_request") from None
        if installation_response.status == 404:
            raise P9SourceTokenStageError("installation_not_found") from None
        if installation_response.status != 200:
            raise P9SourceTokenStageError("installation_status") from None
        if type(installation_response.value) is not dict:
            raise P9SourceTokenStageError("installation_payload") from None
        try:
            server_now = _server_time(installation_response.headers)
        except Exception:
            raise P9SourceTokenStageError("installation_clock") from None
        installation = installation_response.value
        try:
            validate_source_installation(installation)
        except Exception:
            raise P9SourceTokenStageError("installation_scope") from None

        body = json.dumps(
            {
                "repository_ids": [self.repository_id],
                "permissions": REQUIRED_PERMISSIONS,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            token_response = self.requester(
                "POST",
                f"/app/installations/{SOURCE_INSTALLATION_ID}/access_tokens",
                {**_headers(jwt), "Content-Type": "application/json"},
                body,
            )
        except Exception:
            raise P9SourceTokenStageError("token_request") from None
        try:
            token_payload = _object(
                token_response,
                201,
                "source installation token mint",
            )
        except Exception:
            raise P9SourceTokenStageError("token_response") from None
        try:
            token = validate_source_token(
                token_payload,
                repository=self.repository,
                repository_id=self.repository_id,
                now=server_now,
            )
        except Exception:
            raise P9SourceTokenStageError("token_scope") from None
        self._cached_token = token
        return token
