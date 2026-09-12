import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops/contracts/hermes-deals-source-sync-v1.json"
REGISTRY_PATH = ROOT / "ops/deploy/executor-operations.json"
DOC_PATH = ROOT / "docs/HERMES_DEALS_SOURCE_SYNC.md"


class HermesDealsSourceSyncContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text())
        cls.registry = json.loads(REGISTRY_PATH.read_text())
        cls.operation = next(
            item for item in cls.registry["operations"]
            if item["operation_id"] == "hermes-deals.source-sync.v1"
        )

    def test_operation_is_strict_and_globally_disabled(self):
        self.assertFalse(self.registry["execution_enabled"])
        self.assertEqual(self.operation["authorization_class"], "STRICT")
        self.assertFalse(self.operation["ordinary_live_all_eligible"])
        self.assertEqual(self.operation["rollback_policy"], "NONE")
        self.assertEqual(self.contract["status"], "SOURCE_CONTRACT_ONLY_LIVE_DISABLED")
        self.assertFalse(self.contract["operation"]["global_execution_enabled"])
        self.assertFalse(self.contract["operation"]["external_apply_entrypoint_enabled"])
        self.assertFalse(self.contract["operation"]["runtime_live_authority"])

    def test_fixed_identity_matches_reviewed_workflow(self):
        fixed = self.contract["fixed_checkout_identity"]
        anchors = self.contract["source_anchors"]
        self.assertEqual(fixed["path"], "/home/andris/hermes-deals")
        self.assertEqual(fixed["branch"], "main")
        self.assertEqual(fixed["ref"], "refs/heads/main")
        self.assertEqual(fixed["upstream"], "origin/main")
        self.assertEqual(fixed["repository"], "rozkalnsandris/hermes-deals")
        self.assertEqual(fixed["repository_id"], 1317143994)
        self.assertFalse(fixed["caller_selectable"])
        self.assertEqual(anchors["workflow_path"], ".github/workflows/rpi-source-sync.yml")
        self.assertEqual(anchors["workflow_blob"], "b2f4eee1d1c503cf0c47b6099e748d6e6fd6d560")
        self.assertEqual(self.operation["queue_match"]["repository_entrypoint"], anchors["workflow_path"])
        self.assertIn("workflow-blob:" + anchors["workflow_blob"], self.operation["dependencies"])

    def test_target_provenance_is_exact_and_reviewed(self):
        provenance = self.contract["provenance"]
        self.assertTrue(provenance["same_repository_pr_required"])
        self.assertTrue(provenance["merged_pr_required"])
        self.assertTrue(provenance["target_reachable_from_current_main_required"])
        self.assertTrue(provenance["exact_target_sha_ci_success_required"])
        self.assertTrue(provenance["tree_equivalent_exact_pr_head_ci_allowed_when_explicitly_validated"])

    def test_no_generic_or_caller_selected_authority(self):
        authority = self.contract["target_authority"]
        for key, value in authority.items():
            if key.startswith("caller_selectable_") or key == "generic_shell_authority":
                self.assertFalse(value, key)
        exclusions = "\n".join(self.operation["exclusions"]).lower()
        for fragment in ("git subcommand", "checkout path", "remote url", "argv", "environment", "generic privileged shell"):
            self.assertIn(fragment, exclusions)

    def test_future_mutation_is_fast_forward_only(self):
        mutation = self.contract["future_mutation"]
        self.assertEqual(mutation["allowed"], "FAST_FORWARD_TO_EXACT_AUTHORIZED_SHA_ONLY")
        self.assertEqual(mutation["max_operations"], 1)
        self.assertFalse(mutation["network_fetch_in_job_6"])
        self.assertFalse(mutation["checkout_write_in_job_6"])
        self.assertFalse(mutation["dispatcher_invocation_in_job_6"])
        for key in ("reset_allowed", "force_checkout_allowed", "rebase_allowed", "hard_clean_allowed", "history_rewrite_allowed", "arbitrary_ref_fetch_allowed"):
            self.assertFalse(mutation[key], key)
        self.assertEqual(self.operation["mutation_budget"], [{"category": "source-checkout-fast-forward", "max_operations": 1}])

    def test_future_preflight_and_postconditions_are_bounded(self):
        preflight = "\n".join(self.contract["future_preflight"]).lower()
        post = "\n".join(self.contract["future_postconditions"]).lower()
        for fragment in ("git worktree", "remote url", "origin/main", "checkout is clean", "fast-forward"):
            self.assertIn(fragment, preflight)
        for fragment in ("head equals exact authorized target sha", "checkout is clean", "remote", "production deploy"):
            self.assertIn(fragment, post)

    def test_job6_has_no_runtime_entrypoint_or_authority_record(self):
        boundary = self.contract["job_boundary"]
        self.assertEqual(boundary["job_6"], "STATIC_OPERATION_AND_ADAPTER_CONTRACT_ONLY")
        self.assertEqual(boundary["job_7"], "EXECUTABLE_PREFLIGHT_POSTCONDITION_AND_SANITIZED_CANARY_EVIDENCE")
        self.assertTrue(boundary["live_authorization_required_before_future_mutation"])
        self.assertFalse(boundary["ready_or_live_auth_created_here"])
        self.assertFalse(boundary["runtime_receipt_created_here"])
        self.assertFalse(self.contract["source_anchors"]["source_runtime_state_inferred"])

    def test_fail_closed_has_no_automatic_recovery_after_start(self):
        policy = self.contract["fail_closed"]
        self.assertEqual(policy["non_fast_forward"], "REJECT")
        self.assertEqual(policy["dirty_checkout"], "REJECT")
        self.assertEqual(policy["identity_drift"], "REJECT")
        self.assertEqual(policy["provenance_or_ci_drift"], "REJECT")
        self.assertFalse(policy["post_mutation_automatic_retry"])
        self.assertFalse(policy["post_mutation_automatic_cleanup"])
        self.assertFalse(policy["post_mutation_automatic_rollback"])
        self.assertFalse(policy["alternate_mutation_path_after_start"])

    def test_documentation_binds_exact_contract(self):
        doc = DOC_PATH.read_text()
        for value in (
            "hermes-deals.source-sync.v1",
            "/home/andris/hermes-deals",
            "refs/heads/main",
            "origin/main",
            "b2f4eee1d1c503cf0c47b6099e748d6e6fd6d560",
            "fast-forward",
            "Job 7",
        ):
            self.assertIn(value, doc)


if __name__ == "__main__":
    unittest.main()
