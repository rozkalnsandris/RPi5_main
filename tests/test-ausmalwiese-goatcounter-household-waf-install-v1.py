#!/usr/bin/env python3
"""Offline adversarial tests for Ausmalwiese household WAF install/provision source."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install-ausmalwiese-goatcounter-household-waf-v1.py"
OPERATOR = ROOT / "scripts" / "ausmalwiese_goatcounter_household_waf_v1.py"

install_spec = importlib.util.spec_from_file_location("household_waf_install", INSTALLER)
installer = importlib.util.module_from_spec(install_spec)
assert install_spec and install_spec.loader
install_spec.loader.exec_module(installer)

operator_spec = importlib.util.spec_from_file_location("household_waf_operator_provision", OPERATOR)
operator = importlib.util.module_from_spec(operator_spec)
assert operator_spec and operator_spec.loader
operator_spec.loader.exec_module(operator)

SHA = "a" * 40
ZONE = "1" * 32
TOKEN = "dedicated-zone-waf-token-value"


class FakeRunner:
    def __init__(
        self, *, branch="main", dirty=False, wrong_origin=False,
        source_tracked=True, existing=False, dangling=False,
        bad_parent=False, fail_write_at=0, fail_verify=False,
    ):
        self.calls: list[tuple[list[str], bytes | None]] = []
        self.branch = branch
        self.dirty = dirty
        self.wrong_origin = wrong_origin
        self.source_tracked = source_tracked
        self.existing = existing
        self.dangling = dangling
        self.bad_parent = bad_parent
        self.fail_write_at = fail_write_at
        self.fail_verify = fail_verify
        self.writes = 0
        self.operator = OPERATOR.read_bytes()

    def __call__(self, argv, *, input=None, stdout=None, stderr=None, check=False):
        args = list(argv)
        self.calls.append((args, input))
        output = b""
        rc = 0
        if args[:3] == [installer.GIT, "-C", str(installer.ROOT)]:
            suffix = args[3:]
            if suffix == ["rev-parse", "--show-toplevel"]:
                output = (str(installer.ROOT) + "\n").encode()
            elif suffix == ["rev-parse", "HEAD"]:
                output = (SHA + "\n").encode()
            elif suffix == ["branch", "--show-current"]:
                output = (self.branch + "\n").encode()
            elif suffix == ["status", "--porcelain=v1", "--untracked-files=all"]:
                output = b" M scripts/ausmalwiese_goatcounter_household_waf_v1.py\n" if self.dirty else b""
            elif suffix == ["remote", "get-url", "origin"]:
                output = (
                    b"https://github.com/example/wrong.git\n"
                    if self.wrong_origin
                    else b"https://github.com/rozkalnsandris/RPi5_main.git\n"
                )
            elif suffix == ["ls-files", "--error-unmatch", installer.SOURCE_REL]:
                if self.source_tracked:
                    output = (installer.SOURCE_REL + "\n").encode()
                else:
                    rc = 1
            else:
                rc = 3
        elif args[:3] == [installer.SUDO, "-n", installer.STAT]:
            path = args[-1]
            if path in installer.PARENTS:
                output = b"0:0:777:directory" if self.bad_parent else b"0:0:755:directory"
            elif path == installer.RELEASE_DIR:
                output = b"0:0:700:directory"
            elif path == installer.INSTALLED:
                output = b"0:0:500:regular file"
            elif path == installer.RELEASE:
                output = b"0:0:400:regular file"
        elif args[:3] == [installer.SUDO, "-n", installer.TEST]:
            flag = args[-2]
            if self.existing:
                rc = 0
            elif self.dangling and flag == "-L":
                rc = 0
            else:
                rc = 1
        elif args[:3] == [installer.SUDO, "-n", installer.SHA256SUM]:
            path = args[-1]
            digest = hashlib.sha256(
                self.operator if path == installer.INSTALLED
                else installer.metadata_for(SHA, self.operator)
            ).hexdigest()
            if self.fail_verify:
                digest = "b" * 64
            output = f"{digest}  {path}\n".encode()
        elif args[:3] in (
            [installer.SUDO, "-n", installer.MKDIR],
            [installer.SUDO, "-n", installer.INSTALL],
        ):
            self.writes += 1
            if self.writes == self.fail_write_at:
                rc = 42
        return subprocess.CompletedProcess(args, rc, stdout=output, stderr=b"")


class InstallerTests(unittest.TestCase):
    def test_exact_paths_release_binding_and_confirmation(self):
        self.assertEqual(installer.SOURCE, OPERATOR)
        self.assertEqual(installer.INSTALLED, "/usr/local/sbin/rpi5-ausmalwiese-household-waf")
        self.assertEqual(installer.RELEASE_DIR, "/usr/local/libexec/rpi5-ausmalwiese-household-waf")
        self.assertEqual(installer.RELEASE, installer.RELEASE_DIR + "/release.json")
        self.assertEqual(installer.EXPECTED_CONFIRM, "INSTALL-AUSMALWIESE-HOUSEHOLD-WAF")
        metadata = json.loads(installer.metadata_for(SHA, b"operator"))
        self.assertEqual(metadata, {
            "operator_sha256": hashlib.sha256(b"operator").hexdigest(),
            "source_sha": SHA,
        })

    def test_root_caller_rejected(self):
        with mock.patch.object(installer.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(installer.InstallError, "installer_must_not_run_as_root"):
                installer.checked_source(SHA, runner=FakeRunner())

    def test_clean_exact_main_origin_source_parent_and_absent_targets_required(self):
        bad = (
            FakeRunner(branch="other"),
            FakeRunner(dirty=True),
            FakeRunner(wrong_origin=True),
            FakeRunner(source_tracked=False),
            FakeRunner(bad_parent=True),
            FakeRunner(existing=True),
            FakeRunner(dangling=True),
        )
        for runner in bad:
            with self.subTest(runner=runner):
                with mock.patch.object(installer.os, "geteuid", return_value=1000):
                    with self.assertRaises(installer.InstallError):
                        installer.preflight(SHA, runner=runner)
                self.assertEqual(runner.writes, 0)

    def test_preflight_catches_e_and_l_for_all_targets(self):
        runner = FakeRunner()
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            source, metadata = installer.preflight(SHA, runner=runner)
        self.assertEqual(source, OPERATOR.read_bytes())
        self.assertEqual(json.loads(metadata)["source_sha"], SHA)
        tests = [args for args, _ in runner.calls
                 if args[:3] == [installer.SUDO, "-n", installer.TEST]]
        self.assertEqual(len(tests), 6)
        self.assertEqual(set(x[-1] for x in tests),
                         {installer.INSTALLED, installer.RELEASE_DIR, installer.RELEASE})
        self.assertEqual(set(x[-2] for x in tests), {"-e", "-L"})

    def test_success_is_exact_three_fixed_coreutils_mutations(self):
        runner = FakeRunner()
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            installer.install(SHA, runner=runner)
        writes = [(a, payload) for a, payload in runner.calls
                  if a[:3] in (
                      [installer.SUDO, "-n", installer.MKDIR],
                      [installer.SUDO, "-n", installer.INSTALL],
                  )]
        self.assertEqual(len(writes), 3)
        self.assertEqual(writes[0], (
            [installer.SUDO, "-n", installer.MKDIR, "-m", "0700",
             "--", installer.RELEASE_DIR],
            None,
        ))
        self.assertEqual(writes[1][0], [
            installer.SUDO, "-n", installer.INSTALL, "-T", "-o", "root",
            "-g", "root", "-m", "0500", "--", "/dev/stdin", installer.INSTALLED,
        ])
        self.assertEqual(writes[1][1], OPERATOR.read_bytes())
        self.assertEqual(writes[2][0], [
            installer.SUDO, "-n", installer.INSTALL, "-T", "-o", "root",
            "-g", "root", "-m", "0400", "--", "/dev/stdin", installer.RELEASE,
        ])
        self.assertEqual(writes[2][1], installer.metadata_for(SHA, OPERATOR.read_bytes()))
        self.assertEqual(runner.writes, 3)
        for argv, _ in runner.calls:
            joined = " ".join(argv)
            self.assertNotIn("python3", joined)
            self.assertNotIn("bash -c", joined)
            self.assertNotIn("sh -c", joined)
            self.assertNotIn("/usr/bin/rm", joined)

    def test_each_root_write_failure_is_terminal_without_retry_cleanup(self):
        for position in (1, 2, 3):
            runner = FakeRunner(fail_write_at=position)
            with self.subTest(position=position):
                with mock.patch.object(installer.os, "geteuid", return_value=1000):
                    with self.assertRaisesRegex(installer.InstallError, "post_dispatch_unknown_state"):
                        installer.install(SHA, runner=runner)
                self.assertEqual(runner.writes, position)
                self.assertFalse(any("/usr/bin/rm" in " ".join(a) for a, _ in runner.calls))

    def test_post_install_digest_mismatch_is_terminal(self):
        runner = FakeRunner(fail_verify=True)
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(installer.InstallError, "post_dispatch_unknown_state"):
                installer.install(SHA, runner=runner)
        self.assertEqual(runner.writes, 3)

    def test_apply_requires_exact_confirmation_before_preflight(self):
        with mock.patch.object(installer, "install", side_effect=AssertionError("must not install")):
            self.assertEqual(installer.main(["--expected-main", SHA, "--apply"]), 3)


class ProvisioningTests(unittest.TestCase):
    @staticmethod
    def private_dir():
        return SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700,
            st_uid=0,
            st_gid=0,
        )

    def success_patches(self, api_side_effect):
        payload = (json.dumps({
            "zone_id": ZONE,
            "zone_name": operator.ZONE_NAME,
            "api_token": TOKEN,
        }, separators=(",", ":")) + "\n").encode()
        return (
            mock.patch.object(operator, "verified_installed_release"),
            mock.patch.object(Path, "lstat", side_effect=[self.private_dir(), FileNotFoundError()]),
            mock.patch.object(operator.os, "open", side_effect=[7, 8]),
            mock.patch.object(operator.os, "isatty", return_value=True),
            mock.patch.object(operator.os, "close"),
            mock.patch.object(operator.os, "fchmod"),
            mock.patch.object(operator.os, "write", side_effect=lambda fd, data: len(data)),
            mock.patch.object(operator.os, "fsync"),
            mock.patch.object(operator.getpass, "getpass", side_effect=[ZONE, TOKEN]),
            mock.patch.object(operator, "api_call", side_effect=api_side_effect),
            mock.patch.object(operator, "owned_file", return_value=payload),
        )

    def test_provisioning_exact_confirmation_required(self):
        with mock.patch.object(operator, "provision_secret", side_effect=AssertionError("must not provision")):
            with self.assertRaises(operator.GateError):
                operator.main([
                    "--provision-secret",
                    "--expected-main", SHA,
                    "--confirm", "WRONG",
                ])

    def test_provisioning_uses_hidden_tty_exclusive_0600_and_only_gets(self):
        patches = self.success_patches([
            (200, {"id": ZONE, "name": operator.ZONE_NAME}),
            (404, {}),
        ])
        with patches[0], patches[1], patches[2] as opened, patches[3], patches[4], \
             patches[5] as chmod, patches[6], patches[7], patches[8] as prompts, \
             patches[9] as api, patches[10]:
            operator.provision_secret(SHA)
        self.assertEqual(prompts.call_count, 2)
        self.assertEqual(opened.call_args_list[0], mock.call(
            "/dev/tty", os.O_RDWR | os.O_NOCTTY | os.O_NOFOLLOW))
        secret_call = opened.call_args_list[1]
        self.assertEqual(secret_call.args[0], operator.SECRET)
        self.assertEqual(secret_call.args[1],
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW)
        self.assertEqual(secret_call.args[2], 0o600)
        chmod.assert_called_once_with(8, 0o600)
        self.assertEqual([call.args[1] for call in api.call_args_list], ["GET", "GET"])
        self.assertFalse(any(call.args[1] == "POST" for call in api.call_args_list))

    def test_provider_zone_mismatch_blocks_before_secret_creation(self):
        with mock.patch.object(operator, "verified_installed_release"), \
             mock.patch.object(Path, "lstat", side_effect=[self.private_dir(), FileNotFoundError()]), \
             mock.patch.object(operator.os, "open", return_value=7) as opened, \
             mock.patch.object(operator.os, "isatty", return_value=True), \
             mock.patch.object(operator.os, "close"), \
             mock.patch.object(operator.getpass, "getpass", side_effect=[ZONE, TOKEN]), \
             mock.patch.object(operator, "api_call",
                               return_value=(200, {"id": ZONE, "name": "wrong.example"})):
            with self.assertRaisesRegex(operator.GateError, "provider_zone_identity_mismatch"):
                operator.provision_secret(SHA)
        self.assertEqual(opened.call_count, 1)

    def test_provider_transport_failure_blocks_before_secret_creation(self):
        with mock.patch.object(operator, "verified_installed_release"), \
             mock.patch.object(Path, "lstat", side_effect=[self.private_dir(), FileNotFoundError()]), \
             mock.patch.object(operator.os, "open", return_value=7) as opened, \
             mock.patch.object(operator.os, "isatty", return_value=True), \
             mock.patch.object(operator.os, "close"), \
             mock.patch.object(operator.getpass, "getpass", side_effect=[ZONE, TOKEN]), \
             mock.patch.object(operator, "api_call",
                               side_effect=operator.GateError("provider_transport_error")):
            with self.assertRaisesRegex(operator.GateError, "provider_transport_error"):
                operator.provision_secret(SHA)
        self.assertEqual(opened.call_count, 1)

    def test_source_has_no_cli_env_stdin_secret_or_household_provisioning_input(self):
        source = OPERATOR.read_text("utf-8")
        self.assertIn('getpass.getpass("Dedicated ausmalwiese.de Zone ID (hidden): ")', source)
        self.assertIn('getpass.getpass("Dedicated Zone Read + Zone WAF Write token (hidden): ")', source)
        self.assertIn("os.O_EXCL | os.O_NOFOLLOW", source)
        self.assertIn('"PROVISION-AUSMALWIESE-ZONE-WAF-SECRET"', source)
        self.assertNotIn('add_argument("--api-token"', source)
        self.assertNotIn('add_argument("--zone-id"', source)
        self.assertNotIn("os.environ", source)
        provision = source.split("def provision_secret", 1)[1].split("def execute", 1)[0]
        self.assertNotIn("read_household_sources", provision)
        self.assertNotIn('"POST"', provision)

    def test_fixed_secret_path_and_schema_only(self):
        self.assertEqual(
            operator.SECRET,
            Path("/etc/rpi5-secrets/cloudflare/ausmalwiese-zone-waf-writer.json"),
        )
        self.assertEqual(operator.ZONE_NAME, "ausmalwiese.de")


if __name__ == "__main__":
    unittest.main()
