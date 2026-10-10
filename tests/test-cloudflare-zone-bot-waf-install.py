#!/usr/bin/env python3
"""Offline regressions for source-only, coreutils-only zone bot WAF installer."""
from __future__ import annotations

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
    def __init__(self, *, branch="main", dirty=False, existing=False,
                 bad_parent=False, fail_write_at=0, fail_verify=False):
        self.calls: list[tuple[list[str], bytes | None]] = []
        self.branch = branch
        self.dirty = dirty
        self.existing = existing
        self.bad_parent = bad_parent
        self.fail_write_at = fail_write_at
        self.fail_verify = fail_verify
        self.writes = 0
        self.operator = OPERATOR.read_bytes()

    def __call__(self, argv, *, input=None, stdout=None, stderr=None, check=False):
        self.calls.append((list(argv), input))
        args = list(argv)
        output = b""
        rc = 0
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
                rc = 3
        elif args[:3] == [mod.SUDO, "-n", mod.STAT]:
            path = args[-1]
            if path in mod.PARENTS:
                output = b"0:0:777:directory" if self.bad_parent else b"0:0:755:directory"
            elif path == mod.RELEASE_DIR:
                output = b"0:0:700:directory"
            elif path == mod.INSTALLED:
                output = b"0:0:500:regular file"
            elif path == mod.RELEASE:
                output = b"0:0:400:regular file"
        elif args[:3] == [mod.SUDO, "-n", mod.TEST]:
            rc = 0 if self.existing else 1
        elif args[:3] == [mod.SUDO, "-n", mod.SHA256SUM]:
            path = args[-1]
            digest = hashlib.sha256(
                self.operator if path == mod.INSTALLED else mod.metadata_for(SHA, self.operator)
            ).hexdigest()
            if self.fail_verify:
                digest = "b" * 64
            output = f"{digest}  {path}\n".encode()
        elif args[:3] == [mod.SUDO, "-n", mod.MKDIR] or args[:3] == [mod.SUDO, "-n", mod.INSTALL]:
            self.writes += 1
            if self.writes == self.fail_write_at:
                rc = 42
        return subprocess.CompletedProcess(args, rc, stdout=output, stderr=b"")


class InstallerTests(unittest.TestCase):
    def test_source_path_and_pinned_release_metadata(self):
        self.assertEqual(mod.SOURCE, OPERATOR)
        obj = json.loads(mod.metadata_for(SHA, b"operator source bytes"))
        self.assertEqual(obj["source_sha"], SHA)
        self.assertEqual(obj["operator_sha256"], hashlib.sha256(b"operator source bytes").hexdigest())
        self.assertEqual(set(obj), {"source_sha", "operator_sha256"})

    def test_root_must_not_execute_checkout_installer(self):
        with mock.patch.object(mod.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(mod.InstallError, "installer_must_not_run_as_root"):
                mod.checked_source(SHA, runner=FakeRunner())

    def test_clean_main_and_root_parent_and_target_preflight(self):
        runner = FakeRunner()
        with mock.patch.object(mod.os, "geteuid", return_value=1000):
            source, metadata = mod.preflight(SHA, runner=runner)
        self.assertEqual(source, OPERATOR.read_bytes())
        self.assertEqual(json.loads(metadata)["source_sha"], SHA)
        targets = [args for args, _ in runner.calls if args[:3] == [mod.SUDO, "-n", mod.TEST]]
        self.assertEqual(len(targets), 6)
        self.assertEqual(set(x[-1] for x in targets), {mod.INSTALLED, mod.RELEASE_DIR, mod.RELEASE})
        self.assertEqual(set(x[-2] for x in targets), {"-e", "-L"})
        parent_checks = [args[-1] for args, _ in runner.calls
                         if args[:3] == [mod.SUDO, "-n", mod.STAT]]
        self.assertEqual(parent_checks, list(mod.PARENTS))

    def test_branch_dirty_parent_or_existing_target_block_all_writes(self):
        for r in (FakeRunner(branch="other"), FakeRunner(dirty=True),
                  FakeRunner(existing=True), FakeRunner(bad_parent=True)):
            with self.subTest(branch=r.branch, dirty=r.dirty,
                              existing=r.existing, unsafe=r.bad_parent):
                with mock.patch.object(mod.os, "geteuid", return_value=1000):
                    with self.assertRaises(mod.InstallError):
                        mod.preflight(SHA, runner=r)
                self.assertEqual(r.writes, 0)

    def test_success_uses_fixed_coreutils_and_captured_stdin_exactly(self):
        runner = FakeRunner()
        with mock.patch.object(mod.os, "geteuid", return_value=1000):
            mod.install(SHA, runner=runner)
        writes = [(argv, payload) for argv, payload in runner.calls
                  if tuple(argv[:3]) in ((mod.SUDO, "-n", mod.MKDIR),
                                          (mod.SUDO, "-n", mod.INSTALL))]
        self.assertEqual(len(writes), 3)
        self.assertEqual(writes[0], ([mod.SUDO, "-n", mod.MKDIR, "-m", "0700",
                                     "--", mod.RELEASE_DIR], None))
        self.assertEqual(writes[1][0], [mod.SUDO, "-n", mod.INSTALL, "-T", "-o",
                                         "root", "-g", "root", "-m", "0500",
                                         "--", "/dev/stdin", mod.INSTALLED])
        self.assertEqual(writes[1][1], OPERATOR.read_bytes())
        self.assertEqual(writes[2][0], [mod.SUDO, "-n", mod.INSTALL, "-T", "-o",
                                         "root", "-g", "root", "-m", "0400",
                                         "--", "/dev/stdin", mod.RELEASE])
        self.assertEqual(writes[2][1], mod.metadata_for(SHA, OPERATOR.read_bytes()))
        self.assertNotIn(b"api_token", writes[1][1] + writes[2][1])
        self.assertEqual(runner.writes, 3)
        for argv, _ in runner.calls:
            self.assertNotIn("python3", " ".join(argv))
            self.assertNotIn("-c", argv)
        self.assertNotIn("shell=True", INSTALLER.read_text())

    def test_each_root_write_failure_is_final_no_retry_or_cleanup(self):
        for position in (1, 2, 3):
            with self.subTest(position=position):
                runner = FakeRunner(fail_write_at=position)
                with mock.patch.object(mod.os, "geteuid", return_value=1000):
                    with self.assertRaisesRegex(mod.InstallError, "post_dispatch_unknown_state"):
                        mod.install(SHA, runner=runner)
                self.assertEqual(runner.writes, position)
                self.assertFalse(any("rm" in argv or "rmdir" in argv
                                     for argv, _ in runner.calls))

    def test_post_write_digest_mismatch_requires_stop(self):
        runner = FakeRunner(fail_verify=True)
        with mock.patch.object(mod.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(mod.InstallError, "post_dispatch_unknown_state"):
                mod.install(SHA, runner=runner)
        self.assertEqual(runner.writes, 3)

    def test_missing_authorization_confirms_before_root_mutation(self):
        runner = FakeRunner()
        with mock.patch.object(mod.os, "geteuid", return_value=1000), \
             mock.patch.object(mod, "preflight", side_effect=AssertionError("must not call")):
            self.assertEqual(mod.main(["--expected-main", SHA, "--apply"]), 3)
        self.assertEqual(runner.writes, 0)

    def test_future_credential_provisioning_remains_separately_gated(self):
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


if __name__ == "__main__":
    unittest.main()
