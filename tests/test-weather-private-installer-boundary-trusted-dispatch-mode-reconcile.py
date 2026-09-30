from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "ops/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from deploy_executor import weather_private_installer_boundary_trusted_dispatch_mode_reconcile as reconcile  # noqa: E402


def evidence(**overrides: object) -> reconcile.TrustedDispatchEvidence:
    values: dict[str, object] = {
        "source_sha": "a" * 40,
        "current_main_sha": "a" * 40,
        "exact_main_ci_success": True,
        "trusted_present": True,
        "trusted_origin": reconcile.REVIEWED_ORIGIN,
        "trusted_head": reconcile.KNOWN_STALE_HEAD,
        "trusted_clean": True,
        "trusted_detached": True,
        "dispatch_present": True,
        "dispatch_regular": True,
        "dispatch_symlink": False,
        "dispatch_nlink": 1,
        "dispatch_uid": reconcile.ROOT_UID,
        "dispatch_gid": reconcile.ROOT_GID,
        "dispatch_fs_mode": reconcile.RESTRICTIVE_MODE,
        "dispatch_git_mode": reconcile.TRUSTED_DISPATCH_GIT_MODE,
        "dispatch_git_blob": reconcile.TRUSTED_DISPATCH_GIT_BLOB,
        "dispatch_content_blob": reconcile.TRUSTED_DISPATCH_GIT_BLOB,
    }
    values.update(overrides)
    return reconcile.TrustedDispatchEvidence(**values)


class TrustedDispatchModeReconcileTests(unittest.TestCase):
    def test_restrictive_state_builds_exact_one_step_plan(self) -> None:
        plan = reconcile.build_plan(evidence())
        self.assertEqual(plan.prior_state, "RESTRICTIVE")
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].category, reconcile.MUTATION_CATEGORY)
        self.assertEqual(plan.steps[0].relative_path, reconcile.TRUSTED_DISPATCH_RELATIVE)
        self.assertEqual((plan.steps[0].from_mode, plan.steps[0].to_mode), (0o600, 0o644))
        self.assertEqual(plan.rollback_policy, "NONE")

    def test_exact_state_is_preconsume_noop(self) -> None:
        plan = reconcile.build_plan(evidence(dispatch_fs_mode=reconcile.EXACT_MODE))
        self.assertEqual(plan.prior_state, "EXACT")
        self.assertEqual(plan.steps, ())
        self.assertEqual(reconcile.public_plan(plan)["mutation_budget"], [])

    def test_unknown_or_mixed_mode_fails_closed(self) -> None:
        self.assertEqual(reconcile.classify(evidence(dispatch_fs_mode=0o640)), "CONFLICT")
        with self.assertRaisesRegex(reconcile.TrustedDispatchModeReconcileError, "conflicts"):
            reconcile.build_plan(evidence(dispatch_fs_mode=0o640))

    def test_dispatch_identity_drift_fails_closed(self) -> None:
        for override in (
            {"dispatch_regular": False},
            {"dispatch_symlink": True},
            {"dispatch_nlink": 2},
            {"dispatch_uid": 1000},
            {"dispatch_gid": 1000},
            {"dispatch_git_mode": "100755"},
            {"dispatch_git_blob": "f" * 40},
            {"dispatch_content_blob": "f" * 40},
        ):
            with self.subTest(override=override):
                self.assertEqual(reconcile.classify(evidence(**override)), "CONFLICT")

    def test_source_ci_and_trusted_identity_drift_raise(self) -> None:
        cases = (
            ({"current_main_sha": "b" * 40}, "current main"),
            ({"exact_main_ci_success": False}, "CI"),
            ({"trusted_present": False}, "trusted stale boundary"),
            ({"trusted_origin": "https://example.invalid/repo.git"}, "trusted stale boundary"),
            ({"trusted_head": "b" * 40}, "trusted stale boundary"),
            ({"trusted_clean": False}, "trusted stale boundary"),
            ({"trusted_detached": False}, "trusted stale boundary"),
        )
        for override, message in cases:
            with self.subTest(override=override):
                with self.assertRaisesRegex(reconcile.TrustedDispatchModeReconcileError, message):
                    reconcile.classify(evidence(**override))

    def test_contract_is_one_file_one_mutation_and_no_manager_mode_authority(self) -> None:
        contract = json.loads(
            (
                ROOT
                / "ops/deploy/weather-private-installer-boundary-trusted-dispatch-mode-reconcile.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(contract["operation_id"], reconcile.OPERATION_ID)
        self.assertEqual(contract["target_alias"], reconcile.TARGET_ALIAS)
        self.assertFalse(contract["source_merge_authorizes_live"])
        self.assertFalse(contract["manager_checkout_mode_mutation_authorized"])
        self.assertEqual(contract["file"]["relative_path"], reconcile.TRUSTED_DISPATCH_RELATIVE)
        self.assertEqual(contract["file"]["git_blob"], reconcile.TRUSTED_DISPATCH_GIT_BLOB)
        self.assertEqual(
            contract["mutation_budget"],
            [{"category": reconcile.MUTATION_CATEGORY, "max_operations": 1}],
        )
        self.assertEqual(contract["rollback_policy"], "NONE")
        self.assertFalse(contract["automatic_retry"])
        self.assertFalse(contract["automatic_cleanup"])
        self.assertFalse(contract["automatic_rollback"])

    def test_classifier_contains_no_host_mutator_or_manager_mode_surface(self) -> None:
        source = (
            ROOT
            / "ops/lib/deploy_executor/weather_private_installer_boundary_trusted_dispatch_mode_reconcile.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "os.chmod",
            "os.chown",
            "subprocess",
            "runuser",
            "sudo",
            "systemctl",
            "docker",
            "MANAGER_CHECKOUT",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
