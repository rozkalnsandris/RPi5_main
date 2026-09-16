from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import hermes_deals_runner_smoke_broker_bootstrap as base

IMPLEMENTATION_ISSUE = base.IMPLEMENTATION_ISSUE
CHECKOUT_ISOLATION_ISSUE = 584
PAYLOAD_CLOSURE_ISSUE = 588
HISTORICAL_TRUSTED_CHECKOUT_NAME = base.TRUSTED_CHECKOUT_NAME
TRUSTED_CHECKOUT_NAME = "RPi5_main-runner-smoke-broker-bootstrap-v2-trusted"
REVIEWED_ORIGIN = base.REVIEWED_ORIGIN
EXPECTED_HEAD_MODE = base.EXPECTED_HEAD_MODE
SOURCE_DELIVERY_CONTRACT = Path(
    "ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-v2-source-trusted-checkout-bootstrap.json"
)
LEGACY_EXACT_RELEASE_SHA = "db6deecffbc3a46a475d1fd9db97fc679eb15cf8"
LEGACY_RELEASE_DIRECTORIES = (
    Path("ops"),
    Path("ops/bin"),
    Path("ops/lib"),
    Path("ops/lib/deploy_executor"),
)
CURRENT_NEXT_LINK = base.RELEASE_ROOT / "current.next"
UPGRADE_MUTATION_SEQUENCE = (
    "publish-root-owned-sha-release",
    "switch-current-symlink",
)

RunnerSmokeBrokerBootstrapError = base.RunnerSmokeBrokerBootstrapError
RunnerSmokeBrokerBootstrapApplyError = base.RunnerSmokeBrokerBootstrapApplyError
BootstrapObservation = base.BootstrapObservation
BootstrapPlan = base.BootstrapPlan
MUTATION_SEQUENCE = base.MUTATION_SEQUENCE
SOCKET_UNIT = base.SOCKET_UNIT
RECEIPT_SCHEMA = base.RECEIPT_SCHEMA


def source_readiness() -> Mapping[str, Any]:
    ready = dict(base.source_readiness())
    ready.update(
        {
            "checkout_isolation_issue": CHECKOUT_ISOLATION_ISSUE,
            "payload_closure_issue": PAYLOAD_CLOSURE_ISSUE,
            "historical_trusted_checkout_name": HISTORICAL_TRUSTED_CHECKOUT_NAME,
            "trusted_checkout_name": TRUSTED_CHECKOUT_NAME,
            "source_delivery_contract": str(SOURCE_DELIVERY_CONTRACT),
            "legacy_exact_release_sha": LEGACY_EXACT_RELEASE_SHA,
            "legacy_exact_upgrade_supported": True,
            "legacy_release_preserved_after_upgrade": True,
            "upgrade_mutation_sequence": UPGRADE_MUTATION_SEQUENCE,
        }
    )
    return ready


def validate_trusted_checkout(checkout: Path) -> str:
    checkout = checkout.resolve()
    if checkout.name != TRUSTED_CHECKOUT_NAME or not checkout.is_dir():
        base._fail("unexpected trusted checkout identity")
    top = Path(base._git(checkout, "rev-parse", "--show-toplevel").strip()).resolve()
    if top != checkout:
        base._fail("trusted checkout top-level drifted")
    if base._git(checkout, "config", "--get", "remote.origin.url").strip() != REVIEWED_ORIGIN:
        base._fail("trusted checkout origin drifted")
    if base._git(checkout, "rev-parse", "--abbrev-ref", "HEAD").strip() != "HEAD":
        base._fail("trusted checkout must be detached")
    if base._git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        base._fail("trusted checkout is not clean")
    head = base._git(checkout, "rev-parse", "HEAD").strip()
    origin_main = base._git(checkout, "rev-parse", "refs/remotes/origin/main").strip()
    if base._SHA40_RE.fullmatch(head) is None or base._SHA40_RE.fullmatch(origin_main) is None:
        base._fail("trusted checkout SHA is malformed")
    if head != origin_main:
        base._fail("trusted checkout HEAD does not equal origin/main")
    return head


def _legacy_runtime_artifacts() -> tuple[tuple[Path, Path, int], ...]:
    artifacts: list[tuple[Path, Path, int]] = [
        (base.BROKER_ENTRYPOINT, base.BROKER_ENTRYPOINT, base.EXECUTABLE_MODE),
    ]
    artifacts.extend(
        (base.PACKAGE_ROOT / name, base.PACKAGE_ROOT / name, base.MODULE_MODE)
        for name in base.PACKAGE_MODULES
    )
    return tuple(artifacts)


def _desired_for(
    checkout: Path,
    artifacts: Sequence[tuple[Path, Path, int]],
) -> tuple[tuple[Path, bytes, int], ...]:
    return tuple(
        (destination, base._read_source(checkout, source), mode)
        for source, destination, mode in artifacts
    )


def _release_tree_has_only_expected(
    release: Path,
    destinations: Sequence[Path],
    directories: Sequence[Path],
) -> bool:
    expected_files = {str(path) for path in destinations}
    expected_dirs = {str(path) for path in directories}
    try:
        observed_files: set[str] = set()
        observed_dirs: set[str] = set()
        for root, dirs, files in os.walk(release, topdown=True, followlinks=False):
            root_path = Path(root)
            for name in dirs:
                observed_dirs.add(str((root_path / name).relative_to(release)))
            for name in files:
                observed_files.add(str((root_path / name).relative_to(release)))
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError("release tree inspection failed") from exc
    return observed_files == expected_files and observed_dirs == expected_dirs


def _release_contents_exact(
    checkout: Path,
    release: Path,
    artifacts: Sequence[tuple[Path, Path, int]],
    directories: Sequence[Path],
    *,
    uid: int,
    gid: int,
) -> bool:
    required_dirs = (release, *(release / relative for relative in directories))
    if not all(base._directory_exact(path, base.DIRECTORY_MODE, uid=uid, gid=gid) for path in required_dirs):
        return False
    desired = _desired_for(checkout, artifacts)
    for relative, data, mode in desired:
        if not base._regular_exact(release / relative, data, mode, uid=uid, gid=gid):
            return False
    return _release_tree_has_only_expected(
        release,
        [relative for relative, _, _ in desired],
        directories,
    )


def _unit_files_exact(checkout: Path, *, host_root: Path, uid: int, gid: int) -> bool:
    socket_destination = base._host_path(host_root, base.SOCKET_DESTINATION)
    service_destination = base._host_path(host_root, base.SERVICE_DESTINATION)
    return (
        base._regular_exact(
            socket_destination,
            base._read_source(checkout, base.SOCKET_SOURCE),
            base.UNIT_MODE,
            uid=uid,
            gid=gid,
        )
        and base._regular_exact(
            service_destination,
            base._read_source(checkout, base.SERVICE_SOURCE),
            base.UNIT_MODE,
            uid=uid,
            gid=gid,
        )
    )


def _legacy_filesystem_exact(
    checkout: Path,
    *,
    host_root: Path,
    uid: int,
    gid: int,
) -> bool:
    release_root = base._host_path(host_root, base.RELEASE_ROOT)
    releases_root = base._host_path(host_root, base.RELEASES_ROOT)
    current_link = base._host_path(host_root, base.CURRENT_LINK)
    legacy_release = releases_root / LEGACY_EXACT_RELEASE_SHA
    if not all(
        base._directory_exact(path, base.DIRECTORY_MODE, uid=uid, gid=gid)
        for path in (release_root, releases_root)
    ):
        return False
    try:
        releases = {entry.name for entry in releases_root.iterdir()}
        roots = {entry.name for entry in release_root.iterdir()}
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError("legacy release root inspection failed") from exc
    if releases != {LEGACY_EXACT_RELEASE_SHA} or roots != {"releases", "current"}:
        return False
    if not base._current_link_exact(current_link, LEGACY_EXACT_RELEASE_SHA, uid=uid, gid=gid):
        return False
    if not _release_contents_exact(
        checkout,
        legacy_release,
        _legacy_runtime_artifacts(),
        LEGACY_RELEASE_DIRECTORIES,
        uid=uid,
        gid=gid,
    ):
        return False
    return _unit_files_exact(checkout, host_root=host_root, uid=uid, gid=gid)


def _upgraded_filesystem_exact(
    checkout: Path,
    source_sha: str,
    *,
    host_root: Path,
    uid: int,
    gid: int,
) -> bool:
    if source_sha == LEGACY_EXACT_RELEASE_SHA:
        return False
    release_root = base._host_path(host_root, base.RELEASE_ROOT)
    releases_root = base._host_path(host_root, base.RELEASES_ROOT)
    current_link = base._host_path(host_root, base.CURRENT_LINK)
    legacy_release = releases_root / LEGACY_EXACT_RELEASE_SHA
    current_release = releases_root / source_sha
    if not all(
        base._directory_exact(path, base.DIRECTORY_MODE, uid=uid, gid=gid)
        for path in (release_root, releases_root)
    ):
        return False
    try:
        releases = {entry.name for entry in releases_root.iterdir()}
        roots = {entry.name for entry in release_root.iterdir()}
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError("upgraded release root inspection failed") from exc
    if releases != {LEGACY_EXACT_RELEASE_SHA, source_sha} or roots != {"releases", "current"}:
        return False
    if not base._current_link_exact(current_link, source_sha, uid=uid, gid=gid):
        return False
    if not _release_contents_exact(
        checkout,
        legacy_release,
        _legacy_runtime_artifacts(),
        LEGACY_RELEASE_DIRECTORIES,
        uid=uid,
        gid=gid,
    ):
        return False
    if not _release_contents_exact(
        checkout,
        current_release,
        base.runtime_artifacts(),
        base.RELEASE_DIRECTORIES,
        uid=uid,
        gid=gid,
    ):
        return False
    return _unit_files_exact(checkout, host_root=host_root, uid=uid, gid=gid)


def _filesystem_state_v2(
    checkout: Path,
    source_sha: str,
    *,
    host_root: Path,
    uid: int,
    gid: int,
) -> str:
    current = base._filesystem_state(
        checkout,
        source_sha,
        host_root=host_root,
        uid=uid,
        gid=gid,
    )
    if current in {"ABSENT", "EXACT"}:
        return current
    if _legacy_filesystem_exact(checkout, host_root=host_root, uid=uid, gid=gid):
        return "LEGACY_EXACT"
    if _upgraded_filesystem_exact(
        checkout,
        source_sha,
        host_root=host_root,
        uid=uid,
        gid=gid,
    ):
        return "EXACT"
    return "DRIFT"


def observe_bootstrap(
    checkout: Path,
    *,
    host_root: Path = Path("/"),
    uid: int = base.ROOT_UID,
    gid: int = base.ROOT_GID,
) -> BootstrapObservation:
    source_sha = validate_trusted_checkout(checkout)
    filesystem_state = _filesystem_state_v2(
        checkout,
        source_sha,
        host_root=host_root,
        uid=uid,
        gid=gid,
    )
    return BootstrapObservation(
        source_sha=source_sha,
        filesystem_state=filesystem_state,
        socket_enabled_state=base._systemctl_state("is-enabled", SOCKET_UNIT),
        socket_active_state=base._systemctl_state("is-active", SOCKET_UNIT),
    )


def plan_bootstrap(observation: BootstrapObservation) -> BootstrapPlan:
    if (
        isinstance(observation, BootstrapObservation)
        and base._SHA40_RE.fullmatch(observation.source_sha) is not None
        and observation.filesystem_state == "LEGACY_EXACT"
        and observation.socket_enabled_state == "enabled"
        and observation.socket_active_state == "active"
    ):
        return BootstrapPlan(
            schema=base.PLAN_SCHEMA,
            decision="UPGRADE_REQUIRED_EXPLICIT_LIVE",
            source_sha=observation.source_sha,
            mutations_required=UPGRADE_MUTATION_SEQUENCE,
        )
    return base.plan_bootstrap(observation)


def _publish_legacy_upgrade(checkout: Path, source_sha: str) -> None:
    if source_sha == LEGACY_EXACT_RELEASE_SHA:
        base._fail("legacy broker release cannot upgrade to itself")
    release = base.RELEASES_ROOT / source_sha
    base._mkdir_root_owned(release)
    for relative in base.RELEASE_DIRECTORIES:
        base._mkdir_root_owned(release / relative)
    for relative, data, mode in base.desired_artifact_bytes(checkout):
        base._write_root_owned(release / relative, data, mode)
    os.symlink(f"releases/{source_sha}", CURRENT_NEXT_LINK)
    os.lchown(CURRENT_NEXT_LINK, base.ROOT_UID, base.ROOT_GID)
    os.replace(CURRENT_NEXT_LINK, base.CURRENT_LINK)


def apply_bootstrap(checkout: Path) -> Mapping[str, Any]:
    if os.geteuid() != 0:
        base._fail("runner-smoke broker bootstrap requires euid 0")
    observation = observe_bootstrap(checkout)
    plan = plan_bootstrap(observation)
    if plan.decision == "ALREADY_EXACT_NO_MUTATION":
        return {
            "schema": RECEIPT_SCHEMA,
            "result": "ALREADY_EXACT_NO_MUTATION",
            "implementation_issue": IMPLEMENTATION_ISSUE,
            "checkout_isolation_issue": CHECKOUT_ISOLATION_ISSUE,
            "source_sha": plan.source_sha,
            "mutations_started": False,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
        }

    revalidated_plan = plan_bootstrap(observe_bootstrap(checkout))
    if revalidated_plan != plan:
        base._fail("runner-smoke broker bootstrap pre-mutation state drifted")

    mutation_started = False
    try:
        mutation_started = True
        if plan.decision == "INSTALL_REQUIRED_EXPLICIT_LIVE":
            base._publish_absent_state(checkout, plan.source_sha)
        elif plan.decision == "UPGRADE_REQUIRED_EXPLICIT_LIVE":
            _publish_legacy_upgrade(checkout, plan.source_sha)
        else:
            base._fail("runner-smoke broker bootstrap plan is not executable")
        final = observe_bootstrap(checkout)
        if plan_bootstrap(final).decision != "ALREADY_EXACT_NO_MUTATION":
            base._fail("post-install broker bootstrap verification did not converge to exact state")
    except Exception as exc:
        if isinstance(exc, RunnerSmokeBrokerBootstrapApplyError):
            raise
        raise RunnerSmokeBrokerBootstrapApplyError(
            "runner-smoke broker bootstrap failed closed",
            mutation_started=mutation_started,
        ) from exc
    return {
        "schema": RECEIPT_SCHEMA,
        "result": "INSTALLED_EXACT",
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "checkout_isolation_issue": CHECKOUT_ISOLATION_ISSUE,
        "source_sha": plan.source_sha,
        "mutations_started": True,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def failure_receipt(*, mutation_started: bool) -> Mapping[str, Any]:
    value = dict(base.failure_receipt(mutation_started=mutation_started))
    value["checkout_isolation_issue"] = CHECKOUT_ISOLATION_ISSUE
    return value


plan_dict = base.plan_dict
receipt_json = base.receipt_json
