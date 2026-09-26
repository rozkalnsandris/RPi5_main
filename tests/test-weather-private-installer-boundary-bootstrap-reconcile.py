#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import stat
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_installer_boundary_bootstrap_reconcile as reconcile

CONTRACT = ROOT / "ops/contracts/weathernext-private-installer-boundary-bootstrap-v1.json"


def evidence(**overrides):
    values = {
        "exact_source_sha": "a" * 40,
        "current_main_sha": "a" * 40,
        "exact_main_ci_success": True,
        "source_git_mode": reconcile.SOURCE_GIT_MODE,
        "source_git_blob": "b" * 40,
        "source_sha256": "c" * 64,
        "installed_is_regular": True,
        "installed_uid": reconcile.ROOT_UID,
        "installed_gid": reconcile.ROOT_GID,
        "installed_mode": reconcile.DESTINATION_MODE,
        "installed_nlink": 1,
        "installed_sha256": "c" * 64,
    }
    values.update(overrides)
    return reconcile.BootstrapEvidence(**values)


class WeatherNextBootstrapReconcileTests(unittest.TestCase):
    def test_exact_current_is_preconsume_noop(self) -> None:
        plan = reconcile.build_reconcile_plan(evidence())
        self.assertEqual(plan.prior_state, "EXACT")
        self.assertEqual(plan.steps, ())
        public = reconcile.public_plan(plan)
        self.assertEqual(public["mutation_budget"], [])
        self.assertEqual(public["source_git_mode"], "100755")
        self.assertFalse(public["automatic_retry"])
        self.assertFalse(public["automatic_cleanup"])
        self.assertFalse(public["automatic_rollback"])
        self.assertFalse(public["installer_boundary_refresh_allowed"])

    def test_recognized_predecessor_yields_exactly_one_fixed_replacement(self) -> None:
        plan = reconcile.build_reconcile_plan(
            evidence(installed_sha256=reconcile.RECOGNIZED_PREDECESSOR_SHA256)
        )
        self.assertEqual(plan.prior_state, "RECOGNIZED_PREDECESSOR")
        self.assertEqual(len(plan.steps), 1)
        step = plan.steps[0]
        self.assertEqual(step.category, reconcile.MUTATION_BUDGET[0][0])
        self.assertEqual(step.maximum, 1)
        self.assertEqual(step.target, reconcile.DESTINATION)
        public = reconcile.public_plan(plan)
        self.assertEqual(
            public["mutation_budget"],
            [{"category": reconcile.MUTATION_BUDGET[0][0], "max_operations": 1}],
        )
        self.assertEqual(public["rollback_policy"], "NONE")

    def test_unknown_preimage_stops_before_mutation(self) -> None:
        with self.assertRaisesRegex(reconcile.BootstrapReconcileError, "recognized preimage"):
            reconcile.build_reconcile_plan(evidence(installed_sha256="d" * 64))

    def test_fixed_metadata_conflicts_stop(self) -> None:
        conflicts = (
            {"installed_is_regular": False},
            {"installed_uid": reconcile.ROOT_UID + 1},
            {"installed_gid": reconcile.ROOT_GID + 1},
            {"installed_mode": 0o775},
            {"installed_nlink": 2},
        )
        for changed in conflicts:
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(reconcile.BootstrapReconcileError, "recognized preimage"):
                    reconcile.build_reconcile_plan(evidence(**changed))

    def test_source_identity_must_be_exact_current_executable_git_blob(self) -> None:
        cases = (
            ({"current_main_sha": "e" * 40}, "source/head drifted"),
            ({"exact_main_ci_success": False}, "required CI"),
            ({"source_git_mode": "100644"}, "Git mode"),
            ({"source_git_blob": "not-a-sha"}, "Git blob"),
            ({"source_sha256": "not-a-digest"}, "source digest"),
        )
        for changed, message in cases:
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(reconcile.BootstrapReconcileError, message):
                    reconcile.build_reconcile_plan(evidence(**changed))

    def test_contract_derives_target_from_exact_current_main(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        item = contract["reconciliation"]
        self.assertEqual(item["implementation_issue"], 743)
        self.assertEqual(item["operation_id"], reconcile.OPERATION_ID)
        self.assertEqual(item["target_alias"], reconcile.TARGET_ALIAS)
        self.assertEqual(item["source_repository"], reconcile.SOURCE_REPOSITORY)
        self.assertEqual(item["source_path"], reconcile.SOURCE_PATH)
        self.assertEqual(item["destination"], reconcile.DESTINATION)
        self.assertEqual(item["required_mode"], "0755")
        self.assertEqual(item["target_identity"]["source_ref"], "exact-current-main")
        self.assertEqual(item["target_identity"]["required_git_mode"], "100755")
        self.assertTrue(item["target_identity"]["git_blob_derived_from_exact_current_main"])
        self.assertTrue(item["target_identity"]["sha256_derived_from_exact_current_main_bytes"])
        self.assertTrue(item["target_identity"]["contents_must_match_git_blob"])
        self.assertTrue(item["target_identity"]["required_exact_main_ci"])
        self.assertEqual(
            item["recognized_preimage_sha256"],
            [reconcile.RECOGNIZED_PREDECESSOR_SHA256],
        )
        self.assertTrue(item["exact_current_is_preconsume_noop"])
        self.assertTrue(item["unknown_preimage_stops_before_mutation"])
        self.assertEqual(
            item["mutation_budget"],
            [{"category": reconcile.MUTATION_BUDGET[0][0], "max_operations": 1}],
        )
        self.assertTrue(item["separate_from_installer_boundary_refresh_budget"])
        self.assertEqual(item["rollback_policy"], "NONE")
        self.assertFalse(item["automatic_retry"])
        self.assertFalse(item["automatic_cleanup"])
        self.assertFalse(item["automatic_rollback"])
        self.assertFalse(item["source_merge_authorizes_live"])
        self.assertFalse(item["runtime_live_authority"])
        self.assertNotIn("current_reviewed_git_blob", item)
        self.assertNotIn("current_reviewed_sha256", item)

    def test_fixed_regular_metadata_helper_is_strict(self) -> None:
        regular = stat.S_IFREG | 0o755
        self.assertTrue(
            reconcile.metadata_is_fixed_regular(
                regular,
                reconcile.ROOT_UID,
                reconcile.ROOT_GID,
                1,
            )
        )
        self.assertFalse(
            reconcile.metadata_is_fixed_regular(
                stat.S_IFLNK | 0o755,
                reconcile.ROOT_UID,
                reconcile.ROOT_GID,
                1,
            )
        )
        self.assertFalse(
            reconcile.metadata_is_fixed_regular(
                stat.S_IFREG | 0o775,
                reconcile.ROOT_UID,
                reconcile.ROOT_GID,
                1,
            )
        )


if __name__ == "__main__":
    unittest.main()
