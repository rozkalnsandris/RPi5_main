#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/install-simple-deploy-weather-data-v1.py"
spec = importlib.util.spec_from_file_location("weather_data_installer", PATH)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)
CONTRACT = json.loads((ROOT / "ops/deploy/simple-deploy-weather-data-v1.json").read_text())


class Tests(unittest.TestCase):
    def test_fixed_install_targets_and_disabled_default_contract(self):
        actual = [(str(item.target), f"{item.mode:04o}") for item in installer.TRACKED_FILES]
        self.assertEqual(actual, [
            ("/usr/local/libexec/rozkalns-simple-deployer/rozkalns-simple-deploy-weather-data", "0555"),
            ("/usr/local/libexec/rozkalns-simple-deployer/simple_deploy_weather_data_v1.py", "0444"),
            ("/etc/rozkalns-simple-deployer/weather-data-v1.json", "0444"),
            ("/etc/systemd/system/rozkalns-weather-public-ingest.service", "0644"),
            ("/etc/systemd/system/rozkalns-weather-public-ingest.timer", "0644"),
            ("/etc/rozkalns-simple-deployer/weather-data-v1.identity.json", "0444"),
        ])
        self.assertTrue(CONTRACT["recurring"]["installed_disabled_by_default"])
        self.assertFalse(CONTRACT["installer"]["daemon_reload"])
        self.assertFalse(CONTRACT["installer"]["service_start"])
        self.assertFalse(CONTRACT["installer"]["timer_enable_or_start"])
        self.assertFalse(CONTRACT["installer"]["docker_command"])
        self.assertFalse(CONTRACT["installer"]["database_or_data_mutation"])

    def test_identity_is_exact_source_sha_only(self):
        payload = json.loads(installer._identity_bytes("a" * 40))
        self.assertEqual(payload, {
            "schema": installer.CAPABILITY_IDENTITY_SCHEMA,
            "repository": "rozkalnsandris/RPi5_main",
            "source_sha": "a" * 40,
        })
        with self.assertRaises(installer.WeatherDataInstallerError):
            installer._identity_bytes("main")

    def test_existing_target_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "occupied"
            path.write_text("x")
            with self.assertRaisesRegex(installer.WeatherDataInstallerError, "requires separate reconciliation"):
                installer._require_absent(path)

    def test_receipt_never_claims_activation_or_data_write(self):
        receipt = json.loads(installer._receipt("TEST", "a" * 40, installer.Progress()))
        self.assertFalse(receipt["daemon_reload_performed"])
        self.assertFalse(receipt["service_started"])
        self.assertFalse(receipt["timer_enabled_or_started"])
        self.assertFalse(receipt["docker_command_executed"])
        self.assertFalse(receipt["database_or_data_mutation"])
        self.assertFalse(receipt["automatic_retry"])
        self.assertFalse(receipt["automatic_cleanup"])
        self.assertFalse(receipt["automatic_rollback"])

    def test_installer_source_has_no_systemd_or_docker_execution(self):
        source = PATH.read_text()
        self.assertNotIn("systemctl", source)
        self.assertNotIn('(\"docker\",', source)
        self.assertIn("shell=False", source)
        self.assertNotIn("os.system(", source)


if __name__ == "__main__":
    unittest.main()
