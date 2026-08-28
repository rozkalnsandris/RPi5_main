from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import http.client
import json
from pathlib import Path
import stat
import subprocess
from typing import Any, Callable, Mapping, Protocol

from .transport import API_VERSION, InstallationToken

API_HOST = "api.github.com"
API_PORT = 443
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
OPENSSL = "/usr/bin/openssl"


class AppAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class DryRunAppConfig:
    schema: str
    mode: str
    app_id: int
    installation_id: int
    authorization_repository: str
    authorization_repository_id: int
    owner_login: str
    owner_id: int
    poll_interval_seconds: int
    issue_title_prefix: str
    mutation_dispatch_enabled: bool
    result_writer_enabled: bool


CONFIG_KEYS = frozenset(
    {
        "schema",
        "mode",
        "app_id",
        "installation_id",
        "authorization_repository",
        "authorization_repository_id",
        "owner_login",
        "owner_id",
        "poll_interval_seconds",
        "issue_title_prefix",
        "mutation_dispatch_enabled",
        "result_writer_enabled",
    }
)
CONFIG_SCHEMA = "rozkalns.deploy-executor-p8-dry-run-config.v1"
CONFIG_MODE = "READ_ONLY_DRY_RUN"
EXPECTED_AUTHORIZATION_REPOSITORY = "rozkalnsandris/ops-workflows"
EXPECTED_AUTHORIZATION_REPOSITORY_ID = 1328835922
EXPECTED_OWNER_LOGIN = "rozkalnsandris"
EXPECTED_OWNER_ID = 277435981
EXPECTED_APP_ID = 4748870
EXPECTED_INSTALLATION_ID = 157217641


def _positive_int(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise AppAuthError(f"{name} must be a positive integer")
    return value


def load_dry_run_config(path: str | Path) -> DryRunAppConfig:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AppAuthError("dry-run config is unreadable") from exc
    if type(raw) is not dict or frozenset(raw) != CONFIG_KEYS:
        raise AppAuthError("dry-run config schema mismatch")
    if raw["schema"] != CONFIG_SCHEMA or raw["mode"] != CONFIG_MODE:
        raise AppAuthError("dry-run config identity mismatch")
    if raw["authorization_repository"] != EXPECTED_AUTHORIZATION_REPOSITORY:
        raise AppAuthError("authorization repository is not approved")
    if raw["authorization_repository_id"] != EXPECTED_AUTHORIZATION_REPOSITORY_ID:
        raise AppAuthError("authorization repository id mismatch")
    if raw["owner_login"] != EXPECTED_OWNER_LOGIN or raw["owner_id"] != EXPECTED_OWNER_ID:
        raise AppAuthError("owner identity mismatch")
    if raw["app_id"] != EXPECTED_APP_ID or raw["installation_id"] != EXPECTED_INSTALLATION_ID:
        raise AppAuthError("GitHub App identity mismatch")
    if raw["poll_interval_seconds"] != 120:
        raise AppAuthError("poll interval must remain 120 seconds in P8")
    prefix = raw["issue_title_prefix"]
    if type(prefix) is not str or prefix != "[LIVE-AUTH][PENDING] ":
        raise AppAuthError("LIVE-AUTH title prefix mismatch")
    if raw["mutation_dispatch_enabled"] is not False:
        raise AppAuthError("P8 mutation dispatch must remain disabled")
    if raw["result_writer_enabled"] is not False:
        raise AppAuthError("P8 GitHub result writer must remain disabled")
    return DryRunAppConfig(
        schema=raw["schema"],
        mode=raw["mode"],
        app_id=_positive_int(raw["app_id"], "app_id"),
        installation_id=_positive_int(raw["installation_id"], "installation_id"),
        authorization_repository=raw["authorization_repository"],
        authorization_repository_id=_positive_int(
            raw["authorization_repository_id"], "authorization_repository_id"
        ),
        owner_login=raw["owner_login"],
        owner_id=_positive_int(raw["owner_id"], "owner_id"),
        poll_interval_seconds=_positive_int(raw["poll_interval_seconds"], "poll_interval_seconds"),
        issue_title_prefix=prefix,
        mutation_dispatch_enabled=False,
        result_writer_enabled=False,
    )


def require_private_key(path: str | Path) -> Path:
    key = Path(path)
    if not key.is_absolute():
        raise AppAuthError("private key path must be absolute")
    try:
        info = key.lstat()
    except FileNotFoundError as exc:
        raise AppAuthError("private key is missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise AppAuthError("private key must be a regular non-symlink file")
    if info.st_mode & 0o077:
        raise AppAuthError("private key must not be group/world accessible")
    if info.st_size < 256 or info.st_size > 64 * 1024:
        raise AppAuthError("private key size is outside expected bounds")
    return key


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _parse_server_date(headers: Mapping[str, str]) -> datetime:
    value = None
    for key, candidate in headers.items():
        if key.lower() == "date":
            value = candidate
            break
    if type(value) is not str:
        raise AppAuthError("GitHub response omitted Date header")
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AppAuthError("GitHub Date header is invalid") from exc
    if parsed.tzinfo is None:
        raise AppAuthError("GitHub Date header has no timezone")
    return parsed.astimezone(timezone.utc)


def build_app_jwt(
    *,
    app_id: int,
    server_time: datetime,
    private_key: str | Path,
    signer: Callable[[bytes, Path], bytes] | None = None,
) -> str:
    _positive_int(app_id, "app_id")
    if not isinstance(server_time, datetime) or server_time.tzinfo is None:
        raise AppAuthError("server_time must be timezone-aware")
    key = require_private_key(private_key)
    now = int(server_time.astimezone(timezone.utc).timestamp())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url(
        json.dumps(
            {"iat": now - 60, "exp": now + 300, "iss": app_id},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    unsigned = f"{header}.{payload}".encode("ascii")
    if signer is None:
        signature = _openssl_sign(unsigned, key)
    else:
        signature = signer(unsigned, key)
    if type(signature) is not bytes or not signature:
        raise AppAuthError("JWT signer returned no signature")
    return f"{header}.{payload}.{_b64url(signature)}"


def _openssl_sign(payload: bytes, key: Path) -> bytes:
    try:
        proc = subprocess.run(
            [OPENSSL, "dgst", "-sha256", "-sign", str(key)],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise AppAuthError("openssl JWT signer is unavailable") from exc
    if proc.returncode != 0 or not proc.stdout:
        raise AppAuthError("openssl failed to sign GitHub App JWT")
    return proc.stdout


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: Mapping[str, str]
    value: Any


class Requester(Protocol):
    def __call__(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> RawResponse:
        ...


def https_json_request(
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes | None,
) -> RawResponse:
    if method not in {"GET", "POST"}:
        raise AppAuthError("unsupported GitHub App auth method")
    if type(path) is not str or not path.startswith("/") or "://" in path:
        raise AppAuthError("GitHub App auth path is invalid")
    connection = http.client.HTTPSConnection(API_HOST, API_PORT, timeout=20)
    try:
        connection.request(method, path, body=body, headers=dict(headers))
        response = connection.getresponse()
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise AppAuthError("GitHub App auth response exceeds size limit")
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        try:
            value = json.loads(data.decode("utf-8", "strict")) if data else None
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise AppAuthError("GitHub App auth response is malformed") from exc
        return RawResponse(response.status, response_headers, value)
    except AppAuthError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise AppAuthError("GitHub App auth network request failed") from exc
    finally:
        connection.close()


def _request_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "rozkalns-deploy-executor-p8/1",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _expect_object(response: RawResponse, status: int, where: str) -> dict[str, Any]:
    if response.status != status:
        raise AppAuthError(f"{where} returned HTTP {response.status}")
    if type(response.value) is not dict:
        raise AppAuthError(f"{where} returned a non-object payload")
    return response.value


def validate_installation(payload: Mapping[str, Any], config: DryRunAppConfig) -> None:
    if payload.get("id") != config.installation_id:
        raise AppAuthError("installation id mismatch")
    account = payload.get("account")
    if type(account) is not dict:
        raise AppAuthError("installation account is missing")
    if account.get("id") != config.owner_id or account.get("login") != config.owner_login:
        raise AppAuthError("installation owner mismatch")
    if payload.get("repository_selection") != "selected":
        raise AppAuthError("installation must use selected repositories")
    permissions = payload.get("permissions")
    if type(permissions) is not dict:
        raise AppAuthError("installation permissions are missing")
    normalized = {str(key): str(value) for key, value in permissions.items()}
    if normalized.get("issues") != "read":
        raise AppAuthError("installation Issues permission must be read")
    if set(normalized) - {"issues", "metadata"}:
        raise AppAuthError("installation has unexpected permissions")
    if any(value == "write" for value in normalized.values()):
        raise AppAuthError("installation contains write permission")


def validate_token_response(
    payload: Mapping[str, Any],
    config: DryRunAppConfig,
    *,
    now: datetime,
) -> InstallationToken:
    token = payload.get("token")
    if type(token) is not str or len(token) < 20 or any(char.isspace() for char in token):
        raise AppAuthError("installation token is malformed")
    expires_at = payload.get("expires_at")
    if type(expires_at) is not str:
        raise AppAuthError("installation token expiry is missing")
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppAuthError("installation token expiry is invalid") from exc
    if expiry.tzinfo is None:
        raise AppAuthError("installation token expiry has no timezone")
    expiry = expiry.astimezone(timezone.utc)
    remaining = int((expiry - now.astimezone(timezone.utc)).total_seconds())
    if not 3000 <= remaining <= 3700:
        raise AppAuthError("installation token lifetime is outside expected bounds")
    permissions = payload.get("permissions")
    if type(permissions) is not dict:
        raise AppAuthError("installation token permissions are missing")
    normalized = {str(key): str(value) for key, value in permissions.items()}
    if normalized.get("issues") != "read":
        raise AppAuthError("installation token Issues permission must be read")
    if set(normalized) - {"issues", "metadata"}:
        raise AppAuthError("installation token has unexpected permissions")
    if any(value == "write" for value in normalized.values()):
        raise AppAuthError("installation token contains write permission")
    repositories = payload.get("repositories")
    if type(repositories) is not list:
        raise AppAuthError("installation token repository scope is missing")
    observed = [
        (row.get("id"), row.get("full_name"))
        for row in repositories
        if type(row) is dict
    ]
    expected = [(config.authorization_repository_id, config.authorization_repository)]
    if observed != expected:
        raise AppAuthError("installation token repository scope mismatch")
    return InstallationToken(token, expires_at=expiry)


class GitHubAppInstallationTokenProvider:
    def __init__(
        self,
        *,
        config: DryRunAppConfig,
        private_key: str | Path,
        requester: Requester = https_json_request,
        signer: Callable[[bytes, Path], bytes] | None = None,
    ):
        self.config = config
        self.private_key = require_private_key(private_key)
        self.requester = requester
        self.signer = signer

    def get_installation_token(self) -> InstallationToken:
        clock_response = self.requester("GET", "/", _request_headers(), None)
        if clock_response.status != 200:
            raise AppAuthError(f"GitHub clock probe returned HTTP {clock_response.status}")
        server_time = _parse_server_date(clock_response.headers)
        jwt = build_app_jwt(
            app_id=self.config.app_id,
            server_time=server_time,
            private_key=self.private_key,
            signer=self.signer,
        )
        installation_response = self.requester(
            "GET",
            f"/app/installations/{self.config.installation_id}",
            _request_headers(jwt),
            None,
        )
        installation = _expect_object(
            installation_response, 200, "GitHub App installation probe"
        )
        validate_installation(installation, self.config)
        body = json.dumps(
            {
                "repository_ids": [self.config.authorization_repository_id],
                "permissions": {"issues": "read"},
            },
            separators=(",", ":"),
        ).encode("utf-8")
        token_response = self.requester(
            "POST",
            f"/app/installations/{self.config.installation_id}/access_tokens",
            {
                **_request_headers(jwt),
                "Content-Type": "application/json",
            },
            body,
        )
        token_payload = _expect_object(token_response, 201, "installation token mint")
        return validate_token_response(token_payload, self.config, now=server_time)
