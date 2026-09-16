from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

from .hermes_deals_origin_runtime_adapters import (
    ConcreteDurableHermesOriginReplayAuthority,
)
from .hermes_deals_origin_source_auth import (
    SOURCE_CREDENTIAL_PATH,
    build_hermes_deals_source_token_provider,
)
from .hermes_deals_runner_smoke_install import (
    HELPER_SHA256,
    INSTALL_TARGET_ALIAS,
    LIVE_GATE_ID,
    OPERATION_ID,
    OWNER_NUMERIC_ID,
    REGISTRATION_SHA256,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    SOURCE_SHA,
    PosixFixedInstallBackend,
)
from .hermes_deals_runner_smoke_install_consumer import (
    CanonicalRunnerSmokeInstallEvidence,
)
from .hermes_deals_runner_smoke_install_execution_bridge import (
    execute_install_for_authorization,
)
from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import P9ExecutorInstallationTokenProvider, build_p9_read_clients
from .p9_source_auth import (
    HERMES_DEALS_SOURCE_REPOSITORY,
    HERMES_DEALS_SOURCE_REPOSITORY_ID,
    P9SourceInstallationTokenProvider,
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
from .registry import BaselineContract, MutationBudget, OperationRegistry, OperationSpec, QueueMatch
from .source_evidence import verify_source_evidence
from .transport import API_VERSION, GitHubHttpsSender, GitHubRestClient, HTTPStatusError, JSONResponse

IMPLEMENTATION_ISSUE = 546
RPI5_MAIN_REPOSITORY = "rozkalnsandris/RPi5_main"
RPI5_MAIN_REPOSITORY_ID = 1323383044
INSTALL_BASELINE_RESOLVER_ID = "hermes-deals.runner-smoke-install-state.v1"
INSTALL_REPOSITORY_ENTRYPOINT = ".github/workflows/rpi5-audit-command.yml"
EXECUTION_LOCATION_CLASS = "trusted-home-host"
DEPLOY_CLASS = "STRICT_LIVE_AUTH_REQUIRED"
ISOLATED_AUTH_PATH = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_CREDENTIAL_PATH = Path("/etc/rozkalns-deploy-executor/github-app.pem")
MAX_GITHUB_TIMESTAMP_SPREAD_SECONDS = 30
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")

INSTALL_MUTATION_BUDGET = (
    MutationBudget(category="host.system-group-create", max_operations=1),
    MutationBudget(category="host.system-user-create", max_operations=1),
    MutationBudget(category="filesystem.runner-smoke-helper-install", max_operations=1),
    MutationBudget(category="filesystem.runner-smoke-registration-install", max_operations=1),
)
INSTALL_EXCLUSIONS = (
    "caller-selected command/path/argv/environment authority",
    "generic root shell or generic sudo authority",
    "Docker authority or supplementary-group authority",
    "systemd/service/timer/socket/network/firewall/DNS/Cloudflare mutation",
    "credential/secret/token/private-key mutation",
    "database/Review/publication/parser/collector/scheduler mutation",
    "production deployment/cutover",
    "runner registration/deregistration or repository settings mutation",
    "helper invocation during install",
    "automatic retry/cleanup/rollback/alternate mutation after consume",
)
INSTALL_DEPENDENCIES = (
    f"source-repository-id:{SOURCE_REPOSITORY_ID}",
    f"source-sha:{SOURCE_SHA}",
    f"helper-sha256:{HELPER_SHA256}",
    f"registration-sha256:{REGISTRATION_SHA256}",
    "source-contract:RPi5_main#476",
    "consumer-contract:RPi5_main#481",
    "execution-bridge-contract:RPi5_main#534",
    "runtime-composition-contract:RPi5_main#546",
    f"live-gate:{LIVE_GATE_ID}",
    "runtime-activation:disabled-after-source-merge",
)


class RunnerSmokeInstallRuntimeError(RuntimeError):
    pass


class RunnerSmokeReplayAvailability(Protocol):
    def is_available(self, accepted: AcceptedAuthorization) -> bool: ...


class _GitHubTimeWindow:
    def __init__(self) -> None:
        self.first: datetime | None = None
        self.last: datetime | None = None

    def observe(self, value: Any) -> None:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise RunnerSmokeInstallRuntimeError("GitHub response time is unavailable")
        observed = value.astimezone(timezone.utc)
        if observed.microsecond != 0:
            raise RunnerSmokeInstallRuntimeError("GitHub response time is not canonical")
        candidate_first = observed if self.first is None else min(self.first, observed)
        candidate_last = observed if self.last is None else max(self.last, observed)
        if (candidate_last - candidate_first).total_seconds() > MAX_GITHUB_TIMESTAMP_SPREAD_SECONDS:
            raise RunnerSmokeInstallRuntimeError("GitHub response time spread is too large")
        self.first = candidate_first
        self.last = candidate_last

    def canonical_last(self) -> str:
        if self.last is None:
            raise RunnerSmokeInstallRuntimeError("canonical revalidation observed no GitHub time")
        return self.last.strftime("%Y-%m-%dT%H:%M:%SZ")


class _TimedClient:
    def __init__(self, client: Any, window: _GitHubTimeWindow):
        self._client = client
        self._window = window

    def get_json(self, path_or_url: str) -> Any:
        response = self._client.get_json(path_or_url)
        self._window.observe(getattr(response, "server_time", None))
        return response


class FixedPublicRpi5MainReadClient:
    """Credential-free GET reader restricted to public RPi5_main source evidence."""

    def __init__(self, *, sender: Any | None = None):
        self._sender = sender or GitHubHttpsSender()

    @staticmethod
    def _require_path(path: str) -> None:
        if type(path) is not str or not path.startswith("/repos/"):
            raise RunnerSmokeInstallRuntimeError("RPi5_main source read path is invalid")
        remainder = path[len("/repos/") :]
        parts = remainder.split("/", 2)
        if len(parts) < 2 or f"{parts[0]}/{parts[1].split('?', 1)[0]}" != RPI5_MAIN_REPOSITORY:
            raise RunnerSmokeInstallRuntimeError("RPi5_main source read escaped fixed repository")

    def get_json(self, path_or_url: str) -> JSONResponse:
        self._require_path(path_or_url)
        response = self._sender.send(
            method="GET",
            url="https://api.github.com" + path_or_url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "rozkalns-runner-smoke-install-source-read/1",
            },
        )
        if response.status != 200:
            raise HTTPStatusError(response.status)
        date_header = next(
            (value for key, value in response.headers.items() if key.lower() == "date"),
            None,
        )
        if type(date_header) is not str:
            raise RunnerSmokeInstallRuntimeError("RPi5_main source response omitted Date header")
        try:
            server_time = parsedate_to_datetime(date_header)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RunnerSmokeInstallRuntimeError("RPi5_main source Date header is invalid") from exc
        if server_time.tzinfo is None:
            raise RunnerSmokeInstallRuntimeError("RPi5_main source Date header has no timezone")
        try:
            value = json.loads(response.body.decode("utf-8", "strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RunnerSmokeInstallRuntimeError("RPi5_main source response is malformed JSON") from exc
        return JSONResponse(
            value=value,
            server_time=server_time.astimezone(timezone.utc),
            etag=None,
            not_modified=False,
            url="https://api.github.com" + path_or_url,
            next_url=None,
        )


def _fixed_install_registry() -> OperationRegistry:
    operation = OperationSpec(
        operation_id=OPERATION_ID,
        source_repository=SOURCE_REPOSITORY,
        queue_match=QueueMatch(
            target_alias=INSTALL_TARGET_ALIAS,
            execution_location_class=EXECUTION_LOCATION_CLASS,
            repository_entrypoint=INSTALL_REPOSITORY_ENTRYPOINT,
            deploy_class=DEPLOY_CLASS,
        ),
        target_alias=INSTALL_TARGET_ALIAS,
        adapter_id="hermes-deals.runner-smoke-install.v1",
        authorization_class="STRICT",
        ordinary_live_all_eligible=False,
        baseline=BaselineContract(kind="resolver", resolver_id=INSTALL_BASELINE_RESOLVER_ID),
        mutation_budget=INSTALL_MUTATION_BUDGET,
        rollback_policy="NONE",
        exclusions=INSTALL_EXCLUSIONS,
        dependencies=INSTALL_DEPENDENCIES,
        preflight=(
            "owner LIVE-AUTH and READY Queue are independently revalidated",
            "reviewed Hermes runner-smoke SHA is reachable and exact-SHA CI successful",
            "current merged RPi5_main SHA has successful exact-main CI",
            "fixed helper registration and execution-identity state is observed immediately before apply",
            "runtime source remains capability-specific and global execution remains disabled",
        ),
        postconditions=(
            "dedicated execution identity helper and registration are exact",
            "helper is not invoked by install",
            "automatic retry cleanup rollback and alternate mutation are absent",
        ),
        required_github_evidence=(
            "owner-authored non-App LIVE-AUTH",
            "READY Queue exact binding",
            "Hermes source stable identity reachability and exact-SHA CI",
            "current RPi5_main stable identity and exact-main CI",
        ),
    )
    return OperationRegistry(schema_version=1, execution_enabled=False, operations=(operation,))


def _require_read_clients(
    authorization_client: GitHubRestClient,
    queue_client: GitHubRestClient,
    hermes_source_client: GitHubRestClient,
    rpi5_main_client: FixedPublicRpi5MainReadClient,
) -> None:
    if type(authorization_client) is not GitHubRestClient or type(queue_client) is not GitHubRestClient:
        raise RunnerSmokeInstallRuntimeError("control-plane readers are not reviewed GitHub clients")
    for client, repository, repository_id in (
        (authorization_client, AUTHORIZATION_REPOSITORY, AUTHORIZATION_REPOSITORY_ID),
        (queue_client, QUEUE_REPOSITORY, QUEUE_REPOSITORY_ID),
    ):
        provider = client.token_provider
        if type(provider) is not P9ExecutorInstallationTokenProvider:
            raise RunnerSmokeInstallRuntimeError("control-plane reader provider drifted")
        if provider.repository != repository or provider.repository_id != repository_id:
            raise RunnerSmokeInstallRuntimeError("control-plane reader repository binding drifted")
    if type(hermes_source_client) is not GitHubRestClient:
        raise RunnerSmokeInstallRuntimeError("Hermes source reader is not reviewed GitHub client")
    source_provider = hermes_source_client.token_provider
    if type(source_provider) is not P9SourceInstallationTokenProvider:
        raise RunnerSmokeInstallRuntimeError("Hermes source reader provider drifted")
    if (
        source_provider.repository != HERMES_DEALS_SOURCE_REPOSITORY
        or source_provider.repository_id != HERMES_DEALS_SOURCE_REPOSITORY_ID
        or HERMES_DEALS_SOURCE_REPOSITORY != SOURCE_REPOSITORY
        or HERMES_DEALS_SOURCE_REPOSITORY_ID != SOURCE_REPOSITORY_ID
    ):
        raise RunnerSmokeInstallRuntimeError("Hermes source reader repository binding drifted")
    if type(rpi5_main_client) is not FixedPublicRpi5MainReadClient:
        raise RunnerSmokeInstallRuntimeError("RPi5_main reader is not fixed public reader")


def _require_repository(response: Any, *, repository: str, repository_id: int, window: _GitHubTimeWindow) -> None:
    window.observe(getattr(response, "server_time", None))
    value = getattr(response, "value", None)
    if type(value) is not dict or value.get("id") != repository_id or value.get("full_name") != repository:
        raise RunnerSmokeInstallRuntimeError("GitHub repository identity drifted")


def _require_issue(response: Any, *, issue_number: int, repository: str, window: _GitHubTimeWindow) -> Mapping[str, Any]:
    window.observe(getattr(response, "server_time", None))
    value = getattr(response, "value", None)
    if type(value) is not dict or value.get("number") != issue_number:
        raise RunnerSmokeInstallRuntimeError("GitHub issue identity drifted")
    expected_url = f"https://api.github.com/repos/{repository}"
    if value.get("repository_url") not in {None, expected_url}:
        raise RunnerSmokeInstallRuntimeError("GitHub issue repository identity drifted")
    return value


def _require_install_queue(normalized: Any) -> Mapping[str, Any]:
    if getattr(normalized, "execution_enabled", None) is not False:
        raise RunnerSmokeInstallRuntimeError("install registry unexpectedly enables execution")
    operation = getattr(normalized, "operation", None)
    expected = {
        "operation_id": OPERATION_ID,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": INSTALL_TARGET_ALIAS,
        "adapter_id": "hermes-deals.runner-smoke-install.v1",
        "authorization_class": "STRICT",
        "ordinary_live_all_eligible": False,
        "rollback_policy": "NONE",
    }
    for field, value in expected.items():
        if getattr(operation, field, None) != value:
            raise RunnerSmokeInstallRuntimeError(f"install Queue operation {field} drifted")
    baseline = getattr(operation, "baseline", None)
    if (
        getattr(baseline, "kind", None) != "resolver"
        or getattr(baseline, "resolver_id", None) != INSTALL_BASELINE_RESOLVER_ID
    ):
        raise RunnerSmokeInstallRuntimeError("install Queue baseline contract drifted")
    if tuple(getattr(operation, "mutation_budget", ())) != INSTALL_MUTATION_BUDGET:
        raise RunnerSmokeInstallRuntimeError("install Queue mutation budget drifted")
    protocol_queue = normalized.as_protocol_queue()
    if protocol_queue.get("expected_baseline") != {
        "kind": "resolver",
        "value": INSTALL_BASELINE_RESOLVER_ID,
    }:
        raise RunnerSmokeInstallRuntimeError("normalized install Queue baseline drifted")
    return protocol_queue


def _current_rpi5_main_sha(client: _TimedClient) -> str:
    response = client.get_json(f"/repos/{RPI5_MAIN_REPOSITORY}/branches/main")
    value = getattr(response, "value", None)
    if type(value) is not dict or type(value.get("commit")) is not dict:
        raise RunnerSmokeInstallRuntimeError("RPi5_main branch response is malformed")
    sha = value["commit"].get("sha")
    if type(sha) is not str or _SHA40_RE.fullmatch(sha) is None:
        raise RunnerSmokeInstallRuntimeError("RPi5_main current SHA is invalid")
    return sha


class ConcreteRunnerSmokeInstallRevalidator:
    """Reconstruct the exact runner-smoke install authority from reviewed GET surfaces."""

    def __init__(
        self,
        *,
        authorization_client: GitHubRestClient,
        queue_client: GitHubRestClient,
        hermes_source_client: GitHubRestClient,
        rpi5_main_client: FixedPublicRpi5MainReadClient,
        auth_surface: Any,
        registry: OperationRegistry,
        replay_availability: RunnerSmokeReplayAvailability,
    ):
        _require_read_clients(
            authorization_client,
            queue_client,
            hermes_source_client,
            rpi5_main_client,
        )
        require_isolated_auth_surface(auth_surface)
        if registry.execution_enabled is not False or len(registry.operations) != 1:
            raise RunnerSmokeInstallRuntimeError("runner-smoke install registry is not isolated and disabled")
        if not callable(getattr(replay_availability, "is_available", None)):
            raise RunnerSmokeInstallRuntimeError("runner-smoke replay availability is missing")
        self._authorization_client = authorization_client
        self._queue_client = queue_client
        self._hermes_source_client = hermes_source_client
        self._rpi5_main_client = rpi5_main_client
        self._auth_surface = auth_surface
        self._registry = registry
        self._replay_availability = replay_availability

    def revalidate(self, authorization_issue_number: int) -> CanonicalRunnerSmokeInstallEvidence:
        if type(authorization_issue_number) is not int or not 1 <= authorization_issue_number <= 2_147_483_647:
            raise RunnerSmokeInstallRuntimeError("authorization issue number is invalid")
        try:
            return self._revalidate(authorization_issue_number)
        except RunnerSmokeInstallRuntimeError:
            raise
        except Exception:
            raise RunnerSmokeInstallRuntimeError("runner-smoke canonical revalidation failed closed") from None

    def _revalidate(self, issue_number: int) -> CanonicalRunnerSmokeInstallEvidence:
        _require_read_clients(
            self._authorization_client,
            self._queue_client,
            self._hermes_source_client,
            self._rpi5_main_client,
        )
        require_isolated_auth_surface(self._auth_surface)
        window = _GitHubTimeWindow()

        auth_repository = self._authorization_client.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}")
        _require_repository(
            auth_repository,
            repository=AUTHORIZATION_REPOSITORY,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            window=window,
        )
        issue_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        issue = _require_issue(
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
            or payload.get("source_sha") != SOURCE_SHA
            or payload.get("target_alias") != INSTALL_TARGET_ALIAS
            or payload.get("operation_id") != OPERATION_ID
            or payload.get("rollback_policy") != "NONE"
        ):
            raise RunnerSmokeInstallRuntimeError("LIVE-AUTH is not the fixed runner-smoke install capability")

        queue_repository = self._queue_client.get_json(f"/repos/{QUEUE_REPOSITORY}")
        _require_repository(
            queue_repository,
            repository=QUEUE_REPOSITORY,
            repository_id=QUEUE_REPOSITORY_ID,
            window=window,
        )
        queue_issue_number = payload.get("queue_issue")
        if type(queue_issue_number) is not int or queue_issue_number < 1:
            raise RunnerSmokeInstallRuntimeError("runner-smoke Queue issue number is invalid")
        queue_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue_number}"
        )
        queue_issue = _require_issue(
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
        protocol_queue = _require_install_queue(normalized)
        validate_queue_binding(accepted, protocol_queue)

        hermes = verify_source_evidence(
            _TimedClient(self._hermes_source_client, window),
            source_repository=SOURCE_REPOSITORY,
            source_sha=SOURCE_SHA,
        )
        if hermes.repository_id != SOURCE_REPOSITORY_ID:
            raise RunnerSmokeInstallRuntimeError("Hermes source repository identity drifted")

        timed_rpi5 = _TimedClient(self._rpi5_main_client, window)
        rpi5_main_sha = _current_rpi5_main_sha(timed_rpi5)
        rpi5 = verify_source_evidence(
            timed_rpi5,
            source_repository=RPI5_MAIN_REPOSITORY,
            source_sha=rpi5_main_sha,
        )
        if rpi5.repository_id != RPI5_MAIN_REPOSITORY_ID or rpi5.current_main_sha != rpi5_main_sha:
            raise RunnerSmokeInstallRuntimeError("RPi5_main source evidence drifted")

        replay_available = self._replay_availability.is_available(accepted)
        if type(replay_available) is not bool or replay_available is not True:
            raise RunnerSmokeInstallRuntimeError("runner-smoke LIVE-AUTH is unavailable for one-shot consume")

        require_isolated_auth_surface(self._auth_surface)
        final_repository = self._authorization_client.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}")
        _require_repository(
            final_repository,
            repository=AUTHORIZATION_REPOSITORY,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            window=window,
        )
        final_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        final_issue = _require_issue(
            final_response,
            issue_number=issue_number,
            repository=AUTHORIZATION_REPOSITORY,
            window=window,
        )
        verify_authorization_unchanged(
            accepted,
            final_issue,
            server_time=final_response.server_time,
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )

        return CanonicalRunnerSmokeInstallEvidence(
            authorization_issue_number=issue_number,
            authorization_created_at=accepted.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            github_server_time=window.canonical_last(),
            owner_numeric_id=OWNER_NUMERIC_ID,
            owner_type="User",
            app_authored=False,
            operation_id=OPERATION_ID,
            live_gate_id=LIVE_GATE_ID,
            target_alias=INSTALL_TARGET_ALIAS,
            source_repository=SOURCE_REPOSITORY,
            source_repository_id=SOURCE_REPOSITORY_ID,
            source_sha=SOURCE_SHA,
            rpi5_main_sha=rpi5_main_sha,
            rpi5_main_merged_reachable=True,
            rpi5_main_ci_success=True,
            hermes_source_merged_reachable=True,
            hermes_source_ci_success=True,
            helper_sha256=HELPER_SHA256,
            registration_sha256=REGISTRATION_SHA256,
            request_body_sha256=accepted.raw_body_sha256,
            identical_body_refetch=True,
            ttl_valid=True,
            replay_available=True,
            live_authorized=True,
            rollback_policy="NONE",
        )


class ConcreteRunnerSmokeInstallReplayAuthority:
    """Capability adapter over the reviewed durable one-shot replay primitive."""

    def __init__(self) -> None:
        self._delegate = ConcreteDurableHermesOriginReplayAuthority()
        self._candidate: AcceptedAuthorization | None = None

    def is_available(self, accepted: AcceptedAuthorization) -> bool:
        available = self._delegate.is_available(accepted)
        if available:
            self._candidate = accepted
        return available

    def consume(self, *, authorization_issue_number: int, body_sha256: str) -> None:
        candidate = self._candidate
        if candidate is None:
            raise RunnerSmokeInstallRuntimeError("runner-smoke replay consume has no canonical candidate")
        if candidate.issue_number != authorization_issue_number or candidate.raw_body_sha256 != body_sha256:
            raise RunnerSmokeInstallRuntimeError("runner-smoke replay consume authority drifted")
        try:
            receipt = self._delegate.consume(candidate.request_id)
        except Exception:
            raise RunnerSmokeInstallRuntimeError("runner-smoke replay consume failed closed") from None
        if (
            getattr(receipt, "request_id", None) != candidate.request_id
            or getattr(receipt, "state", None) != "CONSUMED"
            or getattr(receipt, "availability_checks", None) != 2
            or getattr(receipt, "durable_replay_consumed", None) is not True
            or getattr(receipt, "replay_mutation_started", None) is not True
            or getattr(receipt, "production_mutation_started", None) is not False
        ):
            raise RunnerSmokeInstallRuntimeError("runner-smoke replay consume receipt drifted")


class RunnerSmokeInstallRuntimeComposition:
    """Fixed root composition; the caller controls only one LIVE-AUTH issue number."""

    def __init__(
        self,
        *,
        canonical_revalidator: ConcreteRunnerSmokeInstallRevalidator,
        replay_authority: ConcreteRunnerSmokeInstallReplayAuthority,
        backend: PosixFixedInstallBackend,
    ):
        if type(canonical_revalidator) is not ConcreteRunnerSmokeInstallRevalidator:
            raise TypeError("runtime composition requires concrete runner-smoke revalidator")
        if type(replay_authority) is not ConcreteRunnerSmokeInstallReplayAuthority:
            raise TypeError("runtime composition requires concrete runner-smoke replay authority")
        if type(backend) is not PosixFixedInstallBackend:
            raise TypeError("runtime composition requires fixed runner-smoke backend")
        if getattr(canonical_revalidator, "_replay_availability", None) is not replay_authority:
            raise TypeError("runtime composition requires one shared replay authority instance")
        self._canonical_revalidator = canonical_revalidator
        self._replay_authority = replay_authority
        self._backend = backend

    def execute(self, authorization_issue_number: int) -> Any:
        try:
            return execute_install_for_authorization(
                authorization_issue_number,
                canonical_revalidator=self._canonical_revalidator,
                authorization_consumer=self._replay_authority,
                backend=self._backend,
            )
        except Exception:
            raise RunnerSmokeInstallRuntimeError("runner-smoke install execution failed closed") from None


def build_runner_smoke_install_runtime() -> RunnerSmokeInstallRuntimeComposition:
    """Build one fixed runtime composition with no caller-selected dependencies."""

    if os.geteuid() != 0:
        raise RunnerSmokeInstallRuntimeError("runner-smoke install runtime requires root identity")
    try:
        auth_surface = load_contract(ISOLATED_AUTH_PATH)
        require_isolated_auth_surface(auth_surface)
        sender = GitHubHttpsSender()
        read_clients = build_p9_read_clients(
            auth_surface=auth_surface,
            private_key=EXECUTOR_CREDENTIAL_PATH,
            sender=sender,
        )
        source_provider = build_hermes_deals_source_token_provider(
            private_key=SOURCE_CREDENTIAL_PATH,
        )
        hermes_source_client = GitHubRestClient(token_provider=source_provider, sender=sender)
        rpi5_main_client = FixedPublicRpi5MainReadClient(sender=sender)
        replay = ConcreteRunnerSmokeInstallReplayAuthority()
        revalidator = ConcreteRunnerSmokeInstallRevalidator(
            authorization_client=read_clients.authorization,
            queue_client=read_clients.queue,
            hermes_source_client=hermes_source_client,
            rpi5_main_client=rpi5_main_client,
            auth_surface=auth_surface,
            registry=_fixed_install_registry(),
            replay_availability=replay,
        )
        return RunnerSmokeInstallRuntimeComposition(
            canonical_revalidator=revalidator,
            replay_authority=replay,
            backend=PosixFixedInstallBackend(),
        )
    except RunnerSmokeInstallRuntimeError:
        raise
    except Exception:
        raise RunnerSmokeInstallRuntimeError("runner-smoke runtime composition failed closed") from None


def source_readiness() -> Mapping[str, Any]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "concrete_canonical_revalidator_implemented": True,
        "fixed_runtime_factory_implemented": True,
        "runtime_factory_arguments": (),
        "source_tree_one_shot_operator_supported": True,
        "caller_authority": ("authorization_issue_number",),
        "authorization_repository": AUTHORIZATION_REPOSITORY,
        "queue_repository": QUEUE_REPOSITORY,
        "hermes_source_repository": SOURCE_REPOSITORY,
        "rpi5_main_repository": RPI5_MAIN_REPOSITORY,
        "install_target_alias": INSTALL_TARGET_ALIAS,
        "live_gate_id": LIVE_GATE_ID,
        "global_executor_execution_enabled": False,
        "runtime_activation_enabled": False,
        "operator_installed": False,
        "sudoers_installed": False,
        "systemd_or_socket_installed": False,
        "queue_item_created": False,
        "live_auth_created": False,
        "production_mutation_started": False,
    }
