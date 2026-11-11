#!/usr/bin/env python3
"""Offline isolated regressions for the source-only exact three-file sitemap suite upgrade."""
from __future__ import annotations

import fcntl
import hashlib
import importlib.machinery
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/upgrade-coloring-pages-sitemap-suite-v1.py"
mod = importlib.machinery.SourceFileLoader(
    "coloring_sitemap_suite_upgrade", str(SCRIPT)
).load_module()


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class ExactSitemapSuiteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
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
        self.old = {
            mod.GENERATOR: b"old generator\n",
            mod.OPERATOR: b"old publisher\n",
            mod.INGEST: b"old ingester\n",
        }
        self.new = {
            mod.GENERATOR: b"new generator\n",
            mod.OPERATOR: b"new publisher\n",
            mod.INGEST: b"new ingester\n",
        }
        patches = mock.patch.multiple(
            mod,
            OLD={k: blob(v) for k, v in self.old.items()},
            NEW={k: blob(v) for k, v in self.new.items()},
        )
        patches.start()
        self.addCleanup(patches.stop)
        for path, name, mode in (
            (self.paths.generator, mod.GENERATOR, 0o444),
            (self.paths.operator, mod.OPERATOR, 0o755),
            (self.paths.ingest, mod.INGEST, 0o755),
        ):
            path.write_bytes(self.old[name])
            path.chmod(mode)

    def run_op(self, apply=False, *, marker="absent", probe=lambda: True,
               sources=None, reconfirm=None):
        candidates = dict(self.new) if sources is None else sources
        return mod.execute(
            self.paths,
            candidates,
            root_uid=self.uid,
            root_gid=self.gid,
            owner_uid=self.uid,
            owner_gid=self.gid,
            apply=apply,
            expected_marker=marker,
            quiescence=probe,
            reconfirm=(lambda: dict(candidates)) if reconfirm is None else reconfirm,
        )

    def test_current_release_pins_and_github_source_blobs(self):
        src = SCRIPT.read_text()
        for digest in (
            "4ade38f1225f4c1bc102fda8d5538f9262695d43",
            "5d1d37c32573aa8ac0d91f45b73938638fd183e9",
            "b10dc43bceb8ac3b77d8af47661b11a4ca50ea90",
            "3263845045f6d38f31ff359158be90ab59006240",
            "f4ffaa4293f9c46f475f96d4409f05ff347a7590",
            "c4e2f67e0154f705e2d46db9dcc87e6a69b108fd",
        ):
            self.assertIn(digest, src)
        self.assertEqual(
            blob((ROOT / mod.OPERATOR).read_bytes()),
            "3263845045f6d38f31ff359158be90ab59006240",
        )
        self.assertEqual(
            blob((ROOT / mod.GENERATOR).read_bytes()),
            "f4ffaa4293f9c46f475f96d4409f05ff347a7590",
        )
        self.assertEqual(
            blob((ROOT / mod.INGEST).read_bytes()),
            "c4e2f67e0154f705e2d46db9dcc87e6a69b108fd",
        )

    def test_check_is_read_only_and_reports_all_three(self):
        result = self.run_op()
        self.assertEqual(result["result"], "CHECK_PASS")
        self.assertEqual(result["old_ingest"], blob(self.old[mod.INGEST]))
        self.assertEqual(result["new_ingest"], blob(self.new[mod.INGEST]))
        self.assertFalse(result["mutation_started"])
        self.assertEqual(self.paths.ingest.read_bytes(), self.old[mod.INGEST])
        for partial in self.stages():
            self.assertFalse(partial.exists())

    def stages(self):
        return (self.paths.generator_stage, self.paths.operator_stage,
                self.paths.ingest_stage)

    def test_three_file_upgrade_fsync_order_and_modes(self):
        actual = mod.os.replace
        swapped = []

        def track(src, dst):
            swapped.append((src, dst))
            return actual(src, dst)

        with mock.patch.object(mod.os, "replace", side_effect=track):
            result = self.run_op(apply=True)
        self.assertEqual(result["result"], "UPGRADE_PASS")
        self.assertEqual(
            [dst for _, dst in swapped],
            [self.paths.generator, self.paths.operator, self.paths.ingest],
        )
        for path, name, mode in (
            (self.paths.generator, mod.GENERATOR, 0o444),
            (self.paths.operator, mod.OPERATOR, 0o755),
            (self.paths.ingest, mod.INGEST, 0o755),
        ):
            self.assertEqual(path.read_bytes(), self.new[name])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
        self.assertTrue(all(not p.exists() for p in self.stages()))

    def test_active_writer_probe_blocks_before_any_stage(self):
        with self.assertRaisesRegex(mod.UpgradeError, "quiescence"):
            self.run_op(apply=True, probe=lambda: False)
        self.assertTrue(all(not p.exists() for p in self.stages()))
        self.assertEqual(self.paths.operator.read_bytes(), self.old[mod.OPERATOR])

    def test_missing_writer_probe_blocks_before_any_stage(self):
        with self.assertRaisesRegex(mod.UpgradeError, "quiescence"):
            self.run_op(apply=True, probe=None)
        self.assertTrue(all(not p.exists() for p in self.stages()))

    def test_fixed_systemd_guard_requires_two_inactive_loaded_units(self):
        healthy = "LoadState=loaded\nActiveState=inactive\nJob=\n"
        failing = "LoadState=loaded\nActiveState=active\nJob=\n"
        with mock.patch.object(
            mod.subprocess, "run",
            side_effect=[subprocess.CompletedProcess([], 0, healthy, ""),
                         subprocess.CompletedProcess([], 0, healthy, "")],
        ) as run:
            self.assertTrue(mod.require_writer_quiescence())
            self.assertEqual(run.call_count, 2)
            for c in run.call_args_list:
                self.assertEqual(c.args[0][0], "/usr/bin/systemctl")
                self.assertEqual(c.args[0][1], "show")
        with mock.patch.object(
            mod.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 0, failing, ""),
        ):
            with self.assertRaisesRegex(mod.UpgradeError, "not quiescent"):
                mod.require_writer_quiescence()
        with mock.patch.object(
            mod.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 1, "", ""),
        ):
            with self.assertRaisesRegex(mod.UpgradeError, "observation failed"):
                mod.require_writer_quiescence()

    def test_quiescence_loss_after_all_three_staged_preserves_evidence(self):
        checks = 0

        def disappears():
            nonlocal checks
            checks += 1
            return checks < 3

        with self.assertRaisesRegex(mod.UpgradeError, "quiescence"):
            self.run_op(apply=True, probe=disappears)
        self.assertEqual(checks, 3)
        self.assertTrue(all(path.exists() for path in self.stages()))
        self.assertEqual(self.paths.generator.read_bytes(), self.old[mod.GENERATOR])
        self.assertEqual(self.paths.ingest.read_bytes(), self.old[mod.INGEST])
        with self.assertRaises(mod.UpgradeError):
            self.run_op(apply=True)

    def test_explicit_enabled_marker_preserved(self):
        self.paths.marker.write_bytes(mod.MARKER_BYTES)
        self.paths.marker.chmod(0o444)
        result = self.run_op(apply=True, marker="enabled")
        self.assertEqual(result["marker"], "enabled")
        self.assertEqual(self.paths.marker.read_bytes(), mod.MARKER_BYTES)
        self.assertEqual(stat.S_IMODE(self.paths.marker.stat().st_mode), 0o444)

    def test_enabled_marker_mismatch_and_tampering_are_fail_closed(self):
        self.paths.marker.write_bytes(mod.MARKER_BYTES)
        self.paths.marker.chmod(0o444)
        with self.assertRaisesRegex(mod.UpgradeError, "expected state mismatch"):
            self.run_op(apply=True, marker="absent")
        self.paths.marker.chmod(0o600)
        self.paths.marker.write_bytes(b"invalid marker\n")
        self.paths.marker.chmod(0o444)
        with self.assertRaisesRegex(mod.UpgradeError, "unsafe post-publish marker"):
            self.run_op(apply=True, marker="enabled")
        self.assertTrue(all(not p.exists() for p in self.stages()))

    def test_modified_candidate_or_old_installed_binary_rejected(self):
        tampered = dict(self.new)
        tampered[mod.INGEST] = b"unsigned new ingester\n"
        with self.assertRaisesRegex(mod.UpgradeError, "candidate source SHA"):
            self.run_op(apply=True, sources=tampered)
        self.paths.ingest.write_bytes(b"unexpected installed ingester\n")
        with self.assertRaisesRegex(mod.UpgradeError, "not the exact old version"):
            self.run_op(apply=True)
        self.assertTrue(all(not p.exists() for p in self.stages()))

    def test_missing_or_drifted_source_reconfirmation_rejected(self):
        with self.assertRaisesRegex(mod.UpgradeError, "confirmation"):
            self.run_op(apply=True, reconfirm=lambda: {})
        with self.assertRaisesRegex(mod.UpgradeError, "confirmation"):
            mod.execute(
                self.paths, self.new, root_uid=self.uid, root_gid=self.gid,
                owner_uid=self.uid, owner_gid=self.gid,
                apply=True, expected_marker="absent",
                quiescence=lambda: True,
            )
        self.assertTrue(all(not p.exists() for p in self.stages()))

    def test_existing_stage_including_ingester_never_cleaned(self):
        self.paths.ingest_stage.write_bytes(b"orphan\n")
        with self.assertRaisesRegex(mod.UpgradeError, "preexisting stage"):
            self.run_op(apply=True)
        self.assertEqual(self.paths.ingest_stage.read_bytes(), b"orphan\n")

    def test_shared_lock_contention_rejected_without_staging(self):
        fd = os.open(self.lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(mod.UpgradeError, "shared lock busy"):
                self.run_op(apply=True)
        finally:
            os.close(fd)
        self.assertTrue(all(not p.exists() for p in self.stages()))

    def test_failure_after_second_stage_preserves_two_stages(self):
        real_stage = mod.stage

        def fail_ingest_stage(path, contents, mode, *, uid, gid):
            if path == self.paths.ingest_stage:
                raise OSError("injected staging failure")
            return real_stage(path, contents, mode, uid=uid, gid=gid)

        with mock.patch.object(mod, "stage", side_effect=fail_ingest_stage):
            with self.assertRaises(OSError):
                self.run_op(apply=True)
        self.assertTrue(self.paths.generator_stage.exists())
        self.assertTrue(self.paths.operator_stage.exists())
        self.assertFalse(self.paths.ingest_stage.exists())
        self.assertEqual(self.paths.generator.read_bytes(), self.old[mod.GENERATOR])

    def test_failure_between_publisher_and_ingester_keeps_mixed_state(self):
        real_replace = mod.os.replace

        def fail_on_ingest(source, target):
            if target == self.paths.ingest:
                raise OSError("injected failure before ingester replacement")
            return real_replace(source, target)

        with mock.patch.object(mod.os, "replace", side_effect=fail_on_ingest):
            with self.assertRaises(OSError):
                self.run_op(apply=True)
        self.assertEqual(self.paths.generator.read_bytes(), self.new[mod.GENERATOR])
        self.assertEqual(self.paths.operator.read_bytes(), self.new[mod.OPERATOR])
        self.assertEqual(self.paths.ingest.read_bytes(), self.old[mod.INGEST])
        self.assertTrue(self.paths.ingest_stage.exists())
        with self.assertRaises(mod.UpgradeError):
            self.run_op(apply=True)

    def test_symlink_and_mode_drift_rejected(self):
        self.paths.ingest.unlink()
        self.paths.ingest.symlink_to(self.paths.operator)
        with self.assertRaises(mod.UpgradeError):
            self.run_op(apply=True)
        self.assertTrue(all(not p.exists() for p in self.stages()))

    def test_no_host_controls_or_implicit_retry(self):
        source = SCRIPT.read_text()
        self.assertIn('Path("/usr/local/bin")', source)
        self.assertIn('Path("/usr/local/share/coloring-pages")', source)
        self.assertIn('Path("/srv/coloring-pages-content/state/drive-ingest/.lock")', source)
        self.assertIn('parser.add_argument("--expected-marker-state"', source)
        self.assertNotIn("os.remove(", source)
        self.assertNotIn("marker.unlink(", source)
        self.assertNotIn("marker.write_bytes(", source)
        self.assertNotIn('"/usr/bin/systemctl", "stop"', source)
        self.assertNotIn('"/usr/bin/systemctl", "restart"', source)


if __name__ == "__main__":
    unittest.main()
