#!/usr/bin/env python3
"""Offline fake-runner checks; no host or Cloudflare actions."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-ausmalwiese-worker-settings-get.py"
EXE = ROOT / "scripts/ausmalwiese_worker_settings_executor.py"
SAN = ROOT / "scripts/ausmalwiese_worker_settings_get.py"
BIND = ROOT / "ops/contracts/ausmalwiese-worker-settings-account-binding-v1.json"
spec = importlib.util.spec_from_file_location("aw_install", INSTALLER)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
SHA = "b" * 40
PIN = hashlib.sha256(b"synthetic-non-real-account").hexdigest()
VERIFIED = json.dumps({"schema_version":1,"worker":"coloring-pages-stats-v1",
    "status":"INDEPENDENTLY_VERIFIED", "account_sha256":PIN,
    "verification_evidence":"https://github.com/rozkalnsandris/RPi5_main/issues/1002#issuecomment-12345"}).encode()

class Runner:
    def __init__(self, *, branch="main", dirty=False, present=False, parent_mode="755",
                 fail_write=0, wrong_digest=False, head=SHA):
        self.calls=[]
        self.writes=0
        self.branch=branch;self.dirty=dirty;self.present=present
        self.parent_mode=parent_mode;self.fail_write=fail_write
        self.wrong_digest=wrong_digest;self.head=head

    def __call__(self, argv, *, input=None, stdout=None, stderr=None, check=False, timeout=None):
        argv=list(argv);self.calls.append((argv,input));rc=0;out=b""
        if argv[:3]==[mod.GIT,"-C",str(mod.ROOT)]:
            a=argv[3:]
            if a==["rev-parse","--show-toplevel"]:out=(str(mod.ROOT)+"\n").encode()
            elif a==["symbolic-ref","--quiet","--short","HEAD"]:out=(self.branch+"\n").encode()
            elif a==["rev-parse","HEAD"]:out=(self.head+"\n").encode()
            elif a[:2]==["status","--porcelain=v1"]:out=b" M source\n" if self.dirty else b""
            elif a==["remote","get-url","origin"]:out=b"https://github.com/rozkalnsandris/RPi5_main.git\n"
            elif a==["show","HEAD:"+mod.EXECUTOR_REL]:out=EXE.read_bytes()
            elif a==["show","HEAD:"+mod.SANITIZER_REL]:out=SAN.read_bytes()
            elif a==["show","HEAD:"+mod.BINDING_REL]:out=BIND.read_bytes()
            else:rc=2
        elif argv[:3]==[mod.SUDO,"-n",mod.STAT]:
            path=argv[-1]
            if path in mod.PARENTS:out=f"0:0:{self.parent_mode}:directory\n".encode()
            elif path==mod.RELEASE_DIR:out=b"0:0:700:directory\n"
            elif path==mod.EXECUTOR:out=b"0:0:500:regular file\n"
            elif path in (mod.SANITIZER,mod.RELEASE):out=b"0:0:400:regular file\n"
        elif argv[:3]==[mod.SUDO,"-n",mod.TEST]:
            rc=0 if self.present else 1
        elif argv[:3]==[mod.SUDO,"-n",mod.SHA256SUM]:
            path=argv[-1]
            metadata=mod.release_bytes(SHA,EXE.read_bytes(),SAN.read_bytes(),PIN)
            raw={mod.EXECUTOR:EXE.read_bytes(),mod.SANITIZER:SAN.read_bytes(),mod.RELEASE:metadata}[path]
            digest=("0"*64) if self.wrong_digest else hashlib.sha256(raw).hexdigest()
            out=f"{digest}  {path}\n".encode()
        elif argv[:3] in ([mod.SUDO,"-n",mod.MKDIR],[mod.SUDO,"-n",mod.INSTALL]):
            self.writes+=1
            if self.writes==self.fail_write:rc=42
        elif argv==[mod.SUDO,"-n",mod.TRUE]:pass
        else:rc=40
        return subprocess.CompletedProcess(argv,rc,stdout=out,stderr=b"secret must not print")

class InstallerTest(unittest.TestCase):
    def pass_preflight(self, runner):
        with mock.patch.object(mod.os,"geteuid",return_value=1000), \
             mock.patch.object(mod,"approved_account_fingerprint",return_value=PIN):
            return mod.preflight(SHA,runner=runner)

    def test_account_binding_not_yet_approved(self):
        obj=json.loads(BIND.read_text())
        self.assertEqual(obj["status"],"PENDING_INDEPENDENT_VERIFICATION")
        self.assertIsNone(obj["account_sha256"])
        with self.assertRaisesRegex(mod.Stop,"account_binding_unverified"):
            mod.approved_account_fingerprint(BIND.read_bytes())

    def test_independently_verified_fixture_accepted(self):
        self.assertEqual(mod.approved_account_fingerprint(VERIFIED),PIN)
        for raw in (b"{}",b'{"account_sha256":"dead"}', VERIFIED.replace(b"INDEPENDENTLY_VERIFIED",b"UNVERIFIED")):
            with self.assertRaises(mod.Stop):
                mod.approved_account_fingerprint(raw)

    def test_preflight_synthetic_clean_snapshot(self):
        r=Runner()
        exe,san,meta=self.pass_preflight(r)
        self.assertEqual(exe,EXE.read_bytes())
        self.assertEqual(san,SAN.read_bytes())
        self.assertEqual(json.loads(meta)["account_sha256"],PIN)
        self.assertEqual(r.writes,0)
        self.assertEqual([x for x in r.calls if x[0][:3]==[mod.SUDO,"-n",mod.TEST]].__len__(),8)

    def test_root_checkout_forbidden(self):
        with mock.patch.object(mod.os,"geteuid",return_value=0):
            with self.assertRaisesRegex(mod.Stop,"installer_must_be_unprivileged"):
                mod.checked_checkout(SHA,runner=Runner())

    def test_dirty_drift_and_branch_stop_before_writes(self):
        for r in (Runner(dirty=True),Runner(branch="other"),Runner(head="c"*40)):
            with self.subTest(reason=(r.dirty,r.branch,r.head)):
                with self.assertRaises(mod.Stop):
                    self.pass_preflight(r)
                self.assertEqual(r.writes,0)

    def test_parent_or_existing_symlink_blocks(self):
        for r in (Runner(parent_mode="777"),Runner(present=True)):
            with self.assertRaises(mod.Stop):self.pass_preflight(r)
            self.assertEqual(r.writes,0)

    def test_invalid_source_snapshot_rejected(self):
        with mock.patch.object(mod,"git",return_value=b"different"):
            with self.assertRaises(mod.Stop):
                mod.tracked_snapshot(mod.EXECUTOR_REL,runner=Runner())

    def test_release_pins_exact_both_hashes_no_credentials(self):
        raw=mod.release_bytes(SHA,b"exe-bytes",b"san-bytes",PIN)
        obj=json.loads(raw)
        self.assertEqual(obj["executor_sha256"],hashlib.sha256(b"exe-bytes").hexdigest())
        self.assertEqual(obj["sanitizer_sha256"],hashlib.sha256(b"san-bytes").hexdigest())
        self.assertEqual(obj["source_sha"],SHA)
        self.assertNotIn(b"api_token",raw)

    def test_install_four_fixed_mutations_only(self):
        r=Runner()
        with mock.patch.object(mod,"preflight",return_value=(EXE.read_bytes(),SAN.read_bytes(),mod.release_bytes(SHA,EXE.read_bytes(),SAN.read_bytes(),PIN))):
            mod.apply(SHA,runner=r)
        writes=[(a,body) for a,body in r.calls if a[:3] in ([mod.SUDO,"-n",mod.MKDIR],[mod.SUDO,"-n",mod.INSTALL])]
        self.assertEqual(len(writes),4)
        self.assertEqual(writes[0][0][-1],mod.RELEASE_DIR)
        self.assertEqual([a[-1] for a,_ in writes[1:]], [mod.EXECUTOR,mod.SANITIZER,mod.RELEASE])
        self.assertTrue(all(a[0]==mod.SUDO for a,_ in writes))
        self.assertNotIn("shell=True",INSTALLER.read_text())

    def test_each_failed_mutation_stops_no_retry(self):
        for i in (1,2,3,4):
            r=Runner(fail_write=i)
            with mock.patch.object(mod,"preflight",return_value=(EXE.read_bytes(),SAN.read_bytes(),b"fake-metadata")):
                with self.assertRaisesRegex(mod.Stop,"post_dispatch_unknown_state"):
                    mod.apply(SHA,runner=r)
            self.assertEqual(r.writes,i)
            self.assertFalse(any("/usr/bin/rm" in a for a,_ in r.calls))

    def test_post_verify_hash_mismatch_stops(self):
        r=Runner(wrong_digest=True)
        with mock.patch.object(mod,"preflight",return_value=(EXE.read_bytes(),SAN.read_bytes(),mod.release_bytes(SHA,EXE.read_bytes(),SAN.read_bytes(),PIN))):
            with self.assertRaisesRegex(mod.Stop,"post_dispatch_unknown_state"):
                mod.apply(SHA,runner=r)
        self.assertEqual(r.writes,4)

    def test_cli_apply_without_confirm_blocks(self):
        with mock.patch.object(mod,"apply") as target, mock.patch("builtins.print"):
            rc=mod.main(["--expected-main",SHA,"--apply"])
        self.assertEqual(rc,3)
        target.assert_not_called()

    def test_scope_fixed_and_no_privileged_python(self):
        src=INSTALLER.read_text()
        for needle in ("sudoers","python3 -c","shell=True","CLOUDFLARE_API_TOKEN"):
            self.assertNotIn(needle,src)
        self.assertEqual(mod.TARGETS,(mod.EXECUTOR,mod.RELEASE_DIR,mod.SANITIZER,mod.RELEASE))
        self.assertEqual(mod.CONFIRM,"INSTALL-AUSMALWIESE-WORKER-SETTINGS-GET")

if __name__=="__main__":
    unittest.main()
