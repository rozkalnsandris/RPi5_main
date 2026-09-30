from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_installer_boundary_bootstrap_reachability as reachability

CONTRACT = ROOT / "ops/contracts/weathernext-private-installer-boundary-bootstrap-v1.json"
DISPATCH = ROOT / "ops/lib/deploy_executor/weather_private_privileged_dispatch.py"


class BootstrapReachabilityTests(unittest.TestCase):
    def evidence(self, **overrides):
        value = reachability.BootstrapReachabilityEvidence(
            exact_source_sha="a" * 40,
            current_main_sha="a" * 40,
            exact_main_ci_success=True,
            manager_head_sha="b" * 40,
            manager_branch_ref=reachability.MANAGER_BRANCH_REF,
            manager_local_main_sha="b" * 40,
            manager_origin=reachability.REVIEWED_ORIGIN,
            manager_clean=True,
            manager_head_reviewed_ancestor=True,
            manager_local_main_reviewed_ancestor_of_head=True,
            manager_runtime_pair_exact_current=False,
            installed_bootstrap_recognized=True,
            installed_privileged_dispatch_exact_current=False,
            installed_privileged_dispatch_reconcile_route=False,
        )
        return replace(value, **overrides)

    def test_stale_attached_manager_requires_fixed_fetch_and_fast_forward(self):
        plan = reachability.build_reachability_plan(self.evidence())
        self.assertEqual(plan.decision, "MANAGER_SYNC_REQUIRED")
        self.assertEqual(plan.next_operation_id, reachability.MANAGER_SYNC_OPERATION_ID)
        self.assertIsNone(plan.execution_entrypoint)
        self.assertEqual(plan.manager_branch_ref, "refs/heads/main")
        self.assertEqual(plan.fixed_environment, reachability.MANAGER_SYNC_FIXED_ENV)
        self.assertEqual(
            [(step.category, step.maximum) for step in plan.steps],
            [
                reachability.MANAGER_SYNC_MUTATION_BUDGET[0],
                reachability.MANAGER_SYNC_MUTATION_BUDGET[2],
            ],
        )
        self.assertEqual(plan.steps[0].argv, reachability.MANAGER_FETCH_ARGV)
        self.assertEqual(plan.steps[1].argv, reachability.MANAGER_FAST_FORWARD_ARGV)
        self.assertNotIn(reachability.MANAGER_SWITCH_MAIN_ARGV, [step.argv for step in plan.steps])
        self.assertEqual(plan.live_gate, "COMPOSITE_LIVE_REQUIRED")
        self.assertEqual(plan.rollback_policy, "NONE")
        self.assertFalse(plan.automatic_retry)
        self.assertFalse(plan.automatic_cleanup)
        self.assertFalse(plan.automatic_rollback)

    def test_reviewed_detached_manager_requires_fetch_switch_main_and_fast_forward(self):
        plan = reachability.build_reachability_plan(
            self.evidence(
                manager_branch_ref=reachability.MANAGER_DETACHED_REF,
                manager_local_main_sha="c" * 40,
                manager_runtime_pair_exact_current=True,
            )
        )
        self.assertEqual(plan.decision, "MANAGER_SYNC_REQUIRED")
        self.assertEqual(plan.next_operation_id, reachability.MANAGER_SYNC_OPERATION_ID)
        self.assertIsNone(plan.execution_entrypoint)
        self.assertEqual(
            [(step.category, step.maximum, step.argv) for step in plan.steps],
            [
                (*reachability.MANAGER_SYNC_MUTATION_BUDGET[0], reachability.MANAGER_FETCH_ARGV),
                (*reachability.MANAGER_SYNC_MUTATION_BUDGET[1], reachability.MANAGER_SWITCH_MAIN_ARGV),
                (*reachability.MANAGER_SYNC_MUTATION_BUDGET[2], reachability.MANAGER_FAST_FORWARD_ARGV),
            ],
        )
        for argv in (
            reachability.MANAGER_FETCH_ARGV,
            reachability.MANAGER_SWITCH_MAIN_ARGV,
            reachability.MANAGER_FAST_FORWARD_ARGV,
        ):
            self.assertIn("core.hooksPath=/dev/null", argv)
            self.assertIn("credential.helper=", argv)
            self.assertIn("protocol.file.allow=never", argv)
        self.assertEqual(reachability.MANAGER_SWITCH_MAIN_ARGV[-2:], ("switch", "main"))

    def test_exact_runtime_pair_makes_installed_bootstrap_the_first_privileged_hop(self):
        plan = reachability.build_reachability_plan(
            self.evidence(manager_runtime_pair_exact_current=True)
        )
        self.assertEqual(plan.decision, "BOUNDARY_REFRESH_REQUIRED")
        self.assertEqual(plan.next_operation_id, reachability.BOUNDARY_REFRESH_OPERATION_ID)
        self.assertEqual(plan.execution_entrypoint, reachability.INSTALLED_BOOTSTRAP)
        self.assertEqual(plan.steps, ())

    def test_exact_current_dispatch_with_fixed_route_makes_reconcile_reachable(self):
        plan = reachability.build_reachability_plan(
            self.evidence(
                installed_privileged_dispatch_exact_current=True,
                installed_privileged_dispatch_reconcile_route=True,
            )
        )
        self.assertEqual(plan.decision, "RECONCILE_REACHABLE")
        self.assertEqual(plan.next_operation_id, reachability.BOOTSTRAP_RECONCILE_OPERATION_ID)
        self.assertEqual(plan.execution_entrypoint, reachability.INSTALLED_PRIVILEGED_DISPATCH)
        self.assertEqual(plan.steps, ())

    def test_missing_unreviewed_or_drifted_transport_provenance_fails_closed(self):
        cases = (
            self.evidence(current_main_sha="c" * 40),
            self.evidence(exact_main_ci_success=False),
            self.evidence(manager_branch_ref="refs/heads/feature"),
            self.evidence(manager_local_main_sha="invalid"),
            self.evidence(manager_local_main_sha="c" * 40),
            self.evidence(manager_origin="https://example.invalid/unreviewed.git"),
            self.evidence(manager_clean=False),
            self.evidence(manager_head_reviewed_ancestor=False),
            self.evidence(installed_bootstrap_recognized=False),
            self.evidence(
                installed_privileged_dispatch_exact_current=True,
                installed_privileged_dispatch_reconcile_route=False,
            ),
            self.evidence(
                installed_privileged_dispatch_exact_current=False,
                installed_privileged_dispatch_reconcile_route=True,
            ),
            self.evidence(
                manager_head_sha="a" * 40,
                manager_local_main_sha="a" * 40,
                manager_runtime_pair_exact_current=False,
            ),
            self.evidence(
                manager_branch_ref=reachability.MANAGER_DETACHED_REF,
                manager_local_main_sha="c" * 40,
                manager_local_main_reviewed_ancestor_of_head=False,
            ),
            self.evidence(
                manager_branch_ref=reachability.MANAGER_DETACHED_REF,
                manager_local_main_sha="b" * 40,
            ),
            self.evidence(
                manager_branch_ref=reachability.MANAGER_DETACHED_REF,
                manager_local_main_sha="c" * 40,
                manager_head_reviewed_ancestor=False,
            ),
        )
        for evidence in cases:
            with self.subTest(evidence=evidence):
                with self.assertRaises(reachability.BootstrapReachabilityContractError):
                    reachability.build_reachability_plan(evidence)

    def test_public_plan_exposes_only_fixed_manager_sync_authority(self):
        attached = reachability.public_plan(reachability.build_reachability_plan(self.evidence()))
        detached = reachability.public_plan(
            reachability.build_reachability_plan(
                self.evidence(
                    manager_branch_ref=reachability.MANAGER_DETACHED_REF,
                    manager_local_main_sha="c" * 40,
                )
            )
        )
        self.assertEqual(attached["manager_branch_ref"], "refs/heads/main")
        self.assertEqual(
            attached["fixed_environment"],
            [
                {"name": name, "value": value}
                for name, value in reachability.MANAGER_SYNC_FIXED_ENV
            ],
        )
        self.assertEqual(
            [item["argv"] for item in attached["mutation_budget"]],
            [list(reachability.MANAGER_FETCH_ARGV), list(reachability.MANAGER_FAST_FORWARD_ARGV)],
        )
        self.assertEqual(
            [item["argv"] for item in detached["mutation_budget"]],
            [
                list(reachability.MANAGER_FETCH_ARGV),
                list(reachability.MANAGER_SWITCH_MAIN_ARGV),
                list(reachability.MANAGER_FAST_FORWARD_ARGV),
            ],
        )

    def test_contract_binds_detached_recovery_without_generic_branch_authority(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        recovery = contract["reconciliation"]["reachability_recovery"]
        sync = recovery["manager_source_sync_prerequisite"]
        self.assertEqual(recovery["recovery_issue"], 770)
        self.assertEqual(
            recovery["planner_module"],
            "ops/lib/deploy_executor/weather_private_installer_boundary_bootstrap_reachability.py",
        )
        self.assertEqual(sync["operation_id"], reachability.MANAGER_SYNC_OPERATION_ID)
        self.assertEqual(sync["required_attached_branch_ref"], reachability.MANAGER_BRANCH_REF)
        self.assertEqual(sync["accepted_detached_branch_ref"], reachability.MANAGER_DETACHED_REF)
        self.assertTrue(sync["detached_recovery_allowed"])
        self.assertTrue(sync["requires_local_main_reviewed_ancestor_of_detached_head"])
        self.assertTrue(sync["requires_detached_head_reviewed_ancestor_of_exact_current_main"])
        self.assertEqual(
            sync["fixed_environment"],
            [
                {"name": name, "value": value}
                for name, value in reachability.MANAGER_SYNC_FIXED_ENV
            ],
        )
        self.assertEqual(
            sync["allowed_argv"],
            [
                list(reachability.MANAGER_FETCH_ARGV),
                list(reachability.MANAGER_SWITCH_MAIN_ARGV),
                list(reachability.MANAGER_FAST_FORWARD_ARGV),
            ],
        )
        self.assertEqual(
            [(item["category"], item["max_operations"]) for item in sync["mutation_budget"]],
            list(reachability.MANAGER_SYNC_MUTATION_BUDGET),
        )
        forbidden = set(sync["explicitly_forbidden"])
        self.assertTrue(
            {
                "reset",
                "clean",
                "pull",
                "rebase",
                "force",
                "arbitrary-branch-switch",
                "caller-selected-branch",
                "caller-selected-argv",
            }.issubset(forbidden)
        )
        self.assertNotIn("branch-switch", forbidden)
        self.assertTrue(sync["owner_live_authorization_required"])
        self.assertFalse(sync["source_merge_authorizes_live"])
        self.assertEqual(
            recovery["first_privileged_hop"]["entrypoint"],
            reachability.INSTALLED_BOOTSTRAP,
        )
        self.assertFalse(recovery["legacy_noninstalled_oneshot"]["privileged_execution_transport"])

    def test_current_dispatch_contains_the_fixed_reconcile_route(self):
        source = DISPATCH.read_text(encoding="utf-8")
        self.assertIn("BOOTSTRAP_RECONCILE_OPERATION_ID", source)
        self.assertIn("run_privileged_bootstrap_reconcile", source)
        self.assertIn("if operation == BOOTSTRAP_RECONCILE_OPERATION_ID", source)


if __name__ == "__main__":
    unittest.main()
