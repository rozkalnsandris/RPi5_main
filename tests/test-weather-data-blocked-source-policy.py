#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/deploy/simple-deploy-weather-data-v1.json"
BRIDGE = ROOT / "ops/lib/deploy_executor/simple_deploy_weather_data_v1.py"
LAST_REVIEWED_BOOTSTRAP_READY_SHA = "789a79820807829cc9b057d9ffafc56e0e41afe9"
CURRENT_BLOCKED_CONSUMER_SHA = "df6095db68ae575155016275ad8fd2780ff7486f"


class Tests(unittest.TestCase):
    def test_current_consumer_source_is_explicitly_blocked(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        blocked = contract["blocked_current_consumer_source"]
        self.assertEqual(contract["status"], "SOURCE_BLOCKED_NO_VERIFIED_DWD_HISTORICAL_TRANSPORT")
        self.assertEqual(blocked["source_sha"], CURRENT_BLOCKED_CONSUMER_SHA)
        self.assertEqual(blocked["consumer_bootstrap_contract_status"], "SOURCE_BLOCKED_NO_VERIFIED_DWD_HISTORICAL_TRANSPORT")
        self.assertEqual(blocked["consumer_bootstrap_plan_state"], "BLOCKED_BY_TRUTH_TRANSPORT_CAPABILITY")
        self.assertEqual(blocked["block_reason"], "TRUTH_TRANSPORT_HISTORICAL_CAPABILITY_UNVERIFIED")
        self.assertEqual(blocked["historical_transport_status"], "no_verified_dwd_historical_transport")
        self.assertEqual(blocked["wmo_to_cdc_station_mapping_status"], "UNVERIFIED")
        self.assertFalse(blocked["live_backfill_allowed"])
        self.assertTrue(blocked["bootstrap_source_binding_must_not_advance_while_blocked"])

    def test_blocked_source_cannot_replace_last_reviewed_bootstrap_binding(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        reviewed = contract["reviewed_bootstrap_consumer_source_sha"]
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertEqual(reviewed, LAST_REVIEWED_BOOTSTRAP_READY_SHA)
        self.assertNotEqual(reviewed, CURRENT_BLOCKED_CONSUMER_SHA)
        self.assertIn(f'EXPECTED_BOOTSTRAP_SOURCE_SHA = "{LAST_REVIEWED_BOOTSTRAP_READY_SHA}"', source)
        self.assertNotIn(f'EXPECTED_BOOTSTRAP_SOURCE_SHA = "{CURRENT_BLOCKED_CONSUMER_SHA}"', source)


if __name__ == "__main__":
    unittest.main()
