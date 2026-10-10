#!/usr/bin/env python3
"""Offline, no-network guards for the source-only zone bot WAF operator."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/cloudflare_zone_bot_waf.py"
CONTRACT = ROOT / "ops/contracts/cloudflare-zone-bot-waf-v1.json"
spec = importlib.util.spec_from_file_location("zone_bot_waf", SOURCE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def current(rules=None):
    return {"id": "a" * 32, "kind": "zone", "phase": mod.PHASE,
            "rules": [] if rules is None else rules}


def existing(rule_id="b" * 32, ref="old-rule"):
    return {"id": rule_id, "ref": ref, "action": "managed_challenge",
            "expression": 'http.request.uri.path eq "/login"', "enabled": True}


class ZoneBotWafTests(unittest.TestCase):
    def test_contract_is_source_only_zone_scoped(self):
        data = json.loads(CONTRACT.read_text("utf-8"))
        self.assertEqual(data["status"], "source-only-not-deployed")
        self.assertEqual(data["zone"], "rozkalns.net")
        self.assertEqual(data["api"]["maximum_writes"], 1)
        self.assertTrue(data["gates"]["cloudflare_mutation_separate_authorization"])
        self.assertFalse(data["production_assurances"]["user_agent_spoof_resistant"])
        self.assertFalse(data["production_assurances"]["private_data_access_control"])
        self.assertFalse(data["credentials"]["reuse_access_or_tunnel_tokens"])

    def test_expression_covers_apex_and_subdomains_without_unrelated_suffix(self):
        expression = mod.EXPRESSION
        self.assertIn('lower(http.host) eq "rozkalns.net"', expression)
        self.assertIn('ends_with(lower(http.host), ".rozkalns.net")', expression)
        for marker in ("gptbot", "claudebot", "chatgpt-user", "ccbot", "bytespider", "perplexity-user"):
            self.assertIn('lower(http.user_agent) contains "' + marker + '"', expression)
        for good in ("googlebot", "bingbot", "google-inspectiontool", "duckduckbot", "oai-searchbot", "claude-searchbot", "perplexitybot"):
            self.assertNotIn(good, expression)
        self.assertNotIn("cf.bot_management.score", expression)
        self.assertNotIn("cf.bot_management.verified_bot", expression)
        self.assertIn("request.ProxyHandler({})", SOURCE.read_text("utf-8"))

    def test_create_entrypoint_only_when_absent(self):
        mode, path, payload, before = mod.plan(None, "1" * 32)
        self.assertEqual(mode, "create_entrypoint")
        self.assertEqual(path, "/zones/" + "1" * 32 + "/rulesets")
        self.assertEqual(payload["kind"], "zone")
        self.assertEqual(payload["rules"], [mod.RULE])
        self.assertEqual(before, [])

    def test_append_preserves_preexisting_rules(self):
        snapshot = current([existing()])
        mode, path, payload, before = mod.plan(snapshot, "1" * 32)
        self.assertEqual(mode, "append_one_rule")
        self.assertEqual(path, "/zones/" + "1" * 32 + "/rulesets/" + "a" * 32 + "/rules")
        self.assertEqual(payload, mod.RULE)
        self.assertEqual(len(before), 1)
        mod.verify(current([existing(), {"id": "c" * 32, **mod.RULE}]), before)

    def test_invalid_or_conflicting_existing_rules_fail_closed(self):
        for snapshot in (current([existing(ref=mod.RULE_REF)]),
                         current([{"id": "b" * 32, **mod.RULE}]),
                         current([existing(), existing()]),
                         {**current(), "phase": "http_ratelimit"},
                         {**current(), "kind": "custom"}):
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(mod.GateError):
                    mod.plan(snapshot, "1" * 32)

    def test_read_only_verify_detects_missing_duplicate_or_drift(self):
        before = mod.plan(current([existing()]), "1" * 32)[3]
        target = {"id": "c" * 32, **mod.RULE}
        for rules in ([existing()], [target], [existing(), target, target],
                      [{**existing(), "action": "block"}, target],
                      [existing(), {**target, "enabled": False}]):
            with self.subTest(rules=rules):
                with self.assertRaises(mod.GateError):
                    mod.verify(current(rules), before)

    def test_api_path_and_root_operator_gate(self):
        for bad in ("", "not-a-zone-id", "1" * 33):
            with self.assertRaises(mod.GateError):
                mod.plan(None, bad)
        with self.assertRaises(mod.GateError):
            mod.api_call("unused", "DELETE", "/zones/" + "1" * 32)
        with self.assertRaises(mod.GateError):
            mod.api_call("unused", "GET", "/accounts/" + "1" * 32)
        with self.assertRaises(mod.GateError):
            mod.installed_credentials("1" * 40)


if __name__ == "__main__":
    unittest.main()
