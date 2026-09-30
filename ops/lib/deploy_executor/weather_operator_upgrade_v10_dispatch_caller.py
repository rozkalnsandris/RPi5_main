from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import socket
from typing import Any, Callable, Iterator, Mapping

from . import weather_operator_upgrade_v9_dispatch_caller as legacy
from . import weather_operator_upgrade_v9_host_capability as cap
from .dispatch_contract import DispatchRequest
from .p9_runtime import P9ExecutorInstallationTokenProvider
from .transport import GitHubHttpsSender, GitHubRestClient

ISSUE = 650
OPERATION_ID = "rpi5-main.weather-operator-upgrade-v10.v1"
TARGET_ALIAS = "rpi5-main-weather-operator-upgrade-v10"
AUTH_START = "<!-- rozkalns-weather-v10-live-auth:v1 -->"
AUTH_END = "<!-- /rozkalns-weather-v10-live-auth:v1 -->"
AUTH_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v10-live-auth.v1"
AUTH_TITLE = "[LIVE-AUTH][PENDING] rpi5-main-weather-operator-upgrade-v10"
OLD_SHA256 = "48c8c5fb0cdc005bf0e4fbb05a203297e05d7ef62689ddd0d6d717c13acc0fcb"
MUTATION_BUDGET = (
    ("git.weather-operator-upgrade-v10-checkout-fetch", 1),
    ("git.weather-operator-upgrade-v10-checkout-worktree-add", 1),
    ("filesystem.weather-operator-upgrade-v10-atomic-replace", 1),
)
REQUIRED_EXCLUSIONS = (
    "no generic sudo/root shell or caller-selected command/path/argv/environment",
    "no cleanup/retry/rollback/worktree remove/prune/repair",
    "no Docker/systemd application mutation",
    "no SQLite/corpus/snapshot/database mutation",
    "no network/firewall/DNS/Cloudflare mutation",
    "no credential/secret/permission/repository-settings mutation",
    "no v9 LIVE authorization reuse",
)
RESULT_SCHEMA = "rozkalns.rpi5-main.weather-v10-successor-dispatch-caller-result.v1"
BROKER_RECEIPT_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v10-broker-receipt.v1"
BROKER_FAIL_CLOSED_UNKNOWN = "BROKER_FAIL_CLOSED_UNKNOWN"

_BROKER_FAILURE_EXACT = {
    "authorized source is not exact current main": "SOURCE_NOT_EXACT_MAIN",
    "source CI response is malformed": "SOURCE_CI_RESPONSE_INVALID",
    "exact-source CI is not successful": "SOURCE_CI_NOT_SUCCESSFUL",
    "installed predecessor operator module drifted": "PREDECESSOR_OPERATOR_DRIFT",
    "READY queue binding drifted": "READY_QUEUE_BINDING_DRIFT",
    "authorization drifted during privileged revalidation": "AUTHORIZATION_DRIFT",
    "READY queue drifted during privileged revalidation": "READY_QUEUE_REVALIDATION_DRIFT",
    "authorization replay state is not a fresh accepted request": "AUTHORIZATION_REPLAY_STATE_INVALID",
    "fixed v10 entrypoint metadata drifted": "V10_ENTRYPOINT_METADATA_DRIFT",
    "fixed v10 upgrade invocation failed to run": "V10_UPGRADE_INVOCATION_FAILED",
    "fixed v10 upgrade output exceeded limit": "V10_UPGRADE_OUTPUT_LIMIT",
    "fixed v10 upgrade did not report success": "V10_UPGRADE_FAILED",
    "fixed v10 upgrade emitted no receipt": "V10_UPGRADE_NO_RECEIPT",
    "fixed v10 upgrade receipt is malformed": "V10_UPGRADE_RECEIPT_MALFORMED",
    "fixed v10 upgrade receipt identity drifted": "V10_UPGRADE_RECEIPT_IDENTITY_DRIFT",
    "installed v10 operator module postcondition failed": "V10_OPERATOR_POSTCONDITION_FAILED",
}
_BROKER_FAILURE_PREFIXES = (
    ("reviewed v10 source blob drifted:", "V10_SOURCE_BLOB_DRIFT"),
)

_CAP_FIELDS = (
    "OPERATION_ID",
    "TARGET_ALIAS",
    "AUTH_START",
    "AUTH_END",
    "AUTH_SCHEMA",
    "AUTH_TITLE",
    "OLD_SHA256",
    "MUTATION_BUDGET",
    "REQUIRED_EXCLUSIONS",
)
_LEGACY_FIELDS = ("AUTH_START", "AUTH_END", "AUTH_TITLE", "_REQUEST_ID_RE", "RESULT_SCHEMA")


class WeatherV10BrokerFailure(legacy.WeatherV9DispatchCallerError):
    def __init__(self, broker_failure_code: str):
        super().__init__(broker_failure_code)
        self.broker_failure_code = broker_failure_code


def _broker_failure_code(reason: Any) -> str:
    if type(reason) is not str:
        return BROKER_FAIL_CLOSED_UNKNOWN
    exact = _BROKER_FAILURE_EXACT.get(reason)
    if exact is not None:
        return exact
    for prefix, code in _BROKER_FAILURE_PREFIXES:
        if reason.startswith(prefix):
            return code
    return BROKER_FAIL_CLOSED_UNKNOWN


def _parse_broker_response(raw: bytes, request: DispatchRequest) -> Mapping[str, Any]:
    if not raw:
        legacy._fail("broker emitted no receipt")
    if len(raw) > legacy.MAX_RESPONSE_BYTES:
        legacy._fail("broker response exceeds fixed maximum")
    try:
        lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
        receipt = json.loads(lines[-1])
    except (UnicodeDecodeError, IndexError, json.JSONDecodeError) as exc:
        raise legacy.WeatherV9DispatchCallerError("broker receipt is malformed") from exc
    if type(receipt) is not dict:
        legacy._fail("broker receipt did not report PASS")
    if receipt.get("result") == "FAIL_CLOSED":
        if receipt.get("schema") != BROKER_RECEIPT_SCHEMA:
            raise WeatherV10BrokerFailure(BROKER_FAIL_CLOSED_UNKNOWN)
        raise WeatherV10BrokerFailure(_broker_failure_code(receipt.get("reason")))
    if receipt.get("result") != "PASS":
        legacy._fail("broker receipt did not report PASS")
    if (
        receipt.get("authorization_issue_number") != request.authorization_issue_number
        or receipt.get("request_id") != request.request_id
    ):
        legacy._fail("broker receipt identity drifted")
    return receipt


def dispatch_to_broker(
    request: DispatchRequest,
    *,
    socket_path: Path = legacy.SOCKET_PATH,
) -> Mapping[str, Any]:
    payload = legacy._request_payload(request)
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
                if total > legacy.MAX_RESPONSE_BYTES:
                    legacy._fail("broker response exceeds fixed maximum")
                chunks.append(chunk)
    except (OSError, TimeoutError) as exc:
        raise legacy.WeatherV9DispatchCallerError(
            "broker transport failed after one dispatch attempt"
        ) from exc
    return _parse_broker_response(b"".join(chunks), request)


def _terminal_failure(exc: Exception) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "result": "FAIL_CLOSED",
        "error_class": type(exc).__name__,
        "automatic_retry": False,
        "production_mutation_started": False,
    }
    if isinstance(exc, WeatherV10BrokerFailure):
        result["broker_failure_code"] = exc.broker_failure_code
    return result


@contextmanager
def successor_profile() -> Iterator[None]:
    """Temporarily select the reviewed v10 authorization profile over the frozen v9 caller."""
    cap_saved = {name: getattr(cap, name) for name in _CAP_FIELDS}
    legacy_saved = {name: getattr(legacy, name) for name in _LEGACY_FIELDS}
    try:
        cap.OPERATION_ID = OPERATION_ID
        cap.TARGET_ALIAS = TARGET_ALIAS
        cap.AUTH_START = AUTH_START
        cap.AUTH_END = AUTH_END
        cap.AUTH_SCHEMA = AUTH_SCHEMA
        cap.AUTH_TITLE = AUTH_TITLE
        cap.OLD_SHA256 = OLD_SHA256
        cap.MUTATION_BUDGET = MUTATION_BUDGET
        cap.REQUIRED_EXCLUSIONS = REQUIRED_EXCLUSIONS

        legacy.AUTH_START = AUTH_START
        legacy.AUTH_END = AUTH_END
        legacy.AUTH_TITLE = AUTH_TITLE
        legacy._REQUEST_ID_RE = re.compile(
            re.escape(AUTH_START)
            + r"\n```json\n(?P<payload>.*?)\n```\n"
            + re.escape(AUTH_END),
            re.DOTALL,
        )
        legacy.RESULT_SCHEMA = RESULT_SCHEMA
        yield
    finally:
        for name, value in legacy_saved.items():
            setattr(legacy, name, value)
        for name, value in cap_saved.items():
            setattr(cap, name, value)


def discover_candidate(client: GitHubRestClient):
    with successor_profile():
        return legacy.discover_candidate(client)


def run_once(
    client: GitHubRestClient,
    *,
    state_dir: Path = legacy.STATE_DIR,
    dispatcher: Callable[[DispatchRequest], Mapping[str, Any]] = dispatch_to_broker,
) -> Mapping[str, Any]:
    with successor_profile():
        return legacy.run_once(client, state_dir=state_dir, dispatcher=dispatcher)


def runtime_main() -> int:
    try:
        credentials = os.environ.get("CREDENTIALS_DIRECTORY")
        if type(credentials) is not str or not credentials.startswith("/"):
            legacy._fail("systemd credential directory is unavailable")
        provider = P9ExecutorInstallationTokenProvider(
            repository=legacy.AUTHORIZATION_REPOSITORY,
            private_key=Path(credentials) / "github-app.pem",
        )
        client = GitHubRestClient(
            token_provider=provider,
            sender=GitHubHttpsSender(),
        )
        result = run_once(client)
    except Exception as exc:
        print(json.dumps(_terminal_failure(exc), sort_keys=True, separators=(",", ":")))
        return 78
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": "rozkalns.rpi5-main.weather-v10-successor-dispatch-caller.v1",
        "issue": ISSUE,
        "result": "SOURCE_READY_FOR_SEPARATE_CALLER_REFRESH_LIVE_GATE",
        "operation_id": OPERATION_ID,
        "authorization_title": AUTH_TITLE,
        "identity_only_dispatch_schema": legacy.DISPATCH_SCHEMA,
        "authorization_repository": legacy.AUTHORIZATION_REPOSITORY,
        "fixed_socket": str(legacy.SOCKET_PATH),
        "historical_v9_caller_source_mutated": False,
        "v9_authorization_reuse": False,
        "broker_failure_diagnostics": "bounded_allowlist_code_only",
        "raw_broker_reason_exposed": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "automatic_retry": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
