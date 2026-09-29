from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
MANAGER_CHECKOUT_RESOLVER = "repo-owner-home/RPi5_main"
MANAGER_BRANCH_REF = "refs/heads/main"
MANAGER_DETACHED_REF = "DETACHED"
REACHABILITY_ISSUE = 770
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
GIT_FIXED_CONFIG = (
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "credential.helper=",
    "-c",
    "protocol.file.allow=never",
)
MANAGER_SYNC_FIXED_ENV = (
    ("PATH", "/usr/bin:/bin"),
    ("LANG", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
    ("GIT_TERMINAL_PROMPT", "0"),
    ("GIT_CONFIG_NOSYSTEM", "1"),
    ("GIT_CONFIG_GLOBAL", "/dev/null"),
)
MANAGER_FETCH_ARGV = (
    "/usr/bin/git",
    *GIT_FIXED_CONFIG,
    "fetch",
    "--no-tags",
    "origin",
    "refs/heads/main:refs/remotes/origin/main",
)
MANAGER_SWITCH_MAIN_ARGV = (
    "/usr/bin/git",
    *GIT_FIXED_CONFIG,
    "switch",
    "main",
)
MANAGER_FAST_FORWARD_ARGV = (
    "/usr/bin/git",
    *GIT_FIXED_CONFIG,
    "merge",
    "--ff-only",
    "refs/remotes/origin/main",
)
MANAGER_SYNC_MUTATION_BUDGET = (
    ("git.rpi5-main-manager-checkout-fetch", 1),
    ("git.rpi5-main-manager-checkout-switch-main", 1),
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
    manager_branch_ref: str
    manager_local_main_sha: str
    manager_origin: str
    manager_clean: bool
    manager_head_reviewed_ancestor: bool
    manager_local_main_reviewed_ancestor_of_head: bool
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
    manager_branch_ref: str
    fixed_environment: tuple[tuple[str, str], ...]
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


def _manager_sync_steps(*, detached: bool) -> tuple[ManagerSyncStep, ...]:
    steps: list[ManagerSyncStep] = [
        ManagerSyncStep(
            category=MANAGER_SYNC_MUTATION_BUDGET[0][0],
            maximum=1,
            argv=MANAGER_FETCH_ARGV,
            invariant=(
                "fetch only reviewed origin/main into refs/remotes/origin/main; fetched ref must "
                "equal exact current main before any branch attachment or fast-forward"
            ),
        )
    ]
    if detached:
        steps.append(
            ManagerSyncStep(
                category=MANAGER_SYNC_MUTATION_BUDGET[1][0],
                maximum=1,
                argv=MANAGER_SWITCH_MAIN_ARGV,
                invariant=(
                    "after fetch, local refs/heads/main must remain a reviewed ancestor of the "
                    "detached reviewed HEAD and that HEAD must remain a reviewed ancestor of exact "
                    "current main; switch only to literal local branch main with hooks disabled"
                ),
            )
        )
    steps.append(
        ManagerSyncStep(
            category=MANAGER_SYNC_MUTATION_BUDGET[2][0],
            maximum=1,
            argv=MANAGER_FAST_FORWARD_ARGV,
            invariant=(
                "after fetched ref equals exact current main and HEAD is attached to fixed main, "
                "fast-forward only to refs/remotes/origin/main; reset rebase clean pull force or "
                "any other branch switch remain forbidden"
            ),
        )
    )
    return tuple(steps)


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
    if not _valid_sha(evidence.manager_local_main_sha):
        _fail("manager local main ref is invalid")
    if evidence.manager_branch_ref not in {MANAGER_BRANCH_REF, MANAGER_DETACHED_REF}:
        _fail("manager checkout is neither fixed main nor reviewed detached state")
    if evidence.manager_origin != REVIEWED_ORIGIN:
        _fail("manager origin drifted")
    if not evidence.manager_clean:
        _fail("manager checkout is not clean")
    if evidence.installed_privileged_dispatch_reconcile_route and not evidence.installed_privileged_dispatch_exact_current:
        _fail("reconcile route provenance is not exact-current")

    detached = evidence.manager_branch_ref == MANAGER_DETACHED_REF
    if detached:
        if evidence.manager_local_main_sha == evidence.manager_head_sha:
            _fail("detached manager HEAD unexpectedly equals local main")
        if not evidence.manager_local_main_reviewed_ancestor_of_head:
            _fail("local main is not a reviewed ancestor of detached manager HEAD")
        if not evidence.manager_head_reviewed_ancestor:
            _fail("detached manager HEAD is not a reviewed ancestor of exact current source")
        if not evidence.installed_bootstrap_recognized:
            _fail("installed bootstrap provenance is not recognized")
        return BootstrapReachabilityPlan(
            decision="MANAGER_SYNC_REQUIRED",
            exact_source_sha=evidence.exact_source_sha,
            next_operation_id=MANAGER_SYNC_OPERATION_ID,
            execution_entrypoint=None,
            manager_checkout_resolver=MANAGER_CHECKOUT_RESOLVER,
            manager_branch_ref=MANAGER_BRANCH_REF,
            fixed_environment=MANAGER_SYNC_FIXED_ENV,
            steps=_manager_sync_steps(detached=True),
        )

    if evidence.manager_local_main_sha != evidence.manager_head_sha:
        _fail("attached manager main ref does not equal HEAD")

    if evidence.installed_privileged_dispatch_exact_current:
        if not evidence.installed_privileged_dispatch_reconcile_route:
            _fail("exact-current privileged dispatch lacks reconcile route")
        return BootstrapReachabilityPlan(
            decision="RECONCILE_REACHABLE",
            exact_source_sha=evidence.exact_source_sha,
            next_operation_id=BOOTSTRAP_RECONCILE_OPERATION_ID,
            execution_entrypoint=INSTALLED_PRIVILEGED_DISPATCH,
            manager_checkout_resolver=MANAGER_CHECKOUT_RESOLVER,
            manager_branch_ref=MANAGER_BRANCH_REF,
            fixed_environment=MANAGER_SYNC_FIXED_ENV,
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
            manager_branch_ref=MANAGER_BRANCH_REF,
            fixed_environment=MANAGER_SYNC_FIXED_ENV,
            steps=(),
        )

    if evidence.manager_head_sha == evidence.exact_source_sha:
        _fail("exact-current manager checkout has drifted refresh runtime pair")
    if not evidence.manager_head_reviewed_ancestor:
        _fail("manager HEAD is not a reviewed ancestor of exact current source")

    return BootstrapReachabilityPlan(
        decision="MANAGER_SYNC_REQUIRED",
        exact_source_sha=evidence.exact_source_sha,
        next_operation_id=MANAGER_SYNC_OPERATION_ID,
        execution_entrypoint=None,
        manager_checkout_resolver=MANAGER_CHECKOUT_RESOLVER,
        manager_branch_ref=MANAGER_BRANCH_REF,
        fixed_environment=MANAGER_SYNC_FIXED_ENV,
        steps=_manager_sync_steps(detached=False),
    )


def public_plan(plan: BootstrapReachabilityPlan) -> dict[str, object]:
    return {
        "decision": plan.decision,
        "exact_source_sha": plan.exact_source_sha,
        "next_operation_id": plan.next_operation_id,
        "execution_entrypoint": plan.execution_entrypoint,
        "manager_checkout_resolver": plan.manager_checkout_resolver,
        "manager_branch_ref": plan.manager_branch_ref,
        "fixed_environment": [
            {"name": name, "value": value} for name, value in plan.fixed_environment
        ],
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
