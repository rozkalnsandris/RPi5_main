#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REFRESH = ROOT / "scripts/refresh-weather-operator-v10-successor-dispatch-caller.py"
CONTRACT = ROOT / "ops/deploy/weather-operator-v10-successor-dispatch-caller-refresh.json"
INSTALLED_SUCCESSOR_PREDECESSOR = "811884275d4859e185ea4b12c5dac8dd92d0f1c8"


def load_refresh():
    spec = importlib.util.spec_from_file_location("weather_v10_successor_refresh", REFRESH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeInstalledPath:
    def __init__(self, data: bytes, *, mode: int = 0o644, missing: bool = False):
        self.data = data
        self.mode = mode
        self.missing = missing

    def lstat(self):
        if self.missing:
            raise FileNotFoundError("absent")
        return SimpleNamespace(
            st_mode=stat.S_IFREG | self.mode,
            st_nlink=1,
            st_uid=0,
            st_gid=0,
        )

    def read_bytes(self) -> bytes:
        if self.missing:
            raise FileNotFoundError("absent")
        return self.data

    def __str__(self) -> str:
        return "/fixed/test-target"


class WeatherV10SuccessorRefreshTests(unittest.TestCase):
    def test_contract_is_update_only_and_predelete_forbidden(self) -> None:
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(value["schema"], "rozkalns.rpi5-main.weather-operator-v10-successor-dispatch-caller-refresh.v2")
        self.assertEqual(value["issue"], 658)
        self.assertEqual(value["installed_successor_predecessor_source_sha"], INSTALLED_SUCCESSOR_PREDECESSOR)
        self.assertEqual(value["desired_source_binding"], "current_exact_head")
        self.assertTrue(value["existing_successor_required"])
        self.assertFalse(value["target_predelete_allowed"])
        self.assertEqual(value["replacement_order"], ["successor_module", "dispatch_caller_entrypoint"])
        self.assertFalse(value["automatic_retry"])
        self.assertFalse(value["automatic_cleanup"])
        self.assertFalse(value["automatic_rollback"])
        self.assertFalse(value["systemd_mutation"])
        self.assertFalse(value["broker_mutation"])
        self.assertFalse(value["registration_mutation"])
        self.assertFalse(value["replay_state_db_mutation"])
        self.assertFalse(value["weather_runtime_mutation"])

    def test_fixed_file_requires_exact_reviewed_existing_artifact(self) -> None:
        refresh = load_refresh()
        refresh.fixed_file(FakeInstalledPath(b"reviewed"), mode=0o644, expected=b"reviewed")
        with self.assertRaises(refresh.CallerRefreshError):
            refresh.fixed_file(FakeInstalledPath(b"drifted"), mode=0o644, expected=b"reviewed")
        with self.assertRaises(refresh.CallerRefreshError):
            refresh.fixed_file(FakeInstalledPath(b"", missing=True), mode=0o644, expected=b"reviewed")

    def test_preflight_checks_installed_successor_predecessor(self) -> None:
        script = REFRESH.read_text(encoding="utf-8")
        self.assertIn("fixed_file(SUCCESSOR_MODULE_TARGET, mode=0o644, expected=predecessor_successor)", script)
        self.assertNotIn("successor caller module target already exists", script)
        self.assertIn("INSTALLED_SUCCESSOR_PREDECESSOR_SOURCE_SHA", script)
        self.assertIn("os.O_EXCL", script)
        for forbidden in ("os.unlink(", "os.remove(", ".unlink(", "shutil.rmtree", "shell=True", "systemctl"):
            self.assertNotIn(forbidden, script)

    def test_apply_stages_then_atomically_replaces_in_fixed_order(self) -> None:
        refresh = load_refresh()
        events: list[tuple[str, str]] = []
        evidence = {
            "source_sha": "f" * 40,
            "installed_predecessor_successor_module_sha256": "a" * 64,
            "installed_predecessor_entrypoint_sha256": "b" * 64,
            "desired_successor_module_sha256": "c" * 64,
            "desired_dispatch_caller_entrypoint_sha256": "d" * 64,
        }

        def fake_blob(commit: str, path: str) -> bytes:
            return b"new-successor" if path == refresh.SUCCESSOR_MODULE_SOURCE else b"new-entrypoint"

        def fake_stage(path, data, mode):
            events.append(("stage", str(path)))

        def fake_replace(src, dst):
            events.append(("replace", str(dst)))

        def fake_require(path, *, mode, expected):
            events.append(("verify", str(path)))

        with mock.patch.object(refresh.os, "geteuid", return_value=0), \
             mock.patch.object(refresh, "preflight", return_value=evidence), \
             mock.patch.object(refresh, "git_blob", side_effect=fake_blob), \
             mock.patch.object(refresh, "stage", side_effect=fake_stage), \
             mock.patch.object(refresh.os, "replace", side_effect=fake_replace), \
             mock.patch.object(refresh, "require_target", side_effect=fake_require):
            result = refresh.apply()

        self.assertEqual(events, [
            ("stage", str(refresh.SUCCESSOR_TEMP)),
            ("stage", str(refresh.ENTRYPOINT_TEMP)),
            ("replace", str(refresh.SUCCESSOR_MODULE_TARGET)),
            ("verify", str(refresh.SUCCESSOR_MODULE_TARGET)),
            ("replace", str(refresh.ENTRYPOINT_TARGET)),
            ("verify", str(refresh.ENTRYPOINT_TARGET)),
        ])
        self.assertEqual(result["result"], "PASS")
        self.assertFalse(result["target_predelete_allowed"])
        self.assertFalse(result["automatic_retry"])
        self.assertFalse(result["automatic_cleanup"])
        self.assertFalse(result["automatic_rollback"])


if __name__ == "__main__":
    unittest.main()
