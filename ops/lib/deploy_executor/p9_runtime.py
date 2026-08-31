from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .github_app_auth import (
    CONFIG_MODE,
    CONFIG_SCHEMA,
    DryRunAppConfig,
    GitHubAppInstallationTokenProvider,
    Requester,
    https_json_request,
)
from .p9_canary import P9DryRunReady, require_isolated_auth_surface, run_p9_dry_run_canary
from .p9_isolated_auth_surface import IsolatedAuthSurfaceContract, load_contract
from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    OWNER_USER_ID,
    QUEUE_REPOSITORY,
    QUEUE_REPOSITORY_ID,
)
from .transport import GitHubHttpsSender, GitHubRestClient, HTTPSender

EXECUTOR_APP_ID = 4748870
EXECUTOR_INSTALLATION_ID = 157217641
OWNER_LOGIN = "rozkalnsandris"
P8_COMPAT_POLL_INTERVAL_SECONDS = 120
LIVE_AUTH_TITLE_PREFIX = "[LIVE-AUTH][PENDING] "
PRODUCTION_MUTATION_STARTED = False


class P9RuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class P9ReadClients:
    authorization: GitHubRestClient
    queue: GitHubRestClient


def _repository_scope_config(
    *,
    repository: str,
    repository_id: int,
) -> DryRunAppConfig:
    return DryRunAppConfig(
        schema=CONFIG_SCHEMA,
        mode=CONFIG_MODE,
        app_id=EXECUTOR_APP_ID,
        installation_id=EXECUTOR_INSTALLATION_ID,
        authorization_repository=repository,
        authorization_repository_id=repository_id,
        owner_login=OWNER_LOGIN,
        owner_id=OWNER_USER_ID,
        poll_interval_seconds=P8_COMPAT_POLL_INTERVAL_SECONDS,
        issue_title_prefix=LIVE_AUTH_TITLE_PREFIX,
        mutation_dispatch_enabled=False,
        result_writer_enabled=False,
    )


def build_p9_read_clients(
    *,
    auth_surface: IsolatedAuthSurfaceContract,
    private_key: str | Path,
    sender: HTTPSender | None = None,
    requester: Requester = https_json_request,
    signer: Callable[[bytes, Path], bytes] | None = None,
) -> P9ReadClients:
    """Build two distinct read-only clients from one selected-repository App installation.

    Each token provider mints a token for exactly one repository. No generic
    two-repository token exists in this composition.
    """

    require_isolated_auth_surface(auth_surface)
    shared_sender = sender or GitHubHttpsSender()

    authorization_provider = GitHubAppInstallationTokenProvider(
        config=_repository_scope_config(
            repository=AUTHORIZATION_REPOSITORY,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
        ),
        private_key=private_key,
        requester=requester,
        signer=signer,
    )
    queue_provider = GitHubAppInstallationTokenProvider(
        config=_repository_scope_config(
            repository=QUEUE_REPOSITORY,
            repository_id=QUEUE_REPOSITORY_ID,
        ),
        private_key=private_key,
        requester=requester,
        signer=signer,
    )

    return P9ReadClients(
        authorization=GitHubRestClient(
            token_provider=authorization_provider,
            sender=shared_sender,
        ),
        queue=GitHubRestClient(
            token_provider=queue_provider,
            sender=shared_sender,
        ),
    )


def run_p9_one_shot(
    *,
    issue_number: int,
    isolated_auth_contract_path: str | Path,
    executor_private_key: str | Path,
    source_client: Any,
    state_store: Any,
    registry: Any,
    adapter_catalog: Any,
    normalize_ready_queue: Callable[..., Any],
    validate_queue_binding: Callable[[Any, Any], None],
    verify_source_evidence: Callable[..., Any],
    resolve_baseline: Callable[..., Any],
    prepare_operation: Callable[[Any], Any],
    sender: HTTPSender | None = None,
    requester: Requester = https_json_request,
    signer: Callable[[bytes, Path], bytes] | None = None,
) -> P9DryRunReady:
    """Source-only one-shot P9 composition.

    This function deliberately has no dispatcher, result writer, StateStore
    consume call, host wiring, service/timer activation, or production apply
    surface. The caller must supply the existing read-only source/CI client.
    """

    auth_surface = load_contract(isolated_auth_contract_path)
    require_isolated_auth_surface(auth_surface)
    clients = build_p9_read_clients(
        auth_surface=auth_surface,
        private_key=executor_private_key,
        sender=sender,
        requester=requester,
        signer=signer,
    )

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
        verify_source_evidence=verify_source_evidence,
        resolve_baseline=resolve_baseline,
        prepare_operation=prepare_operation,
    )
    if result.production_mutation_started is not False:
        raise P9RuntimeError("P9 one-shot unexpectedly crossed the production mutation boundary")
    if result.mutation_dispatch_enabled is not False or result.result_writer_enabled is not False:
        raise P9RuntimeError("P9 one-shot unexpectedly enabled a mutation or result-writer surface")
    return result
