from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    AcceptedAuthorization,
    accept_issue,
    verify_authorization_unchanged,
)

API_BASE = "https://api.github.com"
API_VERSION = "2026-03-10"
ACCEPT_HEADER = "application/vnd.github+json"
USER_AGENT = "rozkalns-deploy-executor/1"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ETAG_BYTES = 512
MAX_ETAG_ENTRIES = 1024
DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_ITEMS = 1000
DEFAULT_TRANSPORT_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = (1.0, 2.0)
MAX_REDIRECTS = 3
TRANSIENT_STATUSES = frozenset({502, 503, 504})
REDIRECT_STATUSES = frozenset({301, 302, 307, 308})
CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
SAFE_LOG_FIELDS = frozenset(
    {
        "method",
        "path",
        "status",
        "attempt",
        "retry_in",
        "not_modified",
        "page",
        "item_count",
        "error_class",
    }
)


class GitHubTransportError(RuntimeError):
    pass


class NetworkFailure(GitHubTransportError):
    pass


class TokenError(GitHubTransportError):
    pass


class CacheIntegrityError(GitHubTransportError):
    pass


class ResponseError(GitHubTransportError):
    pass


class HTTPStatusError(GitHubTransportError):
    def __init__(self, status: int):
        super().__init__(f"GitHub API returned HTTP {status}")
        self.status = status


class RateLimitError(GitHubTransportError):
    def __init__(self, status: int, retry_after_seconds: int):
        super().__init__(f"GitHub API rate limited request; retry after {retry_after_seconds}s")
        self.status = status
        self.retry_after_seconds = retry_after_seconds


class RedirectError(GitHubTransportError):
    pass


class PaginationError(GitHubTransportError):
    pass


class IdentityError(GitHubTransportError):
    pass


class ResultReportingDisabled(GitHubTransportError):
    pass


@dataclass(frozen=True, repr=False)
class InstallationToken:
    """Opaque short-lived installation token supplied by a separately trusted provider."""

    value: str
    expires_at: datetime | None = None

    def __repr__(self) -> str:
        expiry = self.expires_at.isoformat() if self.expires_at is not None else None
        return f"InstallationToken(value=<redacted>, expires_at={expiry!r})"


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class JSONResponse:
    value: Any | None
    server_time: datetime
    etag: str | None
    not_modified: bool
    url: str
    next_url: str | None


class InstallationTokenProvider(Protocol):
    def get_installation_token(self) -> InstallationToken:
        ...


class HTTPSender(Protocol):
    def send(self, *, method: str, url: str, headers: Mapping[str, str]) -> HTTPResponse:
        ...


class EventLogger(Protocol):
    def emit(self, event: str, **fields: object) -> None:
        ...


class ResultWriter(Protocol):
    """Future non-authority receipt-channel abstraction.

    P2 deliberately has no GitHub write implementation. A later writer must be
    separately reviewed and must never mutate the LIVE-AUTH authority surface.
    """

    def write_result(self, receipt: Mapping[str, Any]) -> None:
        ...


class DisabledResultWriter:
    def write_result(self, receipt: Mapping[str, Any]) -> None:
        raise ResultReportingDisabled(
            "automatic GitHub result reporting is disabled until a separate non-authority channel is reviewed"
        )


class NullLogger:
    def emit(self, event: str, **fields: object) -> None:
        return None


class PersistentETagStore:
    """Public-safe conditional-GET cache; never an authority source."""

    SCHEMA = "rozkalns.github-etag-cache.v1"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries: dict[str, str] = {}
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CacheIntegrityError("ETag cache is unreadable") from exc
        if type(payload) is not dict or set(payload) != {"schema", "entries"}:
            raise CacheIntegrityError("ETag cache schema mismatch")
        if payload["schema"] != self.SCHEMA or type(payload["entries"]) is not dict:
            raise CacheIntegrityError("ETag cache schema mismatch")
        if len(payload["entries"]) > MAX_ETAG_ENTRIES:
            raise CacheIntegrityError("ETag cache entry limit exceeded")
        entries: dict[str, str] = {}
        for key, value in payload["entries"].items():
            if type(key) is not str or not _is_sha256(key):
                raise CacheIntegrityError("ETag cache key is invalid")
            entries[key] = _validate_etag(value)
        self._entries = entries

    def get(self, url: str) -> str | None:
        return self._entries.get(_url_cache_key(url))

    def put(self, url: str, etag: str) -> None:
        key = _url_cache_key(url)
        if key not in self._entries and len(self._entries) >= MAX_ETAG_ENTRIES:
            raise CacheIntegrityError("ETag cache entry limit exceeded")
        self._entries[key] = _validate_etag(etag)
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": self.SCHEMA, "entries": dict(sorted(self._entries.items()))}
        encoded = (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        ).encode("utf-8")
        fd, temp_path = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


class GitHubHttpsSender:
    """Host-pinned HTTPS sender. Redirect validation belongs to GitHubRestClient."""

    def __init__(self, *, timeout_seconds: float = 15.0, max_body_bytes: int = MAX_RESPONSE_BYTES):
        self.timeout_seconds = timeout_seconds
        self.max_body_bytes = max_body_bytes

    def send(self, *, method: str, url: str, headers: Mapping[str, str]) -> HTTPResponse:
        parsed = _validate_api_url(url)
        target = urlunsplit(("", "", parsed.path, parsed.query, ""))
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            port=parsed.port,
            timeout=self.timeout_seconds,
        )
        try:
            connection.request(method, target, headers=dict(headers))
            response = connection.getresponse()
            body = response.read(self.max_body_bytes + 1)
            if len(body) > self.max_body_bytes:
                raise ResponseError("GitHub API response exceeds configured size limit")
            response_headers = {key.lower(): value for key, value in response.getheaders()}
            return HTTPResponse(status=response.status, headers=response_headers, body=body)
        except ResponseError:
            raise
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            raise NetworkFailure(type(exc).__name__) from None
        finally:
            connection.close()


class GitHubRestClient:
    def __init__(
        self,
        *,
        token_provider: InstallationTokenProvider,
        sender: HTTPSender,
        etag_store: PersistentETagStore | None = None,
        logger: EventLogger | None = None,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] | None = None,
        max_transport_attempts: int = DEFAULT_TRANSPORT_ATTEMPTS,
        backoff_seconds: Sequence[float] = DEFAULT_BACKOFF_SECONDS,
    ):
        if type(max_transport_attempts) is not int or not 1 <= max_transport_attempts <= 5:
            raise ValueError("max_transport_attempts must be in range 1..5")
        if len(backoff_seconds) < max_transport_attempts - 1:
            raise ValueError("backoff_seconds does not cover configured attempts")
        self.token_provider = token_provider
        self.sender = sender
        self.etag_store = etag_store
        self.logger = logger or NullLogger()
        self.sleeper = sleeper or (lambda _seconds: None)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_transport_attempts = max_transport_attempts
        self.backoff_seconds = tuple(float(value) for value in backoff_seconds)

    def get_json(self, path_or_url: str) -> JSONResponse:
        """Authoritative fresh GET. This method never sends If-None-Match."""
        return self._get_json(path_or_url, conditional=False)

    def conditional_get_json(self, path_or_url: str) -> JSONResponse:
        """Polling optimization only; 304 is never sufficient for mutation revalidation."""
        if self.etag_store is None:
            raise CacheIntegrityError("conditional GET requires an ETag store")
        return self._get_json(path_or_url, conditional=True)

    def get_paginated(
        self,
        path_or_url: str,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_items: int = DEFAULT_MAX_ITEMS,
    ) -> list[Any]:
        if type(max_pages) is not int or not 1 <= max_pages <= 100:
            raise ValueError("max_pages must be in range 1..100")
        if type(max_items) is not int or not 1 <= max_items <= 10_000:
            raise ValueError("max_items must be in range 1..10000")
        url = _coerce_api_url(path_or_url)
        seen: set[str] = set()
        items: list[Any] = []
        for page in range(1, max_pages + 1):
            if url in seen:
                raise PaginationError("pagination loop detected")
            seen.add(url)
            response = self.get_json(url)
            if type(response.value) is not list:
                raise PaginationError("paginated endpoint did not return a JSON array")
            if len(items) + len(response.value) > max_items:
                raise PaginationError("paginated result exceeds max_items")
            items.extend(response.value)
            self._log("github_page", page=page, item_count=len(response.value), path=_log_path(url))
            if response.next_url is None:
                return items
            url = response.next_url
        raise PaginationError("paginated result exceeds max_pages")

    def read_live_auth(
        self,
        issue_number: int,
        *,
        governance_ok: bool,
        approved_operator_app_ids: frozenset[int] = frozenset(),
    ) -> AcceptedAuthorization:
        repository = self.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}")
        repository_id = _validate_repository_identity(repository.value)
        issue_response = self.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{_positive_issue_number(issue_number)}"
        )
        issue = _validate_issue_response_identity(issue_response.value, issue_number)
        return accept_issue(
            issue,
            repository_id=repository_id,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=issue_response.server_time,
            governance_ok=governance_ok,
            approved_operator_app_ids=approved_operator_app_ids,
        )

    def verify_live_auth_unchanged(
        self,
        accepted: AcceptedAuthorization,
        *,
        governance_ok: bool,
        approved_operator_app_ids: frozenset[int] = frozenset(),
    ) -> None:
        repository = self.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}")
        if _validate_repository_identity(repository.value) != accepted.repository_id:
            raise IdentityError("authorization repository identity drifted")
        issue_response = self.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{accepted.issue_number}"
        )
        issue = _validate_issue_response_identity(issue_response.value, accepted.issue_number)
        verify_authorization_unchanged(
            accepted,
            issue,
            server_time=issue_response.server_time,
            governance_ok=governance_ok,
            approved_operator_app_ids=approved_operator_app_ids,
        )

    def _get_json(self, path_or_url: str, *, conditional: bool) -> JSONResponse:
        url = _coerce_api_url(path_or_url)
        headers = self._base_headers()
        if conditional and self.etag_store is not None:
            etag = self.etag_store.get(url)
            if etag is not None:
                headers["If-None-Match"] = etag
        response, final_url = self._request("GET", url, headers)
        response_headers = _normalize_headers(response.headers)
        server_time = _parse_server_date(response_headers)
        link = response_headers.get("link")
        next_url = _parse_next_link_value(link) if link else None
        if response.status == 304:
            if not conditional:
                raise ResponseError("unexpected 304 for authoritative fresh GET")
            self._log(
                "github_get",
                method="GET",
                path=_log_path(final_url),
                status=304,
                not_modified=True,
            )
            return JSONResponse(
                value=None,
                server_time=server_time,
                etag=response_headers.get("etag"),
                not_modified=True,
                url=final_url,
                next_url=next_url,
            )
        if response.status != 200:
            raise HTTPStatusError(response.status)
        etag = response_headers.get("etag")
        if conditional and etag is not None and self.etag_store is not None:
            self.etag_store.put(final_url, etag)
        try:
            value = json.loads(response.body.decode("utf-8", "strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ResponseError("GitHub API returned malformed JSON") from exc
        self._log(
            "github_get",
            method="GET",
            path=_log_path(final_url),
            status=200,
            not_modified=False,
        )
        return JSONResponse(
            value=value,
            server_time=server_time,
            etag=etag,
            not_modified=False,
            url=final_url,
            next_url=next_url,
        )

    def _base_headers(self) -> dict[str, str]:
        token = self._read_token()
        return {
            "Accept": ACCEPT_HEADER,
            "Authorization": f"Bearer {token.value}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }

    def _read_token(self) -> InstallationToken:
        try:
            token = self.token_provider.get_installation_token()
        except Exception as exc:
            self._log("token_error", error_class=type(exc).__name__)
            raise TokenError("installation token provider failed") from None
        if not isinstance(token, InstallationToken):
            raise TokenError("installation token provider returned wrong type")
        if type(token.value) is not str or not token.value or len(token.value) > 16_384:
            raise TokenError("installation token is malformed")
        if CONTROL_CHAR_RE.search(token.value):
            raise TokenError("installation token contains control characters")
        if token.expires_at is not None:
            if not isinstance(token.expires_at, datetime) or token.expires_at.tzinfo is None:
                raise TokenError("installation token expiry must be timezone-aware")
            if token.expires_at.astimezone(timezone.utc) <= self.clock().astimezone(timezone.utc):
                raise TokenError("installation token is expired")
        return token

    def _request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
    ) -> tuple[HTTPResponse, str]:
        current_url = _coerce_api_url(url)
        active_headers = dict(headers)
        redirects = 0
        attempt = 1
        while True:
            try:
                response = self.sender.send(method=method, url=current_url, headers=active_headers)
            except NetworkFailure as exc:
                if attempt >= self.max_transport_attempts:
                    self._log(
                        "github_transport_error",
                        method=method,
                        path=_log_path(current_url),
                        attempt=attempt,
                        error_class=type(exc).__name__,
                    )
                    raise NetworkFailure("GitHub API network request failed") from None
                delay = self.backoff_seconds[attempt - 1]
                self._log(
                    "github_transport_retry",
                    method=method,
                    path=_log_path(current_url),
                    attempt=attempt,
                    retry_in=delay,
                    error_class=type(exc).__name__,
                )
                self.sleeper(delay)
                attempt += 1
                continue
            if len(response.body) > MAX_RESPONSE_BYTES:
                raise ResponseError("GitHub API response exceeds configured size limit")
            normalized = _normalize_headers(response.headers)
            if response.status in REDIRECT_STATUSES:
                location = normalized.get("location")
                if location is None:
                    raise RedirectError("GitHub API redirect omitted Location")
                redirects += 1
                if redirects > MAX_REDIRECTS:
                    raise RedirectError("GitHub API redirect limit exceeded")
                current_url = _coerce_api_url(location)
                active_headers.pop("If-None-Match", None)
                continue
            if _is_rate_limited(response.status, normalized, response.body):
                retry_after = _rate_limit_delay(normalized, _parse_server_date(normalized))
                self._log(
                    "github_rate_limited",
                    method=method,
                    path=_log_path(current_url),
                    status=response.status,
                    retry_in=retry_after,
                )
                raise RateLimitError(response.status, retry_after)
            if response.status in TRANSIENT_STATUSES:
                if attempt >= self.max_transport_attempts:
                    raise HTTPStatusError(response.status)
                delay = self.backoff_seconds[attempt - 1]
                self._log(
                    "github_transport_retry",
                    method=method,
                    path=_log_path(current_url),
                    status=response.status,
                    attempt=attempt,
                    retry_in=delay,
                )
                self.sleeper(delay)
                attempt += 1
                continue
            return response, current_url

    def _log(self, event: str, **fields: object) -> None:
        if any(key not in SAFE_LOG_FIELDS for key in fields):
            raise AssertionError("attempted to log a non-allowlisted field")
        safe: dict[str, object] = {}
        for key, value in fields.items():
            safe[key] = value if isinstance(value, (str, int, float, bool)) or value is None else type(value).__name__
        self.logger.emit(event, **safe)


def _normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in headers.items()
        if type(key) is str and type(value) is str
    }


def _coerce_api_url(path_or_url: str) -> str:
    if type(path_or_url) is not str or not path_or_url:
        raise ResponseError("GitHub API path/URL must be a non-empty string")
    if path_or_url.startswith("/"):
        return API_BASE + path_or_url
    _validate_api_url(path_or_url)
    return path_or_url


def _validate_api_url(url: str):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise RedirectError("GitHub API URL must stay on https://api.github.com")
    if parsed.username is not None or parsed.password is not None:
        raise RedirectError("GitHub API URL must not contain userinfo")
    if parsed.port not in (None, 443):
        raise RedirectError("GitHub API URL uses an unexpected port")
    if not parsed.path.startswith("/") or parsed.fragment:
        raise RedirectError("GitHub API URL path/fragment is invalid")
    return parsed


def _log_path(url: str) -> str:
    return urlsplit(url).path


def _parse_server_date(headers: Mapping[str, str]) -> datetime:
    value = _normalize_headers(headers).get("date")
    if value is None:
        raise ResponseError("GitHub API response omitted Date header")
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResponseError("GitHub API Date header is malformed") from exc
    if parsed.tzinfo is None:
        raise ResponseError("GitHub API Date header is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def _validate_etag(value: Any) -> str:
    if type(value) is not str or not value:
        raise CacheIntegrityError("ETag is malformed")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise CacheIntegrityError("ETag is malformed") from exc
    if len(encoded) > MAX_ETAG_BYTES or CONTROL_CHAR_RE.search(value):
        raise CacheIntegrityError("ETag is malformed")
    return value


def _url_cache_key(url: str) -> str:
    return hashlib.sha256(_coerce_api_url(url).encode("utf-8")).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _is_rate_limited(status: int, headers: Mapping[str, str], body: bytes) -> bool:
    if status == 429:
        return True
    if status != 403:
        return False
    if "retry-after" in headers or headers.get("x-ratelimit-remaining") == "0":
        return True
    try:
        payload = json.loads(body.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError):
        return False
    if type(payload) is not dict or type(payload.get("message")) is not str:
        return False
    message = payload["message"].lower()
    return "rate limit" in message or "abuse detection" in message


def _rate_limit_delay(headers: Mapping[str, str], server_time: datetime) -> int:
    retry_after = headers.get("retry-after")
    if retry_after is not None:
        try:
            value = int(retry_after)
        except ValueError:
            value = 60
        return min(max(value, 1), 3600)
    reset = headers.get("x-ratelimit-reset")
    if reset is not None:
        try:
            reset_epoch = int(reset)
        except ValueError:
            return 60
        return min(max(reset_epoch - int(server_time.timestamp()), 1), 3600)
    return 60


def _parse_next_link_value(value: str) -> str | None:
    for part in value.split(","):
        section = part.strip()
        if ";" not in section:
            continue
        target, *params = [item.strip() for item in section.split(";")]
        if not (target.startswith("<") and target.endswith(">")):
            continue
        rels: set[str] = set()
        for param in params:
            if param.startswith("rel="):
                rels.update(param[4:].strip().strip('"').split())
        if "next" in rels:
            return _coerce_api_url(target[1:-1])
    return None


def _positive_issue_number(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 2_147_483_647:
        raise IdentityError("issue number must be a positive integer")
    return value


def _validate_repository_identity(value: Any) -> int:
    if type(value) is not dict:
        raise IdentityError("repository response must be a JSON object")
    if value.get("id") != AUTHORIZATION_REPOSITORY_ID:
        raise IdentityError("authorization repository numeric identity mismatch")
    if value.get("full_name") != AUTHORIZATION_REPOSITORY:
        raise IdentityError("authorization repository name mismatch")
    return AUTHORIZATION_REPOSITORY_ID


def _validate_issue_response_identity(value: Any, issue_number: int) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise IdentityError("issue response must be a JSON object")
    if value.get("number") != _positive_issue_number(issue_number):
        raise IdentityError("GitHub issue number mismatch")
    expected = f"{API_BASE}/repos/{AUTHORIZATION_REPOSITORY}"
    if value.get("repository_url") != expected:
        raise IdentityError("GitHub issue repository_url mismatch")
    return value
