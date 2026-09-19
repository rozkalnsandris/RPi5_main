#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_v10_successor_broker_refresh as refresh

BROKER = ROOT / "ops/bin/rozkalns-weather-operator-v10-successor-privileged-broker"
HISTORICAL_BROKER = ROOT / "ops/bin/rozkalns-weather-operator-v9-privileged-broker"
SCRIPT = ROOT / "scripts/refresh-weather-operator-v10-successor-broker.py"
CONTRACT = ROOT / "ops/deploy/weather-operator-v10-successor-broker-refresh.json"
V10_ENTRYPOINT = ROOT / "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v10"
V10_MODULE = ROOT / "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v10.py"


def git_blob_sha(path: Path) -> str:
    return subprocess.run(
        ["git", "hash-object", str(path)], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout.strip()


def git_mode(path: Path) -> str:
    row = subprocess.run(
        ["git", "ls-files", "-s", "--", str(path.relative_to(ROOT))], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout.strip()
    return row.split()[0] if row else ""


class WeatherV10SuccessorBrokerTests(unittest.TestCase):
    def test_python_sources_compile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for source in (BROKER, SCRIPT, ROOT / "ops/lib/deploy_executor/weather_operator_v10_successor_broker_refresh.py"):
                py_compile.compile(str(source), cfile=str(Path(temp) / (source.name + ".pyc")), doraise=True)

    def test_historical_v9_broker_is_byte_frozen(self) -> None:
        self.assertEqual(git_blob_sha(HISTORICAL_BROKER), "95d1a0c2a95b75b81d19fe1c359cb49227e9afee")

    def test_successor_is_executable_and_pins_v10_source(self) -> None:
        self.assertEqual(git_mode(BROKER), "100755")
        text = BROKER.read_text(encoding="utf-8")
        self.assertIn('OPERATION_ID = "rpi5-main.weather-operator-upgrade-v10.v1"', text)
        self.assertIn('TARGET_ALIAS = "rpi5-main-weather-operator-upgrade-v10"', text)
        self.assertIn('TRUSTED_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v10-trusted"', text)
        self.assertIn('PRESERVED_V9_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v9-8026125-historical"', text)
        self.assertIn('OLD_SHA256 = "48c8c5fb0cdc005bf0e4fbb05a203297e05d7ef62689ddd0d6d717c13acc0fcb"', text)
        self.assertIn('NEW_SHA256 = "a36e7e7673855e1d9aa49b676133e188ee2a24a0711ba46f2844af6f60240a03"', text)
        self.assertIn('UPGRADE_ENTRYPOINT_BLOB = "86f1f311c252e42a201d75d6e92f38bf255ecf5a"', text)
        self.assertIn('UPGRADE_MODULE_BLOB = "07e1908870f5051119aa61a2e899d0ae9ba466ab"', text)
        self.assertIn('"no v9 LIVE authorization reuse"', text)
        self.assertNotIn("subprocess.run(request", text)

    def test_v10_reviewed_blobs_are_still_exact(self) -> None:
        self.assertEqual(git_blob_sha(V10_ENTRYPOINT), "86f1f311c252e42a201d75d6e92f38bf255ecf5a")
        self.assertEqual(git_blob_sha(V10_MODULE), "07e1908870f5051119aa61a2e899d0ae9ba466ab")

    def test_dynamic_predecessor_plan_preserves_nonbroker_artifacts(self) -> None:
        predecessor_sha = "1" * 40
        target_sha = "2" * 40
        predecessor = {
            "module_sha256": "a" * 64,
            "broker_sha256": "b" * 64,
            "socket_sha256": "c" * 64,
            "service_sha256": "d" * 64,
        }
        registration = {
            "schema": refresh.REGISTRATION_SCHEMA,
            "capability_source_sha": predecessor_sha,
            "manager_checkout": "/home/test/RPi5_main",
            "manager_uid": 1000,
            "manager_gid": 1000,
            "artifact_count": 15,
            **predecessor,
        }
        target = dict(predecessor)
        target["broker_sha256"] = "e" * 64
        plan = refresh.build_refresh_plan(
            source_sha=target_sha,
            predecessor_source_sha=predecessor_sha,
            registration=registration,
            predecessor_hashes=predecessor,
            installed_hashes=predecessor,
            target_hashes=target,
            state_db_present=True,
            temp_paths_absent=True,
        )
        self.assertEqual(plan.predecessor_source_sha, predecessor_sha)
        self.assertEqual(plan.new_registration["capability_source_sha"], target_sha)
        self.assertEqual(plan.new_registration["broker_sha256"], "e" * 64)
        for key in refresh.UNCHANGED_ARTIFACT_KEYS:
            self.assertEqual(plan.new_registration[key], predecessor[key])

    def test_refresh_rejects_unbound_or_widened_predecessor(self) -> None:
        predecessor_sha = "1" * 40
        base = {
            "module_sha256": "a" * 64,
            "broker_sha256": "b" * 64,
            "socket_sha256": "c" * 64,
            "service_sha256": "d" * 64,
        }
        registration = {
            "schema": refresh.REGISTRATION_SCHEMA,
            "capability_source_sha": predecessor_sha,
            "manager_checkout": "/home/test/RPi5_main",
            "manager_uid": 1000,
            "manager_gid": 1000,
            "artifact_count": 15,
            **base,
        }
        target = dict(base)
        target["broker_sha256"] = "e" * 64
        with self.assertRaises(refresh.WeatherV10SuccessorBrokerRefreshError):
            refresh.build_refresh_plan(
                source_sha="2" * 40, predecessor_source_sha="3" * 40,
                registration=registration, predecessor_hashes=base,
                installed_hashes=base, target_hashes=target,
                state_db_present=True, temp_paths_absent=True,
            )
        widened = dict(target)
        widened["socket_sha256"] = "f" * 64
        with self.assertRaises(refresh.WeatherV10SuccessorBrokerRefreshError):
            refresh.build_refresh_plan(
                source_sha="2" * 40, predecessor_source_sha=predecessor_sha,
                registration=registration, predecessor_hashes=base,
                installed_hashes=base, target_hashes=widened,
                state_db_present=True, temp_paths_absent=True,
            )

    def test_contract_keeps_live_as_separate_gate(self) -> None:
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(value["issue"], 643)
        self.assertEqual(value["predecessor_source_authority"], "ROOT_OWNED_INSTALLED_REGISTRATION_CAPABILITY_SOURCE_SHA")
        self.assertFalse(value["systemd_mutation"])
        self.assertFalse(value["queue_or_live_auth_creation"])
        self.assertFalse(value["source_merge_authorizes_live"])
        self.assertEqual(value["replacement_order"], ["broker", "registration"])
        self.assertIn("no v9 LIVE authorization reuse", value["explicit_exclusions"])


if __name__ == "__main__":
    unittest.main()
