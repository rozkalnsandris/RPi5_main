#!/usr/bin/env python3
"""Static fail-closed review of the inert CV-first SIMPLE-DEPLOY timer templates."""
from __future__ import annotations

from configparser import ConfigParser
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "ops" / "systemd"
DOC = ROOT / "docs" / "SIMPLE_DEPLOY_PER_TARGET_TIMER_V1.md"
REGISTRY = ROOT / "ops" / "deploy" / "simple-deploy-targets-v1.json"


def unit(path: Path) -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    with path.open(encoding="utf-8") as f:
        parser.read_file(f)
    return parser


class PerTargetTimerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.old_service = unit(UNITS / "rozkalns-simple-deployer.service")
        cls.old_timer = unit(UNITS / "rozkalns-simple-deployer.timer")
        cls.service = unit(UNITS / "rozkalns-simple-deployer@.service")
        cls.timer = unit(UNITS / "rozkalns-simple-deployer@.timer")
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.doc = DOC.read_text(encoding="utf-8")

    def test_service_keeps_unchanged_runtime_sandbox(self) -> None:
        old = dict(self.old_service["Service"])
        new = dict(self.service["Service"])
        self.assertEqual(set(old), set(new))
        self.assertEqual(
            old.pop("ExecStart"),
            "/usr/local/libexec/rozkalns-simple-deployer/rozkalns-simple-deployer --all",
        )
        self.assertEqual(
            new.pop("ExecStart"),
            "/usr/local/libexec/rozkalns-simple-deployer/rozkalns-simple-deployer --target %i",
        )
        self.assertEqual(old, new)
        self.assertEqual(self.service["Unit"]["Wants"], self.old_service["Unit"]["Wants"])
        self.assertEqual(self.service["Unit"]["After"], self.old_service["Unit"]["After"])
        self.assertFalse(self.service.has_section("Install"))
        self.assertNotIn("/bin/sh", str(self.service.items("Service")))

    def test_timer_only_targets_same_single_instance(self) -> None:
        t = self.timer["Timer"]
        self.assertEqual(t["Unit"], "rozkalns-simple-deployer@%i.service")
        self.assertEqual(t["OnActiveSec"], "2min")
        self.assertEqual(t["OnUnitInactiveSec"], "2min")
        self.assertEqual(t["AccuracySec"], "15s")
        self.assertEqual(t["RandomizedDelaySec"], "10s")
        self.assertEqual(set(t), {"Unit", "OnActiveSec", "OnUnitInactiveSec", "AccuracySec", "RandomizedDelaySec"})
        self.assertEqual(dict(self.timer["Install"]), {"WantedBy": "timers.target"})
        self.assertFalse(self.timer.has_option("Install", "DefaultInstance"))
        self.assertNotIn("OnBootSec", t)
        self.assertNotIn("Persistent", t)
        self.assertEqual(self.old_timer["Timer"]["Unit"], "rozkalns-simple-deployer.service")

    def test_cv_first_and_static_registry_without_reduction(self) -> None:
        self.assertTrue(self.registry["execution_enabled"])
        targets = self.registry["targets"]
        aliases = [t["target_alias"] for t in targets]
        self.assertEqual(len(aliases), 5)
        self.assertEqual(len(set(aliases)), 5)
        self.assertIn("rozkalns-cv-rpi5", aliases)
        self.assertIn("hermes-deals", aliases)
        self.assertIn("hermes-tech-public-rpi5", aliases)
        self.assertIn("rozkalns-simple-deployer@rozkalns-cv-rpi5.timer", self.doc)
        self.assertIn("not a future release or timer authorization", self.doc)

    def test_fail_closed_activation_boundary_is_documented(self) -> None:
        for marker in (
            "SOURCE-ONLY / NOT INSTALLED / NOT ACTIVATED",
            "separate exact owner LIVE gate",
            "generic `--all` timer disabled/inactive",
            "future",
            "GHCR",
            "receipt",
            "STOP",
            "Weather, Coloring Pages, Hermes Deals or Hermes Tech",
            "Production deploy/change REQUIRED: NO",
            "may occur immediately",
        ):
            self.assertIn(marker, self.doc)
        self.assertNotIn("systemctl enable --now", self.doc)
        self.assertNotIn("systemctl start", self.doc)
        for forbidden in ("192.168.", "10.0.0.", "Bearer ", "PRIVATE_KEY", "--all --target"):
            self.assertNotIn(forbidden, self.doc)


if __name__ == "__main__":
    unittest.main()
