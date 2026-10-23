#!/usr/bin/env python3
"""Offline fake-IO tests for the report Wrangler secrets provisioner."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import stat
import unittest
from types import SimpleNamespace
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "scripts/ausmalwiese_report_secrets_provisioner.py"
spec = importlib.util.spec_from_file_location("report_secrets", SOURCE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

VALID = {
    "TURNSTILE_SITE_KEY": "0x4AAAAAAAsynthetic-site-key",
    "TURNSTILE_SECRET": "0x4AAAAAAAsynthetic-secret",
    "BREVO_API_KEY": "synthetic-brevo-api-key-value-not-real",
    "REPORT_TO": "operator" + "@" + "example.test",
}


def fake_stat(mode=0o600, uid=0, gid=0, links=1, size=20, ino=7, dev=8):
    kind = stat.S_IFDIR if mode == 0o700 else stat.S_IFREG
    return SimpleNamespace(
        st_mode=kind | mode, st_uid=uid, st_gid=gid, st_nlink=links,
        st_size=size, st_ino=ino, st_dev=dev,
    )


class ReportSecretsProvisionerTests(unittest.TestCase):
    def test_fixed_contract_and_no_transport(self):
        source = SOURCE.read_text()
        self.assertEqual(str(mod.ENTRY), "/usr/local/sbin/rpi5-ausmalwiese-report-secrets-provision")
        self.assertEqual(str(mod.TARGET), "/etc/rpi5-secrets/cloudflare/ausmalwiese-report-wrangler-secrets.json")
        self.assertEqual(mod.WORKER, "coloring-pages-report-v1")
        self.assertEqual(tuple(mod.SECRET_NAMES), tuple(VALID))
        self.assertIn('os.open("/dev/tty"', source)
        self.assertIn("os.O_CREAT | os.O_EXCL", source)
        self.assertIn("os.O_NOFOLLOW", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("http.client", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("getpass", source)

    def test_payload_has_exact_four_names(self):
        payload = mod.secrets_bytes(dict(VALID))
        parsed = json.loads(payload)
        self.assertEqual(set(parsed), set(VALID))
        self.assertEqual(parsed, VALID)
        self.assertNotIn(b"worker", payload.lower())

    def test_invalid_values_fail_closed(self):
        cases = [
            ("TURNSTILE_SITE_KEY", "short", "turnstile_site_key_invalid"),
            ("TURNSTILE_SECRET", "bad value with spaces", "turnstile_secret_invalid"),
            ("BREVO_API_KEY", "too-short", "brevo_api_key_invalid"),
            ("REPORT_TO", "not-an-email", "report_to_invalid"),
        ]
        for key, value, reason in cases:
            with self.subTest(key=key):
                changed = dict(VALID)
                changed[key] = value
                with self.assertRaisesRegex(mod.Stop, reason):
                    mod.validate_values(changed)

    def test_field_order_and_extra_field_rejected(self):
        reversed_values = dict(reversed(list(VALID.items())))
        with self.assertRaisesRegex(mod.Stop, "secret_fields_invalid"):
            mod.validate_values(reversed_values)
        extra = dict(VALID, EXTRA="x")
        with self.assertRaisesRegex(mod.Stop, "secret_fields_invalid"):
            mod.validate_values(extra)

    def test_trusted_entry_rejects_repo_execution(self):
        with mock.patch.object(mod.os, "geteuid", return_value=0),              mock.patch.object(mod, "safe_parents") as parents:
            with self.assertRaisesRegex(mod.Stop, "installed_root_entry_required"):
                mod.trusted_entry()
            parents.assert_not_called()

    def test_existing_target_and_unknown_state_rejected(self):
        with mock.patch.object(mod.os, "stat", return_value=fake_stat()):
            with self.assertRaisesRegex(mod.Stop, "secrets_file_already_exists"):
                mod.absent(10)
        with mock.patch.object(mod.os, "stat", side_effect=FileNotFoundError):
            mod.absent(10)
        with mock.patch.object(mod.os, "stat", side_effect=PermissionError):
            with self.assertRaisesRegex(mod.Stop, "target_state_unknown"):
                mod.absent(10)

    def test_controlling_tty_missing_never_falls_back(self):
        with mock.patch.object(mod.os, "open", side_effect=OSError),              mock.patch.object(mod, "read_private") as reader:
            with self.assertRaisesRegex(mod.Stop, "controlling_tty_required"):
                mod.owner_tty_values()
            reader.assert_not_called()

    def test_background_tty_rejected(self):
        with mock.patch.object(mod.os, "open", return_value=50),              mock.patch.object(mod.os, "isatty", return_value=True),              mock.patch.object(mod.os, "tcgetpgrp", return_value=2),              mock.patch.object(mod.os, "getpgrp", return_value=3),              mock.patch.object(mod.os, "close"):
            with self.assertRaisesRegex(mod.Stop, "controlling_tty_required"):
                mod.owner_tty_values()

    def test_echo_restored_on_invalid_input(self):
        original = [0, 0, 0, mod.termios.ECHO | mod.termios.ECHONL | mod.termios.ECHOE, 0, 0, []]
        with mock.patch.object(mod.termios, "tcgetattr", return_value=original),              mock.patch.object(mod.termios, "tcsetattr") as setter,              mock.patch.object(mod.os, "write", return_value=4),              mock.patch.object(mod.os, "read", side_effect=[b"\xff", b"\n"]):
            with self.assertRaisesRegex(mod.Stop, "private_input_invalid"):
                mod.read_private(22, b"test", 32)
            self.assertEqual(setter.call_count, 2)
            self.assertEqual(setter.call_args.args[2], original)

    def test_exclusive_create_is_one_shot_0600(self):
        with mock.patch.object(mod.os, "umask", return_value=0o022),              mock.patch.object(mod.os, "open", return_value=83) as opener,              mock.patch.object(mod.os, "write", return_value=3) as writer,              mock.patch.object(mod.os, "close") as closer:
            with self.assertRaisesRegex(mod.Stop, "post_dispatch_unknown_state"):
                mod.exclusive_create(77, b"synthetic")
            self.assertEqual(opener.call_count, 1)
            args, kwargs = opener.call_args
            self.assertEqual(args[0], mod.TARGET.name)
            self.assertTrue(args[1] & mod.os.O_EXCL)
            self.assertTrue(args[1] & mod.os.O_NOFOLLOW)
            self.assertEqual(args[2], 0o600)
            self.assertEqual(kwargs["dir_fd"], 77)
            self.assertEqual(writer.call_count, 1)
            closer.assert_called_once_with(83)

    def test_preflight_failure_blocks_prompt_and_write(self):
        with mock.patch.object(mod, "trusted_entry", side_effect=mod.Stop("installed_root_entry_required")),              mock.patch.object(mod, "owner_tty_values") as tty,              mock.patch.object(mod, "exclusive_create") as create:
            with self.assertRaisesRegex(mod.Stop, "installed_root_entry_required"):
                mod.run()
            tty.assert_not_called()
            create.assert_not_called()

    def test_directory_drift_blocks_write(self):
        with mock.patch.object(mod, "trusted_entry"),              mock.patch.object(mod, "guarded_directory", return_value=(79, (3, 4))),              mock.patch.object(mod, "owner_tty_values", return_value=dict(VALID)),              mock.patch.object(mod, "safe_parents"),              mock.patch.object(mod, "safe_metadata", return_value=fake_stat(0o700, dev=3, ino=5)),              mock.patch.object(mod, "exclusive_create") as create,              mock.patch.object(mod.os, "close"):
            with self.assertRaisesRegex(mod.Stop, "parent_drift"):
                mod.run()
            create.assert_not_called()

    def test_confirmation_gate_and_secret_free_errors(self):
        with mock.patch.object(mod, "run") as run,              mock.patch("sys.stderr", new_callable=io.StringIO):
            code = mod.main(["--confirm", "bad"])
            self.assertEqual(code, 3)
            run.assert_not_called()
        with mock.patch.object(mod, "run", side_effect=OSError("synthetic-secret-should-not-print")),              mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            code = mod.main(["--confirm", mod.CONFIRM])
            self.assertEqual(code, 4)
            self.assertIn("STOP:", err.getvalue())
            self.assertNotIn("synthetic-secret", err.getvalue())


if __name__ == "__main__":
    unittest.main()
