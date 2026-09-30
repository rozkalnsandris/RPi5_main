from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping, Sequence

from .dispatch_contract import DispatchRequest, parse_dispatch_request
from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .queue_normalizer import QUEUE_REPOSITORY, normalize_ready_queue
from .registry import BaselineContract, MutationBudget, OperationRegistry, OperationSpec, QueueMatch
from .state import StateError, StateStore
from .transport import API_VERSION, GitHubHttpsSender, HTTPStatusError

ISSUE = 571
SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
SOURCE_REPOSITORY_ID = 1323383044
OPERATION_ID = "rpi5-main.weather-operator-upgrade-v7.v1"
ADAPTER_ID = OPERATION_ID
TARGET_ALIAS = "rpi5-main-weather-operator-upgrade-v7"
AUTHORIZATION_CLASS = "STRICT"
ROLLBACK_POLICY = "NONE"
BASELINE_RESOLVER_ID = "rpi5-main.weather-operator-upgrade-v7-baseline.v1"
ENTRYPOINT = "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v7"
TRUSTED_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v7-trusted"
PRESERVED_V6_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v6-trusted"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
MINIMUM_REVIEWED_ANCESTOR = "09e39bcfa5d5d01ad19fd6a3730a20b6748ada9b"
TARGET_PATH = Path("/usr/local/sbin/rozkalns-weather-public-runtime-operator")
TARGET_TEMP_PATH = TARGET_PATH.parent / ".rozkalns-weather-public-runtime-operator.weather-v7-broker.tmp"
OLD_SHA256 = "4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f"
NEW_SHA256 = "f6255bf1e80d2918555b0814b0690add739041ac11512297d904fce5e8fc0cf1"
MUTATION_BUDGET = (
    ("git.weather-operator-upgrade-v7-checkout-fetch", 1),
    ("git.weather-operator-upgrade-v7-checkout-worktree-add", 1),
    ("filesystem.weather-operator-upgrade-v7-atomic-replace", 1),
)
AUTH_START = "<!-- rozkalns-weather-v7-live-auth:v1 -->"
AUTH_END = "<!-- /rozkalns-weather-v7-live-auth:v1 -->"
AUTH_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v7-live-auth.v1"
AUTH_TITLE = "[LIVE-AUTH][PENDING] rpi5-main-weather-operator-upgrade-v7"
AUTH_TTL_SECONDS = 600
OWNER_USER_ID = 277435981
MAX_UID = (1 << 32) - 2
REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-registration.v2"
REGISTRATION_PATH = Path("/etc/rozkalns-weather-operator-v7-capability/registration.json")
SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-operator-v7-capability")
STATE_DB_PATH = Path("/var/lib/rozkalns-weather-operator-v7-capability/state.sqlite3")
ISOLATED_AUTH_PATH = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
SOCKET_UNIT = "rozkalns-weather-operator-v7-privileged-broker.socket"
SERVICE_UNIT = "rozkalns-weather-operator-v7-privileged-broker@.service"
BROKER_PATH = Path("/usr/local/libexec/rozkalns-weather-operator-v7-privileged-broker")
MAX_REQUEST_BYTES = 4096
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
AUTH_FIELDS = frozenset({
    "schema", "request_id", "queue_issue", "source_sha", "operation_id",
    "target_alias", "expected_predecessor_sha256", "mutation_budget",
    "rollback_policy", "exclusions",
})
REQUIRED_EXCLUSIONS = (
    "no generic sudo/root shell or caller-selected command/path/argv/environment",
    "no cleanup/retry/rollback/worktree remove/prune/repair",
    "no Docker/systemd application mutation",
    "no SQLite/corpus/snapshot/database mutation",
    "no network/firewall/DNS/Cloudflare mutation",
    "no credential/secret/permission/repository-settings mutation",
)


class WeatherV7HostCapabilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeatherV7Authorization:
    issue_id: int
    issue_number: int
    request_id: str
    queue_issue: int
    source_sha: str
    canonical_payload_sha256: str
    raw_body_sha256: str
    created_at: str


@dataclass(frozen=True)
class WeatherV7BrokerPlan:
    authorization: WeatherV7Authorization
    manager_checkout: Path
    manager_uid: int
    manager_gid: int
    trusted_checkout: Path
    v6_checkout: Path
    checkout_state: str
    capability_source_sha: str
    queue_contract_sha256: str
    source_ci_run_id: int


def _fail(message: str) -> None:
    raise WeatherV7HostCapabilityError(message)


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise WeatherV7HostCapabilityError("authorization cannot be canonicalized") from exc


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate authorization JSON key")
        result[key] = value
    return result


def _parse_utc(value: Any, where: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        _fail(f"{where} must be canonical UTC Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise WeatherV7HostCapabilityError(f"{where} is invalid") from exc
    if parsed.tzinfo is None:
        _fail(f"{where} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _parse_budget(value: Any) -> tuple[tuple[str, int], ...]:
    if type(value) is not list:
        _fail("mutation_budget must be a list")
    observed: list[tuple[str, int]] = []
    for item in value:
        if type(item) is not dict or set(item) != {"category", "max_operations"}:
            _fail("mutation_budget entry is invalid")
        if type(item["category"]) is not str or type(item["max_operations"]) is not int:
            _fail("mutation_budget entry types are invalid")
        observed.append((item["category"], item["max_operations"]))
    result = tuple(observed)
    if result != MUTATION_BUDGET:
        _fail("mutation_budget drifted")
    return result


def parse_authorization_issue(
    issue: Mapping[str, Any], *, server_time: datetime, request: DispatchRequest
) -> WeatherV7Authorization:
    if type(issue) is not dict or issue.get("state") != "open":
        _fail("authorization issue must be open")
    if issue.get("title") != AUTH_TITLE:
        _fail("authorization title drifted")
    if issue.get("number") != request.authorization_issue_number:
        _fail("authorization issue number drifted")
    if issue.get("id") != request.authorization_issue_id:
        _fail("authorization issue id drifted")
    user = issue.get("user")
    if type(user) is not dict or user.get("id") != OWNER_USER_ID or user.get("type") != "User":
        _fail("authorization owner identity drifted")
    if issue.get("performed_via_github_app") is not None:
        _fail("authorization must be directly owner-authored, not app-mediated")
    created = _parse_utc(issue.get("created_at"), "authorization created_at")
    if not isinstance(server_time, datetime) or server_time.tzinfo is None:
        _fail("GitHub server time is unavailable")
    now = server_time.astimezone(timezone.utc)
    age = (now - created).total_seconds()
    if age < -30 or age > AUTH_TTL_SECONDS:
        _fail("authorization TTL is invalid")
    body = issue.get("body")
    if type(body) is not str or body.count(AUTH_START) != 1 or body.count(AUTH_END) != 1:
        _fail("authorization body markers are invalid")
    marker = re.compile(
        re.escape(AUTH_START) + r"\n```json\n(?P<payload>.*?)\n```\n" + re.escape(AUTH_END),
        re.DOTALL,
    )
    match = marker.search(body)
    if match is None:
        _fail("authorization payload block is malformed")
    try:
        payload = json.loads(match.group("payload"), object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WeatherV7HostCapabilityError("authorization payload JSON is malformed") from exc
    if type(payload) is not dict or frozenset(payload) != AUTH_FIELDS:
        _fail("authorization payload fields drifted")
    if payload["schema"] != AUTH_SCHEMA:
        _fail("authorization schema drifted")
    if payload["request_id"] != request.request_id:
        _fail("authorization request_id drifted")
    queue_issue = payload["queue_issue"]
    if type(queue_issue) is not int or queue_issue < 1 or queue_issue == request.authorization_issue_number:
        _fail("authorization queue issue is invalid")
    source_sha = payload["source_sha"]
    if type(source_sha) is not str or SHA40_RE.fullmatch(source_sha) is None:
        _fail("authorization source SHA is invalid")
    if payload["operation_id"] != OPERATION_ID or payload["target_alias"] != TARGET_ALIAS:
        _fail("authorization operation/target drifted")
    if payload["expected_predecessor_sha256"] != OLD_SHA256:
        _fail("authorization predecessor identity drifted")
    _parse_budget(payload["mutation_budget"])
    if payload["rollback_policy"] != ROLLBACK_POLICY:
        _fail("authorization rollback policy drifted")
    exclusions = payload["exclusions"]
    if type(exclusions) is not list or tuple(exclusions) != REQUIRED_EXCLUSIONS:
        _fail("authorization exclusions drifted")
    canonical = _canonical_json(payload)
    return WeatherV7Authorization(
        issue_id=request.authorization_issue_id,
        issue_number=request.authorization_issue_number,
        request_id=request.request_id,
        queue_issue=queue_issue,
        source_sha=source_sha,
        canonical_payload_sha256=hashlib.sha256(canonical).hexdigest(),
        raw_body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        created_at=created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def fixed_registry() -> OperationRegistry:
    operation = OperationSpec(
        operation_id=OPERATION_ID,
        source_repository=SOURCE_REPOSITORY,
        queue_match=QueueMatch(
            target_alias=TARGET_ALIAS,
            execution_location_class="trusted-home-host",
            repository_entrypoint=ENTRYPOINT,
            deploy_class="STRICT_LIVE_AUTH_REQUIRED",
        ),
        target_alias=TARGET_ALIAS,
        adapter_id=ADAPTER_ID,
        authorization_class=AUTHORIZATION_CLASS,
        ordinary_live_all_eligible=False,
        baseline=BaselineContract(kind="resolver", resolver_id=BASELINE_RESOLVER_ID),
        mutation_budget=tuple(
            MutationBudget(category=category, max_operations=maximum)
            for category, maximum in MUTATION_BUDGET
        ),
        rollback_policy=ROLLBACK_POLICY,
        exclusions=REQUIRED_EXCLUSIONS,
        dependencies=(
            "source-contract:RPi5_main#543",
            "host-capability-installer:RPi5_main#571",
            "p8-global-mutation-dispatch:disabled",
            "privileged-boundary:identity-only",
        ),
        preflight=("fresh authorization, READY queue, exact current main/CI and host baseline",),
        postconditions=("v7 operator exact reviewed hash and v6 preserved",),
        required_github_evidence=("owner authorization, READY queue, exact source/CI",),
    )
    return OperationRegistry(schema_version=1, execution_enabled=False, operations=(operation,))


def _public_json(path: str) -> tuple[Mapping[str, Any], datetime]:
    if not path.startswith(f"/repos/{SOURCE_REPOSITORY}"):
        _fail("public source path is outside fixed repository")
    response = GitHubHttpsSender().send(
        method="GET",
        url="https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "rozkalns-weather-v7-capability/1",
        },
    )
    if response.status != 200:
        raise HTTPStatusError(response.status)
    try:
        value = json.loads(response.body.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WeatherV7HostCapabilityError("public source response is malformed") from exc
    date_value = next((value for key, value in response.headers.items() if key.lower() == "date"), None)
    if type(date_value) is not str:
        _fail("public source response omitted Date")
    try:
        server_time = parsedate_to_datetime(date_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WeatherV7HostCapabilityError("public source Date is invalid") from exc
    if server_time.tzinfo is None:
        _fail("public source Date has no timezone")
    if type(value) is not dict:
        _fail("public source response root is malformed")
    return value, server_time.astimezone(timezone.utc)


def verify_source_exact_main_and_ci(source_sha: str) -> int:
    branch, _ = _public_json(f"/repos/{SOURCE_REPOSITORY}/branches/main")
    commit = branch.get("commit")
    if type(commit) is not dict or commit.get("sha") != source_sha:
        _fail("authorized source is not exact current main")
    runs, _ = _public_json(
        f"/repos/{SOURCE_REPOSITORY}/actions/workflows/validate.yml/runs"
        f"?branch=main&head_sha={source_sha}&status=completed&per_page=100"
    )
    rows = runs.get("workflow_runs")
    if type(rows) is not list:
        _fail("source CI response is malformed")
    successful = [
        row for row in rows
        if type(row) is dict
        and row.get("head_sha") == source_sha
        and row.get("status") == "completed"
        and row.get("conclusion") == "success"
        and type(row.get("id")) is int
    ]
    if not successful:
        _fail("exact-source CI is not successful")
    return max(int(row["id"]) for row in successful)


def _safe_file(path: Path, *, uid: int, gid: int, mode: int, max_bytes: int) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        _fail(f"runtime target is not a single-link regular file: {path.name}")
    if before.st_uid != uid or before.st_gid != gid or stat.S_IMODE(before.st_mode) != mode:
        _fail(f"runtime target metadata drifted: {path.name}")
    if not 0 < before.st_size <= max_bytes:
        _fail(f"runtime target size is invalid: {path.name}")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            _fail(f"runtime target changed before open: {path.name}")
        data = os.read(fd, max_bytes + 1)
        if len(data) != opened.st_size or len(data) > max_bytes:
            _fail(f"runtime target changed while read: {path.name}")
        return data
    finally:
        os.close(fd)


def load_registration() -> Mapping[str, Any]:
    raw = _safe_file(REGISTRATION_PATH, uid=0, gid=0, mode=0o600, max_bytes=8192)
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WeatherV7HostCapabilityError("host capability registration is malformed") from exc
    required = {
        "schema",
        "capability_source_sha",
        "manager_checkout",
        "manager_uid",
        "manager_gid",
        "artifact_count",
        "module_sha256",
        "broker_sha256",
        "socket_sha256",
        "service_sha256",
    }
    if type(value) is not dict or set(value) != required:
        _fail("host capability registration fields drifted")
    if value["schema"] != REGISTRATION_SCHEMA:
        _fail("host capability registration schema drifted")
    if type(value["capability_source_sha"]) is not str or SHA40_RE.fullmatch(value["capability_source_sha"]) is None:
        _fail("capability source SHA is invalid")
    if type(value["manager_checkout"]) is not str or not value["manager_checkout"].startswith("/"):
        _fail("manager checkout registration is invalid")
    for key in ("manager_uid", "manager_gid"):
        candidate = value[key]
        if type(candidate) is not int or not (0 < candidate <= MAX_UID):
            _fail(f"{key} registration is invalid")
    if value["artifact_count"] != 15:
        _fail("host capability artifact count drifted")
    for key in ("module_sha256", "broker_sha256", "socket_sha256", "service_sha256"):
        if type(value[key]) is not str or SHA256_RE.fullmatch(value[key]) is None:
            _fail(f"{key} is invalid")
    return value


def verify_installed_capability(registration: Mapping[str, Any]) -> None:
    targets = (
        (
            SUPPORT_ROOT / "deploy_executor" / "weather_operator_upgrade_v7_host_capability.py",
            0o644,
            registration["module_sha256"],
        ),
        (BROKER_PATH, 0o755, registration["broker_sha256"]),
        (Path("/etc/systemd/system") / SOCKET_UNIT, 0o644, registration["socket_sha256"]),
        (Path("/etc/systemd/system") / SERVICE_UNIT, 0o644, registration["service_sha256"]),
    )
    for path, mode, expected in targets:
        raw = _safe_file(path, uid=0, gid=0, mode=mode, max_bytes=2 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != expected:
            _fail(f"installed host capability artifact drifted: {path.name}")


def _run_git(manager: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    _fail("manager-identity Git backend is not installed")


def _require_predecessor() -> None:
    raw = _safe_file(TARGET_PATH, uid=0, gid=0, mode=0o755, max_bytes=2 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != OLD_SHA256:
        _fail("installed predecessor operator drifted")


def _require_manager(manager: Path) -> None:
    if not manager.is_absolute() or manager.name != "RPi5_main":
        _fail("registered manager checkout identity drifted")
    origin = _run_git(manager, "remote", "get-url", "origin").stdout.strip()
    if origin != REVIEWED_ORIGIN:
        _fail("registered manager checkout origin drifted")


def _checkout_state(manager: Path, source_sha: str) -> tuple[str, Path, Path]:
    _fail("manager-identity worktree backend is not installed")


def _fetch_issue(client: Any, number: int) -> tuple[Mapping[str, Any], datetime]:
    response = client.get_json(f"/repos/{QUEUE_REPOSITORY}/issues/{number}")
    value = getattr(response, "value", None)
    server_time = getattr(response, "server_time", None)
    if type(value) is not dict or not isinstance(server_time, datetime) or server_time.tzinfo is None:
        _fail("GitHub issue response is malformed")
    return value, server_time.astimezone(timezone.utc)


def prepare_plan(
    raw_request: bytes,
    *,
    queue_client: Any,
    registration: Mapping[str, Any],
) -> WeatherV7BrokerPlan:
    if type(raw_request) is not bytes or not (1 <= len(raw_request) <= MAX_REQUEST_BYTES) or b"\n" in raw_request.rstrip(b"\n"):
        _fail("broker request framing is invalid")
    try:
        request_value = json.loads(
            raw_request.decode("utf-8", "strict"), object_pairs_hook=_strict_object
        )
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WeatherV7HostCapabilityError("broker request JSON is malformed") from exc
    request = parse_dispatch_request(request_value)
    verify_installed_capability(registration)
    manager = Path(str(registration["manager_checkout"]))
    _require_manager(manager)
    _require_predecessor()
    if TARGET_TEMP_PATH.exists():
        _fail("fixed operator replacement temp path already exists")

    first_issue, first_time = _fetch_issue(queue_client, request.authorization_issue_number)
    auth = parse_authorization_issue(first_issue, server_time=first_time, request=request)
    queue_issue, _ = _fetch_issue(queue_client, auth.queue_issue)
    normalized = normalize_ready_queue(
        queue_issue,
        repository_full_name=QUEUE_REPOSITORY,
        registry=fixed_registry(),
    )
    if normalized.execution_enabled is not False:
        _fail("global/P8 mutation execution unexpectedly enabled")
    protocol_queue = normalized.as_protocol_queue()
    if (
        protocol_queue.get("source_repository") != SOURCE_REPOSITORY
        or protocol_queue.get("source_sha") != auth.source_sha
        or protocol_queue.get("operation_id") != OPERATION_ID
        or protocol_queue.get("target_alias") != TARGET_ALIAS
        or protocol_queue.get("expected_baseline")
        != {"kind": "resolver", "value": BASELINE_RESOLVER_ID}
        or tuple(
            (item["category"], item["max_operations"])
            for item in protocol_queue.get("mutation_budget", [])
        )
        != MUTATION_BUDGET
        or protocol_queue.get("rollback_policy") != ROLLBACK_POLICY
    ):
        _fail("READY queue binding drifted")
    ci_run = verify_source_exact_main_and_ci(auth.source_sha)
    state, v7, v6 = _checkout_state(manager, auth.source_sha)

    final_issue, final_time = _fetch_issue(queue_client, request.authorization_issue_number)
    final = parse_authorization_issue(final_issue, server_time=final_time, request=request)
    if final != auth:
        _fail("authorization drifted during privileged revalidation")
    final_queue, _ = _fetch_issue(queue_client, auth.queue_issue)
    final_normalized = normalize_ready_queue(
        final_queue,
        repository_full_name=QUEUE_REPOSITORY,
        registry=fixed_registry(),
    )
    if final_normalized.canonical_json != normalized.canonical_json:
        _fail("READY queue drifted during privileged revalidation")
    return WeatherV7BrokerPlan(
        authorization=auth,
        manager_checkout=manager,
        manager_uid=int(registration["manager_uid"]),
        manager_gid=int(registration["manager_gid"]),
        trusted_checkout=v7,
        v6_checkout=v6,
        checkout_state=state,
        capability_source_sha=str(registration["capability_source_sha"]),
        queue_contract_sha256=normalized.parsed.contract_sha256,
        source_ci_run_id=ci_run,
    )


def _admit_and_consume(plan: WeatherV7BrokerPlan) -> None:
    auth = plan.authorization
    with StateStore(STATE_DB_PATH) as store:
        try:
            existing = store.get(auth.request_id)
        except StateError:
            store.discover(
                repository_id=1328835922,
                issue_id=auth.issue_id,
                request_id=auth.request_id,
                canonical_payload_sha256=auth.canonical_payload_sha256,
                raw_body_sha256=auth.raw_body_sha256,
            )
            store.transition(auth.request_id, "VALIDATING")
            store.transition(auth.request_id, "ACCEPTED")
        else:
            if (
                existing.repository_id != 1328835922
                or existing.issue_id != auth.issue_id
                or existing.canonical_payload_sha256 != auth.canonical_payload_sha256
                or existing.raw_body_sha256 != auth.raw_body_sha256
                or existing.state != "ACCEPTED"
            ):
                _fail("authorization replay state is not a fresh accepted request")
        store.consume(auth.request_id)


def _bootstrap_checkout(plan: WeatherV7BrokerPlan) -> None:
    _fail("manager-identity worktree bootstrap backend is not installed")


def _run_fixed_upgrade(plan: WeatherV7BrokerPlan) -> Mapping[str, Any]:
    _fail("fixed root-owned operator replacement backend is not installed")


def execute_plan(plan: WeatherV7BrokerPlan) -> Mapping[str, Any]:
    _admit_and_consume(plan)
    _bootstrap_checkout(plan)
    _run_fixed_upgrade(plan)
    raw = _safe_file(TARGET_PATH, uid=0, gid=0, mode=0o755, max_bytes=2 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != NEW_SHA256:
        _fail("installed v7 operator postcondition failed")
    return {
        "schema": "rozkalns.rpi5-main.weather-operator-upgrade-v7-broker-receipt.v1",
        "result": "PASS",
        "authorization_issue_number": plan.authorization.issue_number,
        "request_id": plan.authorization.request_id,
        "source_sha": plan.authorization.source_sha,
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_ci_run_id": plan.source_ci_run_id,
        "queue_contract_sha256": plan.queue_contract_sha256,
        "durable_replay_consumed": True,
        "authorization_reuse_forbidden": True,
        "operator_sha256": NEW_SHA256,
        "v6_checkout_preserved": True,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "docker_mutation": False,
        "systemd_application_mutation": False,
        "sqlite_or_corpus_mutation": False,
        "network_or_cloudflare_mutation": False,
        "production_mutation_started": False,
    }


def runtime_main() -> int:
    if os.geteuid() != 0:
        _fail("privileged broker requires root process identity")
    credentials = os.environ.get("CREDENTIALS_DIRECTORY")
    if type(credentials) is not str or not credentials.startswith("/"):
        _fail("systemd credential directory is unavailable")
    private_key = Path(credentials) / "github-app.pem"
    auth_surface = load_contract(ISOLATED_AUTH_PATH)
    require_isolated_auth_surface(auth_surface)
    clients = build_p9_read_clients(auth_surface=auth_surface, private_key=private_key)
    registration = load_registration()
    raw = os.read(0, MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        _fail("broker request exceeds fixed maximum")
    plan = prepare_plan(raw, queue_client=clients.queue, registration=registration)
    receipt = execute_plan(plan)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability.v1",
        "issue": ISSUE,
        "result": "SOURCE_READY_FOR_HOST_CAPABILITY_INSTALL",
        "operation_id": OPERATION_ID,
        "authorization_class": AUTHORIZATION_CLASS,
        "ordinary_live_all_eligible": False,
        "identity_only_dispatch_schema": "rozkalns.deploy-dispatch-request.v1",
        "authorization_repository": "rozkalnsandris/ops-workflows",
        "fixed_target": str(TARGET_PATH),
        "fixed_entrypoint": ENTRYPOINT,
        "mutation_budget": MUTATION_BUDGET,
        "host_capability_installed": False,
        "privileged_dispatch_enabled": False,
        "p8_mutation_dispatch_enabled": False,
        "global_executor_execution_enabled": False,
        "source_merge_authorizes_live": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "production_mutation_started": False,
    }
