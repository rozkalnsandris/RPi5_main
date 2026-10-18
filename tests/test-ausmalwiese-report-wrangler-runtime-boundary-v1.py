#!/usr/bin/env python3
"""Offline tests for the minimal report Wrangler installed runtime boundary."""
from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/ausmalwiese_report_wrangler_deploy_v1.py"
spec=importlib.util.spec_from_file_location("report_runtime_1092",SOURCE)
plan=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(plan)

def application():
    return {"schema":"ausmalwiese.report-wrangler-source.v1","repository":plan.SOURCE_REPO,"commit":plan.SOURCE_COMMIT,"worker_path":plan.WORKER_PATH,"worker_blob":plan.WORKER_BLOB,"config_path":plan.CONFIG_PATH,"config_blob":plan.CONFIG_BLOB,"config":copy.deepcopy(plan.expected_config())}
def directory(mode=0o755,uid=0,gid=0): return SimpleNamespace(st_mode=stat.S_IFDIR|mode,st_uid=uid,st_gid=gid,st_nlink=2,st_size=0)
def regular(mode=0o500,uid=0,gid=0,links=1,size=12000): return SimpleNamespace(st_mode=stat.S_IFREG|mode,st_uid=uid,st_gid=gid,st_nlink=links,st_size=size)
def runtime_lstat(path):
    if path==str(plan.RUNTIME_ENTRY): return regular()
    if path in {"/","/usr","/usr/local","/usr/local/sbin"}: return directory()
    raise FileNotFoundError(path)

class RuntimeBoundaryTests(unittest.TestCase):
    def test_contract_runtime_has_no_secret_or_stats_dependency(self):
        data=__import__("json").loads(plan.CONTRACT.read_text("utf-8")); plan.check_contract(data)
        self.assertFalse(data["launcher"]["requires_report_secrets"]); self.assertFalse(data["launcher"]["stats_dependency"]); self.assertEqual(data["launcher"]["runtime_operator"],"andris"); self.assertFalse(data["actions"]["credential_or_secret_access"])
    def test_runtime_constants_are_fixed(self):
        self.assertEqual(plan.RUNTIME_SOURCE_ROOT,"/home/andris/coloring-pages"); self.assertEqual(plan.RUNTIME_OPERATOR_UID,1000); self.assertEqual(plan.RUNTIME_OPERATOR_GID,1000); self.assertEqual(plan.NPX,"/usr/bin/npx")
    def test_runtime_entry_requires_root_exact_installed_file(self):
        with mock.patch.object(plan.os,"geteuid",return_value=0), mock.patch.object(plan.Path,"absolute",return_value=plan.RUNTIME_ENTRY): plan.trusted_runtime_entry(lstat=runtime_lstat)
        with mock.patch.object(plan.os,"geteuid",return_value=1000):
            with self.assertRaisesRegex(plan.Blocked,"RUNTIME_ROOT_REQUIRED"): plan.trusted_runtime_entry(lstat=runtime_lstat)
    def test_runtime_command_has_no_secret_transport(self):
        command=plan.runtime_deploy_command(application()); joined=" ".join(command)
        self.assertEqual(command[:4],["/usr/bin/npx","--yes","wrangler@4.135.0","deploy"]); self.assertNotIn("--secrets-file",joined); self.assertNotIn("/dev/stdin",joined); self.assertIn("--strict",command)
    def test_runtime_executes_wrangler_as_fixed_operator_once(self):
        calls=[]
        def runner(args,**kwargs):
            calls.append((list(args),dict(kwargs)))
            if args[-1]=="--version": return SimpleNamespace(returncode=0,stdout="4.135.0\n",stderr="")
            return SimpleNamespace(returncode=0,stdout="deployed",stderr="")
        with mock.patch.object(plan,"trusted_runtime_entry"), mock.patch.object(plan,"application_evidence_from_checkout",return_value=application()):
            result=plan.execute_root_owned_runtime_once(runner=runner)
        self.assertEqual(result,"DEPLOY_DISPATCH_SUCCEEDED_READ_ONLY_VERIFICATION_REQUIRED"); self.assertEqual(len(calls),2)
        for _,kw in calls:
            self.assertEqual(kw["user"],1000); self.assertEqual(kw["group"],1000); self.assertEqual(kw["extra_groups"],()); self.assertEqual(kw["env"],plan.RUNTIME_ENV); self.assertEqual(kw["cwd"],plan.RUNTIME_SOURCE_ROOT); self.assertEqual(kw["stdin"],plan.subprocess.DEVNULL)
        self.assertNotIn("--secrets-file",calls[1][0])
    def test_runtime_version_drift_blocks_before_deploy(self):
        calls=[]
        def runner(args,**kwargs): calls.append(list(args)); return SimpleNamespace(returncode=0,stdout="4.134.0\n",stderr="")
        with mock.patch.object(plan,"trusted_runtime_entry"), mock.patch.object(plan,"application_evidence_from_checkout",return_value=application()):
            with self.assertRaisesRegex(plan.Blocked,"WRANGLER_VERSION_DRIFT"): plan.execute_root_owned_runtime_once(runner=runner)
        self.assertEqual(len(calls),1)
    def test_runtime_failed_dispatch_is_terminal_and_not_retried(self):
        calls=[]
        def runner(args,**kwargs):
            calls.append(list(args))
            if args[-1]=="--version": return SimpleNamespace(returncode=0,stdout="4.135.0\n",stderr="")
            return SimpleNamespace(returncode=1,stdout="",stderr="redacted")
        with mock.patch.object(plan,"trusted_runtime_entry"), mock.patch.object(plan,"application_evidence_from_checkout",return_value=application()):
            with self.assertRaisesRegex(plan.Blocked,"DEPLOY_DISPATCH_UNKNOWN"): plan.execute_root_owned_runtime_once(runner=runner)
        self.assertEqual(len([x for x in calls if x[:4]==["/usr/bin/npx","--yes","wrangler@4.135.0","deploy"]]),1)
    def test_repository_copy_cannot_enter_runtime_mode(self):
        with mock.patch.object(plan.os,"geteuid",return_value=1000), mock.patch("builtins.print"): self.assertEqual(plan.main(["--runtime-deploy","--confirm",plan.RUNTIME_CONFIRM]),2)
    def test_source_contains_no_persistent_secret_access(self):
        text=SOURCE.read_text("utf-8")
        for forbidden in ("/etc/rpi5-secrets","os.memfd_create","os.sendfile","RUNTIME_SECRETS_FILE","STATS_WORKER"): self.assertNotIn(forbidden,text)
        self.assertNotIn("shell=True",text)
if __name__=="__main__": unittest.main()
