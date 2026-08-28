from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Callable, Mapping, Protocol

AUTHORIZATION_REPOSITORY = "rozkalnsandris/ops-workflows"
AUTHORIZATION_REPOSITORY_ID = 1328835922
GOVERNANCE_MAX_AGE_SECONDS = 300
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class P9CanaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class GovernanceEvidence:
    repository: str
    repository_id: int
    observed_at: datetime
    writer_set_sha256: str
    trusted: bool

    def require_current(self, *, server_time: datetime) -> None:
        if self.repository != AUTHORIZATION_REPOSITORY or self.repository_id != AUTHORIZATION_REPOSITORY_ID:
            raise P9CanaryError("governance evidence is bound to the wrong authorization repository")
        if self.trusted is not True:
            raise P9CanaryError("authorization writer-set governance is not trusted")
        if self.observed_at.tzinfo is None or server_time.tzinfo is None:
            raise P9CanaryError("governance/server timestamps must be timezone-aware")
        if SHA256_RE.fullmatch(self.writer_set_sha256) is None:
            raise P9CanaryError("governance writer-set digest is malformed")
        age = (server_time.astimezone(timezone.utc) - self.observed_at.astimezone(timezone.utc)).total_seconds()
        if age < 0 or age > GOVERNANCE_MAX_AGE_SECONDS:
            raise P9CanaryError("governance evidence is stale or from the future")


@dataclass(frozen=True)
class BaselineEvidence:
    resolver_id: str
    target_alias: str
    matched: bool
    evidence_id: str


@dataclass(frozen=True)
class P9DryRunReady:
    result: str
    issue_number: int
    request_id: str
    queue_issue: int
    source_repository: str
    source_sha: str
    current_main_sha: str
    operation_id: str
    target_alias: str
    baseline_resolver: str
    baseline_evidence_id: str
    source_ci_run_id: int
    mutation_dispatch_enabled: bool = False
    result_writer_enabled: bool = False
    production_mutation_started: bool = False


class JSONResponseLike(Protocol):
    value: Any
    server_time: datetime


class AuthorityClient(Protocol):
    def get_json(self, path_or_url: str) -> JSONResponseLike: ...
    def read_live_auth(
        self,
        issue_number: int,
        *,
        governance_ok: bool,
        approved_operator_app_ids: frozenset[int] = frozenset(),
    ) -> Any: ...
    def verify_live_auth_unchanged(
        self,
        accepted: Any,
        *,
        governance_ok: bool,
        approved_operator_app_ids: frozenset[int] = frozenset(),
    ) -> None: ...


class StateStoreLike(Protocol):
    def discover(self, **kwargs: Any) -> Any: ...
    def transition(self, request_id: str, new_state: str) -> Any: ...


class SourceEvidenceLike(Protocol):
    repository: str
    source_sha: str
    current_main_sha: str
    run_id: int


class NormalizedQueueLike(Protocol):
    operation: Any
    execution_enabled: bool
    def as_protocol_queue(self) -> Mapping[str, Any]: ...


class PreparedOperationLike(Protocol):
    adapter_id: str
    execution_enabled: bool


class AdapterLike(Protocol):
    def preflight(self, prepared: PreparedOperationLike) -> Mapping[str, Any]: ...


class AdapterCatalogLike(Protocol):
    def require(self, adapter_id: str) -> AdapterLike: ...


def _positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        raise P9CanaryError(f"{where} must be a positive integer")
    return value


def _require_queue_issue_identity(value: Any, *, queue_issue: int) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise P9CanaryError("queue issue response is not an object")
    if value.get("number") != queue_issue:
        raise P9CanaryError("queue issue number drifted")
    expected_url = f"https://api.github.com/repos/{AUTHORIZATION_REPOSITORY}"
    if value.get("repository_url") not in {None, expected_url}:
        raise P9CanaryError("queue issue repository_url drifted")
    return value


def run_p9_dry_run_canary(
    *,
    issue_number: int,
    authority_client: AuthorityClient,
    source_client: Any,
    governance: GovernanceEvidence,
    state_store: StateStoreLike,
    registry: Any,
    adapter_catalog: AdapterCatalogLike,
    normalize_ready_queue: Callable[..., NormalizedQueueLike],
    validate_queue_binding: Callable[[Any, Mapping[str, Any]], None],
    verify_source_evidence: Callable[..., SourceEvidenceLike],
    resolve_baseline: Callable[[Any, Mapping[str, Any]], BaselineEvidence],
    prepare_operation: Callable[[NormalizedQueueLike], PreparedOperationLike],
    approved_operator_app_ids: frozenset[int] = frozenset(),
) -> P9DryRunReady:
    _positive_int(issue_number, "LIVE-AUTH issue number")

    governance_probe = authority_client.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}")
    governance.require_current(server_time=governance_probe.server_time)

    accepted = authority_client.read_live_auth(
        issue_number,
        governance_ok=True,
        approved_operator_app_ids=approved_operator_app_ids,
    )
    state_store.discover(
        repository_id=accepted.repository_id,
        issue_id=accepted.issue_id,
        request_id=accepted.request_id,
        canonical_payload_sha256=accepted.canonical_payload_sha256,
        raw_body_sha256=accepted.raw_body_sha256,
    )
    state_store.transition(accepted.request_id, "VALIDATING")

    payload = accepted.payload
    queue_issue = _positive_int(payload.get("queue_issue"), "queue_issue")
    queue_response = authority_client.get_json(
        f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{queue_issue}"
    )
    queue_issue_payload = _require_queue_issue_identity(queue_response.value, queue_issue=queue_issue)
    normalized = normalize_ready_queue(
        queue_issue_payload,
        repository_full_name=AUTHORIZATION_REPOSITORY,
        registry=registry,
    )
    if normalized.execution_enabled:
        raise P9CanaryError("P9 requires an execution-disabled operation registry")
    protocol_queue = normalized.as_protocol_queue()
    validate_queue_binding(accepted, protocol_queue)

    source = verify_source_evidence(
        source_client,
        source_repository=payload["source_repository"],
        source_sha=payload["source_sha"],
    )
    baseline = resolve_baseline(normalized.operation, payload["expected_baseline"])
    if baseline.matched is not True:
        raise P9CanaryError("read-only target baseline did not match")
    if baseline.target_alias != payload["target_alias"]:
        raise P9CanaryError("baseline evidence target alias drifted")

    prepared = prepare_operation(normalized)
    if prepared.execution_enabled:
        raise P9CanaryError("P9 prepared operation unexpectedly enables execution")
    adapter = adapter_catalog.require(prepared.adapter_id)
    preflight = adapter.preflight(prepared)
    if type(preflight) is not dict or not preflight:
        raise P9CanaryError("adapter read-only preflight returned no evidence")
    if preflight.get("read_only") is False:
        raise P9CanaryError("adapter preflight does not preserve read-only mode")
    for flag in (
        "mutation_enabled",
        "execution_enabled",
        "privileged_dispatch_ready",
        "production_apply_authorized",
    ):
        if preflight.get(flag) is True:
            raise P9CanaryError(f"adapter preflight unexpectedly enables {flag}")

    # Re-check the same short-lived governance attestation against a fresh
    # GitHub server clock immediately before the final authority re-fetch.
    final_governance_probe = authority_client.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}")
    governance.require_current(server_time=final_governance_probe.server_time)

    # The authorization must still be byte/canonical-equivalent immediately
    # before DRY_RUN_READY is emitted. P9 never calls adapter.apply(),
    # StateStore.consume(), a dispatcher, or a GitHub result writer.
    authority_client.verify_live_auth_unchanged(
        accepted,
        governance_ok=True,
        approved_operator_app_ids=approved_operator_app_ids,
    )
    state_store.transition(accepted.request_id, "ACCEPTED")

    return P9DryRunReady(
        result="DRY_RUN_READY",
        issue_number=issue_number,
        request_id=accepted.request_id,
        queue_issue=queue_issue,
        source_repository=source.repository,
        source_sha=source.source_sha,
        current_main_sha=source.current_main_sha,
        operation_id=payload["operation_id"],
        target_alias=payload["target_alias"],
        baseline_resolver=baseline.resolver_id,
        baseline_evidence_id=baseline.evidence_id,
        source_ci_run_id=source.run_id,
    )
