#!/usr/bin/env python3
"""No host mutation: adversarial source tests of the fixed executor upgrader."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import importlib.util
from io import StringIO
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/upgrade-simple-deploy-executor-v1.py"
spec = importlib.util.spec_from_file_location("simple_deploy_upgrade_933", PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

OLD = b"old-reviewed-executor\n"
NEW = b"new-reviewed-executor\n"
OLD_SHA = hashlib.sha256(OLD).hexdigest()
NEW_SHA = hashlib.sha256(NEW).hexdigest()
COMMIT = "a" * 40
ARGS = ["--expected-source-commit", COMMIT,
        "--expected-source-sha256", NEW_SHA,
        "--expected-installed-sha256", OLD_SHA]
TIMER_OK = (b"LoadState=loaded\nActiveState=inactive\nSubState=dead\n"
            b"UnitFileState=disabled\n")
SERVICE_OK = (b"LoadState=loaded\nActiveState=failed\nSubState=failed\n"
              b"UnitFileState=static\n")


class ContractTests(unittest.TestCase):
    def test_source_is_exact_git_object_no_checkout_change(self):
        with patch.object(mod, "REPO", Path("/tmp")):
            with patch.object(mod, "run", return_value=NEW) as runner:
                self.assertEqual(mod.immutable_source(COMMIT, NEW_SHA), NEW)
            self.assertEqual(runner.call_args.args[0],
                             ["/usr/bin/git", "-C", "/tmp", "cat-file",
                              "blob", f"{COMMIT}:{mod.GIT_PATH}"])

    def test_source_missing_and_hash_drift_fail_closed(self):
        with patch.object(mod, "REPO", Path("/tmp")):
            with patch.object(mod, "run", return_value=OLD):
                with self.assertRaises(mod.Blocked) as cm:
                    mod.immutable_source(COMMIT, NEW_SHA)
                self.assertEqual(cm.exception.code, "SOURCE_HASH_DRIFT")
            with patch.object(mod, "run", side_effect=mod.Blocked("PREFLIGHT_EXEC_FAILED")):
                with self.assertRaises(mod.Blocked):
                    mod.immutable_source(COMMIT, NEW_SHA)

    def test_no_paths_as_command_inputs_or_service_mutators(self):
        src = PATH.read_text()
        for forbidden in (
            '"docker"', '"buildx"', '"stop"', '"start"', '"disable"',
            '"enable"', '"daemon-reload"', '"reset"', '"fetch"',
        ):
            self.assertNotIn(forbidden, src)
        self.assertNotIn("shell=True", src)
        self.assertNotIn("os.unlink(", src)
        self.assertNotIn("os.remove(", src)
        self.assertNotIn("/receipts/", src)
        self.assertNotIn(".env", src)

    def test_quiescence_denies_active_enabled_timer(self):
        cases = [
            (b"LoadState=loaded\nActiveState=active\nSubState=waiting\n"
             b"UnitFileState=enabled\n", "TIMER_NOT_QUIESCED"),
            (b"LoadState=loaded\nActiveState=inactive\nSubState=dead\n"
             b"UnitFileState=enabled\n", "TIMER_NOT_QUIESCED"),
        ]
        for timer, expected in cases:
            with self.subTest(timer=timer):
                with patch.object(mod, "run", side_effect=[timer, SERVICE_OK]):
                    with self.assertRaises(mod.Blocked) as cm:
                        mod.quiescence()
                    self.assertEqual(cm.exception.code, expected)

    def test_quiescence_denies_running_service_and_unknown_metadata(self):
        running = (b"LoadState=loaded\nActiveState=active\nSubState=running\n"
                   b"UnitFileState=static\n")
        with patch.object(mod, "run", side_effect=[TIMER_OK, running]):
            with self.assertRaises(mod.Blocked) as cm:
                mod.quiescence()
            self.assertEqual(cm.exception.code, "SERVICE_NOT_QUIESCED")
        with patch.object(mod, "run", return_value=b"untrusted-data\n"):
            with self.assertRaises(mod.Blocked) as cm:
                mod.quiescence()
            self.assertEqual(cm.exception.code, "UNIT_METADATA_UNAVAILABLE")

    def test_quiescence_is_pure_metadata_check(self):
        with patch.object(mod, "run", side_effect=[TIMER_OK, SERVICE_OK]) as runner:
            mod.quiescence()
        self.assertEqual(len(runner.call_args_list), 2)
        for call in runner.call_args_list:
            self.assertEqual(call.args[0][:3], ["/usr/bin/systemctl", "show", "--no-pager"])

    def test_check_does_not_write_or_require_root(self):
        buffer = StringIO()
        with patch.object(mod, "immutable_source", return_value=NEW), \
             patch.object(mod, "installed_guard"), \
             patch.object(mod, "quiescence") as quiescence, \
             patch.object(mod, "atomic_upgrade") as apply, \
             redirect_stdout(buffer):
            self.assertEqual(mod.main(ARGS), 0)
        quiescence.assert_called_once()
        apply.assert_not_called()
        self.assertIn("result=PREFLIGHT_READY mutation_started=false", buffer.getvalue())

    def test_apply_requires_trusted_root_owned_operator(self):
        buffer = StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(mod.main(ARGS + ["--apply"]), 1)
        self.assertIn("error_code=TRUSTED_OPERATOR_REQUIRED", buffer.getvalue())
        self.assertIn("mutation_started=false", buffer.getvalue())

    def test_drift_and_symlink_block_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "code.py"
            dst.write_bytes(OLD)
            dst.chmod(0o444)
            with patch.object(mod, "INSTALLED", dst), \
                 patch.object(mod, "parent_guard", return_value=dst.parent.stat()):
                with self.assertRaises(mod.Blocked) as cm:
                    mod.installed_guard(NEW_SHA)
                self.assertEqual(cm.exception.code, "INSTALLED_SHA_DRIFT")
                link = Path(tmp) / "symlink.py"
                link.symlink_to(dst)
                with self.assertRaises(mod.Blocked) as cm:
                    mod.read_checked(link, uid=0, mode=0o444)
                self.assertEqual(cm.exception.code, "FILE_TYPE_DRIFT")

    def test_apply_single_atomic_replace_with_preserved_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "simple_deploy_v1.py"
            dst.write_bytes(OLD)
            dst.chmod(0o444)
            def snapshot(expected):
                self.assertEqual(hashlib.sha256(dst.read_bytes()).hexdigest(), expected)
                return dst.lstat()
            def read_post(path, *, uid, mode):
                self.assertEqual(path, dst)
                self.assertEqual(mode, 0o444)
                return path.read_bytes(), path.lstat()
            with patch.object(mod, "INSTALLED", dst), \
                 patch.object(mod, "parent_guard", side_effect=lambda: dst.parent.lstat()), \
                 patch.object(mod, "installed_guard", side_effect=snapshot), \
                 patch.object(mod, "read_checked", side_effect=read_post), \
                 patch.object(mod, "quiescence") as q, \
                 patch.object(mod.os, "fchown"), \
                 patch.object(mod.os, "replace", wraps=os.replace) as swap:
                mod.atomic_upgrade(NEW, OLD_SHA, NEW_SHA)
                self.assertEqual(q.call_count, 3)
                swap.assert_called_once()
            self.assertEqual(dst.read_bytes(), NEW)
            self.assertEqual(stat.S_IMODE(dst.stat().st_mode), 0o444)
            self.assertFalse((dst.parent / mod.STAGE).exists())

    def test_post_staging_failure_keeps_old_and_no_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "simple_deploy_v1.py"
            dst.write_bytes(OLD)
            dst.chmod(0o444)
            def snapshot(expected):
                self.assertEqual(hashlib.sha256(dst.read_bytes()).hexdigest(), expected)
                return dst.lstat()
            with patch.object(mod, "INSTALLED", dst), \
                 patch.object(mod, "parent_guard", side_effect=lambda: dst.parent.lstat()), \
                 patch.object(mod, "installed_guard", side_effect=snapshot), \
                 patch.object(mod, "quiescence"), \
                 patch.object(mod.os, "fchown"), \
                 patch.object(mod.os, "replace", side_effect=OSError("secret-private-error")):
                with self.assertRaises(mod.Blocked) as cm:
                    mod.atomic_upgrade(NEW, OLD_SHA, NEW_SHA)
            self.assertEqual(cm.exception.code, "ATOMIC_REPLACEMENT_FAILED")
            self.assertEqual(dst.read_bytes(), OLD)
            self.assertTrue((dst.parent / mod.STAGE).exists())

    def test_second_timer_check_can_block_after_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "simple_deploy_v1.py"
            dst.write_bytes(OLD)
            dst.chmod(0o444)
            def snapshot(expected):
                self.assertEqual(hashlib.sha256(dst.read_bytes()).hexdigest(), expected)
                return dst.lstat()
            with patch.object(mod, "INSTALLED", dst), \
                 patch.object(mod, "parent_guard", side_effect=lambda: dst.parent.lstat()), \
                 patch.object(mod, "installed_guard", side_effect=snapshot), \
                 patch.object(mod, "quiescence", side_effect=[None, mod.Blocked("TIMER_NOT_QUIESCED")]), \
                 patch.object(mod.os, "fchown"), \
                 patch.object(mod.os, "replace", wraps=os.replace) as swap:
                with self.assertRaises(mod.Blocked) as cm:
                    mod.atomic_upgrade(NEW, OLD_SHA, NEW_SHA)
                swap.assert_not_called()
            self.assertEqual(cm.exception.code, "TIMER_NOT_QUIESCED")
            self.assertEqual(dst.read_bytes(), OLD)
            self.assertTrue((dst.parent / mod.STAGE).exists())

    def test_failed_runner_does_not_leak_stderr(self):
        with patch.object(mod.subprocess, "run", side_effect=OSError("TOKEN_PRIVATE")):
            with self.assertRaises(mod.Blocked) as cm:
                mod.run(["/usr/bin/git", "version"])
        self.assertEqual(cm.exception.code, "PREFLIGHT_EXEC_UNAVAILABLE")
        self.assertNotIn("TOKEN", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
