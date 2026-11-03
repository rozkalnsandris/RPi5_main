#!/usr/bin/env python3
"""Offline regressions. Synthetic Cloudflare configuration only; no I/O/network."""
from copy import deepcopy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ausmalwiese_goatcounter_simple_route_v1 as m


def config():
    return {"originRequest": {}, "warp-routing": {"enabled": False}, "ingress": [
        {"hostname": "other.example", "service": "http://localhost:8000"},
        {"hostname": "ausmalwiese.de", "service": "http://127.0.0.1:9191",
         "originRequest": {"connectTimeout": 8}},
        {"hostname": "www.ausmalwiese.de", "service": "http://127.0.0.1:9191"},
        {"service": "http_status:404"},
    ]}


class SimpleRouteTests(unittest.TestCase):
    def test_exact_entries_only_and_original_unchanged(self):
        before = config()
        untouched = deepcopy(before)
        result, change = m.prepare(before)
        self.assertTrue(change)
        self.assertEqual(before, untouched)
        self.assertEqual(result["warp-routing"], before["warp-routing"])
        self.assertEqual(result["originRequest"], before["originRequest"])
        self.assertEqual([r for r in result["ingress"]
                          if r not in [m.entry(h) for h in m.HOSTS]],
                         before["ingress"])
        for host in m.HOSTS:
            scoped = [r for r in result["ingress"] if r.get("hostname") == host]
            self.assertEqual(scoped[0], m.entry(host))
            self.assertNotIn("path", scoped[1])
            self.assertEqual(scoped[0]["path"], "^/count$")
            self.assertEqual(scoped[0]["service"], "http://127.0.0.1:9194")
            self.assertEqual(scoped[0]["originRequest"],
                             {"httpHostHeader": "goatcounter.ausmalwiese.invalid"})

    def test_exact_already_installed_is_idempotent(self):
        ready, change = m.prepare(config())
        self.assertTrue(change)
        self.assertEqual(m.prepare(ready), (ready, False))

    def test_partial_state_rejected(self):
        c = config()
        c["ingress"].insert(1, m.entry(m.HOSTS[0]))
        with self.assertRaises(m.RouteError): m.prepare(c)

    def test_any_other_path_or_backend_on_public_host_is_rejected(self):
        for bad in ({"path": "^/api/.*$"},
                    {"path": "^/count/.*$"},
                    {"service": "http://127.0.0.1:9193"},
                    {"originRequest": {"httpHostHeader": "ausmalwiese.de"}}):
            c = config()
            rule = m.entry(m.HOSTS[0])
            rule.update(bad)
            c["ingress"].insert(1, rule)
            with self.subTest(bad=bad), self.assertRaises(m.RouteError):
                m.prepare(c)

    def test_wrong_order_rejected(self):
        ready, _ = m.prepare(config())
        rule = ready["ingress"].pop(1)
        ready["ingress"].insert(2, rule)
        with self.assertRaises(m.RouteError): m.prepare(ready)

    def test_matching_wildcards_and_early_catchalls_rejected(self):
        for hostname in ("*.ausmalwiese.de", "*", "", None,
                         "AUSMALWIESE.DE", "ausmalwiese.de."):
            c = config()
            c["ingress"].insert(0, {"hostname": hostname, "service": "http_status:403"})
            with self.subTest(hostname=hostname), self.assertRaises(m.RouteError):
                m.prepare(c)

    def test_duplicate_or_missing_fallback_rejected(self):
        c = config()
        c["ingress"].insert(1, deepcopy(c["ingress"][1]))
        with self.assertRaises(m.RouteError): m.prepare(c)
        c = config()
        del c["ingress"][1]
        with self.assertRaises(m.RouteError): m.prepare(c)

    def test_unsafe_fallback_and_non_loopback_rejected(self):
        for endpoint in ("http://localhost:9194", "http://127.0.0.1:9193",
                         "https://public.example", "http://0.0.0.0:8080",
                         "http://127.0.0.1:99999", "http://127.0.0.1:0"):
            c = config()
            c["ingress"][1]["service"] = endpoint
            with self.subTest(endpoint=endpoint), self.assertRaises(m.RouteError):
                m.prepare(c)

    def test_global_inheritance_and_unexpected_catchall_rejected(self):
        for global_settings in ({"httpHostHeader": "bad.example"}, None):
            c = config()
            c["originRequest"] = global_settings
            with self.assertRaises(m.RouteError): m.prepare(c)
        c = config()
        c["ingress"][-1] = {"service": "http://localhost:9194"}
        with self.assertRaises(m.RouteError): m.prepare(c)

    def test_other_host_rules_preserved(self):
        c = config()
        c["ingress"].insert(1, {"hostname": "independent.example",
                                 "path": "^/count$", "service": "http://localhost:4444"})
        out, _ = m.prepare(c)
        self.assertIn(c["ingress"][1], out["ingress"])


if __name__ == "__main__":
    unittest.main()
