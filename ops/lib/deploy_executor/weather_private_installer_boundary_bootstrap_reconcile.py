from __future__ import annotations

from dataclasses import dataclass
import re
import stat
from typing import Literal

SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
SOURCE_PATH = "ops/bin/rpi5-weathernext-private-installer-boundary-bootstrap"
DESTINATION = "/usr/local/sbin/rpi5-weathernext-private-installer-boundary-bootstrap"
OPERATION_ID = "rpi5.weathernext-private-installer-boundary-bootstrap.reconcile.v1"
TARGET_ALIAS = "rpi5-weathernext-private-installer-boundary-bootstrap-reconcile"
BASELINE_RESOLVER_ID = "rpi5.weathernext-private-installer-boundary-bootstrap.fixed-state-v1"
ROLLBACK_POLICY = "NONE"
ROOT_UID = 0
ROOT_GID = 0
DESTINATION_MODE = 0o755
CURRENT_SOURCE_GIT_BLOB = "1b1e1c47c7ed142b0429816564c124f3896ad54a"
CURRENT_SOURCE_SHA256 = "3db256238a2c5144ba8299ee52b4aaa4efd995b241e186e0fcf7eea3e040f590"
RECOGNIZED_PREDECESSOR_SHA256 = "7ddf7d6ca0537592fc55b48e576be006ca144becf8e0d3f8ae67fd20c8e5b9c2"
MUTATION_BUDGET = (("filesystem.weathernext-private-installer-boundary-bootstrap-reconcile", 1),)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

InstalledState = Literal["EXACT", "RECOGNIZED_PREDECESSOR", "CONFLICT"]


class BootstrapReconcileError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootstrapEvidence:
    exact_source_sha: str
    current_main_sha: str
    exact_main_ci_success: bool
    source_git_blob: str
    source_sha256: str
    installed_is_regular: bool
    installed_uid: int
    installed_gid: int
    installed_mode: int
    installed_nlink: int
    installed_sha256: str


@dataclass(frozen=True)
class ReconcileStep:
    category: str
    maximum: int
    target: str
    invariant: str


@dataclass(frozen=True)
class ReconcilePlan:
    operation_id: str
    target_alias: str
    source_repository: str
    source_sha: str
    source_path: str
    source_git_blob: str
    source_sha256: str
    destination: str
    prior_state: InstalledState
    steps: tuple[ReconcileStep, ...]
    rollback_policy: str = ROLLBACK_POLICY
    authorization_consumed_before_first_mutation: bool = True
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False
    installer_boundary_refresh_allowed: bool = False
    backend_or_application_mutation_allowed: bool = False
    google_action_allowed: bool = False
    sqlite_write_allowed: bool = False
    docker_or_systemd_allowed: bool = False


def _fail(message: str) -> None:
    raise BootstrapReconcileError(message)


def _valid_sha40(value: str) -> bool:
    return isinstance(value, str) and _SHA40.fullmatch(value) is not None


def _valid_sha256(value: str) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def classify_installed(evidence: BootstrapEvidence) -> InstalledState:
    if not _valid_sha40(evidence.exact_source_sha):
        _fail("exact source SHA is invalid")
    if evidence.current_main_sha != evidence.exact_source_sha:
        _fail("source/head drifted from exact current main")
    if not evidence.exact_main_ci_success:
        _fail("exact-main required CI is not successful")
    if evidence.source_git_blob != CURRENT_SOURCE_GIT_BLOB:
        _fail("reviewed bootstrap Git blob drifted")
    if evidence.source_sha256 != CURRENT_SOURCE_SHA256:
        _fail("reviewed bootstrap source bytes drifted")
    if not _valid_sha256(evidence.installed_sha256):
        _fail("installed bootstrap digest is invalid")
    if not evidence.installed_is_regular:
        return "CONFLICT"
    if (
        evidence.installed_uid != ROOT_UID
        or evidence.installed_gid != ROOT_GID
        or evidence.installed_mode != DESTINATION_MODE
        or evidence.installed_nlink != 1
    ):
        return "CONFLICT"
    if evidence.installed_sha256 == CURRENT_SOURCE_SHA256:
        return "EXACT"
    if evidence.installed_sha256 == RECOGNIZED_PREDECESSOR_SHA256:
        return "RECOGNIZED_PREDECESSOR"
    return "CONFLICT"


def build_reconcile_plan(evidence: BootstrapEvidence) -> ReconcilePlan:
    state = classify_installed(evidence)
    if state == "CONFLICT":
        _fail("installed bootstrap is not an exact recognized preimage")
    steps: tuple[ReconcileStep, ...] = ()
    if state == "RECOGNIZED_PREDECESSOR":
        steps = (
            ReconcileStep(
                category=MUTATION_BUDGET[0][0],
                maximum=1,
                target=DESTINATION,
                invariant=(
                    "replace only the fixed root-owned 0755 one-link regular bootstrap when its "
                    "preimage SHA-256 equals the reviewed predecessor; postimage must equal the "
                    "fixed reviewed Git blob and SHA-256"
                ),
            ),
        )
    return ReconcilePlan(
        operation_id=OPERATION_ID,
        target_alias=TARGET_ALIAS,
        source_repository=SOURCE_REPOSITORY,
        source_sha=evidence.exact_source_sha,
        source_path=SOURCE_PATH,
        source_git_blob=CURRENT_SOURCE_GIT_BLOB,
        source_sha256=CURRENT_SOURCE_SHA256,
        destination=DESTINATION,
        prior_state=state,
        steps=steps,
    )


def public_plan(plan: ReconcilePlan) -> dict[str, object]:
    return {
        "operation_id": plan.operation_id,
        "target_alias": plan.target_alias,
        "source_repository": plan.source_repository,
        "source_sha": plan.source_sha,
        "source_path": plan.source_path,
        "source_git_blob": plan.source_git_blob,
        "source_sha256": plan.source_sha256,
        "destination": plan.destination,
        "prior_state": plan.prior_state,
        "mutation_budget": [
            {"category": item.category, "max_operations": item.maximum}
            for item in plan.steps
        ],
        "rollback_policy": plan.rollback_policy,
        "authorization_consumed_before_first_mutation": plan.authorization_consumed_before_first_mutation,
        "automatic_retry": plan.automatic_retry,
        "automatic_cleanup": plan.automatic_cleanup,
        "automatic_rollback": plan.automatic_rollback,
        "installer_boundary_refresh_allowed": plan.installer_boundary_refresh_allowed,
        "backend_or_application_mutation_allowed": plan.backend_or_application_mutation_allowed,
        "google_action_allowed": plan.google_action_allowed,
        "sqlite_write_allowed": plan.sqlite_write_allowed,
        "docker_or_systemd_allowed": plan.docker_or_systemd_allowed,
    }


def metadata_is_fixed_regular(st_mode: int, uid: int, gid: int, nlink: int) -> bool:
    return (
        stat.S_ISREG(st_mode)
        and not stat.S_ISLNK(st_mode)
        and stat.S_IMODE(st_mode) == DESTINATION_MODE
        and uid == ROOT_UID
        and gid == ROOT_GID
        and nlink == 1
    )
