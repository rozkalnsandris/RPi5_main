from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_phase4_runner_retirement import (  # noqa: E402
    CapabilityRequest,
    CapabilityRetirementEvidence,
    HermesDealsPhase4ContractError,
    evaluate_runner_retirement,
    reconcile_auto_live,
    validate_capability_request,
    validate_contract,
)

CONTRACT = ROOT / "ops" / "contracts" / "hermes-deals-phase4-runner-retirement-v1.json"
MODULE = (
    ROOT
    / "ops"
    / "lib"
    / "deploy_executor"
    / "hermes_deals_phase4_runner_retirement.py"
)


class HermesDealsPhase4BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(CONTRACT.read_text(encoding="utf-8"))
        validate_contract(cls.data)

    def test_exact_ten_job_terminal_statuses(self) -> None:
        jobs = self.data["jobs"]
        self.assertEqual([row["job"] for row in jobs], list(range(1, 11)))
        self.assertEqual(
            [row["result"] for row in jobs],
            [
                "DONE",
                "DONE",
                "NO_OP_ALREADY_RECONCILED",
                "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER",
                "NO_OP_ALREADY_RECONCILED",
                "DONE",
                "SOURCE_READY_LIVE_LATER",
                "DONE",
            ],
        )

    def test_fresh_residual_inventory_is_exact_and_bounded(self) -> None:
        rows = {row["capability_id"]: row for row in self.data["residual_runner_paths"]}
        self.assertEqual(
            set(rows),
            {"origin_path_audit", "approved_audit_command", "source_sync", "production_release"},
        )
        self.assertEqual(rows["origin_path_audit"]["workflow_blob"], "99a18c5f669e7880a8a8288c3f964285df87ae22")
        self.assertEqual(rows["approved_audit_command"]["workflow_blob"], "c9107e7597ff3ce1214cb32fb740346fa9d190aa")
        self.assertEqual(rows["source_sync"]["workflow_blob"], "b2f4eee1d1c503cf0c47b6099e748d6e6fd6d560")
        self.assertEqual(rows["production_release"]["workflow_blob"], "c45e14765881a82eb7e3d1bc3fe2f4f50cb0c38f")
        self.assertEqual(rows["production_release"]["runner_label"], "hermes-deals-release")
        for capability_id in ("origin_path_audit", "approved_audit_command", "source_sync"):
            self.assertEqual(rows[capability_id]["runner_label"], "hermes-deals-audit")

    def test_origin_path_reuses_proven_static_operation(self) -> None:
        row = next(
            item for item in self.data["residual_runner_paths"]
            if item["capability_id"] == "origin_path_audit"
        )
        self.assertEqual(row["replacement_operation_id"], "hermes-deals.origin-path-audit.v1")
        self.assertEqual(row["replacement_status"], "PROVEN_EXISTING_SOURCE_CONTRACT")

    def test_audit_surface_is_static_allowlist_only(self) -> None:
        operations = self.data["approved_audit_operations"]
        self.assertEqual(
            {row["legacy_selector"] for row in operations},
            {"runner-smoke", "b15m2-v08"},
        )
        self.assertEqual(len({row["operation_id"] for row in operations}), 2)
        for row in operations:
            self.assertTrue(row["read_only"])
            self.assertTrue(row["static_allowlist_only"])
            self.assertFalse(row["caller_command_selector"])

    def test_source_sync_and_release_remain_future_live(self) -> None:
        sync = self.data["source_sync_contract"]
        self.assertFalse(sync["runtime_execution_enabled"])
        self.assertTrue(sync["requires_separate_live_authorization"])
        self.assertFalse(sync["generic_checkout_path_authority"])
        self.assertFalse(sync["generic_git_subcommand_authority"])

        release = self.data["production_release_contract"]
        self.assertFalse(release["automatic_mutation_enabled"])
        self.assertFalse(release["legacy_release_runner_retirement_enabled"])
        self.assertEqual(release["automatic_candidate_class"], "AUTO_DEPLOY_SAFE")
        self.assertEqual(
            set(release["owner_required_classes"]),
            {"MANUAL_ROLLOUT_REQUIRED", "DB_HOST_APPLY_REQUIRED"},
        )

    def test_netto_uses_stricter_425_identity_not_stale_424(self) -> None:
        netto = self.data["netto_identity"]
        self.assertEqual(netto["authoritative_issue"], 425)
        self.assertEqual(netto["authoritative_pr"], 431)
        self.assertEqual(netto["superseded_issue"], 424)
        self.assertEqual(netto["superseded_pr"], 426)
        self.assertEqual(netto["model"], "DEDICATED_NON_LOGIN_NON_ROOT_NO_DOCKER")
        self.assertEqual(netto["account"], "hermes-netto-audit")
        self.assertEqual(netto["supplementary_groups"], [])
        self.assertFalse(netto["docker_group_authority_allowed"])
        self.assertFalse(netto["caller_selectable_identity"])
        self.assertFalse(netto["execution_enabled"])
        self.assertFalse(netto["host_wiring_enabled"])
        self.assertFalse(netto["canary_authorized"])

    def test_valid_request_is_source_only(self) -> None:
        result = validate_capability_request(
            self.data,
            CapabilityRequest(
                capability_id="source_sync",
                operation_id="hermes-deals.source-sync.v1",
                source_sha="a" * 40,
                owner_numeric_id=277435981,
                merged_reachable=True,
                exact_ci_success=True,
            ),
        )
        self.assertEqual(result["decision"], "SOURCE_REQUEST_VALIDATED")
        self.assertFalse(result["runtime_live_authority"])
        self.assertFalse(result["production_mutation_started"])

    def test_adversarial_request_rejections(self) -> None:
        base = dict(
            capability_id="approved_audit_command",
            operation_id="hermes-deals.approved-audit-command.v1",
            source_sha="b" * 40,
            owner_numeric_id=277435981,
            merged_reachable=True,
            exact_ci_success=True,
        )
        cases = (
            ({"operation_id": "attacker.operation"}, "operation id"),
            ({"source_sha": "bad"}, "source SHA"),
            ({"owner_numeric_id": 1}, "owner numeric"),
            ({"merged_reachable": False}, "merged/reachable"),
            ({"exact_ci_success": False}, "exact-SHA CI"),
        )
        for changes, pattern in cases:
            row = dict(base)
            row.update(changes)
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(HermesDealsPhase4ContractError, pattern):
                    validate_capability_request(self.data, CapabilityRequest(**row))

    def test_request_api_has_no_generic_command_surface(self) -> None:
        names = set(inspect.signature(CapabilityRequest).parameters)
        self.assertFalse(
            names
            & {
                "command",
                "path",
                "argv",
                "environment",
                "cwd",
                "uid",
                "gid",
                "shell",
                "sudo",
            }
        )
        source = MODULE.read_text(encoding="utf-8").lower()
        for forbidden in ("import subprocess", "os.system", "shell=true", "bash -c", "sh -c", "eval("):
            self.assertNotIn(forbidden, source)

    def test_runner_retirement_fails_closed_on_missing_evidence(self) -> None:
        decision = evaluate_runner_retirement(self.data, "hermes-deals-audit", {})
        self.assertEqual(decision["decision"], "NOT_ELIGIBLE")
        self.assertTrue(decision["missing"])
        self.assertFalse(decision["runtime_mutation_authorized"])

    def test_runner_retirement_requires_all_capabilities(self) -> None:
        good = CapabilityRetirementEvidence(True, True, True, True, True)
        decision = evaluate_runner_retirement(
            self.data,
            "hermes-deals-audit",
            {
                "origin_path_audit": good,
                "approved_audit_command": good,
                "source_sync": good,
            },
        )
        self.assertEqual(decision["decision"], "ELIGIBLE")
        self.assertEqual(decision["missing"], ())
        self.assertFalse(decision["runtime_mutation_authorized"])

        bad = CapabilityRetirementEvidence(True, True, False, True, True)
        decision = evaluate_runner_retirement(
            self.data,
            "hermes-deals-release",
            {"production_release": bad},
        )
        self.assertEqual(decision["decision"], "NOT_ELIGIBLE")
        self.assertIn("production_release:genuine_canary_unproven", decision["missing"])

    def test_auto_live_reconciliation_never_grants_mutation(self) -> None:
        owner_required = reconcile_auto_live(
            self.data,
            "MANUAL_ROLLOUT_REQUIRED",
            exact_target_sha_ci_success=True,
            full_range_complete=True,
            manifest_active=True,
            static_operation_registered=True,
        )
        self.assertEqual(owner_required["decision"], "OWNER_REQUIRED")
        self.assertFalse(owner_required["automatic_mutation_allowed"])

        safe = reconcile_auto_live(
            self.data,
            "AUTO_DEPLOY_SAFE",
            exact_target_sha_ci_success=True,
            full_range_complete=True,
            manifest_active=True,
            static_operation_registered=True,
        )
        self.assertEqual(safe["decision"], "AUTO_DEPLOY_SAFE_CANDIDATE")
        self.assertFalse(safe["automatic_mutation_allowed"])
        self.assertFalse(safe["runtime_live_authority"])

        blocked = reconcile_auto_live(
            self.data,
            "AUTO_DEPLOY_SAFE",
            exact_target_sha_ci_success=True,
            full_range_complete=False,
            manifest_active=True,
            static_operation_registered=True,
        )
        self.assertEqual(blocked["decision"], "BLOCKED")

    def test_adversarial_matrix_covers_required_attack_classes(self) -> None:
        cases = {row["case"] for row in self.data["public_event_adversarial_matrix"]}
        self.assertTrue(
            {
                "fork_pull_request",
                "untrusted_issue_comment",
                "malformed_repository_dispatch",
                "unknown_operation_id",
                "caller_selected_command_path_argv_env",
                "unmerged_source_sha",
                "failed_exact_sha_ci",
                "wrong_owner_numeric_identity",
                "consumed_authorization_replay",
                "cross_capability_operation_swap",
            }.issubset(cases)
        )

    def test_all_mutation_flags_are_false(self) -> None:
        self.assertTrue(all(value is False for value in self.data["mutation"].values()))
        boundary = self.data["auto_live_and_full_boundary"]
        self.assertFalse(boundary["candidate_manifest_indexed"])
        self.assertFalse(boundary["candidate_static_operation_registered"])
        self.assertFalse(boundary["automatic_mutation_enabled"])
        self.assertFalse(boundary["auto_run_full_merge_authority_is_live_authority"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
