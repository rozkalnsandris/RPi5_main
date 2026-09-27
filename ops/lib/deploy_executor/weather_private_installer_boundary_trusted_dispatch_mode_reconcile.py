from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
TRUSTED_CHECKOUT = "/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted"
KNOWN_STALE_HEAD = "79372e48ac53bf6d00142578b6543bc33a72a692"
TRUSTED_DISPATCH_RELATIVE = "ops/lib/deploy_executor/weather_private_privileged_dispatch.py"
TRUSTED_DISPATCH_GIT_MODE = "100644"
TRUSTED_DISPATCH_GIT_BLOB = "98218e3138f821390bece6dc10b770bd0b578cd9"
ROOT_UID = 0
ROOT_GID = 0
RESTRICTIVE_MODE = 0o600
EXACT_MODE = 0o644
OPERATION_ID = "rpi5.weathernext-private-installer-boundary.trusted-dispatch-mode-reconcile.v1"
TARGET_ALIAS = "rpi5-weathernext-private-installer-boundary-trusted-dispatch-mode-reconcile"
MUTATION_CATEGORY = "filesystem.weathernext-private-installer-boundary-trusted-dispatch-mode-reconcile"
MAX_MUTATIONS = 1
ROLLBACK_POLICY = "NONE"

ModeState = Literal["EXACT", "RESTRICTIVE", "CONFLICT"]


class TrustedDispatchModeReconcileError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrustedDispatchEvidence:
    source_sha: str
    current_main_sha: str
    exact_main_ci_success: bool
    trusted_present: bool
    trusted_origin: str
    trusted_head: str
    trusted_clean: bool
    trusted_detached: bool
    dispatch_present: bool
    dispatch_regular: bool
    dispatch_symlink: bool
    dispatch_nlink: int
    dispatch_uid: int
    dispatch_gid: int
    dispatch_fs_mode: int
    dispatch_git_mode: str
    dispatch_git_blob: str
    dispatch_content_blob: str


@dataclass(frozen=True)
class ModeStep:
    category: str
    relative_path: str
    from_mode: int
    to_mode: int


@dataclass(frozen=True)
class ModePlan:
    operation_id: str
    target_alias: str
    source_sha: str
    prior_state: ModeState
    steps: tuple[ModeStep, ...]
    rollback_policy: str = ROLLBACK_POLICY
    authorization_consumed_before_first_mutation: bool = True
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False


def classify(evidence: TrustedDispatchEvidence) -> ModeState:
    if evidence.source_sha != evidence.current_main_sha:
        raise TrustedDispatchModeReconcileError("source SHA is not exact current main")
    if not evidence.exact_main_ci_success:
        raise TrustedDispatchModeReconcileError("exact-main CI is not successful")
    if (
        not evidence.trusted_present
        or evidence.trusted_origin != REVIEWED_ORIGIN
        or evidence.trusted_head != KNOWN_STALE_HEAD
        or not evidence.trusted_clean
        or not evidence.trusted_detached
    ):
        raise TrustedDispatchModeReconcileError("trusted stale boundary identity drifted")
    if (
        not evidence.dispatch_present
        or not evidence.dispatch_regular
        or evidence.dispatch_symlink
        or evidence.dispatch_nlink != 1
        or evidence.dispatch_uid != ROOT_UID
        or evidence.dispatch_gid != ROOT_GID
        or evidence.dispatch_git_mode != TRUSTED_DISPATCH_GIT_MODE
        or evidence.dispatch_git_blob != TRUSTED_DISPATCH_GIT_BLOB
        or evidence.dispatch_content_blob != TRUSTED_DISPATCH_GIT_BLOB
    ):
        return "CONFLICT"
    if evidence.dispatch_fs_mode == EXACT_MODE:
        return "EXACT"
    if evidence.dispatch_fs_mode == RESTRICTIVE_MODE:
        return "RESTRICTIVE"
    return "CONFLICT"


def build_plan(evidence: TrustedDispatchEvidence) -> ModePlan:
    state = classify(evidence)
    if state == "CONFLICT":
        raise TrustedDispatchModeReconcileError("trusted dispatch mode state conflicts with reviewed identity")
    if state == "EXACT":
        return ModePlan(OPERATION_ID, TARGET_ALIAS, evidence.source_sha, state, ())
    steps = (
        ModeStep(
            MUTATION_CATEGORY,
            TRUSTED_DISPATCH_RELATIVE,
            RESTRICTIVE_MODE,
            EXACT_MODE,
        ),
    )
    if len(steps) != MAX_MUTATIONS:
        raise TrustedDispatchModeReconcileError("trusted dispatch mutation budget drifted")
    return ModePlan(OPERATION_ID, TARGET_ALIAS, evidence.source_sha, state, steps)


def public_plan(plan: ModePlan) -> dict[str, object]:
    return {
        "operation_id": plan.operation_id,
        "target_alias": plan.target_alias,
        "source_sha": plan.source_sha,
        "prior_state": plan.prior_state,
        "mutation_budget": (
            [{"category": MUTATION_CATEGORY, "max_operations": MAX_MUTATIONS}]
            if plan.steps
            else []
        ),
        "targets": [
            {
                "relative_path": step.relative_path,
                "from_mode": format(step.from_mode, "04o"),
                "to_mode": format(step.to_mode, "04o"),
            }
            for step in plan.steps
        ],
        "rollback_policy": plan.rollback_policy,
        "authorization_consumed_before_first_mutation": plan.authorization_consumed_before_first_mutation,
        "automatic_retry": plan.automatic_retry,
        "automatic_cleanup": plan.automatic_cleanup,
        "automatic_rollback": plan.automatic_rollback,
    }
