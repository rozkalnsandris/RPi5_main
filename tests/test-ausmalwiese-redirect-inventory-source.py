#!/usr/bin/env python3
"""#996: offline only; no Cloudflare credentials, network or installed operator."""
import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts/ausmalwiese_redirect_inventory.py"
spec = importlib.util.spec_from_file_location("legacy_redirect_inventory_test", MODULE)
assert spec and spec.loader
inv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inv)
ZONE = "a" * 32
RULESET = "b" * 32


def response(data):
    return {"success": True, "result": data, "errors": []}


class FakeReader:
    def __init__(self, rules=None, listed=True, missing=False):
        self.calls = []
        self.paths = {
            f"/zones/{ZONE}": (200, response({
                "id": ZONE, "name": "rozkalns.net", "status": "active",
            })),
            f"/zones/{ZONE}/rulesets": (200, response(
                [{"id": RULESET, "kind": "zone", "phase": inv.PHASE}]
                if listed else [],
            )),
            f"/zones/{ZONE}/rulesets/phases/{inv.PHASE}/entrypoint":
                (404, {"success": False, "errors": []}) if missing else
                (200, response({
                    "id": RULESET, "kind": "zone", "phase": inv.PHASE,
                    "rules": rules if rules is not None else [],
                })),
        }

    def __call__(self, method, path):
        self.calls.append((method, path))
        if method != "GET":
            raise AssertionError("non_GET_transport_invoked")
        return self.paths[path]


class GetOnlyRedirectInventoryTests(unittest.TestCase):
    def test_only_exact_zone_three_gets_sanitized_empty(self):
        reader = FakeReader()
        with redirect_stdout(io.StringIO()) as sink:
            data = inv.inspect_redirect_inventory(reader, ZONE)
        self.assertEqual(sink.getvalue(), "")
        self.assertEqual(reader.calls, [
            ("GET", f"/zones/{ZONE}"),
            ("GET", f"/zones/{ZONE}/rulesets"),
            ("GET", f"/zones/{ZONE}/rulesets/phases/{inv.PHASE}/entrypoint"),
        ])
        self.assertEqual(data["rule_count"], 0)
        self.assertEqual(data["entrypoint"], "present")
        self.assertRegex(data["baseline_sha256"], r"^[a-f0-9]{64}$")
        self.assertFalse(data["safe_to_apply"])
        self.assertFalse(data["account_level_checked"])
        self.assertNotIn(ZONE, json.dumps(data))
        for wrong in ("", "z" * 32, "../../token", "A" * 32, None):
            with self.subTest(zone_id=wrong):
                reader = FakeReader()
                with self.assertRaises(inv.InventoryBlocked):
                    inv.inspect_redirect_inventory(reader, wrong)
                self.assertEqual(reader.calls, [])

    def test_order_and_disabled_exact_host_scopes(self):
        r = FakeReader([
            {"expression": 'http.host eq "other.rozkalns.net"', "enabled": True},
            {"expression": 'http.host eq "coloring.rozkalns.net"', "enabled": True},
            {"expression": 'http.host eq "coloring.rozkalns.net"', "enabled": False},
            {"expression": '(http.host eq "coloring.rozkalns.net")', "enabled": True},
            {"expression": 'http.host eq "other2.rozkalns.net"'},
        ])
        data = inv.inspect_redirect_inventory(r, ZONE)
        self.assertEqual(data["active_exact_legacy_positions"], [2, 4])
        self.assertEqual(data["active_ambiguous_positions"], [])
        self.assertEqual(data["other_exact_host_count"], 2)
        self.assertEqual(data["disabled_count"], 1)
        self.assertEqual(data["enabled_count"], 4)
        self.assertFalse(data["safe_to_apply"])

    def test_unknown_rules_fail_conservative_and_do_not_expose_raw(self):
        marker = "TEST_ONLY_SENSITIVE_VALUE_MARKER_987"
        data = inv.inspect_redirect_inventory(FakeReader([
            {"expression": 'http.host eq "other.rozkalns.net" or http.host eq "coloring.rozkalns.net"'},
            {"expression": "true", "description": marker},
            {"expression": 'starts_with(http.request.uri.path, "/")'},
            {"enabled": False, "expression": "unrecognizable"},
        ]), ZONE)
        self.assertEqual(data["active_ambiguous_positions"], [1, 2, 3])
        self.assertEqual(data["disabled_scope_unknown_count"], 1)
        serialized = json.dumps(data)
        for forbidden in (marker, "expression", "description", ZONE, RULESET):
            self.assertNotIn(forbidden, serialized)

    def test_404_requires_confirming_absence_in_zone_list(self):
        out = inv.inspect_redirect_inventory(
            FakeReader(listed=False, missing=True), ZONE,
        )
        self.assertEqual(out["entrypoint"], "absent")
        self.assertFalse(out["safe_to_apply"])
        with self.assertRaisesRegex(inv.InventoryBlocked, "entrypoint_list_disagreement"):
            inv.inspect_redirect_inventory(FakeReader(missing=True), ZONE)
        with self.assertRaisesRegex(inv.InventoryBlocked, "entrypoint_mismatch"):
            inv.inspect_redirect_inventory(FakeReader(listed=False), ZONE)

    def test_fail_closed_http_auth_identity_shapes_and_transport(self):
        cases = [
            ("zone", 403, {}),
            ("zone", 200, response({
                "id": ZONE, "name": "different.net", "status": "active",
            })),
            ("zone", 200, response({
                "id": ZONE, "name": "rozkalns.net", "status": "pending",
            })),
            ("list", 403, {}),
            ("list", 200, {"success": False, "result": []}),
            ("list", 200, response([
                {"id": RULESET, "kind": "zone", "phase": inv.PHASE},
                {"id": RULESET, "kind": "zone", "phase": inv.PHASE},
            ])),
            ("entry", 403, {}),
            ("entry", 200, response({
                "id": RULESET, "kind": "root", "phase": inv.PHASE, "rules": [],
            })),
            ("entry", 200, response({
                "id": RULESET, "kind": "zone", "phase": inv.PHASE,
                "rules": "invalid",
            })),
        ]
        for which, status, body in cases:
            with self.subTest(which=which, status=status):
                reader = FakeReader()
                path = (
                    f"/zones/{ZONE}" if which == "zone" else
                    f"/zones/{ZONE}/rulesets" if which == "list" else
                    f"/zones/{ZONE}/rulesets/phases/{inv.PHASE}/entrypoint"
                )
                reader.paths[path] = (status, body)
                with self.assertRaises(inv.InventoryBlocked):
                    inv.inspect_redirect_inventory(reader, ZONE)
        with self.assertRaisesRegex(inv.InventoryBlocked, "invalid_rule_enabled"):
            inv.inspect_redirect_inventory(FakeReader([
                {"expression": "true", "enabled": "yes"},
            ]), ZONE)
        with self.assertRaisesRegex(inv.InventoryBlocked, "read_only_transport_failed"):
            inv.inspect_redirect_inventory(lambda m, p: 1 / 0, ZONE)

    def test_cursor_paginated_list_never_claims_completeness(self):
        path = f"/zones/{ZONE}/rulesets"
        reader = FakeReader()
        reader.paths[path] = (200, {
            "success": True, "result": [],
            "result_info": {"cursors": {"after": "opaque-cursor"}},
        })
        with self.assertRaisesRegex(inv.InventoryBlocked, "incomplete_ruleset_list"):
            inv.inspect_redirect_inventory(reader, ZONE)
        self.assertEqual(len(reader.calls), 2)
        for broken in ("invalid", {"cursors": "invalid"}):
            with self.subTest(info=broken):
                reader = FakeReader()
                reader.paths[path] = (200, {
                    "success": True, "result": [], "result_info": broken,
                })
                with self.assertRaisesRegex(inv.InventoryBlocked, "invalid_ruleset_pagination"):
                    inv.inspect_redirect_inventory(reader, ZONE)

    def test_inventory_hash_binds_order_parameters_and_state(self):
        specs = [
            [{"expression": 'http.host eq "other.net"'},
             {"expression": 'http.host eq "coloring.rozkalns.net"'}],
            [{"expression": 'http.host eq "coloring.rozkalns.net"'},
             {"expression": 'http.host eq "other.net"'}],
            [{"expression": 'http.host eq "other.net"', "enabled": False},
             {"expression": 'http.host eq "coloring.rozkalns.net"'}],
        ]
        results = [inv.inspect_redirect_inventory(FakeReader(r), ZONE) for r in specs]
        self.assertEqual(len({r["baseline_sha256"] for r in results}), 3)

    def test_no_direct_credentials_network_or_writes(self):
        source = MODULE.read_text(encoding="utf-8")
        for forbidden in (
            "import requests", "import urllib", "import subprocess",
            "getpass", "open(", "os.environ", "Authorization:",
            "api_token", "secret_path", "POST ", "PATCH ", "PUT ", "DELETE ",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('read("GET", path)', source)
        self.assertIn('"safe_to_apply": False', source)


if __name__ == "__main__":
    unittest.main()
