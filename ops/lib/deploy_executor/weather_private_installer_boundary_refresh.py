from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
MANAGER_CHECKOUT_RESOLVER = "repo-owner-home/RPi5_main"
TRUSTED_CHECKOUT = "/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted"
ENTRYPOINT_SOURCE = "ops/bin/rpi5-weathernext-private-host-privileged-install"
ENTRYPOINT_DESTINATION = "/usr/local/sbin/rpi5-weathernext-private-host-privileged-install"
OPERATION_ID = "rpi5.weathernext-private-installer-boundary.refresh.v1"
TARGET_ALIAS = "rpi5-weathernext-private-installer-boundary-refresh"
ROLLBACK_POLICY = "NONE"
ROOT_UID = 0
ROOT_GID = 0
TRUSTED_CHECKOUT_MODE = 0o755
ENTRYPOINT_MODE = 0o755
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

MUTATION_BUDGET = (
    ("git.weathernext-private-installer-checkout-fetch", 1),
    ("git.weathernext-private-installer-trusted-checkout-advance", 1),
    ("filesystem.weathernext-private-installer-entrypoint-replace", 1),
)

BoundaryState = Literal["ABSENT", "EXACT", "STALE", "CONFLICT"]


class BoundaryRefreshError(RuntimeError):
    pass


@dataclass(frozen=True)
class BoundaryEvidence:
    exact_source_sha: str
    current_main_sha: str
    exact_main_ci_success: bool
    manager_origin: str
    manager_snapshot_stable: bool
    trusted_present: bool
    entrypoint_present: bool
    trusted_uid: int | None
    trusted_gid: int | None
    trusted_mode: int | None
    trusted_origin: str | None
    trusted_head_sha: str | None
    trusted_detached: bool
    trusted_clean: bool
    trusted_head_reviewed_ancestor: bool
    trusted_entrypoint_matches_head: bool
    installed_uid: int | None
    installed_gid: int | None
    installed_mode: int | None
    installed_entrypoint_matches_head: bool
    trusted_entrypoint_matches_exact_source: bool
    installed_entrypoint_matches_exact_source: bool


@dataclass(frozen=True)
class RefreshStep:
    category: str
    maximum: int
    target: str
    invariant: str


@dataclass(frozen=True)
class RefreshPlan:
    operation_id: str
    target_alias: str
    source_repository: str
    source_sha: str
    manager_checkout_resolver: str
    reviewed_origin: str
    trusted_checkout: str
    entrypoint_destination: str
    prior_state: BoundaryState
    steps: tuple[RefreshStep, ...]
    rollback_policy: str = ROLLBACK_POLICY
    authorization_consumed_before_first_mutation: bool = True
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False
    backend_install_allowed: bool = False
    google_action_allowed: bool = False
    bigquery_action_allowed: bool = False
    sqlite_write_allowed: bool = False


def _valid_sha(value: str | None) -> bool:
    return isinstance(value, str) and _SHA40.fullmatch(value) is not None


def classify_boundary(evidence: BoundaryEvidence) -> BoundaryState:
    if not _valid_sha(evidence.exact_source_sha):
        raise BoundaryRefreshError("exact source SHA is invalid")
    if evidence.current_main_sha != evidence.exact_source_sha:
        raise BoundaryRefreshError("source/head drifted from exact current main")
    if not evidence.exact_main_ci_success:
        raise BoundaryRefreshError("exact-main required CI is not successful")
    if evidence.manager_origin != REVIEWED_ORIGIN:
        raise BoundaryRefreshError("manager origin drifted")
    if not evidence.manager_snapshot_stable:
        raise BoundaryRefreshError("manager HEAD/index/worktree snapshot drifted")

    if not evidence.trusted_present and not evidence.entrypoint_present:
        return "ABSENT"
    if evidence.trusted_present != evidence.entrypoint_present:
        return "CONFLICT"

    structural_exact = (
        evidence.trusted_uid == ROOT_UID
        and evidence.trusted_gid == ROOT_GID
        and evidence.trusted_mode == TRUSTED_CHECKOUT_MODE
        and evidence.installed_uid == ROOT_UID
        and evidence.installed_gid == ROOT_GID
        and evidence.installed_mode == ENTRYPOINT_MODE
        and evidence.trusted_origin == REVIEWED_ORIGIN
        and evidence.trusted_detached
        and evidence.trusted_clean
        and _valid_sha(evidence.trusted_head_sha)
    )
    if not structural_exact:
        return "CONFLICT"

    if evidence.trusted_head_sha == evidence.exact_source_sha:
        if (
            evidence.trusted_entrypoint_matches_exact_source
            and evidence.installed_entrypoint_matches_exact_source
        ):
            return "EXACT"
        return "CONFLICT"

    if (
        evidence.trusted_head_reviewed_ancestor
        and evidence.trusted_entrypoint_matches_head
        and evidence.installed_entrypoint_matches_head
    ):
        return "STALE"
    return "CONFLICT"


def build_refresh_plan(evidence: BoundaryEvidence) -> RefreshPlan:
    state = classify_boundary(evidence)
    if state == "EXACT":
        return RefreshPlan(
            operation_id=OPERATION_ID,
            target_alias=TARGET_ALIAS,
            source_repository=SOURCE_REPOSITORY,
            source_sha=evidence.exact_source_sha,
            manager_checkout_resolver=MANAGER_CHECKOUT_RESOLVER,
            reviewed_origin=REVIEWED_ORIGIN,
            trusted_checkout=TRUSTED_CHECKOUT,
            entrypoint_destination=ENTRYPOINT_DESTINATION,
            prior_state=state,
            steps=(),
        )
    if state == "ABSENT":
        raise BoundaryRefreshError("boundary is absent; initial bootstrap remains the only allowed path")
    if state != "STALE":
        raise BoundaryRefreshError("installed boundary conflicts with reviewed stale-state contract")

    steps = (
        RefreshStep(
            category=MUTATION_BUDGET[0][0],
            maximum=1,
            target=MANAGER_CHECKOUT_RESOLVER,
            invariant=(
                "fetch only reviewed origin/main; fetched origin/main must equal exact current main; "
                "manager HEAD/index/worktree remains unchanged"
            ),
        ),
        RefreshStep(
            category=MUTATION_BUDGET[1][0],
            maximum=1,
            target=TRUSTED_CHECKOUT,
            invariant=(
                "advance only the fixed clean detached trusted checkout from its reviewed ancestor "
                "to the exact source SHA; no reset/clean/pull/merge/rebase/branch switch"
            ),
        ),
        RefreshStep(
            category=MUTATION_BUDGET[2][0],
            maximum=1,
            target=ENTRYPOINT_DESTINATION,
            invariant=(
                "replace only the fixed root-owned 0755 entrypoint after its preimage matches the "
                "reviewed stale checkout; postimage must equal the exact-source reviewed blob"
            ),
        ),
    )
    return RefreshPlan(
        operation_id=OPERATION_ID,
        target_alias=TARGET_ALIAS,
        source_repository=SOURCE_REPOSITORY,
        source_sha=evidence.exact_source_sha,
        manager_checkout_resolver=MANAGER_CHECKOUT_RESOLVER,
        reviewed_origin=REVIEWED_ORIGIN,
        trusted_checkout=TRUSTED_CHECKOUT,
        entrypoint_destination=ENTRYPOINT_DESTINATION,
        prior_state=state,
        steps=steps,
    )


def public_plan(plan: RefreshPlan) -> dict[str, object]:
    return {
        "operation_id": plan.operation_id,
        "target_alias": plan.target_alias,
        "source_repository": plan.source_repository,
        "source_sha": plan.source_sha,
        "manager_checkout_resolver": plan.manager_checkout_resolver,
        "reviewed_origin": plan.reviewed_origin,
        "trusted_checkout": plan.trusted_checkout,
        "entrypoint_destination": plan.entrypoint_destination,
        "prior_state": plan.prior_state,
        "mutation_budget": [
            {"category": step.category, "max_operations": step.maximum}
            for step in plan.steps
        ],
        "rollback_policy": plan.rollback_policy,
        "authorization_consumed_before_first_mutation": plan.authorization_consumed_before_first_mutation,
        "automatic_retry": plan.automatic_retry,
        "automatic_cleanup": plan.automatic_cleanup,
        "automatic_rollback": plan.automatic_rollback,
        "backend_install_allowed": plan.backend_install_allowed,
        "google_action_allowed": plan.google_action_allowed,
        "bigquery_action_allowed": plan.bigquery_action_allowed,
        "sqlite_write_allowed": plan.sqlite_write_allowed,
    }
