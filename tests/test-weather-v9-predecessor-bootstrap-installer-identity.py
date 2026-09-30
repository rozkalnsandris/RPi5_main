#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-weather-v9-predecessor-bootstrap-capability.py"

def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

installer = load(INSTALLER, "weather_v9_predecessor_bootstrap_installer_identity_test")

class Tests(unittest.TestCase):
    def setUp(self):
        self.original_run = installer.subprocess.run
        self.original_geteuid = installer.os.geteuid
        self.original_getegid = installer.os.getegid

    def tearDown(self):
        installer.subprocess.run = self.original_run
        installer.os.geteuid = self.original_geteuid
        installer.os.getegid = self.original_getegid

    def _capture(self):
        calls = []
        def fake(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout="a" * 40 + "\n", stderr="")
        installer.subprocess.run = fake
        return calls

    def test_same_manager_nonroot_does_not_rebind_credentials(self):
        calls = self._capture()
        installer.os.geteuid = lambda: 1000
        installer.os.getegid = lambda: 1000
        installer._git(1000, 1000, "rev-parse", "HEAD")
        _argv, kwargs = calls[0]
        self.assertNotIn("user", kwargs)
        self.assertNotIn("group", kwargs)
        self.assertNotIn("extra_groups", kwargs)
        self.assertIs(kwargs["shell"], False)

    def test_root_still_drops_to_manager_identity(self):
        calls = self._capture()
        installer.os.geteuid = lambda: 0
        installer.os.getegid = lambda: 0
        installer._git(1000, 1000, "rev-parse", "HEAD")
        _argv, kwargs = calls[0]
        self.assertEqual(kwargs["user"], 1000)
        self.assertEqual(kwargs["group"], 1000)
        self.assertEqual(kwargs["extra_groups"], ())
        self.assertIs(kwargs["shell"], False)

    def test_mismatched_nonroot_identity_fails_before_git(self):
        calls = self._capture()
        installer.os.geteuid = lambda: 1001
        installer.os.getegid = lambda: 1001
        with self.assertRaises(installer.InstallError):
            installer._git(1000, 1000, "rev-parse", "HEAD")
        self.assertEqual(calls, [])

    def test_spawn_oserror_is_bounded_installer_failure(self):
        installer.os.geteuid = lambda: 1000
        installer.os.getegid = lambda: 1000
        def denied(_argv, **_kwargs):
            raise PermissionError(1, "Operation not permitted")
        installer.subprocess.run = denied
        with self.assertRaisesRegex(installer.InstallError, "installer source Git preflight failed"):
            installer._git(1000, 1000, "rev-parse", "HEAD")

if __name__ == "__main__":
    unittest.main()
