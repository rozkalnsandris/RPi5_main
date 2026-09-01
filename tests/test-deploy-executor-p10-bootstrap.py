#!/usr/bin/env python3
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "ops" / "deploy" / "p10-dashboard-preflight.json"
BOOTSTRAP = ROOT / "ops" / "deploy" / "p10-dashboard-bootstrap.json"
DOC = ROOT / "docs" / "OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P10_BOOTSTRAP.md"
WRAPPER = ROOT / "ops" / "bin" / "rozkalns-dashboard-controller-bootstrap"
LIB = ROOT / "ops" / "lib" / "deploy_executor"

CANDIDATE_SHA = "5f7739348f56398d0ba301c9320e1de0062838fc"
HISTORICAL_BLOB = "c501bea57c0d5c35e7961ae1f1e5593a02268661"
HISTORICAL_COMMIT = "400296591ec14c062e4c3c9fdbc95c38109ba0fd"
HARDENED = {
    "7fcc58cbea2f1247d6e4d93bc3805923697fbfab",
    "c0566adb76e044632a4556dbefeb0f46839b4996",
}


def git_blob(data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def load_wrapper():
    module_name = "p10_bootstrap_entrypoint_source_test"
    loader = importlib.machinery.SourceFileLoader(module_name, str(WRAPPER))
    spec = importlib.util.spec_from_file_location(
        module_name,
        WRAPPER,
        loader=loader,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
    return module


def assert_trust_anchor_regression(implementation: dict) -> None:
    wrapper = load_wrapper()
    source = WRAPPER.read_text(encoding="utf-8")
    assert "sys.path.insert" not in source
    assert "from deploy_executor" not in source
    assert source.index("_verify_trust_anchor()") < source.index("_load_trusted_modules()")
    assert "sys.dont_write_bytecode = True" in source
    assert implementation["trust_anchor_verified_before_module_import"] is True
    assert implementation["normal_deploy_executor_package_init_executed"] is False
    assert implementation["source_wrapper_git_blob"] == git_blob(WRAPPER.read_bytes())
    assert implementation["source_wrapper_identity_verification"] == "separate-live-preflight-before-root-invocation"
    assert implementation["source_wrapper_runtime_mode"] == "0755"
    assert implementation["trusted_directory_mode"] == "0755"
    assert implementation["trusted_module_mode"] == "0644"
    assert implementation["future_installed_library_root_mode"] == "0755"
    assert 'Path("/usr/local/sbin")' in source
    assert 'INSTALLED_LIBRARY_ROOT, "installed bootstrap library root"' in source

    expected = implementation["trusted_module_git_blobs"]
    assert expected == wrapper.TRUSTED_MODULE_GIT_BLOBS
    for name, blob in expected.items():
        assert git_blob((LIB / name).read_bytes()) == blob

    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp) / "deploy_executor"
        package.mkdir(mode=0o755)
        (package / "__init__.py").write_text(
            "raise RuntimeError('normal package init must not execute')\n",
            encoding="utf-8",
        )
        for name in expected:
            target = package / name
            target.write_bytes((LIB / name).read_bytes())
            os.chmod(target, 0o644)
        os.chmod(package, 0o755)

        wrapper._verify_trust_anchor(
            package_root=package,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
        )
        loaded = wrapper._load_trusted_modules(package_root=package)
        assert loaded.BOOTSTRAP_ACK == "I_AUTHORIZED_DASHBOARD_RPI5_HARDENED_CONTROLLER_BOOTSTRAP"
        assert not (package / "__pycache__").exists()

        tampered = package / "dashboard_bootstrap.py"
        tampered.write_bytes(tampered.read_bytes() + b"\n# tamper\n")
        os.chmod(tampered, 0o644)
        try:
            wrapper._verify_trust_anchor(
                package_root=package,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
            )
        except wrapper.BootstrapEntrypointError as exc:
            assert "Git blob mismatch" in str(exc)
        else:
            raise AssertionError("tampered trusted module was accepted")


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

    assert bootstrap["schema_version"] == 3
    assert bootstrap["status"] == "INSTALLER_STAGER_SOURCE_MERGED_EXECUTION_DISABLED"
    assert bootstrap["roadmap_issue"] == 236
    assert bootstrap["queue"]["issue"] == 28
    assert bootstrap["queue"]["required_status"] == "WAITING"
    assert bootstrap["queue"]["reason"] == "WAITING_HARDENED_CONTROLLER_BOOTSTRAP_INSTALLER_STAGER_SOURCE"
    assert bootstrap["dashboard"]["candidate_sha"] == CANDIDATE_SHA
    assert bootstrap["dashboard"]["candidate_sha256"] == "c5a2adef8f7242833094a1c0cb8a8074392312567deeddd1228dc46c16cff5c0"
    assert bootstrap["dashboard"]["historical_manifest_schema_source"] == HISTORICAL_COMMIT
    assert bootstrap["dashboard"]["historical_manifest_schema"] == "dashboard-rpi5.production-candidate.v1"

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
    assert invariants["installer_stager_source_merge_authorizes_live_installation"] is False
    assert invariants["installer_stager_may_materialize_production_release"] is False
    assert invariants["installer_stager_may_swap_current_pointer"] is False
    assert invariants["installer_stager_may_execute_p10_plan"] is False
    assert invariants["installer_stager_may_execute_p10_apply"] is False
    assert invariants["normal_executor_registry_remains_globally_execution_disabled"] is True
    assert invariants["bootstrap_is_not_a_persistent_alternate_deploy_channel"] is True

    required_implementation = bootstrap["required_source_implementation"]
    assert required_implementation["owner"] == "RPi5_main-control-plane"
    assert required_implementation["kind"] == "dedicated-one-time-bootstrap-adapter"
    assert required_implementation["generic_shell_authority_forbidden"] is True
    assert required_implementation["arbitrary_path_or_argv_authority_forbidden"] is True
    assert required_implementation["must_bind_exact_dashboard_candidate_sha"] is True
    assert required_implementation["must_bind_exact_historical_controller_blob"] is True
    assert required_implementation["must_use_descriptor_safe_or_equivalent_immutable_candidate_consumption"] is True
    assert required_implementation["must_verify_root_owned_trust_anchor_before_first_privileged_execution"] is True
    assert required_implementation["must_define_exact_mutation_budget_and_exclusions"] is True
    assert required_implementation["must_define_post_mutation_evidence_preservation"] is True
    assert required_implementation["must_be_execution_disabled_until_separate_live_authorization"] is True

    implementation = bootstrap["implementation"]
    assert implementation["operation_id"] == "dashboard-rpi5.hardened-controller-bootstrap.v1"
    assert implementation["adapter_contract"] == "ops/lib/deploy_executor/dashboard_bootstrap_contract.py"
    assert implementation["adapter_implementation"] == "ops/lib/deploy_executor/dashboard_bootstrap_adapter.py"
    assert implementation["descriptor_safe_filesystem"] == "ops/lib/deploy_executor/dashboard_bootstrap_fs.py"
    assert implementation["bootstrap_orchestrator"] == "ops/lib/deploy_executor/dashboard_bootstrap.py"
    assert implementation["source_wrapper"] == "ops/bin/rozkalns-dashboard-controller-bootstrap"
    assert implementation["normal_executor_registry_registered"] is False
    assert implementation["execution_enabled"] is False
    assert implementation["network_allowed"] is False
    assert implementation["process_execution_allowed"] is False
    assert implementation["fixed_production_root"] == "/opt/dashboard_RPi5"
    assert implementation["fixed_candidate_root"].endswith(f"/{CANDIDATE_SHA}/source")
    assert implementation["fixed_manifest_path"].endswith(f"/{CANDIDATE_SHA}/candidate-manifest.json")
    assert_trust_anchor_regression(implementation)

    installer = bootstrap["installer_stager"]
    assert installer["status"] == "SOURCE_MERGED_EXECUTION_DISABLED"
    assert installer["source_merge_pr"] == 320
    assert installer["source_operator"] == "scripts/install-deploy-executor-p10-bootstrap-installer-stager.py"
    assert installer["source_test"] == "tests/test-deploy-executor-p10-bootstrap-installer-stager.py"
    assert installer["preserved_evidence_parent_basename"] == "p10-preflight-5f773934-20260901T074158Z-294325"
    assert installer["caller_supplied_path_arguments"] is False
    assert installer["descriptor_safe_preserved_evidence_consumption"] is True
    assert installer["fixed_staging_root"].endswith(CANDIDATE_SHA)
    assert installer["mutation_budget"] == {
        "fixed_staging_root_materializations": 1,
        "trusted_entrypoint_installations": 1,
        "trusted_module_installations": 3,
        "production_release_materializations": 0,
        "current_pointer_swaps": 0,
        "p10_plan_executions": 0,
        "p10_apply_executions": 0,
        "rollback_attempts": 0,
        "retry_attempts": 0,
    }
    assert installer["failure_semantics"]["automatic_retry"] is False
    assert installer["failure_semantics"]["automatic_cleanup"] is False
    assert installer["failure_semantics"]["automatic_rollback"] is False
    assert installer["separate_live_root_authorization_required_after_source_merge"] is True

    budget = bootstrap["mutation_budget"]
    assert budget["apply_lock"] == 1
    assert budget["release_materialization"] == 1
    assert budget["current_pointer_swap"] == 1
    assert budget["release_deletions"] == 0
    assert budget["rollback_attempts"] == 0
    assert budget["p10_application_apply"] == 0

    failure = bootstrap["failure_semantics"]
    assert failure["pre_release_mutation_failure"] == "remove_transient_lock_only"
    assert failure["post_release_mutation_failure"] == "preserve_lock_and_partial_evidence_then_stop"
    assert failure["automatic_retry"] is False
    assert failure["automatic_cleanup_after_release_mutation"] is False
    assert failure["automatic_rollback"] is False

    transition = bootstrap["p10_transition"]
    assert transition["candidate_build_arm64"] == "PASS"
    assert transition["candidate_manifest_verify"] == "PASS"
    assert transition["runtime_smoke"] == "PASS"
    assert transition["controller_classification"] == "BOOTSTRAP_REQUIRED"
    assert transition["privileged_plan_attempted"] is False
    assert transition["production_mutation_started"] is False
    assert transition["apply_executed"] is False
    assert transition["preflight_retry_allowed"] is False
    assert transition["bootstrap_execution_source"] == "MERGED_EXECUTION_DISABLED"
    assert transition["installer_stager_source"] == "MERGED_EXECUTION_DISABLED"
    assert transition["next_gate"] == "SEPARATE_LIVE_ROOT_INSTALLER_STAGER_AFTER_EXACT_MAIN_REVALIDATION"

    assert "known historical, bootstrap required" in doc
    assert "do not execute operator-writable candidate JavaScript as root" in doc
    assert "do not patch the current immutable release in place" in doc
    assert "do not copy/replace only the installed controller as a preflight workaround" in doc
    assert "separate exact LIVE/root bootstrap authorization" in doc
    assert "dashboard-rpi5.hardened-controller-bootstrap.v1" in doc
    assert "execution-disabled" in doc
    assert "before any installed bootstrap Python module is imported" in doc


if __name__ == "__main__":
    main()
