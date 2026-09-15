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
from .weather_private_bigquery_host_installer import (
    ADAPTER_ID,
    BASELINE_RESOLVER_ID,
    DEPENDENCIES if False else ADAPTER_ID,
)
from .weather_private_bigquery_host_installer import (
    CanonicalInstallEvidence,
    PosixFixedInstallBackend,
    REQUIRED_EXCLUSIONS,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    WeatherNextPrivateHostInstallerError,
    apply_install,
)
from .weather_private_bigquery_host_runtime import (
    INSTALL_MUTATION_BUDGET,
    INSTALL_OPERATION_ID,
    INSTALL_ROLLBACK_POLICY,
    INSTALL_TARGET_ALIAS,
)
from .weather_public_runtime_composite import FixedPublicGitHubReadClient

IMPLEMENTATION_ISSUE = 554
AUTH_SURFACE = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_PRIVATE_KEY = Path("/etc/rozkalns-deploy-executor/github-app.pem")
STATE_DB = Path("/var/lib/rozkalns-deploy-executor-p9/state.sqlite3")
EXECUTION_LOCATION_CLASS = "trusted-home-host"
DEPLOY_CLASS = "STRICT_LIVE_AUTH_REQUIRED"
MINIMUM_REVIEWED_ANCESTOR = "1fa9ace14aa8b0b7c3c46ac465f1a5093d35d0a7"
DEPENDENCIES = (
    "source-contract:RPi5_main#552",
    "privileged-installer-contract:RPi5_main#554",
    f"minimum-reviewed-ancestor:{MINIMUM_REVIEWED_ANCESTOR}",
    "global-executor-execution:disabled",
)


def _fail(message: str) -> None:
    raise WeatherNextPrivateHostInstallerError(message)


def _fixed_registry() -> OperationRegistry:
    operation = OperationSpec(
        operation_id=INSTALL_OPERATION_ID,
        source_repository=SOURCE_REPOSITORY,
        queue_match=QueueMatch(
            target_alias=INSTALL_TARGET_ALIAS,
            execution_location_class=EXECUTION_LOCATION_CLASS,
            repository_entrypoint="ops/bin/rpi5-weathernext-private-host-privileged-install",
            deploy_class=DEPLOY_CLASS,
        ),
        target_alias=INSTALL_TARGET_ALIAS,
        adapter_id=ADAPTER_ID,
        authorization_class="STRICT",
        ordinary_live_all_eligible=False,
        baseline=BaselineContract(kind="resolver", resolver_id=BASELINE_RESOLVER_ID),
        mutation_budget=tuple(
            MutationBudget(category=category, max_operations=maximum)
            for category, maximum in INSTALL_MUTATION_BUDGET
        ),
        rollback_policy=INSTALL_ROLLBACK_POLICY,
        exclusions=REQUIRED_EXCLUSIONS,
        dependencies=DEPENDENCIES,
        preflight=(
            "owner LIVE-AUTH and READY Queue are independently revalidated",
            "current RPi5_main exact-main required CI is successful",
            "fixed host install state is observed immediately before consume",
        ),
        postconditions=(
            "trusted checkout operator and activation marker are exact",
            "no WeatherNext application runtime Google BigQuery or SQLite stage executes",
        ),
        required_github_evidence=(
            "owner-authored non-App LIVE-AUTH",
            "READY Queue exact operation target and source binding",
            "current RPi5_main exact-main required CI",
        ),
    )
    return OperationRegistry(schema_version=1, execution_enabled=False, operations=(operation,))


def _require_live_authority(accepted: AcceptedAuthorization) -> Mapping[str, Any]:
    payload = accepted.payload
    expected = {
        "queue_repository": QUEUE_REPOSITORY,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": INSTALL_TARGET_ALIAS,
        "operation_id": INSTALL_OPERATION_ID,
        "expected_baseline": {"kind": "resolver", "value": BASELINE_RESOLVER_ID},
        "mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in INSTALL_MUTATION_BUDGET
        ],
        "rollback_policy": INSTALL_ROLLBACK_POLICY,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            _fail(f"canonical LIVE-AUTH {field} drifted")
    exclusions = payload.get("exclusions")
    if type(exclusions) is not list or not set(REQUIRED_EXCLUSIONS).issubset(set(exclusions)):
        _fail("canonical LIVE-AUTH exclusions drifted")
    return payload


def _require_queue(normalized: Any) -> Mapping[str, Any]:
    if getattr(normalized, "execution_enabled", None) is not False:
        _fail("private installer registry unexpectedly enables execution")
    operation = getattr(normalized, "operation", None)
    expected = {
        "operation_id": INSTALL_OPERATION_ID,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": INSTALL_TARGET_ALIAS,
        "adapter_id": ADAPTER_ID,
        "authorization_class": "STRICT",
        "ordinary_live_all_eligible": False,
        "rollback_policy": INSTALL_ROLLBACK_POLICY,
    }
    for field, value in expected.items():
        if getattr(operation, field, None) != value:
            _fail(f"private installer Queue {field} drifted")
    observed_budget = tuple(
        (item.category, item.max_operations)
        for item in getattr(operation, "mutation_budget", ())
    )
    if observed_budget != INSTALL_MUTATION_BUDGET:
        _fail("private installer Queue mutation budget drifted")
    baseline = getattr(operation, "baseline", None)
    if (
        getattr(baseline, "kind", None) != "resolver"
        or getattr(baseline, "resolver_id", None) != BASELINE_RESOLVER_ID
    ):
        _fail("private installer Queue baseline drifted")
    protocol_queue = normalized.as_protocol_queue()
    if protocol_queue.get("expected_baseline") != {
        "kind": "resolver",
        "value": BASELINE_RESOLVER_ID,
    }:
        _fail("private installer Queue baseline binding drifted")
    return protocol_queue


def _server_time(response: Any) -> datetime:
    value = getattr(response, "server_time", None)
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fail("GitHub server time is unavailable")
    return value.astimezone(timezone.utc)


class DurableInstallReplayAuthority:
    """Use the reviewed P9 durable state store for one capability-specific consume."""

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
        except WeatherNextPrivateHostInstallerError:
            raise
        except sqlite3.DatabaseError as exc:
            raise WeatherNextPrivateHostInstallerError("durable replay database read failed") from exc

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

    def mark_succeeded(self, request_id: str) -> None:
        if not self._terminal:
            _fail("cannot mark an unconsumed request succeeded")
        store = StateStore(STATE_DB)
        try:
            store.transition(request_id, "VERIFYING")
            record = store.transition(request_id, "SUCCEEDED")
            if record.state != "SUCCEEDED":
                _fail("authorization result did not reach SUCCEEDED")
        finally:
            store.close()


class ConcreteCanonicalInstallRevalidator:
    def __init__(
        self,
        *,
        authorization_client: Any,
        queue_client: Any,
        source_client: FixedPublicGitHubReadClient,
        auth_surface: Any,
        replay: DurableInstallReplayAuthority,
    ):
        require_isolated_auth_surface(auth_surface)
        self._authorization_client = authorization_client
        self._queue_client = queue_client
        self._source_client = source_client
        self._auth_surface = auth_surface
        self._replay = replay
        self._registry = _fixed_registry()

    def revalidate(self, issue_number: int) -> CanonicalInstallEvidence:
        if type(issue_number) is not int or not 1 <= issue_number <= 2_147_483_647:
            _fail("authorization issue number is invalid")
        require_isolated_auth_surface(self._auth_surface)

        auth_repo = self._authorization_client.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}")
        if (
            type(auth_repo.value) is not dict
            or auth_repo.value.get("id") != AUTHORIZATION_REPOSITORY_ID
            or auth_repo.value.get("full_name") != AUTHORIZATION_REPOSITORY
        ):
            _fail("authorization repository identity drifted")
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

        queue_repo = self._queue_client.get_json(f"/repos/{QUEUE_REPOSITORY}")
        if (
            type(queue_repo.value) is not dict
            or queue_repo.value.get("id") != QUEUE_REPOSITORY_ID
            or queue_repo.value.get("full_name") != QUEUE_REPOSITORY
        ):
            _fail("Queue repository identity drifted")
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

        source_sha = payload["source_sha"]
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
            _fail("RPi5_main source is outside reviewed installer ancestry")

        if self._replay.is_available(accepted) is not True:
            _fail("LIVE-AUTH is unavailable for one-shot consume")

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
            _fail("LIVE-AUTH replay state drifted during final revalidation")

        return CanonicalInstallEvidence(
            authorization_issue_number=issue_number,
            authorization_issue_id=accepted.issue_id,
            authorization_created_at=accepted.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            github_server_time=_server_time(final).strftime("%Y-%m-%dT%H:%M:%SZ"),
            request_id=accepted.request_id,
            request_body_sha256=accepted.raw_body_sha256,
            operation_id=INSTALL_OPERATION_ID,
            target_alias=INSTALL_TARGET_ALIAS,
            rpi5_main_sha=source_sha,
            queue_issue_number=queue_issue_number,
        )


def _require_stable_evidence(first: CanonicalInstallEvidence, final: CanonicalInstallEvidence) -> None:
    for field in (
        "authorization_issue_number",
        "authorization_issue_id",
        "request_id",
        "request_body_sha256",
        "operation_id",
        "target_alias",
        "rpi5_main_sha",
        "queue_issue_number",
        "queue_ready",
        "owner_verified",
        "app_authored",
        "authorization_ttl_valid",
        "authorization_body_unchanged",
        "authorization_replay_available",
        "source_exact_main",
        "source_merged_reachable",
        "source_ci_success",
        "rollback_policy",
    ):
        if getattr(first, field) != getattr(final, field):
            _fail(f"canonical install evidence drifted: {field}")


def run_privileged_install(authorization_issue_number: int) -> Any:
    """Build the fixed runtime and execute one JIT-revalidated install request."""

    if os.geteuid() != 0:
        _fail("private host privileged installer must run as root")
    replay = DurableInstallReplayAuthority()
    try:
        auth_surface = load_contract(AUTH_SURFACE)
        require_isolated_auth_surface(auth_surface)
        clients = build_p9_read_clients(
            auth_surface=auth_surface,
            private_key=EXECUTOR_PRIVATE_KEY,
        )
        revalidator = ConcreteCanonicalInstallRevalidator(
            authorization_client=clients.authorization,
            queue_client=clients.queue,
            source_client=FixedPublicGitHubReadClient(),
            auth_surface=auth_surface,
            replay=replay,
        )
        first = revalidator.revalidate(authorization_issue_number)
        final = revalidator.revalidate(authorization_issue_number)
        _require_stable_evidence(first, final)
        return apply_install(
            final,
            replay=replay,
            backend=PosixFixedInstallBackend(),
        )
    except WeatherNextPrivateHostInstallerError:
        raise
    except Exception:
        raise WeatherNextPrivateHostInstallerError(
            "WeatherNext private host privileged install failed closed"
        ) from None


def source_readiness() -> Mapping[str, Any]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "concrete_canonical_revalidator_implemented": True,
        "durable_one_shot_replay_implemented": True,
        "fixed_runtime_factory_implemented": True,
        "runtime_factory_arguments": (),
        "caller_authority": ("authorization_issue_number",),
        "authorization_repository": AUTHORIZATION_REPOSITORY,
        "queue_repository": QUEUE_REPOSITORY,
        "source_repository": SOURCE_REPOSITORY,
        "install_operation_id": INSTALL_OPERATION_ID,
        "install_target_alias": INSTALL_TARGET_ALIAS,
        "fixed_registry_execution_enabled": False,
        "global_executor_execution_enabled": False,
        "runtime_activation_enabled": False,
        "privileged_boundary_installed": False,
        "privileged_dispatch_enabled": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
