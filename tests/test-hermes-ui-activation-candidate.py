#!/usr/bin/env python3
"""Offline checks for the opt-in candidate; no Docker or protected reads."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / "ops/deploy/simple-deploy-compose"


class ActivationCandidateTests(unittest.TestCase):
    def test_only_ui_enable_flag_changes(self):
        disabled = (ADAPTERS / "hermes-deals-household-api.yml").read_text()
        enabled = (ADAPTERS / "hermes-deals-household-enabled-api.yml").read_text()
        flag = '      HERMES_HOUSEHOLD_UI_ENABLED: "1"\n'
        self.assertEqual(enabled.count(flag), 1)
        self.assertEqual(enabled.replace(flag, ""), disabled)
        # Exact delta preserves API-only scope, env keys, mounts and network.

    def test_normal_adoption_does_not_select_enabled_candidate(self):
        registry = json.loads((ROOT / "ops/deploy/simple-deploy-targets-v1.json").read_text())
        target = next(t for t in registry["targets"] if t["target_alias"] == "hermes-deals")
        self.assertEqual(target["compose"]["file"], "hermes-deals-household-api.yml")
        actual = hashlib.sha256((ADAPTERS / target["compose"]["file"]).read_bytes()).hexdigest()
        self.assertEqual(target["compose"]["file_sha256"], actual)
        adoption = (ROOT / "scripts/prepare-hermes-state-adoption.py").read_text()
        self.assertNotIn("hermes-deals-household-enabled-api.yml", adoption)


if __name__ == "__main__":
    unittest.main()
