#!/usr/bin/env python3
"""Offline regression tests for the first-install-only Coloring Pages sitemap installer."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-coloring-pages-sitemap-publisher-v1.py"
OPERATOR = ROOT / "ops/bin/coloring-pages-sitemap-publish"
GENERATOR = ROOT / "ops/vendor/coloring-pages-sitemap"
LOADER = importlib.machinery.SourceFileLoader("coloring_sitemap_installer", str(INSTALLER))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
inst = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
import sys
sys.modules[SPEC.name] = inst
SPEC.loader.exec_module(inst)


class SitemapInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.bin_parent = root / "bin"
        self.share_parent = root / "share"
        self.bin_parent.mkdir()
        self.share_parent.mkdir()
        self.bin_parent.chmod(0o755)
        self.share_parent.chmod(0o755)
        self.paths = inst.Destinations(self.bin_parent, self.share_parent)
        self.uid = os.getuid()
        self.gid = os.getgid()
        self.sources = {
            inst.OPERATOR_REL: OPERATOR.read_bytes(),
            inst.GENERATOR_REL: GENERATOR.read_bytes(),
        }

    def preflight(self):
        return inst.preflight(self.paths, root_uid=self.uid,
                              root_gid=self.gid, sources=self.sources)

    def install(self):
        return inst.install(self.paths, root_uid=self.uid,
                            root_gid=self.gid, sources=self.sources)

    def test_pinned_git_blobs_match_current_source(self):
        for name, expected in inst.EXPECTED_BLOBS.items():
            self.assertEqual(inst.git_blob(self.sources[name]), expected)

    def test_read_only_check_does_not_create_directory_or_files(self):
        self.preflight()
        self.assertFalse(self.paths.vendor_dir.exists())
        self.assertFalse(self.paths.operator.exists())
        self.assertFalse(self.paths.generator.exists())

    def test_first_install_exact_bytes_owner_and_modes(self):
        result = self.install()
        self.assertEqual(result["result"], "INSTALL_PASS")
        self.assertTrue(result["mutation_started"])
        self.assertEqual(self.paths.generator.read_bytes(), self.sources[inst.GENERATOR_REL])
        self.assertEqual(self.paths.operator.read_bytes(), self.sources[inst.OPERATOR_REL])
        self.assertEqual(stat.S_IMODE(self.paths.generator.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(self.paths.operator.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.paths.vendor_dir.stat().st_mode), 0o755)
        for p in (self.paths.operator, self.paths.generator, self.paths.vendor_dir):
            self.assertEqual(p.stat().st_uid, self.uid)
            self.assertEqual(p.stat().st_gid, self.gid)

    def test_strict_umask_still_produces_exact_directory_mode(self):
        old = os.umask(0o077)
        try:
            self.install()
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(self.paths.vendor_dir.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.paths.generator.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(self.paths.operator.stat().st_mode), 0o755)

    def test_second_install_is_rejected_with_exact_bytes_untouched(self):
        self.install()
        original = self.paths.operator.read_bytes()
        with self.assertRaisesRegex(inst.InstallerError, "already exists"):
            self.install()
        self.assertEqual(self.paths.operator.read_bytes(), original)

    def test_existing_vendor_dir_is_rejected_even_when_empty(self):
        self.paths.vendor_dir.mkdir()
        with self.assertRaisesRegex(inst.InstallerError, "already exists"):
            self.preflight()
        self.assertFalse(self.paths.operator.exists())

    def test_existing_operator_is_never_overwritten(self):
        self.paths.operator.write_bytes(b"trusted existing application")
        with self.assertRaisesRegex(inst.InstallerError, "already exists"):
            self.install()
        self.assertEqual(self.paths.operator.read_bytes(), b"trusted existing application")
        self.assertFalse(self.paths.vendor_dir.exists())

    def test_symlink_target_rejected(self):
        other = self.share_parent / "elsewhere"
        other.mkdir()
        self.paths.vendor_dir.symlink_to(other)
        with self.assertRaisesRegex(inst.InstallerError, "already exists"):
            self.preflight()
        self.assertFalse(self.paths.operator.exists())

    def test_bad_parent_metadata_rejected_without_write(self):
        self.share_parent.chmod(0o777)
        with self.assertRaisesRegex(inst.InstallerError, "identity invalid"):
            self.install()
        self.assertFalse(self.paths.vendor_dir.exists())

    def test_parent_symlink_rejected(self):
        external = Path(self.temp.name) / "external"
        external.mkdir()
        shutil.rmtree(self.share_parent)
        self.share_parent.symlink_to(external)
        with self.assertRaisesRegex(inst.InstallerError, "identity invalid"):
            self.preflight()

    def test_wrong_source_blob_rejected_before_any_mutation(self):
        self.sources[inst.OPERATOR_REL] += b"\n# tampered"
        with self.assertRaisesRegex(inst.InstallerError, "pinned blob"):
            self.install()
        self.assertFalse(self.paths.vendor_dir.exists())

    def test_missing_source_snapshot_rejected_before_mutation(self):
        del self.sources[inst.GENERATOR_REL]
        with self.assertRaisesRegex(inst.InstallerError, "pinned blob"):
            self.install()
        self.assertFalse(self.paths.vendor_dir.exists())

    def test_failure_after_generator_creation_keeps_partial_state(self):
        original = inst.secure_create
        def fail_second(path, content, mode, *, root_uid, root_gid):
            if path == self.paths.operator:
                raise OSError("simulated post-mutation failure")
            return original(path, content, mode, root_uid=root_uid, root_gid=root_gid)
        with mock.patch.object(inst, "secure_create", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.install()
        self.assertTrue(self.paths.generator.exists())
        self.assertFalse(self.paths.operator.exists())
        with self.assertRaisesRegex(inst.InstallerError, "already exists"):
            self.install()
        self.assertTrue(self.paths.generator.exists())

    def test_error_after_directory_creation_does_not_remove_directory(self):
        with mock.patch.object(inst, "secure_create", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                self.install()
        self.assertTrue(self.paths.vendor_dir.is_dir())
        self.assertFalse(self.paths.operator.exists())

    def test_git_revision_and_branch_guard(self):
        expected_sha = "a" * 40
        def git(*args):
            if args == ("rev-parse", "HEAD"):
                return (expected_sha + "\n").encode()
            if args == ("branch", "--show-current"):
                return b"main\n"
            if args == ("status", "--porcelain=v1", "--untracked-files=all"):
                return b""
            if args[0] == "ls-tree":
                file = args[-1]
                return ("100644 blob " + inst.EXPECTED_BLOBS[file] + "\t" + file + "\n").encode()
            if args[0] == "show":
                return self.sources[args[1].split(":", 1)[1]]
            raise AssertionError(args)
        with mock.patch.object(inst, "require_directory"):
            with mock.patch.object(inst, "fetch_owner_git", side_effect=git):
                self.assertEqual(
                    inst.source_snapshot(expected_sha, owner_uid=self.uid,
                                         owner_gid=self.gid), self.sources
                )
                with self.assertRaisesRegex(inst.InstallerError, "exact lowercase"):
                    inst.source_snapshot("not-a-sha", owner_uid=self.uid,
                                         owner_gid=self.gid)
        with mock.patch.object(inst, "require_directory"):
            with mock.patch.object(inst, "fetch_owner_git",
                                   side_effect=lambda *a: b"topic-branch\n" if
                                   a == ("branch", "--show-current") else git(*a)):
                with self.assertRaisesRegex(inst.InstallerError, "checkout"):
                    inst.source_snapshot(expected_sha, owner_uid=self.uid,
                                         owner_gid=self.gid)
            with mock.patch.object(inst, "fetch_owner_git",
                                   side_effect=lambda *a: b" M ops/bin/file\n" if
                                   a == ("status", "--porcelain=v1", "--untracked-files=all")
                                   else git(*a)):
                with self.assertRaisesRegex(inst.InstallerError, "checkout"):
                    inst.source_snapshot(expected_sha, owner_uid=self.uid,
                                         owner_gid=self.gid)
            with mock.patch.object(inst, "fetch_owner_git",
                                   side_effect=lambda *a: b"b" * 40 + b"\n" if
                                   a == ("rev-parse", "HEAD") else git(*a)):
                with self.assertRaisesRegex(inst.InstallerError, "checkout"):
                    inst.source_snapshot(expected_sha, owner_uid=self.uid,
                                         owner_gid=self.gid)

    def test_pinned_checkout_blob_mode_rejects_symlink_source(self):
        expected_sha = "b" * 40
        def git(*args):
            if args == ("rev-parse", "HEAD"):
                return (expected_sha + "\n").encode()
            if args == ("branch", "--show-current"):
                return b"main\n"
            if args == ("status", "--porcelain=v1", "--untracked-files=all"):
                return b""
            if args[0] == "ls-tree":
                file = args[-1]
                return ("120000 blob " + inst.EXPECTED_BLOBS[file] + "\t" + file + "\n").encode()
            raise AssertionError(args)
        with mock.patch.object(inst, "require_directory"):
            with mock.patch.object(inst, "fetch_owner_git", side_effect=git):
                with self.assertRaisesRegex(inst.InstallerError, "tracked source blob/mode"):
                    inst.source_snapshot(expected_sha, owner_uid=self.uid,
                                         owner_gid=self.gid)


if __name__ == "__main__":
    unittest.main()
