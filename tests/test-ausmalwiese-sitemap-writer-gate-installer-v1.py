#!/usr/bin/env python3
"""Offline fixture tests for the source-only sitemap writer gate installer."""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install-ausmalwiese-sitemap-writer-gate-v1.py"
loader = importlib.machinery.SourceFileLoader("writer_gate_installer_v1", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
loader.exec_module(mod)


class WriterGateInstallerTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.source = b'#!/usr/bin/env python3\nprint("trusted fixture")\n'
        self.pin = mock.patch.object(mod, "SOURCE_BLOB", mod.git_blob(self.source))
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.bin = self.root / "usr" / "local" / "bin"
        self.bin.mkdir(parents=True)
        for parent in (self.root / "usr", self.root / "usr" / "local", self.bin):
            parent.chmod(0o755)
        self.dest = self.bin / "ausmalwiese-sitemap-writer-gate"
        self.uid = os.getuid()
        self.gid = os.getgid()

    def fixture_preflight(self):
        with mock.patch.object(mod, "require_directory", wraps=mod.require_directory) as dirs:
            mod.preflight(self.dest, self.source, self.uid, self.gid)
            self.assertEqual(dirs.call_count, 3)

    def test_pins_canonical_gate_blob_mode_and_destination(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('SOURCE_REL = "ops/bin/ausmalwiese-sitemap-writer-gate"', text)
        self.assertIn('SOURCE_BLOB = "f189665fa7fbbe18f0b2ef748a7d6f588956fe91"', text)
        self.assertIn('SOURCE_MODE = "100755"', text)
        self.assertIn('DESTINATION = Path("/usr/local/bin/ausmalwiese-sitemap-writer-gate")', text)
        self.assertIn("GIT_OPTIONAL_LOCKS=0", text)
        expected = hashlib.sha1(
            b"blob " + str(len(self.source)).encode() + b"\0" + self.source
        ).hexdigest()
        self.assertEqual(mod.git_blob(self.source), expected)

    def test_check_preflight_is_pure(self):
        self.fixture_preflight()
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.bin.iterdir()), [])

    def test_installs_exact_bytes_root_owned_executable_mode(self):
        old = os.umask(0o077)
        try:
            mod.install_once(self.dest, self.source, self.uid, self.gid)
        finally:
            os.umask(old)
        self.assertEqual(self.dest.read_bytes(), self.source)
        info = self.dest.lstat()
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o755)
        self.assertEqual((info.st_uid, info.st_gid), (self.uid, self.gid))
        self.assertFalse(self.dest.is_symlink())

    def test_existing_file_or_symlink_is_never_overwritten(self):
        self.dest.write_bytes(b"older")
        with self.assertRaisesRegex(mod.Stop, "destination exists"):
            mod.install_once(self.dest, self.source, self.uid, self.gid)
        self.assertEqual(self.dest.read_bytes(), b"older")
        self.dest.unlink()
        other = self.root / "other"
        other.write_bytes(b"other")
        self.dest.symlink_to(other)
        with self.assertRaises(mod.Stop):
            mod.preflight(self.dest, self.source, self.uid, self.gid)
        self.assertEqual(other.read_bytes(), b"other")

    def test_parent_symlink_or_wrong_mode_blocks(self):
        self.bin.chmod(0o775)
        with self.assertRaisesRegex(mod.Stop, "directory identity mismatch"):
            mod.preflight(self.dest, self.source, self.uid, self.gid)
        self.bin.chmod(0o755)
        self.bin.rmdir()
        other = self.root / "other-dir"
        other.mkdir()
        self.bin.symlink_to(other)
        with self.assertRaises(mod.Stop):
            mod.preflight(self.dest, self.source, self.uid, self.gid)
        self.assertEqual(list(other.iterdir()), [])

    def test_pin_mismatch_blocks_before_creation(self):
        with self.assertRaisesRegex(mod.Stop, "source bytes changed"):
            mod.install_once(
                self.dest, self.source + b"tampered", self.uid, self.gid
            )
        self.assertFalse(self.dest.exists())

    def test_failure_after_first_mutation_preserves_partial(self):
        with mock.patch.object(mod.os, "fchmod", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                mod.install_once(self.dest, self.source, self.uid, self.gid)
        self.assertTrue(self.dest.exists())
        self.assertEqual(self.dest.read_bytes(), self.source)
        with self.assertRaisesRegex(mod.Stop, "destination exists"):
            mod.install_once(self.dest, self.source, self.uid, self.gid)

    def test_expected_main_sha_validation_fails_early(self):
        with self.assertRaisesRegex(mod.Stop, "expected full main SHA"):
            mod.trusted_source("short", 123, 123)

    def test_source_checkout_ref_mode_blob_dirty_and_head_guard(self):
        good = "6d744cef8ad0b0b77fb7253cd1ca501920e25445"
        lookups = {
            ("rev-parse", "--verify", "HEAD"): (good + "\n").encode(),
            ("branch", "--show-current"): b"main\n",
            ("status", "--porcelain=v1", "--untracked-files=all"): b"",
            ("ls-tree", "HEAD", "--", mod.SOURCE_REL):
                f"{mod.SOURCE_MODE} blob {mod.SOURCE_BLOB}\t{mod.SOURCE_REL}\n".encode(),
            ("show", "HEAD:" + mod.SOURCE_REL): self.source,
        }

        def lookup(*parts):
            return lookups[tuple(parts)]

        with mock.patch.object(mod, "require_directory"), \
                mock.patch.object(mod, "owner_git", side_effect=lookup):
            self.assertEqual(mod.trusted_source(good, 1000, 1000), self.source)
            cases = [
                (("rev-parse", "--verify", "HEAD"), b"0" * 40 + b"\n"),
                (("branch", "--show-current"), b"feature\n"),
                (("status", "--porcelain=v1", "--untracked-files=all"), b"?? x\n"),
                (("ls-tree", "HEAD", "--", mod.SOURCE_REL),
                 b"100644 blob " + mod.SOURCE_BLOB.encode() + b"\t" + mod.SOURCE_REL.encode() + b"\n"),
                (("show", "HEAD:" + mod.SOURCE_REL), b"changed"),
            ]
            for key, wrong in cases:
                old = lookups[key]
                lookups[key] = wrong
                with self.subTest(key=key), self.assertRaises(mod.Stop):
                    mod.trusted_source(good, 1000, 1000)
                lookups[key] = old

    def test_owner_git_is_sandboxed_and_hook_free(self):
        fake = subprocess.CompletedProcess([], 0, b"ok", b"")
        with mock.patch.object(mod.subprocess, "run", return_value=fake) as run:
            self.assertEqual(mod.owner_git("rev-parse", "HEAD"), b"ok")
        argv = run.call_args.args[0]
        self.assertIn("GIT_OPTIONAL_LOCKS=0", argv)
        self.assertIn("GIT_CONFIG_GLOBAL=/dev/null", argv)
        self.assertIn("core.hooksPath=/dev/null", argv)
        self.assertEqual(argv[-2:], ["rev-parse", "HEAD"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_cli_requires_root_and_mutually_exclusive_mode(self):
        good = "6d744cef8ad0b0b77fb7253cd1ca501920e25445"
        with mock.patch.object(mod.os, "geteuid", return_value=1000):
            self.assertEqual(
                mod.main(["--check", "--expected-rpi5-main-sha", good]), 2
            )
        with mock.patch.object(mod.os, "getuid", return_value=1000):
            self.assertEqual(
                mod.main(["--apply", "--expected-rpi5-main-sha", good]), 2
            )
        with self.assertRaises(SystemExit):
            mod.main(["--apply", "--check", "--expected-rpi5-main-sha", good])
        with self.assertRaises(SystemExit):
            mod.main(["--apply"])


if __name__ == "__main__":
    unittest.main()
