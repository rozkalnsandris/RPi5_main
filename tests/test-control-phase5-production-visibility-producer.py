from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "ops/lib/deploy_executor"
sys.path.insert(0, str(LIB))
import control_phase5_production_visibility_producer as producer

BROKER_PATH = ROOT / "ops/lib/phase5-production-visibility-evidence.py"
spec = importlib.util.spec_from_file_location("phase5_visibility_evidence", BROKER_PATH)
assert spec and spec.loader
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


class ProductionVisibilityProducerTests(unittest.TestCase):
    def make_state(self, root: Path, commit: str, **overrides) -> str:
        transaction_id = f"20260914T123456789012Z-{commit[:12]}"
        (root / "transactions" / transaction_id).mkdir(parents=True)
        (root / "latest-success").write_text(transaction_id + "\n")
        transaction = {
            "schema": broker.TRANSACTION_SCHEMA,
            "id": transaction_id,
            "repository": broker.REPOSITORY,
            "status": "success",
            "commit": commit,
            "completed_at": "2026-09-14T12:34:56Z",
        }
        transaction.update(overrides)
        (root / "transactions" / transaction_id / "transaction.json").write_text(
            json.dumps(transaction)
        )
        return transaction_id

    def publish(self, state_root: Path, evidence_root: Path, *, observed_at="2026-09-14T12:59:00Z"):
        return broker.sync_phase5_visibility(
            state_root=state_root,
            evidence_root=evidence_root,
            observed_at=observed_at,
        )

    def observe(self, evidence_root: Path, expected_main_sha: str, *, now=None):
        return producer.observe_production_visibility(
            expected_main_sha=expected_main_sha,
            evidence_root=evidence_root,
            now=now or datetime(2026, 9, 14, 13, 0, 0, tzinfo=timezone.utc),
        )

    def prepared_snapshot(self, commit="a" * 40, *, observed_at="2026-09-14T12:59:00Z"):
        state_tmp = tempfile.TemporaryDirectory()
        evidence_tmp = tempfile.TemporaryDirectory()
        state_root = Path(state_tmp.name)
        evidence_root = Path(evidence_tmp.name)
        self.make_state(state_root, commit)
        self.publish(state_root, evidence_root, observed_at=observed_at)
        self.addCleanup(state_tmp.cleanup)
        self.addCleanup(evidence_tmp.cleanup)
        return evidence_root

    def test_broker_publishes_full_sha_without_touching_legacy_deployments(self):
        with tempfile.TemporaryDirectory() as state_tmp, tempfile.TemporaryDirectory() as evidence_tmp:
            state_root = Path(state_tmp)
            evidence_root = Path(evidence_tmp)
            legacy = evidence_root / "deployments.json"
            legacy.write_text('{"legacy":true}\n')
            commit = "123456abcdef123456abcdef123456abcdef1234"
            transaction_id = self.make_state(state_root, commit)
            self.assertTrue(self.publish(state_root, evidence_root))
            snapshot = json.loads((evidence_root / broker.EVIDENCE_FILENAME).read_text())
            self.assertEqual(set(snapshot), broker.SNAPSHOT_FIELDS)
            self.assertEqual(snapshot["schema"], broker.SCHEMA)
            self.assertEqual(snapshot["status"], "AVAILABLE")
            self.assertEqual(snapshot["repository"], broker.REPOSITORY)
            self.assertEqual(snapshot["transactionId"], transaction_id)
            self.assertEqual(snapshot["productionSha"], commit)
            self.assertEqual(snapshot["completedAt"], "2026-09-14T12:34:56.000Z")
            self.assertEqual(snapshot["observedAt"], "2026-09-14T12:59:00.000Z")
            self.assertEqual(legacy.read_text(), '{"legacy":true}\n')

    def test_missing_deploy_pointer_overwrites_snapshot_with_unavailable(self):
        with tempfile.TemporaryDirectory() as state_tmp, tempfile.TemporaryDirectory() as evidence_tmp:
            state_root = Path(state_tmp)
            evidence_root = Path(evidence_tmp)
            stale = broker.unavailable_snapshot("2026-09-14T12:00:00.000Z")
            stale.update({
                "status": "AVAILABLE",
                "transactionId": "20260914T123456789012Z-aaaaaaaaaaaa",
                "productionSha": "a" * 40,
                "completedAt": "2026-09-14T12:00:00.000Z",
            })
            (evidence_root / broker.EVIDENCE_FILENAME).write_text(json.dumps(stale))
            self.assertFalse(self.publish(state_root, evidence_root))
            snapshot = json.loads((evidence_root / broker.EVIDENCE_FILENAME).read_text())
            self.assertEqual(snapshot, broker.unavailable_snapshot("2026-09-14T12:59:00.000Z"))
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                self.observe(evidence_root, "a" * 40)
            self.assertEqual(caught.exception.code, "BROKER_EVIDENCE_UNAVAILABLE")

    def test_exact_production_main_match_is_no_deploy_and_uses_broker_time(self):
        commit = "a" * 40
        evidence_root = self.prepared_snapshot(commit)
        value = self.observe(evidence_root, commit)
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
        self.assertEqual(value["observedAt"], "2026-09-14T12:59:00.000Z")

    def test_production_main_drift_does_not_invent_rollout_semantics(self):
        production_sha = "a" * 40
        main_sha = "b" * 40
        evidence_root = self.prepared_snapshot(production_sha)
        value = self.observe(evidence_root, main_sha)
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

    def test_stale_broker_snapshot_fails_closed_at_existing_300_second_boundary(self):
        evidence_root = self.prepared_snapshot("a" * 40, observed_at="2026-09-14T12:54:59Z")
        with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
            self.observe(evidence_root, "a" * 40)
        self.assertEqual(caught.exception.code, "VISIBILITY_STALE_EVIDENCE")

    def test_missing_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                self.observe(Path(tmp), "a" * 40)
        self.assertEqual(caught.exception.code, "BROKER_EVIDENCE_MISSING")

    def test_symlink_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            target.write_text("ignored")
            (root / producer.EVIDENCE_FILENAME).symlink_to(target)
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                self.observe(root, "a" * 40)
        self.assertEqual(caught.exception.code, "BROKER_EVIDENCE_UNSAFE")

    def test_wrong_repository_fails_closed(self):
        evidence_root = self.prepared_snapshot()
        path = evidence_root / producer.EVIDENCE_FILENAME
        value = json.loads(path.read_text())
        value["repository"] = "wrong/repo"
        path.write_text(json.dumps(value))
        with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
            self.observe(evidence_root, "a" * 40)
        self.assertEqual(caught.exception.code, "BROKER_EVIDENCE_INVALID")

    def test_commit_prefix_mismatch_fails_closed(self):
        evidence_root = self.prepared_snapshot()
        path = evidence_root / producer.EVIDENCE_FILENAME
        value = json.loads(path.read_text())
        value["productionSha"] = "b" * 40
        path.write_text(json.dumps(value))
        with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
            self.observe(evidence_root, "a" * 40)
        self.assertEqual(caught.exception.code, "BROKER_EVIDENCE_INVALID")

    def test_duplicate_snapshot_key_fails_closed(self):
        evidence_root = self.prepared_snapshot()
        path = evidence_root / producer.EVIDENCE_FILENAME
        snapshot = json.loads(path.read_text())
        raw = json.dumps(snapshot, separators=(",", ":"))
        raw = raw[:-1] + ',"status":"AVAILABLE"}'
        path.write_text(raw)
        with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
            self.observe(evidence_root, "a" * 40)
        self.assertEqual(caught.exception.code, "BROKER_EVIDENCE_INVALID")

    def test_bad_expected_main_sha_fails_closed_before_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(producer.ProductionVisibilityProducerError) as caught:
                producer.observe_production_visibility(
                    expected_main_sha="not-a-sha",
                    evidence_root=Path(tmp),
                )
        self.assertEqual(caught.exception.code, "EXPECTED_MAIN_SHA_INVALID")

    def test_source_uses_only_sanitized_broker_and_no_mutation_network_secret_bridge(self):
        source = (LIB / "control_phase5_production_visibility_producer.py").read_text().lower()
        forbidden = (
            "subprocess", "os.system(", "os.environ", "requests", "urllib", "socket",
            "paramiko", "sqlite", "docker", "systemctl", "/etc/credstore", "o_wronly",
            "o_rdwr", "o_creat", "unlink(", "rename(", "os.replace(", "/var/lib/rpi5-deploy",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertIn('path("/var/lib/dashboard-rpi5/evidence")', source)
        self.assertIn("phase5-production-visibility.json", source)
        self.assertIn("normalize_production_visibility", source)

    def test_broker_and_wrapper_preserve_narrow_root_to_sanitized_boundary(self):
        helper = BROKER_PATH.read_text().lower()
        wrapper = (ROOT / "ops/bin/rpi5-dashboard-evidence").read_text()
        self.assertIn('/var/lib/rpi5-deploy', helper)
        self.assertIn('/var/lib/dashboard-rpi5/evidence', helper)
        self.assertNotIn("subprocess", helper)
        self.assertNotIn("requests", helper)
        self.assertNotIn("socket", helper)
        self.assertNotIn("os.environ", helper)
        self.assertIn('PHASE5_VISIBILITY_HELPER="/usr/local/lib/rpi5-maintenance/phase5-production-visibility-evidence.py"', wrapper)
        self.assertIn('require_root_controlled_file "$PHASE5_VISIBILITY_HELPER"', wrapper)
        self.assertIn('python3 "$PHASE5_VISIBILITY_HELPER"', wrapper)
        self.assertIn("sync_phase5_visibility", wrapper)
        self.assertNotIn("sudo", wrapper)

    def test_cli_and_docs_do_not_require_root_or_sudo(self):
        cli = (ROOT / "ops/bin/rpi5-control-phase5-production-visibility").read_text().lower()
        docs = (ROOT / "docs/CONTROL_PHASE5_PRODUCTION_VISIBILITY_PRODUCER_SOURCE.md").read_text().lower()
        self.assertNotIn("geteuid", cli)
        self.assertNotIn("execution_identity_invalid", cli)
        self.assertNotIn("sudo", cli)
        self.assertNotIn("sudo python3", docs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
