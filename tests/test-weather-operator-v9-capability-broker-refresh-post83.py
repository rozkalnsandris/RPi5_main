#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_v9_capability_broker_refresh as historical
from deploy_executor import weather_operator_v9_capability_broker_refresh_post83 as refresh


def artifact_hashes(*, broker: str = "2") -> dict[str, str]:
    return {
        "module_sha256": "1" * 64,
        "broker_sha256": broker * 64,
        "socket_sha256": "3" * 64,
        "service_sha256": "4" * 64,
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


def load_wrapper():
    path = ROOT / "scripts/refresh-weather-operator-v9-host-capability-broker-post83.py"
    spec = importlib.util.spec_from_file_location("weather_v9_post83_wrapper", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WeatherV9CapabilityBrokerRefreshPost83Tests(unittest.TestCase):
    def test_exact_post83_predecessor_builds_broker_only_plan(self) -> None:
        self.assertEqual(refresh.PREDECESSOR_SOURCE_SHA, "80261255b3be2aa7dd40986254d4ea478b4e2e1b")
        plan = valid_plan()
        self.assertEqual(plan.predecessor_source_sha, refresh.PREDECESSOR_SOURCE_SHA)
        self.assertEqual(plan.new_registration["capability_source_sha"], "a" * 40)
        self.assertEqual(plan.new_registration["broker_sha256"], "c" * 64)
        self.assertEqual(plan.new_registration["module_sha256"], "1" * 64)
        self.assertEqual(plan.mutation_budget, refresh.MUTATION_BUDGET)
        self.assertEqual(plan.state_db_policy, "PRESERVE_EXISTING_UNCHANGED")
        self.assertFalse(plan.systemd_mutation)
        self.assertFalse(plan.queue_or_live_auth_created)

    def test_wrong_registration_and_installed_drift_fail_closed(self) -> None:
        value = registration()
        value["capability_source_sha"] = "d" * 40
        with self.assertRaises(refresh.WeatherV9CapabilityBrokerRefreshError):
            valid_plan(registration=value)
        installed = artifact_hashes()
        installed["broker_sha256"] = "d" * 64
        with self.assertRaises(refresh.WeatherV9CapabilityBrokerRefreshError):
            valid_plan(installed_hashes=installed)

    def test_target_widening_beyond_broker_fails_closed(self) -> None:
        for key in ("module_sha256", "socket_sha256", "service_sha256"):
            target = artifact_hashes(broker="c")
            target[key] = "f" * 64
            with self.subTest(key=key), self.assertRaises(refresh.WeatherV9CapabilityBrokerRefreshError):
                valid_plan(target_hashes=target)

    def test_missing_state_or_occupied_staging_fails_closed(self) -> None:
        with self.assertRaises(refresh.WeatherV9CapabilityBrokerRefreshError):
            valid_plan(state_db_present=False)
        with self.assertRaises(refresh.WeatherV9CapabilityBrokerRefreshError):
            valid_plan(temp_paths_absent=False)

    def test_current_source_delta_is_broker_only_from_post83_predecessor(self) -> None:
        broker = "ops/bin/rozkalns-weather-operator-v9-privileged-broker"
        self.assertNotEqual(git_bytes("HEAD", broker), git_bytes(refresh.PREDECESSOR_SOURCE_SHA, broker))
        for path in (
            "ops/lib/deploy_executor/weather_operator_upgrade_v9_host_capability.py",
            "ops/systemd/rozkalns-weather-operator-v9-privileged-broker.socket",
            "ops/systemd/rozkalns-weather-operator-v9-privileged-broker@.service",
        ):
            with self.subTest(path=path):
                self.assertEqual(git_bytes("HEAD", path), git_bytes(refresh.PREDECESSOR_SOURCE_SHA, path))

    def test_contract_wrapper_and_historical_contract_are_bounded(self) -> None:
        self.assertEqual(historical.PREDECESSOR_SOURCE_SHA, "dd0230aa1387a553db81bf59a02e4358f6432a1f")
        contract_path = ROOT / "ops/deploy/weather-operator-v9-capability-broker-refresh-post83.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        self.assertEqual(contract["predecessor_source_sha"], refresh.PREDECESSOR_SOURCE_SHA)
        self.assertEqual(
            tuple((row["category"], row["max_operations"]) for row in contract["mutation_budget"]),
            refresh.MUTATION_BUDGET,
        )
        self.assertEqual(contract["replacement_order"], ["broker", "registration"])
        self.assertEqual(contract["state_db_policy"], "PRESERVE_EXISTING_UNCHANGED")
        self.assertFalse(contract["systemd_mutation"])
        self.assertFalse(contract["queue_or_live_auth_creation"])
        self.assertFalse(contract["automatic_retry"])
        self.assertFalse(contract["automatic_cleanup"])
        self.assertFalse(contract["automatic_rollback"])
        self.assertEqual(contract["historical_authority"]["ops-workflows#83"], "SPENT_LIVE_AUTH_DO_NOT_REUSE")

        wrapper = load_wrapper()
        self.assertIs(wrapper.base.refresh, refresh)
        self.assertEqual(wrapper.base.CONTRACT, contract_path)
        base_source = (ROOT / "scripts/refresh-weather-operator-v9-host-capability-broker.py").read_text(encoding="utf-8")
        self.assertIn('remote", "get-url", "origin"', base_source)
        self.assertIn('"merge-base", "--is-ancestor"', base_source)
        self.assertEqual(base_source.count("os.replace("), 2)
        self.assertNotIn("systemctl", base_source)
        self.assertNotIn("STATE_DB.read_bytes", base_source)
        self.assertNotIn("worktree remove", base_source)
        self.assertNotIn("worktree prune", base_source)


if __name__ == "__main__":
    unittest.main()
