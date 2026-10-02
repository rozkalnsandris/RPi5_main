from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    QUEUE_REPOSITORY,
    QUEUE_REPOSITORY_ID,
    AcceptedAuthorization,
    accept_issue,
    validate_queue_binding,
    verify_authorization_unchanged,
)
from .queue_normalizer import normalize_ready_queue
from .registry import BaselineContract, MutationBudget, OperationRegistry, OperationSpec, QueueMatch
from .source_evidence import verify_source_evidence
from .state import EXPECTED_COLUMNS, STATE_DB_APPLICATION_ID, STATE_DB_SCHEMA_VERSION, StateStore
from .weather_private_gcs_auth_binding import (
    ADAPTER_ID,
    BASELINE_RESOLVER_ID,
    CanonicalGCSAuthBindingEvidence,
    MUTATION_BUDGET,
    OPERATION_ID,
    REQUIRED_EXCLUSIONS,
    ROLLBACK_POLICY,
    SOURCE_BINDING_ROOT,
    TARGET_ALIAS,
    WeatherNextPrivateGCSAuthBindingError,
    apply_auth_binding,
    public_receipt,
)
from .weather_public_runtime_composite import FixedPublicGitHubReadClient

IMPLEMENTATION_ISSUE = 843
SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
SOURCE_REPOSITORY_ID = 1323383044
AUTH_SURFACE = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_PRIVATE_KEY = Path("/etc/rozkalns-deploy-executor/github-app.pem")
STATE_DB = Path("/var/lib/rozkalns-deploy-executor-p9/state.sqlite3")
EXECUTION_LOCATION_CLASS = "trusted-home-host"
DEPLOY_CLASS = "STRICT_LIVE_AUTH_REQUIRED"
MINIMUM_REVIEWED_ANCESTOR = "05c9af882d85ab644d157aab40b5943d9ddf855b"
DEPENDENCIES = (
    "source-contract:RPi5_main#843",
    "gcs-host-capability:rpi5.weathernext-private-gcs-backend.v1",
    "protected-source-binding:existing-weather-private-binding",
    f"minimum-reviewed-ancestor:{MINIMUM_REVIEWED_ANCESTOR}",
    "global-executor-execution:disabled",
)


def _fail(message: str) -> None:
    raise WeatherNextPrivateGCSAuthBindingError(message)


def _fixed_registry() -> OperationRegistry:
    operation = OperationSpec(
        operation_id=OPERATION_ID,
        source_repository=SOURCE_REPOSITORY,
        queue_match=QueueMatch(
            target_alias=TARGET_ALIAS,
            execution_location_class=EXECUTION_LOCATION_CLASS,
            repository_entrypoint="ops/bin/rpi5-weathernext-private-host-privileged-install",
            deploy_class=DEPLOY_CLASS,
        ),
        target_alias=TARGET_ALIAS,
        adapter_id=ADAPTER_ID,
        authorization_class="STRICT",
        ordinary_live_all_eligible=False,
        baseline=BaselineContract(kind="resolver", resolver_id=BASELINE_RESOLVER_ID),
        mutation_budget=tuple(
            MutationBudget(category=category, max_operations=maximum)
            for category, maximum in MUTATION_BUDGET
        ),
        rollback_policy=ROLLBACK_POLICY,
        exclusions=REQUIRED_EXCLUSIONS,
        dependencies=DEPENDENCIES,
        preflight=(
            "owner LIVE-AUTH and READY Queue are independently revalidated",
            "current RPi5_main exact-main required CI is successful",
            "target GCS auth binding is absent or exact without partial state",
            "protected source credential is not read before durable authorization consume",
        ),
        postconditions=(
            "fixed GCS private binding credential copy and sanitized ready marker are exact",
            "no Google request project dataset Analytics Hub BigQuery or SQLite action executes",
        ),
        required_github_evidence=(
            "owner-authored non-App LIVE-AUTH",
            "READY Queue exact operation target source and mutation budget binding",
            "current RPi5_main exact-main required CI",
        ),
    )
    return OperationRegistry(schema_version=1, execution_enabled=False, operations=(operation,))


def _require_live_authority(accepted: AcceptedAuthorization) -> Mapping[str, Any]:
    payload = accepted.payload
    expected = {
        "queue_repository": QUEUE_REPOSITORY,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "expected_baseline": {"kind": "resolver", "value": BASELINE_RESOLVER_ID},
        "mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in MUTATION_BUDGET
        ],
        "rollback_policy": ROLLBACK_POLICY,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            _fail(f"canonical GCS auth-binding LIVE-AUTH {field} drifted")
    exclusions = payload.get("exclusions")
    if type(exclusions) is not list or not set(REQUIRED_EXCLUSIONS).issubset(set(exclusions)):
        _fail("canonical GCS auth-binding LIVE-AUTH exclusions drifted")
    return payload


def _require_queue(normalized: Any) -> Mapping[str, Any]:
    if getattr(normalized, "execution_enabled", None) is not False:
        _fail("GCS auth-binding registry unexpectedly enables execution")
    operation = getattr(normalized, "operation", None)
    expected = {
        "operation_id": OPERATION_ID,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "adapter_id": ADAPTER_ID,
        "authorization_class": "STRICT",
        "ordinary_live_all_eligible": False,
        "rollback_policy": ROLLBACK_POLICY,
    }
    for field, value in expected.items():
        if getattr(operation, field, None) != value:
            _fail(f"GCS auth-binding Queue {field} drifted")
    observed_budget = tuple(
        (item.category, item.max_operations)
        for item in getattr(operation, "mutation_budget", ())
    )
    if observed_budget != MUTATION_BUDGET:
        _fail("GCS auth-binding Queue mutation budget drifted")
    baseline = getattr(operation, "baseline", None)
    if (
        getattr(baseline, "kind", None) != "resolver"
        or getattr(baseline, "resolver_id", None) != BASELINE_RESOLVER_ID
    ):
        _fail("GCS auth-binding Queue baseline drifted")
    protocol_queue = normalized.as_protocol_queue()
    if protocol_queue.get("expected_baseline") != {
        "kind": "resolver",
        "value": BASELINE_RESOLVER_ID,
    }:
        _fail("GCS auth-binding Queue baseline binding drifted")
    return protocol_queue


def _server_time(response: Any) -> datetime:
    value = getattr(response, "server_time", None)
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fail("GitHub server time is unavailable")
    return value.astimezone(timezone.utc)


class DurableGCSAuthReplayAuthority:
    def __init__(self) -> None:
        self._candidate: AcceptedAuthorization | None = None
        self._checks = 0
        self._terminal = False

    @staticmethod
    def _readonly_connection() -> sqlite3.Connection:
        if not STATE_DB.is_file():
            _fail("durable replay database is unavailable")
        try:
            conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro&immutable=1", uri=True)
            conn.row_factory = sqlite3.Row
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                _fail("durable replay quick_check failed")
            if conn.execute("PRAGMA application_id").fetchone()[0] != STATE_DB_APPLICATION_ID:
                _fail("durable replay application_id drifted")
            if conn.execute("PRAGMA user_version").fetchone()[0] != STATE_DB_SCHEMA_VERSION:
                _fail("durable replay schema version drifted")
            columns = tuple(
                (row["name"], row["type"], row["notnull"], row["pk"])
                for row in conn.execute("PRAGMA table_info(requests)").fetchall()
            )
            if columns != EXPECTED_COLUMNS:
                _fail("durable replay schema drifted")
            return conn
        except WeatherNextPrivateGCSAuthBindingError:
            raise
        except sqlite3.DatabaseError as exc:
            raise WeatherNextPrivateGCSAuthBindingError(
                "durable replay database read failed"
            ) from exc

    @classmethod
    def _available(cls, accepted: AcceptedAuthorization) -> bool:
        conn = cls._readonly_connection()
        try:
            rows = conn.execute(
                "SELECT request_id FROM requests "
                "WHERE (repository_id = ? AND issue_id = ?) OR request_id = ? LIMIT 2",
                (accepted.repository_id, accepted.issue_id, accepted.request_id),
            ).fetchall()
            return len(rows) == 0
        finally:
            conn.close()

    def is_available(self, accepted: AcceptedAuthorization) -> bool:
        if self._terminal:
            return False
        if type(accepted) is not AcceptedAuthorization:
            _fail("replay authority requires canonical AcceptedAuthorization")
        if self._candidate is not None and self._candidate != accepted:
            _fail("authorization changed between replay checks")
        if not self._available(accepted):
            return False
        self._candidate = accepted
        self._checks += 1
        return True

    def consume(self, request_id: str) -> None:
        candidate = self._candidate
        if self._terminal or candidate is None or candidate.request_id != request_id:
            _fail("replay consume has no canonical available request")
        if self._checks < 2:
            _fail("replay consume requires double canonical availability")
        self._terminal = True
        store = StateStore(STATE_DB)
        try:
            store.discover(
                repository_id=candidate.repository_id,
                issue_id=candidate.issue_id,
                request_id=candidate.request_id,
                canonical_payload_sha256=candidate.canonical_payload_sha256,
                raw_body_sha256=candidate.raw_body_sha256,
            )
            store.transition(request_id, "VALIDATING")
            store.transition(request_id, "ACCEPTED")
            record = store.consume(request_id)
            if record.state != "CONSUMED":
                _fail("authorization did not reach CONSUMED")
        finally:
            store.close()


class ConcreteGCSAuthBindingRevalidator:
    def __init__(
        self,
        *,
        authorization_client: Any,
        queue_client: Any,
        source_client: FixedPublicGitHubReadClient,
        auth_surface: Any,
        replay: DurableGCSAuthReplayAuthority,
    ):
        require_isolated_auth_surface(auth_surface)
        self._authorization_client = authorization_client
        self._queue_client = queue_client
        self._source_client = source_client
        self._auth_surface = auth_surface
        self._replay = replay
        self._registry = _fixed_registry()

    def revalidate(self, issue_number: int) -> CanonicalGCSAuthBindingEvidence:
        if type(issue_number) is not int or not 1 <= issue_number <= 2_147_483_647:
            _fail("authorization issue number is invalid")
        require_isolated_auth_surface(self._auth_surface)
        issue_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        accepted = accept_issue(
            issue_response.value,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=_server_time(issue_response),
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        payload = _require_live_authority(accepted)
        queue_issue_number = payload.get("queue_issue")
        if type(queue_issue_number) is not int or queue_issue_number < 1:
            _fail("Queue issue number is invalid")
        queue_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue_number}"
        )
        normalized = normalize_ready_queue(
            queue_response.value,
            repository_full_name=QUEUE_REPOSITORY,
            registry=self._registry,
        )
        validate_queue_binding(accepted, _require_queue(normalized))
        source_sha = payload.get("source_sha")
        if type(source_sha) is not str:
            _fail("GCS auth-binding source SHA missing")
        source = verify_source_evidence(
            self._source_client,
            source_repository=SOURCE_REPOSITORY,
            source_sha=source_sha,
        )
        if source.repository_id != SOURCE_REPOSITORY_ID or source.current_main_sha != source_sha:
            _fail("RPi5_main source is not exact current main")
        compare = self._source_client.get_json(
            f"/repos/{SOURCE_REPOSITORY}/compare/{MINIMUM_REVIEWED_ANCESTOR}...{source_sha}"
        )
        if type(compare.value) is not dict or compare.value.get("status") not in {"ahead", "identical"}:
            _fail("RPi5_main source is outside reviewed GCS auth-binding ancestry")
        if self._replay.is_available(accepted) is not True:
            _fail("GCS auth-binding LIVE-AUTH is unavailable for one-shot consume")
        final = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        verify_authorization_unchanged(
            accepted,
            final.value,
            server_time=_server_time(final),
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        if self._replay.is_available(accepted) is not True:
            _fail("GCS auth-binding replay state drifted during final revalidation")
        return CanonicalGCSAuthBindingEvidence(
            authorization_issue_number=issue_number,
            request_id=accepted.request_id,
            operation_id=OPERATION_ID,
            target_alias=TARGET_ALIAS,
            rpi5_main_sha=source_sha,
            queue_issue_number=queue_issue_number,
        )


def run_privileged_gcs_auth_binding(authorization_issue_number: int) -> Mapping[str, Any]:
    if os.geteuid() != 0:
        _fail("GCS auth-binding operation must run as root")
    replay = DurableGCSAuthReplayAuthority()
    try:
        auth_surface = load_contract(AUTH_SURFACE)
        require_isolated_auth_surface(auth_surface)
        clients = build_p9_read_clients(
            auth_surface=auth_surface,
            private_key=EXECUTOR_PRIVATE_KEY,
        )
        revalidator = ConcreteGCSAuthBindingRevalidator(
            authorization_client=clients.authorization,
            queue_client=clients.queue,
            source_client=FixedPublicGitHubReadClient(),
            auth_surface=auth_surface,
            replay=replay,
        )
        first = revalidator.revalidate(authorization_issue_number)
        final = revalidator.revalidate(authorization_issue_number)
        if first != final:
            _fail("canonical GCS auth-binding evidence drifted")
        return dict(public_receipt(apply_auth_binding(final, replay=replay)))
    except WeatherNextPrivateGCSAuthBindingError:
        raise
    except Exception:
        raise WeatherNextPrivateGCSAuthBindingError(
            "WeatherNext private GCS auth-binding operation failed closed"
        ) from None


def source_readiness() -> Mapping[str, Any]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_repository": SOURCE_REPOSITORY,
        "protected_source_binding_root": str(SOURCE_BINDING_ROOT),
        "caller_authority": ("authorization_issue_number",),
        "fixed_registry_execution_enabled": False,
        "global_executor_execution_enabled": False,
        "protected_source_read_before_consume": False,
        "google_request_enabled": False,
        "bigquery_execution_enabled": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
