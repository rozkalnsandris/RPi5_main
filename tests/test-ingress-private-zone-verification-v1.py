#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
CONTRACT_PATH=ROOT/"ops/contracts/private-zone-verification-v1.json"
REGISTRY_PATH=ROOT/"ops/contracts/ingress-registry-v1.json"
POLICY_PATH=ROOT/"ops/contracts/cloudflare-hostname-policy.yaml"
WORKFLOW_PATH=ROOT/".github/workflows/cloudflare-phase5-private-external.yml"
ROUTE_WORKFLOW_PATH=ROOT/".github/workflows/deals-9128-route-cutover.yml"

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
external=load("phase5_external",ROOT/"scripts/cloudflare_phase5_private_external_actions.py")
bridge=load("phase5_bridge",ROOT/"scripts/github_phase5_private_external_bridge.py")
host=load("phase5_host",ROOT/"scripts/phase5_private_host_isolation.py")
receipt=load("phase5_receipt",ROOT/"scripts/phase5_private_authorized_path_receipt.py")
SHA="a"*40
OWNER_ID=277435981

def event(body,app=False):
    return {"action":"created","issue":{"number":866},"comment":{"id":123,"body":body,"author_association":"OWNER","performed_via_github_app":{"id":1} if app else None,"user":{"login":"rozkalnsandris","id":OWNER_ID,"type":"User"}},"sender":{"login":"rozkalnsandris","id":OWNER_ID,"type":"User"}}

class Phase5PrivateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract=json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.registry_json=json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.registry=external.load_registry(POLICY_PATH)

    def fake_state(self,domain="deals.rozkalns.net",decision="allow"):
        app_id="00000000-1111-4111-8111-000000000001"
        return {"organization":{},"apps":[{"id":app_id,"type":"self_hosted","domain":domain,"aud":"secret-aud"}],"policies":{app_id:[{"decision":decision,"include":[{"email":{"email":"private_identity_redacted"}}]}]}}

    def test_contract_derives_exact_private_set_and_distinguishes_zones(self):
        private=[x for x in self.registry_json["services"] if x["zone"]=="PRIVATE"]
        self.assertEqual([x["service_id"] for x in private],["hermes-deals"])
        self.assertEqual(self.contract["private_service_selection"]["expected_service_ids"],["hermes-deals"])
        self.assertEqual(self.contract["policy_semantics"]["registry_access_class"],"PRIVATE")
        self.assertEqual(self.contract["policy_semantics"]["hostname_policy_trust_class"],"FAMILY_PRIVATE")
        self.assertFalse(self.contract["policy_semantics"]["public_inheritance_allowed"])
        self.assertFalse(self.contract["policy_semantics"]["admin_scope_overlap_allowed"])

    def test_external_exact_family_scope_and_challenge_pass_sanitized(self):
        report=external.build_report(self.contract,self.registry,self.registry_json,self.fake_state(), "access-challenge")
        self.assertEqual(report["result"],"PASS")
        item=report["services"][0]
        self.assertEqual(item["access_scope_class"],"exact-or-narrow-family")
        self.assertFalse(item["alternate_public_bypass_present"])
        self.assertFalse(item["admin_or_public_scope_overlap_present"])
        rendered=json.dumps(report,sort_keys=True)
        self.assertNotIn("private_identity_redacted",rendered); self.assertNotIn("secret-aud",rendered)

    def test_wildcard_covering_admin_or_public_fails(self):
        report=external.build_report(self.contract,self.registry,self.registry_json,self.fake_state("*.rozkalns.net"),"access-challenge")
        self.assertEqual(report["services"][0]["access_scope_class"],"broader-than-private")
        self.assertTrue(report["services"][0]["admin_or_public_scope_overlap_present"])
        self.assertEqual(report["services"][0]["result"],"FAIL")

    def test_public_or_bypass_fails(self):
        public=external.build_report(self.contract,self.registry,self.registry_json,self.fake_state(),"public")
        self.assertEqual(public["services"][0]["result"],"FAIL")
        bypass=external.build_report(self.contract,self.registry,self.registry_json,self.fake_state(decision="bypass"),"access-challenge")
        self.assertTrue(bypass["services"][0]["alternate_public_bypass_present"])
        self.assertEqual(bypass["services"][0]["result"],"FAIL")

    def test_owner_command_is_exact_sha_bound_and_app_authored_rejected(self):
        body=f"/rpi5-p5-private-external check HEAD={SHA} CANARY=phase5-private-external-v1"
        out=bridge.authorize_event(event(body),repository="rozkalnsandris/RPi5_main",github_sha=SHA,run_attempt="1")
        self.assertEqual(out["expected_sha"],SHA)
        with self.assertRaisesRegex(bridge.AuthorizationError,"app_authored_comment_forbidden"):
            bridge.authorize_event(event(body,True),repository="rozkalnsandris/RPi5_main",github_sha=SHA,run_attempt="1")

    def test_host_loopback_absent_lan_passes(self):
        lan="10.99.0.2"; port=self.contract["host_verifier"]["probe_port"]
        original=host._lan_path
        try:
            host._lan_path=lambda _lan,_port:"absent"
            report=host.build_report(expected_main=SHA,contract=self.contract,listeners={port:{"127.0.0.1"}},lan_address=lan)
        finally:
            host._lan_path=original
        self.assertEqual(report["result"],"PASS")
        self.assertEqual(report["services"][0]["listener_bind_class"],"loopback")
        self.assertEqual(report["services"][0]["lan_path_class"],"absent")

    def test_host_wildcard_or_lan_path_fails(self):
        lan="10.99.0.2"; port=self.contract["host_verifier"]["probe_port"]
        original=host._lan_path
        try:
            host._lan_path=lambda _lan,_port:"present"
            report=host.build_report(expected_main=SHA,contract=self.contract,listeners={port:{"0.0.0.0"}},lan_address=lan)
        finally:
            host._lan_path=original
        self.assertEqual(report["result"],"BLOCKED")

    def test_protected_receipt_is_bounded(self):
        projected=self.contract["service_projections"][0]
        payload={"source_main_sha":SHA,"service":{"service_id":projected["service_id"],"hostname":projected["hostname"],"authorized_private_result":"PASS"}}
        service=receipt.validate_submission(payload,projected,SHA)
        self.assertEqual(receipt.build_report(SHA,service)["result"],"PASS")
        payload["service"]["cookie"]="forbidden"
        with self.assertRaises(receipt.ReceiptError): receipt.validate_submission(payload,projected,SHA)

    def test_workflow_uses_only_existing_p1d03_read_lane(self):
        wf=WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("CLOUDFLARE_P1D03_ACCOUNT_ID",wf); self.assertIn("CLOUDFLARE_P1D03_READ_API_TOKEN",wf)
        for forbidden in ("CLOUDFLARE_TUNNEL_API_TOKEN","CLOUDFLARE_WRITE_API_TOKEN","workflow_dispatch"):
            self.assertNotIn(forbidden,wf)

    def test_route_origin_reuses_existing_v19_verify_only(self):
        route=self.contract["route_origin_verifier"]
        self.assertEqual(route["allowed_phase5_operation"],"verify-loopback")
        self.assertFalse(route["config_mutation_allowed_during_verify"])
        self.assertFalse(route["new_tunnel_credential_consumer_created"])
        wf=ROUTE_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn('"check","cutover","verify-loopback"',wf)
        self.assertIn("scripts/cloudflare_deals_route.py",wf)

    def test_source_is_non_authorizing_and_privacy_bounded(self):
        a=self.contract["authority"]
        for k in ("source_merge_proves_runtime_state","source_merge_authorizes_runtime_verification","source_merge_authorizes_protected_private_verification","source_merge_authorizes_cloudflare_write","source_merge_authorizes_live_mutation"):
            self.assertFalse(a[k])
        source=(ROOT/"scripts/phase5_private_host_isolation.py").read_text(encoding="utf-8")
        for forbidden in ("docker inspect","docker logs","systemctl","journalctl","ufw ","nft ","iptables",".env"):
            self.assertNotIn(forbidden,source)

if __name__=="__main__": unittest.main()
