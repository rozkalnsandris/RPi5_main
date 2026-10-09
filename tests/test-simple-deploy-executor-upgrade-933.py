#!/usr/bin/env python3
"""Offline fake-root and hostile-state tests for #933 source-only operator."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "ops/bin/simple-deploy-executor-upgrade-933"
loader = importlib.machinery.SourceFileLoader("upgrade_933", str(FILE))
spec = importlib.util.spec_from_loader(loader.name, loader)
op = importlib.util.module_from_spec(spec)
loader.exec_module(op)
REAL_UNIT_PROPERTIES = op.unit_properties

TIMER_OK = {
    "LoadState": "loaded", "UnitFileState": "disabled",
    "ActiveState": "inactive", "SubState": "dead",
    "Job": "0", "NeedDaemonReload": "no",
}
SERVICE_OK = {
    "LoadState": "loaded", "ActiveState": "inactive", "SubState": "dead",
    "MainPID": "0", "Job": "0", "NeedDaemonReload": "no",
}
OLD = b"old public installed SIMPLE-DEPLOY code"
NEW = b"reviewed immutable Git object for issue 933"


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "root"
        self.root.mkdir()
        self.target = self.root / "simple_deploy_v1.py"
        self.source = self.base / "approved.py"
        self.approval = self.base / "approval.json"
        self.target.write_bytes(OLD)
        self.source.write_bytes(NEW)
        self.target.chmod(0o444)
        self.source.chmod(0o444)
        self.approval.write_text(json.dumps({
            "schema": "rpi5.simple_deploy_executor_upgrade_owner_authorization.v1",
            "issue": 933, "commit": op.COMMIT,
            "git_blob_sha1": op.blob_id(NEW),
            "source_sha256": op.sha(NEW), "baseline_sha256": op.sha(OLD),
            "target": "simple_deploy_v1.py", "operation": "single_atomic_replace",
            "no_automatic_retry_rollback_cleanup": True,
        }))
        self.approval.chmod(0o400)
        self.patches = [
            patch.object(op, "ROOT", self.root),
            patch.object(op, "TARGET", self.target),
            patch.object(op, "SOURCE", self.source),
            patch.object(op, "APPROVAL", self.approval),
            patch.object(op, "EXPECTED_SOURCE", op.sha(NEW)),
            patch.object(op, "EXPECTED_INSTALLED", op.sha(OLD)),
            patch.object(op, "GIT_BLOB", op.blob_id(NEW)),
            patch.object(op, "safe_directory", return_value=None),
            patch.object(op, "unit_properties", side_effect=self.units),
            patch.object(op, "open_public", side_effect=self.fake_open),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        op.MUTATION_STARTED = False
        self.addCleanup(setattr, op, "MUTATION_STARTED", False)
        self.timer = TIMER_OK.copy()
        self.service = SERVICE_OK.copy()

    def units(self, name, keys):
        if name == op.TIMER:
            return self.timer.copy()
        if name == op.SERVICE:
            return self.service.copy()
        self.fail("unknown systemd unit")

    def fake_open(self, path, *, mode):
        # Simulates root ownership only; still uses real tempfile inode/mode
        # so file swaps, symlinks, deleted files and drift are observable.
        try:
            s = path.lstat()
        except OSError:
            op.fail("public_file_missing_or_symlink")
        if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or
                stat.S_IMODE(s.st_mode) != mode):
            op.fail("public_file_metadata_drift")
        data = path.read_bytes()
        return ((s.st_dev, s.st_ino, s.st_mtime_ns, s.st_size), data)

    def fake_root(self):
        real_stat = os.fstat
        def fstat(fd):
            st = real_stat(fd)
            return types.SimpleNamespace(
                st_mode=st.st_mode, st_uid=0, st_size=st.st_size)
        return (patch.object(op.os, "fstat", side_effect=fstat),
                patch.object(op.os, "fchown", return_value=None))

    def test_default_check_is_read_only(self):
        buf = io.StringIO()
        with redirect_stdout(buf), patch.object(op, "approved") as approval:
            self.assertEqual(op.main([]), 0)
            approval.assert_not_called()
        self.assertEqual(json.loads(buf.getvalue())["result"], "READY")
        self.assertFalse(op.MUTATION_STARTED)
        self.assertFalse((self.root / op.STAGE_NAME).exists())
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_missing_or_corrupt_source_blocks(self):
        self.source.unlink()
        with self.assertRaisesRegex(op.Block, "public_file_missing"):
            op.check()
        self.source.write_bytes(NEW + b"tamper")
        self.source.chmod(0o444)
        with self.assertRaisesRegex(op.Block, "approved_source_identity_mismatch"):
            op.check()

    def test_bad_git_blob_id_blocks(self):
        with patch.object(op, "GIT_BLOB", "0" * 40):
            with self.assertRaisesRegex(op.Block, "approved_source_identity_mismatch"):
                op.check()

    def test_installed_baseline_drift_blocks(self):
        self.target.chmod(0o644)
        self.target.write_bytes(OLD + b"tamper")
        self.target.chmod(0o444)
        with self.assertRaisesRegex(op.Block, "installed_baseline_sha_mismatch"):
            op.check()

    def test_symlink_and_wrong_mode_block(self):
        self.source.chmod(0o666)
        with self.assertRaisesRegex(op.Block, "public_file_metadata_drift"):
            op.check()
        self.source.unlink()
        self.source.symlink_to(self.target)
        with self.assertRaisesRegex(op.Block, "public_file_metadata_drift"):
            op.check()
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_existing_stage_blocks_reentry(self):
        (self.root / op.STAGE_NAME).write_bytes(b"old stage")
        with self.assertRaisesRegex(op.Block, "previous_staging_artifact_present"):
            op.check()

    def test_timer_enabled_active_or_job_blocks(self):
        for key, value in [("UnitFileState", "enabled"),
                           ("ActiveState", "active"), ("Job", "219")]:
            with self.subTest(key=key):
                self.timer = TIMER_OK.copy()
                self.timer[key] = value
                with self.assertRaisesRegex(op.Block, "timer_not_disabled_inactive"):
                    op.check()

    def test_service_active_failed_or_job_blocks(self):
        for key, value in [("ActiveState", "active"),
                           ("ActiveState", "failed"),
                           ("MainPID", "339"), ("Job", "133")]:
            with self.subTest(key=key, value=value):
                self.service = SERVICE_OK.copy()
                self.service[key] = value
                with self.assertRaisesRegex(op.Block, "service_not_inactive"):
                    op.check()

    def test_changed_metadata_in_two_snapshots_blocks(self):
        orig = op.public_sources
        counter = [0]
        def drift():
            counter[0] += 1
            if counter[0] == 2:
                self.target.chmod(0o644)
                self.target.write_bytes(OLD + b"changed")
                self.target.write_bytes(OLD)
                self.target.chmod(0o444)
            return orig()
        with patch.object(op, "public_sources", side_effect=drift):
            with self.assertRaisesRegex(op.Block, "concurrent_source_or_target_change"):
                op.check()

    def test_owner_approval_is_fixed_and_separately_required(self):
        op.approved()
        record = json.loads(self.approval.read_text())
        record["operation"] = "any-command"
        self.approval.chmod(0o600)
        self.approval.write_text(json.dumps(record))
        self.approval.chmod(0o400)
        with self.assertRaisesRegex(op.Block, "owner_approval_mismatch"):
            op.approved()

    def test_uninstalled_root_apply_never_mutates(self):
        buf = io.StringIO()
        with patch.object(op.os, "geteuid", return_value=0), redirect_stdout(buf):
            self.assertEqual(op.main(["--apply"]), 2)
        self.assertEqual(json.loads(buf.getvalue())["reason"], "operator_not_installed")
        self.assertEqual(self.target.read_bytes(), OLD)
        self.assertFalse((self.root / op.STAGE_NAME).exists())

    def test_non_root_apply_never_mutates(self):
        buf = io.StringIO()
        with patch.object(op.os, "geteuid", return_value=1001), redirect_stdout(buf):
            self.assertEqual(op.main(["--apply"]), 2)
        self.assertEqual(json.loads(buf.getvalue())["reason"], "root_required")
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_successful_atomic_one_file_replace(self):
        identity, desired = op.check()
        st, chown = self.fake_root()
        with st, chown:
            self.assertEqual(op.atomic_once(identity, desired), "PASS")
        self.assertTrue(op.MUTATION_STARTED)
        self.assertEqual(self.target.read_bytes(), NEW)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o444)
        self.assertFalse((self.root / op.STAGE_NAME).exists())

    def test_race_before_replace_stops_without_overwrite(self):
        identity, desired = op.check()
        original_quiescence = op.quiescent
        def mutate_target():
            self.target.chmod(0o644)
            self.target.write_bytes(OLD + b"external change")
            self.target.chmod(0o444)
            return original_quiescence()
        st, chown = self.fake_root()
        with st, chown, patch.object(op, "quiescent", side_effect=mutate_target):
            with self.assertRaisesRegex(op.Block, "race_before_replace"):
                op.atomic_once(identity, desired)
        self.assertIn(b"external change", self.target.read_bytes())
        self.assertTrue((self.root / op.STAGE_NAME).exists())

    def test_error_after_stage_keeps_stage_and_baseline(self):
        identity, desired = op.check()
        st, chown = self.fake_root()
        with st, chown, patch.object(op.os, "replace", side_effect=OSError("simulated")) as swap:
            with self.assertRaisesRegex(op.Block, "mutation_io_error_no_retry"):
                op.atomic_once(identity, desired)
            swap.assert_called_once()
        self.assertTrue(op.MUTATION_STARTED)
        self.assertTrue((self.root / op.STAGE_NAME).exists())
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_systemd_command_is_fixed_and_output_fail_closed(self):
        with patch.object(op, "fixed_command", return_value=(
            "LoadState=loaded\nUnitFileState=disabled\nActiveState=inactive\n"
            "SubState=dead\nJob=0\nNeedDaemonReload=no\n")):
            self.assertEqual(REAL_UNIT_PROPERTIES(op.TIMER, tuple(TIMER_OK)), TIMER_OK)
        with patch.object(op, "fixed_command", return_value="ActiveState=active\nActiveState=inactive\n"):
            with self.assertRaisesRegex(op.Block, "systemd_status_invalid"):
                REAL_UNIT_PROPERTIES(op.TIMER, tuple(TIMER_OK))

    def test_no_implicit_runtime_mutations(self):
        source = FILE.read_text()
        self.assertNotIn("os.system(", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("systemctl stop", source)
        self.assertNotIn("systemctl disable", source)
        self.assertNotIn("docker compose", source)
        self.assertNotIn("shutil.copy", source)
        self.assertNotIn("unlink(", source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("os.O_NOFOLLOW", source)
        self.assertIn("os.replace(", source)
        self.assertIn("EXPECTED_INSTALLED", source)
        self.assertIn("EXPECTED_SOURCE", source)


if __name__ == "__main__":
    unittest.main()
