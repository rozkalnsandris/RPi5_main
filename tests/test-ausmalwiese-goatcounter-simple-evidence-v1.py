#!/usr/bin/env python3
"""Disconnected adversarial tests for #1354. All inputs synthetic."""
from copy import deepcopy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ausmalwiese_goatcounter_simple_evidence_v1 as e
from ausmalwiese_goatcounter_simple_readiness_v1 import evaluate

def sample():
    return {
        "service": {
            "source": "authorized_sanitized_host_readback",
            "version": "v2.7.0", "state": "active",
            "listener": "127.0.0.1:9194",
            "vhost": "goatcounter.ausmalwiese.invalid",
            "collect": 130,
            "collect_provenance": "separately_authorized_sanitized_readback",
        },
        "tunnel": {
            "source": "authorized_cloudflare_tunnel_read",
            "tunnel_name": "rpi5-tunnel", "config_src": "cloudflare",
            "version": 7, "owned_hosts_verified": True,
            "config": {
                "ingress": [
                    {"hostname": "ausmalwiese.de", "service": "http://127.0.0.1:9191"},
                    {"hostname": "www.ausmalwiese.de", "service": "http://127.0.0.1:9191"},
                    {"service": "http_status:404"},
                ],
            },
        },
        "worker_routes": {
            "source": "authorized_cloudflare_worker_routes_read",
            "complete": True,
            "routes": [{"pattern": "ausmalwiese.de/api/*", "script": "safe-script"}],
        },
        "worker_domains": {
            "source": "authorized_cloudflare_worker_domains_read",
            "complete": True, "domains": ["api.ausmalwiese.de"],
        },
        "ip": {
            "source": "independently_authorized_spoof_negative_proof",
            "pinned_version": "v2.7.0",
            "peer": "verified_loopback_only",
            "host_header": "verified_pinned_vhost",
            "forwarded_headers": "trusted_proxy_overwrites_untrusted_values",
            "remote_addr": "verified_real_client_after_v2_7_0_processing",
            "spoof_rejected": True, "proto": "verified_https",
        },
        "privacy": {
            "source": "separate_owner_privacy_approval",
            "approved_collect": 130,
            "notice": "reviewed_actual_processing_flow", "frontend": "off",
        },
    }

class EvidenceTests(unittest.TestCase):
    def produce(self, v):
        return e.produce(**v)

    def assert_block(self, key, subkey, value, code):
        inp = sample()
        inp[key][subkey] = value
        self.assertEqual(self.produce(inp), (code, None))

    def test_synthetic_pass_is_sanitized_only(self):
        inp = sample()
        original = deepcopy(inp)
        code, summary = self.produce(inp)
        self.assertEqual(code, "PASS_SOURCE_ONLY")
        self.assertEqual(evaluate(summary), code)
        self.assertEqual(inp, original)
        self.assertEqual(set(summary), {"schema_version", "service", "edge", "ip", "privacy"})
        self.assertNotIn("tunnel_name", str(summary))
        self.assertNotIn("safe-script", str(summary))

    def test_missing_and_unverified(self):
        for name in sample():
            x = sample()
            del x[name]
            self.assertEqual(self.produce(x), ("STOP_UNVERIFIED", None))
        self.assert_block("service", "source", "not_authorized", "STOP_UNVERIFIED")
        self.assert_block("tunnel", "source", "not_authorized", "STOP_UNVERIFIED")
        self.assert_block("worker_routes", "source", "not_authorized", "STOP_UNVERIFIED")
        self.assert_block("worker_domains", "source", "not_authorized", "STOP_UNVERIFIED")
        self.assert_block("ip", "source", "header_present_not_proof", "STOP_UNVERIFIED")
        self.assert_block("privacy", "source", "not_approved", "STOP_UNVERIFIED")

    def test_service_and_collect(self):
        for field, value in (("version", "v2.6.0"), ("state", "inactive"),
                             ("listener", "0.0.0.0:9194"), ("vhost", "ausmalwiese.de")):
            with self.subTest(field=field):
                self.assert_block("service", field, value, "STOP_SERVICE")
        self.assert_block("service", "collect_provenance", "unknown", "STOP_UNVERIFIED")
        for flag in (1, 2, 128, 131, 134, 146, 256, 386, "130", True, None):
            with self.subTest(flag=flag):
                self.assert_block("service", "collect", flag, "STOP_COLLECT")

    def test_tunnel_shape_conflicts_and_partial_routes(self):
        for key, value in (("tunnel_name", "wrong"), ("config_src", "local"),
                           ("version", True), ("version", -1),
                           ("owned_hosts_verified", False)):
            with self.subTest(key=key):
                self.assert_block("tunnel", key, value, "STOP_TUNNEL")
        x = sample()
        x["tunnel"]["config"]["originRequest"] = {"httpHostHeader": "invalid"}
        self.assertEqual(self.produce(x), ("STOP_ROUTE", None))
        x = sample()
        x["tunnel"]["config"]["ingress"].insert(0, {
            "hostname": "ausmalwiese.de", "path": "^/count$",
            "service": "http://127.0.0.1:9194",
            "originRequest": {"httpHostHeader": "goatcounter.ausmalwiese.invalid"}})
        self.assertEqual(self.produce(x), ("STOP_ROUTE", None))
        x = sample()
        x["tunnel"]["config"]["ingress"].insert(0, {"hostname": "*.ausmalwiese.de", "service": "http://127.0.0.1:8191"})
        self.assertEqual(self.produce(x), ("STOP_ROUTE", None))

    def test_worker_routes_safety(self):
        for pattern in ("ausmalwiese.de/*", "www.ausmalwiese.de/count",
                        "*ausmalwiese.de/*", "https://ausmalwiese.de/*", "*",
                        "ausmalwiese.de/COUNT", "weird/path?query"):
            with self.subTest(pattern=pattern):
                x=sample()
                x["worker_routes"]["routes"]=[{"pattern":pattern,"script":"worker"}]
                self.assertEqual(self.produce(x), ("STOP_WORKER", None))
        self.assert_block("worker_routes", "complete", False, "STOP_WORKER")
        x=sample()
        x["worker_routes"]["routes"].append({"pattern":"notknown", "script":"x", "private_token":"sensitive"})
        self.assertEqual(self.produce(x), ("STOP_WORKER", None))
        # Raw Cloudflare results must be normalized by a trusted future reader.
        x=sample()
        x["worker_routes"]["routes"]=[{"id":"private", "pattern":"x.test/*","script":"worker"}]
        self.assertEqual(self.produce(x), ("STOP_WORKER", None))

    def test_worker_route_grammar_and_query_interception(self):
        # No-script exclusion routes are also rejected if /count can match.
        for pattern in (
                "ausmalwiese.de/count*", "ausmalwiese.de/cou*",
                "*ausmalwiese.de/count", "*.ausmalwiese.de/count",
                "https://ausmalwiese.de/count",
                "http://www.ausmalwiese.de/count"):
            with self.subTest(intercept=pattern):
                inp = sample()
                inp["worker_routes"]["routes"] = [{"pattern": pattern, "script": None}]
                self.assertEqual(self.produce(inp), ("STOP_WORKER", None))

        for pattern in (
                "ausmalwiese.de/foo*bar", "ausmalwiese.de/*.jpg",
                "ausmalwiese.de/count?x=y", "Ausmalwiese.de/count",
                "ausmalwiese.de/*/count", "www.*.ausmalwiese.de/count",
                "*", "ausmalwiese.de/COUNT"):
            with self.subTest(unknown=pattern):
                inp = sample()
                inp["worker_routes"]["routes"] = [{"pattern": pattern, "script": "worker"}]
                self.assertEqual(self.produce(inp), ("STOP_WORKER", None))

        for pattern in (
                "ausmalwiese.de/api/*", "https://example.org/*",
                "www.ausmalwiese.de/assets/*",
                "*.ausmalwiese.de/api/*", "ausmalwiese.de/",
                "example.org/count", "ausmalwiese.de"):
            with self.subTest(disjoint=pattern):
                inp = sample()
                inp["worker_routes"]["routes"] = [{"pattern": pattern, "script": "worker"}]
                verdict, summary = self.produce(inp)
                self.assertEqual(verdict, "PASS_SOURCE_ONLY")
                self.assertIsNotNone(summary)

    def test_custom_domain_interception(self):
        for d in ("ausmalwiese.de", "www.ausmalwiese.de", "*.ausmalwiese.de", "", "AUSMALWIESE.DE"):
            x=sample()
            x["worker_domains"]["domains"]=[d]
            self.assertEqual(self.produce(x), ("STOP_WORKER", None))
        self.assert_block("worker_domains", "complete", False, "STOP_WORKER")

    def test_ip_trust(self):
        for key, value in (
                ("pinned_version", "v2.6.0"), ("peer", "public_port"),
                ("host_header", "wrong_host"),
                ("forwarded_headers", "visitor_supplied_xff"),
                ("remote_addr", "proxy_ip_only"),
                ("remote_addr", "cf_connecting_ip_header_only"),
                ("spoof_rejected", False), ("spoof_rejected", "true"),
                ("proto", "unknown")):
            with self.subTest(key=key):
                self.assert_block("ip", key, value, "STOP_IP_TRUST")

    def test_privacy_and_unknown(self):
        self.assert_block("privacy", "approved_collect", 131, "STOP_PRIVACY")
        self.assert_block("privacy", "notice", "draft", "STOP_PRIVACY")
        self.assert_block("privacy", "frontend", "enabled", "STOP_PRIVACY")
        x=sample()
        x["service"]["SECRET_TOKEN"] = "canary-private-string"
        self.assertEqual(self.produce(x), ("STOP_SERVICE", None))
        x=sample()
        x["tunnel"]["config"]="canary-private-string"
        self.assertEqual(self.produce(x), ("STOP_ROUTE", None))
        x=sample()
        x["worker_routes"]["routes"].append("malformed-sensitive-string")
        self.assertEqual(self.produce(x), ("STOP_WORKER", None))
        x=sample()
        x["ip"]["CF-Connecting-IP"] = "198.51.100.8"
        self.assertEqual(self.produce(x), ("STOP_IP_TRUST", None))
        x=sample()
        x["worker_domains"]["domains"]=[{"token":"canary"}]
        self.assertEqual(self.produce(x), ("STOP_WORKER", None))

if __name__ == "__main__":
    unittest.main()
