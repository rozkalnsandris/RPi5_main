from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "ops/lib/deploy_executor"
sys.path.insert(0, str(LIB))
import control_phase5_production_visibility_producer as producer


class ProductionVisibilityProducerTests(unittest.TestCase):
    def make_state(self, root: Path, commit: str, **overrides) -> str:
        transaction_id = f"20260914T123456789012Z-{commit[:12]}"
        (root / "transactions" / transaction_id).mkdir(parents=True)
        (root / "latest-success").write_text(transaction_id + "\n")
        transaction = {
            "schema": producer.DEPLOY_TRANSACTION_SCHEMA,
            "id": transaction_id,
            "repository": producer.REPOSITORY,
            "status": "success",
            "commit": commit,
            "completed_at": "2026-09-14T12:34:56Z",
        }
        transaction.update(overrides)
        (root / "transactions" / transaction_id / "transaction.json").write_text(
            json.dumps(transaction)
        )
        return transaction_id

    def observe(self, root: Path, expected_main_sha: str):
        return producer.observe_production_visibility(
            expected_main_sha=expected_main_sha,
            state_root=root,
            now=datetime(2026, 9, 14, 13, 0, 0, tzinfo=timezone.utc),
        )

    def test_exact_production_main_match_is_no_deploy_and_unknown_elsewhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commit = "a" * 40
            self.make_state(root, commit)
            value = self.observe(root, commit)
        self.assertEqual(set(value), set(producer.visibility.FIELDS))
        self.assertEqual(value["projectId"], "rpi5-main")
        self.assertEqual(value["repository"], producer.REPOSITORY)
        self.assertEqual(value["mainSha"], commit)
        self.assertEqual(value["productionSha"], commit)
        self.assertEqual(value["deployImpact"], "NO_DEPLOY")
        self.assertEqual(value["runtime"], "UNKNOWN")
        self.assertEqual(value["health"], "UNKNOWN")
        self.assertEqual(value["rollback"], "UNKNOWN")
        self.assertEqual(value["blockerCodes"], list(producer.BASE_BLOCKERS))
        self.assertEqual(value["observedAt"], "2026-09-14T13:00:00.000Z")

    def test_production_main_drift_does_not_invent_rollout_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            production_sha = "a" * 40
            main_sha = "b" * 40
            self.make_state(root, production_sha)
            value = self.observe(root, main_sha)
        self.assertEqual(value["productionSha"], production_sha)
        self.assertEqual(value["deployImpact"], "UNKNOWN")
        self.assertEqual(
            value["blockerCodes"],
            [
                "PRODUCTION_SHA_DIFFERS_FROM_MAIN",
                "DEPLOY_IMPACT_OBSERVATION_UNAVAILABLE",
                *producer.BASE_BLOCKERS,
            ],
        )

    def test_missing_pointer_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                self.observe(root, "a" * 40)
        self.assertEqual(caught.exception.code, "DEPLOY_STATE_MISSING")

    def test_symlink_pointer_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            target.write_text("ignored")
            (root / "latest-success").symlink_to(target)
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                self.observe(root, "a" * 40)
        self.assertEqual(caught.exception.code, "DEPLOY_STATE_UNSAFE")

    def test_wrong_repository_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commit = "a" * 40
            self.make_state(root, commit, repository="wrong/repo")
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                self.observe(root, commit)
        self.assertEqual(caught.exception.code, "DEPLOY_STATE_INVALID")

    def test_commit_prefix_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commit = "a" * 40
            transaction_id = self.make_state(root, commit)
            path = root / "transactions" / transaction_id / "transaction.json"
            value = json.loads(path.read_text())
            value["commit"] = "b" * 40
            path.write_text(json.dumps(value))
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                self.observe(root, commit)
        self.assertEqual(caught.exception.code, "DEPLOY_STATE_INVALID")

    def test_duplicate_transaction_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commit = "a" * 40
            transaction_id = self.make_state(root, commit)
            path = root / "transactions" / transaction_id / "transaction.json"
            path.write_text(
                '{"schema":"rpi5.controlled-deploy-transaction.v1",'
                f'"id":"{transaction_id}","repository":"{producer.REPOSITORY}",'
                '"status":"success","status":"success",'
                f'"commit":"{commit}","completed_at":"2026-09-14T12:34:56Z"}}'
            )
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                self.observe(root, commit)
        self.assertEqual(caught.exception.code, "DEPLOY_STATE_INVALID")

    def test_non_utc_completion_timestamp_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commit = "a" * 40
            self.make_state(root, commit, completed_at="2026-09-14T14:34:56+02:00")
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                self.observe(root, commit)
        self.assertEqual(caught.exception.code, "DEPLOY_STATE_INVALID")

    def test_bad_expected_main_sha_fails_closed_before_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                producer.observe_production_visibility(
                    expected_main_sha="not-a-sha",
                    state_root=Path(tmp),
                )
        self.assertEqual(caught.exception.code, "EXPECTED_MAIN_SHA_INVALID")

    def test_source_has_no_mutation_network_secret_or_runtime_bridge(self):
        source = (LIB / "control_phase5_production_visibility_producer.py").read_text().lower()
        forbidden = (
            "subprocess",
            "os.system(",
            "os.environ",
            "requests",
            "urllib",
            "socket",
            "paramiko",
            "sqlite",
            "docker",
            "systemctl",
            "/etc/credstore",
            "o_wronly",
            "o_rdwr",
            "o_creat",
            "unlink(",
            "rename(",
            "os.replace(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertIn('path("/var/lib/rpi5-deploy")', source)
        self.assertIn("normalize_production_visibility", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
