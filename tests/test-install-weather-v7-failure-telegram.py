#!/usr/bin/env python3
"""Weather v7 notifier bounded installer contract, with simulated host only."""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/install-weather-v7-failure-telegram.py"
loader = SourceFileLoader("weather_v7_telegram_installer", str(PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
CONTRACT = json.loads((ROOT / "ops/deploy/weather-v7-failure-telegram-install-v1.json").read_text())


class InstallerTests(unittest.TestCase):
    def test_contract_is_single_unit_source_only_and_no_live(self):
        self.assertEqual(CONTRACT["issue"], 1087)
        self.assertEqual(CONTRACT["state"], "SOURCE_ONLY_NO_LIVE")
        self.assertTrue(CONTRACT["apply_requires_separate_live_authorization"])
        self.assertFalse(CONTRACT["source_merge_authorizes_live"])
        self.assertFalse(CONTRACT["credentials"]["values_inspected"])
        self.assertFalse(CONTRACT["credentials"]["values_written"])
        self.assertEqual(set(CONTRACT["installed_targets"]), {
            str(installer.NOTIFIER_TARGET), str(installer.NOTIFIER_UNIT_TARGET),
            str(installer.CALLER_TARGET),
        })
        self.assertNotIn('systemctl_reload("reset-failed")', PATH.read_text())
        self.assertNotIn("enable", PATH.read_text().split("def apply(")[1].split("def main(")[0])

    def test_original_caller_predecessor_is_only_onfailure_delta(self):
        current = (ROOT / installer.CALLER_SOURCE).read_bytes()
        old = current.replace(installer.ON_FAILURE, b"")
        self.assertEqual(current.count(installer.ON_FAILURE), 1)
        self.assertNotIn(b"OnFailure=", old)
        self.assertIn(b"LoadCredential=github-app.pem:", old)
        self.assertIn(b"Type=oneshot", old)

    def test_source_check_rejects_noncanonical_head_or_dirty(self):
        canonical = "a" * 40
        with patch.object(installer, "git", side_effect=lambda *xs: {
            ("rev-parse", "HEAD"): "b" * 40,
        }.get(xs, "")):
            with self.assertRaises(installer.InstallFailure):
                installer.source_check(canonical)
        with self.assertRaises(installer.InstallFailure):
            installer.source_check("x" * 40)

    def test_historical_failed_78_must_remain_unchanged(self):
        good = {
            "LoadState": "loaded", "UnitFileState": "static",
            "ActiveState": "failed", "SubState": "failed",
            "Result": "exit-code", "ExecMainCode": "1", "ExecMainStatus": "78",
            "ExecMainStartTimestamp": installer.HISTORIC_START,
            "ExecMainExitTimestamp": installer.HISTORIC_EXIT,
        }
        timer = {
            "LoadState": "loaded", "UnitFileState": "enabled",
            "ActiveState": "active", "SubState": "elapsed",
            "Result": "success", "NextElapseUSecMonotonic": "infinity",
        }
        with patch.object(installer, "systemctl_show", side_effect=[good, timer]):
            installer.historic_state()
        for key, value in (
            ("ActiveState", "active"), ("ExecMainStatus", "0"),
            ("ExecMainExitTimestamp", "Sun 2026-10-24 19:00:00 CEST"),
        ):
            changed = {**good, key: value}
            with self.subTest(key=key), patch.object(installer, "systemctl_show", return_value=changed):
                with self.assertRaises(installer.InstallFailure):
                    installer.historic_state()

    def test_preflight_does_not_write_or_reload(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            notifier = root / "notifier"
            notifier_unit = root / "notify.service"
            caller = root / "caller.service"
            stage = root / ".stage"
            timer = root / "caller.timer"
            binary = root / "caller"
            src = (ROOT / installer.CALLER_SOURCE).read_bytes()
            old = src.replace(installer.ON_FAILURE, b"")
            caller.write_bytes(old)
            timer.write_bytes((ROOT / installer.TIMER_SOURCE).read_bytes())
            binary.write_bytes((ROOT / installer.CALLER_BINARY_SOURCE).read_bytes())
            for path, mode in ((caller, 0o644), (timer, 0o644), (binary, 0o755)):
                path.chmod(mode)
            actual_cred = []
            with (
                patch.object(installer, "NOTIFIER_TARGET", notifier),
                patch.object(installer, "NOTIFIER_UNIT_TARGET", notifier_unit),
                patch.object(installer, "CALLER_TARGET", caller),
                patch.object(installer, "CALLER_STAGE", stage),
                patch.object(installer, "TIMER_TARGET", timer),
                patch.object(installer, "CALLER_BINARY_TARGET", binary),
                patch.object(installer, "source_check", return_value={"result": "SOURCE_PASS"}),
                patch.object(installer, "require_directory", return_value=None),
                patch.object(installer, "credentials_metadata", side_effect=lambda: actual_cred.append(1)),
                patch.object(installer, "checked_installed", return_value=None),
                patch.object(installer, "historic_state", return_value=None),
                patch.object(installer, "systemctl_reload", side_effect=AssertionError("reload must not run")),
            ):
                result = installer.host_preflight("a" * 40)
                self.assertEqual(result["result"], "HOST_PREFLIGHT_PASS")
                self.assertFalse(result["host_mutation_started"])
                self.assertEqual(actual_cred, [1])
                self.assertFalse(notifier.exists())
                self.assertFalse(notifier_unit.exists())
                self.assertEqual(caller.read_bytes(), old)

    def test_installer_refuses_target_drift_and_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "artifact"
            path.write_bytes(b"expected")
            path.chmod(0o644)
            with self.assertRaises(installer.InstallFailure):
                installer.checked_installed(path, b"unexpected", 0o644)
            path.unlink()
            path.symlink_to(Path(td) / "target")
            with self.assertRaises(installer.InstallFailure):
                installer.require_absent(path)

    def test_apply_requires_root_and_does_not_attempt_host(self):
        with patch.object(installer.os, "geteuid", return_value=1000):
            with patch.object(installer, "host_preflight", side_effect=AssertionError("host preflight should not run")):
                with self.assertRaises(installer.InstallFailure):
                    installer.apply("a" * 40)

    def test_mutation_failure_produces_stop_no_cleanup(self):
        with patch.object(installer.os, "geteuid", return_value=0):
            with patch.object(installer, "host_preflight", return_value={}):
                with patch.object(installer, "source_file", return_value=b"data"):
                    with patch.object(installer, "exclusive_write", side_effect=OSError("simulated failure")):
                        with patch.object(installer, "systemctl_reload", side_effect=AssertionError("must not reload")):
                            with self.assertRaisesRegex(installer.InstallFailure, "no retry, rollback, cleanup"):
                                installer.apply("a" * 40)

    def test_cli_source_check_only_by_default(self):
        with patch.object(installer, "source_check", return_value={"result": "SOURCE_PASS"}):
            with patch.object(installer, "host_preflight", side_effect=AssertionError("no host call")):
                with patch.object(installer, "apply", side_effect=AssertionError("no apply")):
                    import contextlib
                    import io
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(installer.main(["--expected-main-sha", "a"*40]), 0)


if __name__ == "__main__":
    unittest.main()
