#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_v9_capability_module_refresh as refresh
from deploy_executor import weather_operator_v9_capability_refresh as old_refresh
from deploy_executor import weather_operator_upgrade_v9_host_capability as cap

POST_615_SOURCE_SHA = "dd0230aa1387a553db81bf59a02e4358f6432a1f"
V9_REVIEWED_TARGET_SOURCE_SHA = "84e129909831bd8111c4f4c1f6618b7fff2a803b"
V9_TARGET_SOURCE_PATH = "ops/lib/deploy_executor/weather_public_runtime_operator.py"


def artifact_hashes(*, module: str = "1") -> dict[str, str]:
    return {
        "module_sha256": module * 64,
        "broker_sha256": "2" * 64,
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
        "target_hashes": artifact_hashes(module="c"),
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


class WeatherV9CapabilityModuleRefreshTests(unittest.TestCase):
    def test_exact_predecessor_builds_module_only_refresh_plan(self) -> None:
        plan = valid_plan()
        self.assertEqual(plan.predecessor_source_sha, refresh.PREDECESSOR_SOURCE_SHA)
        self.assertEqual(plan.new_registration["capability_source_sha"], "a" * 40)
        self.assertEqual(plan.new_registration["module_sha256"], "c" * 64)
        self.assertEqual(plan.new_registration["broker_sha256"], "2" * 64)
        self.assertEqual(plan.mutation_budget, refresh.MUTATION_BUDGET)
        self.assertEqual(plan.state_db_policy, "PRESERVE_EXISTING_UNCHANGED")
        self.assertFalse(plan.systemd_mutation)
        self.assertFalse(plan.queue_or_live_auth_created)

    def test_wrong_registration_source_is_rejected(self) -> None:
        value = registration()
        value["capability_source_sha"] = "d" * 40
        with self.assertRaises(refresh.WeatherV9CapabilityModuleRefreshError):
            valid_plan(registration=value)

    def test_installed_hash_drift_is_rejected(self) -> None:
        installed = artifact_hashes()
        installed["broker_sha256"] = "d" * 64
        with self.assertRaises(refresh.WeatherV9CapabilityModuleRefreshError):
            valid_plan(installed_hashes=installed)

    def test_target_widening_beyond_module_is_rejected(self) -> None:
        for key in ("broker_sha256", "socket_sha256", "service_sha256"):
            target = artifact_hashes(module="c")
            target[key] = "f" * 64
            with self.subTest(key=key), self.assertRaises(
                refresh.WeatherV9CapabilityModuleRefreshError
            ):
                valid_plan(target_hashes=target)

    def test_unchanged_target_module_is_rejected(self) -> None:
        with self.assertRaises(refresh.WeatherV9CapabilityModuleRefreshError):
            valid_plan(target_hashes=artifact_hashes())

    def test_missing_replay_state_or_partial_staging_is_rejected(self) -> None:
        with self.assertRaises(refresh.WeatherV9CapabilityModuleRefreshError):
            valid_plan(state_db_present=False)
        with self.assertRaises(refresh.WeatherV9CapabilityModuleRefreshError):
            valid_plan(temp_paths_absent=False)

    def test_registration_round_trip_preserves_manager_and_updates_exact_artifacts(self) -> None:
        plan = valid_plan()
        encoded = refresh.registration_bytes(plan.new_registration)
        decoded = json.loads(encoded.decode("utf-8"))
        self.assertEqual(decoded["manager_checkout"], registration()["manager_checkout"])
        self.assertEqual(decoded["manager_uid"], registration()["manager_uid"])
        self.assertEqual(decoded["manager_gid"], registration()["manager_gid"])
        self.assertEqual(decoded["artifact_count"], 15)
        self.assertEqual(decoded["capability_source_sha"], "a" * 40)
        self.assertEqual(decoded["module_sha256"], "c" * 64)
        self.assertEqual(decoded["broker_sha256"], "2" * 64)

    def test_post_615_source_delta_is_module_only_from_post_610_predecessor(self) -> None:
        module = "ops/lib/deploy_executor/weather_operator_upgrade_v9_host_capability.py"
        self.assertNotEqual(
            git_bytes(POST_615_SOURCE_SHA, module),
            git_bytes(refresh.PREDECESSOR_SOURCE_SHA, module),
        )
        for path in (
            "ops/bin/rozkalns-weather-operator-v9-privileged-broker",
            "ops/systemd/rozkalns-weather-operator-v9-privileged-broker.socket",
            "ops/systemd/rozkalns-weather-operator-v9-privileged-broker@.service",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    git_bytes(POST_615_SOURCE_SHA, path),
                    git_bytes(refresh.PREDECESSOR_SOURCE_SHA, path),
                )

    def test_host_capability_postcondition_is_bound_to_reviewed_v9_target_source(self) -> None:
        target = git_bytes(V9_REVIEWED_TARGET_SOURCE_SHA, V9_TARGET_SOURCE_PATH)
        merged = json.loads(
            (ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v9.json").read_text(
                encoding="utf-8"
            )
        )
        expected = hashlib.sha256(target).hexdigest()
        self.assertEqual(expected, "542412bc15123e6dc8c3f6505983676ba5c9622793ea7611693aacf13fb36974")
        self.assertEqual(merged["new_sha256"], expected)
        self.assertEqual(cap.NEW_SHA256, expected)

    def test_contract_and_operator_preserve_fail_closed_module_refresh_boundary(self) -> None:
        contract = json.loads(
            (ROOT / "ops/deploy/weather-operator-v9-capability-module-refresh.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contract["predecessor_source_sha"], refresh.PREDECESSOR_SOURCE_SHA)
        self.assertEqual(
            tuple((row["category"], row["max_operations"]) for row in contract["mutation_budget"]),
            refresh.MUTATION_BUDGET,
        )
        self.assertEqual(contract["replacement_order"], ["module", "registration"])
        self.assertEqual(contract["state_db_policy"], "PRESERVE_EXISTING_UNCHANGED")
        self.assertFalse(contract["systemd_mutation"])
        self.assertFalse(contract["queue_or_live_auth_creation"])
        self.assertFalse(contract["automatic_retry"])
        self.assertFalse(contract["automatic_cleanup"])
        self.assertFalse(contract["automatic_rollback"])
        self.assertEqual(contract["historical_authority"]["ops-workflows#72"], "SPENT_LIVE_AUTH_DO_NOT_REUSE")

        operator = (ROOT / "scripts/refresh-weather-operator-v9-host-capability-module.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("state_snapshot() != before_state", operator)
        self.assertEqual(operator.count("os.replace("), 2)
        self.assertNotIn("systemctl", operator)
        self.assertNotIn("STATE_DB.read_bytes", operator)
        self.assertNotIn("os.unlink", operator)
        self.assertNotIn("os.remove", operator)
        self.assertNotIn("worktree remove", operator)
        self.assertNotIn("worktree prune", operator)

    def test_operator_binds_root_git_to_exact_reviewed_checkout_command_scope(self) -> None:
        operator = (ROOT / "scripts/refresh-weather-operator-v9-host-capability-module.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('f"safe.directory={ROOT}"', operator)
        self.assertNotIn("git config --global", operator)
        self.assertNotIn("git config --system", operator)

    def test_existing_broker_refresh_contract_remains_frozen(self) -> None:
        self.assertEqual(
            old_refresh.PREDECESSOR_SOURCE_SHA,
            "68ef2b73dc8600dd63cf2a3b6920814e27313600",
        )
        self.assertIn("module_sha256", old_refresh.UNCHANGED_ARTIFACT_KEYS)
        self.assertEqual(
            old_refresh.MUTATION_BUDGET,
            (
                ("filesystem.weather-operator-v9-capability-refresh-stage", 2),
                ("filesystem.weather-operator-v9-capability-refresh-atomic-replace", 2),
            ),
        )


if __name__ == "__main__":
    unittest.main()
