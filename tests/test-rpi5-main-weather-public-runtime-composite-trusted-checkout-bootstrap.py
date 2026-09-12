#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = "ops/deploy/rpi5-main-weather-public-runtime-composite-trusted-checkout-bootstrap.json"
CONTRACT = ROOT / CONTRACT_PATH
HELPER = ROOT / "ops/deploy/weather-public-runtime-helper-install-composite.json"
EXECUTION = ROOT / "ops/deploy/weather-public-runtime-execution.json"
DOC = ROOT / "docs/WEATHER_PUBLIC_RUNTIME_EXECUTOR_SOURCE.md"
TARGET = "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-composite-trusted"
AUTH_SHA = "EXPLICIT_COMPOSITE_STRICT_LIVE_EXACT_RPI5_MAIN_SHA"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
BASE = "95b6b95b132614cbc330d6d764d0557079a67534"

class WeatherCompositeTrustedCheckoutContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = json.loads(CONTRACT.read_text())
        cls.helper = json.loads(HELPER.read_text())
        cls.execution = json.loads(EXECUTION.read_text())
        cls.doc = DOC.read_text()

    def test_identity_and_current_sha_authority_are_fixed(self):
        c=self.c
        self.assertEqual(c["schema"], "rozkalns.rpi5-main.weather-public-runtime-composite-trusted-checkout-bootstrap.v1")
        self.assertTrue(c["source_only"])
        self.assertEqual(c["manager_checkout"]["origin"], ORIGIN)
        self.assertEqual(c["trusted_checkout"]["derivation"], TARGET)
        self.assertEqual(c["trusted_checkout"]["expected_sha_authority"], AUTH_SHA)
        self.assertEqual(c["trusted_checkout"]["minimum_reviewed_ancestor"], BASE)
        self.assertTrue(c["trusted_checkout"]["may_be_absent_before_first_mutation"])
        self.assertEqual(c["trusted_checkout"]["existing_policy"], "verified-reuse-only")
        self.assertEqual(c["verified_existing"]["git_mutation_count"], 0)
        self.assertFalse(c["verified_existing"]["repair_allowed"])

    def test_only_bounded_fetch_and_fixed_worktree_add_can_create_target(self):
        rows=self.c["allowed_git_mutations"]
        self.assertEqual([r["argv"] for r in rows], [["git","fetch","origin","main"],["git","worktree","add","--detach",TARGET,AUTH_SHA]])
        self.assertEqual([r["max_operations"] for r in rows], [1,1])
        self.assertTrue(all(r["working_tree_content_mutation"] is False for r in rows))
        forbidden=set(self.c["forbidden_git_operations"])
        self.assertTrue({"reset","rebase","clean","checkout","switch","merge","pull","worktree remove","worktree prune","force"}.issubset(forbidden))

    def test_historical_checkouts_are_evidence_only(self):
        rows={r["derivation"]:r for r in self.c["historical_checkouts"]}
        for path in (
            "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-trusted",
            "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted",
            "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-trusted",
        ):
            self.assertIn(path, rows)
            self.assertFalse(rows[path]["mutation_allowed"])
            self.assertFalse(rows[path]["cleanup_allowed"])
            self.assertFalse(rows[path]["authority_source"])

    def test_current_composite_surfaces_bind_dedicated_checkout(self):
        for surface in (self.helper,self.execution):
            self.assertEqual(surface["trusted_checkout_bootstrap_contract"], CONTRACT_PATH)
            self.assertEqual(surface["trusted_checkout_target"], TARGET)
        self.assertIn(CONTRACT_PATH, self.doc)
        self.assertIn(TARGET, self.doc)

    def test_source_merge_remains_non_live(self):
        self.assertTrue(self.c["followup"]["merge_never_authorizes_live"])
        self.assertTrue(all(value is False for value in self.c["safety"].values()))
        self.assertFalse(self.c["failure"]["automatic_retry"])
        self.assertFalse(self.c["failure"]["automatic_cleanup"])
        self.assertFalse(self.c["failure"]["automatic_rollback"])

if __name__ == "__main__":
    unittest.main()
