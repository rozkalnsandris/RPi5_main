from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from . import hermes_deals_runner_smoke_broker_bootstrap as base

IMPLEMENTATION_ISSUE = base.IMPLEMENTATION_ISSUE
CHECKOUT_ISOLATION_ISSUE = 584
HISTORICAL_TRUSTED_CHECKOUT_NAME = base.TRUSTED_CHECKOUT_NAME
TRUSTED_CHECKOUT_NAME = "RPi5_main-runner-smoke-broker-bootstrap-v2-trusted"
REVIEWED_ORIGIN = base.REVIEWED_ORIGIN
EXPECTED_HEAD_MODE = base.EXPECTED_HEAD_MODE
SOURCE_DELIVERY_CONTRACT = Path(
    "ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-v2-source-trusted-checkout-bootstrap.json"
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
            "historical_trusted_checkout_name": HISTORICAL_TRUSTED_CHECKOUT_NAME,
            "trusted_checkout_name": TRUSTED_CHECKOUT_NAME,
            "source_delivery_contract": str(SOURCE_DELIVERY_CONTRACT),
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


def observe_bootstrap(
    checkout: Path,
    *,
    host_root: Path = Path("/"),
    uid: int = base.ROOT_UID,
    gid: int = base.ROOT_GID,
) -> BootstrapObservation:
    source_sha = validate_trusted_checkout(checkout)
    filesystem_state = base._filesystem_state(
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
    return base.plan_bootstrap(observation)


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

    mutation_started = False
    try:
        mutation_started = True
        base._publish_absent_state(checkout, plan.source_sha)
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
