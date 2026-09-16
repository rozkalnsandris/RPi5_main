#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops/deploy/rpi5-main-weather-v7-host-capability-installer-source-trusted-checkout-bootstrap.json"
OPERATOR_BOOTSTRAP_PATH = ROOT / "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v7-trusted-checkout-bootstrap.json"
DOC_PATH = ROOT / "docs/WEATHER_OPERATOR_V7_PRIVILEGED_DELIVERY.md"
WORKFLOW_PATH = ROOT / ".github/workflows/validate.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    operator = json.loads(OPERATOR_BOOTSTRAP_PATH.read_text(encoding="utf-8"))
    doc = DOC_PATH.read_text(encoding="utf-8")
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    require(contract["schema"] == "rozkalns.rpi5-main.weather-v7-host-capability-installer-source-trusted-checkout-bootstrap.v1", "schema drifted")
    require(contract["issue"] == 574, "issue binding drifted")
    require(contract["repository"] == "rozkalnsandris/RPi5_main", "repository drifted")
    require(contract["reviewed_origin"] == "https://github.com/rozkalnsandris/RPi5_main.git", "origin drifted")
    require(contract["source_only"] is True, "source-only boundary disabled")
    require(contract["source_merge_enables_live"] is False, "source merge must not authorize LIVE")

    manager = contract["manager_checkout"]
    require(manager["working_tree_content_may_be_dirty"] is True, "dirty manager checkout must be tolerated")
    for key in ("working_tree_content_mutation_allowed", "index_mutation_allowed", "head_advance_allowed", "reset_allowed", "stash_allowed", "clean_allowed"):
        require(manager[key] is False, f"manager mutation unexpectedly enabled: {key}")

    target = contract["trusted_checkout"]
    operator_target = operator["trusted_checkout"]["name"]
    require(target["name"] == "RPi5_main-weather-v7-host-capability-installer-source-trusted", "installer source target drifted")
    require(target["name"] != operator_target, "installer source checkout must be distinct from operator-v7 checkout")
    require(target["distinct_from_later_operator_checkout"] == operator_target, "operator checkout separation drifted")
    require(target["expected_sha_authority"] == "EXPLICIT_WEATHER_V7_HOST_CAPABILITY_INSTALLER_SOURCE_LIVE_EXACT_RPI5_MAIN_SHA", "SHA authority drifted")
    require(target["exact_current_main_required"] is True, "current-main binding required")
    require(target["exact_main_ci_required"] is True, "exact-main CI binding required")
    require(target["required_post_state"] == "EXACT_SHA_DETACHED_CLEAN_CORRECT_ORIGIN", "post-state drifted")
    require("scripts/install-weather-operator-v7-host-capability.py" in target["required_paths"], "#571 installer missing from required paths")

    states = set(contract["preflight_states"])
    require(states == {"ABSENT", "EXACT_CLEAN", "CONFLICT"}, "preflight states must be exactly ABSENT/EXACT_CLEAN/CONFLICT")

    mutations = contract["allowed_git_mutations"]
    require(len(mutations) == 2, "mutation budget must contain exactly two Git operations")
    require(mutations[0]["argv"] == ["git", "fetch", "origin", "main"], "fetch argv drifted")
    require(mutations[0]["max_operations"] == 1, "fetch budget drifted")
    require(mutations[1]["argv"][:4] == ["git", "worktree", "add", "--detach"], "worktree argv drifted")
    require(mutations[1]["argv"][4] == target["derivation"], "worktree target drifted")
    require(mutations[1]["argv"][5] == target["expected_sha_authority"], "worktree SHA authority drifted")
    require(mutations[1]["max_operations"] == 1, "worktree-add budget drifted")
    require(all(item["working_tree_content_mutation"] is False for item in mutations), "manager working-tree mutation enabled")

    required_checks = set(contract["required_exact_main_checks"])
    require(required_checks == {
        "validate",
        "gitleaks",
        "GITHUB-ONLY policy drift / GITHUB-ONLY policy drift",
        "policy-drift / FAST-LANE v2.2 policy drift",
        "public-automation-baseline / public automation policy",
    }, "exact-main required checks drifted")

    forbidden = set(contract["forbidden_git_operations"])
    for op in ("reset", "clean", "stash", "worktree remove", "worktree prune", "worktree repair", "rebase", "push", "force"):
        require(op in forbidden, f"forbidden Git operation missing: {op}")

    failure = contract["failure"]
    require(failure["authorization_consumed_at_first_git_mutation"] is True, "authorization consumption boundary drifted")
    require(failure["automatic_retry"] is False, "automatic retry must remain disabled")
    require(failure["automatic_cleanup"] is False, "automatic cleanup must remain disabled")
    require(failure["automatic_rollback"] is False, "automatic rollback must remain disabled")
    require(failure["after_first_mutation_error"] == "STOP_PRESERVE_MINIMUM_READ_ONLY_EVIDENCE", "fail-closed STOP semantics drifted")

    handoff = contract["handoff"]
    require(handoff["installer_entrypoint"] == "scripts/install-weather-operator-v7-host-capability.py", "handoff entrypoint drifted")
    require(handoff["installer_must_run_from_this_exact_checkout"] is True, "exact checkout handoff disabled")
    require(handoff["source_delivery_authorizes_installer_apply"] is False, "source delivery must not authorize installer apply")
    require(handoff["source_delivery_authorizes_operator_upgrade"] is False, "source delivery must not authorize operator upgrade")
    require(handoff["source_delivery_authorizes_weather_rollout"] is False, "source delivery must not authorize Weather rollout")

    require("Issue #574 trusted installer source delivery" in doc, "#574 continuity documentation missing")
    require("python3 ./tests/test-weather-v7-host-capability-installer-source-delivery.py" in workflow, "#574 security test is not wired into Validate")

    print("weather-v7 host-capability installer source delivery contract: PASS")


if __name__ == "__main__":
    main()
