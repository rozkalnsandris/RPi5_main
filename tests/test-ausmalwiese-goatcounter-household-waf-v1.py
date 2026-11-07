#!/usr/bin/env python3
"""Offline disconnected tests for Ausmalwiese household /count WAF source."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "ausmalwiese_goatcounter_household_waf_v1.py"
CONTRACT = ROOT / "ops" / "contracts" / "ausmalwiese-household-count-waf-v1.json"
spec = importlib.util.spec_from_file_location("household_waf", SOURCE)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


def current(rules=None):
    return {
        "id": "a" * 32,
        "kind": "zone",
        "phase": m.PHASE,
        "rules": [] if rules is None else rules,
    }


def existing(rule_id="b" * 32, ref="old-rule"):
    return {
        "id": rule_id,
        "ref": ref,
        "action": "managed_challenge",
        "expression": 'http.request.uri.path eq "/login"',
        "enabled": True,
    }


class HouseholdWafTests(unittest.TestCase):
    def test_contract_matches_source_and_privacy_boundary(self):
        import json
        data = json.loads(CONTRACT.read_text("utf-8"))
        self.assertEqual(data["zone"], m.ZONE_NAME)
        self.assertEqual(data["hosts"], list(m.HOSTS))
        self.assertEqual(data["path"], m.PATH)
        self.assertEqual(data["phase"], m.PHASE)
        self.assertEqual(data["rule_ref"], m.RULE_REF)
        self.assertEqual(data["provider"]["maximum_writes"], 1)
        self.assertTrue(data["privacy"]["sanitized_receipts_only"])
        self.assertTrue(data["privacy"]["cloudflare_rule_stores_address_material_if_live_approved"])
        self.assertFalse(data["privacy"]["github_raw_household_address_storage"])
        self.assertFalse(data["credentials"]["reuse_tunnel_credentials"])
        self.assertFalse(data["installed_operator"]["installer_in_this_outcome"])

    def test_constants_are_exact_scope(self):
        self.assertEqual(m.ZONE_NAME, "ausmalwiese.de")
        self.assertEqual(m.HOSTS, ("ausmalwiese.de", "www.ausmalwiese.de"))
        self.assertEqual(m.PATH, "/count")
        self.assertEqual(m.PHASE, "http_request_firewall_custom")
        self.assertEqual(m.MAX_FREE_RULES, 5)

    def test_normalizes_public_exact_and_bounded_cidr(self):
        good = ["8.8.8.8", "2606:4700:4700::1111", "8.8.8.0/24", "2606:4700:4700::/48"]
        out = m.normalize_sources(good)
        self.assertEqual(set(out), set(good))
        self.assertEqual(m.source_shape(out), {
            "exact_ipv4": 1, "exact_ipv6": 1,
            "cidr_ipv4": 1, "cidr_ipv6": 1, "total": 4,
        })

    def test_rejects_private_special_noncanonical_and_overbroad(self):
        bad = [
            "127.0.0.1", "10.0.0.1", "169.254.1.1", "224.0.0.1", "0.0.0.0",
            "::1", "fe80::1", "ff02::1", "8.8.8.0/8", "2606:4700::/32",
            "2606:4700:4700:0:0:0:0:1111", "2606:4700:4700::1%eth0", " 8.8.8.8",
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(m.GateError):
                    m.normalize_source(value)

    def test_rejects_empty_duplicates_and_too_many(self):
        for values in ([], ["8.8.8.8", "8.8.8.8"], ["8.8.8.8"] * 9):
            with self.subTest(values=values):
                with self.assertRaises(m.GateError):
                    m.normalize_sources(values)

    def test_expression_is_only_hosts_count_and_ip_set(self):
        values = m.normalize_sources(["8.8.8.8", "2606:4700:4700::/48"])
        expression = m.build_expression(values)
        self.assertIn('http.host eq "ausmalwiese.de"', expression)
        self.assertIn('http.host eq "www.ausmalwiese.de"', expression)
        self.assertIn('http.request.uri.path eq "/count"', expression)
        self.assertIn("ip.src in {", expression)
        self.assertNotIn("wildcard", expression)
        self.assertNotIn("starts_with", expression)
        self.assertNotIn("ends_with", expression)
        self.assertNotIn("http.user_agent", expression)

    def test_create_entrypoint_when_absent(self):
        values = m.normalize_sources(["8.8.8.8"])
        mode, path, payload, before = m.plan(None, "1" * 32, values)
        self.assertEqual(mode, "create_entrypoint")
        self.assertEqual(path, "/zones/" + "1" * 32 + "/rulesets")
        self.assertEqual(before, [])
        self.assertEqual(payload["kind"], "zone")
        self.assertEqual(payload["phase"], m.PHASE)
        self.assertEqual(len(payload["rules"]), 1)
        self.assertEqual(payload["rules"][0]["action"], "block")

    def test_append_preserves_existing_rule_order(self):
        values = m.normalize_sources(["8.8.8.8"])
        before_rules = [existing("b"*32), existing("c"*32, "second")]
        mode, path, payload, before = m.plan(current(before_rules), "1"*32, values)
        self.assertEqual(mode, "append_one_rule")
        self.assertEqual(path, "/zones/" + "1"*32 + "/rulesets/" + "a"*32 + "/rules")
        self.assertEqual(payload["ref"], m.RULE_REF)
        after = current(before_rules + [{"id": "d"*32, **payload}])
        m.verify(after, before, values)

    def test_duplicate_or_conflicting_rule_ref_expression_is_rejected(self):
        values = m.normalize_sources(["8.8.8.8"])
        target = m.target_rule(values)
        cases = [
            current([{"id": "b"*32, **target}]),
            current([{"id": "b"*32, "ref": m.RULE_REF, "action": "block",
                      "expression": "ip.src eq 8.8.4.4", "enabled": True}]),
            current([{"id": "b"*32, "ref": "other", "action": "block",
                      "expression": target["expression"], "enabled": True}]),
        ]
        for snapshot in cases:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(m.GateError):
                    m.plan(snapshot, "1"*32, values)

    def test_free_rule_capacity_fails_closed(self):
        values = m.normalize_sources(["8.8.8.8"])
        rules = [existing(f"{i:032x}", f"r{i}") for i in range(m.MAX_FREE_RULES)]
        with self.assertRaises(m.GateError):
            m.plan(current(rules), "1"*32, values)

    def test_verify_rejects_prior_rule_drift_or_wrong_target(self):
        values = m.normalize_sources(["8.8.8.8"])
        old = existing()
        _, _, payload, before = m.plan(current([old]), "1"*32, values)
        target = {"id": "c"*32, **payload}
        bad = [
            current([target]),
            current([{**old, "action": "block"}, target]),
            current([old, {**target, "enabled": False}]),
            current([old, target, target]),
        ]
        for snapshot in bad:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(m.GateError):
                    m.verify(snapshot, before, values)

    def test_api_is_get_post_zone_rulesets_only(self):
        with self.assertRaises(m.GateError):
            m.api_call("unused", "DELETE", "/zones/" + "1"*32)
        with self.assertRaises(m.GateError):
            m.api_call("unused", "GET", "/accounts/" + "1"*32)
        with self.assertRaises(m.GateError):
            m.api_call("unused", "POST", "/zones/" + "1"*32 + "/dns_records")

    def test_preflight_executes_zero_writes_and_sanitizes_output(self):
        values = m.normalize_sources(["8.8.8.8", "2606:4700:4700::/48"])
        with mock.patch.object(m, "installed_credentials", return_value=("1"*32, "token-value-123456")), \
             mock.patch.object(m, "read_household_sources", return_value=values), \
             mock.patch.object(m, "api_call", side_effect=[
                 (200, {"id": "1"*32, "name": m.ZONE_NAME}),
                 (200, current([existing()])),
             ]) as api:
            result = m.execute("a"*40, False)
        self.assertEqual(result["writes"], 0)
        self.assertEqual(result["existing_rules"], 1)
        self.assertEqual(result["source_shape"]["total"], 2)
        self.assertNotIn("8.8.8.8", str(result))
        self.assertNotIn("2606:4700", str(result))
        self.assertEqual([call.args[1] for call in api.call_args_list], ["GET", "GET"])

    def test_apply_has_one_write_then_get_verification(self):
        values = m.normalize_sources(["8.8.8.8"])
        _, _, payload, _ = m.plan(current([existing()]), "1"*32, values)
        after = current([existing(), {"id": "c"*32, **payload}])
        calls = []
        def api(token, method, path, payload=None):
            calls.append((method, path))
            if len(calls) == 1:
                return 200, {"id": "1"*32, "name": m.ZONE_NAME}
            if len(calls) == 2:
                return 200, current([existing()])
            if len(calls) == 3:
                self.assertEqual(method, "POST")
                return 200, {"id": "c"*32}
            if len(calls) == 4:
                return 200, after
            raise AssertionError("too many calls")
        with mock.patch.object(m, "installed_credentials", return_value=("1"*32, "token-value-123456")), \
             mock.patch.object(m, "read_household_sources", return_value=values), \
             mock.patch.object(m, "api_call", side_effect=api):
            result = m.execute("a"*40, True)
        self.assertEqual(result["writes_attempted"], 1)
        self.assertEqual([x[0] for x in calls], ["GET", "GET", "POST", "GET"])
        self.assertNotIn("8.8.8.8", str(result))

    def test_offline_plan_contains_no_address_material(self):
        result = m.offline_plan()
        self.assertEqual(result["writes"], 0)
        self.assertEqual(result["household_input"], "hidden_local_tty_only")
        text = str(result)
        self.assertNotIn("8.8.8.8", text)
        self.assertNotIn("2606:", text)

    def test_source_does_not_accept_household_address_cli_or_environment(self):
        source = SOURCE.read_text("utf-8")
        self.assertIn('getpass.getpass(', source)
        self.assertNotIn('add_argument("--source"', source)
        self.assertNotIn('os.environ', source)

    def test_main_error_output_is_fixed(self):
        source = SOURCE.read_text("utf-8")
        self.assertIn('print("STOP: bounded_household_waf_gate"', source)


if __name__ == "__main__":
    unittest.main()
