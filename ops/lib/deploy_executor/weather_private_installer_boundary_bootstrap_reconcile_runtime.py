from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    QUEUE_REPOSITORY,
    AcceptedAuthorization,
    accept_issue,
    validate_queue_binding,
    verify_authorization_unchanged,
)
from .queue_normalizer import normalize_ready_queue
from .registry import BaselineContract, MutationBudget, OperationRegistry, OperationSpec, QueueMatch
from .weather_private_bigquery_host_bindings import FixedPublicGitHubReadClient, PublicExactSourceEvidenceProvider
from .weather_private_bigquery_host_installer_runtime import DurableInstallReplayAuthority
from .weather_private_bigquery_host_runtime import RPI5_MAIN_REPOSITORY_ID
from .weather_private_installer_boundary_bootstrap_reconcile import (
    BASELINE_RESOLVER_ID,
    DESTINATION,
    DESTINATION_MODE,
    MUTATION_BUDGET,
    OPERATION_ID,
    RECOGNIZED_PREDECESSOR_SHA256,
    RECOGNIZED_PREDECESSOR_SHA256S,
    ROLLBACK_POLICY,
    ROOT_GID,
    ROOT_UID,
    SOURCE_GIT_MODE,
    SOURCE_PATH,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
    BootstrapEvidence,
    BootstrapReconcileError,
    ReconcilePlan,
    build_reconcile_plan,
    public_plan,
)

IMPLEMENTATION_ISSUE = 743
AUTH_SURFACE = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_PRIVATE_KEY = Path("/etc/rozkalns-deploy-executor/github-app.pem")
EXECUTION_LOCATION_CLASS = "trusted-home-host"
DEPLOY_CLASS = "STRICT_LIVE_AUTH_REQUIRED"
ADAPTER_ID = "rpi5.weathernext-private-installer-boundary-bootstrap-reconcile.fixed-v1"
MAX_BOOTSTRAP_BYTES = 2 * 1024 * 1024
TEMP_DESTINATION = Path(f"{DESTINATION}.reconcile-next")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_EXCLUSIONS = (
    "no caller-selected repository path source destination content command argv or environment authority",
    "no generic root shell or generic file copier authority",
    "no #700/#721 installer-boundary refresh mutation",
    "no manager or trusted-checkout Git mutation",
    "no backend application or private-runtime mutation",
    "no Google ADC IAM project Analytics Hub or BigQuery action",
    "no SQLite schema corpus or snapshot mutation",
    "no Docker systemd package network or Cloudflare mutation",
    "no automatic retry cleanup rollback or alternate mutation path after consume",
)
DEPENDENCIES = (
    "bootstrap-source:RPi5_main#723",
    "source-fix:RPi5_main#738",
    "manager-runtime-mode:RPi5_main#745",
    "weather-gate:rozkalns_weather#224",
)


class BootstrapReconcileRuntimeError(BootstrapReconcileError):
    pass


def _fail(message: str) -> None:
    raise BootstrapReconcileRuntimeError(message)


def _server_time(response: Any) -> datetime:
    value = getattr(response, "server_time", None)
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fail("GitHub server time is unavailable")
    return value.astimezone(timezone.utc)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_blob_sha1(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _require_recognized_preimage(prepared_sha256: str, observed_sha256: str) -> None:
    if (
        prepared_sha256 not in RECOGNIZED_PREDECESSOR_SHA256S
        or observed_sha256 not in RECOGNIZED_PREDECESSOR_SHA256S
        or prepared_sha256 != observed_sha256
    ):
        _fail("bootstrap preimage drifted before replacement")


def _is_sha40(value: Any) -> bool:
    return type(value) is str and _SHA40.fullmatch(value) is not None


def _require_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int:
        _fail(f"required descriptor guard unavailable: {name}")
    return value


def _read_fixed_regular(path: Path) -> tuple[os.stat_result, bytes]:
    try:
        before = path.lstat()
    except OSError as exc:
        raise BootstrapReconcileRuntimeError("fixed bootstrap metadata is unavailable") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != ROOT_UID
        or before.st_gid != ROOT_GID
        or stat.S_IMODE(before.st_mode) != DESTINATION_MODE
        or not 0 < before.st_size <= MAX_BOOTSTRAP_BYTES
    ):
        _fail("fixed bootstrap metadata drifted")
    flags = os.O_RDONLY | _require_flag("O_CLOEXEC") | _require_flag("O_NOFOLLOW")
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise BootstrapReconcileRuntimeError("fixed bootstrap open failed") from exc
    try:
        opened = os.fstat(fd)
        if (
            (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size)
            or opened.st_nlink != 1
            or opened.st_uid != ROOT_UID
            or opened.st_gid != ROOT_GID
            or stat.S_IMODE(opened.st_mode) != DESTINATION_MODE
            or not stat.S_ISREG(opened.st_mode)
        ):
            _fail("fixed bootstrap changed before read")
        chunks: list[bytes] = []
        remaining = MAX_BOOTSTRAP_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != opened.st_size or len(raw) > MAX_BOOTSTRAP_BYTES:
            _fail("fixed bootstrap changed during read")
        after = path.lstat()
        if (
            (after.st_dev, after.st_ino, after.st_size) != (opened.st_dev, opened.st_ino, opened.st_size)
            or after.st_nlink != 1
            or after.st_uid != ROOT_UID
            or after.st_gid != ROOT_GID
            or stat.S_IMODE(after.st_mode) != DESTINATION_MODE
            or not stat.S_ISREG(after.st_mode)
        ):
            _fail("fixed bootstrap path changed during read")
        return opened, raw
    finally:
        os.close(fd)


def _reviewed_source(
    public_client: FixedPublicGitHubReadClient,
    source_sha: str,
) -> tuple[str, str, bytes]:
    if not _is_sha40(source_sha):
        _fail("reviewed source SHA is malformed")
    commit = public_client.get_json(
        f"/repos/{SOURCE_REPOSITORY}/git/commits/{source_sha}"
    ).value
    if type(commit) is not dict or commit.get("sha") != source_sha:
        _fail("reviewed source commit identity drifted")
    tree_ref = commit.get("tree")
    if type(tree_ref) is not dict or not _is_sha40(tree_ref.get("sha")):
        _fail("reviewed source tree identity is malformed")
    tree = public_client.get_json(
        f"/repos/{SOURCE_REPOSITORY}/git/trees/{tree_ref['sha']}?recursive=1"
    ).value
    if type(tree) is not dict or tree.get("truncated") is True or type(tree.get("tree")) is not list:
        _fail("reviewed source tree is unavailable")
    matches = [
        item
        for item in tree["tree"]
        if type(item) is dict and item.get("path") == SOURCE_PATH
    ]
    if len(matches) != 1:
        _fail("reviewed bootstrap source path is not unique")
    entry = matches[0]
    blob = entry.get("sha")
    if entry.get("type") != "blob" or entry.get("mode") != SOURCE_GIT_MODE or not _is_sha40(blob):
        _fail("reviewed bootstrap Git mode or blob identity drifted")

    value = public_client.get_json(
        f"/repos/{SOURCE_REPOSITORY}/contents/{SOURCE_PATH}?ref={source_sha}"
    ).value
    if (
        type(value) is not dict
        or value.get("type") != "file"
        or value.get("path") != SOURCE_PATH
        or value.get("sha") != blob
    ):
        _fail("reviewed bootstrap contents identity drifted")
    if value.get("encoding") != "base64" or type(value.get("content")) is not str:
        _fail("reviewed bootstrap payload is malformed")
    try:
        raw = base64.b64decode(value["content"].replace("\r", "").replace("\n", ""), validate=True)
    except (TypeError, ValueError) as exc:
        raise BootstrapReconcileRuntimeError("reviewed bootstrap payload is malformed") from exc
    if not 0 < len(raw) <= MAX_BOOTSTRAP_BYTES:
        _fail("reviewed bootstrap source size drifted")
    if _git_blob_sha1(raw) != blob:
        _fail("reviewed bootstrap bytes do not match exact-main Git blob")
    return blob, _sha256(raw), raw


def _fixed_registry() -> OperationRegistry:
    operation = OperationSpec(
        operation_id=OPERATION_ID,
        source_repository=SOURCE_REPOSITORY,
        queue_match=QueueMatch(
            target_alias=TARGET_ALIAS,
            execution_location_class=EXECUTION_LOCATION_CLASS,
            repository_entrypoint=SOURCE_PATH,
            deploy_class=DEPLOY_CLASS,
        ),
        target_alias=TARGET_ALIAS,
        adapter_id=ADAPTER_ID,
        authorization_class="STRICT",
        ordinary_live_all_eligible=False,
        baseline=BaselineContract(kind="resolver", resolver_id=BASELINE_RESOLVER_ID),
        mutation_budget=tuple(MutationBudget(category=c, max_operations=m) for c, m in MUTATION_BUDGET),
        rollback_policy=ROLLBACK_POLICY,
        exclusions=REQUIRED_EXCLUSIONS,
        dependencies=DEPENDENCIES,
        preflight=(
            "owner LIVE-AUTH and READY Queue are independently revalidated",
            "exact current RPi5_main required CI is revalidated",
            "reviewed bootstrap executable Git blob and bytes are derived from exact current main",
            "installed bootstrap is either exact-current or the one recognized predecessor",
            "fixed temp destination is absent before consume",
        ),
        postconditions=(
            "installed bootstrap is root-owned one-link regular 0755",
            "installed bytes equal the executable Git blob derived from exact current main",
            "#700/#721 refresh remains unexecuted",
        ),
        required_github_evidence=(
            "owner-authored non-App LIVE-AUTH",
            "READY Queue exact operation target source and one-operation budget binding",
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
            _fail(f"bootstrap-reconcile LIVE-AUTH {field} drifted")
    exclusions = payload.get("exclusions")
    if type(exclusions) is not list or not set(REQUIRED_EXCLUSIONS).issubset(set(exclusions)):
        _fail("bootstrap-reconcile LIVE-AUTH exclusions drifted")
    return payload


def _require_queue(normalized: Any) -> Mapping[str, Any]:
    if getattr(normalized, "execution_enabled", None) is not False:
        _fail("bootstrap-reconcile registry unexpectedly enables execution")
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
            _fail(f"bootstrap-reconcile Queue {field} drifted")
    observed = tuple((item.category, item.max_operations) for item in getattr(operation, "mutation_budget", ()))
    if observed != MUTATION_BUDGET:
        _fail("bootstrap-reconcile Queue mutation budget drifted")
    return normalized.as_protocol_queue()


@dataclass(frozen=True)
class PreparedReconcile:
    source_sha: str
    source_bytes: bytes
    installed_sha256: str
    plan: ReconcilePlan


@dataclass(frozen=True)
class CanonicalEvidence:
    authorization_issue_number: int
    authorization_issue_id: int
    request_id: str
    request_body_sha256: str
    queue_issue_number: int
    source_sha: str
    installed_sha256: str
    plan: Mapping[str, object]


class Revalidator:
    def __init__(
        self,
        *,
        authorization_client: Any,
        queue_client: Any,
        public_client: FixedPublicGitHubReadClient,
        replay: DurableInstallReplayAuthority,
    ):
        self.authorization_client = authorization_client
        self.queue_client = queue_client
        self.public_client = public_client
        self.sources = PublicExactSourceEvidenceProvider(client=public_client)
        self.replay = replay
        self.registry = _fixed_registry()
        self.accepted: AcceptedAuthorization | None = None
        self.prepared: PreparedReconcile | None = None

    def revalidate(self, issue_number: int) -> CanonicalEvidence:
        if type(issue_number) is not int or not 1 <= issue_number <= 2_147_483_647:
            _fail("authorization issue number is invalid")
        response = self.authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        accepted = accept_issue(
            response.value,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=_server_time(response),
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        payload = _require_live_authority(accepted)
        queue_issue = payload.get("queue_issue")
        if type(queue_issue) is not int or queue_issue < 1:
            _fail("bootstrap-reconcile Queue issue number is invalid")
        queue_response = self.queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue}"
        )
        normalized = normalize_ready_queue(
            queue_response.value,
            repository_full_name=QUEUE_REPOSITORY,
            registry=self.registry,
        )
        validate_queue_binding(accepted, _require_queue(normalized))

        source = self.sources.load_exact_source(SOURCE_REPOSITORY, RPI5_MAIN_REPOSITORY_ID)
        if (
            payload.get("source_sha") != source.source_sha
            or source.current_main_sha != source.source_sha
            or not source.required_ci_success
        ):
            _fail("bootstrap-reconcile source is not exact current RPi5_main")
        source_git_blob, source_sha256, source_bytes = _reviewed_source(
            self.public_client,
            source.source_sha,
        )
        installed_meta, installed_bytes = _read_fixed_regular(Path(DESTINATION))
        installed_sha256 = _sha256(installed_bytes)
        evidence = BootstrapEvidence(
            exact_source_sha=source.source_sha,
            current_main_sha=source.current_main_sha,
            exact_main_ci_success=True,
            source_git_mode=SOURCE_GIT_MODE,
            source_git_blob=source_git_blob,
            source_sha256=source_sha256,
            installed_is_regular=True,
            installed_uid=installed_meta.st_uid,
            installed_gid=installed_meta.st_gid,
            installed_mode=stat.S_IMODE(installed_meta.st_mode),
            installed_nlink=installed_meta.st_nlink,
            installed_sha256=installed_sha256,
        )
        plan = build_reconcile_plan(evidence)
        if plan.prior_state == "RECOGNIZED_PREDECESSOR" and TEMP_DESTINATION.exists():
            _fail("fixed bootstrap reconcile temp evidence already exists")
        if self.replay.is_available(accepted) is not True:
            _fail("bootstrap-reconcile LIVE-AUTH is unavailable for one-shot consume")
        final = self.authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        verify_authorization_unchanged(
            accepted,
            final.value,
            server_time=_server_time(final),
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        if self.replay.is_available(accepted) is not True:
            _fail("bootstrap-reconcile LIVE-AUTH replay state drifted")
        self.accepted = accepted
        self.prepared = PreparedReconcile(
            source.source_sha,
            source_bytes,
            installed_sha256,
            plan,
        )
        return CanonicalEvidence(
            issue_number,
            accepted.issue_id,
            accepted.request_id,
            accepted.raw_body_sha256,
            queue_issue,
            source.source_sha,
            installed_sha256,
            public_plan(plan),
        )


def _atomic_replace(prepared: PreparedReconcile) -> Mapping[str, object]:
    if prepared.plan.prior_state != "RECOGNIZED_PREDECESSOR":
        _fail("bootstrap replacement escaped recognized predecessor plan")
    if (
        _sha256(prepared.source_bytes) != prepared.plan.source_sha256
        or _git_blob_sha1(prepared.source_bytes) != prepared.plan.source_git_blob
        or prepared.plan.source_git_mode != SOURCE_GIT_MODE
    ):
        _fail("bootstrap replacement source identity drifted")
    destination = Path(DESTINATION)
    _, before = _read_fixed_regular(destination)
    _require_recognized_preimage(prepared.installed_sha256, _sha256(before))
    if TEMP_DESTINATION.exists():
        _fail("fixed bootstrap reconcile temp evidence already exists")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | _require_flag("O_CLOEXEC")
        | _require_flag("O_NOFOLLOW")
    )
    fd = os.open(TEMP_DESTINATION, flags, 0o600)
    try:
        offset = 0
        while offset < len(prepared.source_bytes):
            written = os.write(fd, prepared.source_bytes[offset:])
            if written <= 0:
                _fail("bootstrap replacement write failed closed")
            offset += written
        os.fchmod(fd, DESTINATION_MODE)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(TEMP_DESTINATION, destination)
    directory_fd = os.open(
        destination.parent,
        os.O_RDONLY | _require_flag("O_DIRECTORY") | _require_flag("O_CLOEXEC"),
    )
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    _, final = _read_fixed_regular(destination)
    if (
        _sha256(final) != prepared.plan.source_sha256
        or _git_blob_sha1(final) != prepared.plan.source_git_blob
    ):
        _fail("bootstrap reconcile postcondition failed")
    return {
        "status": "BOOTSTRAP_EXACT",
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_sha": prepared.source_sha,
        "source_git_blob": prepared.plan.source_git_blob,
        "source_sha256": prepared.plan.source_sha256,
        "authorization_consumed": True,
        "production_mutation_started": True,
        "mutation_categories": [MUTATION_BUDGET[0][0]],
        "rollback_policy": ROLLBACK_POLICY,
    }


def execute_prevalidated(
    evidence: CanonicalEvidence,
    *,
    prepared: PreparedReconcile,
    accepted: AcceptedAuthorization,
    replay: DurableInstallReplayAuthority,
) -> Mapping[str, object]:
    if (
        evidence.request_id != accepted.request_id
        or evidence.source_sha != prepared.source_sha
        or public_plan(prepared.plan) != evidence.plan
    ):
        _fail("bootstrap-reconcile canonical identity drifted")
    if prepared.plan.prior_state == "EXACT":
        return {
            "status": "ALREADY_EXACT",
            "operation_id": OPERATION_ID,
            "target_alias": TARGET_ALIAS,
            "source_sha": evidence.source_sha,
            "source_git_blob": prepared.plan.source_git_blob,
            "source_sha256": prepared.plan.source_sha256,
            "authorization_consumed": False,
            "production_mutation_started": False,
            "mutation_categories": [],
            "rollback_policy": ROLLBACK_POLICY,
        }
    replay.consume(accepted.request_id)
    receipt = dict(_atomic_replace(prepared))
    replay.mark_succeeded(accepted.request_id)
    return receipt


def run_privileged_bootstrap_reconcile(
    authorization_issue_number: int,
) -> Mapping[str, object]:
    if os.geteuid() != ROOT_UID:
        _fail("bootstrap reconcile must run as root")
    replay = DurableInstallReplayAuthority()
    try:
        auth_surface = load_contract(AUTH_SURFACE)
        require_isolated_auth_surface(auth_surface)
        clients = build_p9_read_clients(
            auth_surface=auth_surface,
            private_key=EXECUTOR_PRIVATE_KEY,
        )
        public_client = FixedPublicGitHubReadClient()
        revalidator = Revalidator(
            authorization_client=clients.authorization,
            queue_client=clients.queue,
            public_client=public_client,
            replay=replay,
        )
        first = revalidator.revalidate(authorization_issue_number)
        final = revalidator.revalidate(authorization_issue_number)
        if first != final:
            _fail("canonical bootstrap-reconcile evidence drifted")
        preconsume = revalidator.revalidate(authorization_issue_number)
        if final != preconsume:
            _fail("canonical bootstrap-reconcile evidence drifted before consume")
        accepted = revalidator.accepted
        prepared = revalidator.prepared
        if accepted is None or prepared is None:
            _fail("bootstrap-reconcile canonical revalidation did not prepare execution")
        return execute_prevalidated(
            preconsume,
            prepared=prepared,
            accepted=accepted,
            replay=replay,
        )
    except BootstrapReconcileRuntimeError:
        raise
    except BootstrapReconcileError as exc:
        raise BootstrapReconcileRuntimeError(str(exc)) from exc
    except Exception:
        raise BootstrapReconcileRuntimeError(
            "WeatherNext bootstrap reconcile failed closed"
        ) from None


def source_readiness() -> Mapping[str, object]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_repository": SOURCE_REPOSITORY,
        "source_path": SOURCE_PATH,
        "source_git_mode": SOURCE_GIT_MODE,
        "target_identity": "derived-from-exact-current-main",
        "recognized_predecessor_sha256": RECOGNIZED_PREDECESSOR_SHA256,
        "caller_authority": ("authorization_issue_number",),
        "mutation_budget": MUTATION_BUDGET,
        "rollback_policy": ROLLBACK_POLICY,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "source_merge_authorizes_live": False,
        "runtime_live_authority": False,
        "production_mutation_started": False,
    }