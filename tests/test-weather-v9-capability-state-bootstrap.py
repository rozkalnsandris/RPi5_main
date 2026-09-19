#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "ops/recovery/weather_v9_capability_state_bootstrap.py"
CONTRACT = ROOT / "ops/recovery/weather_v9_capability_state_bootstrap.contract.json"
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor.state import StateStore


def load_recovery():
    spec = importlib.util.spec_from_file_location("weather_v9_state_bootstrap", RECOVERY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


recovery = load_recovery()


class Fixture:
    def __init__(self, *, state_root_present: bool = True):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.support = self.root / "usr/local/libexec/rozkalns-weather-operator-v9-capability"
        self.package = self.support / "deploy_executor"
        self.libexec = self.root / "usr/local/libexec"
        self.broker = self.libexec / "rozkalns-weather-operator-v9-privileged-broker"
        self.config = self.root / "etc/rozkalns-weather-operator-v9-capability"
        self.registration = self.config / "registration.json"
        self.state_root = self.root / "var/lib/rozkalns-weather-operator-v9-capability"
        self.state_root.parent.mkdir(parents=True, exist_ok=True)
        self.state_db = self.state_root / "state.sqlite3"
        self.systemd = self.root / "etc/systemd/system"
        self.socket = self.systemd / recovery.SOCKET_NAME
        self.service = self.systemd / recovery.SERVICE_NAME
        self.module = self.package / "weather_operator_upgrade_v9_host_capability.py"
        self.manager = self.root / "home/operator/RPi5_main"

        self.package.mkdir(parents=True)
        self.config.mkdir(parents=True)
        self.systemd.mkdir(parents=True)
        self.manager.mkdir(parents=True)
        if state_root_present:
            self.state_root.mkdir(parents=True)

        self.support.chmod(0o755)
        self.package.chmod(0o755)
        self.config.chmod(0o700)
        self.systemd.chmod(0o755)
        if state_root_present:
            self.state_root.chmod(0o700)

        package_names = [
            "__init__.py",
            "dispatch_contract.py",
            "github_app_auth.py",
            "p9_canary.py",
            "p9_isolated_auth_surface.py",
            "p9_runtime.py",
            "protocol.py",
            "queue_normalizer.py",
            "registry.py",
            "state.py",
            "transport.py",
            "weather_operator_upgrade_v9_host_capability.py",
        ]
        self.artifacts: list[tuple[str, Path, int]] = []
        self.expected: dict[str, bytes] = {}
        for index, name in enumerate(package_names):
            path = self.package / name
            source = f"ops/lib/deploy_executor/{name}"
            data = f"artifact-{index}-{name}\n".encode()
            self._write(path, data, 0o644)
            self.artifacts.append((source, path, 0o644))
            self.expected[source] = data

        broker_source = "ops/bin/rozkalns-weather-operator-v9-privileged-broker"
        socket_source = "ops/systemd/rozkalns-weather-operator-v9-privileged-broker.socket"
        service_source = "ops/systemd/rozkalns-weather-operator-v9-privileged-broker@.service"
        self._write(self.broker, b"broker\n", 0o755)
        self._write(self.socket, b"socket\n", 0o644)
        self._write(self.service, b"service-rendered\n", 0o644)
        self.artifacts.extend(
            (
                (broker_source, self.broker, 0o755),
                (socket_source, self.socket, 0o644),
                (service_source, self.service, 0o644),
            )
        )
        self.expected[broker_source] = b"broker\n"
        self.expected[socket_source] = b"socket\n"
        self.expected[service_source] = b"service-rendered\n"
        assert len(self.artifacts) == 15

        self.installer = types.SimpleNamespace(
            REGISTRATION_SCHEMA=recovery.REGISTRATION_SCHEMA,
            TARGET_ROOT=self.support,
            PACKAGE_ROOT=self.package,
            BROKER_TARGET=self.broker,
            CONFIG_ROOT=self.config,
            REGISTRATION=self.registration,
            STATE_ROOT=self.state_root,
            STATE_DB=self.state_db,
            SYSTEMD_ROOT=self.systemd,
            SOCKET_NAME=recovery.SOCKET_NAME,
            SERVICE_NAME=recovery.SERVICE_NAME,
            ARTIFACTS=tuple(self.artifacts),
            source_sha=lambda: "a" * 40,
            canonical_manager_checkout=lambda: self.manager,
            manager_identity=lambda _manager: (1000, 1000),
            installed_bytes=lambda source, _manager: self.expected[source],
        )

        self.registration_temp = self.config / ".registration.json.state-bootstrap.tmp"
        self.staging = (
            self.libexec / ".rozkalns-weather-operator-v9-privileged-broker.refresh.tmp",
            self.config / ".registration.json.refresh.tmp",
            self.libexec / ".rozkalns-weather-operator-v9-privileged-broker.broker-refresh.tmp",
            self.config / ".registration.json.broker-refresh.tmp",
            self.package / ".weather_operator_upgrade_v9_host_capability.py.module-refresh.tmp",
            self.config / ".registration.json.module-refresh.tmp",
            self.registration_temp,
            self.state_root / "state.sqlite3-wal",
            self.state_root / "state.sqlite3-shm",
        )

    def _write(self, path: Path, data: bytes, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)

    def patches(self):
        return (
            mock.patch.object(recovery, "SUPPORT_ROOT", self.support),
            mock.patch.object(recovery, "PACKAGE_ROOT", self.package),
            mock.patch.object(recovery, "BROKER_PATH", self.broker),
            mock.patch.object(recovery, "CONFIG_ROOT", self.config),
            mock.patch.object(recovery, "REGISTRATION_PATH", self.registration),
            mock.patch.object(recovery, "STATE_ROOT", self.state_root),
            mock.patch.object(recovery, "STATE_DB_PATH", self.state_db),
            mock.patch.object(recovery, "SYSTEMD_ROOT", self.systemd),
            mock.patch.object(recovery, "SOCKET_UNIT_PATH", self.socket),
            mock.patch.object(recovery, "SERVICE_UNIT_PATH", self.service),
            mock.patch.object(recovery, "MODULE_PATH", self.module),
            mock.patch.object(recovery, "REGISTRATION_TEMP", self.registration_temp),
            mock.patch.object(recovery, "KNOWN_STAGING_PATHS", self.staging),
            mock.patch.object(recovery, "ROOT_UID", os.getuid()),
            mock.patch.object(recovery, "ROOT_GID", os.getgid()),
            mock.patch.object(recovery, "_load_installer", lambda: self.installer),
            mock.patch.object(recovery, "_validate_contract", lambda _installer: None),
        )

    def __enter__(self):
        self.stack = []
        for patcher in self.patches():
            self.stack.append(patcher)
            patcher.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        for patcher in reversed(self.stack):
            patcher.stop()
        self.tmp.cleanup()


class WeatherV9CapabilityStateBootstrapTests(unittest.TestCase):
    def test_contract_binds_canonical_identity_and_fail_closed_policy(self) -> None:
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["schema"],
            "rozkalns.rpi5-main.weather-operator-v9-capability-state-bootstrap.v1",
        )
        self.assertEqual(payload["issue"], 623)
        self.assertEqual(
            payload["accepted_baseline"],
            {"registration": "ABSENT", "state_db": "ABSENT"},
        )
        self.assertEqual(payload["artifact_count"], 15)
        self.assertEqual(payload["registration_schema"], recovery.REGISTRATION_SCHEMA)
        self.assertTrue(payload["registration_published_last"])
        self.assertFalse(payload["systemd_mutation"])
        self.assertFalse(payload["automatic_retry"])
        self.assertFalse(payload["automatic_cleanup"])
        self.assertFalse(payload["automatic_rollback"])
        self.assertFalse(payload["source_merge_authorizes_live"])
        self.assertIn(
            "/usr/local/libexec/rozkalns-weather-operator-v9-privileged-broker",
            payload["fixed_targets"].values(),
        )
        self.assertIn(
            "/etc/systemd/system/rozkalns-weather-operator-v9-privileged-broker@.service",
            payload["fixed_targets"].values(),
        )

    def test_source_has_no_new_privilege_or_systemd_command_path(self) -> None:
        source = RECOVERY.read_text(encoding="utf-8")
        self.assertNotIn("systemctl", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("/usr/bin/sudo", source)
        self.assertLess(source.index("StateStore(STATE_DB_PATH, bootstrap=True)"), source.index("os.replace(REGISTRATION_TEMP"))

    def test_happy_path_bootstraps_canonical_state_and_registration_last(self) -> None:
        with Fixture(state_root_present=False) as fixture:
            before = {path: path.read_bytes() for _source, path, _mode in fixture.artifacts}
            with (
                mock.patch.object(recovery.os, "geteuid", lambda: 0),
                mock.patch.object(recovery, "_load_state_store", lambda: StateStore),
            ):
                receipt = recovery.apply()

            self.assertEqual(receipt["result"], "PASS")
            self.assertTrue(receipt["state_db_bootstrapped"])
            self.assertTrue(receipt["registration_published"])
            self.assertTrue(fixture.state_db.is_file())
            self.assertEqual(stat.S_IMODE(fixture.state_db.stat().st_mode), 0o600)
            with StateStore(fixture.state_db):
                pass

            registration = json.loads(fixture.registration.read_text(encoding="utf-8"))
            self.assertEqual(frozenset(registration), recovery.REGISTRATION_FIELDS)
            self.assertEqual(registration["schema"], recovery.REGISTRATION_SCHEMA)
            self.assertEqual(registration["capability_source_sha"], "a" * 40)
            self.assertEqual(registration["manager_checkout"], str(fixture.manager))
            self.assertEqual(registration["manager_uid"], 1000)
            self.assertEqual(registration["manager_gid"], 1000)
            self.assertEqual(registration["artifact_count"], 15)
            self.assertEqual(stat.S_IMODE(fixture.registration.stat().st_mode), 0o600)
            self.assertFalse(fixture.registration_temp.exists())

            after = {path: path.read_bytes() for _source, path, _mode in fixture.artifacts}
            self.assertEqual(after, before)

    def test_preflight_rejects_mixed_or_complete_durable_state(self) -> None:
        for registration_present, db_present in ((True, False), (False, True), (True, True)):
            with self.subTest(registration=registration_present, db=db_present):
                with Fixture() as fixture:
                    if registration_present:
                        fixture.registration.write_text("{}\n", encoding="utf-8")
                        fixture.registration.chmod(0o600)
                    if db_present:
                        fixture.state_db.write_bytes(b"existing")
                        fixture.state_db.chmod(0o600)
                    with self.assertRaises(recovery.RecoveryError):
                        recovery.preflight_material()

    def test_preflight_rejects_known_staging_residue(self) -> None:
        with Fixture() as fixture:
            residue = fixture.staging[2]
            residue.write_bytes(b"residue")
            residue.chmod(0o600)
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()

    def test_preflight_rejects_artifact_byte_drift(self) -> None:
        with Fixture() as fixture:
            fixture.module.write_bytes(b"drifted\n")
            fixture.module.chmod(0o644)
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()

    def test_preflight_rejects_symlink_and_mode_drift(self) -> None:
        with Fixture() as fixture:
            original = fixture.socket
            target = fixture.root / "socket-target"
            target.write_bytes(b"socket\n")
            target.chmod(0o644)
            original.unlink()
            original.symlink_to(target)
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()

        with Fixture() as fixture:
            fixture.broker.chmod(0o775)
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()

    def test_preflight_rejects_owner_drift(self) -> None:
        with Fixture() as fixture:
            with mock.patch.object(recovery, "ROOT_UID", os.getuid() + 10000):
                with self.assertRaises(recovery.RecoveryError):
                    recovery.preflight_material()

    def test_apply_requires_separate_root_authority_before_preflight(self) -> None:
        with mock.patch.object(recovery.os, "geteuid", lambda: 1000):
            with mock.patch.object(recovery, "preflight_material") as preflight:
                with self.assertRaises(recovery.RecoveryError):
                    recovery.apply()
                preflight.assert_not_called()

    def test_state_root_may_only_be_absent_or_exact_root_0700(self) -> None:
        with Fixture() as fixture:
            fixture.state_root.chmod(0o755)
            with self.assertRaises(recovery.RecoveryError):
                recovery.preflight_material()


if __name__ == "__main__":
    unittest.main(verbosity=2)
