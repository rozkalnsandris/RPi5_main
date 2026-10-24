#!/usr/bin/env python3
"""Offline regression tests for #1114 bounded legacy redirect write source."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ausmalwiese_redirect_write_v1 as write

ZONE = "a" * 32
RULESET = "b" * 32
LEGACY_RULE = "c" * 32
OTHER_RULE = "d" * 32
TOKEN = "T" * 32


def provider_rule(rule, rule_id):
    value = copy.deepcopy(rule)
    value["id"] = rule_id
    value["version"] = "1"
    value["last_updated"] = "2026-10-19T00:00:00Z"
    return value


def unrelated_rule():
    return {
        "id": OTHER_RULE,
        "version": "1",
        "last_updated": "2026-10-19T00:00:00Z",
        "expression": 'http.host eq "other.rozkalns.net"',
        "action": "redirect",
        "action_parameters": {
            "from_value": {
                "target_url": {"value": "https://example.com/"},
                "status_code": 302,
                "preserve_query_string": False,
            }
        },
        "enabled": True,
    }


class FakeTransport:
    def __init__(self, rules=None, *, absent=False, tamper_post=False):
        self.ruleset_id = RULESET
        self.entrypoint = None if absent else {
            "id": RULESET,
            "kind": "zone",
            "phase": write.PHASE,
            "rules": copy.deepcopy(rules or []),
        }
        self.read_calls = []
        self.writes = []
        self.tamper_post = tamper_post
        self.did_write = False

    def read(self, method, path):
        self.read_calls.append((method, path))
        if method != "GET":
            raise AssertionError("read must be GET")
        prefix = f"/zones/{ZONE}"
        if path == prefix:
            return 200, {
                "success": True,
                "result": {"id": ZONE, "name": write.ZONE_NAME, "status": "active"},
            }
        if path == prefix + "/rulesets":
            listed = []
            if self.entrypoint is not None:
                listed.append({
                    "id": self.ruleset_id,
                    "kind": "zone",
                    "phase": write.PHASE,
                })
            return 200, {"success": True, "result": listed}
        phase = prefix + f"/rulesets/phases/{write.PHASE}/entrypoint"
        if path == phase:
            if self.entrypoint is None:
                return 404, {"success": False}
            result = copy.deepcopy(self.entrypoint)
            if self.did_write and self.tamper_post:
                for rule in result["rules"]:
                    if rule.get("expression") == write.MATCH_EXPRESSION:
                        rule["action_parameters"]["from_value"]["target_url"] = {
                            "expression": 'concat("https://wrong.example", http.request.uri.path)'
                        }
            return 200, {"success": True, "result": result}
        raise AssertionError(path)

    def write_once(self, method, path, payload):
        if self.writes:
            raise AssertionError("second provider write")
        self.writes.append((method, path, copy.deepcopy(payload)))
        prefix = f"/zones/{ZONE}"
        if method == "POST" and path == prefix + "/rulesets":
            self.entrypoint = {
                "id": RULESET,
                "kind": "zone",
                "phase": write.PHASE,
                "rules": [provider_rule(payload["rules"][0], LEGACY_RULE)],
            }
        elif (
            method == "POST"
            and path == prefix + f"/rulesets/{RULESET}/rules"
        ):
            self.entrypoint["rules"].append(
                provider_rule(payload, LEGACY_RULE)
            )
        elif (
            method == "PATCH"
            and path == prefix + f"/rulesets/{RULESET}/rules/{LEGACY_RULE}"
        ):
            rules = []
            for rule in self.entrypoint["rules"]:
                if rule.get("id") == LEGACY_RULE:
                    rules.append(provider_rule(payload, LEGACY_RULE))
                else:
                    rules.append(rule)
            self.entrypoint["rules"] = rules
        else:
            raise AssertionError((method, path))
        self.did_write = True


class FakeResponse:
    def __init__(self, url, result):
        self.status = 200
        self.url = url
        self.body = json.dumps({
            "success": True,
            "result": result,
        }).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, count):
        return self.body[:count]


class FakeOpener:
    def __init__(self):
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        suffix = request.full_url[len(write.API_ORIGIN):]
        prefix = f"/zones/{ZONE}"
        if request.method == "GET" and suffix == prefix:
            result = {"id": ZONE, "name": write.ZONE_NAME, "status": "active"}
        elif request.method == "GET" and suffix == prefix + "/rulesets":
            result = [{"id": RULESET, "kind": "zone", "phase": write.PHASE}]
        elif (
            request.method == "GET"
            and suffix == prefix + f"/rulesets/phases/{write.PHASE}/entrypoint"
        ):
            result = {
                "id": RULESET,
                "kind": "zone",
                "phase": write.PHASE,
                "rules": [],
            }
        else:
            result = {"id": RULESET}
        return FakeResponse(request.full_url, result)


class RedirectWriteTests(unittest.TestCase):
    def test_exact_rule_preserves_path_and_query(self):
        rule = write.desired_rule()
        self.assertEqual(rule["expression"], 'http.host eq "coloring.rozkalns.net"')
        from_value = rule["action_parameters"]["from_value"]
        self.assertEqual(
            from_value["target_url"]["expression"],
            'concat("https://ausmalwiese.de", http.request.uri.path)',
        )
        self.assertEqual(from_value["status_code"], 301)
        self.assertIs(from_value["preserve_query_string"], True)
        self.assertIs(rule["enabled"], True)

    def test_absent_entrypoint_creates_exact_ruleset_once_and_verifies(self):
        fake = FakeTransport(absent=True)
        before = write.preflight(fake, ZONE)
        self.assertEqual(before["operation"], "CREATE_RULESET")
        result = write.run_once(fake, ZONE, before["baseline_sha256"])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["operation"], "CREATE_RULESET")
        self.assertTrue(result["mutation_started"])
        self.assertEqual(len(fake.writes), 1)
        method, path, body = fake.writes[0]
        self.assertEqual((method, path), ("POST", f"/zones/{ZONE}/rulesets"))
        self.assertEqual(body, write.create_ruleset_body())

    def test_existing_entrypoint_adds_one_rule_without_changing_unrelated(self):
        other = unrelated_rule()
        fake = FakeTransport([other])
        before = write.preflight(fake, ZONE)
        self.assertEqual(before["operation"], "ADD_RULE")
        result = write.run_once(fake, ZONE, before["baseline_sha256"])
        self.assertEqual(result["operation"], "ADD_RULE")
        self.assertEqual(len(fake.writes), 1)
        self.assertEqual(
            fake.writes[0][:2],
            ("POST", f"/zones/{ZONE}/rulesets/{RULESET}/rules"),
        )
        self.assertEqual(fake.entrypoint["rules"][0], other)
        self.assertEqual(
            fake.entrypoint["rules"][1]["ref"],
            write.RULE_REF,
        )

    def test_exact_legacy_rule_updates_in_place_once(self):
        wrong = provider_rule(write.desired_rule(), LEGACY_RULE)
        wrong["action_parameters"]["from_value"]["status_code"] = 302
        fake = FakeTransport([unrelated_rule(), wrong])
        before = write.preflight(fake, ZONE)
        self.assertEqual(before["operation"], "UPDATE_RULE")
        result = write.run_once(fake, ZONE, before["baseline_sha256"])
        self.assertEqual(result["operation"], "UPDATE_RULE")
        self.assertEqual(len(fake.writes), 1)
        self.assertEqual(
            fake.writes[0][:2],
            (
                "PATCH",
                f"/zones/{ZONE}/rulesets/{RULESET}/rules/{LEGACY_RULE}",
            ),
        )
        self.assertEqual(fake.entrypoint["rules"][0], unrelated_rule())
        self.assertEqual(
            fake.entrypoint["rules"][1]["action_parameters"],
            write.desired_rule()["action_parameters"],
        )

    def test_already_exact_is_noop_with_zero_writes(self):
        fake = FakeTransport([
            unrelated_rule(),
            provider_rule(write.desired_rule(), LEGACY_RULE),
        ])
        before = write.preflight(fake, ZONE)
        self.assertEqual(before["operation"], "NOOP")
        result = write.run_once(fake, ZONE, before["baseline_sha256"])
        self.assertEqual(result["operation"], "NOOP")
        self.assertFalse(result["mutation_started"])
        self.assertEqual(fake.writes, [])

    def test_ambiguous_or_duplicate_legacy_blocks_before_write(self):
        ambiguous = {
            "id": "e" * 32,
            "expression": 'http.host eq "coloring.rozkalns.net" or true',
            "action": "redirect",
            "enabled": True,
        }
        fake = FakeTransport([ambiguous])
        with self.assertRaisesRegex(write.WriteBlocked, "AMBIGUOUS_ACTIVE_RULE"):
            write.preflight(fake, ZONE)
        self.assertEqual(fake.writes, [])

        disabled_ambiguous = copy.deepcopy(ambiguous)
        disabled_ambiguous["enabled"] = False
        fake = FakeTransport([disabled_ambiguous])
        with self.assertRaisesRegex(
            write.WriteBlocked, "AMBIGUOUS_DISABLED_RULE"
        ):
            write.preflight(fake, ZONE)
        self.assertEqual(fake.writes, [])

        exact = provider_rule(write.desired_rule(), LEGACY_RULE)
        disabled = provider_rule(write.desired_rule(), "f" * 32)
        disabled["enabled"] = False
        fake = FakeTransport([exact, disabled])
        with self.assertRaisesRegex(write.WriteBlocked, "DUPLICATE_LEGACY_RULE"):
            write.preflight(fake, ZONE)
        self.assertEqual(fake.writes, [])

    def test_baseline_drift_blocks_before_write(self):
        fake = FakeTransport([unrelated_rule()])
        before = write.preflight(fake, ZONE)
        fake.entrypoint["rules"][0]["description"] = "drift"
        with self.assertRaisesRegex(write.WriteBlocked, "BASELINE_DRIFT"):
            write.run_once(fake, ZONE, before["baseline_sha256"])
        self.assertEqual(fake.writes, [])

    def test_postverify_failure_stops_after_single_write_without_retry(self):
        fake = FakeTransport([unrelated_rule()], tamper_post=True)
        before = write.preflight(fake, ZONE)
        with self.assertRaisesRegex(
            write.WriteBlocked, "POST_DESIRED_RULE_UNPROVEN"
        ):
            write.run_once(fake, ZONE, before["baseline_sha256"])
        self.assertEqual(len(fake.writes), 1)

    def test_transport_enforces_observed_identity_and_one_write_shape(self):
        opener = FakeOpener()
        transport = write.FixedZoneRedirectWriteTransport(
            ZONE, TOKEN, opener=opener
        )
        with self.assertRaisesRegex(
            write.WriteBlocked, "WRITE_BASELINE_NOT_SEEN"
        ):
            transport.write_once(
                "POST",
                f"/zones/{ZONE}/rulesets/{RULESET}/rules",
                write.desired_rule(),
            )
        self.assertEqual(opener.calls, [])

        before = write.preflight(transport, ZONE)
        self.assertEqual(before["operation"], "ADD_RULE")
        self.assertEqual(len(opener.calls), 3)

        with self.assertRaisesRegex(write.WriteBlocked, "WRITE_BODY_DRIFT"):
            transport.write_once(
                "POST",
                f"/zones/{ZONE}/rulesets/{RULESET}/rules",
                {"name": "wrong"},
            )
        self.assertEqual(len(opener.calls), 3)

        transport.write_once(
            "POST",
            f"/zones/{ZONE}/rulesets/{RULESET}/rules",
            write.desired_rule(),
        )
        self.assertEqual(len(opener.calls), 4)
        request, timeout = opener.calls[-1]
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            request.full_url,
            write.API_ORIGIN
            + f"/zones/{ZONE}/rulesets/{RULESET}/rules",
        )
        sent = json.loads(request.data.decode("ascii"))
        self.assertEqual(sent, write.desired_rule())
        self.assertEqual(timeout, 8)

        with self.assertRaisesRegex(write.WriteBlocked, "SECOND_WRITE_FORBIDDEN"):
            transport.write_once(
                "POST",
                f"/zones/{ZONE}/rulesets/{RULESET}/rules",
                write.desired_rule(),
            )
        self.assertEqual(len(opener.calls), 4)

    def test_contract_and_source_keep_live_boundary_closed(self):
        contract = json.loads(
            (ROOT / "ops/contracts/ausmalwiese-redirect-write-v1.json").read_text()
        )
        self.assertEqual(contract["issue"], 1114)
        self.assertEqual(contract["parent_issue"], 996)
        self.assertEqual(
            contract["write_budget"]["max_provider_writes_per_invocation"], 1
        )
        self.assertEqual(contract["write_budget"]["retries"], 0)
        self.assertFalse(contract["write_budget"]["rollback"])
        self.assertFalse(contract["write_budget"]["cleanup"])
        self.assertIn(
            "Cloudflare_write_execution",
            contract["capabilities_not_granted_by_this_source"],
        )
        source = (
            ROOT / "scripts/ausmalwiese_redirect_write_v1.py"
        ).read_text()
        for banned in (
            "os.environ",
            "getpass",
            "argparse",
            "if __name__",
            ".env",
            "subprocess",
        ):
            self.assertNotIn(banned, source)
        self.assertIn("inventory._scope(rule)", source)


if __name__ == "__main__":
    unittest.main()
