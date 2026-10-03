#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from unittest import mock
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
        self.assertEqual(report["failure_class"], "mapping")

    def test_duplicate_route_fails_closed_unknown(self) -> None:
        config = good_config(self.contract)
        config["ingress"].insert(1, dict(config["ingress"][0]))
        report = route.build_report(self.contract, config)
        self.assertEqual(report["services"][0]["route_origin_class"], "unknown")
        self.assertEqual(report["services"][0]["result"], "UNKNOWN")
        self.assertEqual(report["failure_class"], "mapping")

    def test_unexpected_public_origin_is_other_and_fail(self) -> None:
        config = good_config(self.contract)
        config["ingress"][0]["service"] = "https://origin.example.test"
        report = route.build_report(self.contract, config)
        self.assertEqual(report["services"][0]["route_origin_class"], "other")
        self.assertEqual(report["services"][0]["result"], "FAIL")
        self.assertEqual(report["failure_class"], "mapping")

    def test_failure_class_is_allowlisted_and_sanitized(self) -> None:
        self.assertEqual(route._failure_class("tunnel_lookup", route.AuditError("cloudflare_api_http_403")), "permission")
        self.assertEqual(route._failure_class("tunnel_lookup", route.AuditError("tunnel_lookup_none")), "tunnel_lookup")
        self.assertEqual(route._failure_class("configuration", route.AuditError("configuration_missing")), "configuration")
        self.assertEqual(route._failure_class("mapping", route.AuditError("ingress_shape_invalid")), "mapping")
        self.assertEqual(route._failure_class("binding", route.AuditError("read_token_invalid")), "binding")
        self.assertEqual(route._failure_class("unknown", OSError("private-detail")), "unknown")

        report = route._unknown_report(self.contract, "configuration")
        rendered = json.dumps(report, sort_keys=True)
        self.assertEqual(report["failure_class"], "configuration")
        self.assertNotIn("tunnel_lookup_detail", report)
        self.assertNotIn("private-detail", rendered)

    def test_tunnel_lookup_detail_is_allowlisted_and_sanitized(self) -> None:
        cases = {
            "cloudflare_api_http_500": "http_error",
            "cloudflare_api_unsuccessful": "api_unsuccessful",
            "cloudflare_api_request_failed": "request_failed",
            "tunnel_list_shape_invalid": "response_shape",
            "tunnel_lookup_none": "ambiguous",
            "tunnel_lookup_multiple": "ambiguous",
            "tunnel_id_invalid": "id_invalid",
            "private-provider-detail": "unknown",
        }
        for reason, expected in cases.items():
            with self.subTest(reason=reason):
                self.assertEqual(route._tunnel_lookup_detail(route.AuditError(reason)), expected)

        report = route._unknown_report(self.contract, "tunnel_lookup", "ambiguous", "none")
        self.assertEqual(report["tunnel_lookup_detail"], "ambiguous")
        self.assertEqual(report["tunnel_lookup_match_state"], "none")
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("private-provider-detail", rendered)

        clamped = route._unknown_report(self.contract, "tunnel_lookup", "private-detail")
        self.assertEqual(clamped["tunnel_lookup_detail"], "unknown")
        self.assertNotIn("tunnel_lookup_match_state", clamped)

    def test_tunnel_lookup_match_state_is_allowlisted_without_count(self) -> None:
        self.assertEqual(
            route._tunnel_lookup_match_state(route.AuditError("tunnel_lookup_none")),
            "none",
        )
        self.assertEqual(
            route._tunnel_lookup_match_state(route.AuditError("tunnel_lookup_multiple")),
            "multiple",
        )
        self.assertEqual(
            route._tunnel_lookup_match_state(route.AuditError("private-detail")),
            "unknown",
        )

        none_report = route._unknown_report(
            self.contract, "tunnel_lookup", "ambiguous", "none"
        )
        multiple_report = route._unknown_report(
            self.contract, "tunnel_lookup", "ambiguous", "multiple"
        )
        self.assertEqual(none_report["tunnel_lookup_match_state"], "none")
        self.assertEqual(multiple_report["tunnel_lookup_match_state"], "multiple")
        for report in (none_report, multiple_report):
            rendered = json.dumps(report, sort_keys=True)
            self.assertNotIn("match_count", rendered)
            self.assertNotIn("matching_tunnels", rendered)

    def test_route_origin_capability_is_explicitly_unbound(self) -> None:
        capability = self.contract["route_origin_runtime_capability"]
        self.assertEqual(capability["status"], "unbound")
        self.assertEqual(
            capability["required_cloudflare_permission"],
            "Cloudflare Tunnel Read",
        )
        self.assertFalse(capability["existing_p1d03_access_lane_reusable"])
        self.assertFalse(capability["runtime_execution_allowed"])
        self.assertTrue(
            capability["binding_requires_separate_owner_authorized_source_change"]
        )
        self.assertFalse(capability["secret_or_permission_provisioning_authorized_here"])
        with self.assertRaisesRegex(
            route.AuditError,
            "tunnel_read_capability_unbound",
        ):
            route._require_tunnel_read_capability(self.contract)

    def test_bound_capability_requires_explicit_binding_contract_ref(self) -> None:
        contract = json.loads(json.dumps(self.contract))
        capability = contract["route_origin_runtime_capability"]
        capability["status"] = "bound"
        capability["runtime_execution_allowed"] = True
        with self.assertRaisesRegex(
            route.AuditError,
            "route_origin_capability_contract_invalid",
        ):
            route._require_tunnel_read_capability(contract)

        capability["binding_contract_ref"] = "ops/contracts/example-tunnel-read.json"
        route._require_tunnel_read_capability(contract)

    def test_unbound_capability_report_is_sanitized(self) -> None:
        report = route._unknown_report(self.contract, "capability_binding")
        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["failure_class"], "capability_binding")
        self.assertEqual(report["capability_requirement"], "tunnel-read")
        self.assertEqual(report["capability_binding"], "unbound")
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("account_id", rendered)
        self.assertNotIn("tunnel_id", rendered)
        self.assertNotIn("api_token", rendered)

    def test_unbound_capability_blocks_before_cloudflare_client(self) -> None:
        with mock.patch.object(
            route,
            "_load_contract",
            return_value=self.contract,
        ), mock.patch.object(route, "CloudflareGetClient") as client:
            rc = route.main()
        self.assertEqual(rc, 2)
        client.assert_not_called()

    def test_workflow_injects_no_cloudflare_secret_while_tunnel_read_unbound(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "CLOUDFLARE_P1D03_ACCOUNT_ID",
            "CLOUDFLARE_P1D03_READ_API_TOKEN",
            "CLOUDFLARE_P1D03_OWNER_EMAIL",
            "CLOUDFLARE_WRITE_API_TOKEN",
            "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
            "secrets.",
        ):
            self.assertNotIn(forbidden, workflow)

    def test_source_uses_official_get_paths_and_no_raw_output_fields(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('/cfd_tunnel"', source)
        self.assertIn('/configurations"', source)
        self.assertIn('"name": EXPECTED_TUNNEL_NAME', source)
        self.assertIn('"is_deleted": "false"', source)
        self.assertIn('"failure_class": failure_class', source)
        self.assertIn('report["tunnel_lookup_detail"] = tunnel_lookup_detail', source)
        self.assertIn('report["tunnel_lookup_match_state"] = tunnel_lookup_match_state', source)
        for forbidden_output_key in (
            '"tunnel_id":',
            '"account_id":',
            '"service":',
            '"port":',
            '"raw_api_payload":',
            '"match_count":',
            '"matching_tunnels":',
        ):
            self.assertNotIn(forbidden_output_key, source)


if __name__ == "__main__":
    unittest.main()
