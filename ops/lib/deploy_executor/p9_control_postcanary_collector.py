from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
import http.client
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping, Protocol
import urllib.error
import urllib.request

from .control_center_postcanary_adapter import (
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
    TARGET_REPOSITORY_ID,
    WORKFLOW_SOURCE_BLOB,
)
from .p9_control_postcanary_producer import (
    ControlPostCanaryObservation,
    ControlPostCanaryTargetEvidence,
    TARGET_PROJECT_ID,
    TARGET_REPOSITORY,
    target_github_evidence_failure_code,
)
from .p9_evidence import CONTROL_BASELINE_RESOLVER
from .p9_source_auth import P9SourceInstallationTokenProvider
from .source_evidence import verify_source_evidence
from .transport import (
    ACCEPT_HEADER,
    API_BASE,
    API_VERSION,
    GitHubHttpsSender,
    GitHubRestClient,
    HTTPSender,
)

D1_ACCOUNT_ID = "70e29dbca0e8363358659102d2b74178"
D1_DATABASE_ID = "8504e986-faf0-450c-bfb5-41b5dbf8be09"
D1_API_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{D1_ACCOUNT_ID}"
    f"/d1/database/{D1_DATABASE_ID}/query"
)
DEFAULT_SOURCE_KEY = Path("/root/.config/rozkalns-automation/github-app.pem")
DEFAULT_D1_TOKEN = Path(
    "/root/.config/rozkalns-deploy-executor-p9/control-d1-read-token"
)

AUDIT_SQL = (
    "SELECT request_id, repository, project_id, issue_number, pull_number, "
    "merge_method, expected_head_sha, expected_main_sha, requested_at, state, "
    "outcome_code, mutation_attempted, observed_head_sha, observed_main_sha, "
    "observed_at, merge_sha, completed_at FROM merge_decisions "
    "WHERE request_id = ? LIMIT 2"
)
TARGET_SQL = (
    "SELECT request_id, state, merge_sha FROM merge_decisions "
    "WHERE repository = ? AND pull_number = ? ORDER BY requested_at ASC LIMIT 3"
)
_ALLOWED_SQL = frozenset({AUDIT_SQL, TARGET_SQL})
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_D1_RESPONSE_BYTES = 256 * 1024

# Historical Control Merge canary tuple. These values are source-pinned so the
# evidence collector cannot be redirected to a different run, request, PR or
# D1 row. source_sha remains the separately supplied current/authorized Control
# source identity that the P9 resolver binds to READY/LIVE-AUTH.
PINNED_CANARY_RUN_ID = 33269213486
PINNED_CANARY_SOURCE_SHA = "7890b1b590b75547d4a3fcf4e30a1cdf643d8c12"
PINNED_TARGET_ISSUE_NUMBER = 25
PINNED_TARGET_PR_NUMBER = 24
PINNED_EXPECTED_PR_HEAD = "7cd685c55b8ccba33400b2062ac703cbed668fc5"
PINNED_EXPECTED_OLD_MAIN = "c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8"
PINNED_EXPECTED_MERGE_SHA = "db3b0ff76ee471d3b430e440a14d5cabbb1d99bc"
PINNED_REQUEST_ID = "rcmerge_04b1e930_033d_41eb_8a9a_2d65d91db7b0"


class ControlPostCanaryCollectorError(RuntimeError):
    pass


class JSONReader(Protocol):
    def get_json(self, path_or_url: str): ...


@dataclass(frozen=True)
class ControlPostCanaryCollectionRequest:
    source_sha: str


@dataclass(frozen=True)
class D1SelectResult:
    sql: str
    rows: tuple[Mapping[str, Any], ...]
    success: bool
    result_success: bool
    changed_db: bool
    rows_written: int
    changes: int

    def producer_metadata(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "success": self.success,
            "result_success": self.result_success,
            "changed_db": self.changed_db,
            "rows_written": self.rows_written,
            "changes": self.changes,
        }


class D1Reader(Protocol):
    def select_pinned_request(self) -> D1SelectResult: ...

    def select_pinned_target(self) -> D1SelectResult: ...


D1ClientFactory = Callable[[], D1Reader]


@dataclass(frozen=True)
class _PublicJSONResponse:
    value: Any
    server_time: datetime


class PublicTargetGitHubReader:
    """Unauthenticated GET-only reader pinned to the one public target repository."""

    def __init__(self, *, sender: HTTPSender | None = None):
        self._sender = sender or GitHubHttpsSender()

    @staticmethod
    def _validate_path(path: str) -> None:
        root = f"/repos/{TARGET_REPOSITORY}"
        prefix = root + "/"
        if type(path) is not str or (path != root and not path.startswith(prefix)):
            raise ControlPostCanaryCollectorError("target GitHub path is outside the reviewed repository")
        if "://" in path or any(ch in path for ch in ("\r", "\n", "\x00")):
            raise ControlPostCanaryCollectorError("target GitHub path is invalid")

    def get_json(self, path_or_url: str) -> _PublicJSONResponse:
        self._validate_path(path_or_url)
        response = self._sender.send(
            method="GET",
            url=f"{API_BASE}{path_or_url}",
            headers={
                "Accept": ACCEPT_HEADER,
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "rozkalns-deploy-executor-p9-control-baseline/1",
            },
        )
        if response.status != 200:
            raise ControlPostCanaryCollectorError(
                f"target GitHub read returned HTTP {response.status}"
            )
        date = response.headers.get("date")
        if type(date) is not str:
            raise ControlPostCanaryCollectorError("target GitHub response has no server date")
        try:
            server_time = parsedate_to_datetime(date)
            value = json.loads(response.body.decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ControlPostCanaryCollectorError("target GitHub response is malformed") from exc
        if server_time.tzinfo is None:
            raise ControlPostCanaryCollectorError("target GitHub server date is timezone-naive")
        return _PublicJSONResponse(value=value, server_time=server_time)


D1Requester = Callable[[str, Mapping[str, str], bytes], tuple[int, bytes]]


def _default_d1_requester(
    url: str, headers: Mapping[str, str], body: bytes
) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        method="POST",
        headers=dict(headers),
        data=body,
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(MAX_D1_RESPONSE_BYTES + 1)
            if len(raw) > MAX_D1_RESPONSE_BYTES:
                raise ControlPostCanaryCollectorError("D1 response exceeds size limit")
            return int(response.status), raw
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(MAX_D1_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise ControlPostCanaryCollectorError("D1 read request failed") from exc


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class FixedD1ReadClient:
    """Capability-specific D1 reader exposing only two reviewed SELECT statements."""

    def __init__(
        self,
        *,
        api_token: str,
        requester: D1Requester | None = None,
    ):
        if type(api_token) is not str or len(api_token) < 20 or any(ch.isspace() for ch in api_token):
            raise ControlPostCanaryCollectorError("D1 read token is missing or malformed")
        self._token = api_token
        self._requester = requester or _default_d1_requester

    def _query(self, sql: str, params: tuple[Any, ...]) -> D1SelectResult:
        if sql not in _ALLOWED_SQL or not sql.startswith("SELECT "):
            raise ControlPostCanaryCollectorError("D1 SQL is outside the reviewed SELECT allowlist")
        body = json.dumps(
            {"sql": sql, "params": list(params)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        status, raw = self._requester(
            D1_API_URL,
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "rozkalns-deploy-executor-p9-control-baseline/1",
            },
            body,
        )
        if status != 200 or len(raw) > MAX_D1_RESPONSE_BYTES:
            raise ControlPostCanaryCollectorError(f"D1 read returned HTTP {status}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ControlPostCanaryCollectorError("D1 response is malformed") from exc
        if type(payload) is not dict or payload.get("success") is not True:
            raise ControlPostCanaryCollectorError("D1 outer response is unsuccessful")
        result = payload.get("result")
        if type(result) is not list or len(result) != 1 or type(result[0]) is not dict:
            raise ControlPostCanaryCollectorError("D1 result shape is unexpected")
        item = result[0]
        meta = item.get("meta")
        rows = item.get("results")
        if type(meta) is not dict or type(rows) is not list or any(type(row) is not dict for row in rows):
            raise ControlPostCanaryCollectorError("D1 result metadata/rows are malformed")
        values = D1SelectResult(
            sql=sql,
            rows=tuple(rows),
            success=True,
            result_success=item.get("success") is True,
            changed_db=meta.get("changed_db"),
            rows_written=meta.get("rows_written"),
            changes=meta.get("changes"),
        )
        if (
            values.result_success is not True
            or values.changed_db is not False
            or type(values.rows_written) is not int
            or values.rows_written != 0
            or type(values.changes) is not int
            or values.changes != 0
        ):
            raise ControlPostCanaryCollectorError("D1 SELECT did not prove zero-write semantics")
        return values

    def select_pinned_request(self) -> D1SelectResult:
        return self._query(AUDIT_SQL, (PINNED_REQUEST_ID,))

    def select_pinned_target(self) -> D1SelectResult:
        return self._query(TARGET_SQL, (TARGET_REPOSITORY, PINNED_TARGET_PR_NUMBER))


def _positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        raise ControlPostCanaryCollectorError(f"{where} must be a positive integer")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or SHA40_RE.fullmatch(value) is None:
        raise ControlPostCanaryCollectorError(f"{where} must be a lowercase 40-character SHA")
    return value


def _validate_request_id(value: Any) -> str:
    if type(value) is not str or _REQUEST_ID_RE.fullmatch(value) is None:
        raise ControlPostCanaryCollectorError("request_id is outside the reviewed identifier grammar")
    return value


def validate_collection_request(
    request: ControlPostCanaryCollectionRequest,
) -> ControlPostCanaryCollectionRequest:
    if not isinstance(request, ControlPostCanaryCollectionRequest):
        raise ControlPostCanaryCollectorError("collection request has the wrong type")
    _sha(request.source_sha, "source_sha")
    return request


def _dict(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ControlPostCanaryCollectorError(f"{where} is not an object")
    return value


def _list_of_dicts(value: Any, where: str) -> tuple[dict[str, Any], ...]:
    if type(value) is not list or any(type(row) is not dict for row in value):
        raise ControlPostCanaryCollectorError(f"{where} is not an object list")
    return tuple(value)


def collect_control_postcanary_observation(
    request: ControlPostCanaryCollectionRequest,
    *,
    source_client: JSONReader,
    target_client: JSONReader,
    d1_client_factory: D1ClientFactory | None = None,
) -> ControlPostCanaryObservation:
    request = validate_collection_request(request)
    _positive_int(PINNED_CANARY_RUN_ID, "PINNED_CANARY_RUN_ID")
    _positive_int(PINNED_TARGET_ISSUE_NUMBER, "PINNED_TARGET_ISSUE_NUMBER")
    _positive_int(PINNED_TARGET_PR_NUMBER, "PINNED_TARGET_PR_NUMBER")
    _sha(PINNED_CANARY_SOURCE_SHA, "PINNED_CANARY_SOURCE_SHA")
    _sha(PINNED_EXPECTED_PR_HEAD, "PINNED_EXPECTED_PR_HEAD")
    _sha(PINNED_EXPECTED_OLD_MAIN, "PINNED_EXPECTED_OLD_MAIN")
    _sha(PINNED_EXPECTED_MERGE_SHA, "PINNED_EXPECTED_MERGE_SHA")
    _validate_request_id(PINNED_REQUEST_ID)

    source = verify_source_evidence(
        source_client,
        source_repository=SOURCE_REPOSITORY,
        source_sha=request.source_sha,
    )
    if source.repository != SOURCE_REPOSITORY or source.source_sha != request.source_sha:
        raise ControlPostCanaryCollectorError("Control source verification returned unexpected identity")

    canary_response = source_client.get_json(
        f"/repos/{SOURCE_REPOSITORY}/actions/runs/{PINNED_CANARY_RUN_ID}"
    )
    canary = _dict(canary_response.value, "canary run")
    observed_at = getattr(canary_response, "server_time", None)
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
        raise ControlPostCanaryCollectorError("canary observation lacks trusted GitHub server time")

    jobs_payload = _dict(
        source_client.get_json(
            f"/repos/{SOURCE_REPOSITORY}/actions/runs/{PINNED_CANARY_RUN_ID}/jobs"
            "?filter=latest&per_page=100"
        ).value,
        "canary jobs response",
    )
    canary_jobs = _list_of_dicts(jobs_payload.get("jobs"), "canary jobs")

    target_repository = _dict(
        target_client.get_json(f"/repos/{TARGET_REPOSITORY}").value,
        "target repository",
    )
    if (
        target_repository.get("id") != TARGET_REPOSITORY_ID
        or target_repository.get("full_name") != TARGET_REPOSITORY
        or target_repository.get("default_branch") != "main"
    ):
        raise ControlPostCanaryCollectorError("target repository identity drifted")

    target_issue = _dict(
        target_client.get_json(
            f"/repos/{TARGET_REPOSITORY}/issues/{PINNED_TARGET_ISSUE_NUMBER}"
        ).value,
        "target issue",
    )
    target_pr = _dict(
        target_client.get_json(
            f"/repos/{TARGET_REPOSITORY}/pulls/{PINNED_TARGET_PR_NUMBER}"
        ).value,
        "target pull request",
    )
    target_merge_commit = _dict(
        target_client.get_json(
            f"/repos/{TARGET_REPOSITORY}/commits/{PINNED_EXPECTED_MERGE_SHA}"
        ).value,
        "target merge commit",
    )
    target_compare = _dict(
        target_client.get_json(
            f"/repos/{TARGET_REPOSITORY}/compare/{PINNED_EXPECTED_MERGE_SHA}...main"
        ).value,
        "target compare",
    )

    target_evidence = ControlPostCanaryTargetEvidence(
        target_issue_number=PINNED_TARGET_ISSUE_NUMBER,
        target_issue=target_issue,
        target_pr_number=PINNED_TARGET_PR_NUMBER,
        target_pr=target_pr,
        expected_pr_head=PINNED_EXPECTED_PR_HEAD,
        expected_old_main=PINNED_EXPECTED_OLD_MAIN,
        expected_merge_sha=PINNED_EXPECTED_MERGE_SHA,
        target_merge_commit=target_merge_commit,
        target_compare=target_compare,
    )
    target_failure = target_github_evidence_failure_code(target_evidence)
    if target_failure is not None:
        raise ControlPostCanaryCollectorError(
            "target GitHub semantic validation failed before D1: "
            f"{target_failure}"
        )

    d1_client = (
        d1_client_factory()
        if d1_client_factory is not None
        else FixedD1ReadClient(api_token=read_fixed_d1_token())
    )
    audit = d1_client.select_pinned_request()
    target = d1_client.select_pinned_target()

    return ControlPostCanaryObservation(
        observed_at=observed_at,
        resolver_id=CONTROL_BASELINE_RESOLVER,
        target_alias=TARGET_ALIAS,
        source_repository=SOURCE_REPOSITORY,
        source_sha=request.source_sha,
        workflow_source_blob=WORKFLOW_SOURCE_BLOB,
        canary_run_id=PINNED_CANARY_RUN_ID,
        canary_source_sha=PINNED_CANARY_SOURCE_SHA,
        canary_run=canary,
        canary_jobs=canary_jobs,
        target_issue_number=PINNED_TARGET_ISSUE_NUMBER,
        target_issue=target_issue,
        target_pr_number=PINNED_TARGET_PR_NUMBER,
        target_pr=target_pr,
        expected_pr_head=PINNED_EXPECTED_PR_HEAD,
        expected_old_main=PINNED_EXPECTED_OLD_MAIN,
        expected_merge_sha=PINNED_EXPECTED_MERGE_SHA,
        target_merge_commit=target_merge_commit,
        target_compare=target_compare,
        request_id=PINNED_REQUEST_ID,
        audit_rows=audit.rows,
        target_audit_rows=target.rows,
        d1_selects=(audit.producer_metadata(), target.producer_metadata()),
        observed_mutation_classes=(),
    )


def build_source_client(
    *, source_private_key: str | Path = DEFAULT_SOURCE_KEY, sender: HTTPSender | None = None
) -> GitHubRestClient:
    provider = P9SourceInstallationTokenProvider(
        repository=SOURCE_REPOSITORY,
        private_key=source_private_key,
    )
    return GitHubRestClient(
        token_provider=provider,
        sender=sender or GitHubHttpsSender(),
    )


def read_fixed_d1_token(path: str | Path | None = None) -> str:
    token_path = DEFAULT_D1_TOKEN if path is None else Path(path)
    if token_path != DEFAULT_D1_TOKEN:
        raise ControlPostCanaryCollectorError("D1 token path is not the reviewed fixed path")
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        if type(getattr(os, name, None)) is not int:
            raise ControlPostCanaryCollectorError("required credential open guard is unavailable")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(token_path, flags)
    except OSError as exc:
        raise ControlPostCanaryCollectorError("D1 read token is unavailable") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ControlPostCanaryCollectorError("D1 read token must be a regular file")
        if before.st_uid != 0 or stat.S_IMODE(before.st_mode) not in {0o400, 0o600}:
            raise ControlPostCanaryCollectorError("D1 read token ownership/mode mismatch")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(4097 - total, 4097))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > 4096:
                raise ControlPostCanaryCollectorError("D1 read token exceeds size limit")
        raw = b"".join(chunks)
        after = os.fstat(fd)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_size != len(raw)
        ):
            raise ControlPostCanaryCollectorError("D1 read token changed during read")
    finally:
        os.close(fd)
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ControlPostCanaryCollectorError("D1 read token is not UTF-8") from exc
    if len(value) < 20 or any(ch.isspace() for ch in value):
        raise ControlPostCanaryCollectorError("D1 read token is malformed")
    return value
