#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPAIR = ROOT / "scripts/repair-weather-v9-predecessor-bootstrap-capability.py"
CONTRACT = ROOT / "ops/deploy/weather-v9-predecessor-bootstrap-capability-repair.json"
DOC = ROOT / "docs/operations/weather-v9-predecessor-bootstrap-capability-repair.md"
WORKFLOW = ROOT / ".github/workflows/validate.yml"


def load_repair():
    spec = importlib.util.spec_from_file_location("weather_v9_bootstrap_capability_repair_test", REPAIR)
    if spec is None or spec.loader is None:
        raise RuntimeError("repair module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair = load_repair()
installer = repair.installer


class WeatherV9BootstrapCapabilityRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = REPAIR.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def baseline(self):
        old_broker = b"old-broker\n"
        target_broker = b"target-broker\n"
        target_files: dict[str, bytes] = {}
        predecessor_files: dict[str, bytes] = {}
        installed_files: dict[str, bytes] = {}
        release_hashes: dict[str, str] = {}
        for relative in installer.RELEASE_FILES:
            if relative == repair.BROKER_RELATIVE:
                predecessor = old_broker
                target = target_broker
                installed = old_broker
            else:
                target = predecessor = installed = ("unchanged:" + relative + "\n").encode()
            target_files[relative] = target
            predecessor_files[relative] = predecessor
            installed_files[str(installer.RELEASE_ROOT / relative)] = installed
            release_hashes[relative] = hashlib.sha256(installed).hexdigest()

        for relative, target in (
            ("ops/systemd/rozkalns-weather-v9-predecessor-bootstrap.socket", installer.SOCKET_TARGET),
            ("ops/systemd/rozkalns-weather-v9-predecessor-bootstrap@.service", installer.SERVICE_TARGET),
        ):
            data = ("unit:" + relative + "\n").encode()
            target_files[relative] = data
            predecessor_files[relative] = data
            installed_files[str(target)] = data

        manager = Path("/srv/test-owner/RPi5_main")
        registration = {
            "schema": repair.REGISTRATION_SCHEMA,
            "source_sha": repair.PREDECESSOR_SOURCE_SHA,
            "source_checkout": "/srv/test-owner/RPi5_main-weather-v9-predecessor-bootstrap-old-trusted",
            "manager_checkout": str(manager),
            "manager_uid": 1000,
            "manager_gid": 1000,
            "release_files": release_hashes,
            "socket_sha256": hashlib.sha256(installed_files[str(installer.SOCKET_TARGET)]).hexdigest(),
            "service_sha256": hashlib.sha256(installed_files[str(installer.SERVICE_TARGET)]).hexdigest(),
        }
        return old_broker, target_broker, target_files, predecessor_files, installed_files, manager, registration

    def test_contract_has_only_two_fixed_replacements(self) -> None:
        self.assertEqual(self.contract["issue"], 634)
        self.assertFalse(self.contract["source_merge_authorizes_live"])
        self.assertEqual(self.contract["predecessor"]["source_sha"], repair.PREDECESSOR_SOURCE_SHA)
        self.assertEqual(self.contract["predecessor"]["broker_sha256"], repair.PREDECESSOR_BROKER_SHA256)
        self.assertEqual(self.contract["target"]["broker_sha256"], repair.TARGET_BROKER_SHA256)
        budget = self.contract["repair"]["mutation_budget"]
        self.assertEqual(
            budget,
            [
                {"category": "filesystem.weather-v9-bootstrap-registration-atomic-replace", "max_operations": 1},
                {"category": "filesystem.weather-v9-bootstrap-broker-atomic-replace", "max_operations": 1},
            ],
        )
        self.assertFalse(self.contract["repair"]["systemd_mutation"])
        self.assertFalse(self.contract["repair"]["replay_mutation"])
        self.assertFalse(self.contract["repair"]["other_release_file_mutation"])
        self.assertEqual(self.contract["preserve"]["release_files_except_broker"], 8)

    def test_preflight_accepts_only_exact_predecessor_and_unchanged_closure(self) -> None:
        old_broker, target_broker, target_files, predecessor_files, installed_files, manager, registration = self.baseline()

        def read_installed(path: Path, **_: object) -> bytes:
            return installed_files[str(path)]

        with (
            mock.patch.object(repair, "repair_source_identity", return_value=("a" * 40, manager, 1000, 1000)),
            mock.patch.object(repair, "require_contract", return_value=self.contract),
            mock.patch.object(repair, "load_registration", return_value=registration),
            mock.patch.object(repair, "_root_dir"),
            mock.patch.object(repair, "source_bytes", side_effect=lambda relative: target_files[relative]),
            mock.patch.object(
                repair,
                "predecessor_source_bytes",
                side_effect=lambda _uid, _gid, relative: predecessor_files[relative],
            ),
            mock.patch.object(repair, "safe_file", side_effect=read_installed),
            mock.patch.object(Path, "exists", return_value=False),
            mock.patch.object(repair, "PREDECESSOR_BROKER_SHA256", hashlib.sha256(old_broker).hexdigest()),
            mock.patch.object(repair, "TARGET_BROKER_SHA256", hashlib.sha256(target_broker).hexdigest()),
        ):
            receipt = repair.preflight()

        self.assertEqual(receipt["result"], "PASS")
        self.assertFalse(receipt["mutation_started"])
        self.assertFalse(receipt["systemd_mutated"])
        self.assertFalse(receipt["replay_mutated"])
        self.assertEqual(receipt["target_release_hashes"][repair.BROKER_RELATIVE], hashlib.sha256(target_broker).hexdigest())

    def test_preflight_blocks_installed_broker_drift(self) -> None:
        old_broker, target_broker, target_files, predecessor_files, installed_files, manager, registration = self.baseline()
        installed_files[str(installer.RELEASE_ROOT / repair.BROKER_RELATIVE)] = b"drifted\n"

        with (
            mock.patch.object(repair, "repair_source_identity", return_value=("a" * 40, manager, 1000, 1000)),
            mock.patch.object(repair, "require_contract", return_value=self.contract),
            mock.patch.object(repair, "load_registration", return_value=registration),
            mock.patch.object(repair, "_root_dir"),
            mock.patch.object(repair, "source_bytes", side_effect=lambda relative: target_files[relative]),
            mock.patch.object(
                repair,
                "predecessor_source_bytes",
                side_effect=lambda _uid, _gid, relative: predecessor_files[relative],
            ),
            mock.patch.object(repair, "safe_file", side_effect=lambda path, **_: installed_files[str(path)]),
            mock.patch.object(Path, "exists", return_value=False),
            mock.patch.object(repair, "PREDECESSOR_BROKER_SHA256", hashlib.sha256(old_broker).hexdigest()),
            mock.patch.object(repair, "TARGET_BROKER_SHA256", hashlib.sha256(target_broker).hexdigest()),
        ):
            with self.assertRaises(repair.RepairError):
                repair.preflight()

    def test_apply_replaces_registration_then_broker_only(self) -> None:
        _, target_broker, _, _, _, manager, _ = self.baseline()
        target_hashes = {
            relative: hashlib.sha256((target_broker if relative == repair.BROKER_RELATIVE else ("unchanged:" + relative + "\n").encode())).hexdigest()
            for relative in installer.RELEASE_FILES
        }
        evidence = {
            "source_sha": "b" * 40,
            "manager_checkout": str(manager),
            "manager_uid": 1000,
            "manager_gid": 1000,
            "target_release_hashes": target_hashes,
            "socket_sha256": "1" * 64,
            "service_sha256": "2" * 64,
        }
        written: dict[str, bytes] = {}
        order: list[str] = []

        def replace(path: Path, data: bytes, _mode: int) -> None:
            order.append(str(path))
            written[str(path)] = data

        def read_after(path: Path, **_: object) -> bytes:
            return written[str(path)]

        with (
            mock.patch.object(repair.os, "geteuid", return_value=0),
            mock.patch.object(repair, "preflight", return_value=evidence),
            mock.patch.object(repair, "source_bytes", return_value=target_broker),
            mock.patch.object(repair, "atomic_replace", side_effect=replace),
            mock.patch.object(repair, "safe_file", side_effect=read_after),
            mock.patch.object(repair, "_root_dir"),
        ):
            receipt = repair.apply()

        self.assertEqual(
            order,
            [
                str(installer.REGISTRATION),
                str(installer.RELEASE_ROOT / repair.BROKER_RELATIVE),
            ],
        )
        registration = json.loads(written[str(installer.REGISTRATION)].decode())
        self.assertEqual(registration["source_sha"], "b" * 40)
        self.assertEqual(registration["release_files"][repair.BROKER_RELATIVE], target_hashes[repair.BROKER_RELATIVE])
        self.assertTrue(receipt["registration_replaced"])
        self.assertTrue(receipt["broker_replaced"])
        self.assertFalse(receipt["systemd_mutated"])
        self.assertFalse(receipt["replay_mutated"])
        self.assertFalse(receipt["bootstrap_apply_started"])

    def test_script_has_no_systemd_cleanup_or_replay_write_surface(self) -> None:
        self.assertEqual(self.script.count("atomic_replace("), 3)  # definition + exactly two calls
        for forbidden in (
            "/usr/bin/systemctl",
            "systemctl ",
            ".unlink(",
            "shutil.rmtree",
            "os.remove(",
            "consumed.json",
            "REPLAY_PATH",
            "/usr/bin/sudo",
        ):
            self.assertNotIn(forbidden, self.script)
        self.assertIn("no retry/cleanup/rollback is authorized", self.script)

    def test_docs_and_ci_bind_issue_634_repair(self) -> None:
        self.assertIn("Issue: #634", self.doc)
        self.assertIn("exactly two atomic replacement operations", self.doc)
        self.assertIn("one new root-broker `preflight` request", self.doc)
        self.assertIn(
            "python3 ./tests/test-weather-v9-predecessor-bootstrap-capability-repair.py",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
