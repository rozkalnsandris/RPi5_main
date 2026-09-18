#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_v9_capability_refresh as refresh


def artifact_hashes(*, broker: str = "b") -> dict[str, str]:
    return {
        "module_sha256": "1" * 64,
        "broker_sha256": broker * 64,
        "socket_sha256": "2" * 64,
        "service_sha256": "3" * 64,
    }


def registration() -> dict[str, object]:
    return {
        "schema": refresh.REGISTRATION_SCHEMA,
        "capability_source_sha": refresh.PREDECESSOR_SOURCE_SHA,
        "manager_checkout": "/home/operator/RPi5_main",
        "manager_uid": 1000,
        "manager_gid": 1000,
        "artifact_count": 15,
        **artifact_hashes(),
    }


def valid_plan(**overrides: object) -> refresh.RefreshPlan:
    values: dict[str, object] = {
        "source_sha": "a" * 40,
        "registration": registration(),
        "predecessor_hashes": artifact_hashes(),
        "installed_hashes": artifact_hashes(),
        "target_hashes": artifact_hashes(broker="c"),
        "state_db_present": True,
        "temp_paths_absent": True,
    }
    values.update(overrides)
    return refresh.build_refresh_plan(**values)  # type: ignore[arg-type]


def git_bytes(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(ROOT), "show", f"{commit}:{path}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


class WeatherV9CapabilityRefreshTests(unittest.TestCase):
    def test_exact_predecessor_builds_narrow_refresh_plan(self) -> None:
        plan = valid_plan()
        self.assertEqual(plan.predecessor_source_sha, refresh.PREDECESSOR_SOURCE_SHA)
        self.assertEqual(plan.new_registration["capability_source_sha"], "a" * 40)
        self.assertEqual(plan.new_registration["broker_sha256"], "c" * 64)
        self.assertEqual(plan.new_registration["module_sha256"], "1" * 64)
        self.assertEqual(plan.mutation_budget, refresh.MUTATION_BUDGET)
        self.assertEqual(plan.state_db_policy, "PRESERVE_EXISTING_UNCHANGED")
        self.assertFalse(plan.systemd_mutation)
        self.assertFalse(plan.queue_or_live_auth_created)

    def test_wrong_registration_source_is_rejected(self) -> None:
        value = registration()
        value["capability_source_sha"] = "d" * 40
        with self.assertRaises(refresh.WeatherV9CapabilityRefreshError):
            valid_plan(registration=value)

    def test_installed_hash_drift_is_rejected(self) -> None:
        installed = artifact_hashes()
        installed["broker_sha256"] = "d" * 64
        with self.assertRaises(refresh.WeatherV9CapabilityRefreshError):
            valid_plan(installed_hashes=installed)

    def test_target_widening_beyond_broker_is_rejected(self) -> None:
        target = artifact_hashes(broker="c")
        target["module_sha256"] = "f" * 64
        with self.assertRaises(refresh.WeatherV9CapabilityRefreshError):
            valid_plan(target_hashes=target)

    def test_missing_replay_state_or_partial_staging_is_rejected(self) -> None:
        with self.assertRaises(refresh.WeatherV9CapabilityRefreshError):
            valid_plan(state_db_present=False)
        with self.assertRaises(refresh.WeatherV9CapabilityRefreshError):
            valid_plan(temp_paths_absent=False)

    def test_registration_round_trip_preserves_manager_and_replay_binding_fields(self) -> None:
        plan = valid_plan()
        encoded = refresh.registration_bytes(plan.new_registration)
        decoded = json.loads(encoded.decode("utf-8"))
        self.assertEqual(decoded["manager_checkout"], registration()["manager_checkout"])
        self.assertEqual(decoded["manager_uid"], registration()["manager_uid"])
        self.assertEqual(decoded["manager_gid"], registration()["manager_gid"])
        self.assertEqual(decoded["artifact_count"], 15)
        self.assertEqual(decoded["capability_source_sha"], "a" * 40)

    def test_current_source_delta_is_broker_only_for_installed_capability_artifacts(self) -> None:
        unchanged = (
            "ops/lib/deploy_executor/weather_operator_upgrade_v9_host_capability.py",
            "ops/systemd/rozkalns-weather-operator-v9-privileged-broker.socket",
            "ops/systemd/rozkalns-weather-operator-v9-privileged-broker@.service",
        )
        for path in unchanged:
            with self.subTest(path=path):
                self.assertEqual(git_bytes("HEAD", path), git_bytes(refresh.PREDECESSOR_SOURCE_SHA, path))
        broker = "ops/bin/rozkalns-weather-operator-v9-privileged-broker"
        self.assertNotEqual(git_bytes("HEAD", broker), git_bytes(refresh.PREDECESSOR_SOURCE_SHA, broker))

    def test_contract_and_operator_preserve_fail_closed_recovery_boundary(self) -> None:
        contract = json.loads(
            (ROOT / "ops/deploy/weather-operator-v9-capability-refresh.json").read_text()
        )
        self.assertEqual(contract["predecessor_source_sha"], refresh.PREDECESSOR_SOURCE_SHA)
        self.assertEqual(
            tuple((row["category"], row["max_operations"]) for row in contract["mutation_budget"]),
            refresh.MUTATION_BUDGET,
        )
        self.assertEqual(contract["state_db_policy"], "PRESERVE_EXISTING_UNCHANGED")
        self.assertFalse(contract["systemd_mutation"])
        self.assertFalse(contract["queue_or_live_auth_creation"])
        self.assertEqual(contract["historical_authority"]["ops-workflows#69"], "STALE_PRE_RECOVERY_QUEUE_DO_NOT_REUSE")
        self.assertEqual(contract["historical_authority"]["ops-workflows#70"], "SPENT_LIVE_AUTH_DO_NOT_REUSE")

        operator = (ROOT / "scripts/refresh-weather-operator-v9-host-capability.py").read_text()
        self.assertIn("state_snapshot() != before_state", operator)
        self.assertEqual(operator.count("os.replace("), 2)
        self.assertNotIn("systemctl", operator)
        self.assertNotIn("STATE_DB.read_bytes", operator)
        self.assertNotIn("os.unlink", operator)
        self.assertNotIn("os.remove", operator)
        self.assertNotIn("worktree remove", operator)
        self.assertNotIn("worktree prune", operator)


if __name__ == "__main__":
    unittest.main()
