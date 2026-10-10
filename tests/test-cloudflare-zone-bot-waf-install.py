#!/usr/bin/env python3
"""Offline regression gates for dedicated, source-only zone bot WAF installer."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-cloudflare-zone-bot-waf.py"
OPERATOR = ROOT / "scripts/cloudflare_zone_bot_waf.py"
spec = importlib.util.spec_from_file_location("zone_waf_installer", INSTALLER)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SHA = "a" * 40


class FakeRunner:
    def __init__(self, *, branch="main", dirty=False, existing=False, fail_dispatch=False):
        self.calls = []
        self.branch = branch
        self.dirty = dirty
        self.existing = existing
        self.fail_dispatch = fail_dispatch

    def __call__(self, argv, *, input=None, stdout=None, stderr=None, check=False):
        self.calls.append((list(argv), input))
        args = list(argv)
        output = b""
        status = 0
        if args[:3] == [mod.GIT, "-C", str(mod.ROOT)]:
            suffix = args[3:]
            if suffix == ["rev-parse", "--show-toplevel"]:
                output = (str(mod.ROOT) + "\n").encode()
            elif suffix == ["rev-parse", "HEAD"]:
                output = (SHA + "\n").encode()
            elif suffix == ["branch", "--show-current"]:
                output = (self.branch + "\n").encode()
            elif suffix[:2] == ["status", "--porcelain=v1"]:
                output = b" M scripts/cloudflare_zone_bot_waf.py\n" if self.dirty else b""
            elif suffix == ["remote", "get-url", "origin"]:
                output = b"https://github.com/rozkalnsandris/RPi5_main.git\n"
            elif suffix == ["ls-files", "--error-unmatch", mod.SOURCE_REL]:
                output = (mod.SOURCE_REL + "\n").encode()
            else:
                status = 3
        elif args[:3] == [mod.SUDO, "-n", "/usr/bin/test"]:
            status = 0 if self.existing else 1
        elif args[:4] == [mod.SUDO, "-n", mod.PYTHON, "-c"]:
            status = 51 if self.fail_dispatch else 0
            output = b'{"status":"installed","files_verified":2}' if not self.fail_dispatch else b""
        return subprocess.CompletedProcess(args, status, stdout=output, stderr=b"")


class InstallerTests(unittest.TestCase):
    def test_source_path_and_metadata(self):
        self.assertEqual(mod.SOURCE, OPERATOR)
        source = b"simple operator bytes"
        obj = json.loads(mod.metadata_for(SHA, source))
        self.assertEqual(obj["source_sha"], SHA)
        self.assertEqual(obj["operator_sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(set(obj), {"source_sha", "operator_sha256"})

    def test_root_must_not_execute_checkout_installer(self):
        with mock.patch.object(mod.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(mod.InstallError, "installer_must_not_run_as_root"):
                mod.checked_source(SHA, runner=FakeRunner())

    def test_preflight_clean_main_and_exact_targets(self):
        runner = FakeRunner()
        with mock.patch.object(mod.os, "geteuid", return_value=1000):
            data, metadata = mod.preflight(SHA, runner=runner)
        self.assertEqual(data, OPERATOR.read_bytes())
        self.assertEqual(json.loads(metadata)["source_sha"], SHA)
        probes = [argv for argv, _ in runner.calls if argv[:3] == [mod.SUDO, "-n", "/usr/bin/test"]]
        self.assertEqual(len(probes), 6)
        self.assertEqual(set(x[-1] for x in probes), {mod.INSTALLED, mod.RELEASE_DIR, mod.RELEASE})
        self.assertEqual(set(x[-2] for x in probes), {"-e", "-L"})

    def test_drift_dirty_or_existing_paths_block_before_write(self):
        for runner in (FakeRunner(branch="other"), FakeRunner(dirty=True), FakeRunner(existing=True)):
            with mock.patch.object(mod.os, "geteuid", return_value=1000):
                with self.assertRaises(mod.InstallError):
                    mod.preflight(SHA, runner=runner)
            self.assertFalse(any(argv[:4] == [mod.SUDO, "-n", mod.PYTHON, "-c"]
                                 for argv, _ in runner.calls))

    def test_single_root_dispatch_exact_payload_and_no_secret(self):
        runner = FakeRunner()
        with mock.patch.object(mod.os, "geteuid", return_value=1000):
            mod.install(SHA, runner=runner)
        dispatches = [(argv, data) for argv, data in runner.calls
                      if argv[:4] == [mod.SUDO, "-n", mod.PYTHON, "-c"]]
        self.assertEqual(len(dispatches), 1)
        argv, raw = dispatches[0]
        self.assertEqual(argv[4], mod.ROOT_INSTALL_WRITER)
        obj = json.loads(raw)
        self.assertEqual(base64.b64decode(obj["source_b64"], validate=True), OPERATOR.read_bytes())
        self.assertEqual(json.loads(base64.b64decode(obj["metadata_b64"]))["source_sha"], SHA)
        self.assertNotIn(b"api_token", raw)
        self.assertNotIn("os.replace", mod.ROOT_INSTALL_WRITER)
        self.assertNotIn("os.unlink", mod.ROOT_INSTALL_WRITER)
        self.assertIn("os.O_EXCL", mod.ROOT_INSTALL_WRITER)

    def test_failed_root_dispatch_is_stop_without_retry(self):
        runner = FakeRunner(fail_dispatch=True)
        with mock.patch.object(mod.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(mod.InstallError, "post_dispatch_unknown_state"):
                mod.install(SHA, runner=runner)
        dispatches = [argv for argv, _ in runner.calls if argv[:4] == [mod.SUDO, "-n", mod.PYTHON, "-c"]]
        self.assertEqual(len(dispatches), 1)

    def test_provision_source_stays_installed_only_tty_and_exclusive(self):
        source = OPERATOR.read_text("utf-8")
        for fragment in (
            "verified_installed_release(expected_main)",
            'os.open("/dev/tty"',
            "getpass.getpass(",
            "getpass.GetPassWarning",
            "os.O_EXCL | os.O_NOFOLLOW",
            "secret_post_mutation_unknown_state",
            'GET", f"/zones/{zone}"',
            '"PROVISION-ROZKALNS-ZONE-WAF-SECRET"',
        ):
            self.assertIn(fragment, source)
        self.assertNotIn("input(", source)
        self.assertIn("Zone Read + Zone WAF Edit token", source)
        self.assertIn("if args.confirm !=", source)


if __name__ == "__main__":
    unittest.main()
