from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
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
from .weather_private_application_staging import _rename_noreplace
from .weather_private_bigquery_host_bindings import (
    FixedPublicGitHubReadClient,
    PublicExactSourceEvidenceProvider,
)
from .weather_private_bigquery_host_installer_runtime import DurableInstallReplayAuthority
from .weather_private_bigquery_host_runtime import RPI5_MAIN_REPOSITORY, RPI5_MAIN_REPOSITORY_ID
from .weather_private_bigquery_runtime_materialization import (
    ARTIFACT_CACHE_ROOT,
    MAX_ARTIFACT_BYTES,
    OPERATION_ID,
    PRIVATE_CONTRACT_ID,
    RUNTIME_BASE,
    RUNTIME_MARKER_NAME,
    TARGET_PIP_PLATFORM,
    TARGET_PYTHON_ABI,
    ObservedRuntimeIdentity,
    RuntimeArtifactReceipt,
    WeatherNextRuntimeMaterializationError,
    _hash_file,
    _load_archive_payload,
    classify_runtime_identity,
    load_runtime_lock,
    materialize_reviewed_runtime,
    validate_artifact_receipt,
)

IMPLEMENTATION_ISSUE = 704
TARGET_ALIAS = "rpi5-weathernext-private-runtime-materialization"
SOURCE_REPOSITORY = RPI5_MAIN_REPOSITORY
AUTH_SURFACE = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_PRIVATE_KEY = Path("/etc/rozkalns-deploy-executor/github-app.pem")
TRUSTED_BOUNDARY = Path("/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted")
REVIEWED_RPI5_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
RUNTIME_WORKFLOW = "weathernext-private-runtime-source.yml"
INCOMING_ROOT = Path("/var/lib/rpi5-deploy/weather-private-runtime/incoming")
INCOMING_RECEIPT = INCOMING_ROOT / "runtime-artifact-receipt.json"
INCOMING_ARTIFACT = INCOMING_ROOT / "weathernext-private-runtime.tar"
INCOMING_ACTIONS_EVIDENCE = INCOMING_ROOT / "actions-artifact-handoff.json"
CACHE_RECEIPT = ARTIFACT_CACHE_ROOT / "artifact-receipt.json"
CACHE_ACTIONS_EVIDENCE = ARTIFACT_CACHE_ROOT / INCOMING_ACTIONS_EVIDENCE.name
EXECUTION_LOCATION_CLASS = "trusted-home-host"
DEPLOY_CLASS = "STRICT_LIVE_AUTH_REQUIRED"
ADAPTER_ID = "rpi5.weathernext-private-runtime-materialization.fixed-v1"
BASELINE_RESOLVER_ID = "rpi5.weathernext-private-runtime.fixed-state-v1"
ROLLBACK_POLICY = "NONE"
MUTATION_BUDGET = (
    ("filesystem.weathernext-private-runtime-artifact-cache-publish", 1),
    ("filesystem.weathernext-private-runtime-materialization", 1),
)
REQUIRED_EXCLUSIONS = (
    "no Actions artifact download or credential acquisition",
    "no Google auth or project binding",
    "no Analytics Hub link mutation",
    "no BigQuery access",
    "no SQLite or corpus write",
    "no Docker or systemd mutation",
    "no package manager or network-control mutation",
    "no generic shell path argv or environment authority",
    "no automatic retry cleanup or rollback",
)
DEPENDENCIES = (
    "source-contract:RPi5_main#704",
    "host-capability:rpi5.weathernext-private-backend.v1",
    "application-stage:rozkalns_weather#122-prerequisite-exact",
    "global-executor-execution:disabled",
)


class WeatherNextPrivateRuntimeTransportError(WeatherNextRuntimeMaterializationError):
    pass


def _fail(message: str) -> None:
    raise WeatherNextPrivateRuntimeTransportError(message)


def _safe_regular(path: Path, *, max_bytes: int) -> os.stat_result:
    try:
        st = path.lstat()
    except OSError:
        _fail(f"fixed runtime transport file is unavailable: {path.name}")
    if (
        not stat.S_ISREG(st.st_mode)
        or stat.S_ISLNK(st.st_mode)
        or st.st_nlink != 1
        or st.st_uid != 0
        or st.st_gid != 0
        or stat.S_IMODE(st.st_mode) != 0o644
        or st.st_size <= 0
        or st.st_size > max_bytes
    ):
        _fail(f"fixed runtime transport file metadata drifted: {path.name}")
    return st


def _read_json_regular(path: Path, *, max_bytes: int) -> Mapping[str, Any]:
    st = _safe_regular(path, max_bytes=max_bytes)
    try:
        raw = path.read_bytes()
        if len(raw) != st.st_size:
            _fail(f"fixed runtime JSON changed during read: {path.name}")
        value = json.loads(raw.decode("utf-8", "strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail(f"fixed runtime JSON is unreadable: {path.name}")
    if type(value) is not dict:
        _fail(f"fixed runtime JSON must be an object: {path.name}")
    return value


def _load_receipt(path: Path, *, expected_source_sha: str) -> RuntimeArtifactReceipt:
    value = _read_json_regular(path, max_bytes=64 * 1024)
    try:
        receipt = RuntimeArtifactReceipt.from_mapping(value)
        validate_artifact_receipt(receipt, expected_source_sha=expected_source_sha)
    except WeatherNextRuntimeMaterializationError as exc:
        raise WeatherNextPrivateRuntimeTransportError(str(exc)) from exc
    return receipt


def _validate_artifact(path: Path, receipt: RuntimeArtifactReceipt) -> None:
    st = _safe_regular(path, max_bytes=MAX_ARTIFACT_BYTES)
    if st.st_size != receipt.artifact_size_bytes:
        _fail("runtime artifact size mismatch")
    if _hash_file(path) != receipt.artifact_sha256:
        _fail("runtime artifact digest mismatch")
    try:
        _load_archive_payload(path, load_runtime_lock(), receipt)
    except WeatherNextRuntimeMaterializationError as exc:
        raise WeatherNextPrivateRuntimeTransportError(str(exc)) from exc


@dataclass(frozen=True)
class RuntimeActionsEvidence:
    source_sha: str
    run_id: int
    artifact_id: int
    artifact_name: str
    artifact_digest: str


def _runtime_actions_evidence(
    client: FixedPublicGitHubReadClient,
    source_sha: str,
) -> RuntimeActionsEvidence:
    if type(client) is not FixedPublicGitHubReadClient:
        _fail("runtime Actions evidence requires fixed public GitHub client")
    expected_name = f"weathernext-private-runtime-{source_sha}"
    runs_value = client.get_json(
        f"/repos/{RPI5_MAIN_REPOSITORY}/actions/workflows/{RUNTIME_WORKFLOW}/runs"
        f"?branch=main&head_sha={source_sha}&status=completed&per_page=100"
    ).value
    if type(runs_value) is not dict or type(runs_value.get("workflow_runs")) is not list:
        _fail("runtime Actions workflow run list is malformed")
    successful = [
        row
        for row in runs_value["workflow_runs"]
        if type(row) is dict
        and row.get("head_sha") == source_sha
        and row.get("head_branch") == "main"
        and row.get("event") == "push"
        and row.get("status") == "completed"
        and row.get("conclusion") == "success"
        and type(row.get("id")) is int
        and row["id"] > 0
    ]
    if not successful:
        _fail("exact-main runtime source workflow has no successful run")
    run_id = max(row["id"] for row in successful)

    artifacts_value = client.get_json(
        f"/repos/{RPI5_MAIN_REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100"
    ).value
    if type(artifacts_value) is not dict or type(artifacts_value.get("artifacts")) is not list:
        _fail("runtime Actions artifact list is malformed")
    matches = []
    for row in artifacts_value["artifacts"]:
        if type(row) is not dict:
            continue
        workflow_run = row.get("workflow_run")
        if type(workflow_run) is not dict:
            continue
        digest = row.get("digest")
        if (
            row.get("name") == expected_name
            and row.get("expired") is False
            and type(row.get("id")) is int
            and row["id"] > 0
            and workflow_run.get("id") == run_id
            and workflow_run.get("head_sha") == source_sha
            and type(digest) is str
            and digest.startswith("sha256:")
            and len(digest) == 71
            and all(char in "0123456789abcdef" for char in digest[7:])
        ):
            matches.append(row)
    if len(matches) != 1:
        _fail("exact-main runtime Actions artifact identity is unavailable or ambiguous")
    artifact = matches[0]
    return RuntimeActionsEvidence(
        source_sha=source_sha,
        run_id=run_id,
        artifact_id=artifact["id"],
        artifact_name=expected_name,
        artifact_digest=artifact["digest"],
    )


def _actions_handoff_value(expected: RuntimeActionsEvidence) -> Mapping[str, Any]:
    return {
        "schema": "rpi5.weathernext-private-runtime-actions-handoff.v1",
        "source_sha": expected.source_sha,
        "workflow": RUNTIME_WORKFLOW,
        "run_id": expected.run_id,
        "artifact_id": expected.artifact_id,
        "artifact_name": expected.artifact_name,
        "artifact_digest": expected.artifact_digest,
    }


def _require_actions_handoff(
    expected: RuntimeActionsEvidence,
    *,
    path: Path = INCOMING_ACTIONS_EVIDENCE,
) -> None:
    value = _read_json_regular(path, max_bytes=16 * 1024)
    required = {
        "schema",
        "source_sha",
        "workflow",
        "run_id",
        "artifact_id",
        "artifact_name",
        "artifact_digest",
    }
    if set(value) != required:
        _fail("runtime Actions handoff keys mismatch")
    observed = {
        "schema": value.get("schema"),
        "source_sha": value.get("source_sha"),
        "workflow": value.get("workflow"),
        "run_id": value.get("run_id"),
        "artifact_id": value.get("artifact_id"),
        "artifact_name": value.get("artifact_name"),
        "artifact_digest": value.get("artifact_digest"),
    }
    required_value = _actions_handoff_value(expected)
    if observed != required_value:
        _fail("runtime Actions handoff identity drifted from exact successful artifact")


def _incoming_receipt(
    expected_source_sha: str,
    actions_evidence: RuntimeActionsEvidence,
) -> RuntimeArtifactReceipt:
    try:
        root = INCOMING_ROOT.lstat()
    except OSError:
        _fail("fixed runtime incoming handoff is absent")
    if (
        not stat.S_ISDIR(root.st_mode)
        or stat.S_ISLNK(root.st_mode)
        or root.st_uid != 0
        or root.st_gid != 0
        or stat.S_IMODE(root.st_mode) != 0o755
    ):
        _fail("fixed runtime incoming root metadata drifted")
    try:
        entries = {item.name for item in INCOMING_ROOT.iterdir()}
    except OSError:
        _fail("fixed runtime incoming root is unreadable")
    if entries != {
        INCOMING_RECEIPT.name,
        INCOMING_ARTIFACT.name,
        INCOMING_ACTIONS_EVIDENCE.name,
    }:
        _fail("fixed runtime incoming handoff contains unexpected entries")
    _require_actions_handoff(actions_evidence)
    receipt = _load_receipt(INCOMING_RECEIPT, expected_source_sha=expected_source_sha)
    _validate_artifact(INCOMING_ARTIFACT, receipt)
    return receipt


def _cache_state(
    receipt: RuntimeArtifactReceipt,
    actions_evidence: RuntimeActionsEvidence,
) -> str:
    partial = ARTIFACT_CACHE_ROOT.parent / f".{ARTIFACT_CACHE_ROOT.name}.{receipt.artifact_sha256}.partial"
    if partial.exists() or partial.is_symlink():
        return "CONFLICT"
    if not ARTIFACT_CACHE_ROOT.exists() and not ARTIFACT_CACHE_ROOT.is_symlink():
        return "ABSENT"
    try:
        st = ARTIFACT_CACHE_ROOT.lstat()
    except OSError:
        return "CONFLICT"
    if (
        not stat.S_ISDIR(st.st_mode)
        or stat.S_ISLNK(st.st_mode)
        or st.st_uid != 0
        or st.st_gid != 0
        or stat.S_IMODE(st.st_mode) != 0o755
    ):
        return "CONFLICT"
    artifact = ARTIFACT_CACHE_ROOT / f"{receipt.artifact_sha256}.tar"
    try:
        cached = _load_receipt(CACHE_RECEIPT, expected_source_sha=receipt.source_sha)
        _validate_artifact(artifact, cached)
        _require_actions_handoff(actions_evidence, path=CACHE_ACTIONS_EVIDENCE)
    except WeatherNextRuntimeMaterializationError:
        return "CONFLICT"
    return "EXACT" if cached == receipt else "CONFLICT"


def _runtime_state(receipt: RuntimeArtifactReceipt) -> str:
    staging = RUNTIME_BASE.parent / f".{RUNTIME_BASE.name}.{receipt.artifact_sha256}.partial"
    if staging.exists() or staging.is_symlink():
        return "CONFLICT"
    if not RUNTIME_BASE.exists() and not RUNTIME_BASE.is_symlink():
        return "ABSENT"
    try:
        st = RUNTIME_BASE.lstat()
        marker_path = RUNTIME_BASE / RUNTIME_MARKER_NAME
        marker_st = marker_path.lstat()
        value = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "CONFLICT"
    if (
        not stat.S_ISDIR(st.st_mode)
        or stat.S_ISLNK(st.st_mode)
        or st.st_uid != 0
        or st.st_gid != 0
        or not stat.S_ISREG(marker_st.st_mode)
        or stat.S_ISLNK(marker_st.st_mode)
        or marker_st.st_uid != 0
        or marker_st.st_gid != 0
        or stat.S_IMODE(marker_st.st_mode) != 0o644
    ):
        return "CONFLICT"
    lock = load_runtime_lock()
    expected_marker = {
        "schema": "rozkalns-weather.weathernext-private-runtime-installed.v1",
        "operation_id": OPERATION_ID,
        "source_sha": receipt.source_sha,
        "closure_sha256": receipt.closure_sha256,
        "artifact_sha256": receipt.artifact_sha256,
        "target_python_abi": TARGET_PYTHON_ABI,
        "target_platform": TARGET_PIP_PLATFORM,
        "package_count": len(lock["packages"]),
        "credential_binding": False,
        "project_binding": False,
        "analytics_hub_link": False,
        "bigquery_access": False,
        "sqlite_write": False,
    }
    if value != expected_marker:
        return "CONFLICT"
    observed = ObservedRuntimeIdentity(
        present=True,
        source_sha=value["source_sha"],
        closure_sha256=value["closure_sha256"],
        artifact_sha256=value["artifact_sha256"],
        target_python_abi=value["target_python_abi"],
        target_platform=value["target_platform"],
    )
    return (
        "EXACT"
        if classify_runtime_identity(observed, receipt=receipt)
        == "runtime_materialization_source_ready"
        else "CONFLICT"
    )


@dataclass(frozen=True)
class RuntimeTransportPlan:
    source_sha: str
    receipt: RuntimeArtifactReceipt
    actions_evidence: RuntimeActionsEvidence
    cache_state: str
    runtime_state: str
    mutation_categories: tuple[str, ...]


def build_transport_plan(
    expected_source_sha: str,
    actions_evidence: RuntimeActionsEvidence,
) -> RuntimeTransportPlan:
    if actions_evidence.source_sha != expected_source_sha:
        _fail("runtime Actions evidence source SHA drifted")
    receipt = _incoming_receipt(expected_source_sha, actions_evidence)
    cache_state = _cache_state(receipt, actions_evidence)
    runtime_state = _runtime_state(receipt)
    if cache_state == "CONFLICT" or runtime_state == "CONFLICT":
        _fail("private runtime transport conflicts with fixed reviewed state")
    categories: list[str] = []
    if cache_state == "ABSENT":
        categories.append(MUTATION_BUDGET[0][0])
    if runtime_state == "ABSENT":
        categories.append(MUTATION_BUDGET[1][0])
    return RuntimeTransportPlan(
        source_sha=expected_source_sha,
        receipt=receipt,
        actions_evidence=actions_evidence,
        cache_state=cache_state,
        runtime_state=runtime_state,
        mutation_categories=tuple(categories),
    )


def public_plan(plan: RuntimeTransportPlan) -> Mapping[str, Any]:
    return {
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_sha": plan.source_sha,
        "artifact_sha256": plan.receipt.artifact_sha256,
        "closure_sha256": plan.receipt.closure_sha256,
        "actions_run_id": plan.actions_evidence.run_id,
        "actions_artifact_id": plan.actions_evidence.artifact_id,
        "actions_artifact_name": plan.actions_evidence.artifact_name,
        "actions_artifact_digest": plan.actions_evidence.artifact_digest,
        "cache_state": plan.cache_state,
        "runtime_state": plan.runtime_state,
        "mutation_categories": list(plan.mutation_categories),
        "rollback_policy": ROLLBACK_POLICY,
    }


def _publish_cache(
    receipt: RuntimeArtifactReceipt,
    actions_evidence: RuntimeActionsEvidence,
) -> None:
    if _cache_state(receipt, actions_evidence) != "ABSENT":
        _fail("runtime artifact cache changed before publish")
    parent = ARTIFACT_CACHE_ROOT.parent
    try:
        parent_st = parent.lstat()
    except OSError:
        _fail("runtime artifact cache parent is unavailable")
    if (
        not stat.S_ISDIR(parent_st.st_mode)
        or stat.S_ISLNK(parent_st.st_mode)
        or parent_st.st_uid != 0
        or parent_st.st_gid != 0
    ):
        _fail("runtime artifact cache parent metadata drifted")
    partial = parent / f".{ARTIFACT_CACHE_ROOT.name}.{receipt.artifact_sha256}.partial"
    if partial.exists() or partial.is_symlink():
        _fail("runtime artifact cache partial state exists")
    partial.mkdir(mode=0o755)
    receipt_path = partial / CACHE_RECEIPT.name
    actions_path = partial / CACHE_ACTIONS_EVIDENCE.name
    artifact_path = partial / f"{receipt.artifact_sha256}.tar"
    receipt_path.write_text(
        json.dumps(
            {
                "source_sha": receipt.source_sha,
                "closure_sha256": receipt.closure_sha256,
                "artifact_sha256": receipt.artifact_sha256,
                "artifact_size_bytes": receipt.artifact_size_bytes,
                "artifact_format": receipt.artifact_format,
                "target_os": receipt.target_os,
                "target_architecture": receipt.target_architecture,
                "target_python_version": receipt.target_python_version,
                "target_python_abi": receipt.target_python_abi,
                "target_platform": receipt.target_platform,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(receipt_path, 0o644)
    actions_path.write_text(
        json.dumps(_actions_handoff_value(actions_evidence), sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    os.chmod(actions_path, 0o644)
    with INCOMING_ARTIFACT.open("rb") as source, artifact_path.open("xb") as destination:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            destination.write(block)
    os.chmod(artifact_path, 0o644)
    _validate_artifact(artifact_path, receipt)
    _rename_noreplace(partial, ARTIFACT_CACHE_ROOT)


def apply_transport_plan(plan: RuntimeTransportPlan) -> Mapping[str, Any]:
    if os.geteuid() != 0:
        _fail("private runtime transport must run as root")
    if public_plan(build_transport_plan(plan.source_sha, plan.actions_evidence)) != public_plan(plan):
        _fail("private runtime transport plan drifted before mutation")
    executed: list[str] = []
    if plan.cache_state == "ABSENT":
        _publish_cache(plan.receipt, plan.actions_evidence)
        executed.append(MUTATION_BUDGET[0][0])
    if plan.runtime_state == "ABSENT":
        try:
            result = materialize_reviewed_runtime(
                PRIVATE_CONTRACT_ID,
                plan.receipt,
                expected_source_sha=plan.source_sha,
            )
        except WeatherNextRuntimeMaterializationError as exc:
            raise WeatherNextPrivateRuntimeTransportError(str(exc)) from exc
        if result.get("status") != "runtime_materialized":
            _fail("private runtime materializer returned unexpected status")
        executed.append(MUTATION_BUDGET[1][0])
    return {
        "status": "runtime_transport_exact",
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_sha": plan.source_sha,
        "artifact_sha256": plan.receipt.artifact_sha256,
        "closure_sha256": plan.receipt.closure_sha256,
        "actions_run_id": plan.actions_evidence.run_id,
        "actions_artifact_id": plan.actions_evidence.artifact_id,
        "mutation_categories": executed,
        "production_mutation_started": bool(executed),
        "rollback_policy": ROLLBACK_POLICY,
    }


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
            "exact current RPi5_main and trusted privileged boundary are revalidated",
            "exact successful runtime-source Actions run/artifact identity is independently derived",
            "fixed incoming artifact receipt tar and Actions handoff are root-controlled and exact",
            "artifact cache and runtime are absent or exact without partial/conflicting state",
        ),
        postconditions=(
            "fixed reviewed runtime artifact cache is exact",
            "private cp313 runtime identity is exact",
            "no credential Google BigQuery SQLite Docker systemd package or network stage executes",
        ),
        required_github_evidence=(
            "owner-authored non-App LIVE-AUTH",
            "READY Queue exact operation target source and mutation budget binding",
            "current RPi5_main exact-main required CI",
            "successful exact-main WeatherNext private runtime source workflow artifact metadata",
        ),
    )
    return OperationRegistry(schema_version=1, execution_enabled=False, operations=(operation,))


def _server_time(response: Any) -> datetime:
    value = getattr(response, "server_time", None)
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fail("GitHub server time is unavailable")
    return value.astimezone(timezone.utc)


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
            _fail(f"canonical runtime LIVE-AUTH {field} drifted")
    exclusions = payload.get("exclusions")
    if type(exclusions) is not list or not set(REQUIRED_EXCLUSIONS).issubset(set(exclusions)):
        _fail("canonical runtime LIVE-AUTH exclusions drifted")
    return payload


def _require_queue(normalized: Any) -> Mapping[str, Any]:
    if getattr(normalized, "execution_enabled", None) is not False:
        _fail("private runtime registry unexpectedly enables execution")
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
            _fail(f"private runtime Queue {field} drifted")
    observed_budget = tuple(
        (item.category, item.max_operations)
        for item in getattr(operation, "mutation_budget", ())
    )
    if observed_budget != MUTATION_BUDGET:
        _fail("private runtime Queue mutation budget drifted")
    baseline = getattr(operation, "baseline", None)
    if (
        getattr(baseline, "kind", None) != "resolver"
        or getattr(baseline, "resolver_id", None) != BASELINE_RESOLVER_ID
    ):
        _fail("private runtime Queue baseline drifted")
    return normalized.as_protocol_queue()


def _require_trusted_boundary_exact(rpi5_main_sha: str) -> None:
    module_path = Path(__file__).resolve()
    expected_lib = TRUSTED_BOUNDARY / "ops/lib/deploy_executor"
    try:
        module_path.relative_to(expected_lib)
    except ValueError:
        _fail("runtime transport is outside fixed trusted installer boundary")
    from .weather_private_application_staging import _default_runner, _fixed_git_prefix, _run

    prefix = _fixed_git_prefix()
    origin = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "config", "--get", "remote.origin.url"),
        "trusted boundary origin",
    ).strip()
    head = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "rev-parse", "HEAD"),
        "trusted boundary HEAD",
    ).strip()
    branch = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "rev-parse", "--abbrev-ref", "HEAD"),
        "trusted boundary detached state",
    ).strip()
    tracked = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "status", "--porcelain", "--untracked-files=no"),
        "trusted boundary clean state",
    )
    if origin != REVIEWED_RPI5_ORIGIN or head != rpi5_main_sha or branch != "HEAD" or tracked != "":
        _fail("installed privileged boundary is not exact current RPi5_main")


@dataclass(frozen=True)
class CanonicalRuntimeEvidence:
    authorization_issue_number: int
    authorization_issue_id: int
    authorization_created_at: str
    request_id: str
    request_body_sha256: str
    rpi5_main_sha: str
    queue_issue_number: int
    actions_run_id: int
    actions_artifact_id: int
    actions_artifact_name: str
    actions_artifact_digest: str


class ConcreteRuntimeRevalidator:
    def __init__(
        self,
        *,
        authorization_client: Any,
        queue_client: Any,
        sources: PublicExactSourceEvidenceProvider,
        public_client: FixedPublicGitHubReadClient,
        auth_surface: Any,
        replay: DurableInstallReplayAuthority,
    ):
        require_isolated_auth_surface(auth_surface)
        self._authorization_client = authorization_client
        self._queue_client = queue_client
        self._sources = sources
        self._public_client = public_client
        self._auth_surface = auth_surface
        self._replay = replay
        self._registry = _fixed_registry()
        self.accepted: AcceptedAuthorization | None = None

    def revalidate(self, issue_number: int) -> CanonicalRuntimeEvidence:
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
            _fail("private runtime Queue issue number is invalid")
        queue_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue_number}"
        )
        normalized = normalize_ready_queue(
            queue_response.value,
            repository_full_name=QUEUE_REPOSITORY,
            registry=self._registry,
        )
        validate_queue_binding(accepted, _require_queue(normalized))
        rpi = self._sources.load_exact_source(RPI5_MAIN_REPOSITORY, RPI5_MAIN_REPOSITORY_ID)
        if payload.get("source_sha") != rpi.source_sha or rpi.current_main_sha != rpi.source_sha:
            _fail("private runtime source is not exact current RPi5_main")
        _require_trusted_boundary_exact(rpi.source_sha)
        actions = _runtime_actions_evidence(self._public_client, rpi.source_sha)
        build_transport_plan(rpi.source_sha, actions)
        if self._replay.is_available(accepted) is not True:
            _fail("private runtime LIVE-AUTH is unavailable for one-shot consume")
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
            _fail("private runtime LIVE-AUTH replay state drifted")
        self.accepted = accepted
        return CanonicalRuntimeEvidence(
            authorization_issue_number=issue_number,
            authorization_issue_id=accepted.issue_id,
            authorization_created_at=accepted.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            request_id=accepted.request_id,
            request_body_sha256=accepted.raw_body_sha256,
            rpi5_main_sha=rpi.source_sha,
            queue_issue_number=queue_issue_number,
            actions_run_id=actions.run_id,
            actions_artifact_id=actions.artifact_id,
            actions_artifact_name=actions.artifact_name,
            actions_artifact_digest=actions.artifact_digest,
        )


def _stable(first: CanonicalRuntimeEvidence, final: CanonicalRuntimeEvidence) -> None:
    if first != final:
        _fail("canonical private runtime evidence drifted")


def _actions_from_evidence(evidence: CanonicalRuntimeEvidence) -> RuntimeActionsEvidence:
    return RuntimeActionsEvidence(
        source_sha=evidence.rpi5_main_sha,
        run_id=evidence.actions_run_id,
        artifact_id=evidence.actions_artifact_id,
        artifact_name=evidence.actions_artifact_name,
        artifact_digest=evidence.actions_artifact_digest,
    )


def run_privileged_runtime_materialization(authorization_issue_number: int) -> Mapping[str, object]:
    if os.geteuid() != 0:
        _fail("private runtime boundary must run as root")
    replay = DurableInstallReplayAuthority()
    try:
        auth_surface = load_contract(AUTH_SURFACE)
        require_isolated_auth_surface(auth_surface)
        clients = build_p9_read_clients(auth_surface=auth_surface, private_key=EXECUTOR_PRIVATE_KEY)
        public_client = FixedPublicGitHubReadClient()
        sources = PublicExactSourceEvidenceProvider(client=public_client)
        revalidator = ConcreteRuntimeRevalidator(
            authorization_client=clients.authorization,
            queue_client=clients.queue,
            sources=sources,
            public_client=public_client,
            auth_surface=auth_surface,
            replay=replay,
        )
        first = revalidator.revalidate(authorization_issue_number)
        final = revalidator.revalidate(authorization_issue_number)
        _stable(first, final)
        actions = _actions_from_evidence(final)
        plan = build_transport_plan(final.rpi5_main_sha, actions)
        if not plan.mutation_categories:
            return {
                "status": "ALREADY_EXACT",
                "operation_id": OPERATION_ID,
                "target_alias": TARGET_ALIAS,
                "source_sha": final.rpi5_main_sha,
                "actions_run_id": final.actions_run_id,
                "actions_artifact_id": final.actions_artifact_id,
                "authorization_consumed": False,
                "production_mutation_started": False,
                "mutation_categories": [],
                "rollback_policy": ROLLBACK_POLICY,
            }
        preconsume = revalidator.revalidate(authorization_issue_number)
        _stable(final, preconsume)
        preconsume_plan = build_transport_plan(
            preconsume.rpi5_main_sha,
            _actions_from_evidence(preconsume),
        )
        if public_plan(preconsume_plan) != public_plan(plan):
            _fail("private runtime plan drifted immediately before consume")
        accepted = revalidator.accepted
        if accepted is None or accepted.request_id != preconsume.request_id:
            _fail("private runtime accepted authorization identity drifted")
        replay.consume(accepted.request_id)
        receipt = dict(apply_transport_plan(preconsume_plan))
        replay.mark_succeeded(accepted.request_id)
        receipt["authorization_consumed"] = True
        return receipt
    except WeatherNextPrivateRuntimeTransportError:
        raise
    except WeatherNextRuntimeMaterializationError as exc:
        raise WeatherNextPrivateRuntimeTransportError(str(exc)) from exc
    except Exception:
        raise WeatherNextPrivateRuntimeTransportError(
            "WeatherNext private runtime transport failed closed"
        ) from None


def source_readiness() -> Mapping[str, object]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_repository": SOURCE_REPOSITORY,
        "caller_authority": ("authorization_issue_number",),
        "incoming_root": str(INCOMING_ROOT),
        "incoming_actions_evidence": str(INCOMING_ACTIONS_EVIDENCE),
        "artifact_cache_root": str(ARTIFACT_CACHE_ROOT),
        "runtime_root": str(RUNTIME_BASE),
        "mutation_budget": MUTATION_BUDGET,
        "rollback_policy": ROLLBACK_POLICY,
        "runtime_actions_metadata_evidence_required": True,
        "actions_artifact_download_authority": False,
        "credential_acquisition_authority": False,
        "network_install_authority": False,
        "package_manager_authority": False,
        "google_action_allowed": False,
        "bigquery_action_allowed": False,
        "sqlite_write_allowed": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
