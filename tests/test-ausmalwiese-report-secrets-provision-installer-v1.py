#!/usr/bin/env python3
"""Synthetic tests for the report secrets provisioner installer source."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import stat
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/install-ausmalwiese-report-secrets-provisioner-v1.py"
HELPER = ROOT / "scripts/ausmalwiese_report_secrets_provisioner.py"
spec = importlib.util.spec_from_file_location("report_secrets_installer", SOURCE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

HEAD = "b" * 40
PAYLOAD = HELPER.read_bytes()


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
        sudo_disabled=False,
        deny_exact_copy=False,
        race_at_dispatch=False,
        skip_copy=False,
        unexpected_copy_output=False,
        corrupted_source=False,
        wrong_blob=False,
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
        self.sudo_disabled = sudo_disabled
        self.deny_exact_copy = deny_exact_copy
        self.race_at_dispatch = race_at_dispatch
        self.skip_copy = skip_copy
        self.unexpected_copy_output = unexpected_copy_output
        self.corrupted_source = corrupted_source
        self.wrong_blob = wrong_blob
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
            if self.sudo_disabled:
                rc = 1
            else:
                out = (
                    f"cp (GNU coreutils) {self.cp_version}\nCopyright...\n"
                ).encode()

        elif args[:3] == [mod.SUDO, "-n", mod.STAT]:
            if self.sudo_disabled:
                rc = 1
            elif args[-1] in mod.PARENTS:
                out = (
                    f"0:0:{self.parent_mode}:{self.parent_kind}\n"
                ).encode()
            elif args[-1] == mod.INSTALL_TARGET and args[3] == "-c":
                out = (
                    b"0:0:400:regular file:1\n"
                    if self.wrong_metadata
                    else b"0:0:500:regular file:1\n"
                )
            else:
                rc = 3

        elif args[:4] == [mod.SUDO, "-n", "-l", "--"]:
            if self.sudo_disabled or self.deny_exact_copy:
                rc = 1
            elif args[4:] != mod.cp_command(
                f"cp (GNU coreutils) {self.cp_version}"
            ):
                raise AssertionError("unapproved sudo capability query")

        elif args[:3] == [mod.SUDO, "-n", mod.TEST]:
            if self.sudo_disabled:
                rc = 7
            elif args[3] == "-L":
                rc = 0 if self.symlink else 1
            else:
                rc = 0 if self.present else 1

        elif args[:3] == [mod.SUDO, "-n", mod.SHA256SUM]:
            digest = (
                "0" * 64
                if self.wrong_sha
                else hashlib.sha256(PAYLOAD).hexdigest()
            )
            out = (digest + "  " + mod.INSTALL_TARGET + "\n").encode()

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
                    "'/dev/stdin' -> '"
                    + mod.INSTALL_TARGET
                    + "'\n"
                ).encode("ascii")
            if self.unexpected_copy_output:
                out = b"unexpected"
        else:
            raise AssertionError("unanticipated subprocess")

        return subprocess.CompletedProcess(args, rc, stdout=out, stderr=b"safe")


def preflight(runner):
    with mock.patch.object(mod.os, "geteuid", return_value=1000):
        return mod.preflight(HEAD, runner=runner)


class ReportSecretsInstallerTests(unittest.TestCase):
    def test_fixed_scope_and_blob(self):
        self.assertEqual(
            mod.INSTALL_TARGET,
            "/usr/local/sbin/rpi5-ausmalwiese-report-secrets-provision",
        )
        self.assertEqual(
            mod.PROTECTED_TARGET,
            "/etc/rpi5-secrets/cloudflare/ausmalwiese-report-wrangler-secrets.json",
        )
        self.assertEqual(mod.WORKER, "coloring-pages-report-v1")
        self.assertEqual(mod.git_blob(PAYLOAD), mod.SOURCE_BLOB)
        mod.fixed_source_constants(PAYLOAD)

    def test_source_identity_rejects_tamper_or_blob_drift(self):
        with self.assertRaisesRegex(mod.Stop, "helper_source_mismatch"):
            preflight(Runner(corrupted_source=True))
        with self.assertRaisesRegex(mod.Stop, "helper_source_mismatch"):
            preflight(Runner(wrong_blob=True))

    def test_checkout_guards(self):
        cases = [
            Runner(branch="feature"),
            Runner(head="a" * 40),
            Runner(dirty=True),
            Runner(origin="https://example.invalid/repo.git"),
        ]
        for runner in cases:
            with self.subTest(runner=runner):
                with self.assertRaises(mod.Stop):
                    preflight(runner)
                self.assertEqual(runner.writes, 0)

    def test_cp_versions_fail_closed_except_91_and_96_plus(self):
        self.assertEqual(
            mod.cp_copy_options("cp (GNU coreutils) 9.1"),
            ("--no-clobber", "--verbose"),
        )
        self.assertEqual(
            mod.cp_copy_options("cp (GNU coreutils) 9.6"),
            ("--update=none-fail",),
        )
        self.assertEqual(
            mod.cp_copy_options("cp (GNU coreutils) 10.0"),
            ("--update=none-fail",),
        )
        for version in ("9.0", "9.2", "9.3", "9.4", "9.5", "invalid"):
            with self.subTest(version=version):
                with self.assertRaises(mod.Stop):
                    preflight(Runner(cp_version=version))

    def test_exact_sudo_copy_capability_required(self):
        runner = Runner(deny_exact_copy=True)
        with self.assertRaisesRegex(mod.Stop, "sudo_exact_copy_not_allowed"):
            preflight(runner)
        self.assertEqual(runner.writes, 0)

    def test_parent_and_target_guards(self):
        cases = [
            Runner(parent_mode="777"),
            Runner(parent_mode="775"),
            Runner(parent_kind="symbolic link"),
            Runner(present=True),
            Runner(symlink=True),
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
        expected = mod.cp_command("cp (GNU coreutils) 9.1")
        self.assertIn(
            ([mod.SUDO, "-n", "-l", "--", *expected], None),
            runner.calls,
        )

    def test_gnu91_copy_requires_exact_verbose_creation_proof(self):
        good = subprocess.CompletedProcess(
            [],
            0,
            (
                "'/dev/stdin' -> '"
                + mod.INSTALL_TARGET
                + "'\n"
            ).encode(),
            b"",
        )
        mod.cp_copy_proven(good, ("--no-clobber", "--verbose"))
        for result in (
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, b"unexpected", b""),
            subprocess.CompletedProcess([], 1, b"", b""),
        ):
            with self.assertRaises(mod.Stop):
                mod.cp_copy_proven(
                    result, ("--no-clobber", "--verbose")
                )

    def test_sealed_memfd_mode_and_seals(self):
        info = type(
            "Stat",
            (),
            {
                "st_mode": stat.S_IFREG | 0o500,
                "st_size": len(PAYLOAD),
            },
        )()
        with mock.patch.object(mod.os, "memfd_create", return_value=45), \
             mock.patch.object(mod.os, "write", return_value=len(PAYLOAD)), \
             mock.patch.object(mod.os, "fchmod") as chmod, \
             mock.patch.object(mod.os, "lseek"), \
             mock.patch.object(mod.fcntl, "fcntl") as seal, \
             mock.patch.object(mod.os, "fstat", return_value=info):
            fd = mod.sealed_memfd(PAYLOAD)
        self.assertEqual(fd, 45)
        chmod.assert_called_once_with(45, 0o500)
        self.assertEqual(seal.call_count, 1)

    def test_apply_exact_one_copy(self):
        runner = Runner()
        with mock.patch.object(mod, "preflight", return_value=PAYLOAD), \
             mock.patch.object(mod, "sealed_memfd", return_value=45), \
             mock.patch.object(mod, "exact_checkout"), \
             mock.patch.object(mod.os, "close") as close:
            mod.apply(HEAD, runner=runner)
        self.assertEqual(runner.writes, 1)
        close.assert_called_once_with(45)

    def test_race_or_post_dispatch_failure_stops_without_retry(self):
        for runner in (
            Runner(race_at_dispatch=True),
            Runner(fail_write=True),
            Runner(wrong_metadata=True),
            Runner(wrong_sha=True),
            Runner(cp_version="9.1", skip_copy=True),
            Runner(cp_version="9.1", unexpected_copy_output=True),
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

    def test_drift_before_dispatch_blocks_write(self):
        runner = Runner()
        with mock.patch.object(mod, "preflight", return_value=PAYLOAD), \
             mock.patch.object(mod, "sealed_memfd", return_value=45), \
             mock.patch.object(
                 mod, "exact_checkout", side_effect=mod.Stop("main_drift")
             ), \
             mock.patch.object(mod.os, "close"):
            with self.assertRaisesRegex(mod.Stop, "main_drift"):
                mod.apply(HEAD, runner=runner)
        self.assertEqual(runner.writes, 0)

    def test_confirmation_does_not_bypass_apply_gate(self):
        with mock.patch.object(mod, "apply") as apply, \
             mock.patch("builtins.print"):
            self.assertEqual(
                mod.main(["--expected-main", HEAD, "--apply"]),
                3,
            )
            apply.assert_not_called()

    def test_source_has_no_secret_or_generic_root_path(self):
        text = SOURCE.read_text()
        self.assertNotIn("api_token", text)
        self.assertNotIn("secret_value", text)
        self.assertNotIn("os.environ", text)
        self.assertNotIn("shell=True", text)
        self.assertNotIn("/usr/bin/rm", text)


if __name__ == "__main__":
    unittest.main()
