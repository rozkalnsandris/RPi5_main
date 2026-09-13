from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "ops/lib/deploy_executor/control_phase5_signer_handoff.py"
spec = importlib.util.spec_from_file_location("control_phase5_signer_handoff_test", PATH)
assert spec and spec.loader
handoff = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = handoff
spec.loader.exec_module(handoff)

SOURCE_SHA = handoff.REVIEWED_CONTROL_SOURCE_SHA
DEPLOYMENT = "11111111-1111-4111-8111-111111111111"
VERSION = "22222222-2222-4222-8222-222222222222"
KEY_ID = "fixture-v1"
GENERATED = "2026-09-13T12:00:00.000Z"
NOW = "2026-09-13T12:04:59.000Z"


def valid_manifest():
    return {
        "schema_version": 1,
        "contract": "PHASE5_RPI5_SIGNER_HANDOFF_V1",
        "source_repository": "rozkalnsandris/rozkalns-control-center",
        "control_source_sha": SOURCE_SHA,
        "worker": "rozkalns-control",
        "expected_worker": {
            "deployment_id": DEPLOYMENT,
            "version_id": VERSION,
            "traffic_percent": 100,
            "ingest_state": "PRESENT_TRUE",
        },
        "key_id": KEY_ID,
        "observation_contract_version": "control-phase5-rpi5-observation-v1",
        "generated_at": GENERATED,
        "receiver": {
            "repository": "rozkalnsandris/RPi5_main",
            "lane": "RPI5_SIGNER_RUNTIME",
            "authority_owner": "RPi5_main",
        },
        "authority": {
            "evidence_only": True,
            "grants_live_authority": False,
            "grants_cross_repo_write": False,
            "grants_rpi5_runtime_mutation": False,
        },
    }


def expected_identity():
    return {
        "control_source_sha": SOURCE_SHA,
        "deployment_id": DEPLOYMENT,
        "version_id": VERSION,
        "key_id": KEY_ID,
    }


class Phase5SignerHandoffTests(unittest.TestCase):
    def test_valid_exact_handoff_normalizes_and_matches_identity(self):
        normalized = handoff.normalize_phase5_signer_handoff(valid_manifest(), NOW)
        self.assertEqual(normalized, valid_manifest())
        handoff.assert_phase5_signer_handoff_identity(normalized, expected_identity())

    def test_unknown_missing_or_nested_extra_fields_fail_closed(self):
        cases = []
        extra = valid_manifest(); extra["extra"] = True; cases.append(extra)
        missing = valid_manifest(); del missing["key_id"]; cases.append(missing)
        nested = valid_manifest(); nested["expected_worker"]["extra"] = True; cases.append(nested)
        authority = valid_manifest(); authority["authority"]["extra"] = False; cases.append(authority)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(handoff.Phase5SignerHandoffError):
                    handoff.normalize_phase5_signer_handoff(value, NOW)

    def test_freshness_and_canonical_timestamp_fail_closed(self):
        stale = valid_manifest(); stale["generated_at"] = "2026-09-13T11:59:58.000Z"
        future = valid_manifest(); future["generated_at"] = "2026-09-13T12:05:00.000Z"
        malformed = valid_manifest(); malformed["generated_at"] = "2026-09-13T12:00:00Z"
        for value in (stale, future, malformed):
            with self.assertRaises(handoff.Phase5SignerHandoffError):
                handoff.normalize_phase5_signer_handoff(value, NOW)

    def test_worker_receiver_and_authority_literals_fail_closed(self):
        worker = valid_manifest(); worker["expected_worker"]["traffic_percent"] = 99
        receiver = valid_manifest(); receiver["receiver"]["lane"] = "OTHER"
        authority = valid_manifest(); authority["authority"]["grants_live_authority"] = True
        for value in (worker, receiver, authority):
            with self.assertRaises(handoff.Phase5SignerHandoffError):
                handoff.normalize_phase5_signer_handoff(value, NOW)

    def test_identity_drift_and_unreviewed_control_source_fail_closed(self):
        normalized = handoff.normalize_phase5_signer_handoff(valid_manifest(), NOW)
        mismatch = expected_identity(); mismatch["version_id"] = "33333333-3333-4333-8333-333333333333"
        with self.assertRaises(handoff.Phase5SignerHandoffError) as caught:
            handoff.assert_phase5_signer_handoff_identity(normalized, mismatch)
        self.assertEqual(caught.exception.code, "HANDOFF_IDENTITY_MISMATCH")

        unreviewed = expected_identity(); unreviewed["control_source_sha"] = "a" * 40
        with self.assertRaises(handoff.Phase5SignerHandoffError) as caught:
            handoff.assert_phase5_signer_handoff_identity(normalized, unreviewed)
        self.assertEqual(caught.exception.code, "UNREVIEWED_CONTROL_SOURCE")

    def test_errors_do_not_echo_manifest_values(self):
        value = valid_manifest(); value["key_id"] = "SECRET BAD VALUE"
        with self.assertRaises(handoff.Phase5SignerHandoffError) as caught:
            handoff.normalize_phase5_signer_handoff(value, NOW)
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertNotIn("BAD VALUE", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
