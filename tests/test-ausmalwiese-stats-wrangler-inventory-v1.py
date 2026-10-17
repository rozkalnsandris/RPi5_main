#!/usr/bin/env python3
"""Offline tests for the Stats Wrangler normalized inventory collector (#1054)."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_stats_wrangler_inventory_v1.py"
spec = importlib.util.spec_from_file_location(
    "stats_wrangler_inventory_1054", SOURCE
)
plan = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(plan)

NEW_VERSION = "12345678-1234-4234-a234-123456789abc"
SECOND_VERSION = "22345678-1234-4234-a234-123456789abc"
DEPLOYMENT = "32345678-1234-4234-a234-123456789abc"


def versions(
    version=plan.BASELINE_VERSION,
    source="api",
    number=10,
):
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": {
            "items": [
                {
                    "id": version,
                    "number": number,
                    "metadata": {"source": source},
                },
                {
                    "id": SECOND_VERSION,
                    "number": number - 1,
                    "metadata": {"source": "api"},
                },
            ]
        },
    }


def deployments(
    active=plan.BASELINE_VERSION,
    percentage=100,
):
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": {
            "deployments": [
                {
                    "id": DEPLOYMENT,
                    "strategy": "percentage",
                    "versions": [
                        {
                            "version_id": active,
                            "percentage": percentage,
                        }
                    ],
                }
            ]
        },
    }


def detail(
    version=plan.BASELINE_VERSION,
    source="api",
):
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": {
            "id": version,
            "number": 10,
            "metadata": {"source": source},
            "resources": {
                "bindings": [
                    {
                        "name": "DB",
                        "type": "d1",
                        "database_id": plan.D1_DATABASE_ID,
                    },
                    {
                        "name": "RATE_LIMITER",
                        "type": "ratelimit",
                        "namespace_id": plan.RATE_NAMESPACE_ID,
                        "simple": {
                            "limit": plan.RATE_LIMIT,
                            "period": plan.RATE_PERIOD,
                        },
                    },
                    {
                        "name": "CF_ANALYTICS_API_TOKEN",
                        "type": "secret_text",
                    },
                    {
                        "name": "VISITOR_HMAC_KEY",
                        "type": "secret_text",
                    },
                    {
                        "name": "CF_ANALYTICS_HOST",
                        "type": "plain_text",
                        "text": "analytics.example.invalid",
                    },
                    {
                        "name": "CF_ZONE_TAG",
                        "type": "plain_text",
                        "text": "zone-fingerprint-source",
                    },
                    {
                        "name": "PUBLIC_ORIGIN",
                        "type": "plain_text",
                        "text": "https://ausmalwiese.de",
                    },
                ],
                "script": {
                    "etag": "not-used-as-code-proof",
                    "handlers": ["fetch"],
                    "last_deployed_from": source,
                    "named_handlers": [],
                },
                "script_runtime": {
                    "compatibility_date": "2026-10-06T00:00:00Z",
                    "compatibility_flags": [],
                    "exports": {
                        "default": {
                            "type": "worker",
                            "state": "created",
                        }
                    },
                    "limits": {"cpu_ms": 50},
                    "usage_model": "standard",
                },
            },
        },
    }


class InventoryTests(unittest.TestCase):
    def test_contract_is_source_only(self):
        c = json.loads(plan.CONTRACT.read_text("utf-8"))
        plan.check_contract(c)
        self.assertEqual(
            c["account_sha256"],
            "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34",
        )
        for key in (
            "cloudflare_request",
            "credential_access",
            "host_install",
            "merge",
            "live",
            "retry",
            "rollback",
            "cleanup",
        ):
            self.assertFalse(c["actions"][key])
        self.assertEqual(plan.main(["--check-contract"]), 0)
        self.assertEqual(plan.main(["--run"]), 2)

    def test_request_plan_is_three_fixed_gets_no_retry_redirect(self):
        specs = plan.request_specs(plan.BASELINE_VERSION)
        self.assertEqual(len(specs), 3)
        self.assertEqual(
            [x["stage"] for x in specs],
            ["versions", "deployments", "version_detail"],
        )
        for item in specs:
            self.assertEqual(item["method"], "GET")
            self.assertEqual(item["host"], "api.cloudflare.com")
            self.assertEqual(item["retries"], 0)
            self.assertEqual(item["redirects"], 0)
            self.assertIn("coloring-pages-stats-v1", item["path"])
            self.assertNotIn("http://", item["path"])
            self.assertNotIn("https://", item["path"])
        self.assertIn("page=1&per_page=2", specs[0]["path"])
        self.assertIn("page=1&per_page=2", specs[1]["path"])
        self.assertTrue(
            specs[2]["path"].endswith(plan.BASELINE_VERSION)
        )

    def test_before_inventory_matches_1052_and_never_outputs_plain_values(self):
        snapshot = plan.build_inventory(
            versions(),
            deployments(),
            detail(),
        )
        out = plan.inventory_output(snapshot, stage="before")
        self.assertEqual(out["inventory"], snapshot)
        self.assertEqual(
            out["inventory_sha256"],
            plan.canonical_sha256(snapshot),
        )
        encoded = json.dumps(out, sort_keys=True)
        self.assertNotIn("analytics.example.invalid", encoded)
        self.assertNotIn("zone-fingerprint-source", encoded)
        self.assertNotIn("https://ausmalwiese.de", encoded)
        self.assertEqual(snapshot["source_class"], "script_api")
        self.assertEqual(
            snapshot["compatibility_date"],
            "2026-10-06",
        )

    def test_after_upload_inventory_matches_1052(self):
        v = versions(NEW_VERSION, "wrangler", 11)
        v["result"]["items"][1] = {
            "id": plan.BASELINE_VERSION,
            "number": 10,
            "metadata": {"source": "api"},
        }
        snapshot = plan.build_inventory(
            v,
            deployments(plan.BASELINE_VERSION),
            detail(NEW_VERSION, "wrangler"),
            stage="after_upload",
            new_version_id=NEW_VERSION,
        )
        out = plan.inventory_output(
            snapshot,
            stage="after_upload",
            new_version_id=NEW_VERSION,
        )
        self.assertEqual(
            out["inventory_sha256"],
            plan.canonical_sha256(snapshot),
        )
        self.assertEqual(
            snapshot["source_class"],
            "wrangler_versions_upload",
        )
        self.assertEqual(
            snapshot["latest_uploaded_version"],
            NEW_VERSION,
        )
        self.assertEqual(
            snapshot["active_versions"][0]["version_id"],
            plan.BASELINE_VERSION,
        )

    def test_versions_reject_legacy_shape_pagination_order_duplicate_and_unknown_source(self):
        bad = versions()
        bad["result_info"] = {
            "page": 1,
            "per_page": 2,
            "count": 2,
            "total_count": 2,
        }
        with self.assertRaisesRegex(
            plan.Blocked,
            "PAGINATION_UNEXPECTED",
        ):
            plan.parse_versions(bad)

        bad = versions()
        bad["result"] = bad["result"]["items"]
        with self.assertRaisesRegex(
            plan.Blocked,
            "VERSIONS_RESULT",
        ):
            plan.parse_versions(bad)

        bad = versions()
        bad["result"]["items"][1]["number"] = 10
        with self.assertRaisesRegex(
            plan.Blocked,
            "VERSION_ORDER",
        ):
            plan.parse_versions(bad)

        bad = versions()
        bad["result"]["items"][1]["id"] = plan.BASELINE_VERSION
        with self.assertRaisesRegex(
            plan.Blocked,
            "VERSION_DUPLICATE",
        ):
            plan.parse_versions(bad)

        bad = versions(source="dash")
        parsed_id, source = plan.parse_versions(bad)
        with self.assertRaisesRegex(
            plan.Blocked,
            "SOURCE_UNSUPPORTED",
        ):
            plan.parse_version_detail(
                detail(parsed_id, source),
                expected_version=parsed_id,
                list_source=source,
            )

    def test_deployments_reject_split_or_multiple_active(self):
        bad = deployments(percentage=50)
        with self.assertRaisesRegex(
            plan.Blocked,
            "SPLIT_TRAFFIC",
        ):
            plan.parse_deployments(bad)

        bad = deployments()
        bad["result"]["deployments"][0]["versions"].append(
            {
                "version_id": NEW_VERSION,
                "percentage": 0,
            }
        )
        with self.assertRaisesRegex(
            plan.Blocked,
            "ACTIVE_VERSION_COUNT",
        ):
            plan.parse_deployments(bad)

    def test_deployments_accept_optional_pagination_and_reject_drift(self):
        good = deployments()
        good["result_info"] = {
            "page": 1,
            "per_page": 2,
            "count": 1,
            "total_count": 8,
            "total_pages": 8,
        }
        self.assertEqual(
            plan.parse_deployments(good)["version_id"],
            plan.BASELINE_VERSION,
        )

        bad = deployments()
        bad["result_info"] = {
            "page": 2,
            "per_page": 2,
            "count": 1,
            "total_count": 8,
            "total_pages": 8,
        }
        with self.assertRaisesRegex(
            plan.Blocked,
            "PAGINATION_DRIFT",
        ):
            plan.parse_deployments(bad)

    def test_detail_rejects_identity_source_and_binding_drift(self):
        bad = detail(NEW_VERSION)
        with self.assertRaisesRegex(
            plan.Blocked,
            "DETAIL_VERSION",
        ):
            plan.parse_version_detail(
                bad,
                expected_version=plan.BASELINE_VERSION,
                list_source="api",
            )

        bad = detail()
        bad["result"]["resources"]["script"][
            "last_deployed_from"
        ] = "wrangler"
        with self.assertRaisesRegex(
            plan.Blocked,
            "SOURCE_AMBIGUOUS",
        ):
            plan.parse_version_detail(
                bad,
                expected_version=plan.BASELINE_VERSION,
                list_source="api",
            )

        bad = detail()
        bad["result"]["resources"]["bindings"].append(
            copy.deepcopy(
                bad["result"]["resources"]["bindings"][0]
            )
        )
        with self.assertRaisesRegex(
            plan.Blocked,
            "BINDING_DUPLICATE",
        ):
            plan.parse_version_detail(
                bad,
                expected_version=plan.BASELINE_VERSION,
                list_source="api",
            )

    def test_detail_rejects_secret_disclosure_and_binding_policy_drift(self):
        bad = detail()
        bad["result"]["resources"]["bindings"][2][
            "text"
        ] = "must-not-be-read"
        with self.assertRaisesRegex(
            plan.Blocked,
            "SECRET_VALUE_PRESENT",
        ):
            plan.parse_version_detail(
                bad,
                expected_version=plan.BASELINE_VERSION,
                list_source="api",
            )

        bad = detail()
        bad["result"]["resources"]["bindings"][0][
            "database_id"
        ] = "other"
        with self.assertRaisesRegex(plan.Blocked, "D1_ID"):
            plan.parse_version_detail(
                bad,
                expected_version=plan.BASELINE_VERSION,
                list_source="api",
            )

        bad = detail()
        bad["result"]["resources"]["bindings"][1][
            "simple"
        ]["limit"] = 99
        with self.assertRaisesRegex(
            plan.Blocked,
            "RATE_POLICY",
        ):
            plan.parse_version_detail(
                bad,
                expected_version=plan.BASELINE_VERSION,
                list_source="api",
            )

        bad = detail()
        bad["result"]["resources"]["bindings"][4][
            "name"
        ] = "OTHER"
        with self.assertRaisesRegex(
            plan.Blocked,
            "BINDING_SET",
        ):
            plan.parse_version_detail(
                bad,
                expected_version=plan.BASELINE_VERSION,
                list_source="api",
            )

    def test_decode_reply_is_bounded_json_only_and_no_redirect_semantics(self):
        body = json.dumps(versions()).encode()
        self.assertEqual(
            plan.decode_reply(
                200,
                "application/json; charset=utf-8",
                "identity",
                body,
            ),
            versions(),
        )
        cases = [
            (301, "application/json", "identity", body),
            (500, "application/json", "identity", body),
            (200, "text/html", "identity", body),
            (200, "application/json", "gzip", body),
            (200, "application/json", "identity", b"{bad"),
            (
                200,
                "application/json",
                "identity",
                b"x" * (plan.MAX_RESPONSE_BYTES + 1),
            ),
        ]
        for args in cases:
            with self.assertRaises(plan.Blocked):
                plan.decode_reply(*args)

    def test_inventory_hash_is_deterministic_and_settings_preservation_detectable(self):
        first = plan.build_inventory(
            versions(),
            deployments(),
            detail(),
        )
        second = plan.build_inventory(
            versions(),
            deployments(),
            detail(),
        )
        self.assertEqual(
            plan.canonical_sha256(first),
            plan.canonical_sha256(second),
        )

        changed = detail()
        changed["result"]["resources"]["script_runtime"][
            "limits"
        ]["cpu_ms"] = 51
        third = plan.build_inventory(
            versions(),
            deployments(),
            changed,
        )
        self.assertNotEqual(
            first["settings_sha256"],
            third["settings_sha256"],
        )

    def test_source_has_no_transport_credential_or_live_executor(self):
        source_text = SOURCE.read_text("utf-8")
        for forbidden in (
            "http.client",
            "import requests",
            "requests.",
            "urllib.request",
            "os.environ",
            "Authorization: Bearer",
            "subprocess",
        ):
            self.assertNotIn(forbidden, source_text)


if __name__ == "__main__":
    unittest.main()
