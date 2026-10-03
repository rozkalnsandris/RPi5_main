#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

EXTERNAL_PATH = ROOT / "scripts" / "cloudflare_phase4_admin_remaining_infra_actions.py"
HOST_PATH = ROOT / "scripts" / "cloudflare_phase4_admin_remaining_infra_host.py"
BRIDGE_PATH = ROOT / "scripts" / "github_phase4_admin_remaining_infra_bridge.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "cloudflare-phase4-admin-remaining-infra.yml"
ADMIN_PATH = ROOT / "ops" / "contracts" / "admin-zone-verification-v1.json"
VERIFIER_PATH = ROOT / "ops" / "contracts" / "admin-zone-remaining-infra-verifier-v1.json"
REGISTRY_PATH = ROOT / "ops" / "contracts" / "ingress-registry-v1.json"

OWNER_ID = 277435981
SHA = "a" * 40


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


external = load_module("remaining_external", EXTERNAL_PATH)
host = load_module("remaining_host", HOST_PATH)
bridge = load_module("remaining_bridge", BRIDGE_PATH)


def event(body: str, *, app_authored: bool = False) -> dict:
    return {
        "action": "created",
        "issue": {"number": 819},
        "comment": {
            "id": 123,
            "body": body,
            "author_association": "OWNER",
            "performed_via_github_app": {"id": 1} if app_authored else None,
            "user": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
        },
        "sender": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
    }


class Phase4RemainingInfraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.admin = json.loads(ADMIN_PATH.read_text(encoding="utf-8"))
        cls.verifier = json.loads(VERIFIER_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_contract_is_non_authorizing_and_split_by_execution_surface(self) -> None:
        authority = self.verifier["authority"]
        for key in (
            "source_merge_proves_runtime_state",
            "source_merge_authorizes_runtime_execution",
            "source_merge_authorizes_protected_admin_context",
            "source_merge_authorizes_cloudflare_write",
            "source_merge_authorizes_live_mutation",
        ):
            self.assertFalse(authority[key])
        self.assertTrue(authority["external_execution_requires_fresh_owner_authorization"])
        self.assertTrue(authority["host_execution_requires_fresh_owner_authorization"])
        self.assertEqual(
            self.verifier["external_component"]["execution_surface"],
            "github-hosted-actions",
        )
        self.assertEqual(
            self.verifier["host_component"]["execution_surface"],
            "owner-authorized-rpi5-read-only",
        )

    def test_probe_targets_match_exact_admin_set(self) -> None:
        projections = {
            item["service_id"]: item
            for item in self.admin["service_projections"]
        }
        targets = {
            item["service_id"]: item
            for item in self.verifier["host_probe_targets"]
        }
        self.assertEqual(set(targets), set(projections))
        self.assertEqual(len(targets), 8)
        for service_id, target in targets.items():
            self.assertEqual(target["hostname"], projections[service_id]["hostname"])
            self.assertIsInstance(target["probe_port"], int)
            self.assertGreater(target["probe_port"], 0)
            self.assertTrue(target["port_source_ref"])

    def test_external_http_classification_is_fail_closed(self) -> None:
        self.assertEqual(
            external._classify_http_status(
                302,
                "https://team.cloudflareaccess.com/cdn-cgi/access/login/example",
            ),
            "access-challenge",
        )
        self.assertEqual(external._classify_http_status(403, None), "denied")
        self.assertEqual(external._classify_http_status(401, None), "denied")
        self.assertEqual(external._classify_http_status(200, None), "public")
        self.assertEqual(
            external._classify_http_status(302, "https://example.com/other"),
            "public",
        )
        self.assertEqual(external._classify_http_status(503, None), "unknown")

    def test_external_report_is_sanitized_and_passes_expected_classes(self) -> None:
        access_report = {
            "services": [
                {
                    "hostname": item["hostname"],
                    "bypass_present": False,
                    "result": "PASS",
                }
                for item in self.admin["service_projections"]
            ]
        }
        classes = {
            item["hostname"]: "access-challenge"
            for item in self.admin["service_projections"]
        }
        report = external.build_report(
            self.admin,
            self.verifier,
            self.registry,
            access_report,
            classes,
        )
        self.assertEqual(report["result"], "PASS")
        self.assertTrue(all(item["result"] == "PASS" for item in report["services"]))
        rendered = json.dumps(report, sort_keys=True)
        for forbidden in (
            "redirect_location",
            "account_id",
            "api_token",
            "app_id",
            "policy_id",
            "port",
            "listener_address",
            "process_identity",
            "container_identity",
        ):
            self.assertNotIn(f'"{forbidden}":', rendered)

    def test_external_source_never_reads_body_or_sends_identity_material(self) -> None:
        source = EXTERNAL_PATH.read_text(encoding="utf-8")
        self.assertNotIn("response.read(", source)
        self.assertNotIn("exc.read(", source)
        self.assertNotIn('"Authorization"', source)
        self.assertNotIn('"Cookie"', source)
        self.assertIn("NoRedirect", source)
        self.assertIn("CLOUDFLARE_P1D03_READ_API_TOKEN", source)
        self.assertNotIn("CLOUDFLARE_TUNNEL_API_TOKEN = os.environ", source)

    def test_host_bind_classifier_and_sanitized_report(self) -> None:
        lan_address = "198.51.100.7"
        listeners: dict[int, set[str]] = {}
        for target in self.verifier["host_probe_targets"]:
            projection = next(
                item
                for item in self.admin["service_projections"]
                if item["service_id"] == target["service_id"]
            )
            listeners[target["probe_port"]] = (
                {"127.0.0.1"}
                if projection["expected_origin_class"] == "loopback"
                else {lan_address}
            )

        def lan_path(_address: str, port: int) -> str:
            dash_port = next(
                item["probe_port"]
                for item in self.verifier["host_probe_targets"]
                if item["service_id"] == "dashboard-rpi5"
            )
            return "absent" if port == dash_port else "present"

        with mock.patch.object(host, "_lan_path_class", side_effect=lan_path):
            report = host.build_report(
                expected_main=SHA,
                admin=self.admin,
                verifier=self.verifier,
                listeners=listeners,
                lan_address=lan_address,
            )

        self.assertEqual(report["result"], "PASS")
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn(lan_address, rendered)
        for target in self.verifier["host_probe_targets"]:
            self.assertNotIn(f'"probe_port": {target["probe_port"]}', rendered)
        self.assertNotIn('"process_identity":', rendered)
        self.assertNotIn('"container_identity":', rendered)

    def test_host_source_uses_only_bounded_read_only_observation(self) -> None:
        source = HOST_PATH.read_text(encoding="utf-8")
        self.assertIn('["ss", "-H", "-lnt"]', source)
        self.assertIn('["ip", "-j", "-4", "route", "get", "1.1.1.1"]', source)
        self.assertIn("socket.create_connection", source)
        for forbidden in (
            "docker inspect",
            "docker logs",
            "systemctl",
            "journalctl",
            "ufw ",
            "nft ",
            "iptables",
            "/proc/",
            ".env",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("-lntp", source)

    def test_bridge_requires_direct_owner_comment(self) -> None:
        body = (
            f"/rpi5-p4-remaining-infra-external check HEAD={SHA} "
            "CANARY=phase4-admin-remaining-infra-external-v1"
        )
        out = bridge.authorize_event(
            event(body),
            repository="rozkalnsandris/RPi5_main",
            github_sha=SHA,
            run_attempt="1",
        )
        self.assertEqual(out["expected_sha"], SHA)
        with self.assertRaisesRegex(
            bridge.AuthorizationError,
            "app_authored_comment_forbidden",
        ):
            bridge.authorize_event(
                event(body, app_authored=True),
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="1",
            )

    def test_workflow_injects_only_access_read_lane(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("CLOUDFLARE_P1D03_ACCOUNT_ID", workflow)
        self.assertIn("CLOUDFLARE_P1D03_READ_API_TOKEN", workflow)
        self.assertNotIn("CLOUDFLARE_TUNNEL_API_TOKEN", workflow)
        self.assertNotIn("CLOUDFLARE_WRITE_API_TOKEN", workflow)
        self.assertNotIn("workflow_dispatch", workflow)

    def test_output_contract_forbids_sensitive_runtime_fields(self) -> None:
        output = self.verifier["sanitized_output"]
        forbidden = set(output["forbidden_output"])
        for item in (
            "response-body",
            "redirect-location",
            "cookies",
            "credentials",
            "tokens",
            "private-ip-addresses",
            "listener-addresses",
            "ports",
            "process-identities",
            "container-identities",
            "raw-command-output",
        ):
            self.assertIn(item, forbidden)


if __name__ == "__main__":
    unittest.main()
