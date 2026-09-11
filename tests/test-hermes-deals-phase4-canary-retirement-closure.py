from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_phase4_canary_retirement_closure import (  # noqa: E402
    RetirementEvidence,
    RuntimePreflightEvidence,
    evaluate_phase4_closure,
    evaluate_runner_retirement,
    evaluate_runtime_preflight,
    reconcile_auto_live_scale_out,
    validate_contract,
)

CONTRACT = ROOT / "ops" / "contracts" / "hermes-deals-phase4-canary-retirement-closure-v1.json"
MODULE = ROOT / "ops" / "lib" / "deploy_executor" / "hermes_deals_phase4_canary_retirement_closure.py"


class HermesDealsPhase4ClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(CONTRACT.read_text(encoding="utf-8"))
        validate_contract(cls.data)

    def test_exact_ten_terminal_source_statuses(self) -> None:
        jobs = self.data["jobs"]
        self.assertEqual([row["job"] for row in jobs], list(range(1, 11)))
        self.assertEqual(
            [row["result"] for row in jobs],
            [
                "DONE", "DONE", "SOURCE_READY_LIVE_LATER", "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER", "NO_OP_ALREADY_RECONCILED",
                "SOURCE_READY_LIVE_LATER", "DONE", "SOURCE_READY_LIVE_LATER", "DONE",
            ],
        )

    def test_source_path_drift_uses_capability_specific_current_paths(self) -> None:
        drift = self.data["source_path_drift"]
        self.assertEqual(drift["stale_path"], "tools/install-hermes-deals-audit-runner.sh")
        self.assertFalse(drift["stale_path_is_current_authority"])
        self.assertEqual(drift["resolution"], "CAPABILITY_SPECIFIC_TOOLS_RUNNER_PATHS")
        paths = {row["path"] for row in drift["current_paths"]}
        self.assertIn("tools/runner/install-rpi5-audit-dispatcher.sh", paths)
        self.assertIn("tools/runner/install-rpi-source-sync-bridge.sh", paths)
        self.assertIn("tools/runner/install-rpi5-release-dispatcher.sh", paths)
        self.assertTrue(all(path.startswith("tools/runner/") for path in paths))

    def test_residual_capability_inventory_is_bounded_and_exact(self) -> None:
        rows = {row["capability_id"]: row for row in self.data["residual_capabilities"]}
        self.assertEqual(set(rows), {"origin_path_audit", "approved_audit_command", "source_sync", "production_release"})
        self.assertEqual(rows["approved_audit_command"]["workflow_blob"], "c9107e7597ff3ce1214cb32fb740346fa9d190aa")
        self.assertEqual(rows["source_sync"]["workflow_blob"], "b2f4eee1d1c503cf0c47b6099e748d6e6fd6d560")
        self.assertEqual(rows["production_release"]["workflow_blob"], "c45e14765881a82eb7e3d1bc3fe2f4f50cb0c38f")
        self.assertTrue(all(row["source_replacement_ready"] for row in rows.values()))
        self.assertFalse(any(row["runtime_wiring_asserted_by_bundle"] for row in rows.values()))

    def test_runner_smoke_canary_package_is_source_only(self) -> None:
        canary = self.data["canary_readiness"]
        self.assertEqual(canary["operation_id"], "hermes-deals.runner-smoke-audit.v1")
        self.assertTrue(canary["runner_independent_helper_source_required_before_live"])
        self.assertTrue(canary["runner_independent_registration_identity_required_before_live"])
        self.assertFalse(canary["caller_command_path_argv_environment_authority"])
        self.assertFalse(canary["ready_or_live_auth_created"])
        self.assertFalse(canary["genuine_canary_performed"])
        self.assertFalse(canary["expected_receipt"]["production_mutation_started"])
        self.assertFalse(canary["replay"]["automatic_retry_after_helper_start"])

    def test_source_sync_and_release_stay_live_disabled(self) -> None:
        sync = self.data["source_sync_readiness"]
        self.assertEqual(sync["source_checkout_path"], "/home/andris/hermes-deals")
        self.assertFalse(sync["generic_checkout_path_authority"])
        self.assertFalse(sync["generic_git_subcommand_authority"])
        self.assertFalse(sync["runtime_execution_enabled"])
        self.assertTrue(sync["requires_separate_live_authorization"])
        release = self.data["production_release_readiness"]
        self.assertEqual(release["future_auto_live_candidate_class"], "AUTO_DEPLOY_SAFE")
        self.assertFalse(release["manifest_indexed"])
        self.assertFalse(release["static_operation_registered"])
        self.assertFalse(release["automatic_mutation_enabled"])

    def test_netto_425_remains_authoritative(self) -> None:
        netto = self.data["netto_identity_supersession"]
        self.assertEqual(netto["authoritative_issue"], 425)
        self.assertEqual(netto["superseded_issue"], 424)
        self.assertEqual(netto["model"], "DEDICATED_NON_LOGIN_NON_ROOT_NO_DOCKER")
        self.assertEqual(netto["account"], "hermes-netto-audit")
        self.assertEqual(netto["supplementary_groups"], [])
        self.assertIn("docker", netto["forbidden_groups"])
        self.assertTrue({"root", "andris", "github-runner"}.issubset(netto["forbidden_accounts"]))
        self.assertFalse(netto["caller_selectable_identity"])
        self.assertFalse(netto["execution_enabled"])
        self.assertFalse(netto["host_wiring_enabled"])

    def test_preflight_is_default_read_only_and_identity_bound(self) -> None:
        result = evaluate_runtime_preflight(
            self.data,
            "source_sync",
            RuntimePreflightEvidence(
                source_sha="87eeb9a6dcfbd802158e42bc8501b5ad8629431f",
                exact_sha_ci_success=True,
                helper_source_path="tools/runner/install-rpi-source-sync-bridge.sh",
                helper_source_blob="0e258f3b6285a43637f54eca4b10ae4efb2416d8",
                registration_identity_matches=True,
                execution_identity_matches=True,
            ),
        )
        self.assertEqual(result["decision"], "SOURCE_PREFLIGHT_READY")
        self.assertFalse(result["helper_execution_allowed"])
        self.assertFalse(result["host_write_allowed"])
        self.assertFalse(result["runtime_live_authority"])

    def test_preflight_fails_closed_on_provenance_or_ci_drift(self) -> None:
        result = evaluate_runtime_preflight(
            self.data,
            "production_release",
            RuntimePreflightEvidence(
                source_sha="87eeb9a6dcfbd802158e42bc8501b5ad8629431f",
                exact_sha_ci_success=False,
                helper_source_path="tools/runner/install-rpi5-release-dispatcher.sh",
                helper_source_blob="0" * 40,
                registration_identity_matches=True,
                execution_identity_matches=True,
            ),
        )
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("exact_sha_ci_missing", result["missing"])
        self.assertIn("helper_source_blob_mismatch", result["missing"])

    def test_preflight_api_has_no_generic_execution_surface(self) -> None:
        fields = set(inspect.signature(RuntimePreflightEvidence).parameters)
        self.assertFalse(fields & {"command", "argv", "environment", "cwd", "sudo", "shell", "uid", "gid"})
        source = MODULE.read_text(encoding="utf-8").lower()
        for forbidden in ("import subprocess", "os.system", "shell=true", "bash -c", "sh -c", "eval("):
            self.assertNotIn(forbidden, source)

    def test_retirement_graph_denies_missing_or_partial_evidence(self) -> None:
        result = evaluate_runner_retirement(self.data, "hermes-deals-audit", {})
        self.assertEqual(result["decision"], "NOT_ELIGIBLE")
        self.assertTrue(result["missing"])
        self.assertFalse(result["runner_deregistration_authorized"])
        good = RetirementEvidence(True, True, True, True, True)
        bad = RetirementEvidence(True, False, True, True, True)
        result = evaluate_runner_retirement(self.data, "hermes-deals-audit", {"origin_path_audit": good, "approved_audit_command": good, "source_sync": bad})
        self.assertEqual(result["decision"], "NOT_ELIGIBLE")
        self.assertIn("source_sync:runtime_wiring_proven", result["missing"])

    def test_complete_retirement_evidence_only_opens_separate_owner_gate(self) -> None:
        good = RetirementEvidence(True, True, True, True, True)
        result = evaluate_runner_retirement(self.data, "hermes-deals-release", {"production_release": good})
        self.assertEqual(result["decision"], "ELIGIBLE_FOR_SEPARATE_OWNER_RETIREMENT_GATE")
        self.assertFalse(result["runner_deregistration_authorized"])

    def test_auto_live_scale_out_is_class_and_provenance_bound_but_disabled(self) -> None:
        safe = reconcile_auto_live_scale_out(self.data, "production_release", "AUTO_DEPLOY_SAFE", exact_sha_ci_success=True, full_range_complete=True, stable_concurrency=True, helper_identity_matches=True)
        self.assertEqual(safe["decision"], "SOURCE_ELIGIBLE_LIVE_STILL_DISABLED")
        self.assertFalse(safe["automatic_mutation_allowed"])
        self.assertFalse(safe["runtime_live_authority"])
        sync = reconcile_auto_live_scale_out(self.data, "source_sync", "MANUAL_ROLLOUT_REQUIRED", exact_sha_ci_success=True, full_range_complete=True, stable_concurrency=True, helper_identity_matches=True)
        self.assertEqual(sync["decision"], "OWNER_REQUIRED")
        self.assertFalse(sync["automatic_mutation_allowed"])

    def test_auto_live_rejects_class_or_evidence_drift(self) -> None:
        mismatch = reconcile_auto_live_scale_out(self.data, "source_sync", "AUTO_DEPLOY_SAFE", exact_sha_ci_success=True, full_range_complete=True, stable_concurrency=True, helper_identity_matches=True)
        self.assertEqual(mismatch["decision"], "BLOCKED")
        missing = reconcile_auto_live_scale_out(self.data, "production_release", "AUTO_DEPLOY_SAFE", exact_sha_ci_success=False, full_range_complete=True, stable_concurrency=True, helper_identity_matches=True)
        self.assertEqual(missing["decision"], "BLOCKED")

    def test_phase4_source_contract_never_closes_phase4_itself(self) -> None:
        blocked = evaluate_phase4_closure(self.data, fresh_final_inventory=False, runner_count=1, residual_runner_owner_acceptance=False, all_required_capability_evidence_complete=False)
        self.assertEqual(blocked["decision"], "NOT_CLOSED")
        self.assertFalse(blocked["phase4_closed"])
        eligible = evaluate_phase4_closure(self.data, fresh_final_inventory=True, runner_count=0, residual_runner_owner_acceptance=False, all_required_capability_evidence_complete=True)
        self.assertEqual(eligible["decision"], "ELIGIBLE_FOR_EXPLICIT_OWNER_PHASE4_CLOSURE_DECISION")
        self.assertFalse(eligible["phase4_closed"])
        self.assertFalse(eligible["runtime_live_authority"])

    def test_all_mutation_flags_remain_false(self) -> None:
        self.assertTrue(all(value is False for value in self.data["mutation"].values()))
        self.assertFalse(self.data["phase4_closure"]["source_evidence_alone_can_close_phase4"])
        self.assertFalse(self.data["runner_retirement_graph"]["runner_deregistration_authorized"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
