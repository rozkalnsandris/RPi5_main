from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .github_app_auth import (
    CONFIG_MODE,
    CONFIG_SCHEMA,
    DryRunAppConfig,
    Requester,
    build_app_jwt,
    https_json_request,
    require_private_key,
    validate_installation,
    validate_token_response,
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
from .transport import API_VERSION, GitHubHttpsSender, GitHubRestClient, HTTPSender, InstallationToken

EXECUTOR_APP_ID = 4748870
EXECUTOR_INSTALLATION_ID = 157217641
OWNER_LOGIN = "rozkalnsandris"
OWNER_TYPE = "User"
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


def _executor_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "rozkalns-deploy-executor-p9/1",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _server_time(headers: Mapping[str, str]) -> datetime:
    value = next((candidate for key, candidate in headers.items() if key.lower() == "date"), None)
    if type(value) is not str:
        raise P9RuntimeError("executor repository-installation response omitted Date header")
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise P9RuntimeError("executor repository-installation Date header is invalid") from exc
    if parsed.tzinfo is None:
        raise P9RuntimeError("executor repository-installation Date header has no timezone")
    return parsed.astimezone(timezone.utc)


class P9ExecutorInstallationTokenProvider:
    """Mint once and cache one Issues-read token for one exact P9 control-plane repository."""

    _REPOSITORIES = {
        AUTHORIZATION_REPOSITORY: AUTHORIZATION_REPOSITORY_ID,
        QUEUE_REPOSITORY: QUEUE_REPOSITORY_ID,
    }

    def __init__(
        self,
        *,
        repository: str,
        private_key: str | Path,
        requester: Requester = https_json_request,
        signer: Callable[[bytes, Path], bytes] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        try:
            repository_id = self._REPOSITORIES[repository]
        except KeyError as exc:
            raise P9RuntimeError("P9 executor repository is not allowlisted") from exc
        self.repository = repository
        self.repository_id = repository_id
        self.config = _repository_scope_config(
            repository=repository,
            repository_id=repository_id,
        )
        self.private_key = require_private_key(private_key)
        self.requester = requester
        self.signer = signer
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._cached_token: InstallationToken | None = None

    def get_installation_token(self) -> InstallationToken:
        if self._cached_token is not None:
            return self._cached_token

        local_now = self.clock()
        if not isinstance(local_now, datetime) or local_now.tzinfo is None:
            raise P9RuntimeError("P9 executor clock must return timezone-aware datetime")
        local_now = local_now.astimezone(timezone.utc)

        jwt = build_app_jwt(
            app_id=EXECUTOR_APP_ID,
            server_time=local_now,
            private_key=self.private_key,
            signer=self.signer,
        )

        owner, repository_name = self.repository.split("/", 1)
        installation_response = self.requester(
            "GET",
            f"/repos/{owner}/{repository_name}/installation",
            _executor_headers(jwt),
            None,
        )
        if installation_response.status != 200:
            raise P9RuntimeError(
                f"executor repository-installation probe returned HTTP {installation_response.status}"
            )
        installation = installation_response.value
        if type(installation) is not dict:
            raise P9RuntimeError("executor repository-installation probe returned a non-object payload")
        server_now = _server_time(installation_response.headers)

        if installation.get("app_id") != EXECUTOR_APP_ID:
            raise P9RuntimeError("executor repository-installation app id mismatch")
        if installation.get("target_id") != OWNER_USER_ID or installation.get("target_type") != OWNER_TYPE:
            raise P9RuntimeError("executor repository-installation target mismatch")
        account = installation.get("account")
        if type(account) is not dict or account.get("type") != OWNER_TYPE:
            raise P9RuntimeError("executor repository-installation account type mismatch")
        validate_installation(installation, self.config)

        body = json.dumps(
            {
                "repository_ids": [self.repository_id],
                "permissions": {"issues": "read"},
            },
            separators=(",", ":"),
        ).encode("utf-8")
        token_response = self.requester(
            "POST",
            f"/app/installations/{EXECUTOR_INSTALLATION_ID}/access_tokens",
            {
                **_executor_headers(jwt),
                "Content-Type": "application/json",
            },
            body,
        )
        if token_response.status != 201:
            raise P9RuntimeError(
                f"executor installation token mint returned HTTP {token_response.status}"
            )
        token_payload = token_response.value
        if type(token_payload) is not dict:
            raise P9RuntimeError("executor installation token mint returned a non-object payload")
        token = validate_token_response(
            token_payload,
            self.config,
            now=server_now,
        )
        self._cached_token = token
        return token


def build_p9_read_clients(
    *,
    auth_surface: IsolatedAuthSurfaceContract,
    private_key: str | Path,
    sender: HTTPSender | None = None,
    requester: Requester = https_json_request,
    signer: Callable[[bytes, Path], bytes] | None = None,
) -> P9ReadClients:
    """Build two distinct read-only clients from one selected-repository App installation.

    Each provider mints at most one token for exactly one repository during the
    one-shot P9 process. No generic two-repository token exists in this
    composition, and no unauthenticated root clock probe is used.
    """

    require_isolated_auth_surface(auth_surface)
    shared_sender = sender or GitHubHttpsSender()

    authorization_provider = P9ExecutorInstallationTokenProvider(
        repository=AUTHORIZATION_REPOSITORY,
        private_key=private_key,
        requester=requester,
        signer=signer,
    )
    queue_provider = P9ExecutorInstallationTokenProvider(
        repository=QUEUE_REPOSITORY,
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
