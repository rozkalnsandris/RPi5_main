#!/usr/bin/env python3
"""Offline contract tests only; never import Cloudflare credentials or call APIs."""
import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-legacy-redirect-v1.json"
DOC = ROOT / "docs/AUSMALWIESE_LEGACY_REDIRECT_V1.md"


def illustrative_map(url):
    """Hypothetical rule mapping; NOT a Cloudflare implementation or LIVE proof."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.netloc != "coloring.rozkalns.net":
        return None
    return urlunsplit(("https", "ausmalwiese.de", parts.path or "/", parts.query, parts.fragment))


class LegacyDomainRedirectSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_fixed_zone_host_rule_and_target(self):
        cfg = self.contract
        self.assertEqual(cfg["schema"], "rozkalns.rpi5-main.ausmalwiese-legacy-redirect.v1")
        self.assertEqual(cfg["status"] if "status" in cfg else cfg["state"],
                         "SOURCE_REVIEW_ONLY_NO_LIVE_OR_CREDENTIAL_AUTHORITY")
        self.assertEqual(cfg["issue"], {"repository": "rozkalnsandris/RPi5_main", "number": 996})
        self.assertEqual(cfg["zone"], "rozkalns.net")
        self.assertEqual(cfg["source_hostname"], "coloring.rozkalns.net")
        self.assertEqual(cfg["destination_origin"], "https://ausmalwiese.de")
        self.assertEqual(cfg["phase"], "http_request_dynamic_redirect")
        rule = cfg["rule_candidate"]
        self.assertEqual(rule, {
            "matcher": "wildcard",
            "request_url": "http*://coloring.rozkalns.net/*",
            "target_url": "https://ausmalwiese.de/${2}",
            "action": "redirect",
            "status_code": 301,
            "preserve_query_string": True,
        })

    def test_static_source_grants_no_cloudflare_or_host_write_authority(self):
        cfg = self.contract
        self.assertTrue(all(v is False for v in cfg["live_authority"].values()))
        self.assertFalse(cfg["runtime_evidence"]["legacy_edge_redirect_active"])
        self.assertFalse(cfg["runtime_evidence"]["cloudflare_ruleset_inventory_verified"])
        for forbidden in ("api_token", "secret_value", "apply_command", "authorization_token"):
            self.assertNotIn(forbidden, cfg)
        text = DOC.read_text(encoding="utf-8")
        for term in ("separate", "no retry", "owner", "source PR merge never permits LIVE"):
            self.assertIn(term.lower(), text.lower())

    def test_paths_queries_and_exact_old_host_only(self):
        cases = [
            ("https://coloring.rozkalns.net/", "https://ausmalwiese.de/"),
            ("http://coloring.rozkalns.net/?campaign=kita-01",
             "https://ausmalwiese.de/?campaign=kita-01"),
            ("https://coloring.rozkalns.net/detail.html?id=1234567&campaign=x",
             "https://ausmalwiese.de/detail.html?id=1234567&campaign=x"),
            ("https://coloring.rozkalns.net/print.html?id=1234567",
             "https://ausmalwiese.de/print.html?id=1234567"),
            ("https://coloring.rozkalns.net/media/1234567/print.png",
             "https://ausmalwiese.de/media/1234567/print.png"),
            ("https://coloring.rozkalns.net/api/stats/rankings",
             "https://ausmalwiese.de/api/stats/rankings"),
            ("https://coloring.rozkalns.net/health",
             "https://ausmalwiese.de/health"),
            ("https://coloring.rozkalns.net/ready",
             "https://ausmalwiese.de/ready"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(illustrative_map(source), expected)
        for other in (
            "https://ausmalwiese.de/",
            "https://www.ausmalwiese.de/",
            "https://rozkalns.net/",
            "https://home.rozkalns.net/path",
            "https://coloring.rozkalns.net.attacker.example/",
            "https://evil.test/?next=https://coloring.rozkalns.net/",
        ):
            with self.subTest(unrelated=other):
                self.assertIsNone(illustrative_map(other))

    def test_fail_closed_external_dependencies_and_health_monitor_gate(self):
        cfg = self.contract
        blockers = set(cfg["preflight_gates"])
        for required in (
            "owner_reviewed_existing_rozkalns_net_redirect_inventory_and_order",
            "separate_exact_owner_live_authorization_for_redirect_write",
            "coloring_pages_pr_214_reviewed_merged_and_new_host_deployed",
            "new_host_robots_and_runtime_sitemap_urls_catalog_consistent",
            "new_host_stats_get_post_and_q_worker_compatibility_verified",
            "legacy_health_ready_monitors_retargeted_or_approved_exception",
        ):
            self.assertIn(required, blockers)
        self.assertEqual(len(blockers), len(cfg["preflight_gates"]))
        self.assertEqual(len(cfg["impact_paths"]), len(set(cfg["impact_paths"])))
        self.assertIn("/api/stats/print", cfg["impact_paths"])
        self.assertIn("/health", cfg["impact_paths"])
        self.assertIn("/ready", cfg["impact_paths"])


if __name__ == "__main__":
    unittest.main()
