#!/usr/bin/env python3
import importlib.machinery, importlib.util, json, pathlib, subprocess, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "ops/bin/adguard-dhcpv4-migration-preflight"
VERIFIER = ROOT / "ops/bin/adguard-dhcpv4-migration-preflight-verify"

def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module

collector = load(COLLECTOR, "dhcp4_collector")
verifier = load(VERIFIER, "dhcp4_verifier")

ARGS = [
    "--router-dhcpv4-enabled",
    "--single-active-dhcpv4-authority",
    "--adguard-dhcp-available",
    "--adguard-dhcpv4-disabled",
    "--rpi5-static-lan-identity",
    "--dhcpv4-firewall-ready",
    "--candidate-gateway-matches-router",
    "--candidate-subnet-matches-lan",
    "--candidate-pool-valid",
    "--candidate-pool-excludes-infra",
    "--candidate-dns-is-rpi5-only",
    "--ipv6-unchanged",
    "--adguard-dns-healthy",
    "--candidate-parameter-fingerprint", "0123456789abcdef",
]

class T(unittest.TestCase):
    def payload(self):
        return collector.collect(ARGS)

    def test_ready(self):
        out = verifier.verify(self.payload())
        self.assertEqual(out["status"], "READY_PHASE4_DHCPV4_MIGRATION")
        self.assertEqual(out["max_forward_writes"], 3)

    def test_cutover_order(self):
        out = verifier.verify(self.payload())
        self.assertEqual(out["cutover_order"], [
            "STAGE_ADGUARD_DHCPV4_DISABLED",
            "DISABLE_ULTRAHUB_DHCPV4",
            "ENABLE_ADGUARD_DHCPV4",
        ])

    def test_baseline_blocks(self):
        p = self.payload()
        p["baseline"]["router_dhcpv4_enabled"] = False
        with self.assertRaisesRegex(verifier.VerifyError, "baseline_not_ready"):
            verifier.verify(p)

    def test_firewall_readiness_false_blocks(self):
        p = self.payload()
        p["baseline"]["dhcpv4_firewall_ready"] = False
        with self.assertRaisesRegex(verifier.VerifyError, "baseline_not_ready"):
            verifier.verify(p)

    def test_firewall_readiness_missing_blocks(self):
        p = self.payload()
        del p["baseline"]["dhcpv4_firewall_ready"]
        with self.assertRaisesRegex(verifier.VerifyError, "baseline_not_ready"):
            verifier.verify(p)

    def test_candidate_blocks(self):
        p = self.payload()
        p["candidate"]["pool_excludes_infra"] = False
        with self.assertRaisesRegex(verifier.VerifyError, "candidate_not_ready"):
            verifier.verify(p)

    def test_privacy_blocks(self):
        p = self.payload()
        p["privacy"]["client_identity_emitted"] = True
        with self.assertRaisesRegex(verifier.VerifyError, "privacy_boundary_invalid"):
            verifier.verify(p)

    def test_fingerprint_blocks(self):
        p = self.payload()
        p["candidate"]["parameter_fingerprint"] = "raw-address"
        with self.assertRaisesRegex(verifier.VerifyError, "candidate_fingerprint_invalid"):
            verifier.verify(p)

    def test_cli_roundtrip(self):
        c = subprocess.run([sys.executable, str(COLLECTOR), *ARGS], check=True, text=True, capture_output=True)
        v = subprocess.run([sys.executable, str(VERIFIER)], input=c.stdout, check=True, text=True, capture_output=True)
        self.assertEqual(json.loads(v.stdout)["status"], "READY_PHASE4_DHCPV4_MIGRATION")

if __name__ == "__main__":
    unittest.main()
