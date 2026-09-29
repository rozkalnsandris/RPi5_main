from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
MANAGER_CHECKOUT_RESOLVER = "repo-owner-home/RPi5_main"
REACHABILITY_ISSUE = 768
MANAGER_SYNC_OPERATION_ID = "rpi5.weathernext-private-installer-manager-source-sync.v1"
MANAGER_SYNC_TARGET_ALIAS = "rpi5-weathernext-private-installer-manager-source-sync"
BOUNDARY_REFRESH_OPERATION_ID = "rpi5.weathernext-private-installer-boundary.refresh.v1"
BOOTSTRAP_RECONCILE_OPERATION_ID = (
    "rpi5.weathernext-private-installer-boundary-bootstrap.reconcile.v1"
)
INSTALLED_BOOTSTRAP = "/usr/local/sbin/rpi5-weathernext-private-installer-boundary-bootstrap"
INSTALLED_PRIVILEGED_DISPATCH = "/usr/local/sbin/rpi5-weathernext-private-host-privileged-install"
PRIVILEGED_DISPATCH_SOURCE = "ops/bin/rpi5-weathernext-private-host-privileged-install"
ROLLBACK_POLICY = "NONE"
LIVE_GATE = "COMPOSITE_LIVE_REQUIRED"
MANAGER_FETCH_ARGV = (
    "/usr/bin/git",
    "fetch",
    "--no-tags",
    "origin",
    "refs/heads/main:refs/remotes/origin/main",
)
MANAGER_FAST_FORWARD_ARGV = (
    "/usr/bin/git",
    "merge",
    "--ff-only",
    "refs/remotes/origin/main",
)
MANAGER_SYNC_MUTATION_BUDGET = (
    ("git.rpi5-main-manager-checkout-fetch", 1),
    ("git.rpi5-main-manager-checkout-fast-forward", 1),
)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

ReachabilityDecision = Literal[
    "MANAGER_SYNC_REQUIRED",
    "BOUNDARY_REFRESH_REQUIRED",
    "RECONCILE_REACHABLE",
]


class BootstrapReachabilityContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootstrapReachabilityEvidence:
    exact_source_sha: str
    current_main_sha: str
    exact_main_ci_success: bool
    manager_head_sha: str
    manager_origin: str
    manager_clean: bool
    manager_head_reviewed_ancestor: bool
    manager_runtime_pair_exact_current: bool
    installed_bootstrap_recognized: bool
    installed_privileged_dispatch_exact_current: bool
    installed_privileged_dispatch_reconcile_route: bool


@dataclass(frozen=True)
class ManagerSyncStep:
    category: str
    maximum: int
    argv: tuple[str, ...]
    invariant: str


@dataclass(frozen=True)
class BootstrapReachabilityPlan:
    decision: ReachabilityDecision
    exact_source_sha: str
    next_operation_id: str
    execution_entrypoint: str | None
    manager_checkout_resolver: str
    steps: tuple[ManagerSyncStep, ...]
    live_gate: str = LIVE_GATE
    rollback_policy: str = ROLLBACK_POLICY
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False


def _fail(message: str) -> None:
    raise BootstrapReachabilityContractError(message)


def _valid_sha(value: str) -> bool:
    return isinstance(value, str) and _SHA40.fullmatch(value) is not None


def build_reachability_plan(
    evidence: BootstrapReachabilityEvidence,
) -> BootstrapReachabilityPlan:
    if not _valid_sha(evidence.exact_source_sha):
        _fail("exact source SHA is invalid")
    if evidence.current_main_sha != evidence.exact_source_sha:
        _fail("current main drifted from exact source")
    if not evidence.exact_main_ci_success:
        _fail("exact-main required CI is not successful")
    if not _valid_sha(evidence.manager_head_sha):
        _fail("manager HEAD is invalid")
    if evidence.manager_origin != REVIEWED_ORIGIN:
        _fail("manager origin drifted")
    if not evidence.manager_clean:
        _fail("manager checkout is not clean")
    if evidence.installed_privileged_dispatch_reconcile_route and not evidence.installed_privileged_dispatch_exact_current:
        _fail("reconcile route provenance is not exact-current")
    if evidence.installed_privileged_dispatch_exact_current:
        if not evidence.installed_privileged_dispatch_reconcile_route:
            _fail("exact-current privileged dispatch lacks reconcile route")
        return BootstrapReachabilityPlan(
            decision="RECONCILE_REACHABLE",
            exact_source_sha=evidence.exact_source_sha,
            next_operation_id=BOOTSTRAP_RECONCILE_OPERATION_ID,
            execution_entrypoint=INSTALLED_PRIVILEGED_DISPATCH,
            manager_checkout_resolver=MANAGER_CHECKOUT_RESOLVER,
            steps=(),
        )

    if not evidence.installed_bootstrap_recognized:
        _fail("installed bootstrap provenance is not recognized")

    if evidence.manager_runtime_pair_exact_current:
        return BootstrapReachabilityPlan(
            decision="BOUNDARY_REFRESH_REQUIRED",
            exact_source_sha=evidence.exact_source_sha,
            next_operation_id=BOUNDARY_REFRESH_OPERATION_ID,
            execution_entrypoint=INSTALLED_BOOTSTRAP,
            manager_checkout_resolver=MANAGER_CHECKOUT_RESOLVER,
            steps=(),
        )

    if evidence.manager_head_sha == evidence.exact_source_sha:
        _fail("exact-current manager checkout has drifted refresh runtime pair")
    if not evidence.manager_head_reviewed_ancestor:
        _fail("manager HEAD is not a reviewed ancestor of exact current source")

    steps = (
        ManagerSyncStep(
            category=MANAGER_SYNC_MUTATION_BUDGET[0][0],
            maximum=1,
            argv=MANAGER_FETCH_ARGV,
            invariant=(
                "fetch only reviewed origin/main into refs/remotes/origin/main; fetched ref must "
                "equal exact current main before fast-forward"
            ),
        ),
        ManagerSyncStep(
            category=MANAGER_SYNC_MUTATION_BUDGET[1][0],
            maximum=1,
            argv=MANAGER_FAST_FORWARD_ARGV,
            invariant=(
                "fast-forward only the clean fixed manager checkout to the already verified "
                "origin/main; no reset rebase clean force pull or branch switch"
            ),
        ),
    )
    return BootstrapReachabilityPlan(
        decision="MANAGER_SYNC_REQUIRED",
        exact_source_sha=evidence.exact_source_sha,
        next_operation_id=MANAGER_SYNC_OPERATION_ID,
        execution_entrypoint=None,
        manager_checkout_resolver=MANAGER_CHECKOUT_RESOLVER,
        steps=steps,
    )


def public_plan(plan: BootstrapReachabilityPlan) -> dict[str, object]:
    return {
        "decision": plan.decision,
        "exact_source_sha": plan.exact_source_sha,
        "next_operation_id": plan.next_operation_id,
        "execution_entrypoint": plan.execution_entrypoint,
        "manager_checkout_resolver": plan.manager_checkout_resolver,
        "mutation_budget": [
            {
                "category": step.category,
                "max_operations": step.maximum,
                "argv": list(step.argv),
                "invariant": step.invariant,
            }
            for step in plan.steps
        ],
        "live_gate": plan.live_gate,
        "rollback_policy": plan.rollback_policy,
        "automatic_retry": plan.automatic_retry,
        "automatic_cleanup": plan.automatic_cleanup,
        "automatic_rollback": plan.automatic_rollback,
    }
