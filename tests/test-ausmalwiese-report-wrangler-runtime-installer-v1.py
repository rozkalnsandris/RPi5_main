#!/usr/bin/env python3
"""Synthetic tests for the report Wrangler runtime-boundary installer."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import stat
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/install-ausmalwiese-report-wrangler-runtime-boundary-v1.py"
RUNTIME = ROOT / "scripts/ausmalwiese_report_wrangler_deploy_v1.py"
spec = importlib.util.spec_from_file_location("report_runtime_installer_1075", SOURCE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

HEAD = "b" * 40
PAYLOAD = RUNTIME.read_bytes()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw
    ).hexdigest()


class Runner:
    def __init__(
        self,
        *,
        head=HEAD,
        branch="main",
        dirty=False,
        origin="https://github.com/rozkalnsandris/RPi5_main.git",
        parent_mode="755",
        parent_kind="directory",
        present=False,
        symlink=False,
        cp_version="9.7",
        fail_write=False,
        wrong_metadata=False,
        wrong_sha=False,
        deny_exact_copy=False,
        race_at_dispatch=False,
        skip_copy=False,
        wrong_blob=False,
        corrupted_source=False,
    ):
        self.head = head
        self.branch = branch
        self.dirty = dirty
        self.origin = origin
        self.parent_mode = parent_mode
        self.parent_kind = parent_kind
        self.present = present
        self.symlink = symlink
        self.cp_version = cp_version
        self.fail_write = fail_write
        self.wrong_metadata = wrong_metadata
        self.wrong_sha = wrong_sha
        self.deny_exact_copy = deny_exact_copy
        self.race_at_dispatch = race_at_dispatch
        self.skip_copy = skip_copy
        self.wrong_blob = wrong_blob
        self.corrupted_source = corrupted_source
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
            raise AssertionError("subprocess environment not bounded")
        rc = 0
        out = b""

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
                out = b" M changed\x00" if self.dirty else b""
            elif command == ["remote", "get-url", "origin"]:
                out = (self.origin + "\n").encode()
            elif command == ["show", "HEAD:" + mod.SOURCE_REL]:
                out = b"tampered" if self.corrupted_source else PAYLOAD
            elif command == ["ls-tree", "HEAD", "--", mod.SOURCE_REL]:
                blob = "0" * 40 if self.wrong_blob else mod.SOURCE_BLOB
                out = (
                    f"100644 blob {blob}\t{mod.SOURCE_REL}\n"
                ).encode()
            else:
                rc = 4

        elif args[:3] == [mod.SUDO, "-n", mod.CP] and args[-1:] == ["--version"]:
            out = (
                f"cp (GNU coreutils) {self.cp_version}\nCopyright...\n"
            ).encode()

        elif args[:3] == [mod.SUDO, "-n", mod.STAT]:
            if args[-1] in mod.PARENTS:
                out = (
                    f"0:0:{self.parent_mode}:{self.parent_kind}\n"
                ).encode()
            elif args[-1] == mod.TARGET and args[3] == "-c":
                out = (
                    b"0:0:400:regular file:1\n"
                    if self.wrong_metadata
                    else b"0:0:500:regular file:1\n"
                )
            else:
                rc = 3

        elif args[:4] == [mod.SUDO, "-n", "-l", "--"]:
            if self.deny_exact_copy:
                rc = 1
            elif args[4:] != mod.cp_command(
                f"cp (GNU coreutils) {self.cp_version}"
            ):
                raise AssertionError("unapproved sudo capability query")

        elif args[:3] == [mod.SUDO, "-n", mod.TEST]:
            if args[3] == "-L":
                rc = 0 if self.symlink else 1
            else:
                rc = 0 if self.present else 1

        elif args[:3] == [mod.SUDO, "-n", mod.SHA256SUM]:
            digest = (
                "0" * 64
                if self.wrong_sha
                else hashlib.sha256(PAYLOAD).hexdigest()
            )
            out = (digest + "  " + mod.TARGET + "\n").encode()

        elif args[:3] == [mod.SUDO, "-n", mod.CP]:
            self.writes += 1
            expected = [
                mod.SUDO,
                "-n",
                *mod.cp_command(f"cp (GNU coreutils) {self.cp_version}"),
            ]
            if args != expected:
                raise AssertionError("unsafe copy argv")
            if stdin != 45:
                raise AssertionError("sealed memfd required")
            rc = (
                1
                if self.fail_write
                or self.present
                or self.symlink
                or self.race_at_dispatch
                else 0
            )
            if self.skip_copy:
                rc = 0
                out = b""
            elif self.cp_version == "9.1":
                out = (
                    "'/dev/stdin' -> '" + mod.TARGET + "'\n"
                ).encode("ascii")
        else:
            raise AssertionError("unanticipated subprocess")

        return subprocess.CompletedProcess(args, rc, stdout=out, stderr=b"safe")


def preflight(runner):
    with mock.patch.object(mod.os, "geteuid", return_value=1000):
        return mod.preflight(HEAD, runner=runner)


class RuntimeInstallerTests(unittest.TestCase):
    def test_exact_runtime_blob_and_target_are_pinned(self):
        self.assertEqual(git_blob(PAYLOAD), mod.SOURCE_BLOB)
        self.assertEqual(
            mod.TARGET,
            "/usr/local/sbin/rpi5-ausmalwiese-report-wrangler-deploy",
        )
        self.assertEqual(
            mod.SOURCE_REL,
            "scripts/ausmalwiese_report_wrangler_deploy_v1.py",
        )

    def test_source_or_checkout_drift_stops_before_write(self):
        cases = [
            Runner(branch="feature"),
            Runner(head="a" * 40),
            Runner(dirty=True),
            Runner(origin="https://example.invalid/repo"),
            Runner(corrupted_source=True),
            Runner(wrong_blob=True),
        ]
        for runner in cases:
            with self.subTest(runner=runner):
                with self.assertRaises(mod.Stop):
                    preflight(runner)
                self.assertEqual(runner.writes, 0)

    def test_cp_91_and_96_plus_only(self):
        self.assertEqual(
            mod.cp_copy_options("cp (GNU coreutils) 9.1"),
            ("--no-clobber", "--verbose"),
        )
        self.assertEqual(
            mod.cp_copy_options("cp (GNU coreutils) 9.6"),
            ("--update=none-fail",),
        )
        for version in ("9.0", "9.2", "9.3", "9.4", "9.5", "invalid"):
            with self.subTest(version=version):
                with self.assertRaises(mod.Stop):
                    preflight(Runner(cp_version=version))

    def test_parent_target_and_sudo_guards(self):
        cases = [
            Runner(parent_mode="777"),
            Runner(parent_kind="symbolic link"),
            Runner(present=True),
            Runner(symlink=True),
            Runner(deny_exact_copy=True),
        ]
        for runner in cases:
            with self.subTest(runner=runner):
                with self.assertRaises(mod.Stop):
                    preflight(runner)
                self.assertEqual(runner.writes, 0)

    def test_preflight_is_read_only(self):
        runner = Runner(cp_version="9.1")
        self.assertEqual(preflight(runner), PAYLOAD)
        self.assertEqual(runner.writes, 0)
        command = mod.cp_command("cp (GNU coreutils) 9.1")
        self.assertIn(
            ([mod.SUDO, "-n", "-l", "--", *command], None),
            runner.calls,
        )

    def test_exact_one_root_copy(self):
        runner = Runner()
        with mock.patch.object(mod, "preflight", return_value=PAYLOAD), \
             mock.patch.object(mod, "sealed_memfd", return_value=45), \
             mock.patch.object(mod, "exact_checkout"), \
             mock.patch.object(mod.os, "close"):
            mod.apply(HEAD, runner=runner)
        self.assertEqual(runner.writes, 1)

    def test_gnu91_silent_skip_or_race_is_terminal(self):
        for runner in (
            Runner(cp_version="9.1", skip_copy=True),
            Runner(cp_version="9.1", race_at_dispatch=True),
        ):
            with self.subTest(runner=runner):
                with mock.patch.object(mod, "preflight", return_value=PAYLOAD), \
                     mock.patch.object(mod, "sealed_memfd", return_value=45), \
                     mock.patch.object(mod, "exact_checkout"), \
                     mock.patch.object(mod.os, "close"):
                    with self.assertRaisesRegex(
                        mod.Stop, "post_dispatch_unknown_state"
                    ):
                        mod.apply(HEAD, runner=runner)
                self.assertEqual(runner.writes, 1)

    def test_post_verify_failure_has_no_retry_or_cleanup(self):
        for runner in (
            Runner(fail_write=True),
            Runner(wrong_metadata=True),
            Runner(wrong_sha=True),
        ):
            with self.subTest(runner=runner):
                with mock.patch.object(mod, "preflight", return_value=PAYLOAD), \
                     mock.patch.object(mod, "sealed_memfd", return_value=45), \
                     mock.patch.object(mod, "exact_checkout"), \
                     mock.patch.object(mod.os, "close"):
                    with self.assertRaisesRegex(
                        mod.Stop, "post_dispatch_unknown_state"
                    ):
                        mod.apply(HEAD, runner=runner)
                self.assertEqual(runner.writes, 1)
                self.assertFalse(
                    any(
                        "/usr/bin/rm" in " ".join(args)
                        for args, _ in runner.calls
                    )
                )

    def test_upgrade_is_bound_to_exact_old_runtime_blob_and_ref(self):
        self.assertEqual(
            mod.OLD_SOURCE_REF,
            "a17f83668acdcdfde26ef6f586b1c2f8aa765ada",
        )
        self.assertEqual(
            mod.OLD_SOURCE_BLOB,
            "600f9f15ac706d581d4d58ca5bdf4f78b2053801",
        )
        with mock.patch.object(mod, "exact_checkout") as checkout, \
             mock.patch.object(mod, "tracked_runtime", return_value=PAYLOAD), \
             mock.patch.object(mod, "historical_runtime", return_value=b"old-runtime"), \
             mock.patch.object(mod, "upgrade_root_preflight") as roots:
            self.assertEqual(
                mod.upgrade_preflight(
                    HEAD,
                    mod.OLD_SOURCE_BLOB,
                ),
                PAYLOAD,
            )
        checkout.assert_called_once_with(HEAD, runner=subprocess.run)
        roots.assert_called_once_with(b"old-runtime", runner=subprocess.run)

        with mock.patch.object(mod, "exact_checkout") as checkout:
            with self.assertRaisesRegex(mod.Stop, "invalid_upgrade_source"):
                mod.upgrade_preflight(HEAD, "0" * 40)
        checkout.assert_not_called()

    def test_upgrade_root_preflight_checks_old_metadata_digest_and_capability(self):
        old_payload = b"old-runtime"
        digest = hashlib.sha256(old_payload).hexdigest()

        def metadata(args, **kwargs):
            if args[:3] == [mod.STAT, "-c", "%u:%g:%a:%F"]:
                return "0:0:755:directory"
            if args[:3] == [mod.STAT, "-c", "%u:%g:%a:%F:%h"]:
                return "0:0:500:regular file:1"
            if args[:2] == [mod.SHA256SUM, "--"]:
                return digest + "  " + mod.TARGET
            raise AssertionError(args)

        def invoke(args, **kwargs):
            if args == [mod.SUDO, "-n", mod.TEST, "-L", mod.TARGET]:
                return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"")
            if args == [mod.SUDO, "-n", "-l", "--", *mod.upgrade_command()]:
                return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
            raise AssertionError(args)

        with mock.patch.object(mod, "sudo_metadata", side_effect=metadata), \
             mock.patch.object(mod, "invoke", side_effect=invoke):
            self.assertEqual(
                mod.upgrade_root_preflight(old_payload),
                mod.upgrade_command(),
            )

        def wrong_digest(args, **kwargs):
            if args[:3] == [mod.STAT, "-c", "%u:%g:%a:%F"]:
                return "0:0:755:directory"
            if args[:3] == [mod.STAT, "-c", "%u:%g:%a:%F:%h"]:
                return "0:0:500:regular file:1"
            if args[:2] == [mod.SHA256SUM, "--"]:
                return ("0" * 64) + "  " + mod.TARGET
            raise AssertionError(args)

        with mock.patch.object(mod, "sudo_metadata", side_effect=wrong_digest), \
             mock.patch.object(mod, "invoke", side_effect=invoke):
            with self.assertRaisesRegex(
                mod.Stop,
                "upgrade_target_digest_mismatch",
            ):
                mod.upgrade_root_preflight(old_payload)

    def test_upgrade_dispatches_once_and_failure_is_terminal(self):
        def runner(args, **kwargs):
            self.assertEqual(
                list(args),
                [mod.SUDO, "-n", *mod.upgrade_command()],
            )
            self.assertEqual(kwargs["stdin"], 45)
            self.assertEqual(kwargs["env"], mod.CLEAN_ENV)
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        with mock.patch.object(mod, "upgrade_preflight", return_value=PAYLOAD), \
             mock.patch.object(mod, "sealed_memfd", return_value=45), \
             mock.patch.object(mod, "exact_checkout"), \
             mock.patch.object(mod, "historical_runtime", return_value=b"old"), \
             mock.patch.object(
                 mod,
                 "upgrade_root_preflight",
                 return_value=mod.upgrade_command(),
             ), \
             mock.patch.object(mod, "post_verify") as verify, \
             mock.patch.object(mod.os, "close"):
            mod.upgrade(HEAD, mod.OLD_SOURCE_BLOB, runner=runner)
        verify.assert_called_once_with(PAYLOAD, runner=runner)

        calls = []
        def failed(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"safe")

        with mock.patch.object(mod, "upgrade_preflight", return_value=PAYLOAD), \
             mock.patch.object(mod, "sealed_memfd", return_value=45), \
             mock.patch.object(mod, "exact_checkout"), \
             mock.patch.object(mod, "historical_runtime", return_value=b"old"), \
             mock.patch.object(
                 mod,
                 "upgrade_root_preflight",
                 return_value=mod.upgrade_command(),
             ), \
             mock.patch.object(mod, "post_verify"), \
             mock.patch.object(mod.os, "close"):
            with self.assertRaisesRegex(
                mod.Stop,
                "post_dispatch_unknown_state",
            ):
                mod.upgrade(HEAD, mod.OLD_SOURCE_BLOB, runner=failed)
        self.assertEqual(len(calls), 1)

    def test_confirmation_alone_never_installs(self):
        with mock.patch.object(mod, "apply") as apply, \
             mock.patch("builtins.print"):
            self.assertEqual(
                mod.main(["--expected-main", HEAD, "--apply"]),
                3,
            )
            apply.assert_not_called()

    def test_installer_contains_no_secret_or_cloudflare_transport(self):
        text = SOURCE.read_text("utf-8")
        self.assertNotIn("CLOUDFLARE_API_TOKEN", text)
        self.assertNotIn("BREVO_API_KEY", text)
        self.assertNotIn("/etc/rpi5-secrets", text)
        self.assertNotIn("wrangler@", text)
        self.assertNotIn("shell=True", text)


if __name__ == "__main__":
    unittest.main()
