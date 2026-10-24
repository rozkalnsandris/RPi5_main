#!/usr/bin/env python3
"""Offline/synthetic tests: Weather v7 credential source does not access host."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load("weather_v7_credentials", ROOT / "scripts/weather-v7-telegram-credentials-helper.py")
installer = load("weather_v7_credentials_installer", ROOT / "scripts/install-weather-v7-telegram-credentials-helper.py")


def synthetic_values():
    # No literal credential-like values in public source or logs.
    return "123456" + ":" + "A" * 30, "-100" + "1234567890"


class CredentialsSourceTests(unittest.TestCase):
    def test_scope_and_no_network_or_argv_secrets(self):
        source = (ROOT / "scripts/weather-v7-telegram-credentials-helper.py").read_text()
        self.assertEqual(len(helper.TARGETS), 2)
        self.assertEqual(installer.TARGET.name, "rpi5-weather-v7-telegram-credentials")
        for unwanted in ("requests", "urllib", "socket.", "subprocess", "os.environ",
                         "os.getenv", "getpass"):
            self.assertNotIn(unwanted, source)
        self.assertIn("os.O_NOFOLLOW", source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("termios.ECHO", source)
        self.assertIn('os.open("/dev/tty"', source)

    def test_both_values_validated_before_mutation(self):
        token, chat = synthetic_values()
        helper.validate_values(token, chat)
        for t, c in (("bad", chat), (token, "not-numeric"), (token, "0"),
                     (token + "!" , chat), (token, "-" + "9" * 20)):
            with self.subTest(t=t == token, c=c == chat):
                with self.assertRaises(helper.Stop):
                    helper.validate_values(t, c)

    def test_trusted_entry_rejects_repo_root_execution(self):
        with mock.patch.object(helper.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(helper.Stop, "installed_root_entry_required"):
                helper.trusted_entry()

    def test_no_controlling_tty_no_stdin_fallback(self):
        with mock.patch.object(helper.os, "open", side_effect=OSError):
            with self.assertRaisesRegex(helper.Stop, "controlling_tty_required"):
                helper.values_from_owner_tty()

    def test_existing_credential_target_fails_closed(self):
        with mock.patch.object(helper.os, "stat", return_value=SimpleNamespace()):
            with self.assertRaisesRegex(helper.Stop, "credential_target_exists"):
                helper.targets_absent(9)
        with mock.patch.object(helper.os, "stat", side_effect=FileNotFoundError):
            helper.targets_absent(9)
        with mock.patch.object(helper.os, "stat", side_effect=PermissionError):
            with self.assertRaisesRegex(helper.Stop, "credential_target_state_unknown"):
                helper.targets_absent(9)

    def test_faked_private_credential_file_creation_is_exclusive(self):
        token, _ = synthetic_values()
        with tempfile.TemporaryDirectory() as tmp:
            directory_fd = helper.os.open(tmp, helper.os.O_DIRECTORY | helper.os.O_RDONLY)
            try:
                # No root host access: private temporary test directory only.
                fake_root = SimpleNamespace(
                    st_mode=0o100600, st_uid=0, st_gid=0, st_nlink=1,
                    st_size=len(token.encode()) + 1,
                )
                with mock.patch.object(helper.os, "fstat", return_value=fake_root):
                    helper.exclusive_credential(directory_fd, "test-credential", token)
                path = Path(tmp) / "test-credential"
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.read_bytes(), token.encode() + b"\n")
                with self.assertRaisesRegex(helper.Stop, "post_mutation_unknown"):
                    helper.exclusive_credential(directory_fd, "test-credential", token)
                self.assertEqual(path.read_bytes(), token.encode() + b"\n")
            finally:
                helper.os.close(directory_fd)

    def test_no_confirmation_never_runs(self):
        with mock.patch.object(helper, "run", side_effect=AssertionError("must not run")):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(helper.main(["--confirm", "wrong"]), 3)

    def test_read_only_check_path_requires_installed_entry(self):
        with mock.patch.object(helper, "run", return_value={"result": "PREFLIGHT_PASS"}) as call:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(helper.main(["--check"]), 0)
            call.assert_called_once_with(check_only=True)

    def test_installer_default_is_only_offline_source_check(self):
        with mock.patch.object(installer, "source_check", return_value={"result":"SOURCE_PASS"}) as sc:
            with mock.patch.object(installer, "preflight", side_effect=AssertionError("host")):
                with mock.patch.object(installer, "apply", side_effect=AssertionError("mutation")):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(installer.main(["--expected-main-sha","a"*40]), 0)
            sc.assert_called_once_with("a"*40)

    def test_installer_apply_refuses_unprivileged(self):
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            with mock.patch.object(installer, "preflight", side_effect=AssertionError("must not host inspect")):
                with self.assertRaisesRegex(installer.Stop, "root_required"):
                    installer.apply("a"*40)

    def test_installer_no_credentials_and_contract(self):
        source=(ROOT / "scripts/install-weather-v7-telegram-credentials-helper.py").read_text()
        self.assertIn("os.O_CREAT | os.O_EXCL", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("reset-failed", source)
        self.assertNotIn("telegram_send", source)
        self.assertNotIn("/etc/credstore", source)
        import json
        data=json.loads((ROOT/"ops/contracts/weather-v7-telegram-credentials-v1.json").read_text())
        self.assertFalse(data["source_merge_authorizes_live"])
        self.assertTrue(data["credential_provision_requires_separate_explicit_live_authorization"])
        self.assertTrue(data["helper_install_requires_separate_explicit_live_authorization"])


if __name__=="__main__":
    unittest.main()
