#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/reconcile-simple-deploy-weather-data-v1.py"
spec = importlib.util.spec_from_file_location("weather_data_reconciler", PATH)
assert spec and spec.loader
reconciler = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reconciler
spec.loader.exec_module(reconciler)


class Tests(unittest.TestCase):
    def test_predecessor_is_frozen_exact_main(self):
        self.assertEqual(reconciler.PREDECESSOR_SOURCE_SHA, "7be2772ca8c0dddefd00181c805bd693bc06a9ed")

    def test_unknown_preimage_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            target_path = Path(temp) / "helper"
            target_path.write_bytes(b"unknown")
            target_path.chmod(0o600)
            target = SimpleNamespace(target=target_path, mode=0o600, source_path="x")
            expected_uid = os.geteuid()
            expected_gid = os.getegid()
            with mock.patch.object(reconciler, "ROOT_UID", expected_uid), \
                 mock.patch.object(reconciler, "ROOT_GID", expected_gid), \
                 mock.patch.object(reconciler.installer, "TRACKED_FILES", (target,)), \
                 mock.patch.object(reconciler, "_require_source_checkout"), \
                 mock.patch.object(reconciler.installer, "_require_dir"), \
                 mock.patch.object(reconciler.installer, "_require_principal"), \
                 mock.patch.object(reconciler.installer, "_require_file"), \
                 mock.patch.object(reconciler.installer, "BASE_REQUIRED_FILES", ()), \
                 mock.patch.object(reconciler, "_source_bytes", side_effect=[b"known-predecessor", b"desired"]):
                with self.assertRaisesRegex(reconciler.ReconcileError, "preimage drifted"):
                    reconciler._prepared("a" * 40)

    def test_preflight_plans_only_changed_tracked_files(self):
        prepared = (
            (SimpleNamespace(), b"same", b"same"),
            (SimpleNamespace(), b"old", b"new"),
        )
        with mock.patch.object(reconciler, "_prepared", return_value=prepared):
            import json
            receipt = json.loads(reconciler.preflight("a" * 40))
        self.assertEqual(receipt["result"], "WEATHER_DATA_RECONCILE_PREFLIGHT_READY")
        self.assertEqual(receipt["planned_replacements"], 1)
        self.assertFalse(receipt["mutation_started"])
        self.assertFalse(receipt["timer_enabled_or_started"])
        self.assertFalse(receipt["docker_command_executed"])
        self.assertFalse(receipt["database_or_data_mutation"])

    def test_apply_requires_root_before_any_preparation(self):
        with mock.patch.object(reconciler.os, "geteuid", return_value=1000), mock.patch.object(reconciler, "_prepared") as prepared:
            with self.assertRaisesRegex(reconciler.ReconcileError, "requires root"):
                reconciler.apply("a" * 40)
        prepared.assert_not_called()

    def test_source_has_no_activation_docker_delete_or_cleanup_authority(self):
        source = PATH.read_text()
        self.assertNotIn("systemctl", source)
        self.assertNotIn('(\"docker\",', source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system(", source)
        self.assertNotIn("unlink(", source)
        self.assertNotIn("remove(", source)
        self.assertNotIn("rmtree", source)
        self.assertIn("os.replace", source)
        self.assertIn("O_EXCL", source)

    def test_receipt_distinguishes_pre_and_post_mutation_state(self):
        import json
        before = json.loads(reconciler._receipt("PRE_MUTATION_FAILURE", "a" * 40, reconciler.Progress()))
        after = json.loads(reconciler._receipt("FAIL_CLOSED", "a" * 40, reconciler.Progress(mutation_started=True, files_replaced=1)))
        self.assertFalse(before["mutation_started"])
        self.assertTrue(after["mutation_started"])
        self.assertEqual(after["files_replaced"], 1)
        self.assertFalse(after["automatic_retry"])
        self.assertFalse(after["automatic_cleanup"])
        self.assertFalse(after["automatic_rollback"])


if __name__ == "__main__":
    unittest.main()
