from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
SOURCE_ANCHOR = "b4374e735ef0e5d6efa26acee85669de5433cb67"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
MANAGER_CHECKOUT_RESOLVER = "repo-owner-home/RPi5_main"
TRUSTED_CHECKOUT = "/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted"
KNOWN_STALE_HEAD = "79372e48ac53bf6d00142578b6543bc33a72a692"
OPERATION_ID = "rpi5.weathernext-private-installer-boundary.mode-reconcile.v1"
TARGET_ALIAS = "rpi5-weathernext-private-installer-boundary-mode-reconcile"
MUTATION_CATEGORY = "filesystem.weathernext-private-installer-boundary-mode-reconcile"
MAX_MUTATIONS = 3
ROLLBACK_POLICY = "NONE"

ModeState = Literal["EXACT", "RESTRICTIVE", "CONFLICT"]


class ModeReconcileError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileSpec:
    key: str
    scope: Literal["manager", "trusted"]
    relative_path: str
    owner_class: Literal["manager", "root"]
    git_mode: str
    git_blob: str
    restrictive_mode: int
    exact_mode: int


FILE_SPECS = (
    FileSpec(
        key="runtime_adapter",
        scope="manager",
        relative_path="ops/bin/rpi5-weathernext-private-installer-boundary-refresh-runtime",
        owner_class="manager",
        git_mode="100755",
        git_blob="b9e607dfcfdaec9dbd138dd16c41588c5e65dd0b",
        restrictive_mode=0o700,
        exact_mode=0o755,
    ),
    FileSpec(
        key="runtime_module",
        scope="manager",
        relative_path="ops/lib/deploy_executor/weather_private_installer_boundary_refresh_runtime.py",
        owner_class="manager",
        git_mode="100644",
        git_blob="4fa33b16a87bc6e0f1eb495067d8ad689057292e",
        restrictive_mode=0o600,
        exact_mode=0o644,
    ),
    FileSpec(
        key="stale_dispatch",
        scope="trusted",
        relative_path="ops/lib/deploy_executor/weather_private_privileged_dispatch.py",
        owner_class="root",
        git_mode="100644",
        git_blob="98218e3138f821390bece6dc10b770bd0b578cd9",
        restrictive_mode=0o600,
        exact_mode=0o644,
    ),
)


@dataclass(frozen=True)
class FileEvidence:
    key: str
    present: bool
    regular: bool
    symlink: bool
    nlink: int
    owner_class: str
    fs_mode: int
    git_mode: str
    git_blob: str
    content_blob: str


@dataclass(frozen=True)
class ModeEvidence:
    source_sha: str
    current_main_sha: str
    exact_main_ci_success: bool
    manager_origin: str
    manager_clean: bool
    manager_snapshot_stable: bool
    trusted_origin: str
    trusted_head: str
    trusted_clean: bool
    trusted_detached: bool
    files: tuple[FileEvidence, ...]


@dataclass(frozen=True)
class ModeStep:
    category: str
    target_key: str
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


def _by_key(evidence: ModeEvidence) -> Mapping[str, FileEvidence]:
    values = {item.key: item for item in evidence.files}
    if len(values) != len(evidence.files) or set(values) != {item.key for item in FILE_SPECS}:
        raise ModeReconcileError("fixed mode-reconcile file set drifted")
    return values


def classify(evidence: ModeEvidence) -> ModeState:
    if evidence.source_sha != evidence.current_main_sha:
        raise ModeReconcileError("source SHA is not exact current main")
    if not evidence.exact_main_ci_success:
        raise ModeReconcileError("exact-main CI is not successful")
    if evidence.manager_origin != REVIEWED_ORIGIN or not evidence.manager_clean or not evidence.manager_snapshot_stable:
        raise ModeReconcileError("manager checkout identity drifted")
    if (
        evidence.trusted_origin != REVIEWED_ORIGIN
        or evidence.trusted_head != KNOWN_STALE_HEAD
        or not evidence.trusted_clean
        or not evidence.trusted_detached
    ):
        raise ModeReconcileError("trusted stale boundary identity drifted")

    observed = _by_key(evidence)
    states: list[ModeState] = []
    for spec in FILE_SPECS:
        item = observed[spec.key]
        if (
            not item.present
            or not item.regular
            or item.symlink
            or item.nlink != 1
            or item.owner_class != spec.owner_class
            or item.git_mode != spec.git_mode
            or item.git_blob != spec.git_blob
            or item.content_blob != spec.git_blob
        ):
            return "CONFLICT"
        if item.fs_mode == spec.exact_mode:
            states.append("EXACT")
        elif item.fs_mode == spec.restrictive_mode:
            states.append("RESTRICTIVE")
        else:
            return "CONFLICT"

    if all(state == "EXACT" for state in states):
        return "EXACT"
    if all(state == "RESTRICTIVE" for state in states):
        return "RESTRICTIVE"
    return "CONFLICT"


def build_plan(evidence: ModeEvidence) -> ModePlan:
    state = classify(evidence)
    if state == "CONFLICT":
        raise ModeReconcileError("mixed or conflicting mode-reconcile state")
    if state == "EXACT":
        return ModePlan(OPERATION_ID, TARGET_ALIAS, evidence.source_sha, state, ())
    steps = tuple(
        ModeStep(MUTATION_CATEGORY, spec.key, spec.restrictive_mode, spec.exact_mode)
        for spec in FILE_SPECS
    )
    if len(steps) != MAX_MUTATIONS:
        raise ModeReconcileError("mode-reconcile mutation budget drifted")
    return ModePlan(OPERATION_ID, TARGET_ALIAS, evidence.source_sha, state, steps)


def public_plan(plan: ModePlan) -> dict[str, object]:
    return {
        "operation_id": plan.operation_id,
        "target_alias": plan.target_alias,
        "source_sha": plan.source_sha,
        "prior_state": plan.prior_state,
        "mutation_budget": [
            {"category": MUTATION_CATEGORY, "max_operations": MAX_MUTATIONS}
        ] if plan.steps else [],
        "targets": [
            {
                "key": step.target_key,
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
