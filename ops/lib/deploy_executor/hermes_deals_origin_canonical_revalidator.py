from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from .adapters import prepare_operation
from .hermes_deals_origin_adapter import (
    ADAPTER_ID,
    DISPATCHER_SOURCE_BLOB,
    HermesDealsOriginAuditAdapter,
    INSTALLER_SOURCE_BLOB,
    OPERATION_ID,
    PROBE_SOURCE_BLOB,
    PULL_HELPER_ARGUMENTS,
    PULL_HELPER_CAPABILITY,
    PULL_HELPER_EVIDENCE_SCHEMA,
    PULL_HELPER_MACHINE_ID,
    PULL_HELPER_REGISTRATION_SCHEMA,
    PULL_HELPER_SOURCE_BLOB,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    TARGET_ALIAS,
    WORKFLOW_SOURCE_BLOB,
)
from .hermes_deals_origin_privileged_consumer import CanonicalHermesOriginEvidence
from .p9_canary import require_isolated_auth_surface
from .p9_runtime import P9ExecutorInstallationTokenProvider
from .p9_source_auth import (
    HERMES_DEALS_SOURCE_REPOSITORY,
    HERMES_DEALS_SOURCE_REPOSITORY_ID,
    P9SourceInstallationTokenProvider,
    REQUIRED_PERMISSIONS,
    SOURCE_APP_ID,
    SOURCE_INSTALLATION_ID,
)
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
from .source_evidence import verify_source_evidence
from .transport import GitHubRestClient

MAX_GITHUB_TIMESTAMP_SPREAD_SECONDS = 30
CANONICAL_REVALIDATOR_IMPLEMENTED = True
SOURCE_READ_AUTHORITY_PROVEN = False
PRODUCTION_MUTATION_STARTED = False


class ConcreteCanonicalHermesOriginRevalidatorError(RuntimeError):
    pass


class AuthorizationReplayAvailability(Protocol):
    """Read-only replay decision supplied by the existing durable authority store."""

    def is_available(self, accepted: AcceptedAuthorization) -> bool: ...


@dataclass
class _GitHubTimeWindow:
    first: datetime | None = None
    last: datetime | None = None

    def observe(self, value: Any) -> None:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "GitHub response time is unavailable"
            )
        observed = value.astimezone(timezone.utc)
        if observed.microsecond != 0:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "GitHub response time is not canonical to whole seconds"
            )
        if self.last is not None and observed < self.last:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "GitHub response time regressed during canonical revalidation"
            )
        if self.first is None:
            self.first = observed
        if (
            observed - self.first
        ).total_seconds() > MAX_GITHUB_TIMESTAMP_SPREAD_SECONDS:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "GitHub response times are inconsistent during canonical revalidation"
            )
        self.last = observed

    def canonical_last(self) -> str:
        if self.last is None:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "canonical revalidation observed no GitHub response time"
            )
        return self.last.strftime("%Y-%m-%dT%H:%M:%SZ")


class _TimedSourceClient:
    def __init__(self, client: GitHubRestClient, window: _GitHubTimeWindow):
        self._client = client
        self._window = window

    def get_json(self, path_or_url: str) -> Any:
        response = self._client.get_json(path_or_url)
        self._window.observe(getattr(response, "server_time", None))
        return response


def _require_repository(
    response: Any,
    *,
    repository: str,
    repository_id: int,
    window: _GitHubTimeWindow,
) -> None:
    window.observe(getattr(response, "server_time", None))
    value = getattr(response, "value", None)
    if type(value) is not dict:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "GitHub repository identity response is malformed"
        )
    if value.get("id") != repository_id or value.get("full_name") != repository:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "GitHub repository identity drifted"
        )


def _require_read_clients(
    authorization_client: GitHubRestClient,
    queue_client: GitHubRestClient,
    source_client: GitHubRestClient,
) -> None:
    if any(
        type(client) is not GitHubRestClient
        for client in (authorization_client, queue_client, source_client)
    ):
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "canonical revalidator requires reviewed GitHub read clients"
        )

    authorization_provider = authorization_client.token_provider
    queue_provider = queue_client.token_provider
    if type(authorization_provider) is not P9ExecutorInstallationTokenProvider:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "authorization client is not bound to the reviewed read-only App"
        )
    if type(queue_provider) is not P9ExecutorInstallationTokenProvider:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "queue client is not bound to the reviewed read-only App"
        )
    if (
        authorization_provider.repository != AUTHORIZATION_REPOSITORY
        or authorization_provider.repository_id != AUTHORIZATION_REPOSITORY_ID
        or queue_provider.repository != QUEUE_REPOSITORY
        or queue_provider.repository_id != QUEUE_REPOSITORY_ID
    ):
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "control-plane read client repository binding drifted"
        )

    source_provider = source_client.token_provider
    if type(source_provider) is not P9SourceInstallationTokenProvider:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "source client is not the reviewed Hermes Source App composition"
        )
    if (
        source_provider.repository != HERMES_DEALS_SOURCE_REPOSITORY
        or source_provider.repository_id != HERMES_DEALS_SOURCE_REPOSITORY_ID
        or HERMES_DEALS_SOURCE_REPOSITORY != SOURCE_REPOSITORY
        or HERMES_DEALS_SOURCE_REPOSITORY_ID != SOURCE_REPOSITORY_ID
    ):
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "Hermes Source App repository binding drifted"
        )


def _require_issue_response(
    response: Any,
    *,
    issue_number: int,
    repository: str,
    window: _GitHubTimeWindow,
) -> Mapping[str, Any]:
    window.observe(getattr(response, "server_time", None))
    value = getattr(response, "value", None)
    if type(value) is not dict or value.get("number") != issue_number:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "GitHub issue identity drifted"
        )
    expected_url = f"https://api.github.com/repos/{repository}"
    if value.get("repository_url") not in {None, expected_url}:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "GitHub issue repository identity drifted"
        )
    return value


def _require_hermes_operation(normalized: Any) -> tuple[Any, Mapping[str, Any]]:
    if getattr(normalized, "execution_enabled", None) is not False:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "Hermes operation registry must remain execution-disabled"
        )
    operation = getattr(normalized, "operation", None)
    expected = {
        "operation_id": OPERATION_ID,
        "adapter_id": ADAPTER_ID,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "authorization_class": "STRICT",
        "ordinary_live_all_eligible": False,
    }
    for name, value in expected.items():
        if getattr(operation, name, None) != value:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                f"canonical Hermes operation {name} drifted"
            )
    baseline = getattr(operation, "baseline", None)
    if (
        getattr(baseline, "kind", None) != "resolver"
        or getattr(baseline, "resolver_id", None)
        != "hermes-deals.origin-path-registration.v1"
    ):
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "canonical Hermes baseline contract drifted"
        )
    protocol_queue = normalized.as_protocol_queue()
    if protocol_queue.get("expected_baseline") != {
        "kind": "resolver",
        "value": "hermes-deals.origin-path-registration.v1",
    }:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "canonical Hermes queue baseline binding drifted"
        )
    return operation, protocol_queue


def _require_adapter_preflight(normalized: Any) -> Mapping[str, Any]:
    prepared = prepare_operation(normalized)
    if prepared.execution_enabled is not False:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "prepared Hermes operation unexpectedly enables execution"
        )
    result = HermesDealsOriginAuditAdapter().preflight(prepared)
    expected = {
        "adapter_id": ADAPTER_ID,
        "source_sha": prepared.source_sha,
        "source_repository_id": SOURCE_REPOSITORY_ID,
        "workflow_source_blob": WORKFLOW_SOURCE_BLOB,
        "dispatcher_source_blob": DISPATCHER_SOURCE_BLOB,
        "installer_source_blob": INSTALLER_SOURCE_BLOB,
        "probe_source_blob": PROBE_SOURCE_BLOB,
        "pull_helper_source_blob": PULL_HELPER_SOURCE_BLOB,
        "pull_helper_capability": PULL_HELPER_CAPABILITY,
        "pull_helper_registration_schema": PULL_HELPER_REGISTRATION_SCHEMA,
        "pull_helper_evidence_schema": PULL_HELPER_EVIDENCE_SCHEMA,
        "pull_helper_machine_id": PULL_HELPER_MACHINE_ID,
        "pull_helper_arguments": PULL_HELPER_ARGUMENTS,
        "pull_helper_interface_bound": True,
        "read_only": True,
        "execution_enabled": False,
        "privileged_dispatch_ready": False,
        "result": "SOURCE_CANARY_CONTRACT_PASS",
    }
    if result != expected:
        raise ConcreteCanonicalHermesOriginRevalidatorError(
            "Hermes adapter preflight evidence drifted"
        )
    return result


class ConcreteCanonicalHermesOriginRevalidator:
    """Reconstruct canonical Hermes authority using only reviewed read clients.

    The constructor accepts no repository, SHA, URL, path, capability, command,
    argv, environment or identity selector. The socket caller can supply only the
    LIVE-AUTH issue number to :meth:`revalidate`.
    """

    def __init__(
        self,
        *,
        authorization_client: GitHubRestClient,
        queue_client: GitHubRestClient,
        source_client: GitHubRestClient,
        auth_surface: Any,
        registry: Any,
        replay_availability: AuthorizationReplayAvailability,
    ):
        _require_read_clients(authorization_client, queue_client, source_client)
        require_isolated_auth_surface(auth_surface)
        if getattr(registry, "execution_enabled", None) is not False:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "canonical Hermes registry must remain execution-disabled"
            )
        if not callable(getattr(replay_availability, "is_available", None)):
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "canonical Hermes replay availability is missing"
            )
        self._authorization_client = authorization_client
        self._queue_client = queue_client
        self._source_client = source_client
        self._auth_surface = auth_surface
        self._registry = registry
        self._replay_availability = replay_availability

    def revalidate(self, authorization_issue_number: int) -> CanonicalHermesOriginEvidence:
        if type(authorization_issue_number) is not int or not (
            1 <= authorization_issue_number <= 2_147_483_647
        ):
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "authorization issue number is invalid"
            )
        try:
            return self._revalidate(authorization_issue_number)
        except ConcreteCanonicalHermesOriginRevalidatorError:
            raise
        except Exception:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "canonical Hermes revalidation failed closed"
            ) from None

    def _revalidate(self, issue_number: int) -> CanonicalHermesOriginEvidence:
        _require_read_clients(
            self._authorization_client,
            self._queue_client,
            self._source_client,
        )
        require_isolated_auth_surface(self._auth_surface)
        window = _GitHubTimeWindow()

        auth_repository_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}"
        )
        _require_repository(
            auth_repository_response,
            repository=AUTHORIZATION_REPOSITORY,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            window=window,
        )
        issue_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        issue = _require_issue_response(
            issue_response,
            issue_number=issue_number,
            repository=AUTHORIZATION_REPOSITORY,
            window=window,
        )
        accepted = accept_issue(
            issue,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=issue_response.server_time,
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        payload = accepted.payload
        if (
            payload.get("source_repository") != SOURCE_REPOSITORY
            or payload.get("operation_id") != OPERATION_ID
            or payload.get("target_alias") != TARGET_ALIAS
        ):
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "LIVE-AUTH is not the fixed Hermes origin capability"
            )

        queue_repository_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}"
        )
        _require_repository(
            queue_repository_response,
            repository=QUEUE_REPOSITORY,
            repository_id=QUEUE_REPOSITORY_ID,
            window=window,
        )
        queue_issue_number = payload.get("queue_issue")
        if type(queue_issue_number) is not int or queue_issue_number < 1:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "canonical Hermes queue issue is invalid"
            )
        queue_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue_number}"
        )
        queue_issue = _require_issue_response(
            queue_response,
            issue_number=queue_issue_number,
            repository=QUEUE_REPOSITORY,
            window=window,
        )
        normalized = normalize_ready_queue(
            queue_issue,
            repository_full_name=QUEUE_REPOSITORY,
            registry=self._registry,
        )
        operation, protocol_queue = _require_hermes_operation(normalized)
        validate_queue_binding(accepted, protocol_queue)

        source = verify_source_evidence(
            _TimedSourceClient(self._source_client, window),
            source_repository=SOURCE_REPOSITORY,
            source_sha=payload["source_sha"],
        )
        if source.repository_id != SOURCE_REPOSITORY_ID:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "canonical Hermes source repository identity drifted"
            )
        preflight = _require_adapter_preflight(normalized)
        replay_available = self._replay_availability.is_available(accepted)
        if type(replay_available) is not bool or replay_available is not True:
            raise ConcreteCanonicalHermesOriginRevalidatorError(
                "canonical Hermes authorization is unavailable for one-shot consumption"
            )

        require_isolated_auth_surface(self._auth_surface)
        final_repository_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}"
        )
        _require_repository(
            final_repository_response,
            repository=AUTHORIZATION_REPOSITORY,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            window=window,
        )
        final_issue_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        final_issue = _require_issue_response(
            final_issue_response,
            issue_number=issue_number,
            repository=AUTHORIZATION_REPOSITORY,
            window=window,
        )
        verify_authorization_unchanged(
            accepted,
            final_issue,
            server_time=final_issue_response.server_time,
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )

        return CanonicalHermesOriginEvidence(
            authorization_issue_number=issue_number,
            authorization_created_at=accepted.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            github_server_time=window.canonical_last(),
            request_id=accepted.request_id,
            queue_issue=queue_issue_number,
            source_repository=source.repository,
            source_sha=source.source_sha,
            current_main_sha=source.current_main_sha,
            source_ci_run_id=source.run_id,
            operation_id=operation.operation_id,
            adapter_id=operation.adapter_id,
            target_alias=operation.target_alias,
            authorization_class=operation.authorization_class,
            ordinary_live_all_eligible=operation.ordinary_live_all_eligible,
            rollback_policy=operation.rollback_policy,
            mutation_budget=tuple(
                (item.category, item.max_operations)
                for item in operation.mutation_budget
            ),
            exclusions=tuple(operation.exclusions),
            dependencies=tuple(protocol_queue["dependencies"]),
            isolated_authorization_surface_valid=True,
            authorization_owner_verified=True,
            authorization_ttl_valid=True,
            authorization_body_unchanged=True,
            authorization_replay_available=True,
            queue_ready=True,
            queue_binding_valid=True,
            registry_execution_enabled=False,
            source_reachable_from_main=True,
            source_ci_success=True,
            baseline_contract_valid=True,
            prepared_execution_enabled=False,
            adapter_preflight_read_only=preflight["read_only"],
            adapter_preflight_privileged_dispatch_ready=preflight[
                "privileged_dispatch_ready"
            ],
        )


def source_readiness() -> Mapping[str, object]:
    return {
        "concrete_canonical_revalidator_implemented": CANONICAL_REVALIDATOR_IMPLEMENTED,
        "source_repository": SOURCE_REPOSITORY,
        "source_repository_id": SOURCE_REPOSITORY_ID,
        "source_app_id": SOURCE_APP_ID,
        "source_installation_id": SOURCE_INSTALLATION_ID,
        "source_permissions": dict(REQUIRED_PERMISSIONS),
        "caller_authority": ("authorization_issue_number",),
        "github_timestamp_spread_seconds": MAX_GITHUB_TIMESTAMP_SPREAD_SECONDS,
        "source_read_authority_proven": SOURCE_READ_AUTHORITY_PROVEN,
        "credential_read_or_write_implemented": False,
        "permission_mutation_authorized": False,
        "production_mutation_started": PRODUCTION_MUTATION_STARTED,
    }
