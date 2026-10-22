#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, tempfile, unittest
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/"scripts/deploy-ausmalwiese-admin-v1.py"
INSTALLER=ROOT/"scripts/install-coloring-pages-admin-publish-v1.sh"
spec=importlib.util.spec_from_file_location("admin_simple_deploy",MODULE)
assert spec and spec.loader
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

SHA="a"*40

class Result:
    def __init__(self,code=0,out=b"",err=b""):self.returncode=code;self.stdout=out;self.stderr=err

class Runner:
    def __init__(self,installer_code=0,service_code=0,installer_err=b""):
        self.calls=[];self.installer_code=installer_code;self.service_code=service_code;self.installer_err=installer_err
    def __call__(self,argv,timeout_seconds=30):
        self.calls.append((tuple(argv),timeout_seconds))
        if argv[:2]==["/usr/bin/systemctl","is-active"]:return Result(self.service_code)
        if argv and argv[0]=="/usr/bin/bash":return Result(self.installer_code,err=self.installer_err)
        raise AssertionError(argv)

class Tests(unittest.TestCase):
    def test_require_source_enforces_exact_main_origin_and_clean_checkout(self):
        original=mod.git
        values={
            ("rev-parse","HEAD"):SHA,
            ("branch","--show-current"):"main",
            ("remote","get-url","origin"):mod.ORIGIN,
            ("status","--porcelain=v1","--untracked-files=all"):"",
        }
        try:
            mod.git=lambda *args:values[args]
            mod.require_source(SHA)
            values[("branch","--show-current")]="feature"
            with self.assertRaises(mod.DeployError):mod.require_source(SHA)
            values[("branch","--show-current")]="main"
            values[("remote","get-url","origin")]="https://example.invalid/repo.git"
            with self.assertRaises(mod.DeployError):mod.require_source(SHA)
            values[("remote","get-url","origin")]=mod.ORIGIN
            values[("status","--porcelain=v1","--untracked-files=all")]="?? dirty"
            with self.assertRaises(mod.DeployError):mod.require_source(SHA)
        finally:
            mod.git=original

    def test_installer_argv_is_exact_and_target_bound(self):
        self.assertEqual(mod.installer_argv(SHA),[
            "/usr/bin/bash",str(mod.INSTALLER),SHA,
            "OWNER-AUTHORIZED-AUSMALWIESE-ADMIN-ZIP-PUBLISHER-INSTALL","full"
        ])
        for bad in ("A"*40,"../x","a"*39):
            with self.assertRaises(mod.DeployError):mod.installer_argv(bad)

    def test_deploy_invokes_installer_once_then_read_only_verify(self):
        r=Runner()
        seen=[]
        def verifier(command_runner):
            seen.append("verify")
            result=command_runner(["/usr/bin/systemctl","is-active","--quiet",mod.SERVICE],10)
            if result.returncode:raise mod.DeployError("inactive")
        mod.deploy(SHA,command_runner=r,verifier=verifier)
        installer=[c for c in r.calls if c[0] and c[0][0]=="/usr/bin/bash"]
        self.assertEqual(len(installer),1)
        self.assertEqual(seen,["verify"])

    def test_installer_failure_stops_before_verify_and_no_retry(self):
        r=Runner(installer_code=1,installer_err=b"MAIN_MISMATCH\nprivate detail must not surface\n");seen=[]
        with self.assertRaisesRegex(mod.DeployError,r"reviewed ADMIN installer failed: MAIN_MISMATCH") as ctx:
            mod.deploy(SHA,command_runner=r,verifier=lambda **_kw:seen.append("verify"))
        self.assertNotIn("private detail",str(ctx.exception))
        self.assertEqual(seen,[])
        self.assertEqual(len(r.calls),1)

    def test_unknown_installer_failure_does_not_surface_raw_stderr(self):
        r=Runner(installer_code=2,installer_err=b"curl: internal diagnostic\n")
        with self.assertRaisesRegex(mod.DeployError,r"UNKNOWN_INSTALLER_FAILURE") as ctx:
            mod.deploy(SHA,command_runner=r,verifier=lambda **_kw:None)
        self.assertNotIn("curl:",str(ctx.exception))

    def test_wrapper_environment_remains_bounded(self):
        self.assertEqual(mod.ENV,{"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","LC_ALL":"C.UTF-8"})
        self.assertNotIn("SUDO_UID",mod.ENV)

    def test_installer_git_validation_uses_exact_repo_safe_directory(self):
        source=INSTALLER.read_text()
        self.assertIn('GIT=(git -c "safe.directory=$REPO" -C "$REPO")',source)
        self.assertGreaterEqual(source.count('"${GIT[@]}"'),4)
        self.assertNotIn("safe.directory=*",source)
        self.assertNotIn("git config --global",source)
        self.assertNotIn("git config --system",source)

    def test_post_verify_validates_fixed_models(self):
        r=Runner()
        payloads={
            "/api/catalog":{"catalog_sha256":"b"*64,"count":1,"entries":[{"id":"1"}]},
            "/api/archive":{"catalog_sha256":"b"*64,"count":0,"entries":[]},
            "/api/activity":{"count":2,"events":[{},{}]},
        }
        home=[]
        mod.post_verify(command_runner=r,http_get=lambda p:payloads[p],homepage_get=lambda p:home.append(p) or b"ok")
        self.assertEqual(home,["/"])
        self.assertEqual(r.calls[0][0],("/usr/bin/systemctl","is-active","--quiet",mod.SERVICE))

    def test_response_validators_fail_closed(self):
        with self.assertRaises(mod.DeployError):mod.validate_catalog({"catalog_sha256":"x","count":0,"entries":[]})
        with self.assertRaises(mod.DeployError):mod.validate_archive({"catalog_sha256":"b"*64,"count":1,"entries":[]})
        with self.assertRaises(mod.DeployError):mod.validate_activity({"count":201,"events":[]})

    def test_contract_is_narrow(self):
        c=json.loads((ROOT/"ops/contracts/ausmalwiese-admin-simple-deploy-v1.json").read_text())
        self.assertEqual(c["issue"],1176)
        self.assertFalse(c["invocation"]["arbitrary_command"])
        self.assertFalse(c["invocation"]["arbitrary_argv"])
        self.assertEqual(c["installer"]["invocations_per_attempt"],1)
        self.assertEqual(c["installer"]["mode"],"full")
        self.assertFalse(c["failure"]["automatic_retry"])
        self.assertFalse(c["failure"]["automatic_rollback"])
        self.assertFalse(c["generic_simple_deploy"]["integrated"])
        self.assertTrue(c["live"]["separate_exact_owner_authority_required"])

    def test_source_has_no_generic_execution_inputs(self):
        s=MODULE.read_text()
        self.assertNotIn("shell=True",s)
        self.assertNotIn("os.system",s)
        self.assertNotIn("urlopen",s)
        self.assertNotIn("Popen(",s)
        self.assertNotIn('add_argument("--command',s)
        self.assertNotIn('add_argument("--path',s)
        self.assertNotIn('add_argument("--env',s)

if __name__=="__main__":unittest.main()
