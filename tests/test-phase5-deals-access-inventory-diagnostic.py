#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cloudflare_phase5_deals_access_inventory_diagnostic as diag

def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

bridge = load(
    "phase5_deals_access_inventory_diag_bridge",
    ROOT / "scripts/github_phase5_deals_access_inventory_diagnostic_bridge.py",
)

SHA = "a" * 40
ACCOUNT = "a" * 32
OTHER_ACCOUNT = "b" * 32
APP = "11111111-1111-4111-8111-111111111111"
OTHER_APP = "22222222-2222-4222-8222-222222222222"
OWNER_ID = 277435981


def visibility(
    *,
    app_ids: list[str] | None = None,
    deals_ids: list[str] | None = None,
) -> dict:
    app_ids = [APP, OTHER_APP] if app_ids is None else app_ids
    deals_ids = [APP] if deals_ids is None else deals_ids
    resolution = "none"
    if len(deals_ids) == 1:
        resolution = "one"
    elif len(deals_ids) > 1:
        resolution = "multiple"
    return {
        "_app_ids": sorted(app_ids),
        "_deals_ids": sorted(deals_ids),
        "access_apps_visible": bool(app_ids),
        "deals_app_resolution": resolution,
    }


def event(body: str, *, app: bool = False, issue: int = 897) -> dict:
    return {
        "action": "created",
        "issue": {"number": issue},
        "comment": {
            "id": 123,
            "body": body,
            "author_association": "OWNER",
            "performed_via_github_app": {"id": 1} if app else None,
            "user": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
        },
        "sender": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
    }


class FakeClient:
    def __init__(self, apps: list[dict]) -> None:
        self.apps = apps
        self.paths: list[str] = []

    def get(self, path: str, query=None):
        self.paths.append(path)
        if path == "/user/tokens/verify":
            return {"result": {"status": "active"}}
        if path == f"/accounts/{ACCOUNT}/access/apps":
            return {
                "result": self.apps,
                "result_info": {"page": 1, "total_pages": 1},
            }
        raise AssertionError(f"unexpected path: {path}")


class DealsAccessInventoryDiagnosticTests(unittest.TestCase):
    def test_consistent_visibility_passes_without_identifiers(self):
        report = diag.build_report(
            p1d03_account_id=ACCOUNT,
            p1d03=visibility(),
            p1d04_account_id=ACCOUNT,
            p1d04=visibility(),
        )
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["reason"], "visibility_consistent")
        self.assertTrue(report["account_binding_matches"])
        self.assertTrue(report["application_inventory_matches"])
        self.assertTrue(report["deals_application_identity_matches"])
        self.assertFalse(report["mutation_performed"])
        self.assertEqual(report["cloudflare_write_requests_performed"], 0)
        encoded = json.dumps(report, sort_keys=True)
        for private in (ACCOUNT, APP, OTHER_APP):
            self.assertNotIn(private, encoded)

    def test_account_binding_mismatch_is_sanitized_block(self):
        report = diag.build_report(
            p1d03_account_id=ACCOUNT,
            p1d03=visibility(),
            p1d04_account_id=OTHER_ACCOUNT,
            p1d04=visibility(),
        )
        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(
            report["reason"], "p1d03_p1d04_account_binding_mismatch"
        )
        self.assertFalse(report["account_binding_matches"])

    def test_p1d04_empty_inventory_is_distinct(self):
        report = diag.build_report(
            p1d03_account_id=ACCOUNT,
            p1d03=visibility(),
            p1d04_account_id=ACCOUNT,
            p1d04=visibility(app_ids=[], deals_ids=[]),
        )
        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(
            report["reason"], "p1d04_access_application_inventory_empty"
        )
        self.assertTrue(report["p1d03"]["access_apps_visible"])
        self.assertFalse(report["p1d04"]["access_apps_visible"])

    def test_both_empty_and_missing_deals_are_distinct(self):
        report = diag.build_report(
            p1d03_account_id=ACCOUNT,
            p1d03=visibility(app_ids=[], deals_ids=[]),
            p1d04_account_id=ACCOUNT,
            p1d04=visibility(app_ids=[], deals_ids=[]),
        )
        self.assertEqual(
            report["reason"], "both_access_application_inventories_empty"
        )

        no_deals = visibility(deals_ids=[])
        report = diag.build_report(
            p1d03_account_id=ACCOUNT,
            p1d03=no_deals,
            p1d04_account_id=ACCOUNT,
            p1d04=no_deals,
        )
        self.assertEqual(
            report["reason"], "p1d04_deals_application_not_visible"
        )

    def test_inventory_visibility_difference_blocks(self):
        p1d04 = visibility(app_ids=[APP], deals_ids=[APP])
        report = diag.build_report(
            p1d03_account_id=ACCOUNT,
            p1d03=visibility(),
            p1d04_account_id=ACCOUNT,
            p1d04=p1d04,
        )
        self.assertEqual(
            report["reason"],
            "access_application_visibility_differs_between_read_lanes",
        )

    def test_collect_visibility_is_get_only_and_resolves_target(self):
        client = FakeClient(
            [
                {"id": APP, "domain": "deals.rozkalns.net"},
                {"id": OTHER_APP, "domain": "kuma.rozkalns.net"},
            ]
        )
        state = diag.collect_visibility(client, ACCOUNT)
        self.assertTrue(state["access_apps_visible"])
        self.assertEqual(state["deals_app_resolution"], "one")
        self.assertEqual(
            client.paths,
            ["/user/tokens/verify", f"/accounts/{ACCOUNT}/access/apps"],
        )

    def test_bridge_requires_direct_owner_exact_sha_and_first_attempt(self):
        body = (
            f"/rpi5-p5-deals-access-inventory diagnose HEAD={SHA} "
            "CANARY=phase5-deals-access-inventory-diagnostic-v1"
        )
        out = bridge.authorize_event(
            event(body),
            repository="rozkalnsandris/RPi5_main",
            github_sha=SHA,
            run_attempt="1",
        )
        self.assertEqual(out["expected_sha"], SHA)
        with self.assertRaisesRegex(
            bridge.AuthorizationError, "workflow_rerun_forbidden"
        ):
            bridge.authorize_event(
                event(body),
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="2",
            )
        with self.assertRaisesRegex(
            bridge.AuthorizationError, "app_authored_comment_forbidden"
        ):
            bridge.authorize_event(
                event(body, app=True),
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="1",
            )

    def test_workflow_uses_read_lanes_only(self):
        workflow = (
            ROOT
            / ".github/workflows/cloudflare-phase5-deals-access-inventory-diagnostic.yml"
        ).read_text(encoding="utf-8")
        for expected in (
            "CLOUDFLARE_P1D03_ACCOUNT_ID",
            "CLOUDFLARE_P1D03_READ_API_TOKEN",
            "CLOUDFLARE_P1D04_ACCOUNT_ID",
            "CLOUDFLARE_P1D04_READ_API_TOKEN",
            "github.event.issue.number == 897",
            "cloudflare_phase5_deals_access_inventory_diagnostic_actions.py",
        ):
            self.assertIn(expected, workflow)
        for forbidden in (
            "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
            "CLOUDFLARE_WRITE_API_TOKEN",
            "workflow_dispatch",
            "wrangler ",
            "curl ",
        ):
            self.assertNotIn(forbidden, workflow)

        source = (
            ROOT / "scripts/cloudflare_phase5_deals_access_inventory_diagnostic.py"
        ).read_text(encoding="utf-8")
        for forbidden in ('method="DELETE"', 'method="PUT"', 'method="PATCH"'):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
