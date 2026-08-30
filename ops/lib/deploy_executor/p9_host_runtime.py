from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .adapters import AdapterCatalog, prepare_operation
from .control_center_postcanary_adapter import ControlCenterPostCanaryAdapter
from .p9_canary import P9DryRunReady, require_isolated_auth_surface, run_p9_dry_run_canary
from .p9_evidence import resolve_p9_baseline
from .p9_isolated_auth_surface import load_contract
from .p9_provenance import load_control_postcanary_baseline_evidence
from .p9_runtime import build_p9_read_clients
from .p9_source_auth import CONTROL_SOURCE_REPOSITORY, P9SourceInstallationTokenProvider
from .protocol import QUEUE_REPOSITORY, validate_queue_binding
from .queue_normalizer import normalize_ready_queue
from .registry import load_registry
from .source_evidence import verify_source_evidence
from .state import StateStore
from .transport import GitHubHttpsSender, GitHubRestClient, HTTPSender, JSONResponse

DEFAULT_ISOLATED_AUTH = Path("/etc/rozkalns-deploy-executor/executor-p9-isolated-auth-surface.json")
DEFAULT_REGISTRY = Path("/etc/rozkalns-deploy-executor/executor-operations.json")
DEFAULT_EXECUTOR_KEY = Path("/etc/rozkalns-deploy-executor/github-app.pem")
DEFAULT_SOURCE_KEY = Path("/root/.config/rozkalns-automation/github-app.pem")
DEFAULT_STATE_DB = Path("/var/lib/rozkalns-deploy-executor-p9/state.sqlite3")
CONTROL_OPERATION_ID = "rozkalns-control-center.merge-postcanary-reconcile.v1"


class P9HostRuntimeError(RuntimeError):
    pass


class CapturingGitHubClient:
    def __init__(self, client: GitHubRestClient):
        self.client = client
        self.last_server_time: datetime | None = None

    def get_json(self, path_or_url: str, **kwargs: Any) -> JSONResponse:
        response = self.client.get_json(path_or_url, **kwargs)
        self.last_server_time = response.server_time
        return response


def _load_registry_exact(path: str | Path):
    registry = load_registry(path)
    if registry.execution_enabled is not False:
        raise P9HostRuntimeError("P9 host registry unexpectedly enables execution")
    if len(registry.operations) != 1:
        raise P9HostRuntimeError("P9 host registry must contain exactly one reviewed operation")
    operation = registry.operations[0]
    if operation.operation_id != CONTROL_OPERATION_ID or operation.source_repository != CONTROL_SOURCE_REPOSITORY:
        raise P9HostRuntimeError("P9 host registry does not select the reviewed Control operation")
    return registry


def _build_source_client(
    *,
    source_private_key: str | Path,
    sender: HTTPSender | None = None,
) -> CapturingGitHubClient:
    provider = P9SourceInstallationTokenProvider(
        repository=CONTROL_SOURCE_REPOSITORY,
        private_key=source_private_key,
    )
    return CapturingGitHubClient(
        GitHubRestClient(token_provider=provider, sender=sender or GitHubHttpsSender())
    )


@dataclass(frozen=True)
class P9HostPreflight:
    issue_number: int
    request_id: str
    queue_issue: int
    source_repository: str
    source_sha: str
    source_current_main_sha: str
    source_ci_run_id: int
    baseline_evidence_id: str
    operation_id: str
    execution_enabled: bool = False
    mutation_dispatch_enabled: bool = False
    result_writer_enabled: bool = False
    production_mutation_started: bool = False


def _preflight(
    *,
    issue_number: int,
    authorization_client: GitHubRestClient,
    queue_client: GitHubRestClient,
    source_client: CapturingGitHubClient,
    registry: Any,
    adapter_catalog: AdapterCatalog,
    trusted_baseline: dict[str, Any],
) -> P9HostPreflight:
    accepted = authorization_client.read_live_auth(
        issue_number,
        governance_ok=True,
        approved_operator_app_ids=frozenset(),
    )
    payload = accepted.payload
    queue_issue = payload.get("queue_issue")
    if type(queue_issue) is not int or queue_issue < 1:
        raise P9HostRuntimeError("LIVE-AUTH queue_issue is invalid")
    queue = queue_client.get_json(f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue}").value
    normalized = normalize_ready_queue(
        queue,
        repository_full_name=QUEUE_REPOSITORY,
        registry=registry,
    )
    validate_queue_binding(accepted, normalized.as_protocol_queue())
    source = verify_source_evidence(
        source_client,
        source_repository=payload["source_repository"],
        source_sha=payload["source_sha"],
    )
    server_time = source_client.last_server_time
    if server_time is None:
        raise P9HostRuntimeError("source evidence did not provide GitHub server time")
    baseline = resolve_p9_baseline(
        normalized.operation,
        payload["expected_baseline"],
        evidence=trusted_baseline,
        source_sha=source.source_sha,
        server_time=server_time,
    )
    prepared = prepare_operation(normalized)
    adapter = adapter_catalog.require(prepared.adapter_id)
    adapter_result = adapter.preflight(prepared)
    if adapter_result.get("read_only") is not True or adapter_result.get("execution_enabled") is not False:
        raise P9HostRuntimeError("adapter preflight did not preserve read-only execution-disabled state")
    if adapter_result.get("privileged_dispatch_ready") is not False:
        raise P9HostRuntimeError("adapter preflight unexpectedly enables privileged dispatch")
    authorization_client.verify_live_auth_unchanged(
        accepted,
        governance_ok=True,
        approved_operator_app_ids=frozenset(),
    )
    return P9HostPreflight(
        issue_number=issue_number,
        request_id=accepted.request_id,
        queue_issue=queue_issue,
        source_repository=source.repository,
        source_sha=source.source_sha,
        source_current_main_sha=source.current_main_sha,
        source_ci_run_id=source.run_id,
        baseline_evidence_id=baseline.evidence_id,
        operation_id=normalized.operation.operation_id,
    )


def run_p9_host_one_shot(
    *,
    issue_number: int,
    isolated_auth_path: str | Path = DEFAULT_ISOLATED_AUTH,
    registry_path: str | Path = DEFAULT_REGISTRY,
    executor_private_key: str | Path = DEFAULT_EXECUTOR_KEY,
    source_private_key: str | Path = DEFAULT_SOURCE_KEY,
    state_db: str | Path = DEFAULT_STATE_DB,
    sender: HTTPSender | None = None,
) -> tuple[P9HostPreflight, P9DryRunReady]:
    """Canonical manual P9 composition. No dispatcher/result writer/apply surface exists."""

    if type(issue_number) is not int or issue_number < 1:
        raise P9HostRuntimeError("LIVE-AUTH issue number must be positive")
    auth_surface = load_contract(isolated_auth_path)
    require_isolated_auth_surface(auth_surface)
    registry = _load_registry_exact(registry_path)
    trusted = load_control_postcanary_baseline_evidence()
    adapter_catalog = AdapterCatalog((ControlCenterPostCanaryAdapter(),))
    shared_sender = sender or GitHubHttpsSender()
    clients = build_p9_read_clients(
        auth_surface=auth_surface,
        private_key=executor_private_key,
        sender=shared_sender,
    )
    source_client = _build_source_client(
        source_private_key=source_private_key,
        sender=shared_sender,
    )
    preflight = _preflight(
        issue_number=issue_number,
        authorization_client=clients.authorization,
        queue_client=clients.queue,
        source_client=source_client,
        registry=registry,
        adapter_catalog=adapter_catalog,
        trusted_baseline=trusted.payload,
    )

    state_store = StateStore(state_db)
    context: dict[str, Any] = {}

    def source_verifier(client: Any, *, source_repository: str, source_sha: str):
        result = verify_source_evidence(
            client,
            source_repository=source_repository,
            source_sha=source_sha,
        )
        if source_client.last_server_time is None:
            raise P9HostRuntimeError("source verifier has no GitHub server time")
        context["source_sha"] = result.source_sha
        context["server_time"] = source_client.last_server_time
        return result

    def baseline_resolver(operation: Any, expected_baseline: dict[str, Any]):
        if "source_sha" not in context or "server_time" not in context:
            raise P9HostRuntimeError("baseline resolver ran before source verification")
        return resolve_p9_baseline(
            operation,
            expected_baseline,
            evidence=trusted.payload,
            source_sha=context["source_sha"],
            server_time=context["server_time"],
        )

    try:
        result = run_p9_dry_run_canary(
            issue_number=issue_number,
            authorization_client=clients.authorization,
            queue_client=clients.queue,
            source_client=source_client,
            auth_surface=auth_surface,
            state_store=state_store,
            registry=registry,
            adapter_catalog=adapter_catalog,
            normalize_ready_queue=normalize_ready_queue,
            validate_queue_binding=validate_queue_binding,
            verify_source_evidence=source_verifier,
            resolve_baseline=baseline_resolver,
            prepare_operation=prepare_operation,
        )
    finally:
        state_store.close()
    if result.mutation_dispatch_enabled or result.result_writer_enabled or result.production_mutation_started:
        raise P9HostRuntimeError("P9 result crossed a forbidden mutation boundary")
    return preflight, result


def public_result(preflight: P9HostPreflight, result: P9DryRunReady) -> dict[str, Any]:
    return {
        "preflight": asdict(preflight),
        "result": asdict(result),
    }
