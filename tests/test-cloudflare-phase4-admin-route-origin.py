#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

MODULE_PATH = ROOT / "scripts" / "cloudflare_phase4_admin_route_origin_actions.py"
SPEC = importlib.util.spec_from_file_location("phase4_route", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
route = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(route)

BRIDGE_PATH = ROOT / "scripts" / "github_phase4_admin_route_origin_bridge.py"
BRIDGE_SPEC = importlib.util.spec_from_file_location("phase4_route_bridge", BRIDGE_PATH)
assert BRIDGE_SPEC is not None and BRIDGE_SPEC.loader is not None
bridge = importlib.util.module_from_spec(BRIDGE_SPEC)
BRIDGE_SPEC.loader.exec_module(bridge)

WORKFLOW_PATH = ROOT / ".github" / "workflows" / "cloudflare-phase4-admin-route-origin.yml"
CONTRACT_PATH = ROOT / "ops" / "contracts" / "admin-zone-verification-v1.json"

OWNER_ID = 277435981
SHA = "a" * 40


def event(body: str) -> dict:
    return {
        "action": "created",
        "issue": {"number": 819},
        "comment": {
            "id": 123,
            "body": body,
            "author_association": "OWNER",
            "performed_via_github_app": None,
            "user": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
        },
        "sender": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
    }


def private_host(index: int) -> str:
    return ".".join(["10", "17", "23", str(index)])


def loopback_host() -> str:
    return ".".join(["127", "0", "0", "1"])


def good_config(contract: dict) -> dict:
    ingress = []
    for index, item in enumerate(contract["service_projections"], start=1):
        if item["expected_origin_class"] == "loopback":
            host = loopback_host()
        else:
            host = private_host(index)
        ingress.append({
            "hostname": item["hostname"],
            "service": f"http://{host}:{9000 + index}",
        })
    ingress.append({"service": "http_status:404"})
    return {"ingress": ingress}


class Phase4AdminRouteOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_owner_command_is_exact_issue_and_sha_bound(self) -> None:
        body = f"/rpi5-p4-route-origin check HEAD={SHA} CANARY=phase4-admin-route-origin-v1"
        out = bridge.authorize_event(
            event(body),
            repository="rozkalnsandris/RPi5_main",
            github_sha=SHA,
            run_attempt="1",
        )
        self.assertEqual(out["expected_sha"], SHA)

        broken = event(body)
        broken["comment"]["performed_via_github_app"] = {"id": 1}
        with self.assertRaisesRegex(bridge.AuthorizationError, "app_authored_comment_forbidden"):
            bridge.authorize_event(
                broken,
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="1",
            )

    def test_expected_route_classes_pass_without_raw_services(self) -> None:
        config = good_config(self.contract)
        report = route.build_report(self.contract, config)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(len(report["services"]), 8)
        by_host = {item["hostname"]: item for item in report["services"]}
        self.assertEqual(by_host["dash.rozkalns.net"]["route_origin_class"], "loopback")
        self.assertTrue(
            all(
                item["route_origin_class"] == "lan"
                for item in report["services"]
                if item["hostname"] != "dash.rozkalns.net"
            )
        )

        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn(private_host(1), rendered)
        self.assertNotIn(loopback_host(), rendered)
        self.assertNotIn(":900", rendered)

    def test_missing_route_fails_closed_unknown(self) -> None:
        config = good_config(self.contract)
        config["ingress"] = config["ingress"][1:]
        report = route.build_report(self.contract, config)
        self.assertEqual(report["services"][0]["route_origin_class"], "unknown")
        self.assertEqual(report["services"][0]["result"], "UNKNOWN")
        self.assertEqual(report["result"], "BLOCKED")

    def test_duplicate_route_fails_closed_unknown(self) -> None:
        config = good_config(self.contract)
        config["ingress"].insert(1, dict(config["ingress"][0]))
        report = route.build_report(self.contract, config)
        self.assertEqual(report["services"][0]["route_origin_class"], "unknown")
        self.assertEqual(report["services"][0]["result"], "UNKNOWN")

    def test_unexpected_public_origin_is_other_and_fail(self) -> None:
        config = good_config(self.contract)
        config["ingress"][0]["service"] = "https://origin.example.test"
        report = route.build_report(self.contract, config)
        self.assertEqual(report["services"][0]["route_origin_class"], "other")
        self.assertEqual(report["services"][0]["result"], "FAIL")

    def test_workflow_uses_only_existing_read_secret_lane(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("CLOUDFLARE_P1D03_ACCOUNT_ID", workflow)
        self.assertIn("CLOUDFLARE_P1D03_READ_API_TOKEN", workflow)
        for forbidden in (
            "CLOUDFLARE_WRITE_API_TOKEN",
            "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
            "CLOUDFLARE_P1D03_OWNER_EMAIL",
        ):
            self.assertNotIn(forbidden, workflow)

    def test_source_uses_official_get_paths_and_no_raw_output_fields(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('/cfd_tunnel"', source)
        self.assertIn('/configurations"', source)
        self.assertIn('"name": EXPECTED_TUNNEL_NAME', source)
        self.assertIn('"is_deleted": "false"', source)
        for forbidden_output_key in (
            '"tunnel_id":',
            '"account_id":',
            '"service":',
            '"port":',
            '"raw_api_payload":',
        ):
            self.assertNotIn(forbidden_output_key, source)


if __name__ == "__main__":
    unittest.main()
