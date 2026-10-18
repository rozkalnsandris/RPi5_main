#!/usr/bin/env python3
"""Offline tests for Stats Gate A D1 runtime installer (#996)."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/install-ausmalwiese-stats-gate-a-d1-runtime-v1.py"
RUNTIME = ROOT / "scripts/ausmalwiese_stats_gate_a_d1_runtime_v1.py"
spec = importlib.util.spec_from_file_location("stats_gate_a_installer_996", SOURCE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

HEAD = "a" * 40
PAYLOAD = RUNTIME.read_bytes()


class Runner:
    def __init__(
        self,
        *,
        head=HEAD,
        branch="main",
        dirty=False,
        origin="https://github.com/rozkalnsandris/RPi5_main.git",
        present=False,
        symlink=False,
        cp_version="9.7",
        deny=False,
        fail=False,
        skip=False,
        wrong_blob=False,
        wrong_metadata=False,
        wrong_sha=False,
    ):
        self.head = head
        self.branch = branch
        self.dirty = dirty
        self.origin = origin
        self.present = present
        self.symlink = symlink
        self.cp_version = cp_version
        self.deny = deny
        self.fail = fail
        self.skip = skip
        self.wrong_blob = wrong_blob
        self.wrong_metadata = wrong_metadata
        self.wrong_sha = wrong_sha
        self.calls = []
        self.writes = 0

    def __call__(
        self,
        argv,
        *,
        stdin=None,
        stdout=None,
        stderr=None,
        check=False,
        timeout=None,
        env=None,
    ):
        args = list(argv)
        self.calls.append((args, stdin))
        if env != mod.CLEAN_ENV:
            raise AssertionError("unbounded environment")
        rc, out = 0, b""

        if args[:3] == [mod.GIT, "-C", str(mod.ROOT)]:
            command = args[3:]
            if command == ["rev-parse", "--show-toplevel"]:
                out = (str(mod.ROOT) + "\n").encode()
            elif command == ["symbolic-ref", "--quiet", "--short", "HEAD"]:
                out = (self.branch + "\n").encode()
            elif command == ["rev-parse", "HEAD"]:
                out = (self.head + "\n").encode()
            elif command == [
                "status", "--porcelain=v1", "-z", "--untracked-files=all"
            ]:
                out = b" M x\x00" if self.dirty else b""
            elif command == ["remote", "get-url", "origin"]:
                out = (self.origin + "\n").encode()
            elif command == ["show", "HEAD:" + mod.SOURCE_REL]:
                out = PAYLOAD
            elif command == ["ls-tree", "HEAD", "--", mod.SOURCE_REL]:
                blob = "0" * 40 if self.wrong_blob else mod.SOURCE_BLOB
                out = f"100644 blob {blob}\t{mod.SOURCE_REL}\n".encode()
            else:
                rc = 9

        elif args[:3] == [mod.SUDO, "-n", mod.CP] and args[-1:] == ["--version"]:
            out = f"cp (GNU coreutils) {self.cp_version}\n".encode()

        elif args[:3] == [mod.SUDO, "-n", mod.STAT]:
            if args[-1] in mod.PARENTS:
                out = b"0:0:755:directory\n"
            elif args[-1] == mod.TARGET:
                out = (
                    b"0:0:400:regular file:1\n"
                    if self.wrong_metadata
                    else b"0:0:500:regular file:1\n"
                )
            else:
                rc = 8

        elif args[:3] == [mod.SUDO, "-n", mod.TEST]:
            if args[3] == "-L":
                rc = 0 if self.symlink else 1
            else:
                rc = 0 if self.present else 1

        elif args[:4] == [mod.SUDO, "-n", "-l", "--"]:
            rc = 1 if self.deny else 0

        elif args[:3] == [mod.SUDO, "-n", mod.SHA256SUM]:
            digest = (
                "0" * 64
                if self.wrong_sha
                else hashlib.sha256(PAYLOAD).hexdigest()
            )
            out = (digest + "  " + mod.TARGET + "\n").encode()

        elif args[:3] == [mod.SUDO, "-n", mod.CP]:
            self.writes += 1
            if stdin != 45:
                raise AssertionError("sealed memfd required")
            if self.fail or self.present or self.symlink:
                rc = 1
            elif self.skip:
                out = b""
            elif self.cp_version == "9.1":
                out = ("'/dev/stdin' -> '" + mod.TARGET + "'\n").encode()
        else:
            raise AssertionError(args)

        return subprocess.CompletedProcess(args, rc, stdout=out, stderr=b"safe")


def preflight(runner):
    with mock.patch.object(mod.os, "geteuid", return_value=1000):
        return mod.preflight(HEAD, runner=runner)


class InstallerTests(unittest.TestCase):
    def test_runtime_blob_and_target_are_pinned(self):
        raw = PAYLOAD
        blob = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\x00" + raw
        ).hexdigest()
        self.assertEqual(blob, mod.SOURCE_BLOB)
        self.assertEqual(
            mod.TARGET,
            "/usr/local/sbin/rpi5-ausmalwiese-stats-gate-a-d1-migrate",
        )

    def test_checkout_drift_stops_before_write(self):
        for runner in (
            Runner(branch="feature"),
            Runner(head="b" * 40),
            Runner(dirty=True),
            Runner(origin="https://example.invalid/repo"),
            Runner(wrong_blob=True),
        ):
            with self.subTest(runner=runner):
                with self.assertRaises(mod.Stop):
                    preflight(runner)
                self.assertEqual(runner.writes, 0)

    def test_target_must_be_absent(self):
        for runner in (Runner(present=True), Runner(symlink=True)):
            with self.subTest(runner=runner):
                with self.assertRaisesRegex(mod.Stop, "target_exists"):
                    preflight(runner)

    def test_cp_capability_is_bounded(self):
        self.assertEqual(
            mod.cp_copy_options("cp (GNU coreutils) 9.1"),
            ("--no-clobber", "--verbose"),
        )
        self.assertEqual(
            mod.cp_copy_options("cp (GNU coreutils) 9.7"),
            ("--update=none-fail",),
        )
        for version in ("9.0", "9.2", "9.5", "bad"):
            with self.subTest(version=version):
                with self.assertRaises(mod.Stop):
                    preflight(Runner(cp_version=version))

    def test_preflight_is_read_only_and_exact_sudo_scoped(self):
        runner = Runner()
        self.assertEqual(preflight(runner), PAYLOAD)
        self.assertEqual(runner.writes, 0)
        self.assertTrue(
            any(
                call[0][:4] == [mod.SUDO, "-n", "-l", "--"]
                for call in runner.calls
            )
        )
        with self.assertRaisesRegex(mod.Stop, "sudo_exact_copy_not_allowed"):
            preflight(Runner(deny=True))

    def test_apply_dispatches_one_copy(self):
        runner = Runner()
        with mock.patch.object(mod, "preflight", return_value=PAYLOAD), \
             mock.patch.object(mod, "sealed_memfd", return_value=45), \
             mock.patch.object(mod, "exact_checkout"), \
             mock.patch.object(
                 mod, "root_preflight",
                 return_value=mod.cp_command("cp (GNU coreutils) 9.7")
             ), \
             mock.patch.object(mod, "post_verify"), \
             mock.patch.object(mod.os, "close"):
            mod.apply(HEAD, runner=runner)
        self.assertEqual(runner.writes, 1)

    def test_copy_failure_is_terminal_no_retry(self):
        runner = Runner(fail=True)
        with mock.patch.object(mod, "preflight", return_value=PAYLOAD), \
             mock.patch.object(mod, "sealed_memfd", return_value=45), \
             mock.patch.object(mod, "exact_checkout"), \
             mock.patch.object(
                 mod, "root_preflight",
                 return_value=mod.cp_command("cp (GNU coreutils) 9.7")
             ), \
             mock.patch.object(mod, "post_verify"), \
             mock.patch.object(mod.os, "close"):
            with self.assertRaisesRegex(
                mod.Stop, "post_dispatch_unknown_state"
            ):
                mod.apply(HEAD, runner=runner)
        self.assertEqual(runner.writes, 1)

    def test_confirmation_alone_never_installs(self):
        with mock.patch.object(mod, "apply") as apply, \
             mock.patch("builtins.print"):
            self.assertEqual(
                mod.main(["--expected-main", HEAD, "--apply"]),
                3,
            )
        apply.assert_not_called()

    def test_installer_has_no_provider_or_secret_surface(self):
        text = SOURCE.read_text("utf-8")
        for forbidden in (
            "/etc/rpi5-secrets",
            "CLOUDFLARE_API_TOKEN",
            "d1 execute",
            "npx ",
            "npm ",
            "/usr/bin/curl",
            "/usr/bin/rm",
            "shell=True",
        ):
            self.assertNotIn(forbidden.lower(), text.lower())


if __name__ == "__main__":
    unittest.main()
