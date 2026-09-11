from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_phase4_operational_readiness import (  # noqa: E402
    RetirementEvidence,
    SelectedAuditPreflightEvidence,
    evaluate_auto_live_a5,
    evaluate_phase4_handoff,
    evaluate_runner_retirement,
    evaluate_selected_audit_preflight,
    validate_contract,
)

CONTRACT = ROOT / "ops" / "contracts" / "hermes-deals-phase4-operational-readiness-v1.json"
BRIDGE = ROOT / "ops" / "deploy" / "hermes-deals-auto-live-a5-source-bridge.json"
MODULE = ROOT / "ops" / "lib" / "deploy_executor" / "hermes_deals_phase4_operational_readiness.py"


class HermesDealsPhase4OperationalReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.bridge = json.loads(BRIDGE.read_text(encoding="utf-8"))
        validate_contract(cls.data)

    def test_exact_ten_terminal_source_statuses(self) -> None:
        jobs = self.data["jobs"]
        self.assertEqual([row["job"] for row in jobs], list(range(1, 11)))
        self.assertEqual(
            [row["result"] for row in jobs],
            [
                "DONE",
                "DONE",
                "DONE",
                "SOURCE_READY_LIVE_LATER",
                "DONE",
                "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER",
                "DONE",
                "DONE",
            ],
        )

    def test_fresh_residual_capability_identities_are_exact(self) -> None:
        rows = {row["capability_id"]: row for row in self.data["residual_capabilities"]}
        self.assertEqual(
            set(rows),
            {"origin_path_audit", "approved_audit_command", "source_sync", "production_release"},
        )
        self.assertEqual(
            rows["approved_audit_command"]["workflow_blob"],
            "c9107e7597ff3ce1214cb32fb740346fa9d190aa",
        )
        self.assertEqual(
            rows["source_sync"]["workflow_blob"],
            "b2f4eee1d1c503cf0c47b6099e748d6e6fd6d560",
        )
        self.assertEqual(
            rows["production_release"]["workflow_blob"],
            "c45e14765881a82eb7e3d1bc3fe2f4f50cb0c38f",
        )
        self.assertFalse(any(row["current_runtime_state_asserted"] for row in rows.values()))

    def test_selected_runner_smoke_exposes_legacy_coupling_but_never_reuses_it_live(self) -> None:
        selected = self.data["selected_audit_capability"]
        self.assertEqual(selected["selected_audit"], "runner-smoke")
        self.assertEqual(selected["future_operation_id"], "hermes-deals.runner-smoke-audit.v1")
        self.assertTrue(selected["read_only"])
        self.assertTrue(selected["legacy_path_runner_coupled"])
        self.assertFalse(selected["legacy_path_live_reuse_allowed"])
        self.assertTrue(selected["runner_independent_design_required"])
        self.assertFalse(selected["caller_command_path_argv_environment_authority"])
        self.assertFalse(selected["generic_privileged_execution"])

    def test_host_wiring_source_contract_uses_dedicated_non_login_nonroot_identity(self) -> None:
        wiring = self.data["host_wiring_source_contract"]
        identity = wiring["execution_identity"]
        self.assertEqual(identity["account"], "hermes-deals-audit-canary")
        self.assertEqual(identity["login_shell"], "/usr/sbin/nologin")
        self.assertFalse(identity["root"])
        self.assertFalse(identity["docker_group"])
        self.assertEqual(identity["supplementary_groups"], [])
        self.assertEqual(wiring["privileged_boundary_input"], ["authorization_issue_number"])
        self.assertTrue(wiring["no_overwrite"])
        self.assertTrue(wiring["nofollow_required"])
        self.assertFalse(wiring["runtime_installation_performed"])
        self.assertFalse(wiring["service_or_runner_mutation_performed"])

    def test_selected_audit_preflight_is_read_only_and_exact_source_bound(self) -> None:
        result = evaluate_selected_audit_preflight(
            self.data,
            SelectedAuditPreflightEvidence(
                source_sha="8015d6175b2b3c260fdb26546021bb17dcc5f4fb",
                exact_sha_ci_success=True,
                helper_identity_matches=True,
                registration_identity_matches=True,
                execution_identity_matches=True,
                helper_owner_mode_matches=True,
                registration_owner_mode_matches=True,
                expected_inert_state=True,
            ),
        )
        self.assertEqual(result["decision"], "SOURCE_PREFLIGHT_READY")
        self.assertFalse(result["helper_execution_allowed"])
        self.assertFalse(result["host_write_allowed"])
        self.assertFalse(result["protected_credential_read_allowed"])
        self.assertFalse(result["live_authorization_consumed"])

    def test_selected_audit_preflight_fails_closed_on_any_identity_or_ci_gap(self) -> None:
        result = evaluate_selected_audit_preflight(
            self.data,
            SelectedAuditPreflightEvidence(
                source_sha="8015d6175b2b3c260fdb26546021bb17dcc5f4fb",
                exact_sha_ci_success=False,
                helper_identity_matches=True,
                registration_identity_matches=False,
                execution_identity_matches=True,
                helper_owner_mode_matches=True,
                registration_owner_mode_matches=False,
                expected_inert_state=True,
            ),
        )
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("exact_sha_ci_missing", result["missing"])
        self.assertIn("registration_identity_unproven", result["missing"])
        self.assertIn("registration_owner_mode_unproven", result["missing"])

    def test_preflight_api_has_no_generic_execution_surface(self) -> None:
        fields = set(inspect.signature(SelectedAuditPreflightEvidence).parameters)
        self.assertFalse(fields & {"command", "argv", "environment", "cwd", "sudo", "shell", "uid", "gid", "path"})
        source = MODULE.read_text(encoding="utf-8").lower()
        for forbidden in ("import subprocess", "os.system", "shell=true", "bash -c", "sh -c", "eval("):
            self.assertNotIn(forbidden, source)

    def test_genuine_canary_package_defines_protocol_without_creating_authority(self) -> None:
        canary = self.data["genuine_canary_package"]
        self.assertEqual(canary["authorization_protocol"], "RPi5_main#236")
        self.assertTrue(canary["canonical_body_hash_required"])
        self.assertTrue(canary["identical_body_refetch_before_helper"])
        self.assertTrue(canary["durable_one_shot_replay_required"])
        self.assertTrue(canary["consume_immediately_before_first_helper_invocation"])
        self.assertFalse(canary["ready_queue_created"])
        self.assertFalse(canary["live_auth_created"])
        self.assertFalse(canary["genuine_canary_performed"])
        self.assertFalse(canary["production_mutation_started"])
        self.assertFalse(canary["automatic_retry_after_helper_start"])

    def test_source_sync_remains_fast_forward_only_and_live_disabled(self) -> None:
        sync = self.data["source_sync_operational_readiness"]
        self.assertEqual(sync["canonical_checkout_identity"], "HERMES_DEALS_CANONICAL_SOURCE_CHECKOUT")
        self.assertEqual(sync["allowed_future_mutation"], "FAST_FORWARD_TO_EXACT_MERGED_REACHABLE_SHA")
        self.assertFalse(sync["caller_selectable_checkout_path"])
        self.assertFalse(sync["generic_git_subcommand_authority"])
        self.assertFalse(sync["generic_checkout_path_authority"])
        self.assertFalse(sync["runtime_execution_enabled"])
        self.assertFalse(sync["host_mutation_performed"])
        self.assertTrue(sync["requires_separate_live_authorization"])

    def test_auto_live_a5_descriptor_is_inactive_default_deny(self) -> None:
        bridge = self.bridge
        self.assertEqual(bridge["status"], "SOURCE_DESCRIPTOR_ONLY_NOT_ACTIVE")
        self.assertEqual(bridge["static_operation_id"], "hermes-deals.production-release.v1")
        manifest = bridge["manifest_descriptor"]
        self.assertEqual(manifest["activation_state"], "INACTIVE_SOURCE_ONLY")
        self.assertFalse(manifest["automatic_mutation_enabled"])
        self.assertEqual(manifest["eligible_classes"], ["AUTO_DEPLOY_SAFE"])
        self.assertEqual(manifest["unknown_or_ambiguous_path_result"], "BLOCKED")
        self.assertFalse(bridge["registration"]["global_executor_operation_registered"])
        self.assertFalse(bridge["registration"]["auto_live_manifest_indexed"])
        self.assertTrue(all(value is False for value in bridge["mutation"].values()))

    def test_auto_live_source_evaluation_never_grants_execution(self) -> None:
        safe = evaluate_auto_live_a5(
            self.data,
            "AUTO_DEPLOY_SAFE",
            exact_sha_ci_success=True,
            full_range_complete=True,
            helper_identity_matches=True,
            production_baseline_matches=True,
        )
        self.assertEqual(safe["decision"], "SOURCE_DESCRIPTOR_ELIGIBLE_EXECUTION_DISABLED")
        self.assertFalse(safe["automatic_mutation_allowed"])
        self.assertFalse(safe["runtime_live_authority"])
        manual = evaluate_auto_live_a5(
            self.data,
            "MANUAL_ROLLOUT_REQUIRED",
            exact_sha_ci_success=True,
            full_range_complete=True,
            helper_identity_matches=True,
            production_baseline_matches=True,
        )
        self.assertEqual(manual["decision"], "OWNER_REQUIRED")
        missing = evaluate_auto_live_a5(
            self.data,
            "AUTO_DEPLOY_SAFE",
            exact_sha_ci_success=False,
            full_range_complete=True,
            helper_identity_matches=True,
            production_baseline_matches=True,
        )
        self.assertEqual(missing["decision"], "BLOCKED")

    def test_runner_retirement_remains_fail_closed_until_all_runtime_evidence_exists(self) -> None:
        blocked = evaluate_runner_retirement(self.data, "hermes-deals-audit", {})
        self.assertEqual(blocked["decision"], "NOT_ELIGIBLE")
        self.assertTrue(blocked["missing"])
        self.assertFalse(blocked["runner_deregistration_authorized"])
        good = RetirementEvidence(True, True, True, True, True, True)
        release = evaluate_runner_retirement(
            self.data,
            "hermes-deals-release",
            {"production_release": good},
        )
        self.assertEqual(release["decision"], "ELIGIBLE_FOR_SEPARATE_OWNER_RETIREMENT_GATE")
        self.assertFalse(release["runner_deregistration_authorized"])
        self.assertFalse(release["repository_settings_mutation_authorized"])

    def test_netto_425_strict_identity_guard_cannot_regress(self) -> None:
        netto = self.data["netto_identity_guard"]
        self.assertEqual(netto["authoritative_issue"], 425)
        self.assertEqual(netto["model"], "DEDICATED_NON_LOGIN_NON_ROOT_NO_DOCKER")
        self.assertEqual(netto["supplementary_groups"], [])
        self.assertIn("docker", netto["forbidden_groups"])
        self.assertTrue({"root", "andris", "github-runner"}.issubset(netto["forbidden_accounts"]))
        self.assertFalse(netto["caller_selectable_identity"])

    def test_phase4_handoff_never_closes_phase4_or_authorizes_retirement(self) -> None:
        blocked = evaluate_phase4_handoff(
            self.data,
            selected_capability_host_wiring_proven=False,
            selected_capability_canary_proven=False,
            all_residual_capabilities_proven=False,
            fresh_final_runner_inventory=False,
        )
        self.assertEqual(blocked["decision"], "NOT_CLOSED_LIVE_EVIDENCE_REQUIRED")
        self.assertFalse(blocked["phase4_closed"])
        complete = evaluate_phase4_handoff(
            self.data,
            selected_capability_host_wiring_proven=True,
            selected_capability_canary_proven=True,
            all_residual_capabilities_proven=True,
            fresh_final_runner_inventory=True,
        )
        self.assertEqual(complete["decision"], "ELIGIBLE_FOR_EXPLICIT_OWNER_PHASE4_CLOSURE_DECISION")
        self.assertFalse(complete["phase4_closed"])
        self.assertFalse(complete["runtime_live_authority"])
        self.assertFalse(complete["runner_retirement_authorized"])

    def test_all_bundle_mutation_flags_remain_false(self) -> None:
        self.assertTrue(all(value is False for value in self.data["mutation"].values()))
        self.assertEqual(self.data["runner_retirement_graph"]["current_decision"], "NOT_ELIGIBLE")
        self.assertFalse(self.data["operational_handoff"]["source_evidence_alone_can_close_phase4"])
        self.assertFalse(self.data["operational_handoff"]["merge_authorizes_live"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
