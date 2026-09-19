#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_v10_successor_preflight as preflight

BROKER = ROOT / "ops/bin/rozkalns-weather-operator-v10-successor-preflight-broker"
SOCKET_UNIT = ROOT / "ops/systemd/rozkalns-weather-operator-v10-successor-preflight.socket"
SERVICE_UNIT = ROOT / "ops/systemd/rozkalns-weather-operator-v10-successor-preflight@.service"
DIAGNOSTIC = ROOT / "scripts/diagnose-weather-operator-v10-successor-preflight.py"
INSTALLER = ROOT / "scripts/install-weather-operator-v10-successor-preflight-capability.py"
CONTRACT = ROOT / "ops/deploy/weather-operator-v10-successor-preflight.json"
HISTORICAL_V9_BROKER = ROOT / "ops/bin/rozkalns-weather-operator-v9-privileged-broker"
HISTORICAL_PREDECESSOR_BROKER = ROOT / "ops/bin/rozkalns-weather-v9-predecessor-bootstrap-broker"


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


def _write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


class WeatherV10SuccessorPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.originals = {
            name: getattr(preflight, name)
            for name in (
                "ROOT_UID", "ROOT_GID", "REGISTRATION", "STATE_DB", "MODULE_TARGET",
                "BROKER_TARGET", "SOCKET_TARGET", "SERVICE_TARGET", "BROKER_TEMP", "REGISTRATION_TEMP",
            )
        }

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(preflight, name, value)

    def _fixture(self, root: Path) -> dict[str, str]:
        preflight.ROOT_UID = os.getuid()
        preflight.ROOT_GID = os.getgid()
        preflight.REGISTRATION = root / "registration.json"
        preflight.STATE_DB = root / "state.sqlite3"
        preflight.MODULE_TARGET = root / "module.py"
        preflight.BROKER_TARGET = root / "broker"
        preflight.SOCKET_TARGET = root / "broker.socket"
        preflight.SERVICE_TARGET = root / "broker@.service"
        preflight.BROKER_TEMP = root / ".broker.tmp"
        preflight.REGISTRATION_TEMP = root / ".registration.tmp"
        artifacts = {
            "module_sha256": hashlib.sha256(b"module\n").hexdigest(),
            "broker_sha256": hashlib.sha256(b"broker\n").hexdigest(),
            "socket_sha256": hashlib.sha256(b"socket\n").hexdigest(),
            "service_sha256": hashlib.sha256(b"service\n").hexdigest(),
        }
        _write(preflight.MODULE_TARGET, b"module\n", 0o644)
        _write(preflight.BROKER_TARGET, b"broker\n", 0o755)
        _write(preflight.SOCKET_TARGET, b"socket\n", 0o644)
        _write(preflight.SERVICE_TARGET, b"service\n", 0o644)
        _write(preflight.STATE_DB, b"sqlite-state\n", 0o600)
        registration = {
            "schema": preflight.REGISTRATION_SCHEMA,
            "capability_source_sha": "a" * 40,
            "manager_checkout": "/home/test/RPi5_main",
            "manager_uid": 1000,
            "manager_gid": 1000,
            "artifact_count": 15,
            **artifacts,
        }
        _write(preflight.REGISTRATION, (json.dumps(registration, sort_keys=True, separators=(",", ":")) + "\n").encode(), 0o600)
        return artifacts

    def test_sources_compile_and_executable_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for source in (BROKER, DIAGNOSTIC, INSTALLER, ROOT / "ops/lib/deploy_executor/weather_operator_v10_successor_preflight.py"):
                py_compile.compile(str(source), cfile=str(Path(temp) / (source.name + ".pyc")), doraise=True)
        self.assertEqual(git_mode(BROKER), "100755")
        self.assertEqual(git_mode(DIAGNOSTIC), "100755")
        self.assertEqual(git_mode(INSTALLER), "100755")

    def test_exact_request_returns_allowlisted_read_only_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifacts = self._fixture(Path(temp))
            request = json.dumps({"schema": preflight.REQUEST_SCHEMA, "operation": preflight.OPERATION}).encode()
            receipt = preflight.execute_request(request)
            self.assertEqual(set(receipt), set(preflight.PASS_FIELDS))
            self.assertEqual(receipt["artifact_hashes"], artifacts)
            self.assertEqual(receipt["capability_source_sha"], "a" * 40)
            self.assertTrue(receipt["durable_state_db_valid"])
            self.assertTrue(receipt["staging_paths_absent"])
            self.assertFalse(receipt["host_mutation_started"])
            self.assertFalse(receipt["systemd_mutation_started"])
            self.assertFalse(receipt["network_access_required"])
            encoded = preflight.encode_receipt(receipt)
            self.assertLessEqual(len(encoded), preflight.RECEIPT_MAX_BYTES)
            self.assertNotIn(b"manager_checkout", encoded)
            self.assertNotIn(b"manager_uid", encoded)
            self.assertNotIn(b"manager_gid", encoded)

    def test_request_rejects_extra_or_caller_selected_inputs(self) -> None:
        bad = [
            {"schema": preflight.REQUEST_SCHEMA, "operation": preflight.OPERATION, "path": "/etc/shadow"},
            {"schema": preflight.REQUEST_SCHEMA, "operation": "run", "argv": ["id"]},
            {"schema": preflight.REQUEST_SCHEMA, "operation": preflight.OPERATION, "source_sha": "b" * 40},
        ]
        for value in bad:
            with self.assertRaises(preflight.WeatherV10SuccessorPreflightError):
                preflight.execute_request(json.dumps(value).encode())

    def test_installed_hash_or_staging_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._fixture(root)
            request = json.dumps({"schema": preflight.REQUEST_SCHEMA, "operation": preflight.OPERATION}).encode()
            preflight.BROKER_TARGET.write_bytes(b"drift\n")
            preflight.BROKER_TARGET.chmod(0o755)
            with self.assertRaises(preflight.WeatherV10SuccessorPreflightError):
                preflight.execute_request(request)
            self._fixture(root)
            preflight.BROKER_TEMP.write_text("residue", encoding="utf-8")
            with self.assertRaises(preflight.WeatherV10SuccessorPreflightError):
                preflight.execute_request(request)

    def test_historical_v9_brokers_remain_byte_frozen(self) -> None:
        self.assertEqual(git_blob_sha(HISTORICAL_V9_BROKER), "95d1a0c2a95b75b81d19fe1c359cb49227e9afee")
        self.assertEqual(git_blob_sha(HISTORICAL_PREDECESSOR_BROKER), "d88604e8e6e31b2df18554319a7f2a41b88dfb9a")

    def test_systemd_transport_is_fixed_read_only_and_hardened(self) -> None:
        socket_text = SOCKET_UNIT.read_text(encoding="utf-8")
        service_text = SERVICE_UNIT.read_text(encoding="utf-8")
        self.assertIn("ListenStream=/run/rozkalns-weather-operator-v10-successor-preflight/request.sock", socket_text)
        self.assertIn("SocketUser=andris", socket_text)
        self.assertIn("SocketGroup=andris", socket_text)
        self.assertIn("SocketMode=0600", socket_text)
        self.assertIn("Accept=yes", socket_text)
        self.assertIn("MaxConnections=1", socket_text)
        self.assertIn("StandardInput=socket", service_text)
        self.assertIn("StandardOutput=socket", service_text)
        self.assertIn("ProtectSystem=strict", service_text)
        self.assertIn("ProtectHome=yes", service_text)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", service_text)
        self.assertIn("CapabilityBoundingSet=\n", service_text)
        self.assertNotIn("ReadWritePaths=", service_text)
        self.assertNotIn("Environment=", service_text)
        self.assertNotIn("sudo", service_text.lower())

    def test_contract_keeps_install_activation_and_mutation_separate(self) -> None:
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(value["issue"], 647)
        self.assertEqual(value["predecessor_source_authority"], "ROOT_OWNED_INSTALLED_WEATHER_HOST_CAPABILITY_REGISTRATION")
        self.assertFalse(value["root_preflight_performs_git"])
        self.assertFalse(value["root_preflight_performs_network"])
        self.assertFalse(value["root_preflight_performs_systemd_mutation"])
        self.assertFalse(value["root_preflight_performs_filesystem_mutation"])
        self.assertFalse(value["caller_selected_command_path_argv_environment"])
        self.assertFalse(value["source_merge_authorizes_live"])
        self.assertTrue(value["installation_requires_fresh_live_authorization"])
        self.assertTrue(value["systemd_activation_requires_fresh_live_authorization"])
        self.assertTrue(value["broker_refresh_requires_separate_live_authorization"])


if __name__ == "__main__":
    unittest.main()
