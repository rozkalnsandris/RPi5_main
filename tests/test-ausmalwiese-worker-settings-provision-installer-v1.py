#!/usr/bin/env python3
"""Fully synthetic fake-runner tests; never access host, token or Cloudflare."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/install-ausmalwiese-worker-settings-provisioner-v1.py"
HELPER = ROOT / "scripts/ausmalwiese_worker_settings_provisioner.py"
spec = importlib.util.spec_from_file_location("helper_install_v1", SOURCE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
HEAD = "b" * 40
PAYLOAD = HELPER.read_bytes()


class Runner:
    def __init__(self, *, head=HEAD, branch="main", dirty=False,
                 origin="https://github.com/rozkalnsandris/RPi5_main.git",
                 parent_mode="755", parent_kind="directory", present=False,
                 symlink=False, cp_version="9.7", fail_write=False,
                 wrong_metadata=False, wrong_sha=False, sudo_disabled=False,
                 corrupted_source=False):
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
        self.corrupted_source = corrupted_source
        self.calls = []
        self.writes = 0

    def __call__(self, argv, *, stdin=None, stdout=None, stderr=None,
                 check=False, timeout=None, env=None):
        a = list(argv)
        self.calls.append((a,stdin))
        if env != mod.CLEAN_ENV:
            raise AssertionError("subprocess environment not bounded")
        rc = 0
        out = b""
        if a[:3] == [mod.GIT, "-C", str(mod.ROOT)]:
            command = a[3:]
            if command == ["rev-parse","--show-toplevel"]:
                out = (str(mod.ROOT)+"\n").encode()
            elif command == ["symbolic-ref","--quiet","--short","HEAD"]:
                out = (self.branch+"\n").encode()
            elif command == ["rev-parse","HEAD"]:
                out = (self.head+"\n").encode()
            elif command == ["status","--porcelain=v1","-z","--untracked-files=all"]:
                out = b" M changed\x00" if self.dirty else b""
            elif command == ["remote","get-url","origin"]:
                out = (self.origin+"\n").encode()
            elif command == ["show","HEAD:"+mod.SOURCE_REL]:
                out = b"tampered" if self.corrupted_source else PAYLOAD
            else:
                rc = 4
        elif a[:3] == [mod.SUDO,"-n",mod.CP] and a[-1:] == ["--version"]:
            if self.sudo_disabled:
                rc = 1
            else:
                out = f"cp (GNU coreutils) {self.cp_version}\nCopyright...\n".encode()
        elif a[:3] == [mod.SUDO,"-n",mod.STAT]:
            if self.sudo_disabled:
                rc = 1
            elif a[-1] in mod.PARENTS:
                out = f"0:0:{self.parent_mode}:{self.parent_kind}\n".encode()
            elif a[-1] == mod.TARGET and a[3] == "-c":
                out = b"0:0:400:regular file:1\n" if self.wrong_metadata else b"0:0:500:regular file:1\n"
            else:
                rc = 3
        elif a[:3] == [mod.SUDO,"-n",mod.TEST]:
            if self.sudo_disabled:
                rc = 7
            elif a[3] == "-L":
                rc = 0 if self.symlink else 1
            else:
                rc = 0 if self.present else 1
        elif a[:3] == [mod.SUDO,"-n",mod.SHA256SUM]:
            value = ("0"*64 if self.wrong_sha else hashlib.sha256(PAYLOAD).hexdigest())
            out = (value+"  "+mod.TARGET+"\n").encode()
        elif a[:3] == [mod.SUDO,"-n",mod.CP]:
            self.writes += 1
            if a != [mod.SUDO,"-n",mod.CP,"--update=none-fail",
                     "--preserve=mode","-T","--","/dev/stdin",mod.TARGET]:
                raise AssertionError("unsafe cp write argv")
            if stdin != 45:
                raise AssertionError("must pass sealed memfd as stdin")
            rc = 1 if self.fail_write or self.present or self.symlink else 0
        else:
            raise AssertionError("unanticipated subprocess")
        return subprocess.CompletedProcess(a,rc,stdout=out,stderr=b"secret-synthetic-message")


def preflight(runner):
    with mock.patch.object(mod.os,"geteuid",return_value=1000):
        return mod.preflight(HEAD,runner=runner)


class HelperInstallTests(unittest.TestCase):
    def test_fixed_scope_and_source_compiles(self):
        self.assertEqual(mod.TARGET,"/usr/local/sbin/rpi5-ausmalwiese-worker-settings-provision")
        self.assertEqual(mod.SOURCE_REL,"scripts/ausmalwiese_worker_settings_provisioner.py")
        self.assertEqual(mod.GET_RELEASE,"6c55e46d43889fed2a17770d0f466c79b1db736a")
        self.assertIn("--update=none-fail",SOURCE.read_text())
        self.assertNotIn("shell=True",SOURCE.read_text())
        self.assertNotIn("/usr/bin/install",SOURCE.read_text())
        mod.fixed_source_constants(PAYLOAD)

    def test_exact_checkout_clean(self):
        self.assertEqual(preflight(Runner()),PAYLOAD)

    def test_checkout_fail_closed_before_privileged_read(self):
        cases=(Runner(head="0"*40),Runner(branch="branch"),
               Runner(dirty=True),Runner(origin="https://invalid.test/repo.git"))
        for r in cases:
            with self.subTest(head=r.head,branch=r.branch,dirty=r.dirty,origin=r.origin):
                with self.assertRaises(mod.Stop):
                    preflight(r)
                self.assertFalse(any(a[0]==mod.SUDO for a,_ in r.calls))

    def test_root_invocation_refused(self):
        with mock.patch.object(mod.os,"geteuid",return_value=0):
            with self.assertRaisesRegex(mod.Stop,"must_run_unprivileged"):
                mod.exact_checkout(HEAD,runner=Runner())

    def test_wrong_expected_sha_rejected(self):
        with mock.patch.object(mod.os,"geteuid",return_value=1000):
            with self.assertRaisesRegex(mod.Stop,"expected_main_invalid"):
                mod.exact_checkout("notsha",runner=Runner())

    def test_git_source_mismatch_rejected_before_sudo(self):
        r=Runner(corrupted_source=True)
        with self.assertRaisesRegex(mod.Stop,"helper_source_mismatch"):
            preflight(r)
        self.assertFalse(any(a[0]==mod.SUDO for a,_ in r.calls))

    def test_ast_source_identity_static_and_wrong_fixed_target(self):
        altered=PAYLOAD.replace(b'coloring-pages-stats-v1',b'wrong-worker',1)
        with self.assertRaisesRegex(mod.Stop,"helper_identity_mismatch"):
            mod.fixed_source_constants(altered)
        other=PAYLOAD.replace(b'rpi5-ausmalwiese-worker-settings-provision',
                              b'unapproved-provision-executable',1)
        with self.assertRaisesRegex(mod.Stop,"helper_identity_mismatch"):
            mod.fixed_source_constants(other)

    def test_sudo_capability_and_version_below_min_refused(self):
        for r in (Runner(sudo_disabled=True),Runner(cp_version="9.1"),
                  Runner(cp_version="invalid")):
            with self.subTest(version=r.cp_version,disabled=r.sudo_disabled):
                with self.assertRaises(mod.Stop):
                    preflight(r)
                self.assertEqual(r.writes,0)

    def test_root_parent_symlink_or_writable_parent_refused(self):
        for r in (Runner(parent_mode="777"),Runner(parent_kind="symbolic link"),
                  Runner(parent_mode="775"),Runner(parent_mode="644")):
            with self.subTest(mode=r.parent_mode,kind=r.parent_kind):
                with self.assertRaisesRegex(mod.Stop,"unsafe_parent"):
                    preflight(r)
                self.assertEqual(r.writes,0)

    def test_existing_file_and_dangling_symlink_refused(self):
        for r in (Runner(present=True),Runner(symlink=True)):
            with self.subTest(symlink=r.symlink):
                with self.assertRaisesRegex(mod.Stop,"target_exists"):
                    preflight(r)
                self.assertEqual(r.writes,0)

    def test_privileged_preflight_read_only(self):
        r=Runner()
        preflight(r)
        self.assertEqual(r.writes,0)
        self.assertEqual([a[3] for a,_ in r.calls if a[:3]==[mod.SUDO,"-n",mod.TEST]],["-e","-L"])

    def test_postverify_hash_and_metadata(self):
        mod.post_verify(PAYLOAD,runner=Runner())
        for r,reason in ((Runner(wrong_metadata=True),"post_verify_metadata_mismatch"),
                         (Runner(wrong_sha=True),"post_verify_hash_mismatch")):
            with self.assertRaisesRegex(mod.Stop,reason):
                mod.post_verify(PAYLOAD,runner=r)

    def test_sealed_memory_mode_and_seals(self):
        info=type("Stat",(),{"st_mode":stat.S_IFREG|0o500,"st_size":len(PAYLOAD)})()
        with mock.patch.object(mod.os,"memfd_create",return_value=45), \
             mock.patch.object(mod.os,"write",return_value=len(PAYLOAD)), \
             mock.patch.object(mod.os,"fchmod") as chmod, \
             mock.patch.object(mod.os,"lseek"), \
             mock.patch.object(mod.fcntl,"fcntl") as seal, \
             mock.patch.object(mod.os,"fstat",return_value=info):
            fd=mod.sealed_memfd(PAYLOAD)
        self.assertEqual(fd,45)
        chmod.assert_called_once_with(45,0o500)
        self.assertEqual(seal.call_count,1)
        self.assertEqual(seal.call_args.args[1],mod.fcntl.F_ADD_SEALS)

    def test_memfd_preparation_failure_before_privileged_write(self):
        with mock.patch.object(mod.os,"memfd_create",side_effect=OSError), \
             mock.patch.object(mod.os,"close") as close:
            with self.assertRaisesRegex(mod.Stop,"memfd_unavailable"):
                mod.sealed_memfd(PAYLOAD)
            close.assert_not_called()

    def test_exact_one_root_copy_and_verify(self):
        r=Runner()
        with mock.patch.object(mod,"preflight",return_value=PAYLOAD), \
             mock.patch.object(mod,"sealed_memfd",return_value=45), \
             mock.patch.object(mod,"exact_checkout"), \
             mock.patch.object(mod.os,"close") as close:
            mod.apply(HEAD,runner=r)
        self.assertEqual(r.writes,1)
        self.assertEqual([a[0] for a,_ in r.calls if a[:3]==[mod.SUDO,"-n",mod.CP]], [mod.SUDO])
        close.assert_called_once_with(45)

    def test_post_dispatch_fail_stops_no_retry_or_cleanup(self):
        for r in (Runner(fail_write=True),Runner(wrong_metadata=True),
                  Runner(wrong_sha=True)):
            with self.subTest(case=(r.fail_write,r.wrong_metadata,r.wrong_sha)):
                with mock.patch.object(mod,"preflight",return_value=PAYLOAD), \
                     mock.patch.object(mod,"sealed_memfd",return_value=45), \
                     mock.patch.object(mod,"exact_checkout"), \
                     mock.patch.object(mod.os,"close"):
                    with self.assertRaisesRegex(mod.Stop,"post_dispatch_unknown_state"):
                        mod.apply(HEAD,runner=r)
                self.assertEqual(r.writes,1)
                self.assertFalse(any("/usr/bin/rm" in " ".join(a) for a,_ in r.calls))

    def test_drift_pre_dispatch_aborts_without_write(self):
        with mock.patch.object(mod,"preflight",return_value=PAYLOAD), \
             mock.patch.object(mod,"sealed_memfd",return_value=45), \
             mock.patch.object(mod,"exact_checkout",side_effect=mod.Stop("main_drift")), \
             mock.patch.object(mod.os,"close"):
            r=Runner()
            with self.assertRaisesRegex(mod.Stop,"main_drift"):
                mod.apply(HEAD,runner=r)
            self.assertEqual(r.writes,0)

    def test_confirmation_alone_does_not_authorize(self):
        with mock.patch.object(mod,"apply") as apply, \
             mock.patch("builtins.print"):
            self.assertEqual(mod.main(["--expected-main",HEAD,"--apply"]),3)
            apply.assert_not_called()

    def test_no_secret_output_or_root_python_in_source(self):
        src=SOURCE.read_text()
        self.assertNotIn("api_token",src)
        self.assertEqual(mod.CREDENTIAL_PATH, "/etc/rpi5-secrets/cloudflare/ausmalwiese-worker-settings-read.json")
        self.assertNotIn("python3 -c",src)
        self.assertNotIn("sudoers",src)
        self.assertNotIn("os.environ",src)
        self.assertNotIn("shell=True",src)

if __name__=="__main__":
    unittest.main()
