#!/usr/bin/env python3
"""Disconnected tests for Ausmalwiese household /count WAF source."""
from __future__ import annotations

import importlib.util
import json
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
        "description": "unrelated",
        "action": "managed_challenge",
        "expression": 'http.request.uri.path eq "/login"',
        "enabled": True,
    }


def target(values, rule_id="d" * 32, **overrides):
    result = {"id": rule_id, **m.target_rule(values)}
    result.update(overrides)
    return result


class HouseholdWafTests(unittest.TestCase):
    def test_contract_matches_source_and_privacy_boundary(self):
        data = json.loads(CONTRACT.read_text("utf-8"))
        self.assertEqual(data["zone"], m.ZONE_NAME)
        self.assertEqual(data["hosts"], list(m.HOSTS))
        self.assertEqual(data["path"], m.PATH)
        self.assertEqual(data["phase"], m.PHASE)
        self.assertEqual(data["rule_ref"], m.RULE_REF)
        self.assertEqual(data["provider"]["maximum_writes_per_operation"], 1)
        self.assertEqual(
            data["provider"]["existing_target_mutation"],
            "PATCH /zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule_id}",
        )
        self.assertTrue(data["privacy"]["sanitized_receipts_only"])
        self.assertTrue(
            data["privacy"]["cloudflare_rule_stores_address_material_if_live_approved"]
        )
        self.assertFalse(data["privacy"]["github_raw_household_address_storage"])
        self.assertFalse(data["credentials"]["reuse_tunnel_credentials"])
        self.assertTrue(data["installed_operator"]["installer_source_implemented"])
        self.assertTrue(
            data["installed_operator"]["replacement_installer_source_implemented"]
        )
        self.assertTrue(data["credentials"]["provisioning_source_implemented"])

    def test_constants_are_exact_scope(self):
        self.assertEqual(m.ZONE_NAME, "ausmalwiese.de")
        self.assertEqual(m.HOSTS, ("ausmalwiese.de", "www.ausmalwiese.de"))
        self.assertEqual(m.PATH, "/count")
        self.assertEqual(m.PHASE, "http_request_firewall_custom")
        self.assertEqual(
            m.RULE_REF,
            "ausmalwiese-household-goatcounter-exclusion-v1",
        )
        self.assertEqual(m.MAX_FREE_RULES, 5)

    def test_normalizes_public_exact_and_bounded_cidr(self):
        good = [
            "8.8.8.8",
            "2606:4700:4700::1111",
            "8.8.8.0/24",
            "2606:4700:4700::/48",
        ]
        out = m.normalize_sources(good)
        self.assertEqual(set(out), set(good))
        self.assertEqual(m.source_shape(out), {
            "exact_ipv4": 1,
            "exact_ipv6": 1,
            "cidr_ipv4": 1,
            "cidr_ipv6": 1,
            "total": 4,
        })

    def test_rejects_private_special_noncanonical_and_overbroad(self):
        bad = [
            "127.0.0.1",
            "10.0.0.1",
            "169.254.1.1",
            "224.0.0.1",
            "0.0.0.0",
            "::1",
            "fe80::1",
            "ff02::1",
            "8.8.8.0/8",
            "2606:4700::/32",
            "2606:4700:4700:0:0:0:0:1111",
            "2606:4700:4700::1%eth0",
            " 8.8.8.8",
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(m.GateError):
                    m.normalize_source(value)

    def test_rejects_empty_duplicates_and_too_many(self):
        for values in (
            [],
            ["8.8.8.8", "8.8.8.8"],
            ["8.8.8.8"] * 9,
        ):
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
        before_rules = [existing("b" * 32), existing("c" * 32, "second")]
        mode, path, payload, before = m.plan(
            current(before_rules),
            "1" * 32,
            values,
        )
        self.assertEqual(mode, "append_one_rule")
        self.assertEqual(
            path,
            "/zones/" + "1" * 32 + "/rulesets/" + "a" * 32 + "/rules",
        )
        after = current(before_rules + [{"id": "d" * 32, **payload}])
        m.verify(after, before, values)

    def test_create_duplicate_or_conflict_is_rejected(self):
        values = m.normalize_sources(["8.8.8.8"])
        intended = m.target_rule(values)
        cases = [
            current([{"id": "b" * 32, **intended}]),
            current([{
                "id": "b" * 32,
                "ref": m.RULE_REF,
                "action": "block",
                "expression": "ip.src eq 8.8.4.4",
                "enabled": True,
            }]),
            current([{
                "id": "b" * 32,
                "ref": "other",
                "action": "block",
                "expression": intended["expression"],
                "enabled": True,
            }]),
        ]
        for snapshot in cases:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(m.GateError):
                    m.plan(snapshot, "1" * 32, values)

    def test_free_rule_capacity_fails_closed_for_create(self):
        values = m.normalize_sources(["8.8.8.8"])
        rules = [
            existing(f"{i:032x}", f"r{i}")
            for i in range(m.MAX_FREE_RULES)
        ]
        with self.assertRaises(m.GateError):
            m.plan(current(rules), "1" * 32, values)

    def test_update_plan_is_exact_single_rule_patch(self):
        incumbent = m.normalize_sources(["8.8.8.8"])
        desired = m.normalize_sources([
            "8.8.8.8",
            "2606:4700:4700::/48",
        ])
        rules = [existing(), target(incumbent)]
        mode, path, payload, before, index, observed = m.plan_update(
            current(rules),
            "1" * 32,
            desired,
        )
        self.assertEqual(mode, "update_existing_target")
        self.assertEqual(
            path,
            "/zones/" + "1" * 32 + "/rulesets/" + "a" * 32
            + "/rules/" + "d" * 32,
        )
        self.assertEqual(index, 1)
        self.assertEqual(observed, incumbent)
        self.assertEqual(payload, m.target_rule(desired))
        self.assertEqual(before, m.existing_projection(rules))

    def test_update_requires_exactly_one_healthy_target(self):
        incumbent = m.normalize_sources(["8.8.8.8"])
        desired = m.normalize_sources(["8.8.8.8", "2606:4700:4700::/48"])
        bad = [
            current([existing()]),
            current([target(incumbent), target(incumbent, "e" * 32)]),
            current([target(incumbent, action="challenge")]),
            current([target(incumbent, enabled=False)]),
            current([target(incumbent, description="changed")]),
            current([target(incumbent, expression="ip.src eq 8.8.8.8")]),
        ]
        for snapshot in bad:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(m.GateError):
                    m.plan_update(snapshot, "1" * 32, desired)

    def test_update_preserves_incumbent_and_adds_only_ipv6(self):
        incumbent = m.normalize_sources(["8.8.8.8"])
        cases = [
            ["2606:4700:4700::/48"],
            ["8.8.8.8"],
            ["8.8.8.8", "8.8.4.4", "2606:4700:4700::/48"],
            ["8.8.4.4", "2606:4700:4700::/48"],
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                desired = m.normalize_sources(raw)
                with self.assertRaises(m.GateError):
                    m.plan_update(
                        current([target(incumbent)]),
                        "1" * 32,
                        desired,
                    )

    def test_update_rejects_target_without_incumbent_ipv4(self):
        incumbent = m.normalize_sources(["2606:4700:4700::1111"])
        desired = m.normalize_sources([
            "2606:4700:4700::1111",
            "2606:4700:4701::/48",
        ])
        with self.assertRaises(m.GateError):
            m.plan_update(current([target(incumbent)]), "1" * 32, desired)

    def test_verify_update_preserves_unrelated_rules_and_order(self):
        incumbent = m.normalize_sources(["8.8.8.8"])
        desired = m.normalize_sources([
            "8.8.8.8",
            "2606:4700:4700::/48",
        ])
        rules = [
            existing("b" * 32, "first"),
            target(incumbent),
            existing("c" * 32, "last"),
        ]
        _, _, payload, before, index, _ = m.plan_update(
            current(rules),
            "1" * 32,
            desired,
        )
        good = current([
            rules[0],
            {"id": "d" * 32, **payload},
            rules[2],
        ])
        m.verify_update(good, before, index, desired)

        bad = [
            current([{"id": "d" * 32, **payload}, rules[0], rules[2]]),
            current([
                {**rules[0], "action": "block"},
                {"id": "d" * 32, **payload},
                rules[2],
            ]),
            current([
                rules[0],
                {"id": "e" * 32, **payload},
                rules[2],
            ]),
            current([
                rules[0],
                {"id": "d" * 32, **payload, "enabled": False},
                rules[2],
            ]),
        ]
        for snapshot in bad:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(m.GateError):
                    m.verify_update(snapshot, before, index, desired)

    def test_api_restricts_methods_and_paths(self):
        zone = "1" * 32
        ruleset = "2" * 32
        rule = "3" * 32
        with self.assertRaises(m.GateError):
            m.api_call("unused", "DELETE", f"/zones/{zone}")
        with self.assertRaises(m.GateError):
            m.api_call("unused", "PUT", f"/zones/{zone}")
        with self.assertRaises(m.GateError):
            m.api_call("unused", "GET", "/accounts/" + zone)
        with self.assertRaises(m.GateError):
            m.api_call("unused", "PATCH", f"/zones/{zone}/dns_records/{rule}")
        allowed = f"/zones/{zone}/rulesets/{ruleset}/rules/{rule}"
        with mock.patch.object(m.request, "build_opener") as opener:
            response = mock.MagicMock()
            response.__enter__.return_value.status = 200
            response.__enter__.return_value.read.return_value = (
                b'{"success":true,"result":{}}'
            )
            opener.return_value.open.return_value = response
            code, result = m.api_call("token-value-123456", "PATCH", allowed, {})
        self.assertEqual(code, 200)
        self.assertEqual(result, {})

    def test_create_preflight_zero_writes_and_sanitized(self):
        values = m.normalize_sources(["8.8.8.8", "2606:4700:4700::/48"])
        with (
            mock.patch.object(
                m,
                "installed_credentials",
                return_value=("1" * 32, "token-value-123456"),
            ),
            mock.patch.object(m, "read_household_sources", return_value=values),
            mock.patch.object(m, "api_call", side_effect=[
                (200, {"id": "1" * 32, "name": m.ZONE_NAME}),
                (200, current([existing()])),
            ]) as api,
        ):
            result = m.execute_create("a" * 40, False)
        self.assertEqual(result["writes"], 0)
        self.assertEqual(result["existing_rules"], 1)
        self.assertEqual(result["source_shape"]["total"], 2)
        self.assertNotIn("8.8.8.8", str(result))
        self.assertNotIn("2606:4700", str(result))
        self.assertEqual(
            [call.args[1] for call in api.call_args_list],
            ["GET", "GET"],
        )

    def test_update_preflight_zero_writes_and_sanitized(self):
        incumbent = m.normalize_sources(["8.8.8.8"])
        desired = m.normalize_sources([
            "8.8.8.8",
            "2606:4700:4700::/48",
        ])
        snapshot = current([existing(), target(incumbent)])
        with (
            mock.patch.object(
                m,
                "installed_credentials",
                return_value=("1" * 32, "token-value-123456"),
            ),
            mock.patch.object(m, "read_household_sources", return_value=desired),
            mock.patch.object(m, "api_call", side_effect=[
                (200, {"id": "1" * 32, "name": m.ZONE_NAME}),
                (200, snapshot),
            ]) as api,
        ):
            result = m.execute_update("a" * 40, False)
        self.assertEqual(result["writes"], 0)
        self.assertEqual(result["incumbent_source_shape"]["exact_ipv4"], 1)
        self.assertEqual(result["source_shape"]["cidr_ipv6"], 1)
        self.assertNotIn("8.8.8.8", str(result))
        self.assertNotIn("2606:4700", str(result))
        self.assertEqual(
            [call.args[1] for call in api.call_args_list],
            ["GET", "GET"],
        )

    def test_update_apply_has_exactly_one_patch_then_get(self):
        incumbent = m.normalize_sources(["8.8.8.8"])
        desired = m.normalize_sources([
            "8.8.8.8",
            "2606:4700:4700::/48",
        ])
        before_rules = [existing(), target(incumbent)]
        after_rules = [existing(), target(desired)]
        calls = []

        def api(token, method, path, payload=None):
            calls.append((method, path))
            if len(calls) == 1:
                return 200, {"id": "1" * 32, "name": m.ZONE_NAME}
            if len(calls) == 2:
                return 200, current(before_rules)
            if len(calls) == 3:
                self.assertEqual(method, "PATCH")
                self.assertEqual(payload, m.target_rule(desired))
                return 200, target(desired)
            if len(calls) == 4:
                return 200, current(after_rules)
            raise AssertionError("too many calls")

        with (
            mock.patch.object(
                m,
                "installed_credentials",
                return_value=("1" * 32, "token-value-123456"),
            ),
            mock.patch.object(m, "read_household_sources", return_value=desired),
            mock.patch.object(m, "api_call", side_effect=api),
        ):
            result = m.execute_update("a" * 40, True)

        self.assertEqual(result["writes_attempted"], 1)
        self.assertEqual(
            [item[0] for item in calls],
            ["GET", "GET", "PATCH", "GET"],
        )
        self.assertEqual(sum(method == "PATCH" for method, _ in calls), 1)
        self.assertFalse(any(
            method in {"POST", "PUT", "DELETE"} for method, _ in calls
        ))
        self.assertNotIn("8.8.8.8", str(result))
        self.assertNotIn("2606:4700", str(result))

    def test_patch_or_post_patch_failure_is_terminal_without_retry(self):
        incumbent = m.normalize_sources(["8.8.8.8"])
        desired = m.normalize_sources([
            "8.8.8.8",
            "2606:4700:4700::/48",
        ])
        snapshot = current([target(incumbent)])

        for fail_post_get in (False, True):
            calls = []

            def api(token, method, path, payload=None):
                calls.append(method)
                if len(calls) == 1:
                    return 200, {"id": "1" * 32, "name": m.ZONE_NAME}
                if len(calls) == 2:
                    return 200, snapshot
                if len(calls) == 3:
                    if fail_post_get:
                        return 200, target(desired)
                    raise m.GateError("provider_transport_error")
                raise m.GateError("provider_transport_error")

            with self.subTest(fail_post_get=fail_post_get):
                with (
                    mock.patch.object(
                        m,
                        "installed_credentials",
                        return_value=("1" * 32, "token-value-123456"),
                    ),
                    mock.patch.object(
                        m,
                        "read_household_sources",
                        return_value=desired,
                    ),
                    mock.patch.object(m, "api_call", side_effect=api),
                ):
                    expected = (
                        "post_patch_verification_failed"
                        if fail_post_get
                        else "patch_outcome_unknown"
                    )
                    with self.assertRaisesRegex(m.GateError, expected):
                        m.execute_update("a" * 40, True)
            self.assertLessEqual(calls.count("PATCH"), 1)
            self.assertNotIn("POST", calls)
            self.assertNotIn("PUT", calls)
            self.assertNotIn("DELETE", calls)

    def test_offline_plan_contains_no_address_material(self):
        result = m.offline_plan()
        self.assertEqual(result["writes"], 0)
        self.assertEqual(result["household_input"], "hidden_local_tty_only")
        self.assertEqual(
            result["update_semantics"],
            "preserve-incumbent-add-ipv6-only",
        )
        text = str(result)
        self.assertNotIn("8.8.8.8", text)
        self.assertNotIn("2606:", text)

    def test_source_does_not_accept_household_address_cli_or_environment(self):
        source = SOURCE.read_text("utf-8")
        self.assertIn("getpass.getpass(", source)
        self.assertNotIn('add_argument("--source"', source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("print(values", source)
        self.assertNotIn("print(incumbent", source)

    def test_main_error_output_is_fixed(self):
        source = SOURCE.read_text("utf-8")
        self.assertIn('print("STOP: bounded_household_waf_gate"', source)
        self.assertIn(m.UPDATE_CONFIRM, source)


if __name__ == "__main__":
    unittest.main()
