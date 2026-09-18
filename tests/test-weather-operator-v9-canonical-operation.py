#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_upgrade_v7_host_capability as v7cap
from deploy_executor import weather_operator_upgrade_v9_host_capability as cap


class WeatherV9CanonicalOperationTests(unittest.TestCase):
    def test_v9_operation_is_canonical_capability_local_and_not_global(self) -> None:
        delivery = json.loads(
            (ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v9-privileged-delivery.json").read_text(
                encoding="utf-8"
            )
        )
        global_registry = json.loads(
            (ROOT / "ops/deploy/executor-operations.json").read_text(encoding="utf-8")
        )
        fixed = cap.fixed_registry()

        self.assertEqual(delivery["registry_scope"], "CAPABILITY_LOCAL_FIXED_REGISTRY")
        self.assertFalse(delivery["global_executor_registration"])
        self.assertFalse(delivery["global_executor_execution_enabled"])
        self.assertFalse(fixed.execution_enabled)
        self.assertEqual(len(fixed.operations), 1)

        normalized_fixed = json.loads(json.dumps(asdict(fixed.operations[0]), sort_keys=True))
        self.assertEqual(normalized_fixed, delivery["operation"])

        global_ids = {row["operation_id"] for row in global_registry["operations"]}
        self.assertFalse(global_registry["execution_enabled"])
        self.assertIn(v7cap.OPERATION_ID, global_ids)
        self.assertNotIn(cap.OPERATION_ID, global_ids)

    def test_capability_local_operation_keeps_exact_v9_transition(self) -> None:
        delivery = json.loads(
            (ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v9-privileged-delivery.json").read_text(
                encoding="utf-8"
            )
        )
        operation = delivery["operation"]
        budget = tuple(
            (row["category"], row["max_operations"])
            for row in operation["mutation_budget"]
        )

        self.assertEqual(operation["operation_id"], cap.OPERATION_ID)
        self.assertEqual(operation["target_alias"], cap.TARGET_ALIAS)
        self.assertEqual(operation["authorization_class"], "STRICT")
        self.assertFalse(operation["ordinary_live_all_eligible"])
        self.assertEqual(operation["rollback_policy"], "NONE")
        self.assertEqual(budget, cap.MUTATION_BUDGET)
        self.assertIn("p8-global-mutation-dispatch:disabled", operation["dependencies"])
        self.assertIn("v7-authority-reuse:forbidden", operation["dependencies"])

    def test_host_capability_postcondition_matches_exact_v9_target_bytes(self) -> None:
        target = (ROOT / "ops/lib/deploy_executor/weather_public_runtime_operator.py").read_bytes()
        contract = json.loads(
            (ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v9.json").read_text(
                encoding="utf-8"
            )
        )
        expected = hashlib.sha256(target).hexdigest()
        self.assertEqual(cap.NEW_SHA256, expected)
        self.assertEqual(contract["new_sha256"], expected)

    def test_post_614_capability_module_refresh_regression_suite(self) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "tests/test-weather-operator-v9-capability-module-refresh.py")],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
