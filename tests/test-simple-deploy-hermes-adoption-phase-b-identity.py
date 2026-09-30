#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/adopt-simple-deploy-hermes-v1.py"
CONTRACT_PATH = ROOT / "ops/contracts/simple-deploy-hermes-adoption-v1.json"

spec = importlib.util.spec_from_file_location("adopt_simple_deploy_hermes_v1_phase_b", MODULE_PATH)
assert spec and spec.loader
adopt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adopt
spec.loader.exec_module(adopt)

EXPECTED_SOURCE_SHA = "7c6c7a8a80ca62d783c7f378b5865fae348a3fe9"
EXPECTED_IDENTITY_SHA256 = "244abc1480a20937acb3d702760289631700aa27d0e518b454a7271dbd777df1"
SUPERSEDED_PHASE_A_SHA = "b57ed42d5eb01f15b62c1f53459ffe0539a57d9c"
SUPERSEDED_PHASE_A_IDENTITY_SHA256 = "602b5d58db380fc5c7844c089e0a8f64549e9efd0a11ff417602cb3965405bd5"


def identity_bytes(source_sha: str) -> bytes:
    value = {
        "schema": adopt.IDENTITY_SCHEMA,
        "repository": adopt.HOST_REPOSITORY,
        "source_sha": source_sha,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class HermesPhaseBIdentityBaselineTests(unittest.TestCase):
    def test_adoption_binds_exact_post_phase_b_identity(self) -> None:
        self.assertEqual(adopt.BASELINE_SOURCE_SHA, EXPECTED_SOURCE_SHA)
        self.assertEqual(adopt._identity_bytes(), identity_bytes(EXPECTED_SOURCE_SHA))
        self.assertEqual(hashlib.sha256(adopt._identity_bytes()).hexdigest(), EXPECTED_IDENTITY_SHA256)

    def test_superseded_phase_a_identity_remains_distinct(self) -> None:
        old_identity = identity_bytes(SUPERSEDED_PHASE_A_SHA)
        self.assertEqual(hashlib.sha256(old_identity).hexdigest(), SUPERSEDED_PHASE_A_IDENTITY_SHA256)
        self.assertNotEqual(old_identity, adopt._identity_bytes())

    def test_machine_contract_matches_exact_identity_baseline(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        baseline = contract["baseline"]
        self.assertEqual(baseline["identity_source_sha"], EXPECTED_SOURCE_SHA)
        self.assertEqual(baseline["identity_sha256"], EXPECTED_IDENTITY_SHA256)
        self.assertEqual(baseline["identity_provenance"], "post-phase-b-repair")


if __name__ == "__main__":
    unittest.main()
