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
P1D03_CONTRACT_PATH = ROOT / "ops" / "contracts" / "cloudflare-p1d03-github-delivery.json"
TUNNEL_OPERATOR_PATH = ROOT / "ops" / "contracts" / "cloudflare-tunnel-operator-v1.json"

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
        cls.operator = json.loads(TUNNEL_OPERATOR_PATH.read_text(encoding="utf-8"))

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

    def test_route_origin_capability_uses_shared_tunnel_operator(self) -> None:
        capability = self.contract["route_origin_runtime_capability"]
        self.assertEqual(capability["status"], "bound")
        self.assertEqual(
            capability["required_cloudflare_permission"],
            "Cloudflare One Connector: cloudflared Write",
        )
        self.assertEqual(
            capability["binding_contract_ref"],
            "ops/contracts/cloudflare-tunnel-operator-v1.json",
        )
        self.assertEqual(
            capability["consumer_id"],
            "phase4-admin-route-origin-read-v1",
        )
        self.assertTrue(capability["shared_tunnel_operator_reusable"])
        self.assertFalse(capability["p1d03_access_lane_reusable"])
        self.assertTrue(capability["runtime_execution_allowed"])
        self.assertTrue(
            capability["runtime_execution_requires_fresh_owner_authorization"]
        )
        self.assertFalse(capability["cloudflare_mutation_allowed"])
        self.assertFalse(capability["secret_or_permission_provisioning_authorized_here"])
        route._require_tunnel_operator_read_consumer(self.contract, self.operator)

    def test_shared_tunnel_operator_has_one_stable_write_capable_credential(self) -> None:
        credential = self.operator["credential_model"]
        execution = self.operator["execution_model"]
        classes = self.operator["consumer_classes"]
        rotation = self.operator["rotation_semantics"]

        self.assertEqual(
            self.operator["schema"],
            "rozkalns.rpi5-main.cloudflare-tunnel-operator.v1",
        )
        self.assertEqual(self.operator["status"], "source-defined")
        self.assertEqual(
            credential["cloudflare_permission"],
            "Cloudflare One Connector: cloudflared Write",
        )
        self.assertEqual(
            credential["stable_account_id_secret"],
            "CLOUDFLARE_TUNNEL_ACCOUNT_ID",
        )
        self.assertEqual(
            credential["stable_api_token_secret"],
            "CLOUDFLARE_TUNNEL_API_TOKEN",
        )
        self.assertEqual(
            credential["dashboard_ui_mapping"],
            {
                "category": "Cloudflare One / Zero Trust",
                "permission_group": "Cloudflare One Connector: cloudflared",
                "access": "Edit",
            },
        )
        self.assertTrue(credential["exact_permission_required"])
        self.assertFalse(credential["broader_or_legacy_alternates_allowed"])
        for key in (
            "token_value_in_source_allowed",
            "token_creation_or_rotation_authorized_by_source",
            "repository_secret_provisioning_authorized_by_source",
            "reuse_outside_tunnel_capability_allowed",
            "dns_permission_included",
            "access_permission_included",
            "api_tokens_permission_included",
        ):
            self.assertFalse(credential[key])

        self.assertFalse(execution["possession_of_token_grants_operation_authority"])
        self.assertFalse(execution["caller_selected_method_allowed"])
        self.assertFalse(execution["caller_selected_endpoint_allowed"])
        self.assertFalse(execution["caller_selected_payload_allowed"])
        self.assertTrue(execution["reviewed_consumer_contract_required"])
        self.assertTrue(execution["exact_owner_authorization_required_for_write"])
        self.assertTrue(execution["write_mutation_budget_required"])
        self.assertTrue(execution["post_write_fail_closed_required"])
        self.assertFalse(execution["automatic_retry_after_write_ambiguity_allowed"])
        self.assertFalse(execution["automatic_rollback_after_write_ambiguity_allowed"])

        self.assertEqual(classes["read_only"]["allowed_methods"], ["GET"])
        self.assertFalse(classes["read_only"]["write_methods_allowed"])
        self.assertTrue(classes["write"]["operation_specific_source_contract_required"])
        self.assertTrue(classes["write"]["exact_target_required"])
        self.assertTrue(classes["write"]["exact_main_binding_required"])
        self.assertTrue(classes["write"]["fresh_explicit_owner_authorization_required"])

        self.assertTrue(rotation["stable_secret_aliases_preserved"])
        self.assertFalse(rotation["consumer_source_rewire_required_on_token_rotation"])
        self.assertTrue(
            rotation["token_replacement_requires_separate_owner_settings_authorization"]
        )

    def test_phase4_consumer_is_get_only_even_with_write_capable_token(self) -> None:
        consumers = [
            item
            for item in self.operator["initial_consumers"]
            if item["id"] == "phase4-admin-route-origin-read-v1"
        ]
        self.assertEqual(len(consumers), 1)
        consumer = consumers[0]
        self.assertEqual(consumer["class"], "read_only")
        self.assertEqual(consumer["allowed_methods"], ["GET"])
        self.assertEqual(
            consumer["allowed_paths"],
            [
                "/accounts/{account_id}/cfd_tunnel",
                "/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
            ],
        )
        self.assertFalse(consumer["cloudflare_mutation_allowed"])

    def test_shared_operator_rejects_weakened_read_write_gates(self) -> None:
        operator = json.loads(json.dumps(self.operator))
        operator["credential_model"]["cloudflare_permission"] = "Cloudflare Tunnel Write"
        with self.assertRaisesRegex(
            route.AuditError,
            "tunnel_operator_contract_invalid",
        ):
            route._require_tunnel_operator_read_consumer(self.contract, operator)

        operator = json.loads(json.dumps(self.operator))
        operator["credential_model"]["cloudflare_permission"] = "Cloudflare One Connectors Write"
        with self.assertRaisesRegex(
            route.AuditError,
            "tunnel_operator_contract_invalid",
        ):
            route._require_tunnel_operator_read_consumer(self.contract, operator)

        operator = json.loads(json.dumps(self.operator))
        operator["execution_model"]["caller_selected_method_allowed"] = True
        with self.assertRaisesRegex(
            route.AuditError,
            "tunnel_operator_contract_invalid",
        ):
            route._require_tunnel_operator_read_consumer(self.contract, operator)

        operator = json.loads(json.dumps(self.operator))
        operator["consumer_classes"]["read_only"]["write_methods_allowed"] = True
        with self.assertRaisesRegex(
            route.AuditError,
            "tunnel_operator_contract_invalid",
        ):
            route._require_tunnel_operator_read_consumer(self.contract, operator)

        operator = json.loads(json.dumps(self.operator))
        operator["consumer_classes"]["write"]["fresh_explicit_owner_authorization_required"] = False
        with self.assertRaisesRegex(
            route.AuditError,
            "tunnel_operator_contract_invalid",
        ):
            route._require_tunnel_operator_read_consumer(self.contract, operator)

    def test_p1d03_contract_does_not_bind_tunnel_get_surfaces(self) -> None:
        p1d03 = json.loads(P1D03_CONTRACT_PATH.read_text(encoding="utf-8"))
        surfaces = p1d03["preflight"]["get_surfaces"]
        self.assertNotIn("/accounts/{account_id}/cfd_tunnel", surfaces)
        self.assertFalse(any("/cfd_tunnel/" in item for item in surfaces))

    def test_route_source_uses_only_shared_tunnel_runtime_names(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("CLOUDFLARE_TUNNEL_ACCOUNT_ID", source)
        self.assertIn("CLOUDFLARE_TUNNEL_API_TOKEN", source)
        self.assertNotIn("CLOUDFLARE_PHASE4_TUNNEL_ACCOUNT_ID", source)
        self.assertNotIn("CLOUDFLARE_PHASE4_TUNNEL_READ_API_TOKEN", source)
        self.assertIn('"CLOUDFLARE_P1D03_ACCOUNT_ID"', source)
        self.assertIn('"CLOUDFLARE_P1D03_READ_API_TOKEN"', source)
        self.assertNotIn(
            'os.environ.pop("CLOUDFLARE_P1D03_ACCOUNT_ID"',
            source,
        )
        self.assertNotIn(
            'os.environ.pop("CLOUDFLARE_P1D03_READ_API_TOKEN"',
            source,
        )

    def test_missing_dedicated_secrets_blocks_before_cloudflare_client(self) -> None:
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "issue_comment",
            "PHASE4_ROUTE_CANARY": route.CANARY_ID,
            "PHASE4_EXPECTED_SHA": SHA,
            "GITHUB_SHA": SHA,
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "rozkalnsandris/RPi5_main",
            "GITHUB_TOKEN": "github-token-placeholder",
        }
        with mock.patch.dict(route.os.environ, env, clear=True), \
             mock.patch.object(route, "fetch_and_validate_exact_main"), \
             mock.patch.object(route, "CloudflareGetClient") as client:
            rc = route.main()
        self.assertEqual(rc, 2)
        client.assert_not_called()

    def test_workflow_injects_only_shared_tunnel_operator_secrets(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "CLOUDFLARE_TUNNEL_ACCOUNT_ID: "
            "${{ secrets.CLOUDFLARE_TUNNEL_ACCOUNT_ID }}",
            workflow,
        )
        self.assertIn(
            "CLOUDFLARE_TUNNEL_API_TOKEN: "
            "${{ secrets.CLOUDFLARE_TUNNEL_API_TOKEN }}",
            workflow,
        )
        self.assertNotIn("CLOUDFLARE_PHASE4_TUNNEL_", workflow)
        for forbidden in (
            "CLOUDFLARE_P1D03_ACCOUNT_ID",
            "CLOUDFLARE_P1D03_READ_API_TOKEN",
            "CLOUDFLARE_P1D03_OWNER_EMAIL",
            "CLOUDFLARE_WRITE_API_TOKEN",
            "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
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
