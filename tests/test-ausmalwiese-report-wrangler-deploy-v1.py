#!/usr/bin/env python3
"""Offline tests for the minimal Ausmalwiese report Wrangler deploy contract (#1104)."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_report_wrangler_deploy_v1.py"
spec = importlib.util.spec_from_file_location("report_wrangler_deploy_1104", SOURCE)
plan = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(plan)
VERSION = "12345678-1234-4234-a234-123456789abc"

def application():
    return {"schema":"ausmalwiese.report-wrangler-source.v1","repository":plan.SOURCE_REPO,"commit":plan.SOURCE_COMMIT,"worker_path":plan.WORKER_PATH,"worker_blob":plan.WORKER_BLOB,"config_path":plan.CONFIG_PATH,"config_blob":plan.CONFIG_BLOB,"config":copy.deepcopy(plan.expected_config())}

def approval():
    return {"worker":plan.WORKER,"wrangler_version":plan.WRANGLER_VERSION,"source_commit":plan.SOURCE_COMMIT,"worker_blob":plan.WORKER_BLOB,"config_blob":plan.CONFIG_BLOB,"allow_deploy_once":True}

def report_snapshot():
    return {
        "schema":"ausmalwiese.report-wrangler-post-deploy.v2","worker":plan.WORKER,
        "wrangler_version":plan.WRANGLER_VERSION,"source_commit":plan.SOURCE_COMMIT,
        "source_blob":plan.WORKER_BLOB,"config_blob":plan.CONFIG_BLOB,
        "latest_version":VERSION,"active_versions":[{"version_id":VERSION,"percentage":100}],
        "version_tag":"git:"+plan.SOURCE_COMMIT,
        "version_message":"source-commit:"+plan.SOURCE_COMMIT+",source-blob:"+plan.WORKER_BLOB+",config-blob:"+plan.CONFIG_BLOB,
        "routes":copy.deepcopy(plan.ROUTES),"binding_kinds":copy.deepcopy(plan.BINDING_KINDS),
        "observability":copy.deepcopy(plan.OBSERVABILITY),
    }

class ReportWranglerDeployTests(unittest.TestCase):
    def test_contract_is_source_only_minimal_and_has_no_stats_or_secrets(self):
        data=json.loads(plan.CONTRACT.read_text("utf-8")); plan.check_contract(data)
        self.assertEqual(data["issue"],1108); self.assertEqual(data["send_failure_diagnostic"],plan.SEND_FAILURE_DIAGNOSTIC); self.assertEqual(data["email_binding"],{"name":plan.EMAIL_BINDING_NAME,"destination_local_part":plan.DESTINATION_LOCAL_PART,"destination_domain":plan.DESTINATION_DOMAIN,"destination_source":"assembled-fixed-config"}); self.assertEqual(data["observability"],plan.OBSERVABILITY)
        self.assertFalse(data["launcher"]["requires_report_secrets"]); self.assertFalse(data["launcher"]["stats_dependency"])
        self.assertNotIn("stats_worker",data); self.assertNotIn("required_secret_names",data); self.assertNotIn("ratelimits",data)
        self.assertFalse(data["actions"]["credential_or_secret_access"]); self.assertFalse(data["actions"]["live"])
        self.assertEqual(plan.main(["--check-contract"]),0)

    def test_exact_minimal_application_repin(self):
        self.assertEqual(plan.SOURCE_COMMIT,"9a8111f19f9d82395f331ed49409af22f4765db7")
        self.assertEqual(plan.WORKER_BLOB,"384c93ae6f7348efc2dcbddbcc5a23743d8311d2")
        self.assertEqual(plan.CONFIG_BLOB,"0ddb5e8c23e0503a957d0de69e11a7d98d6651cd")

    def test_sanitized_send_failure_diagnostic_is_source_provenance_only(self):
        self.assertEqual(
            plan.SEND_FAILURE_DIAGNOSTIC,
            {
                "event":"report_email_send_failed",
                "fields":["event","code"],
                "code_pattern":"^E_[A-Z0-9_]{1,62}$",
                "fallback":"UNKNOWN",
                "source_provenance_only":True,
                "forbidden":[
                    "provider-message","stack","request-payload","activity-id",
                    "page","reason","sender","destination","headers","ip","url",
                ],
            },
        )
        self.assertIn(
            "sanitized-email-send-failure-diagnostic-by-exact-worker-blob",
            plan.expected_contract()["post_deploy_requires"],
        )

    def test_exact_reviewed_config_is_only_two_routes_and_email_binding(self):
        good=plan.expected_config(); self.assertEqual(plan.validate_config(good),good)
        self.assertEqual(good["routes"],plan.ROUTES); self.assertEqual(good["observability"],plan.OBSERVABILITY); self.assertEqual(good["send_email"][0]["name"],plan.EMAIL_BINDING_NAME)
        self.assertEqual(good["send_email"][0]["destination_address"],plan.destination_address())
        upper=copy.deepcopy(good); upper["send_email"][0]["destination_address"]=plan.DESTINATION_LOCAL_PART.upper()+"@"+plan.DESTINATION_DOMAIN
        with self.assertRaisesRegex(plan.Blocked,"CONFIG_DRIFT"): plan.validate_config(upper)
        for forbidden in ("secrets","ratelimits","vars"): self.assertNotIn(forbidden,good)
        for mutation in (
            lambda x:x.update(name="other-worker"),
            lambda x:x["routes"].append({"pattern":"ausmalwiese.de/api/report/config","zone_name":"ausmalwiese.de"}),
            lambda x:x["send_email"][0].update(name="OTHER"),
            lambda x:x["observability"]["logs"].update(enabled=False),
            lambda x:x["observability"]["traces"].update(enabled=True),
            lambda x:x.update(secrets={"required":["REPORT_TO"]}),
            lambda x:x.update(ratelimits=[]),
        ):
            bad=copy.deepcopy(good); mutation(bad)
            with self.assertRaisesRegex(plan.Blocked,"CONFIG_DRIFT"): plan.validate_config(bad)

    def test_application_provenance_is_exact(self):
        good=application(); self.assertEqual(plan.validate_application_evidence(good),good)
        for key in ("commit","worker_blob","config_blob"):
            bad=copy.deepcopy(good); bad[key]="0"*40
            with self.assertRaisesRegex(plan.Blocked,"APPLICATION_PROVENANCE_DRIFT"): plan.validate_application_evidence(bad)

    def test_deploy_command_has_no_secret_or_stats_surface(self):
        cmd=plan.deploy_command(application(),approval()); joined=" ".join(cmd)
        self.assertEqual(cmd[:4],["npx","--yes","wrangler@4.135.0","deploy"])
        self.assertIn("--strict",cmd); self.assertIn("--no-bundle",cmd)
        for forbidden in ("--secrets-file","--env-file","secret list","coloring-pages-stats-v1","/api/report/config"): self.assertNotIn(forbidden,joined)

    def test_deploy_approval_contains_no_secret_reference(self):
        self.assertEqual(plan.validate_deploy_approval(approval()),approval())
        bad=approval(); bad["wrangler_version"]="4.134.0"
        with self.assertRaisesRegex(plan.Blocked,"DEPLOY_APPROVAL_UNBOUND"): plan.validate_deploy_approval(bad)
        bad=approval(); bad["secrets_file"]="/tmp/no"
        with self.assertRaisesRegex(plan.Blocked,"DEPLOY_APPROVAL_FIELDS"): plan.validate_deploy_approval(bad)

    def test_post_deploy_snapshot_is_only_report_state(self):
        good=report_snapshot(); self.assertEqual(plan.validate_report_snapshot(good),good)
        for mutation in (
            lambda x:x["active_versions"][0].update(percentage=90),
            lambda x:x["routes"].append({"pattern":"ausmalwiese.de/*","zone_name":"ausmalwiese.de"}),
            lambda x:x["binding_kinds"].update(EXTRA="secret_text"),
            lambda x:x["binding_kinds"].update(EMAIL="plain_text"),
            lambda x:x["observability"]["logs"].update(enabled=False),
            lambda x:x["observability"]["traces"].update(enabled=True),
            lambda x:x.update(version_tag="wrong"),
        ):
            bad=report_snapshot(); mutation(bad)
            with self.assertRaises(plan.Blocked): plan.validate_report_snapshot(bad)

    def test_verification_commands_are_three_report_reads_only(self):
        joined=[" ".join(cmd) for cmd in plan.read_only_verification_commands(VERSION)]
        self.assertEqual(len(joined),3)
        self.assertTrue(any("versions list" in x for x in joined)); self.assertTrue(any("deployments list" in x for x in joined)); self.assertTrue(any("versions view "+VERSION in x for x in joined))
        for item in joined:
            self.assertNotIn(" secret "," "+item+" "); self.assertNotIn("/api/report/config",item); self.assertNotIn("coloring-pages-stats-v1",item)

    def test_fixed_launcher_dispatches_exactly_once_without_secret_file(self):
        calls=[]
        def runner(args,**kwargs):
            calls.append(list(args))
            if args[:4]==["git","-C",args[2],"rev-parse"]: return SimpleNamespace(returncode=0,stdout=plan.SOURCE_COMMIT+"\n",stderr="")
            if args[:4]==["git","-C",args[2],"ls-tree"]: return SimpleNamespace(returncode=0,stdout="100644 blob "+plan.WORKER_BLOB+"\t"+plan.WORKER_PATH+"\n100644 blob "+plan.CONFIG_BLOB+"\t"+plan.CONFIG_PATH+"\n",stderr="")
            if args[:4]==["git","-C",args[2],"diff"]: return SimpleNamespace(returncode=0,stdout="",stderr="")
            if args==["npx","--yes","wrangler@4.135.0","--version"]: return SimpleNamespace(returncode=0,stdout="4.135.0\n",stderr="")
            return SimpleNamespace(returncode=0,stdout="deployed",stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"cloudflare").mkdir(); (root/plan.WORKER_PATH).write_text("// source\n","utf-8"); (root/plan.CONFIG_PATH).write_text(json.dumps(plan.expected_config()),"utf-8")
            result=plan.execute_deploy_once(str(root),approval(),runner=runner)
        self.assertEqual(result,"DEPLOY_DISPATCH_SUCCEEDED_READ_ONLY_VERIFICATION_REQUIRED")
        deploys=[x for x in calls if x[:4]==["npx","--yes","wrangler@4.135.0","deploy"]]
        self.assertEqual(len(deploys),1); self.assertNotIn("--secrets-file",deploys[0])

    def test_failed_dispatch_is_terminal_and_source_has_no_secret_transport(self):
        calls=[]
        def runner(args,**kwargs):
            calls.append(list(args))
            if args[0]=="git" and "rev-parse" in args: return SimpleNamespace(returncode=0,stdout=plan.SOURCE_COMMIT+"\n",stderr="")
            if args[0]=="git" and "ls-tree" in args: return SimpleNamespace(returncode=0,stdout="100644 blob "+plan.WORKER_BLOB+"\t"+plan.WORKER_PATH+"\n100644 blob "+plan.CONFIG_BLOB+"\t"+plan.CONFIG_PATH+"\n",stderr="")
            if args[0]=="git" and "diff" in args: return SimpleNamespace(returncode=0,stdout="",stderr="")
            if args[-1]=="--version": return SimpleNamespace(returncode=0,stdout="4.135.0\n",stderr="")
            return SimpleNamespace(returncode=1,stdout="",stderr="redacted")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"cloudflare").mkdir(); (root/plan.WORKER_PATH).write_text("// source\n","utf-8"); (root/plan.CONFIG_PATH).write_text(json.dumps(plan.expected_config()),"utf-8")
            with self.assertRaisesRegex(plan.Blocked,"DEPLOY_DISPATCH_UNKNOWN"): plan.execute_deploy_once(str(root),approval(),runner=runner)
        self.assertEqual(len([x for x in calls if x[:4]==["npx","--yes","wrangler@4.135.0","deploy"]]),1)
        text=SOURCE.read_text("utf-8")
        for forbidden in ("/etc/rpi5-secrets","os.memfd_create","os.sendfile","STATS_WORKER","BREVO_API_KEY","REPORT_TO"): self.assertNotIn(forbidden,text)

if __name__=="__main__": unittest.main()
