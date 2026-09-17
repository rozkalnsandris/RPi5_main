#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-weather-operator-v7-host-capability.py"
BROKER = ROOT / "ops/bin/rozkalns-weather-operator-v7-privileged-broker"
REPAIR = ROOT / "scripts/repair-weather-operator-v7-host-capability-registration.py"
CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v7-host-capability-repair.json"
DOC = ROOT / "docs/WEATHER_OPERATOR_V7_REPAIR_593.md"
WORKFLOW = ROOT / ".github/workflows/validate.yml"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"


class WeatherV7RegistrationRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installer = INSTALLER.read_text(encoding="utf-8")
        cls.broker = BROKER.read_text(encoding="utf-8")
        cls.repair = REPAIR.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_first_install_registers_canonical_manager_not_linked_source_root(self) -> None:
        self.assertIn('run_git("rev-parse", "--path-format=absolute", "--git-common-dir")', self.installer)
        self.assertIn('if common.name != ".git"', self.installer)
        self.assertIn('if manager.name != "RPi5_main"', self.installer)
        self.assertIn('"manager_checkout": str(manager)', self.installer)
        self.assertNotIn('"manager_checkout": str(ROOT)', self.installer)

    def test_linked_worktree_resolves_to_primary_rpi5_main_manager(self) -> None:
        spec = importlib.util.spec_from_file_location("weather_v7_installer_593_test", INSTALLER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec is not None else None)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            manager = base / "RPi5_main"
            worktree = base / "RPi5_main-weather-v7-host-capability-repair-source-trusted"
            subprocess.run(
                ["git", "init", "-b", "main", str(manager)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(manager), "remote", "add", "origin", ORIGIN],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(manager),
                    "-c", "user.name=Weather v7 test",
                    "-c", "user.email=weather-v7-test.invalid",
                    "commit", "--allow-empty", "-m", "fixture",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(manager), "worktree", "add", "--detach", str(worktree), "HEAD"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            with mock.patch.object(module, "ROOT", worktree):
                self.assertEqual(module.canonical_manager_checkout(), manager.resolve())

    def test_broker_git_trust_is_exact_command_scoped_and_not_persistent(self) -> None:
        self.assertIn('f"safe.directory={reviewed}"', self.broker)
        self.assertIn('"/usr/bin/git"', self.broker)
        self.assertIn('cap._run_git = _bounded_run_git', self.broker)
        self.assertIn('cap._bootstrap_checkout = _bootstrap_checkout', self.broker)
        self.assertNotIn("safe.directory=*", self.broker)
        for forbidden in ("--global", "--system", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
            self.assertNotIn(forbidden, self.broker)

    def test_broker_worktree_add_uses_the_same_bounded_helper(self) -> None:
        tree = ast.parse(self.broker)
        bootstrap = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_bootstrap_checkout"
        )
        calls = [
            node for node in ast.walk(bootstrap)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_bounded_run_git"
        ]
        rendered = [ast.unparse(node) for node in calls]
        self.assertTrue(any("'fetch'" in call and "'origin'" in call for call in rendered))
        self.assertTrue(any("'worktree'" in call and "'add'" in call for call in rendered))
        direct_subprocess = [
            node for node in ast.walk(bootstrap)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ]
        self.assertEqual(direct_subprocess, [])

    def test_repair_contract_is_two_target_fail_closed_and_non_live(self) -> None:
        self.assertEqual(self.contract["issue"], 593)
        self.assertFalse(self.contract["source_merge_authorizes_live"])
        self.assertEqual(
            self.contract["trusted_source_checkout"]["name"],
            "RPi5_main-weather-v7-host-capability-repair-source-trusted",
        )
        self.assertEqual(
            [item["category"] for item in self.contract["repair"]["mutation_budget"]],
            [
                "filesystem.weather-v7-capability-broker-atomic-replace",
                "filesystem.weather-v7-capability-registration-atomic-replace",
            ],
        )
        self.assertEqual(len(self.contract["repair"]["fixed_targets"]), 2)
        self.assertFalse(self.contract["repair"]["systemd_mutation"])
        self.assertFalse(self.contract["repair"]["operator_replacement"])
        self.assertFalse(self.contract["repair"]["v7_checkout_creation"])
        self.assertFalse(self.contract["failure"]["automatic_retry"])
        self.assertFalse(self.contract["failure"]["automatic_cleanup"])
        self.assertFalse(self.contract["failure"]["automatic_rollback"])
        self.assertFalse(self.contract["failed_authorization"]["reuse_allowed"])

    def test_repair_installer_binds_known_predecessor_and_mutation_boundary(self) -> None:
        self.assertIn(
            'PREDECESSOR_SOURCE_SHA = "76496822e73e8ce628915978a1fea7970a2230ea"',
            self.repair,
        )
        self.assertIn(
            'PREDECESSOR_BROKER_SHA256 = "69d203453f4769e694f93a7840b3f81881d1cb49ea105322d3ad508a5b55925f"',
            self.repair,
        )
        self.assertIn('parser.add_argument("--apply", action="store_true")', self.repair)
        self.assertIn("os.geteuid() != 0", self.repair)
        self.assertIn("atomic_replace(installer.BROKER_TARGET", self.repair)
        self.assertIn("atomic_replace(installer.REGISTRATION", self.repair)
        self.assertLess(
            self.repair.index("mutation_started = True"),
            self.repair.index("atomic_replace(installer.BROKER_TARGET"),
        )
        self.assertNotIn("systemctl(", self.repair)
        self.assertNotIn("/usr/bin/sudo", self.repair)
        self.assertNotIn("safe.directory=*", self.repair)
        self.assertIn("no retry/cleanup/rollback is authorized", self.repair)

    def test_docs_and_ci_wire_the_recovery_lane(self) -> None:
        self.assertIn("Weather v7 broker registration / Git trust repair (#593)", self.doc)
        self.assertIn("ops-workflows#65", self.doc)
        self.assertIn("brand-new", self.doc)
        self.assertIn(
            "python3 ./tests/test-weather-v7-host-capability-registration-repair.py",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
