#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-weather-operator-v7-host-capability.py"

spec = importlib.util.spec_from_file_location("weather_v7_installer", INSTALLER)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}


class WeatherV7SudoGitTrustTests(unittest.TestCase):
    def test_root_propagates_only_validated_sudo_uid(self) -> None:
        with mock.patch.object(installer.os, "geteuid", return_value=0):
            with mock.patch.dict(
                installer.os.environ,
                {"SUDO_UID": "1000", "HOME": "/tmp/ignored", "GIT_CONFIG_GLOBAL": "/tmp/ignored"},
                clear=True,
            ):
                self.assertEqual(installer.git_environment(), {**BASE_ENV, "SUDO_UID": "1000"})

    def test_root_without_sudo_uid_keeps_minimal_environment(self) -> None:
        with mock.patch.object(installer.os, "geteuid", return_value=0):
            with mock.patch.dict(installer.os.environ, {}, clear=True):
                self.assertEqual(installer.git_environment(), BASE_ENV)

    def test_non_root_never_propagates_sudo_uid(self) -> None:
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            with mock.patch.dict(installer.os.environ, {"SUDO_UID": "1000"}, clear=True):
                self.assertEqual(installer.git_environment(), BASE_ENV)

    def test_malformed_or_reserved_sudo_uid_fails_closed(self) -> None:
        for value in ("", "-1", "abc", "１２３", str((1 << 32) - 1)):
            with self.subTest(value=value):
                with mock.patch.object(installer.os, "geteuid", return_value=0):
                    with mock.patch.dict(installer.os.environ, {"SUDO_UID": value}, clear=True):
                        with self.assertRaises(installer.InstallError):
                            installer.git_environment()

    def test_no_safe_directory_or_git_config_bypass(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn("safe.directory", source)
        self.assertNotIn("GIT_CONFIG_GLOBAL", source)
        self.assertNotIn("GIT_CONFIG_SYSTEM", source)
        self.assertIn("env=git_environment()", source)


if __name__ == "__main__":
    unittest.main()
