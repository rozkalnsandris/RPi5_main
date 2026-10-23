#!/usr/bin/env python3
"""Offline invariants for the read-only ausmalwiese.de Cloudflare crawler runbook."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "ops/contracts/ausmalwiese-crawler-policy-v1.json"
RUNBOOK = ROOT / "docs/AUSMALWIESE_GOOGLE_ONLY_CRAWLERS_V1.md"

class AusmalwieseCrawlerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.p = json.loads(POLICY.read_text(encoding="utf-8"))
        self.doc = RUNBOOK.read_text(encoding="utf-8")

    def test_exact_zone_and_source_only(self):
        p = self.p
        self.assertEqual(p["status"], "SOURCE_ONLY_NOT_APPLIED")
        self.assertEqual(p["zone"], "ausmalwiese.de")
        self.assertEqual(p["hosts"], ["ausmalwiese.de", "www.ausmalwiese.de"])
        self.assertEqual(p["plan"], "CLOUDFLARE_FREE")
        self.assertEqual(p["source_mutation_budget"], 0)
        self.assertEqual(p["execution"], "OWNER_AUTHORIZED_CLOUDFLARE_DASHBOARD_ONLY")
        self.assertEqual(p["live_approval"], "SEPARATE_EXACT_ZONE_AND_FINAL_MUTATION_LIST")

    def test_google_search_exceptions_and_explicit_blocks_are_disjoint(self):
        p = self.p
        keep = set(p["preserve_search"]) | set(p["preserve_search_console_diagnostic"])
        block = p["required_known_blocks"]
        self.assertIn("Googlebot", keep)
        self.assertIn("Googlebot-Image", keep)
        self.assertIn("Google-InspectionTool", keep)
        self.assertIn("Claude-SearchBot", block)
        self.assertIn("Bingbot", block)
        self.assertIn("OAI-SearchBot", block)
        self.assertEqual(len(block), len(set(block)))
        self.assertFalse(keep & set(block))
        self.assertNotIn("Google-Extended", keep)

    def test_fail_closed_non_google_blocks_have_no_broad_exemptions(self):
        p = self.p
        self.assertEqual(p["additional_visible_non_google_crawlers"], "INVENTORY_AND_FREEZE_BEFORE_LIVE")
        self.assertEqual(p["crawler_not_in_ui"], "UNSUPPORTED_NOT_AUTOMATICALLY_BLOCKED")
        self.assertEqual(p["verified_google_allowlist_from_user_agent"], "FORBIDDEN")
        self.assertEqual(p["global_verified_bot_skip"], "FORBIDDEN")
        self.assertEqual(p["global_search_category_block"], "FORBIDDEN")
        self.assertEqual(p["bot_fight_mode"], "KEEP_OFF")
        self.assertEqual(p["robots_txt_origin_change"], "FORBIDDEN")
        self.assertEqual(p["extra_custom_waf_rule"], "NOT_PROPOSED")
        self.assertEqual(p["live_failure"], "STOP_NO_RETRY_ROLLBACK_CLEANUP")

    def test_shared_waf_budget_and_unverified_google_images(self):
        p = self.p
        self.assertEqual(p["enforcement"], "AI_CRAWL_CONTROL_MANAGED_ONE_SHARED_WAF_CUSTOM_RULE")
        self.assertEqual(p["baseline_2026_10_12"]["custom_waf_rules_used"], 0)
        self.assertEqual(p["baseline_2026_10_12"]["custom_waf_rule_limit"], 5)
        self.assertEqual(p["baseline_2026_10_12"]["googlebot_image"], "NOT_LISTED_UNVERIFIED")
        self.assertIn("Googlebot-Image", self.doc)
        self.assertIn("Search Console", self.doc)

    def test_runbook_maintains_owner_gates_and_validations(self):
        for marker in ("NOT AUTHORIZED", "Cloudflare Free", "Claude-SearchBot",
                       "Security Events", "/api/stats/*", "/q", "/sitemap.xml",
                       "A4 print", "no-retry", "first", "separate owner LIVE authorization",
                       "rozkalns.net"):
            with self.subTest(marker=marker):
                self.assertIn(marker.lower(), self.doc.lower())

if __name__ == "__main__":
    unittest.main()
