from __future__ import annotations

import os

from . import dashboard_bootstrap_contract as c
from . import dashboard_bootstrap_fs as fs

BOOTSTRAP_ACK = c.BOOTSTRAP_ACK
DashboardBootstrapError = c.DashboardBootstrapError
BootstrapPaths = c.BootstrapPaths
BootstrapReceipt = c.BootstrapReceipt
DashboardHardenedControllerBootstrapAdapter = c.DashboardHardenedControllerBootstrapAdapter


def _validate_inputs(expected_current: str, expected_candidate_sha256: str, acknowledgement: str) -> None:
    if os.geteuid() != c.ROOT_UID:
        raise c.DashboardBootstrapError("Dashboard bootstrap must run as root through the reviewed helper")
    if acknowledgement != c.BOOTSTRAP_ACK:
        raise c.DashboardBootstrapError("Dashboard bootstrap owner acknowledgement mismatch")
    if fs.FULL_SHA.fullmatch(expected_current) is None:
        raise c.DashboardBootstrapError("expected current SHA is invalid")
    if expected_current == c.SOURCE_SHA:
        raise c.DashboardBootstrapError("bootstrap is already satisfied; normal P10 controller path must be used")
    if fs.SHA256.fullmatch(expected_candidate_sha256) is None:
        raise c.DashboardBootstrapError("expected candidate digest is invalid")


def _read_only_gate(paths: c.BootstrapPaths, expected_current: str, expected_candidate_sha256: str) -> c.CandidateManifest:
    manifest = fs.load_candidate(paths, expected_candidate_sha256)
    fs.verify_candidate(paths, manifest)
    fs.verify_current(paths, expected_current, c.HISTORICAL_CONTROLLER_BLOB)
    fs.require_target_absent(paths)
    return manifest


def apply_bootstrap(
    *,
    expected_current: str,
    expected_candidate_sha256: str,
    acknowledgement: str,
    paths: c.BootstrapPaths = c.BootstrapPaths(),
) -> c.BootstrapReceipt:
    """Cross the one historical->hardened Dashboard controller boundary exactly once.

    Source existence or merge does not authorize calling this function on a host.
    A separate LIVE/root authorization must bind expected_current and candidate digest.
    """

    _validate_inputs(expected_current, expected_candidate_sha256, acknowledgement)
    _read_only_gate(paths, expected_current, expected_candidate_sha256)

    lock_fd = fs.acquire_lock(paths)
    state = fs.MutationState()
    operation_error: BaseException | None = None
    try:
        manifest = _read_only_gate(paths, expected_current, expected_candidate_sha256)
        fs.materialize(paths, manifest, state)

        root = fs.open_abs_dir(paths.production_root, "production root")
        try:
            releases = os.open("releases", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            try:
                installed = fs.verify_release(releases, c.SOURCE_SHA, c.HARDENED_CONTROLLER_BLOB)
                if installed.candidate_sha256 != expected_candidate_sha256:
                    raise c.DashboardBootstrapError("installed candidate digest mismatch")
            finally:
                os.close(releases)
        finally:
            os.close(root)

        fs.verify_current(paths, expected_current, c.HISTORICAL_CONTROLLER_BLOB)
        fs.swap_current(paths, state)
        fs.verify_current(paths, c.SOURCE_SHA, c.HARDENED_CONTROLLER_BLOB)
    except BaseException as exc:
        operation_error = exc

    close_error: BaseException | None = None
    try:
        os.close(lock_fd)
    except BaseException as exc:
        close_error = exc

    if operation_error is not None and state.release_started:
        raise c.DashboardBootstrapError(
            "Dashboard bootstrap failed after release mutation started; apply lock and partial evidence are preserved"
        ) from operation_error
    if close_error is not None and state.release_started:
        raise c.DashboardBootstrapError(
            "Dashboard bootstrap completed mutation but apply lock close failed; lock is preserved"
        ) from close_error

    unlink_error: BaseException | None = None
    try:
        fs.remove_lock(paths)
    except BaseException as exc:
        unlink_error = exc

    if operation_error is not None:
        if close_error is not None or unlink_error is not None:
            raise c.DashboardBootstrapError(
                "Dashboard bootstrap failed before release mutation and transient lock cleanup was incomplete"
            ) from operation_error
        raise operation_error
    if close_error is not None:
        raise c.DashboardBootstrapError("Dashboard bootstrap lock close failed") from close_error
    if unlink_error is not None:
        raise c.DashboardBootstrapError(
            "Dashboard bootstrap succeeded but apply lock cleanup failed; explicit review required"
        ) from unlink_error

    return c.BootstrapReceipt(
        status="BOOTSTRAP_APPLIED",
        source_sha=c.SOURCE_SHA,
        previous_release=expected_current,
        current_release=c.SOURCE_SHA,
        candidate_sha256=expected_candidate_sha256,
        historical_controller_blob=c.HISTORICAL_CONTROLLER_BLOB,
        hardened_controller_blob=c.HARDENED_CONTROLLER_BLOB,
        releases_deleted=0,
        p10_apply_executed=False,
    )
