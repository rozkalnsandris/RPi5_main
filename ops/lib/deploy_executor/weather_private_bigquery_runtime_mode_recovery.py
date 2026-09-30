from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping
import zipfile

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
from .weather_private_application_staging import _default_runner, _fixed_git_prefix, _run
from .weather_private_bigquery_host_bindings import (
    FixedPublicGitHubReadClient,
    PublicExactSourceEvidenceProvider,
)
from .weather_private_bigquery_host_installer_runtime import DurableInstallReplayAuthority
from .weather_private_bigquery_host_runtime import RPI5_MAIN_REPOSITORY, RPI5_MAIN_REPOSITORY_ID
from .weather_private_bigquery_runtime_materialization import (
    ARTIFACT_CACHE_ROOT,
    FIXED_DIRECTORY_MODE,
    RUNTIME_BASE,
    RUNTIME_MARKER_NAME,
    RUNTIME_SITE_PACKAGES_NAME,
    TARGET_PIP_PLATFORM,
    TARGET_PYTHON_ABI,
    RuntimeArtifactReceipt,
    WeatherNextRuntimeMaterializationError,
    _hash_file,
    _load_archive_payload,
    _safe_posix_parts,
    _wheel_target,
    load_runtime_lock,
)
from .weather_private_bigquery_runtime_transport import (
    AUTH_SURFACE,
    CACHE_ACTIONS_EVIDENCE,
    CACHE_RECEIPT,
    DEPLOY_CLASS,
    EXECUTION_LOCATION_CLASS,
    EXECUTOR_PRIVATE_KEY,
    REVIEWED_RPI5_ORIGIN,
    RuntimeActionsEvidence,
    _incoming_receipt,
    _load_receipt,
    _require_actions_handoff,
    _runtime_actions_evidence,
    _validate_artifact,
)

IMPLEMENTATION_ISSUE = 717
OPERATION_ID = "rpi5.weathernext-private-runtime-mode-recovery.v1"
TARGET_ALIAS = "rpi5-weathernext-private-runtime-mode-recovery"
SOURCE_REPOSITORY = RPI5_MAIN_REPOSITORY
ADAPTER_ID = "rpi5.weathernext-private-runtime-mode-recovery.fixed-v1"
BASELINE_RESOLVER_ID = "rpi5.weathernext-private-runtime-mode-recovery.fixed-state-v1"
ROLLBACK_POLICY = "NONE"
INCIDENT_SOURCE_SHA = "79372e48ac53bf6d00142578b6543bc33a72a692"
INCIDENT_DIRECTORY_MODE = 0o700
ROOT_UID = 0
ROOT_GID = 0
INSTALLED_ENTRYPOINT = Path("/usr/local/sbin/rpi5-weathernext-private-host-privileged-install")
TRUSTED_BOUNDARY = Path("/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted")
TRUSTED_ENTRYPOINT = TRUSTED_BOUNDARY / "ops/bin/rpi5-weathernext-private-host-privileged-install"

MUTATION_BUDGET = (("filesystem.weathernext-private-runtime-directory-mode-reconciliation", 1),)
REQUIRED_EXCLUSIONS = (
    "no runtime artifact republish or rematerialization",
    "no Actions artifact download or credential acquisition",
    "no Google auth project API or Analytics Hub action",
    "no BigQuery access",
    "no SQLite corpus or application-stage write",
    "no Docker or systemd mutation",
    "no package manager or network-control mutation",
    "no caller-selected shell path argv or environment authority",
    "no automatic retry cleanup or rollback",
)
DEPENDENCIES = (
    "incident-runtime:ops-workflows#104-and-deploy-authorizations#39-consumed",
    "future-creation-fix:RPi5_main#707",
    "application-stage:rozkalns_weather#122-prerequisite-exact",
    "installer-boundary:exact-current-RPi5_main",
)


class WeatherNextPrivateRuntimeModeRecoveryError(WeatherNextRuntimeMaterializationError):
    pass


def _fail(message: str) -> None:
    raise WeatherNextPrivateRuntimeModeRecoveryError(message)


@dataclass(frozen=True)
class ExpectedRuntimeFile:
    relative_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ExpectedRuntimeManifest:
    directories: tuple[str, ...]
    files: tuple[ExpectedRuntimeFile, ...]


@dataclass(frozen=True)
class RuntimeModeRecoveryPlan:
    current_source_sha: str
    receipt: RuntimeArtifactReceipt
    actions_evidence: RuntimeActionsEvidence
    manifest: ExpectedRuntimeManifest
    prior_state: str
    directory_paths: tuple[Path, ...]
    mutation_categories: tuple[str, ...]


def _manifest_from_wheels(wheels: Mapping[str, bytes], lock: Mapping[str, Any]) -> ExpectedRuntimeManifest:
    directories: set[tuple[str, ...]] = set()
    files: dict[tuple[str, ...], ExpectedRuntimeFile] = {}

    def add_directory(parts: tuple[str, ...]) -> None:
        for index in range(1, len(parts) + 1):
            prefix = parts[:index]
            if prefix in files:
                _fail("reviewed runtime wheel has file-directory collision")
            directories.add(prefix)

    for package in lock["packages"]:
        filename = package["filename"]
        data = wheels.get(filename)
        if type(data) is not bytes:
            _fail("reviewed runtime wheel payload is incomplete")
        try:
            archive = zipfile.ZipFile(io.BytesIO(data), mode="r")
        except zipfile.BadZipFile as exc:
            raise WeatherNextPrivateRuntimeModeRecoveryError(
                "reviewed runtime wheel is not a valid ZIP archive"
            ) from exc
        with archive:
            for info in archive.infolist():
                parts = _safe_posix_parts(info.filename)
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(unix_mode):
                    _fail("reviewed runtime wheel symlinks are forbidden")
                mapped = _wheel_target(parts)
                if info.is_dir():
                    add_directory(mapped)
                    continue
                if mapped[:-1]:
                    add_directory(mapped[:-1])
                if mapped in directories or mapped in files:
                    _fail("reviewed runtime wheel target collision")
                payload = archive.read(info)
                files[mapped] = ExpectedRuntimeFile(
                    PurePosixPath(*mapped).as_posix(),
                    len(payload),
                    hashlib.sha256(payload).hexdigest(),
                )

    ordered_directories = tuple(
        PurePosixPath(*parts).as_posix()
        for parts in sorted(directories, key=lambda item: (len(item), item))
    )
    ordered_files = tuple(files[parts] for parts in sorted(files))
    if not ordered_files:
        _fail("reviewed runtime manifest contains no files")
    return ExpectedRuntimeManifest(ordered_directories, ordered_files)


def _require_real_root_directory(path: Path, *, allowed_modes: frozenset[int]) -> int:
    try:
        st = path.lstat()
    except OSError as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError(
            f"fixed recovery directory is unavailable: {path.name}"
        ) from exc
    mode = stat.S_IMODE(st.st_mode)
    if (
        not stat.S_ISDIR(st.st_mode)
        or stat.S_ISLNK(st.st_mode)
        or st.st_uid != ROOT_UID
        or st.st_gid != ROOT_GID
        or mode not in allowed_modes
    ):
        _fail(f"fixed recovery directory metadata drifted: {path.name}")
    return mode


def _require_parent_and_no_partials(receipt: RuntimeArtifactReceipt) -> None:
    parent = RUNTIME_BASE.parent
    _require_real_root_directory(parent, allowed_modes=frozenset({FIXED_DIRECTORY_MODE}))
    fixed = {
        parent / f".{ARTIFACT_CACHE_ROOT.name}.{receipt.artifact_sha256}.partial",
        parent / f".{RUNTIME_BASE.name}.{receipt.artifact_sha256}.partial",
    }
    if any(path.exists() or path.is_symlink() for path in fixed):
        _fail("fixed runtime partial state exists")
    try:
        names = {entry.name for entry in parent.iterdir()}
    except OSError as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError("runtime parent cannot be enumerated") from exc
    if any(
        (name.startswith(f".{ARTIFACT_CACHE_ROOT.name}.") or name.startswith(f".{RUNTIME_BASE.name}."))
        and name.endswith(".partial")
        for name in names
    ):
        _fail("unexpected runtime partial state exists")


def _validate_cache(
    receipt: RuntimeArtifactReceipt,
    actions: RuntimeActionsEvidence,
) -> tuple[RuntimeArtifactReceipt, dict[str, bytes], int]:
    cache_mode = _require_real_root_directory(
        ARTIFACT_CACHE_ROOT,
        allowed_modes=frozenset({INCIDENT_DIRECTORY_MODE, FIXED_DIRECTORY_MODE}),
    )
    artifact = ARTIFACT_CACHE_ROOT / f"{receipt.artifact_sha256}.tar"
    expected_entries = {CACHE_RECEIPT.name, CACHE_ACTIONS_EVIDENCE.name, artifact.name}
    try:
        observed_entries = {item.name for item in ARTIFACT_CACHE_ROOT.iterdir()}
    except OSError as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError(
            "runtime artifact cache cannot be enumerated"
        ) from exc
    if observed_entries != expected_entries:
        _fail("runtime artifact cache contains unexpected entries")
    cached = _load_receipt(CACHE_RECEIPT, expected_source_sha=INCIDENT_SOURCE_SHA)
    if cached != receipt:
        _fail("cached runtime receipt drifted from incident handoff")
    _validate_artifact(artifact, cached)
    _require_actions_handoff(actions, path=CACHE_ACTIONS_EVIDENCE)
    try:
        _metadata, wheels = _load_archive_payload(artifact, load_runtime_lock(), cached)
    except WeatherNextRuntimeMaterializationError as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError(str(exc)) from exc
    return cached, wheels, cache_mode


def _expected_marker(receipt: RuntimeArtifactReceipt) -> Mapping[str, Any]:
    lock = load_runtime_lock()
    return {
        "schema": "rozkalns-weather.weathernext-private-runtime-installed.v1",
        "operation_id": "rozkalns-weather.weathernext-private-runtime-materialization.v1",
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


def _validate_marker(receipt: RuntimeArtifactReceipt) -> None:
    marker = RUNTIME_BASE / RUNTIME_MARKER_NAME
    try:
        st = marker.lstat()
    except OSError as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError("runtime marker is unavailable") from exc
    if (
        not stat.S_ISREG(st.st_mode)
        or stat.S_ISLNK(st.st_mode)
        or st.st_nlink != 1
        or st.st_uid != ROOT_UID
        or st.st_gid != ROOT_GID
        or stat.S_IMODE(st.st_mode) != 0o644
        or not 0 < st.st_size <= 64 * 1024
    ):
        _fail("runtime marker metadata drifted")
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError("runtime marker is unreadable") from exc
    if value != _expected_marker(receipt):
        _fail("runtime marker identity drifted")


def _scan_site_packages(site_packages: Path) -> tuple[dict[str, int], dict[str, os.stat_result]]:
    directories: dict[str, int] = {}
    files: dict[str, os.stat_result] = {}

    def visit(directory: Path, relative: tuple[str, ...]) -> None:
        try:
            entries = tuple(os.scandir(directory))
        except OSError as exc:
            raise WeatherNextPrivateRuntimeModeRecoveryError(
                "runtime site-packages cannot be enumerated"
            ) from exc
        for entry in entries:
            rel = relative + (entry.name,)
            rel_name = PurePosixPath(*rel).as_posix()
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise WeatherNextPrivateRuntimeModeRecoveryError(
                    "runtime site-packages metadata read failed"
                ) from exc
            if stat.S_ISLNK(st.st_mode):
                _fail("runtime site-packages contains a symlink")
            if st.st_uid != ROOT_UID or st.st_gid != ROOT_GID:
                _fail("runtime site-packages ownership drifted")
            if stat.S_ISDIR(st.st_mode):
                mode = stat.S_IMODE(st.st_mode)
                if mode not in {INCIDENT_DIRECTORY_MODE, FIXED_DIRECTORY_MODE}:
                    _fail("runtime site-packages directory mode drifted")
                directories[rel_name] = mode
                visit(Path(entry.path), rel)
            elif stat.S_ISREG(st.st_mode):
                if st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o644:
                    _fail("runtime site-packages file metadata drifted")
                files[rel_name] = st
            else:
                _fail("runtime site-packages contains unsupported object type")

    visit(site_packages, ())
    return directories, files


def _validate_runtime_tree(
    receipt: RuntimeArtifactReceipt,
    manifest: ExpectedRuntimeManifest,
) -> tuple[tuple[Path, ...], tuple[int, ...]]:
    runtime_mode = _require_real_root_directory(
        RUNTIME_BASE,
        allowed_modes=frozenset({INCIDENT_DIRECTORY_MODE, FIXED_DIRECTORY_MODE}),
    )
    site_packages = RUNTIME_BASE / RUNTIME_SITE_PACKAGES_NAME
    site_mode = _require_real_root_directory(
        site_packages,
        allowed_modes=frozenset({INCIDENT_DIRECTORY_MODE, FIXED_DIRECTORY_MODE}),
    )
    try:
        root_entries = {entry.name for entry in RUNTIME_BASE.iterdir()}
    except OSError as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError("runtime root cannot be enumerated") from exc
    if root_entries != {RUNTIME_SITE_PACKAGES_NAME, RUNTIME_MARKER_NAME}:
        _fail("runtime root contains unexpected entries")
    _validate_marker(receipt)

    observed_directories, observed_files = _scan_site_packages(site_packages)
    expected_directories = set(manifest.directories)
    expected_files = {item.relative_path: item for item in manifest.files}
    if set(observed_directories) != expected_directories:
        _fail("runtime directory manifest drifted from reviewed artifact")
    if set(observed_files) != set(expected_files):
        _fail("runtime file manifest drifted from reviewed artifact")
    for relative, expected in expected_files.items():
        st = observed_files[relative]
        if st.st_size != expected.size:
            _fail("runtime file size drifted from reviewed artifact")
        path = site_packages.joinpath(*PurePosixPath(relative).parts)
        if _hash_file(path) != expected.sha256:
            _fail("runtime file bytes drifted from reviewed artifact")

    nested_paths = tuple(
        site_packages.joinpath(*PurePosixPath(relative).parts)
        for relative in manifest.directories
    )
    nested_modes = tuple(observed_directories[relative] for relative in manifest.directories)
    return (RUNTIME_BASE, site_packages, *nested_paths), (runtime_mode, site_mode, *nested_modes)


def _classify_modes(cache_mode: int, runtime_modes: tuple[int, ...]) -> str:
    modes = {cache_mode, *runtime_modes}
    if modes == {FIXED_DIRECTORY_MODE}:
        return "EXACT"
    if modes == {INCIDENT_DIRECTORY_MODE}:
        return "INCIDENT"
    return "CONFLICT"


def _validated_incident_state(
    public_client: FixedPublicGitHubReadClient,
) -> tuple[RuntimeArtifactReceipt, RuntimeActionsEvidence, ExpectedRuntimeManifest, tuple[Path, ...], str]:
    actions = _runtime_actions_evidence(public_client, INCIDENT_SOURCE_SHA)
    receipt = _incoming_receipt(INCIDENT_SOURCE_SHA, actions)
    _require_parent_and_no_partials(receipt)
    cached, wheels, cache_mode = _validate_cache(receipt, actions)
    manifest = _manifest_from_wheels(wheels, load_runtime_lock())
    runtime_paths, runtime_modes = _validate_runtime_tree(cached, manifest)
    state = _classify_modes(cache_mode, runtime_modes)
    if state == "CONFLICT":
        _fail("runtime directory modes are partial or conflict with incident/exact state")
    return cached, actions, manifest, (*runtime_paths, ARTIFACT_CACHE_ROOT), state


def _mutation_order(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    cache = ARTIFACT_CACHE_ROOT
    runtime = RUNTIME_BASE
    site = RUNTIME_BASE / RUNTIME_SITE_PACKAGES_NAME
    nested = [path for path in paths if path not in {cache, runtime, site}]
    nested.sort(key=lambda path: (-len(path.parts), str(path)))
    return (*nested, site, runtime, cache)


def build_recovery_plan(
    current_source_sha: str,
    public_client: FixedPublicGitHubReadClient,
) -> RuntimeModeRecoveryPlan:
    if len(current_source_sha) != 40 or any(c not in "0123456789abcdef" for c in current_source_sha):
        _fail("current RPi5_main source SHA is invalid")
    receipt, actions, manifest, directory_paths, state = _validated_incident_state(public_client)
    categories = () if state == "EXACT" else (MUTATION_BUDGET[0][0],)
    return RuntimeModeRecoveryPlan(
        current_source_sha,
        receipt,
        actions,
        manifest,
        state,
        _mutation_order(directory_paths),
        categories,
    )


def public_plan(plan: RuntimeModeRecoveryPlan) -> Mapping[str, Any]:
    return {
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "current_source_sha": plan.current_source_sha,
        "incident_source_sha": INCIDENT_SOURCE_SHA,
        "artifact_sha256": plan.receipt.artifact_sha256,
        "closure_sha256": plan.receipt.closure_sha256,
        "actions_run_id": plan.actions_evidence.run_id,
        "actions_artifact_id": plan.actions_evidence.artifact_id,
        "prior_state": plan.prior_state,
        "site_packages_directory_count": len(plan.manifest.directories) + 1,
        "runtime_file_count": len(plan.manifest.files),
        "recovery_directory_count": len(plan.directory_paths),
        "mutation_categories": list(plan.mutation_categories),
        "rollback_policy": ROLLBACK_POLICY,
    }


def _chmod_incident_directory_exact(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError(
            "fixed recovery directory changed before mutation"
        ) from exc
    try:
        st = os.fstat(fd)
        if (
            not stat.S_ISDIR(st.st_mode)
            or st.st_uid != ROOT_UID
            or st.st_gid != ROOT_GID
            or stat.S_IMODE(st.st_mode) != INCIDENT_DIRECTORY_MODE
        ):
            _fail("fixed recovery directory changed before mutation")
        os.fchmod(fd, FIXED_DIRECTORY_MODE)
        after = os.fstat(fd)
        if (
            after.st_uid != ROOT_UID
            or after.st_gid != ROOT_GID
            or stat.S_IMODE(after.st_mode) != FIXED_DIRECTORY_MODE
        ):
            _fail("fixed recovery directory mode postcondition failed")
    except OSError as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError(
            "fixed recovery directory mode mutation failed"
        ) from exc
    finally:
        os.close(fd)


def apply_recovery_plan(
    plan: RuntimeModeRecoveryPlan,
    public_client: FixedPublicGitHubReadClient,
) -> Mapping[str, Any]:
    if os.geteuid() != 0:
        _fail("runtime mode recovery must run as root")
    refreshed = build_recovery_plan(plan.current_source_sha, public_client)
    if public_plan(refreshed) != public_plan(plan):
        _fail("runtime mode recovery plan drifted before mutation")
    if plan.prior_state == "EXACT":
        if plan.mutation_categories:
            _fail("exact runtime mode state cannot contain mutations")
        return {
            "status": "ALREADY_EXACT",
            "operation_id": OPERATION_ID,
            "target_alias": TARGET_ALIAS,
            "current_source_sha": plan.current_source_sha,
            "incident_source_sha": INCIDENT_SOURCE_SHA,
            "authorization_consumed": False,
            "production_mutation_started": False,
            "mutation_categories": [],
            "rollback_policy": ROLLBACK_POLICY,
        }
    if plan.prior_state != "INCIDENT" or plan.mutation_categories != (MUTATION_BUDGET[0][0],):
        _fail("runtime mode recovery mutation budget drifted")
    for path in plan.directory_paths:
        _chmod_incident_directory_exact(path)
    post = build_recovery_plan(plan.current_source_sha, public_client)
    if post.prior_state != "EXACT" or post.mutation_categories:
        _fail("runtime mode recovery postcondition is not exact")
    return {
        "status": "RUNTIME_MODES_EXACT",
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "current_source_sha": plan.current_source_sha,
        "incident_source_sha": INCIDENT_SOURCE_SHA,
        "artifact_sha256": plan.receipt.artifact_sha256,
        "closure_sha256": plan.receipt.closure_sha256,
        "site_packages_directory_count": len(plan.manifest.directories) + 1,
        "runtime_file_count": len(plan.manifest.files),
        "recovery_directory_count": len(plan.directory_paths),
        "mutation_categories": [MUTATION_BUDGET[0][0]],
        "production_mutation_started": True,
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
        mutation_budget=tuple(MutationBudget(category=c, max_operations=m) for c, m in MUTATION_BUDGET),
        rollback_policy=ROLLBACK_POLICY,
        exclusions=REQUIRED_EXCLUSIONS,
        dependencies=DEPENDENCIES,
        preflight=(
            "owner LIVE-AUTH and READY Queue are independently revalidated",
            "exact current RPi5_main required CI and installed privileged boundary are revalidated",
            "incident source remains a reviewed ancestor of exact current RPi5_main",
            "historical incoming and cache receipt artifact and Actions identities are exact",
            "runtime marker file manifest directory manifest ownership and no-symlink invariants are exact",
            "all recoverable directories are uniformly incident 0700 or already exact 0755",
        ),
        postconditions=(
            "all validated fixed runtime directories are exact 0755",
            "all regular runtime bytes and modes remain exact to the reviewed artifact",
            "no artifact rematerialization credential Google BigQuery SQLite Docker systemd package or network stage executes",
        ),
        required_github_evidence=(
            "owner-authored non-App LIVE-AUTH",
            "READY Queue exact recovery operation target current source and one-item mutation budget binding",
            "current RPi5_main exact-main required CI",
            "historical exact-main WeatherNext runtime Actions artifact metadata",
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
            _fail(f"canonical recovery LIVE-AUTH {field} drifted")
    exclusions = payload.get("exclusions")
    if type(exclusions) is not list or not set(REQUIRED_EXCLUSIONS).issubset(set(exclusions)):
        _fail("canonical recovery LIVE-AUTH exclusions drifted")
    return payload


def _require_queue(normalized: Any) -> Mapping[str, Any]:
    if getattr(normalized, "execution_enabled", None) is not False:
        _fail("runtime mode recovery registry unexpectedly enables execution")
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
            _fail(f"runtime mode recovery Queue {field} drifted")
    observed_budget = tuple(
        (item.category, item.max_operations) for item in getattr(operation, "mutation_budget", ())
    )
    if observed_budget != MUTATION_BUDGET:
        _fail("runtime mode recovery Queue mutation budget drifted")
    baseline = getattr(operation, "baseline", None)
    if (
        getattr(baseline, "kind", None) != "resolver"
        or getattr(baseline, "resolver_id", None) != BASELINE_RESOLVER_ID
    ):
        _fail("runtime mode recovery Queue baseline drifted")
    return normalized.as_protocol_queue()


def _require_installed_boundary_exact(current_source_sha: str) -> None:
    module_path = Path(__file__).resolve()
    try:
        module_path.relative_to(TRUSTED_BOUNDARY / "ops/lib/deploy_executor")
    except ValueError:
        _fail("runtime mode recovery is outside fixed trusted installer boundary")
    prefix = _fixed_git_prefix()
    origin = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "config", "--get", "remote.origin.url"),
        "runtime recovery trusted boundary origin",
    ).strip()
    head = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "rev-parse", "HEAD"),
        "runtime recovery trusted boundary HEAD",
    ).strip()
    branch = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "rev-parse", "--abbrev-ref", "HEAD"),
        "runtime recovery trusted boundary detached state",
    ).strip()
    tracked = _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "status", "--porcelain", "--untracked-files=no"),
        "runtime recovery trusted boundary clean state",
    )
    _run(
        _default_runner,
        prefix + ("-C", str(TRUSTED_BOUNDARY), "merge-base", "--is-ancestor", INCIDENT_SOURCE_SHA, current_source_sha),
        "runtime recovery incident ancestry",
    )
    if origin != REVIEWED_RPI5_ORIGIN or head != current_source_sha or branch != "HEAD" or tracked != "":
        _fail("installed privileged boundary is not exact current RPi5_main")
    for path in (TRUSTED_ENTRYPOINT, INSTALLED_ENTRYPOINT):
        try:
            st = path.lstat()
        except OSError as exc:
            raise WeatherNextPrivateRuntimeModeRecoveryError(
                "privileged entrypoint identity is unavailable"
            ) from exc
        if (
            not stat.S_ISREG(st.st_mode)
            or stat.S_ISLNK(st.st_mode)
            or st.st_nlink != 1
            or st.st_uid != ROOT_UID
            or st.st_gid != ROOT_GID
            or stat.S_IMODE(st.st_mode) != 0o755
        ):
            _fail("privileged entrypoint metadata drifted")
    if _hash_file(TRUSTED_ENTRYPOINT) != _hash_file(INSTALLED_ENTRYPOINT):
        _fail("installed privileged entrypoint bytes drifted from exact current source")


@dataclass(frozen=True)
class CanonicalRecoveryEvidence:
    authorization_issue_number: int
    authorization_issue_id: int
    authorization_created_at: str
    request_id: str
    request_body_sha256: str
    current_source_sha: str
    queue_issue_number: int
    historical_actions_run_id: int
    historical_actions_artifact_id: int
    historical_actions_artifact_name: str
    historical_actions_artifact_digest: str
    plan: Mapping[str, Any]


class ConcreteRecoveryRevalidator:
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

    def revalidate(self, issue_number: int) -> CanonicalRecoveryEvidence:
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
            _fail("runtime mode recovery Queue issue number is invalid")
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
            _fail("runtime mode recovery source is not exact current RPi5_main")
        _require_installed_boundary_exact(rpi.source_sha)
        plan = build_recovery_plan(rpi.source_sha, self._public_client)
        if self._replay.is_available(accepted) is not True:
            _fail("runtime mode recovery LIVE-AUTH is unavailable for one-shot consume")
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
            _fail("runtime mode recovery LIVE-AUTH replay state drifted")
        self.accepted = accepted
        return CanonicalRecoveryEvidence(
            issue_number,
            accepted.issue_id,
            accepted.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            accepted.request_id,
            accepted.raw_body_sha256,
            rpi.source_sha,
            queue_issue_number,
            plan.actions_evidence.run_id,
            plan.actions_evidence.artifact_id,
            plan.actions_evidence.artifact_name,
            plan.actions_evidence.artifact_digest,
            public_plan(plan),
        )


def _stable(first: CanonicalRecoveryEvidence, final: CanonicalRecoveryEvidence) -> None:
    if first != final:
        _fail("canonical runtime mode recovery evidence drifted")


def run_privileged_runtime_mode_recovery(authorization_issue_number: int) -> Mapping[str, object]:
    if os.geteuid() != 0:
        _fail("runtime mode recovery boundary must run as root")
    replay = DurableInstallReplayAuthority()
    try:
        auth_surface = load_contract(AUTH_SURFACE)
        require_isolated_auth_surface(auth_surface)
        clients = build_p9_read_clients(auth_surface=auth_surface, private_key=EXECUTOR_PRIVATE_KEY)
        public_client = FixedPublicGitHubReadClient()
        sources = PublicExactSourceEvidenceProvider(client=public_client)
        revalidator = ConcreteRecoveryRevalidator(
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
        plan = build_recovery_plan(final.current_source_sha, public_client)
        if public_plan(plan) != final.plan:
            _fail("runtime mode recovery plan drifted after canonical revalidation")
        if not plan.mutation_categories:
            return {
                "status": "ALREADY_EXACT",
                "operation_id": OPERATION_ID,
                "target_alias": TARGET_ALIAS,
                "current_source_sha": final.current_source_sha,
                "incident_source_sha": INCIDENT_SOURCE_SHA,
                "authorization_consumed": False,
                "production_mutation_started": False,
                "mutation_categories": [],
                "rollback_policy": ROLLBACK_POLICY,
            }
        preconsume = revalidator.revalidate(authorization_issue_number)
        _stable(final, preconsume)
        preconsume_plan = build_recovery_plan(preconsume.current_source_sha, public_client)
        if public_plan(preconsume_plan) != final.plan:
            _fail("runtime mode recovery plan drifted immediately before consume")
        accepted = revalidator.accepted
        if accepted is None or accepted.request_id != preconsume.request_id:
            _fail("runtime mode recovery accepted authorization identity drifted")
        replay.consume(accepted.request_id)
        receipt = dict(apply_recovery_plan(preconsume_plan, public_client))
        replay.mark_succeeded(accepted.request_id)
        receipt["authorization_consumed"] = True
        return receipt
    except WeatherNextPrivateRuntimeModeRecoveryError:
        raise
    except WeatherNextRuntimeMaterializationError as exc:
        raise WeatherNextPrivateRuntimeModeRecoveryError(str(exc)) from exc
    except Exception:
        raise WeatherNextPrivateRuntimeModeRecoveryError(
            "WeatherNext private runtime mode recovery failed closed"
        ) from None


def source_readiness() -> Mapping[str, object]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_repository": SOURCE_REPOSITORY,
        "incident_source_sha": INCIDENT_SOURCE_SHA,
        "caller_authority": ("authorization_issue_number",),
        "mutation_budget": MUTATION_BUDGET,
        "baseline_resolver_id": BASELINE_RESOLVER_ID,
        "rollback_policy": ROLLBACK_POLICY,
        "artifact_republish_authority": False,
        "runtime_rematerialization_authority": False,
        "credential_acquisition_authority": False,
        "google_action_allowed": False,
        "bigquery_action_allowed": False,
        "sqlite_write_allowed": False,
        "docker_action_allowed": False,
        "systemd_action_allowed": False,
        "package_manager_authority": False,
        "network_control_authority": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
