from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_phase4_activation_evidence import (  # noqa: E402
    evaluate_activation_handoff,
    evaluate_runner_smoke_preflight,
    evaluate_runtime_evidence,
    evaluate_source_sync_preflight,
    validate_contract,
    validate_runner_smoke_receipt,
)

CONTRACT = ROOT / "ops" / "contracts" / "hermes-deals-phase4-activation-evidence-v1.json"
MANIFEST = ROOT / "ops" / "deploy" / "auto-live-manifests" / "hermes-deals.json"
MANIFEST_INDEX = ROOT / "ops" / "deploy" / "auto-live-manifests.json"
EXECUTOR_OPERATIONS = ROOT / "ops" / "deploy" / "executor-operations.json"
BRIDGE = ROOT / "ops" / "deploy" / "hermes-deals-auto-live-a5-source-bridge.json"


class HermesDealsPhase4ActivationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.manifest_index = json.loads(MANIFEST_INDEX.read_text(encoding="utf-8"))
        cls.executor = json.loads(EXECUTOR_OPERATIONS.read_text(encoding="utf-8"))
        cls.bridge = json.loads(BRIDGE.read_text(encoding="utf-8"))
        validate_contract(cls.data)

    def test_exact_ten_terminal_source_results(self) -> None:
        jobs = self.data["jobs"]
        self.assertEqual([row["job"] for row in jobs], list(range(1, 11)))
        self.assertEqual(
            [row["result"] for row in jobs],
            [
                "DONE",
                "DONE",
                "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER",
                "SOURCE_READY_LIVE_LATER",
                "DONE",
                "DONE",
            ],
        )

    def test_frozen_provenance_matches_fresh_hermes_snapshot(self) -> None:
        provenance = self.data["capability_provenance"]
        self.assertEqual(
            provenance["source_sha"],
            "8015d6175b2b3c260fdb26546021bb17dcc5f4fb",
        )
        self.assertEqual(
            provenance["exact_sha_ci"]["workflow_blob"],
            "89059e310ab3270001daef43fd8f22a38b258c99",
        )
        capabilities = provenance["capabilities"]
        self.assertEqual(
            capabilities["approved_audit_command"]["workflow_blob"],
            "c9107e7597ff3ce1214cb32fb740346fa9d190aa",
        )
        self.assertEqual(
            capabilities["source_sync"]["dispatcher_blob"],
            "6110be33d1ed6bb394e650b187e17f612cfcb005",
        )
        self.assertEqual(
            capabilities["production_release"]["release_installer_blob"],
            "5ce5fa19e09db576b9daa9318c05bd9d8771900c",
        )
        self.assertEqual(provenance["removed_or_superseded_paths"], [])

    def test_runner_smoke_is_capability_specific_and_non_privileged_by_caller(self) -> None:
        smoke = self.data["runner_smoke_source_package"]
        self.assertEqual(smoke["operation_id"], "hermes-deals.runner-smoke-audit.v1")
        self.assertEqual(smoke["target_alias"], "hermes-deals-runner-smoke-audit")
        self.assertEqual(smoke["execution_identity"]["account"], "hermes-deals-audit-canary")
        self.assertEqual(smoke["execution_identity"]["login_shell"], "/usr/sbin/nologin")
        self.assertFalse(smoke["execution_identity"]["root"])
        self.assertFalse(smoke["execution_identity"]["docker_group"])
        self.assertEqual(smoke["execution_identity"]["supplementary_groups"], [])
        self.assertEqual(smoke["privileged_boundary_input"], ["authorization_issue_number"])
        self.assertTrue(smoke["no_overwrite"])
        self.assertTrue(smoke["nofollow_required"])
        self.assertFalse(smoke["caller_command_path_argv_environment_authority"])
        self.assertFalse(smoke["generic_sudo_or_root_shell"])
        self.assertFalse(smoke["legacy_generic_dispatcher_reuse_allowed"])
        self.assertFalse(smoke["runtime_installation_performed"])
        self.assertFalse(smoke["helper_execution_performed"])

    def test_runner_smoke_preflight_passes_source_only_and_never_executes(self) -> None:
        result = evaluate_runner_smoke_preflight(
            self.data,
            {
                "source_sha": "8015d6175b2b3c260fdb26546021bb17dcc5f4fb",
                "exact_sha_ci_success": True,
                "helper_identity_matches": True,
                "registration_identity_matches": True,
                "execution_identity_matches": True,
                "helper_owner_mode_matches": True,
                "registration_owner_mode_matches": True,
                "expected_inert_state": True,
            },
        )
        self.assertEqual(result["decision"], "SOURCE_PREFLIGHT_READY")
        self.assertFalse(result["helper_execution_allowed"])
        self.assertFalse(result["host_write_allowed"])
        self.assertFalse(result["runtime_live_authority"])

    def test_runner_smoke_preflight_fails_closed_on_identity_gap(self) -> None:
        result = evaluate_runner_smoke_preflight(
            self.data,
            {
                "source_sha": "8015d6175b2b3c260fdb26546021bb17dcc5f4fb",
                "exact_sha_ci_success": True,
                "helper_identity_matches": True,
                "registration_identity_matches": False,
                "execution_identity_matches": True,
                "helper_owner_mode_matches": True,
                "registration_owner_mode_matches": False,
                "expected_inert_state": True,
            },
        )
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("registration_identity_matches", result["missing"])
        self.assertIn("registration_owner_mode_matches", result["missing"])

    def test_runner_smoke_receipt_requires_real_sanitized_runtime_observation(self) -> None:
        receipt = {
            "schema": "rozkalns.hermes-deals.runner-smoke-canary-evidence.v1",
            "status": "PASS",
            "operation_id": "hermes-deals.runner-smoke-audit.v1",
            "target_alias": "hermes-deals-runner-smoke-audit",
            "source_sha": "8015d6175b2b3c260fdb26546021bb17dcc5f4fb",
            "authorization_issue_number": 999,
            "request_body_sha256": "a" * 64,
            "observed_at": "2026-09-11T18:30:00+00:00",
            "helper_identity_sha256": "b" * 64,
            "registration_identity_sha256": "c" * 64,
            "sanitized": True,
            "runtime_observation": True,
        }
        result = validate_runner_smoke_receipt(self.data, receipt)
        self.assertEqual(result["decision"], "VALID_PASS")
        receipt["runtime_observation"] = False
        self.assertEqual(
            validate_runner_smoke_receipt(self.data, receipt)["decision"],
            "BLOCKED",
        )

    def test_source_sync_remains_fixed_checkout_fast_forward_only_and_live_disabled(self) -> None:
        sync = self.data["source_sync_operation"]
        self.assertEqual(sync["canonical_checkout_identity"], "HERMES_DEALS_CANONICAL_SOURCE_CHECKOUT")
        self.assertEqual(sync["fixed_checkout_path"], "/home/andris/hermes-deals")
        self.assertEqual(sync["allowed_future_mutation"], "FAST_FORWARD_TO_EXACT_MERGED_REACHABLE_SHA")
        self.assertFalse(sync["caller_selectable_checkout_path"])
        self.assertFalse(sync["generic_git_subcommand_authority"])
        self.assertFalse(sync["caller_command_argv_environment_authority"])
        self.assertFalse(sync["runtime_execution_enabled"])
        self.assertFalse(sync["host_mutation_performed"])
        result = evaluate_source_sync_preflight(
            self.data,
            {
                "exact_target_sha": "8015d6175b2b3c260fdb26546021bb17dcc5f4fb",
                "merged_reachable": True,
                "exact_sha_ci_success": True,
                "canonical_checkout_identity_matches": True,
                "checkout_is_clean_main": True,
                "installed_dispatcher_identity_matches": True,
            },
        )
        self.assertEqual(result["decision"], "SOURCE_PREFLIGHT_READY")
        self.assertFalse(result["source_sync_execution_allowed"])

    def test_auto_live_a5_is_registered_but_explicitly_inert(self) -> None:
        self.assertFalse(self.manifest_index["execution_enabled"])
        indexed = {row["source_repository"]: row for row in self.manifest_index["manifests"]}
        self.assertIn("rozkalnsandris/hermes-deals", indexed)
        self.assertEqual(indexed["rozkalnsandris/hermes-deals"]["path"], "ops/deploy/auto-live-manifests/hermes-deals.json")
        self.assertEqual(self.manifest["activation"]["state"], "INACTIVE_SOURCE_ONLY")
        self.assertFalse(self.manifest["activation"]["automatic_mutation_enabled"])
        self.assertEqual(self.manifest["automatic_eligibility"]["eligible_classes"], ["AUTO_DEPLOY_SAFE"])
        self.assertEqual(self.manifest["classifier"]["rules"]["AUTO_DEPLOY_SAFE"]["exact_paths"], [])
        self.assertEqual(self.manifest["classifier"]["rules"]["AUTO_DEPLOY_SAFE"]["path_prefixes"], [])
        operations = {row["operation_id"]: row for row in self.executor["operations"]}
        operation = operations["hermes-deals.production-release.v1"]
        self.assertFalse(self.executor["execution_enabled"])
        self.assertFalse(operation["ordinary_live_all_eligible"])
        self.assertEqual(operation["rollback_policy"], "NONE")
        self.assertTrue(self.bridge["registration"]["global_executor_operation_registered"])
        self.assertTrue(self.bridge["registration"]["auto_live_manifest_indexed"])
        self.assertFalse(self.bridge["registration"]["registration_is_live_activation"])
        self.assertFalse(self.bridge["registration"]["global_execution_enabled"])
        self.assertEqual(self.bridge["registration"]["manifest_activation_state"], "INACTIVE_SOURCE_ONLY")
        self.assertTrue(all(value is False for value in self.bridge["mutation"].values()))

    def _runtime_receipts(self, now: datetime) -> list[dict[str, object]]:
        receipts: list[dict[str, object]] = []
        for capability_id in self.data["runtime_evidence_ingestion"]["capabilities"]:
            for slot in self.data["runtime_evidence_ingestion"]["required_runtime_slots"]:
                receipts.append(
                    {
                        "schema": "rozkalns.hermes-deals.phase4-runtime-evidence.v1",
                        "receipt_id": f"{capability_id}:{slot}",
                        "capability_id": capability_id,
                        "source_sha": "8015d6175b2b3c260fdb26546021bb17dcc5f4fb",
                        "slot": slot,
                        "observed_at": (now - timedelta(minutes=5)).isoformat(),
                        "status": "PASS",
                        "authentic": True,
                        "sanitized": True,
                        "current_runtime_observation": True,
                        "source_generated": False,
                        "conflict": False,
                    }
                )
        return receipts

    def test_runtime_evidence_missing_is_never_runner_retirement_eligible(self) -> None:
        now = datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc)
        result = evaluate_runtime_evidence(self.data, [], now=now)
        self.assertEqual(result["runners"]["hermes-deals-audit"]["decision"], "NOT_ELIGIBLE")
        self.assertEqual(result["runners"]["hermes-deals-release"]["decision"], "NOT_ELIGIBLE")
        self.assertFalse(result["runner_deregistration_authorized"])

    def test_complete_runtime_evidence_only_reaches_separate_owner_retirement_gate(self) -> None:
        now = datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc)
        result = evaluate_runtime_evidence(self.data, self._runtime_receipts(now), now=now)
        self.assertFalse(result["rejected"])
        self.assertEqual(
            result["runners"]["hermes-deals-audit"]["decision"],
            "ELIGIBLE_FOR_SEPARATE_OWNER_RETIREMENT_GATE",
        )
        self.assertEqual(
            result["runners"]["hermes-deals-release"]["decision"],
            "ELIGIBLE_FOR_SEPARATE_OWNER_RETIREMENT_GATE",
        )
        self.assertFalse(result["runners"]["hermes-deals-audit"]["runner_deregistration_authorized"])
        self.assertFalse(result["runners"]["hermes-deals-release"]["repository_settings_mutation_authorized"])

    def test_stale_or_source_generated_runtime_evidence_is_rejected(self) -> None:
        now = datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc)
        receipts = self._runtime_receipts(now)
        receipts[0]["observed_at"] = (now - timedelta(days=2)).isoformat()
        receipts[1]["source_generated"] = True
        result = evaluate_runtime_evidence(self.data, receipts, now=now)
        self.assertTrue(any("stale_or_future" in item for item in result["rejected"]))
        self.assertTrue(any("source_generated_forbidden" in item for item in result["rejected"]))
        self.assertEqual(result["runners"]["hermes-deals-audit"]["decision"], "NOT_ELIGIBLE")

    def test_handoff_names_one_first_future_live_gate_without_granting_live(self) -> None:
        result = evaluate_activation_handoff(self.data, True)
        self.assertEqual(result["decision"], "SOURCE_READY_FOR_EXPLICIT_FIRST_LIVE_GATE")
        self.assertEqual(result["first_future_live_gate"], "hermes-deals.runner-smoke-audit.install.v1")
        self.assertEqual(result["phase4_state"], "NOT_CLOSED_LIVE_EVIDENCE_REQUIRED")
        self.assertFalse(result["runtime_live_authority"])
        self.assertFalse(result["phase4_closed"])
        self.assertFalse(result["runner_retirement_authorized"])

    def test_bundle_contains_no_runtime_mutation_or_synthetic_authority(self) -> None:
        self.assertTrue(all(value is False for value in self.data["mutation"].values()))
        self.assertFalse(self.data["activation_handoff"]["merge_authorizes_live"])
        self.assertFalse(self.data["activation_handoff"]["runtime_live_authority"])
        self.assertEqual(self.data["runner_retirement"]["current_decision"], "NOT_ELIGIBLE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
