#!/usr/bin/env python3
"""Synthetic, network-free Weather v7 Telegram failure notification tests."""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/rozkalns-weather-v7-failure-telegram"
loader = SourceFileLoader("weather_v7_failure_telegram", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec and spec.loader
alert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alert)

SAMPLE = (
    "ActiveState=failed\nResult=exit-code\nExecMainCode=1\nExecMainStatus=78\n"
    "StateChangeTimestampMonotonic=12345678\n"
    "ExecMainExitTimestamp=Wed 2026-09-30 21:55:22 CEST\n"
)
BOOT = "123e4567-e89b-42d3-a456-426614174000"


class FailureTelegramTests(unittest.TestCase):
    def event(self, metadata=SAMPLE):
        return alert.failure_event(metadata, BOOT)

    @staticmethod
    def credentials(path):
        path.joinpath("telegram-token").write_text("123456:ABCDEFghijklmnopqrstuvwxyz0123456789")
        path.joinpath("telegram-chat-id").write_text("-1001234567890")

    def test_rejects_success_stale_or_unknown_unit_metadata(self):
        for change in (
            ("ActiveState=failed", "ActiveState=active"),
            ("Result=exit-code", "Result=success"),
            ("StateChangeTimestampMonotonic=12345678", "StateChangeTimestampMonotonic=0"),
            ("ExecMainStatus=78", "ExecMainStatus=78\nExtraUnit=other"),
            ("ExecMainCode=1", "ExecMainCode=hello"),
        ):
            with self.subTest(change=change), self.assertRaises(alert.AlertError):
                self.event(SAMPLE.replace(*change))

    def test_same_failure_is_sent_at_most_once(self):
        with tempfile.TemporaryDirectory() as root:
            state, creds = Path(root) / "state", Path(root) / "creds"
            state.mkdir(mode=0o700)
            creds.mkdir(mode=0o700)
            self.credentials(creds)
            sent = []
            def sender(token, chat, msg):
                self.assertIn("Weather v7", msg)
                self.assertIn("status=78", msg)
                sent.append((token, chat))
                return True
            event = self.event()
            self.assertEqual(alert.notify_once(event, state, creds, sender), "API_ACCEPTED")
            self.assertEqual(alert.notify_once(event, state, creds, sender), "ALREADY_ATTEMPTED")
            self.assertEqual(len(sent), 1)
            receipt = list(state.iterdir())
            self.assertEqual(len(receipt), 1)
            self.assertEqual(receipt[0].read_bytes(), b"ATTEMPTED\nTELEGRAM_API_ACCEPTED\n")

    def test_failed_attempt_is_not_retried_and_new_failure_is_allowed(self):
        with tempfile.TemporaryDirectory() as root:
            state, creds = Path(root) / "state", Path(root) / "creds"
            state.mkdir(mode=0o700)
            creds.mkdir(mode=0o700)
            self.credentials(creds)
            calls = []
            def failing(*args):
                calls.append(1)
                raise ConnectionError("URL must never be logged")
            with self.assertRaises(ConnectionError):
                alert.notify_once(self.event(), state, creds, failing)
            self.assertEqual(alert.notify_once(self.event(), state, creds, failing), "ALREADY_ATTEMPTED")
            changed = self.event(SAMPLE.replace("ExecMainStatus=78", "ExecMainStatus=79")
                                 .replace("12345678", "12345679"))
            self.assertEqual(alert.notify_once(changed, state, creds, lambda *_: True), "API_ACCEPTED")
            self.assertEqual(calls, [1])

    def test_missing_credentials_fail_without_network_or_ledger(self):
        with tempfile.TemporaryDirectory() as root:
            state, creds = Path(root) / "state", Path(root) / "creds"
            state.mkdir(mode=0o700)
            creds.mkdir(mode=0o700)
            with self.assertRaises((FileNotFoundError, alert.AlertError)):
                alert.notify_once(self.event(), state, creds, lambda *_: self.fail("network"))
            self.assertFalse(list(state.iterdir()))

    def test_symlink_credential_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            state, creds = Path(root) / "state", Path(root) / "creds"
            state.mkdir(mode=0o700)
            creds.mkdir(mode=0o700)
            self.credentials(creds)
            creds.joinpath("telegram-token").unlink()
            creds.joinpath("telegram-token").symlink_to(creds / "telegram-chat-id")
            with self.assertRaises(OSError):
                alert.notify_once(self.event(), state, creds)

    def test_exact_unit_only_and_source_only_activation(self):
        original = (ROOT / "ops/systemd/rozkalns-weather-operator-v7-dispatch-caller.service").read_text()
        notify_unit = (ROOT / "ops/systemd/rozkalns-weather-v7-failure-telegram.service").read_text()
        timer = (ROOT / "ops/systemd/rozkalns-weather-operator-v7-dispatch-caller.timer").read_text()
        self.assertIn("OnFailure=rozkalns-weather-v7-failure-telegram.service", original)
        self.assertEqual(original.count("OnFailure="), 1)
        self.assertIn("DynamicUser=yes", notify_unit)
        self.assertIn("LoadCredential=telegram-token:", notify_unit)
        self.assertIn("LoadCredential=telegram-chat-id:", notify_unit)
        self.assertIn("ExecStart=/usr/local/libexec/rozkalns-weather-v7-failure-telegram", notify_unit)
        self.assertNotIn("Restart=", notify_unit)
        self.assertNotIn("OnFailure=", notify_unit)
        self.assertIn("OnBootSec=2min", timer)
        self.assertNotIn("OnUnitInactiveSec", timer)
        self.assertNotIn("OnCalendar=", timer)
        self.assertNotIn("subprocess.Popen", SCRIPT.read_text())
        self.assertNotIn("shell=True", SCRIPT.read_text())

    def test_transport_failure_is_sanitized(self):
        with patch.object(alert, "read_current_failure", side_effect=RuntimeError("secret_value")):
            with patch.dict(alert.os.environ, {"STATE_DIRECTORY": "/tmp/not-used",
                                                "CREDENTIALS_DIRECTORY": "/tmp/not-used"}):
                import contextlib
                import io
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(alert.main(), 1)
                self.assertNotIn("secret_value", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
