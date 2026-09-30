#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "ops/recovery/weather_v9_predecessor_state_bootstrap.py"
BASE_TEST = ROOT / "tests/test-weather-v9-capability-state-bootstrap.py"
CONTRACT = ROOT / "ops/recovery/weather_v9_predecessor_state_bootstrap.contract.json"
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor.state import StateStore


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


recovery = load_module("weather_v9_predecessor_state_bootstrap", RECOVERY)
base_test = load_module("weather_v9_capability_state_bootstrap_test_fixture", BASE_TEST)
Fixture = base_test.Fixture

EXECUTION_SHA = "b" * 40
BROKER_SOURCE = "ops/bin/rozkalns-weather-operator-v9-privileged-broker"
SERVICE_SOURCE = "ops/systemd/rozkalns-weather-operator-v9-privileged-broker@.service"


def prepare_installer(fixture: Fixture, *, ancestor: bool = True):
    installer = fixture.installer
    installer.SERVICE_SOURCE = SERVICE_SOURCE
    installer.source_sha = lambda: EXECUTION_SHA
    installer.render_service_unit = lambda data, _manager: data

    def run_git(*args: str, check: bool = True):
        if args[:2] == ("merge-base", "--is-ancestor"):
            return types.SimpleNamespace(returncode=0 if ancestor else 1, stdout="")
        if len(args) == 4 and args[0] == "ls-tree" and args[2] == "--":
            source = args[3]
            mode = next(
                mode
                for item_source, _target, mode in installer.ARTIFACTS
                if item_source == source
            )
            git_mode = "100755" if mode & 0o111 else "100644"
            return types.SimpleNamespace(
                returncode=0,
                stdout=f"{git_mode} blob {'1' * 40}\t{source}\n",
            )
        if len(args) == 2 and args[0] == "show":
            commit_path = args[1]
            prefix = recovery.PREDECESSOR_SOURCE_SHA + ":"
            if not commit_path.startswith(prefix):
                return types.SimpleNamespace(returncode=1, stdout="")
            source = commit_path[len(prefix):]
            data = fixture.expected[source]
            return types.SimpleNamespace(
                returncode=0,
                stdout=data.decode("utf-8"),
            )
        raise AssertionError(f"unexpected git invocation: {args!r}")

    installer.run_git = run_git
    return installer


class RecoveryFixture:
    def __init__(self, *, state_root_present: bool = True, ancestor: bool = True):
        self.fixture = Fixture(state_root_present=state_root_present)
        self.installer = prepare_installer(self.fixture, ancestor=ancestor)
        self.patchers = (
            mock.patch.object(recovery, "SUPPORT_ROOT", self.fixture.support),
            mock.patch.object(recovery, "PACKAGE_ROOT", self.fixture.package),
            mock.patch.object(recovery, "BROKER_PATH", self.fixture.broker),
            mock.patch.object(recovery, "CONFIG_ROOT", self.fixture.config),
            mock.patch.object(recovery, "REGISTRATION_PATH", self.fixture.registration),
            mock.patch.object(recovery, "STATE_ROOT", self.fixture.state_root),
            mock.patch.object(recovery, "STATE_DB_PATH", self.fixture.state_db),
            mock.patch.object(recovery, "SYSTEMD_ROOT", self.fixture.systemd),
            mock.patch.object(recovery, "SOCKET_UNIT_PATH", self.fixture.socket),
            mock.patch.object(recovery, "SERVICE_UNIT_PATH", self.fixture.service),
            mock.patch.object(recovery, "MODULE_PATH", self.fixture.module),
            mock.patch.object(
                recovery, "REGISTRATION_TEMP", self.fixture.registration_temp
            ),
            mock.patch.object(recovery, "KNOWN_STAGING_PATHS", self.fixture.staging),
            mock.patch.object(recovery, "_load_installer", lambda: self.installer),
            mock.patch.object(recovery, "_validate_contract", lambda _installer: None),
            mock.patch.object(recovery.base, "ROOT_UID", os.getuid()),
            mock.patch.object(recovery.base, "ROOT_GID", os.getgid()),
        )

    def __enter__(self):
        self.active = []
        for patcher in self.patchers:
            self.active.append(patcher)
            patcher.start()
        return self.fixture

    def __exit__(self, exc_type, exc, tb):
        for patcher in reversed(self.active):
            patcher.stop()
        self.fixture.tmp.cleanup()


class WeatherV9PredecessorStateBootstrapTests(unittest.TestCase):
    def test_contract_exact_binds_predecessor_and_live_boundary(self) -> None:
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["schema"],
            "rozkalns.rpi5-main.weather-operator-v9-predecessor-state-bootstrap.v1",
        )
        self.assertEqual(payload["issue"], 625)
        self.assertEqual(
            payload["predecessor_source_sha"],
            recovery.PREDECESSOR_SOURCE_SHA,
        )
        self.assertEqual(
            payload["registration_binding_source_sha"],
            recovery.PREDECESSOR_SOURCE_SHA,
        )
        self.assertEqual(
            payload["accepted_baseline"],
            {"registration": "ABSENT", "state_db": "ABSENT"},
        )
        self.assertEqual(payload["artifact_count"], 15)
        self.assertTrue(payload["registration_published_last"])
        self.assertFalse(payload["systemd_mutation"])
        self.assertFalse(payload["automatic_retry"])
        self.assertFalse(payload["automatic_cleanup"])
        self.assertFalse(payload["automatic_rollback"])
        self.assertFalse(payload["source_merge_authorizes_live"])

    def test_source_has_no_direct_privilege_or_systemd_command_path(self) -> None:
        source = RECOVERY.read_text(encoding="utf-8")
        self.assertNotIn("systemctl", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("/usr/bin/sudo", source)
        self.assertLess(
            source.index("StateStore(STATE_DB_PATH, bootstrap=True)"),
            source.index("os.replace(REGISTRATION_TEMP"),
        )

    def test_happy_path_bootstraps_predecessor_registration_last(self) -> None:
        with RecoveryFixture(state_root_present=False) as fixture:
            before = {
                path: path.read_bytes()
                for _source, path, _mode in fixture.artifacts
            }
            with (
                mock.patch.object(recovery.os, "geteuid", lambda: 0),
                mock.patch.object(recovery, "_load_state_store", lambda: StateStore),
            ):
                receipt = recovery.apply()

            self.assertEqual(receipt["result"], "PASS")
            self.assertEqual(receipt["execution_source_sha"], EXECUTION_SHA)
            self.assertEqual(
                receipt["registration_source_sha"],
                recovery.PREDECESSOR_SOURCE_SHA,
            )
            self.assertEqual(receipt["next_gate"], "POST83_BROKER_REFRESH")
            self.assertTrue(fixture.state_db.is_file())
            self.assertEqual(stat.S_IMODE(fixture.state_db.stat().st_mode), 0o600)

            registration = json.loads(
                fixture.registration.read_text(encoding="utf-8")
            )
            self.assertEqual(
                registration["capability_source_sha"],
                recovery.PREDECESSOR_SOURCE_SHA,
            )
            self.assertEqual(registration["artifact_count"], 15)
            self.assertEqual(
                stat.S_IMODE(fixture.registration.stat().st_mode), 0o600
            )
            self.assertFalse(fixture.registration_temp.exists())

            after = {
                path: path.read_bytes()
                for _source, path, _mode in fixture.artifacts
            }
            self.assertEqual(after, before)

    def test_preflight_accepts_predecessor_broker_and_rejects_target_broker(self) -> None:
        with RecoveryFixture():
            plan = recovery.preflight_material()
            self.assertEqual(
                plan.registration_source_sha,
                recovery.PREDECESSOR_SOURCE_SHA,
            )

        with RecoveryFixture() as fixture:
            fixture.broker.write_bytes(b"current-target-broker\n")
            fixture.broker.chmod(0o755)
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()

    def test_preflight_rejects_execution_source_not_descended_from_predecessor(self) -> None:
        with RecoveryFixture(ancestor=False):
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()

    def test_preflight_rejects_mixed_durable_state_and_staging_residue(self) -> None:
        with RecoveryFixture() as fixture:
            fixture.registration.write_text("{}\n", encoding="utf-8")
            fixture.registration.chmod(0o600)
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()

        with RecoveryFixture() as fixture:
            residue = fixture.staging[2]
            residue.write_bytes(b"residue")
            residue.chmod(0o600)
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()

    def test_preflight_rejects_artifact_mode_and_owner_drift(self) -> None:
        with RecoveryFixture() as fixture:
            fixture.broker.chmod(0o775)
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()

        with RecoveryFixture():
            with mock.patch.object(
                recovery.base, "ROOT_UID", os.getuid() + 10000
            ):
                with self.assertRaises(recovery.RecoveryError):
                    recovery.preflight_material()

    def test_apply_requires_separate_root_authority_before_preflight(self) -> None:
        with mock.patch.object(recovery.os, "geteuid", lambda: 1000):
            with mock.patch.object(recovery, "preflight_material") as preflight:
                with self.assertRaises(recovery.RecoveryError):
                    recovery.apply()
                preflight.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
