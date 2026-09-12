from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "ops/deploy/weather-public-runtime-helper-install.json"
NEW = ROOT / "ops/deploy/weather-public-runtime-helper-install-composite.json"


class WeatherCompositeHelperInstallContractTests(unittest.TestCase):
    def test_composite_manifest_versions_checkout_identity_without_changing_artifacts(self) -> None:
        old = json.loads(OLD.read_text(encoding="utf-8"))
        new = json.loads(NEW.read_text(encoding="utf-8"))
        self.assertEqual(old["contract"], "rozkalns-weather.public-runtime-helper-install.v1")
        self.assertEqual(new["contract"], "rozkalns-weather.public-runtime-helper-install-composite.v1")
        self.assertEqual(new["status"], "SOURCE_ONLY_COMPOSITE_INSTALL_DISABLED")
        self.assertEqual(new["trusted_checkout_bootstrap_contract"], "ops/deploy/rpi5-main-weather-public-runtime-composite-trusted-checkout-bootstrap.json")
        self.assertEqual(new["trusted_checkout_target"], "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-composite-trusted")
        self.assertEqual(new["artifact_count"], 13)
        self.assertEqual(new["artifacts"], old["artifacts"])
        self.assertEqual(new["closure_policy"], old["closure_policy"])
        self.assertTrue(all(value is False for value in new["activation"].values()))
        self.assertNotEqual(new["trusted_checkout_target"], old["trusted_checkout_target"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
