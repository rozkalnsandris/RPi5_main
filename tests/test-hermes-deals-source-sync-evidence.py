import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_source_sync_evidence import (  # noqa: E402
    POSTCONDITION,
    evaluate_postcondition,
    evaluate_preflight,
    validate_canary_receipt,
    validate_contract,
)

CONTRACT_PATH = ROOT / "ops/contracts/hermes-deals-source-sync-evidence-v1.json"
STATIC_PATH = ROOT / "ops/contracts/hermes-deals-source-sync-v1.json"
MODULE_PATH = ROOT / "ops/lib/deploy_executor/hermes_deals_source_sync_evidence.py"
WORKFLOW_PATH = ROOT / ".github/workflows/hermes-deals-source-sync-source.yml"

TARGET = "f105f972bef13864b392bd4e3edc555bcd0ae2e9"
HEAD = "8015d6175b2b3c260fdb26546021bb17dcc5f4fb"
RPI5 = "6219f91751063340a64453b5e525fca4283567ac"

class HermesDealsSourceSyncEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text())
        cls.static = json.loads(STATIC_PATH.read_text())

    def preflight(self):
        fixed = self.contract["fixed_identity"]
        return {"target_sha": TARGET, "current_head_sha": HEAD, "repository": fixed["repository"], "repository_id": fixed["repository_id"], "remote_url": fixed["remote_url"], "checkout_identity": fixed["checkout_identity"], "branch": fixed["branch"], "ref": fixed["ref"], "upstream": fixed["upstream"], "worktree": True, "clean": True, "merged_same_repository_pr": True, "target_reachable_from_current_main": True, "ci_mode": "EXACT_TARGET_SHA_CI", "ci_proof_valid": True, "workflow_blob": self.contract["source_anchors"]["workflow_blob"], "target_is_fast_forward_descendant": True}

    def postcondition(self):
        fixed = self.contract["fixed_identity"]
        return {"head_after": TARGET, "repository": fixed["repository"], "repository_id": fixed["repository_id"], "remote_url": fixed["remote_url"], "checkout_identity": fixed["checkout_identity"], "branch": fixed["branch"], "ref": fixed["ref"], "upstream": fixed["upstream"], "clean": True}

    def receipt(self):
        values = {field: False for field in self.contract["canary_evidence"]["forbidden_mutation_fields"]}
        values.update({"schema": self.contract["canary_evidence"]["schema"], "status": "PASS", "reason_code": None, "operation_id": "hermes-deals.source-sync.v1", "future_live_gate_id": "hermes-deals.source-sync.sync.v1", "target_alias": "hermes-deals-source-sync", "source_repository": "rozkalnsandris/hermes-deals", "source_repository_id": 1317143994, "rpi5_source_sha": RPI5, "target_sha": TARGET, "authorization_issue_number": 999, "request_body_sha256": "a" * 64, "head_before": HEAD, "head_after": TARGET, "preflight_decision": "PASS", "fast_forward_proven": True, "mutation_capable_entry": True, "network_fetch_attempted": True, "source_checkout_head_changed": True, "postcondition_result": POSTCONDITION, "sanitized": True, "runtime_observation": True})
        return values

    def test_contract_is_bound_and_live_disabled(self):
        validate_contract(self.contract)
        self.assertEqual(self.contract["status"], "SOURCE_READY_LIVE_LATER")
        self.assertFalse(self.contract["operation"]["global_execution_enabled"])
        self.assertFalse(self.contract["operation"]["external_apply_entrypoint_enabled"])
        self.assertFalse(self.contract["job_boundary"]["runtime_live_authority"])
        self.assertEqual(self.static["job_7_source"]["contract_path"], "ops/contracts/hermes-deals-source-sync-evidence-v1.json")

    def test_valid_preflight_is_read_only_ready_but_not_execution_authority(self):
        result = evaluate_preflight(self.contract, TARGET, self.preflight())
        self.assertEqual(result["decision"], "PASS")
        self.assertTrue(result["fast_forward_proven"])
        self.assertFalse(result["source_sync_execution_allowed"])

    def test_preflight_rejects_generic_authority_field(self):
        observed = self.preflight(); observed["checkout_path"] = "/tmp/caller-selected"
        result = evaluate_preflight(self.contract, TARGET, observed)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertEqual(result["unexpected"], ("checkout_path",))

    def test_preflight_rejects_identity_dirty_target_and_provenance_drift(self):
        mutations = (("remote_url", "https://example.invalid/repo.git", "REMOTE_IDENTITY_DRIFT"), ("upstream", "evil/main", "BRANCH_REF_UPSTREAM_DRIFT"), ("clean", False, "DIRTY_CHECKOUT"), ("target_is_fast_forward_descendant", False, "NON_FAST_FORWARD_TARGET"), ("ci_proof_valid", False, "CI_PROOF_INVALID"), ("merged_same_repository_pr", False, "MERGED_PR_PROVENANCE_MISSING"), ("target_reachable_from_current_main", False, "TARGET_NOT_REACHABLE_FROM_MAIN"))
        for field, value, reason in mutations:
            with self.subTest(field=field):
                observed = self.preflight(); observed[field] = value
                self.assertIn(reason, evaluate_preflight(self.contract, TARGET, observed)["reason_codes"])

    def test_preflight_rejects_wrong_or_malformed_authorized_target(self):
        self.assertIn("TARGET_SHA_MISMATCH", evaluate_preflight(self.contract, "x", self.preflight())["reason_codes"])
        observed = self.preflight(); observed["target_sha"] = "0" * 40
        self.assertIn("TARGET_SHA_MISMATCH", evaluate_preflight(self.contract, TARGET, observed)["reason_codes"])

    def test_postcondition_is_exact_target_clean_main_and_identity(self):
        result = evaluate_postcondition(self.contract, TARGET, self.postcondition())
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["predicate"], POSTCONDITION)
        observed = self.postcondition(); observed["head_after"] = HEAD
        self.assertIn("HEAD_NOT_EXACT_TARGET", evaluate_postcondition(self.contract, TARGET, observed)["reason_codes"])
        observed = self.postcondition(); observed["clean"] = False
        self.assertIn("CHECKOUT_NOT_CLEAN", evaluate_postcondition(self.contract, TARGET, observed)["reason_codes"])

    def test_receipt_schema_is_closed_and_validates_real_pass(self):
        receipt = self.receipt()
        self.assertEqual(validate_canary_receipt(self.contract, RPI5, TARGET, receipt)["decision"], "VALID_PASS")
        receipt["command"] = "git reset --hard"
        self.assertEqual(validate_canary_receipt(self.contract, RPI5, TARGET, receipt)["reason"], "FIELD_DRIFT")

    def test_receipt_rejects_forbidden_mutation_and_synthetic_pass(self):
        receipt = self.receipt(); receipt["systemd_change_performed"] = True
        self.assertEqual(validate_canary_receipt(self.contract, RPI5, TARGET, receipt)["reason"], "FORBIDDEN_MUTATION_ATTESTED")
        receipt = self.receipt(); receipt["runtime_observation"] = False
        self.assertEqual(validate_canary_receipt(self.contract, RPI5, TARGET, receipt)["reason"], "UNSANITIZED_OR_SYNTHETIC")

    def test_blocked_receipt_is_representable_without_synthetic_success(self):
        receipt = self.receipt(); receipt.update({"status": "BLOCKED", "reason_code": "PREFLIGHT_DRIFT", "mutation_capable_entry": False, "network_fetch_attempted": False, "source_checkout_head_changed": False, "head_after": HEAD, "postcondition_result": "NOT_EVALUATED"})
        self.assertEqual(validate_canary_receipt(self.contract, RPI5, TARGET, receipt)["decision"], "VALID_BLOCKED")

    def test_future_owner_gate_and_failure_semantics_are_frozen(self):
        gate = self.contract["future_owner_gate"]
        self.assertEqual(gate["allowed_mutation"], "FAST_FORWARD_TO_EXACT_AUTHORIZED_SHA_ONLY")
        self.assertEqual(gate["max_operations"], 1)
        self.assertEqual(gate["rollback_policy"], "NONE")
        failure = self.contract["replay_failure"]
        self.assertEqual(failure["authorization_consumed_at"], "MUTATION_CAPABLE_ENTRY")
        self.assertFalse(failure["automatic_retry_after_start"])
        self.assertFalse(failure["automatic_cleanup_after_start"])
        self.assertFalse(failure["automatic_rollback_after_start"])
        self.assertFalse(failure["alternate_mutation_path_after_start"])

    def test_module_has_no_mutation_or_shell_transport(self):
        source = MODULE_PATH.read_text()
        for fragment in ("subprocess", "os.system", "git fetch", "git merge", "git reset", "git checkout", "git clean", "bash -c", "sh -c"):
            self.assertNotIn(fragment, source)

    def test_focused_ci_executes_job7_test(self):
        workflow = WORKFLOW_PATH.read_text()
        self.assertIn("test-hermes-deals-source-sync-evidence.py", workflow)
        self.assertIn("hermes-deals-source-sync-evidence-v1.json", workflow)
        self.assertIn("hermes_deals_source_sync_evidence.py", workflow)

if __name__ == "__main__":
    unittest.main()
