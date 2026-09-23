from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/lib/deploy_executor/weather_private_installer_boundary_refresh.py"
DESCRIPTOR_PATH = ROOT / "ops/deploy/weather-private-installer-boundary-refresh.json"

spec = importlib.util.spec_from_file_location("boundary_refresh", MODULE_PATH)
assert spec is not None and spec.loader is not None
boundary_refresh = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = boundary_refresh
spec.loader.exec_module(boundary_refresh)

CURRENT = "f" * 40
STALE = "c" * 40


def evidence(**overrides):
    values = dict(
        exact_source_sha=CURRENT,
        current_main_sha=CURRENT,
        exact_main_ci_success=True,
        manager_origin=boundary_refresh.REVIEWED_ORIGIN,
        manager_snapshot_stable=True,
        trusted_present=True,
        entrypoint_present=True,
        trusted_uid=0,
        trusted_gid=0,
        trusted_mode=0o755,
        trusted_origin=boundary_refresh.REVIEWED_ORIGIN,
        trusted_head_sha=STALE,
        trusted_detached=True,
        trusted_clean=True,
        trusted_head_reviewed_ancestor=True,
        trusted_entrypoint_matches_head=True,
        installed_uid=0,
        installed_gid=0,
        installed_mode=0o755,
        installed_entrypoint_matches_head=True,
        trusted_entrypoint_matches_exact_source=False,
        installed_entrypoint_matches_exact_source=False,
    )
    values.update(overrides)
    return boundary_refresh.BoundaryEvidence(**values)


class BoundaryRefreshTests(unittest.TestCase):
    def test_stale_reviewed_boundary_builds_exact_three_step_plan(self):
        plan = boundary_refresh.build_refresh_plan(evidence())
        self.assertEqual(plan.prior_state, "STALE")
        self.assertEqual(
            tuple((step.category, step.maximum) for step in plan.steps),
            boundary_refresh.MUTATION_BUDGET,
        )
        self.assertEqual(plan.trusted_checkout, boundary_refresh.TRUSTED_CHECKOUT)
        self.assertEqual(plan.entrypoint_destination, boundary_refresh.ENTRYPOINT_DESTINATION)
        self.assertEqual(plan.rollback_policy, "NONE")
        self.assertTrue(plan.authorization_consumed_before_first_mutation)
        self.assertFalse(plan.automatic_retry)
        self.assertFalse(plan.automatic_cleanup)
        self.assertFalse(plan.automatic_rollback)

    def test_exact_boundary_is_preconsume_noop(self):
        exact = evidence(
            trusted_head_sha=CURRENT,
            trusted_head_reviewed_ancestor=True,
            trusted_entrypoint_matches_exact_source=True,
            installed_entrypoint_matches_exact_source=True,
        )
        plan = boundary_refresh.build_refresh_plan(exact)
        self.assertEqual(plan.prior_state, "EXACT")
        self.assertEqual(plan.steps, ())

    def test_absent_boundary_must_use_initial_bootstrap(self):
        with self.assertRaisesRegex(boundary_refresh.BoundaryRefreshError, "initial bootstrap"):
            boundary_refresh.build_refresh_plan(
                evidence(
                    trusted_present=False,
                    entrypoint_present=False,
                    trusted_uid=None,
                    trusted_gid=None,
                    trusted_mode=None,
                    trusted_origin=None,
                    trusted_head_sha=None,
                    trusted_detached=False,
                    trusted_clean=False,
                    trusted_head_reviewed_ancestor=False,
                    trusted_entrypoint_matches_head=False,
                    installed_uid=None,
                    installed_gid=None,
                    installed_mode=None,
                    installed_entrypoint_matches_head=False,
                )
            )

    def test_wrong_origin_dirty_or_unreviewed_stale_state_fails_closed(self):
        cases = (
            dict(manager_origin="https://example.invalid/RPi5_main.git"),
            dict(trusted_origin="https://example.invalid/RPi5_main.git"),
            dict(trusted_clean=False),
            dict(trusted_detached=False),
            dict(trusted_head_reviewed_ancestor=False),
            dict(installed_entrypoint_matches_head=False),
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(boundary_refresh.BoundaryRefreshError):
                    boundary_refresh.build_refresh_plan(evidence(**changes))

    def test_source_head_ci_and_manager_snapshot_drift_fail_before_plan(self):
        cases = (
            dict(current_main_sha="a" * 40),
            dict(exact_main_ci_success=False),
            dict(manager_snapshot_stable=False),
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(boundary_refresh.BoundaryRefreshError):
                    boundary_refresh.build_refresh_plan(evidence(**changes))

    def test_fixed_targets_and_forbidden_authority_are_frozen(self):
        plan = boundary_refresh.build_refresh_plan(evidence())
        self.assertEqual(plan.manager_checkout_resolver, "repo-owner-home/RPi5_main")
        self.assertEqual(
            plan.trusted_checkout,
            "/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted",
        )
        self.assertEqual(
            plan.entrypoint_destination,
            "/usr/local/sbin/rpi5-weathernext-private-host-privileged-install",
        )
        self.assertFalse(plan.backend_install_allowed)
        self.assertFalse(plan.google_action_allowed)
        self.assertFalse(plan.bigquery_action_allowed)
        self.assertFalse(plan.sqlite_write_allowed)
        for step in plan.steps:
            self.assertNotIn("caller", step.target)
            self.assertNotIn("environment", step.target)

    def test_descriptor_matches_python_contract(self):
        descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
        self.assertEqual(descriptor["operation_id"], boundary_refresh.OPERATION_ID)
        self.assertEqual(descriptor["target_alias"], boundary_refresh.TARGET_ALIAS)
        self.assertEqual(descriptor["source_repository"], boundary_refresh.SOURCE_REPOSITORY)
        self.assertEqual(descriptor["reviewed_origin"], boundary_refresh.REVIEWED_ORIGIN)
        self.assertEqual(descriptor["trusted_checkout"], boundary_refresh.TRUSTED_CHECKOUT)
        self.assertEqual(
            descriptor["entrypoint_destination"],
            boundary_refresh.ENTRYPOINT_DESTINATION,
        )
        self.assertEqual(
            tuple(
                (item["category"], item["max_operations"])
                for item in descriptor["mutation_budget"]
            ),
            boundary_refresh.MUTATION_BUDGET,
        )
        self.assertEqual(descriptor["rollback_policy"], boundary_refresh.ROLLBACK_POLICY)
        self.assertFalse(descriptor["source_merge_authorizes_live"])
        self.assertFalse(descriptor["backend_install_allowed"])
        self.assertFalse(descriptor["google_action_allowed"])
        self.assertFalse(descriptor["bigquery_action_allowed"])
        self.assertFalse(descriptor["sqlite_write_allowed"])


if __name__ == "__main__":
    unittest.main()
