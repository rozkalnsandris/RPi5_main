#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "ops" / "deploy" / "p10-dashboard-preflight.json"
BOOTSTRAP = ROOT / "ops" / "deploy" / "p10-dashboard-bootstrap.json"
DOC = ROOT / "docs" / "OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P10_BOOTSTRAP.md"

CANDIDATE_SHA = "5f7739348f56398d0ba301c9320e1de0062838fc"
HISTORICAL_BLOB = "c501bea57c0d5c35e7961ae1f1e5593a02268661"
HISTORICAL_COMMIT = "400296591ec14c062e4c3c9fdbc95c38109ba0fd"
HARDENED = {
    "7fcc58cbea2f1247d6e4d93bc3805923697fbfab",
    "c0566adb76e044632a4556dbefeb0f46839b4996",
}


def main() -> None:
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    bootstrap = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))
    doc = DOC.read_text(encoding="utf-8")

    assert preflight["schema_version"] == 2
    assert preflight["source"]["sha"] == CANDIDATE_SHA

    controller = preflight["controller"]
    accepted = {entry["git_blob"] for entry in controller["accepted_plan_identities"]}
    assert accepted == HARDENED
    assert HISTORICAL_BLOB not in accepted

    required = controller["bootstrap_required_identities"]
    assert len(required) == 1
    historical = required[0]
    assert historical == {
        "git_blob": HISTORICAL_BLOB,
        "source_commit": HISTORICAL_COMMIT,
        "classification": "known-historical-pre-descriptor-safe",
        "privileged_plan_allowed": False,
        "candidate_checkout_root_execution_allowed": False,
        "retry_under_consumed_preflight_allowed": False,
        "next_gate": "SOURCE_ONLY_HARDENED_CONTROLLER_BOOTSTRAP_IMPLEMENTATION",
    }

    dependency = preflight["bootstrap_dependency"]
    assert dependency["historical_controller_is_normal_plan_allowlist_member"] is False
    assert dependency["bootstrap_may_patch_current_release_in_place"] is False
    assert dependency["bootstrap_may_execute_operator_writable_candidate_javascript_as_root"] is False
    assert dependency["bootstrap_may_be_inferred_from_merge_or_preflight_authorization"] is False
    assert dependency["separate_source_implementation_required"] is True
    assert dependency["separate_live_root_authorization_required_after_source_merge"] is True

    assert bootstrap["schema_version"] == 1
    assert bootstrap["status"] == "SOURCE_ONLY_BOOTSTRAP_RECONCILIATION"
    assert bootstrap["roadmap_issue"] == 236
    assert bootstrap["queue"]["issue"] == 28
    assert bootstrap["queue"]["required_status"] == "WAITING"
    assert bootstrap["queue"]["reason"] == "WAITING_HARDENED_CONTROLLER_BOOTSTRAP_IMPLEMENTATION"
    assert bootstrap["dashboard"]["candidate_sha"] == CANDIDATE_SHA

    observed = bootstrap["observed_historical_controller"]
    assert observed["git_blob"] == HISTORICAL_BLOB
    assert observed["source_commit"] == HISTORICAL_COMMIT
    assert observed["normal_privileged_plan_allowed"] is False
    assert observed["normal_privileged_apply_allowed"] is False
    assert set(bootstrap["hardened_controller_identities"]) == HARDENED

    invariants = bootstrap["invariants"]
    assert invariants["candidate_checkout_is_data_only"] is True
    assert invariants["candidate_checkout_javascript_may_execute_as_root"] is False
    assert invariants["historical_controller_may_be_added_to_normal_plan_allowlist"] is False
    assert invariants["current_release_may_be_patched_in_place"] is False
    assert invariants["installed_controller_may_be_replaced_as_preflight_workaround"] is False
    assert invariants["bootstrap_requires_root_owned_immutable_trust_anchor"] is True
    assert invariants["bootstrap_requires_exact_reviewed_provenance"] is True
    assert invariants["bootstrap_requires_fail_closed_no_retry_after_mutation"] is True
    assert invariants["bootstrap_source_merge_authorizes_live_installation"] is False
    assert invariants["bootstrap_preflight_authorization_authorizes_live_installation"] is False

    implementation = bootstrap["required_source_implementation"]
    assert implementation["owner"] == "RPi5_main-control-plane"
    assert implementation["kind"] == "dedicated-one-time-bootstrap-adapter"
    assert implementation["generic_shell_authority_forbidden"] is True
    assert implementation["arbitrary_path_or_argv_authority_forbidden"] is True
    assert implementation["must_bind_exact_dashboard_candidate_sha"] is True
    assert implementation["must_bind_exact_historical_controller_blob"] is True
    assert implementation["must_use_descriptor_safe_or_equivalent_immutable_candidate_consumption"] is True
    assert implementation["must_verify_root_owned_trust_anchor_before_first_privileged_execution"] is True
    assert implementation["must_define_exact_mutation_budget_and_exclusions"] is True
    assert implementation["must_define_post_mutation_evidence_preservation"] is True
    assert implementation["must_be_execution_disabled_until_separate_live_authorization"] is True

    transition = bootstrap["p10_transition"]
    assert transition["candidate_build_arm64"] == "PASS"
    assert transition["candidate_manifest_verify"] == "PASS"
    assert transition["runtime_smoke"] == "PASS"
    assert transition["controller_classification"] == "BOOTSTRAP_REQUIRED"
    assert transition["privileged_plan_attempted"] is False
    assert transition["production_mutation_started"] is False
    assert transition["apply_executed"] is False
    assert transition["preflight_retry_allowed"] is False

    for forbidden in [
        "add the historical controller to the normal PLAN allowlist",
        "execute operator-writable candidate JavaScript as root",
        "patch the current immutable release in place",
    ]:
        assert forbidden not in doc

    assert "known historical, bootstrap required" in doc
    assert "do not execute operator-writable candidate JavaScript as root" in doc
    assert "do not patch the current immutable release in place" in doc
    assert "separate exact LIVE bootstrap authorization" in doc


if __name__ == "__main__":
    main()
