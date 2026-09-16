from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import socket
import tempfile
from typing import Any, Callable, Mapping

from .dispatch_contract import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    SCHEMA as DISPATCH_SCHEMA,
    DispatchRequest,
    parse_dispatch_request,
)
from .p9_runtime import P9ExecutorInstallationTokenProvider
from .transport import GitHubHttpsSender, GitHubRestClient
from .weather_operator_upgrade_v7_host_capability import (
    AUTH_END,
    AUTH_START,
    AUTH_TITLE,
    WeatherV7HostCapabilityError,
    parse_authorization_issue,
)

ISSUE = 591
SOCKET_PATH = Path("/run/rozkalns-weather-operator-v7-capability/request.sock")
STATE_DIR = Path("/var/lib/rozkalns-weather-operator-v7-dispatch-caller")
ATTEMPT_LEDGER = STATE_DIR / "attempted.json"
MAX_OPEN_ISSUES = 100
MAX_REQUEST_BYTES = 4096
MAX_RESPONSE_BYTES = 16384
LEDGER_SCHEMA = "rozkalns.rpi5-main.weather-v7-dispatch-caller-attempt-ledger.v1"
RESULT_SCHEMA = "rozkalns.rpi5-main.weather-v7-dispatch-caller-result.v1"
_REQUEST_ID_RE = re.compile(
    re.escape(AUTH_START)
    + r"\n```json\n(?P<payload>.*?)\n```\n"
    + re.escape(AUTH_END),
    re.DOTALL,
)


class WeatherV7DispatchCallerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    request: DispatchRequest
    server_time: datetime


def _fail(message: str) -> None:
    raise WeatherV7DispatchCallerError(message)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate authorization JSON key")
        result[key] = value
    return result


def _request_id_from_body(body: Any) -> str:
    if type(body) is not str or body.count(AUTH_START) != 1 or body.count(AUTH_END) != 1:
        _fail("authorization body markers are invalid")
    match = _REQUEST_ID_RE.search(body)
    if match is None:
        _fail("authorization payload block is malformed")
    try:
        payload = json.loads(match.group("payload"), object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WeatherV7DispatchCallerError("authorization payload JSON is malformed") from exc
    if type(payload) is not dict:
        _fail("authorization payload is not an object")
    request_id = payload.get("request_id")
    if type(request_id) is not str:
        _fail("authorization request_id is unavailable")
    return request_id


def _candidate_request(issue: Mapping[str, Any], *, server_time: datetime) -> DispatchRequest:
    if type(issue) is not dict:
        _fail("authorization issue is malformed")
    request = parse_dispatch_request(
        {
            "schema": DISPATCH_SCHEMA,
            "authorization_repository": AUTHORIZATION_REPOSITORY,
            "authorization_repository_id": AUTHORIZATION_REPOSITORY_ID,
            "authorization_issue_id": issue.get("id"),
            "authorization_issue_number": issue.get("number"),
            "request_id": _request_id_from_body(issue.get("body")),
        }
    )
    parse_authorization_issue(issue, server_time=server_time, request=request)
    return request


def discover_candidate(client: GitHubRestClient) -> Candidate | None:
    repository = client.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}")
    repo = repository.value
    if (
        type(repo) is not dict
        or repo.get("id") != AUTHORIZATION_REPOSITORY_ID
        or repo.get("full_name") != AUTHORIZATION_REPOSITORY
    ):
        _fail("authorization repository identity drifted")
    response = client.get_json(
        f"/repos/{AUTHORIZATION_REPOSITORY}/issues"
        f"?state=open&per_page={MAX_OPEN_ISSUES}&sort=created&direction=desc"
    )
    if response.next_url is not None:
        _fail("authorization issue set exceeds bounded first page")
    if not isinstance(response.server_time, datetime) or response.server_time.tzinfo is None:
        _fail("GitHub server time is unavailable")
    rows = response.value
    if type(rows) is not list:
        _fail("authorization issue poll returned a non-array payload")
    candidates = []
    for row in rows:
        if type(row) is not dict:
            _fail("authorization issue poll contains malformed item")
        if "pull_request" not in row and row.get("title") == AUTH_TITLE:
            candidates.append(row)
    if not candidates:
        return None
    if len(candidates) != 1:
        _fail("authorization issue identity is ambiguous")
    return Candidate(
        request=_candidate_request(candidates[0], server_time=response.server_time),
        server_time=response.server_time,
    )


def _validate_state_dir(path: Path) -> None:
    if not path.is_absolute():
        _fail("state directory must be absolute")
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise WeatherV7DispatchCallerError(
            "state directory is missing; systemd StateDirectory must create it"
        ) from exc
    if not path.is_dir() or path.is_symlink():
        _fail("state directory must be a real directory")
    if info.st_mode & 0o077:
        _fail("state directory must not be group/world accessible")


def _load_attempted(path: Path) -> dict[str, int]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WeatherV7DispatchCallerError("attempt ledger is unreadable") from exc
    if type(raw) is not dict or set(raw) != {"schema", "attempted"}:
        _fail("attempt ledger schema drifted")
    if raw["schema"] != LEDGER_SCHEMA or type(raw["attempted"]) is not dict:
        _fail("attempt ledger payload drifted")
    attempted: dict[str, int] = {}
    for request_id, issue_number in raw["attempted"].items():
        if type(request_id) is not str or type(issue_number) is not int or issue_number < 1:
            _fail("attempt ledger entry is malformed")
        attempted[request_id] = issue_number
    if len(attempted) > 256:
        _fail("attempt ledger exceeds bounded capacity")
    return attempted


def _mark_attempted(path: Path, request: DispatchRequest) -> None:
    attempted = _load_attempted(path)
    if request.request_id in attempted:
        return
    if len(attempted) >= 256:
        _fail("attempt ledger is full")
    attempted[request.request_id] = request.authorization_issue_number
    payload = (
        json.dumps(
            {"schema": LEDGER_SCHEMA, "attempted": attempted},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".attempted.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _request_payload(request: DispatchRequest) -> bytes:
    raw = (
        json.dumps(
            {
                "schema": DISPATCH_SCHEMA,
                "authorization_repository": request.authorization_repository,
                "authorization_repository_id": request.authorization_repository_id,
                "authorization_issue_id": request.authorization_issue_id,
                "authorization_issue_number": request.authorization_issue_number,
                "request_id": request.request_id,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("utf-8")
    if len(raw) > MAX_REQUEST_BYTES:
        _fail("identity-only dispatch request exceeds fixed maximum")
    return raw


def dispatch_to_broker(
    request: DispatchRequest,
    *,
    socket_path: Path = SOCKET_PATH,
) -> Mapping[str, Any]:
    payload = _request_payload(request)
    chunks: list[bytes] = []
    total = 0
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(30.0)
            client.connect(str(socket_path))
            client.sendall(payload)
            client.shutdown(socket.SHUT_WR)
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    _fail("broker response exceeds fixed maximum")
                chunks.append(chunk)
    except (OSError, TimeoutError) as exc:
        raise WeatherV7DispatchCallerError("broker transport failed after one dispatch attempt") from exc
    raw = b"".join(chunks)
    if not raw:
        _fail("broker emitted no receipt")
    try:
        lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
        receipt = json.loads(lines[-1])
    except (UnicodeDecodeError, IndexError, json.JSONDecodeError) as exc:
        raise WeatherV7DispatchCallerError("broker receipt is malformed") from exc
    if type(receipt) is not dict or receipt.get("result") != "PASS":
        _fail("broker receipt did not report PASS")
    if (
        receipt.get("authorization_issue_number") != request.authorization_issue_number
        or receipt.get("request_id") != request.request_id
    ):
        _fail("broker receipt identity drifted")
    return receipt


def run_once(
    client: GitHubRestClient,
    *,
    state_dir: Path = STATE_DIR,
    dispatcher: Callable[[DispatchRequest], Mapping[str, Any]] = dispatch_to_broker,
) -> Mapping[str, Any]:
    _validate_state_dir(state_dir)
    candidate = discover_candidate(client)
    if candidate is None:
        return {
            "schema": RESULT_SCHEMA,
            "result": "NO_PENDING_AUTHORIZATION",
            "dispatch_attempted": False,
            "automatic_retry": False,
            "production_mutation_started": False,
        }
    request = candidate.request
    ledger = state_dir / ATTEMPT_LEDGER.name
    attempted = _load_attempted(ledger)
    if request.request_id in attempted:
        return {
            "schema": RESULT_SCHEMA,
            "result": "AUTHORIZATION_ALREADY_ATTEMPTED",
            "authorization_issue_number": request.authorization_issue_number,
            "request_id": request.request_id,
            "dispatch_attempted": False,
            "automatic_retry": False,
            "production_mutation_started": False,
        }

    _mark_attempted(ledger, request)
    receipt = dispatcher(request)
    return {
        "schema": RESULT_SCHEMA,
        "result": "PASS",
        "authorization_issue_number": request.authorization_issue_number,
        "request_id": request.request_id,
        "dispatch_attempted": True,
        "broker_result": receipt.get("result"),
        "automatic_retry": False,
        "production_mutation_started": False,
    }


def runtime_main() -> int:
    try:
        credentials = os.environ.get("CREDENTIALS_DIRECTORY")
        if type(credentials) is not str or not credentials.startswith("/"):
            _fail("systemd credential directory is unavailable")
        provider = P9ExecutorInstallationTokenProvider(
            repository=AUTHORIZATION_REPOSITORY,
            private_key=Path(credentials) / "github-app.pem",
        )
        client = GitHubRestClient(
            token_provider=provider,
            sender=GitHubHttpsSender(),
        )
        result = run_once(client)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": RESULT_SCHEMA,
                    "result": "FAIL_CLOSED",
                    "error_class": type(exc).__name__,
                    "automatic_retry": False,
                    "production_mutation_started": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 78
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": "rozkalns.rpi5-main.weather-v7-dispatch-caller.v1",
        "issue": ISSUE,
        "result": "SOURCE_READY_FOR_CALLER_HOST_INSTALL",
        "operation_id": "rpi5-main.weather-operator-upgrade-v7.v1",
        "identity_only_dispatch_schema": DISPATCH_SCHEMA,
        "authorization_repository": AUTHORIZATION_REPOSITORY,
        "fixed_socket": str(SOCKET_PATH),
        "service_identity": "rozkalns-deploy-executor",
        "p8_mutation_dispatch_enabled": False,
        "global_executor_execution_enabled": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "automatic_retry": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
