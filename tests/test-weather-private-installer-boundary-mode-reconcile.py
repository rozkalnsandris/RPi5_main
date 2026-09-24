from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "ops/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from deploy_executor import weather_private_installer_boundary_mode_reconcile as mode_reconcile  # noqa: E402


def evidence(*, restrictive: bool, mixed: bool = False, mutate: dict[str, object] | None = None):
    files = []
    for index, spec in enumerate(mode_reconcile.FILE_SPECS):
        fs_mode = spec.restrictive_mode if restrictive else spec.exact_mode
        if mixed and index == 0:
            fs_mode = spec.exact_mode
        item = mode_reconcile.FileEvidence(
            key=spec.key,
            present=True,
            regular=True,
            symlink=False,
            nlink=1,
            owner_class=spec.owner_class,
            fs_mode=fs_mode,
            git_mode=spec.git_mode,
            git_blob=spec.git_blob,
            content_blob=spec.git_blob,
        )
        files.append(item)
    if mutate:
        key = str(mutate["key"])
        field = str(mutate["field"])
        value = mutate["value"]
        updated = []
        for item in files:
            if item.key == key:
                data = item.__dict__.copy()
                data[field] = value
                item = mode_reconcile.FileEvidence(**data)
            updated.append(item)
        files = updated
    return mode_reconcile.ModeEvidence(
        source_sha="a" * 40,
        current_main_sha="a" * 40,
        exact_main_ci_success=True,
        manager_origin=mode_reconcile.REVIEWED_ORIGIN,
        manager_clean=True,
        manager_snapshot_stable=True,
        trusted_origin=mode_reconcile.REVIEWED_ORIGIN,
        trusted_head=mode_reconcile.KNOWN_STALE_HEAD,
        trusted_clean=True,
        trusted_detached=True,
        files=tuple(files),
    )


class ModeReconcileTests(unittest.TestCase):
    def test_restrictive_umask_state_builds_exact_three_step_plan(self):
        plan = mode_reconcile.build_plan(evidence(restrictive=True))
        self.assertEqual(plan.prior_state, "RESTRICTIVE")
        self.assertEqual(len(plan.steps), 3)
        self.assertTrue(all(step.category == mode_reconcile.MUTATION_CATEGORY for step in plan.steps))
        self.assertEqual(
            [(step.target_key, step.from_mode, step.to_mode) for step in plan.steps],
            [
                ("runtime_adapter", 0o700, 0o755),
                ("runtime_module", 0o600, 0o644),
                ("stale_dispatch", 0o600, 0o644),
            ],
        )

    def test_canonical_modes_are_exact_noop(self):
        plan = mode_reconcile.build_plan(evidence(restrictive=False))
        self.assertEqual(plan.prior_state, "EXACT")
        self.assertEqual(plan.steps, ())
        public = mode_reconcile.public_plan(plan)
        self.assertEqual(public["mutation_budget"], [])

    def test_mixed_partial_state_is_conflict(self):
        with self.assertRaisesRegex(mode_reconcile.ModeReconcileError, "mixed or conflicting"):
            mode_reconcile.build_plan(evidence(restrictive=True, mixed=True))

    def test_unexpected_mode_fails_closed(self):
        observed = evidence(
            restrictive=True,
            mutate={"key": "runtime_adapter", "field": "fs_mode", "value": 0o777},
        )
        self.assertEqual(mode_reconcile.classify(observed), "CONFLICT")

    def test_wrong_owner_or_blob_fails_closed(self):
        owner = evidence(
            restrictive=True,
            mutate={"key": "runtime_module", "field": "owner_class", "value": "root"},
        )
        blob = evidence(
            restrictive=True,
            mutate={"key": "stale_dispatch", "field": "content_blob", "value": "f" * 40},
        )
        self.assertEqual(mode_reconcile.classify(owner), "CONFLICT")
        self.assertEqual(mode_reconcile.classify(blob), "CONFLICT")

    def test_symlink_or_hardlink_fails_closed(self):
        symlink = evidence(
            restrictive=True,
            mutate={"key": "runtime_adapter", "field": "symlink", "value": True},
        )
        hardlink = evidence(
            restrictive=True,
            mutate={"key": "runtime_module", "field": "nlink", "value": 2},
        )
        self.assertEqual(mode_reconcile.classify(symlink), "CONFLICT")
        self.assertEqual(mode_reconcile.classify(hardlink), "CONFLICT")

    def test_source_and_git_identity_drift_raise(self):
        base = evidence(restrictive=True)
        with self.assertRaisesRegex(mode_reconcile.ModeReconcileError, "current main"):
            mode_reconcile.classify(
                mode_reconcile.ModeEvidence(**{**base.__dict__, "current_main_sha": "b" * 40})
            )
        wrong_git = evidence(
            restrictive=True,
            mutate={"key": "runtime_adapter", "field": "git_mode", "value": "100644"},
        )
        self.assertEqual(mode_reconcile.classify(wrong_git), "CONFLICT")

    def test_contract_matches_classifier_and_grants_no_live(self):
        contract = json.loads(
            (ROOT / "ops/deploy/weather-private-installer-boundary-mode-reconcile.json").read_text(encoding="utf-8")
        )
        self.assertEqual(contract["operation_id"], mode_reconcile.OPERATION_ID)
        self.assertEqual(contract["target_alias"], mode_reconcile.TARGET_ALIAS)
        self.assertFalse(contract["source_merge_authorizes_live"])
        self.assertEqual(
            contract["mutation_budget"],
            [{"category": mode_reconcile.MUTATION_CATEGORY, "max_operations": 3}],
        )
        self.assertEqual([item["key"] for item in contract["files"]], [item.key for item in mode_reconcile.FILE_SPECS])
        self.assertEqual(contract["rollback_policy"], "NONE")
        self.assertFalse(contract["automatic_retry"])
        self.assertFalse(contract["automatic_cleanup"])
        self.assertFalse(contract["automatic_rollback"])

    def test_source_has_no_host_mutator(self):
        source = (
            ROOT / "ops/lib/deploy_executor/weather_private_installer_boundary_mode_reconcile.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("os.chmod", "os.chown", "subprocess", "sudo", "systemctl", "docker"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
