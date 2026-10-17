#!/usr/bin/env python3
"""Purely offline, isolated fixture tests for the source-only installer."""
from __future__ import annotations

from contextlib import ExitStack
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

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install-ausmalwiese-catalog-hide-v1.py'
loader = importlib.machinery.SourceFileLoader('hide_installer_v1', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
loader.exec_module(mod)


class PinnedInstallerTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.src = b'#!/usr/bin/env python3\nprint("trusted fixture")\n'
        self.pin = mock.patch.object(mod, 'SOURCE_BLOB', mod.git_blob(self.src))
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.bin = self.root / 'usr' / 'local' / 'bin'
        self.bin.mkdir(parents=True)
        for parent in [self.root / 'usr', self.root / 'usr' / 'local', self.bin]:
            parent.chmod(0o755)
        self.dest = self.bin / 'ausmalwiese-catalog-hide'
        self.uid = os.getuid()
        self.gid = os.getgid()

    def fixture_preflight(self):
        # /tmp/<fixture>/usr: the root sandbox parent is not a tested LIVE path.
        with mock.patch.object(mod, 'require_directory', wraps=mod.require_directory) as dirs:
            mod.preflight(self.dest, self.src, self.uid, self.gid)
            self.assertEqual(dirs.call_count, 3)

    def test_pinned_canonical_blob_and_fixed_target(self):
        # The true constant is checked before fixture patching via raw file text.
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('SOURCE_BLOB = "a07d95fe78f34b5fc90eaf2eb202eb3a4815259c"', text)
        self.assertIn('SOURCE_MODE = "100755"', text)
        self.assertIn('DESTINATION = Path("/usr/local/bin/ausmalwiese-catalog-hide")', text)
        self.assertIn('GIT_OPTIONAL_LOCKS=0', text)
        self.assertEqual(mod.git_blob(self.src), hashlib.sha1(b'blob '+str(len(self.src)).encode()+b'\0'+self.src).hexdigest())

    def test_check_preflight_is_pure(self):
        self.fixture_preflight()
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.bin.iterdir()), [])

    def test_installs_exact_bytes_root_owned_mode_with_umask(self):
        old = os.umask(0o077)
        try:
            mod.install_once(self.dest, self.src, self.uid, self.gid)
        finally:
            os.umask(old)
        self.assertEqual(self.dest.read_bytes(), self.src)
        z = self.dest.lstat()
        self.assertEqual(stat.S_IMODE(z.st_mode), 0o755)
        self.assertEqual((z.st_uid, z.st_gid), (self.uid, self.gid))
        self.assertFalse(self.dest.is_symlink())

    def test_existing_file_and_symlink_never_overwritten(self):
        self.dest.write_bytes(b'older')
        with self.assertRaisesRegex(mod.Stop, 'destination exists'):
            mod.install_once(self.dest, self.src, self.uid, self.gid)
        self.assertEqual(self.dest.read_bytes(), b'older')
        self.dest.unlink()
        other = self.root / 'elsewhere'
        other.write_bytes(b'other')
        self.dest.symlink_to(other)
        with self.assertRaises(mod.Stop):
            mod.preflight(self.dest, self.src, self.uid, self.gid)
        self.assertEqual(other.read_bytes(), b'other')

    def test_parent_symlink_and_wrong_mode_block(self):
        self.bin.chmod(0o775)
        with self.assertRaisesRegex(mod.Stop, 'directory identity mismatch'):
            mod.preflight(self.dest, self.src, self.uid, self.gid)
        self.bin.chmod(0o755)
        self.bin.rmdir()
        other = self.root / 'other_dir'
        other.mkdir()
        self.bin.symlink_to(other)
        with self.assertRaises(mod.Stop):
            mod.preflight(self.dest, self.src, self.uid, self.gid)
        self.assertEqual(list(other.iterdir()), [])

    def test_pin_mismatch_fails_before_creation(self):
        with self.assertRaisesRegex(mod.Stop, 'source bytes changed'):
            mod.install_once(self.dest, self.src+b' tampered', self.uid, self.gid)
        self.assertFalse(self.dest.exists())

    def test_failure_after_first_mutation_preserves_partial_without_cleanup(self):
        with mock.patch.object(mod.os, 'fchmod', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                mod.install_once(self.dest, self.src, self.uid, self.gid)
        self.assertTrue(self.dest.exists())
        self.assertEqual(self.dest.read_bytes(), self.src)
        self.assertNotEqual(stat.S_IMODE(self.dest.stat().st_mode), 0o755)
        with self.assertRaisesRegex(mod.Stop, 'destination exists'):
            mod.install_once(self.dest, self.src, self.uid, self.gid)

    def test_expected_main_sha_validation_fails_early(self):
        with self.assertRaisesRegex(mod.Stop, 'expected full main SHA'):
            mod.trusted_source('short', 123, 123)

    def test_source_checkout_ref_mode_blob_dirty_and_head_guard(self):
        good = '6d744cef8ad0b0b77fb7253cd1ca501920e25445'
        blobs = {
            ('rev-parse','--verify','HEAD'): (good+'\n').encode(),
            ('branch','--show-current'): b'main\n',
            ('status','--porcelain=v1','--untracked-files=all'): b'',
            ('ls-tree','HEAD','--',mod.SOURCE_REL): f'{mod.SOURCE_MODE} blob {mod.SOURCE_BLOB}\t{mod.SOURCE_REL}\n'.encode(),
            ('show','HEAD:'+mod.SOURCE_REL): self.src,
        }
        def lookup(*parts):
            return blobs[tuple(parts)]
        with mock.patch.object(mod, 'require_directory'), mock.patch.object(mod, 'owner_git', side_effect=lookup):
            self.assertEqual(mod.trusted_source(good, 1000, 1000), self.src)
            for key, wrong, message in [
                (('rev-parse','--verify','HEAD'), b'0'*40+b'\n', 'checkout'),
                (('branch','--show-current'), b'feature\n', 'checkout'),
                (('status','--porcelain=v1','--untracked-files=all'), b'?? unknown\n', 'checkout'),
                (('ls-tree','HEAD','--',mod.SOURCE_REL), b'100644 blob '+mod.SOURCE_BLOB.encode()+b'\t'+mod.SOURCE_REL.encode()+b'\n', 'mode'),
                (('show','HEAD:'+mod.SOURCE_REL), b'changed', 'byte')]:
                old=blobs[key]
                blobs[key]=wrong
                with self.subTest(key=key), self.assertRaises(mod.Stop):
                    mod.trusted_source(good, 1000, 1000)
                blobs[key]=old

    def test_sandboxed_owner_git_does_not_run_hooks_or_inherit_env(self):
        fake = subprocess.CompletedProcess([], 0, b'ok', b'')
        with mock.patch.object(mod.subprocess, 'run', return_value=fake) as run:
            self.assertEqual(mod.owner_git('rev-parse','HEAD'), b'ok')
        argv = run.call_args.args[0]
        self.assertIn('GIT_OPTIONAL_LOCKS=0', argv)
        self.assertIn('GIT_CONFIG_GLOBAL=/dev/null', argv)
        self.assertIn('core.hooksPath=/dev/null', argv)
        self.assertEqual(argv[-2:], ['rev-parse', 'HEAD'])
        self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)

    def test_cli_requires_root_and_exact_mode(self):
        good = '6d744cef8ad0b0b77fb7253cd1ca501920e25445'
        with mock.patch.object(mod.os, 'geteuid', return_value=1000):
            self.assertEqual(mod.main(['--check','--expected-rpi5-main-sha',good]), 2)
        with mock.patch.object(mod.os, 'getuid', return_value=1000):
            self.assertEqual(mod.main(['--apply','--expected-rpi5-main-sha',good]), 2)
        with self.assertRaises(SystemExit):
            mod.main(['--apply','--check','--expected-rpi5-main-sha',good])
        with self.assertRaises(SystemExit):
            mod.main(['--apply'])


if __name__ == '__main__':
    unittest.main()
