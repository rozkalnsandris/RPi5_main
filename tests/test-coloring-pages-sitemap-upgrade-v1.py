#!/usr/bin/env python3
"""Offline tests only; no production host paths are accessed."""
from __future__ import annotations
import fcntl
import hashlib
import importlib.machinery
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/upgrade-coloring-pages-sitemap-publisher-v1.py"
mod = importlib.machinery.SourceFileLoader("sitemap_exact_upgrade", str(SCRIPT)).load_module()


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class ExactUpgradeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bin = self.root / "bin"
        self.vendor = self.root / "share/coloring-pages"
        self.state = self.root / "state/drive-ingest"
        for d in (self.bin, self.vendor, self.state):
            d.mkdir(parents=True)
            d.chmod(0o755)
        self.lock = self.state / ".lock"
        self.lock.touch()
        self.lock.chmod(0o600)
        self.paths = mod.Paths(self.bin, self.vendor, self.lock)
        self.uid, self.gid = os.getuid(), os.getgid()
        self.old = {mod.OPERATOR: b"old operator\n", mod.GENERATOR: b"old generator\n"}
        self.new = {mod.OPERATOR: b"new operator\n", mod.GENERATOR: b"new generator\n"}
        patches = mock.patch.multiple(
            mod, OLD={k: blob(v) for k, v in self.old.items()},
            NEW={k: blob(v) for k, v in self.new.items()},
        )
        patches.start()
        self.addCleanup(patches.stop)
        self.paths.operator.write_bytes(self.old[mod.OPERATOR])
        self.paths.operator.chmod(0o755)
        self.paths.generator.write_bytes(self.old[mod.GENERATOR])
        self.paths.generator.chmod(0o444)

    def run_op(self, apply=False, *, candidates=None, reconfirm=None):
        src = self.new if candidates is None else candidates
        return mod.execute(
            self.paths, src, root_uid=self.uid, root_gid=self.gid,
            owner_uid=self.uid, owner_gid=self.gid, apply=apply,
            reconfirm=(lambda: dict(src)) if reconfirm is None else reconfirm,
        )

    def test_fixed_source_pins_and_blob_hash(self):
        content = SCRIPT.read_text()
        for expected in (
            "0da51ef361f9ce815ebde3e4cc6cae19a2c2ffe8",
            "5644c8fd366c0c57f6339fddd163c5091ea134c5",
            "7b0330f30e27d6fe9c5f3e4fbf81fc6473ade660",
            "49c8ba34cf0a4c4ab100463df9adacc4c6e90c2c",
        ):
            self.assertIn(expected, content)
        self.assertEqual(blob(b"abc"), "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f")

    def test_check_is_read_only(self):
        self.assertEqual(self.run_op()["result"], "CHECK_PASS")
        self.assertFalse(self.paths.operator_stage.exists())
        self.assertFalse(self.paths.generator_stage.exists())
        self.assertEqual(self.paths.operator.read_bytes(), self.old[mod.OPERATOR])

    def test_exact_upgrade_preserves_modes(self):
        self.assertEqual(self.run_op(apply=True)["result"], "UPGRADE_PASS")
        self.assertEqual(self.paths.operator.read_bytes(), self.new[mod.OPERATOR])
        self.assertEqual(self.paths.generator.read_bytes(), self.new[mod.GENERATOR])
        self.assertEqual(stat.S_IMODE(self.paths.operator.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.paths.generator.stat().st_mode), 0o444)
        self.assertFalse(self.paths.operator_stage.exists())
        self.assertFalse(self.paths.generator_stage.exists())

    def test_duplicate_upgrade_not_retried(self):
        self.run_op(apply=True)
        with self.assertRaisesRegex(mod.UpgradeError, "not the exact old"):
            self.run_op(apply=True)

    def test_enabled_marker_blocks_before_mutation(self):
        self.paths.marker.write_bytes(b"enabled")
        with self.assertRaisesRegex(mod.UpgradeError, "post-publish hook"):
            self.run_op(apply=True)
        self.assertFalse(self.paths.generator_stage.exists())

    def test_tampered_installed_bytes_or_mode(self):
        for file in (self.paths.operator, self.paths.generator):
            old, mode = file.read_bytes(), stat.S_IMODE(file.stat().st_mode)
            file.chmod(0o600)  # Fixture: 0444 generator cannot be written directly.
            file.write_bytes(b"foreign bytes")
            file.chmod(mode)
            with self.assertRaises(mod.UpgradeError):
                self.run_op(apply=True)
            file.chmod(0o600)
            file.write_bytes(old)
            with self.assertRaises(mod.UpgradeError):
                self.run_op(apply=True)
            file.chmod(mode)

    def test_symlink_rejected(self):
        self.paths.operator.unlink()
        self.paths.operator.symlink_to(self.paths.generator)
        with self.assertRaises(mod.UpgradeError):
            self.run_op(apply=True)

    def test_wrong_candidate_rejected(self):
        incorrect = dict(self.new)
        incorrect[mod.GENERATOR] = b"not trusted"
        with self.assertRaisesRegex(mod.UpgradeError, "SHA mismatch"):
            self.run_op(apply=True, candidates=incorrect)
        self.assertFalse(self.paths.generator_stage.exists())

    def test_preexisting_partial_stage_untouched(self):
        self.paths.generator_stage.write_bytes(b"orphan")
        with self.assertRaisesRegex(mod.UpgradeError, "stage"):
            self.run_op(apply=True)
        self.assertEqual(self.paths.generator_stage.read_bytes(), b"orphan")

    def test_shared_lock_contention_no_write(self):
        fd = os.open(self.lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(mod.UpgradeError, "shared lock busy"):
                self.run_op(apply=True)
        finally:
            os.close(fd)
        self.assertFalse(self.paths.generator_stage.exists())

    def test_missing_or_drifted_reconfirmation(self):
        with self.assertRaisesRegex(mod.UpgradeError, "confirmation"):
            self.run_op(apply=True, reconfirm=lambda: {})
        with self.assertRaisesRegex(mod.UpgradeError, "confirmation"):
            mod.execute(self.paths, self.new, root_uid=self.uid, root_gid=self.gid,
                        owner_uid=self.uid, owner_gid=self.gid, apply=True)
        self.assertFalse(self.paths.generator_stage.exists())

    def test_failure_after_first_stage_keeps_partial(self):
        actual = mod.stage
        def error_second(path, content, mode, *, uid, gid):
            if path == self.paths.operator_stage:
                raise OSError("injected failure after first stage")
            return actual(path, content, mode, uid=uid, gid=gid)
        with mock.patch.object(mod, "stage", side_effect=error_second):
            with self.assertRaises(OSError):
                self.run_op(apply=True)
        self.assertTrue(self.paths.generator_stage.exists())
        self.assertEqual(self.paths.operator.read_bytes(), self.old[mod.OPERATOR])
        with self.assertRaises(mod.UpgradeError):
            self.run_op(apply=True)

    def test_failure_between_replacements_keeps_old_and_new(self):
        actual = mod.os.replace
        def error_second(source, target):
            if target == self.paths.operator:
                raise OSError("injected between replacements")
            return actual(source, target)
        with mock.patch.object(mod.os, "replace", side_effect=error_second):
            with self.assertRaises(OSError):
                self.run_op(apply=True)
        self.assertEqual(self.paths.generator.read_bytes(), self.new[mod.GENERATOR])
        self.assertEqual(self.paths.operator.read_bytes(), self.old[mod.OPERATOR])
        self.assertTrue(self.paths.operator_stage.exists())
        with self.assertRaises(mod.UpgradeError):
            self.run_op(apply=True)

    def test_bad_lock_metadata_blocks(self):
        self.lock.chmod(0o644)
        with self.assertRaisesRegex(mod.UpgradeError, "unsafe shared lock"):
            self.run_op(apply=True)

    def test_no_generic_paths_cleanup_or_marker_toggle(self):
        src = SCRIPT.read_text()
        self.assertIn('Path("/usr/local/bin")', src)
        self.assertIn('Path("/usr/local/share/coloring-pages")', src)
        self.assertIn('Path("/srv/coloring-pages-content/state/drive-ingest/.lock")', src)
        self.assertNotIn("os.remove(", src)
        self.assertNotIn("marker.unlink(", src)
        self.assertNotIn("marker.write_bytes(", src)


if __name__ == "__main__":
    unittest.main()
