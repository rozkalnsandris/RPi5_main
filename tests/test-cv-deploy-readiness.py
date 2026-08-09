from __future__ import annotations

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cv-deploy-readiness.py"

spec = importlib.util.spec_from_file_location("cv_deploy_readiness", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SHA_A = "a" * 40
SHA_B = "b" * 40


class CvDeployReadinessTests(unittest.TestCase):
    def test_records_sanitized_manual_state_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            payload = module.record(
                state_root=root,
                reason="MANUAL_ROLLOUT_REQUIRED",
                target_sha=SHA_B,
                production_sha=SHA_A,
                deploy_impact="MANUAL_ROLLOUT_REQUIRED",
                control_plane_changed=True,
                ci_run_id=12345,
            )
            state_path = root / module.STATE_FILENAME
            self.assertTrue(state_path.is_file())
            self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            stored = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(stored, payload)
            self.assertFalse(stored["production_mutation_authorized"])
            self.assertEqual(stored["reason"], "MANUAL_ROLLOUT_REQUIRED")
            self.assertEqual(stored["ci_run_id"], 12345)
            datetime.fromisoformat(stored["last_seen_utc"].replace("Z", "+00:00"))

    def test_same_state_preserves_first_seen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            first = module.record(
                state_root=root,
                reason="WAIT_CI",
                target_sha=SHA_B,
                production_sha=SHA_A,
                deploy_impact="UNCLASSIFIED",
                control_plane_changed=False,
                ci_run_id=None,
            )
            second = module.record(
                state_root=root,
                reason="WAIT_CI",
                target_sha=SHA_B,
                production_sha=SHA_A,
                deploy_impact="UNCLASSIFIED",
                control_plane_changed=False,
                ci_run_id=None,
            )
            self.assertEqual(first["first_seen_utc"], second["first_seen_utc"])

    def test_current_requires_matching_shas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                module.record(
                    state_root=Path(tmp),
                    reason="CURRENT",
                    target_sha=SHA_B,
                    production_sha=SHA_A,
                    deploy_impact="NO_DEPLOY",
                    control_plane_changed=False,
                    ci_run_id=None,
                )

    def test_preflight_failure_is_only_reason_allowed_without_shas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = module.record(
                state_root=Path(tmp),
                reason="PREFLIGHT_FAILED",
                target_sha="",
                production_sha="",
                deploy_impact="UNCLASSIFIED",
                control_plane_changed=False,
                ci_run_id=None,
            )
            self.assertEqual(payload["reason"], "PREFLIGHT_FAILED")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                module.record(
                    state_root=Path(tmp),
                    reason="WAIT_CI",
                    target_sha="",
                    production_sha="",
                    deploy_impact="UNCLASSIFIED",
                    control_plane_changed=False,
                    ci_run_id=None,
                )

    def test_pull_transport_wait_state_is_sanitized_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = module.record(
                state_root=Path(tmp),
                reason="WAIT_PULL_TRANSPORT_ACTIVATION",
                target_sha=SHA_B,
                production_sha=SHA_A,
                deploy_impact="AUTO_DEPLOY_SAFE",
                control_plane_changed=False,
                ci_run_id=67890,
            )
            self.assertEqual(payload["reason"], "WAIT_PULL_TRANSPORT_ACTIVATION")
            self.assertEqual(payload["deploy_impact"], "AUTO_DEPLOY_SAFE")
            self.assertFalse(payload["control_plane_changed"])
            self.assertFalse(payload["production_mutation_authorized"])

    def test_deploy_failure_state_is_sanitized_and_requires_exact_shas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = module.record(
                state_root=Path(tmp),
                reason="DEPLOY_FAILED",
                target_sha=SHA_B,
                production_sha=SHA_A,
                deploy_impact="AUTO_DEPLOY_SAFE",
                control_plane_changed=False,
                ci_run_id=98765,
            )
            self.assertEqual(payload["reason"], "DEPLOY_FAILED")
            self.assertEqual(payload["target_sha"], SHA_B)
            self.assertEqual(payload["production_sha"], SHA_A)
            self.assertFalse(payload["production_mutation_authorized"])

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                module.record(
                    state_root=Path(tmp),
                    reason="DEPLOY_FAILED",
                    target_sha="",
                    production_sha="",
                    deploy_impact="AUTO_DEPLOY_SAFE",
                    control_plane_changed=False,
                    ci_run_id=98765,
                )

    def test_reason_and_impact_sets_match_phase3_contract(self) -> None:
        self.assertIn("AUTO_DEPLOY_READY", module.REASONS)
        self.assertIn("WAIT_HELPER_ACTIVATION", module.REASONS)
        self.assertIn("WAIT_PULL_TRANSPORT_ACTIVATION", module.REASONS)
        self.assertIn("MANUAL_ROLLOUT_REQUIRED", module.REASONS)
        self.assertIn("DB_HOST_APPLY_REQUIRED", module.REASONS)
        self.assertIn("DEPLOY_FAILED", module.REASONS)
        self.assertNotIn("APPROVED", module.REASONS)
        self.assertEqual(
            module.DEPLOY_IMPACTS,
            {
                "NO_DEPLOY",
                "AUTO_DEPLOY_SAFE",
                "MANUAL_ROLLOUT_REQUIRED",
                "DB_HOST_APPLY_REQUIRED",
                "UNCLASSIFIED",
            },
        )


if __name__ == "__main__":
    unittest.main()
