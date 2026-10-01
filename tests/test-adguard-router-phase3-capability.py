#!/usr/bin/env python3
import importlib.machinery,importlib.util,json,pathlib,subprocess,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
COLLECTOR=ROOT/"ops/bin/adguard-router-phase3-capability-preflight"
VERIFIER=ROOT/"ops/bin/adguard-router-phase3-capability-preflight-verify"
def load(path,name):
    loader=importlib.machinery.SourceFileLoader(name,str(path))
    spec=importlib.util.spec_from_loader(name,loader)
    m=importlib.util.module_from_spec(spec); sys.modules[name]=m; loader.exec_module(m); return m
collector=load(COLLECTOR,"phase3_collector"); verifier=load(VERIFIER,"phase3_verifier")
class T(unittest.TestCase):
    def payload(self):
        return collector.collect(["--authenticated","--expert-mode","--scope-complete","--dhcpv4-custom-dns","SUPPORTED","--ipv6-custom-dns-or-rdnss","UNSUPPORTED","--outbound-dns53-enforcement","UNSUPPORTED","--dot-enforcement","UNSUPPORTED"])
    def test_sanitized(self):
        p=self.payload(); self.assertFalse(p["mutation_started"]); self.assertTrue(all(v is False for v in p["privacy"].values()))
    def test_ready(self): self.assertEqual(verifier.verify(self.payload())["status"],"READY_PHASE3_CAPABILITY_DECISION")
    def test_unknown_blocks(self):
        p=self.payload(); p["capabilities"]["dot_enforcement"]="UNKNOWN"
        with self.assertRaisesRegex(verifier.VerifyError,"capability_unknown"): verifier.verify(p)
    def test_unauth_blocks(self):
        p=self.payload(); p["router"]["authenticated"]=False
        with self.assertRaisesRegex(verifier.VerifyError,"authenticated_inspection_required"): verifier.verify(p)
    def test_incomplete_blocks(self):
        p=self.payload(); p["router"]["relevant_scope_complete"]=False
        with self.assertRaisesRegex(verifier.VerifyError,"inspection_scope_incomplete"): verifier.verify(p)
    def test_privacy_blocks(self):
        p=self.payload(); p["privacy"]["session_material_emitted"]=True
        with self.assertRaisesRegex(verifier.VerifyError,"privacy_boundary_invalid"): verifier.verify(p)
    def test_cli_roundtrip(self):
        args=[sys.executable,str(COLLECTOR),"--authenticated","--expert-mode","--scope-complete","--dhcpv4-custom-dns","SUPPORTED","--ipv6-custom-dns-or-rdnss","UNSUPPORTED","--outbound-dns53-enforcement","UNSUPPORTED","--dot-enforcement","UNSUPPORTED"]
        c=subprocess.run(args,check=True,text=True,capture_output=True)
        v=subprocess.run([sys.executable,str(VERIFIER)],input=c.stdout,check=True,text=True,capture_output=True)
        self.assertEqual(json.loads(v.stdout)["status"],"READY_PHASE3_CAPABILITY_DECISION")
if __name__=="__main__": unittest.main()
