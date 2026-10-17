#!/usr/bin/env python3
"""Offline three-component Ausmalwiese cutover negative tests; temp files only."""
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
FILE = ROOT / "scripts/upgrade-ausmalwiese-coordinated-v1.py"
mod = importlib.machinery.SourceFileLoader("ausmalwiese_coordinated_under_test", str(FILE)).load_module()


def blob(value: bytes):
    return hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest()


class CoordinatedTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        binary = root / "bin"
        vendor = root / "share/coloring-pages"
        state = root / "state/drive-ingest"
        for folder in (binary, vendor, state):
            folder.mkdir(parents=True)
            folder.chmod(0o755)
        lock = state / ".lock"
        lock.touch()
        lock.chmod(0o600)
        self.paths = mod.Paths(binary, vendor, lock)
        self.uid, self.gid = os.getuid(), os.getgid()
        self.old = {k: ("old " + k + "\n").encode() for k in mod.OLD}
        self.new = {k: ("new " + k + "\n").encode() for k in mod.NEW}
        with mock.patch.object(mod, "OLD", {k: blob(v) for k, v in self.old.items()}):
            pass
        patch = mock.patch.multiple(
            mod, OLD={k: blob(v) for k, v in self.old.items()},
            NEW={k: blob(v) for k, v in self.new.items()},
        )
        patch.start()
        self.addCleanup(patch.stop)
        for name, dest in self.paths.installed.items():
            dest.write_bytes(self.old[name])
            dest.chmod(0o444 if name == mod.GEN else 0o755)
        self.paths.marker.write_bytes(mod.MARKER_BYTES)
        self.paths.marker.chmod(0o444)
        self.paths.quiescence.write_bytes(mod.QUIESCENCE_BYTES)
        self.paths.quiescence.chmod(0o444)

    def run_op(self, apply=False, sources=None, reconfirm=None):
        source = self.new if sources is None else sources
        return mod.execute(
            self.paths, source, root_uid=self.uid, root_gid=self.gid,
            owner_uid=self.uid, owner_gid=self.gid, apply=apply,
            reconfirm=(lambda: dict(source)) if reconfirm is None else reconfirm)

    def test_read_only_check_preserves_active_marker(self):
        self.assertEqual(self.run_op()["result"], "CHECK_PASS")
        self.assertEqual(self.paths.marker.read_bytes(), mod.MARKER_BYTES)
        self.assertFalse(any(p.exists() for p in self.paths.stages.values()))

    def test_exact_three_component_upgrade_marker_unchanged(self):
        initial = self.paths.marker.stat()
        report = self.run_op(apply=True)
        self.assertEqual(report["result"], "UPGRADE_PASS")
        self.assertTrue(report["enabled_marker_preserved"])
        for key, path in self.paths.installed.items():
            self.assertEqual(path.read_bytes(), self.new[key])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),
                             0o444 if key == mod.GEN else 0o755)
        self.assertEqual(self.paths.marker.stat().st_ino, initial.st_ino)
        self.assertEqual(self.paths.marker.read_bytes(), mod.MARKER_BYTES)
        self.assertFalse(any(p.exists() for p in self.paths.stages.values()))

    def test_missing_or_bad_quiescence_is_stop(self):
        self.paths.quiescence.unlink()
        with self.assertRaises((OSError, mod.Stop)):
            self.run_op(apply=True)
        self.assertFalse(any(p.exists() for p in self.paths.stages.values()))
        self.paths.quiescence.write_bytes(b"not an attestation")
        self.paths.quiescence.chmod(0o444)
        with self.assertRaises(mod.Stop):
            self.run_op(apply=True)

    def test_enabled_marker_wrong_bytes_or_identity_rejected(self):
        self.paths.marker.chmod(0o600)
        with self.assertRaises(mod.helper.UpgradeError):
            self.run_op(apply=True)
        self.paths.marker.chmod(0o444)
        self.paths.marker.unlink()
        self.paths.marker.symlink_to(self.paths.quiescence)
        with self.assertRaises(mod.helper.UpgradeError):
            self.run_op(apply=True)

    def test_lock_contention_prevents_any_write(self):
        fd = os.open(self.paths.lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(mod.helper.UpgradeError):
                self.run_op(apply=True)
        finally:
            os.close(fd)
        self.assertFalse(any(p.exists() for p in self.paths.stages.values()))

    def test_bad_old_ingester_or_candidate_aborts_before_stage(self):
        file = self.paths.installed[mod.INGEST]
        file.write_bytes(b"tampered")
        with self.assertRaises(mod.Stop):
            self.run_op(apply=True)
        file.write_bytes(self.old[mod.INGEST])
        bad = dict(self.new)
        bad[mod.INGEST] = b"untrusted candidate"
        with self.assertRaises(mod.Stop):
            self.run_op(apply=True, sources=bad)
        self.assertFalse(any(p.exists() for p in self.paths.stages.values()))

    def test_dirty_snapshot_reconfirmation_rejected(self):
        with self.assertRaises(mod.Stop):
            self.run_op(apply=True, reconfirm=lambda: {})
        self.assertFalse(any(p.exists() for p in self.paths.stages.values()))

    def test_orphan_partial_is_preserved_without_retry(self):
        first = self.paths.stages[mod.GEN]
        first.write_bytes(b"orphan")
        with self.assertRaises(mod.Stop):
            self.run_op(apply=True)
        self.assertEqual(first.read_bytes(), b"orphan")

    def test_interrupted_staging_keeps_partial_files(self):
        original = mod.helper.stage
        def fail_later(path, data, mode, *, uid, gid):
            if path == self.paths.stages[mod.INGEST]:
                raise OSError("failure after staging other components")
            return original(path, data, mode, uid=uid, gid=gid)
        with mock.patch.object(mod.helper, "stage", side_effect=fail_later):
            with self.assertRaises(OSError):
                self.run_op(apply=True)
        self.assertTrue(self.paths.stages[mod.GEN].exists())
        self.assertTrue(self.paths.stages[mod.PUBLISH].exists())
        with self.assertRaises(mod.Stop):
            self.run_op(apply=True)

    def test_interrupted_replace_keeps_partial_old_new_mix(self):
        original = mod.os.replace
        def fail_ingester(a, b):
            if b == self.paths.installed[mod.INGEST]:
                raise OSError("failure after replacing sitemap files")
            return original(a, b)
        with mock.patch.object(mod.os, "replace", side_effect=fail_ingester):
            with self.assertRaises(OSError):
                self.run_op(apply=True)
        self.assertEqual(self.paths.installed[mod.GEN].read_bytes(), self.new[mod.GEN])
        self.assertEqual(self.paths.installed[mod.PUBLISH].read_bytes(), self.new[mod.PUBLISH])
        self.assertEqual(self.paths.installed[mod.INGEST].read_bytes(), self.old[mod.INGEST])
        self.assertTrue(self.paths.stages[mod.INGEST].exists())
        with self.assertRaises(mod.Stop):
            self.run_op(apply=True)

    def test_enabled_marker_mid_upgrade_drift_stops(self):
        original = mod.helper.stage
        def change_gate(path, data, mode, *, uid, gid):
            result = original(path, data, mode, uid=uid, gid=gid)
            if path == self.paths.stages[mod.INGEST]:
                self.paths.marker.chmod(0o600)
            return result
        with mock.patch.object(mod.helper, "stage", side_effect=change_gate):
            with self.assertRaises(mod.helper.UpgradeError):
                self.run_op(apply=True)
        self.assertTrue(self.paths.stages[mod.INGEST].exists())
        self.assertEqual(self.paths.installed[mod.INGEST].read_bytes(), self.old[mod.INGEST])

    def test_second_apply_must_stop(self):
        self.run_op(apply=True)
        with self.assertRaises(mod.Stop):
            self.run_op(apply=True)

    def test_no_implicit_activation_or_cleanup(self):
        code = FILE.read_text()
        self.assertNotIn("marker.unlink", code)
        self.assertNotIn("quiescence.unlink", code)
        self.assertNotIn("os.remove(", code)
        self.assertNotIn("shutil.rmtree(", code)
        self.assertIn("sitemap-ingest-quiesced-v1.confirmed", code)
        for digest in (
            "b1e796696307dcdbc9f92c1caf190c38032ccd71",
            "6aba3414af9cc484bde40171f6dd815485c18e22",
        ):
            self.assertIn(digest, code)


if __name__ == "__main__":
    unittest.main()
