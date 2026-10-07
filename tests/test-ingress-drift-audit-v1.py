#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ingress_drift_audit as audit  # noqa: E402
import ingress_drift_host as host  # noqa: E402

REGISTRY_PATH = ROOT / "ops" / "contracts" / "ingress-registry-v1.json"
AUDIT_PATH = ROOT / "ops" / "contracts" / "ingress-drift-audit-v1.json"
ADMIN_PATH = ROOT / "ops" / "contracts" / "admin-zone-remaining-infra-verifier-v1.json"
PRIVATE_PATH = ROOT / "ops" / "contracts" / "private-zone-verification-v1.json"

SHA = "a" * 40
LAN_ADDRESS = "192.0.2.7"
LAN_NETWORK = "192.0.2.0/24"


class IngressDriftAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.contract = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        cls.admin = json.loads(ADMIN_PATH.read_text(encoding="utf-8"))
        cls.private = json.loads(PRIVATE_PATH.read_text(encoding="utf-8"))
        cls.targets = host._derive_targets(
            cls.registry,
            cls.contract,
            cls.admin,
            cls.private,
        )

    def clean_host_report(self) -> dict:
        listeners: dict[int, set[str]] = {}
        docker: dict[int, set[str]] = {}
        ufw_lines = ["Status: active"]
        index = 1
        for target in self.targets.values():
            port = target["probe_port"]
            if target["desired_origin_class"] == "loopback":
                listeners[port] = {"loopback"}
                docker[port] = {"loopback"}
            else:
                listeners[port] = {"lan"}
                docker[port] = {"lan"}
                ufw_lines.append(
                    f"[ {index}] {port}/tcp ALLOW IN {LAN_NETWORK}"
                )
                index += 1
        connector = {
            "service_active": True,
            "service_enabled": True,
            "edge_connection_count": 4,
            "drift_codes": [],
            "result": "PASS",
        }
        return host.build_report(
            expected_main=SHA,
            targets=self.targets,
            listeners=listeners,
            docker_publishes=docker,
            ufw_text="\n".join(ufw_lines),
            lan_address=LAN_ADDRESS,
            lan_network=LAN_NETWORK,
            connector=connector,
        )

    def clean_cloudflare_report(self) -> dict:
        rows = []
        for item in self.registry["services"]:
            origin = (
                "loopback"
                if item["desired_origin_class"] == "loopback"
                else "private-lan"
            )
            rows.append(
                {
                    "hostname": item["hostname"],
                    "route": {"origin_class": origin},
                }
            )
        return {
            "audit": "phase7-cloudflare-route-reconciliation",
            "mutation_performed": False,
            "blockers": [],
            "hostnames": rows,
        }

    def test_contract_is_non_authorizing_and_reuses_existing_cloudflare_client(self) -> None:
        authority = self.contract["authority"]
        self.assertFalse(authority["source_merge_proves_runtime_state"])
        self.assertFalse(authority["source_merge_authorizes_runtime_execution"])
        self.assertFalse(authority["source_merge_authorizes_cloudflare_write"])
        self.assertFalse(authority["source_merge_authorizes_host_mutation"])
        self.assertTrue(authority["runtime_execution_requires_fresh_owner_authorization"])
        cloud = self.contract["cloudflare_component"]
        self.assertTrue(cloud["api_client_reuse_required"])
        self.assertTrue(cloud["new_write_capable_client_forbidden"])
        self.assertEqual(cloud["allowed_http_methods"], ["GET"])
        self.assertEqual(cloud["token_transport"], "stdin-only")
        self.assertFalse(cloud["token_environment_allowed"])

    def test_target_set_is_exact_registry_set_and_reuses_zone_contracts(self) -> None:
        service_ids = {item["service_id"] for item in self.registry["services"]}
        self.assertEqual(set(self.targets), service_ids)
        self.assertEqual(len(self.targets), 13)

        public_ids = {
            item["service_id"]
            for item in self.contract["host_component"]["public_probe_targets"]
        }
        self.assertEqual(
            public_ids,
            {"apex-web", "hermes-tech", "coloring-pages", "weather-public"},
        )

        admin_ids = {
            item["service_id"]
            for item in self.admin["host_probe_targets"]
        }
        self.assertTrue(admin_ids.issubset(self.targets))
        self.assertEqual(
            self.private["service_projections"][0]["service_id"],
            "hermes-deals",
        )

    def test_clean_host_and_cloudflare_evidence_combines_to_pass(self) -> None:
        host_report = self.clean_host_report()
        self.assertEqual(host_report["result"], "PASS")

        report = audit.build_report(
            expected_main=SHA,
            registry=self.registry,
            audit=self.contract,
            cloudflare_report=self.clean_cloudflare_report(),
            host_report=host_report,
        )
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["cloudflare"]["result"], "PASS")
        self.assertEqual(report["connector"]["result"], "PASS")
        self.assertEqual(len(report["services"]), 13)
        self.assertTrue(all(item["result"] == "PASS" for item in report["services"]))

        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn(LAN_ADDRESS, rendered)
        self.assertNotIn(LAN_NETWORK, rendered)
        self.assertNotIn('"probe_port"', rendered)
        for target in self.targets.values():
            self.assertNotIn(f'"port": {target["probe_port"]}', rendered)

    def test_unknown_cloudflare_route_is_drift_without_access_policy_coupling(self) -> None:
        cloud = self.clean_cloudflare_report()
        cloud["blockers"] = [
            "unclassified_tunnel_hostname:rogue.rozkalns.net",
            "public_hostname_has_access_application:tech.rozkalns.net",
        ]
        report = audit.build_report(
            expected_main=SHA,
            registry=self.registry,
            audit=self.contract,
            cloudflare_report=cloud,
            host_report=self.clean_host_report(),
        )
        self.assertEqual(report["result"], "DRIFT")
        self.assertEqual(
            report["cloudflare"]["drift_codes"],
            ["cloudflare_route_inventory_drift"],
        )
        self.assertEqual(
            report["cloudflare"]["reason_codes"],
            ["unclassified_tunnel_hostname:rogue.rozkalns.net"],
        )

    def test_route_origin_drift_is_service_scoped(self) -> None:
        cloud = self.clean_cloudflare_report()
        row = next(item for item in cloud["hostnames"] if item["hostname"] == "rozkalns.net")
        row["route"] = {"origin_class": "private-lan"}

        report = audit.build_report(
            expected_main=SHA,
            registry=self.registry,
            audit=self.contract,
            cloudflare_report=cloud,
            host_report=self.clean_host_report(),
        )
        apex = next(item for item in report["services"] if item["service_id"] == "apex-web")
        self.assertEqual(apex["result"], "DRIFT")
        self.assertIn("route_origin_class_drift", apex["drift_codes"])

    def test_host_classifier_flags_wildcard_docker_publish(self) -> None:
        target = copy.deepcopy(self.targets["portainer"])
        report = host._service_report(
            target,
            listener_classes={"lan"},
            docker_classes={"wildcard"},
            firewall_class="lan-only",
        )
        self.assertEqual(report["result"], "DRIFT")
        self.assertIn("unexpected_wildcard_publish", report["drift_codes"])
        self.assertIn("admin_break_glass_broadened", report["drift_codes"])

    def test_host_classifier_flags_missing_loopback(self) -> None:
        target = copy.deepcopy(self.targets["apex-web"])
        report = host._service_report(
            target,
            listener_classes=set(),
            docker_classes=set(),
            firewall_class="none",
        )
        self.assertEqual(report["result"], "DRIFT")
        self.assertIn("expected_loopback_missing", report["drift_codes"])
        self.assertIn("listener_bind_drift", report["drift_codes"])

    def test_host_classifier_flags_break_glass_missing_and_broadened(self) -> None:
        target = copy.deepcopy(self.targets["grafana"])
        missing = host._service_report(
            target,
            listener_classes=set(),
            docker_classes=set(),
            firewall_class="none",
        )
        self.assertIn("admin_break_glass_missing", missing["drift_codes"])

        broadened = host._service_report(
            target,
            listener_classes={"wildcard"},
            docker_classes={"wildcard"},
            firewall_class="broad",
        )
        self.assertIn("admin_break_glass_broadened", broadened["drift_codes"])
        self.assertIn("firewall_exposure_drift", broadened["drift_codes"])

    def test_connector_drift_propagates_to_overall_result(self) -> None:
        host_report = self.clean_host_report()
        host_report["connector"] = {
            "service_active": False,
            "service_enabled": True,
            "edge_connection_count": 3,
            "drift_codes": ["cloudflared_service_drift", "connector_health_drift"],
            "result": "DRIFT",
        }
        host_report["result"] = "DRIFT"
        report = audit.build_report(
            expected_main=SHA,
            registry=self.registry,
            audit=self.contract,
            cloudflare_report=self.clean_cloudflare_report(),
            host_report=host_report,
        )
        self.assertEqual(report["result"], "DRIFT")
        self.assertEqual(report["connector"]["result"], "DRIFT")

    def test_host_source_is_bounded_metadata_only(self) -> None:
        source = (ROOT / "scripts" / "ingress_drift_host.py").read_text(encoding="utf-8")
        self.assertIn('["ss", "-H", "-lnt"]', source)
        self.assertNotIn("-lntp", source)
        self.assertIn('["docker", "ps", "--format", "{{.Ports}}"]', source)
        self.assertIn('["sudo", "-n", "ufw", "status", "numbered"]', source)
        self.assertIn('["systemctl", "is-active", "cloudflared.service"]', source)
        self.assertIn('["systemctl", "is-enabled", "cloudflared.service"]', source)
        self.assertIn("http://127.0.0.1:20241/metrics", source)

        for forbidden in (
            "docker inspect",
            "docker logs",
            "docker exec",
            "docker stop",
            "docker restart",
            "ufw allow",
            "ufw delete",
            "systemctl restart",
            "systemctl stop",
            "systemctl start",
            "journalctl",
            "iptables",
            "nft ",
            ".env",
            "/proc/",
        ):
            self.assertNotIn(forbidden, source)

    def test_phase7_reuses_cloudflare_module_without_new_http_client(self) -> None:
        source = (ROOT / "scripts" / "ingress_drift_audit.py").read_text(encoding="utf-8")
        self.assertIn("import cloudflare_zero_trust_reconcile as cloudflare", source)
        self.assertIn("cloudflare.CloudflareGetClient", source)
        self.assertNotIn("cloudflare.collect_state", source)
        self.assertIn(
            'client.get(f"/accounts/{account_id}/tokens/verify")',
            source,
        )
        self.assertIn("cfd_tunnel/{tunnel_id}", source)
        self.assertIn("_discover_tunnel_id", source)
        self.assertIn("tunnel_id_env_forbidden", source)
        self.assertNotIn("/access/apps", source)
        self.assertNotIn("/access/organizations", source)
        self.assertIn("sys.stdin.readline", source)
        self.assertIn("cloudflare_token_env_forbidden", source)
        self.assertNotIn("cloudflare.require_bindings()", source)
        self.assertNotIn("urllib.request", source)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotIn(f'method="{method}"', source)
            self.assertNotIn(f"method='{method}'", source)

    def test_output_contract_forbids_private_and_protected_material(self) -> None:
        forbidden = set(self.contract["sanitized_output"]["forbidden_output"])
        for item in (
            "private-ip-addresses",
            "private-subnets",
            "ports",
            "raw-firewall-rules",
            "process-identities",
            "container-identities",
            "container-environments",
            "application-config",
            "application-logs",
            "application-data",
            "credentials",
            "tokens",
            "cookies",
            "session-material",
            "account-identifiers",
            "tunnel-identifiers",
            "access-audience-values",
        ):
            self.assertIn(item, forbidden)


    def test_phase7_discovers_single_tunnel_without_tunnel_id_binding(self) -> None:
        tunnel_id = "11111111-1111-4111-8111-111111111111"

        class Client:
            def __init__(self):
                self.calls = []

            def get(self, path, query=None):
                self.calls.append((path, query))
                return {
                    "result": [{
                        "id": tunnel_id,
                        "name": "rpi5-tunnel",
                        "config_src": "cloudflare",
                    }]
                }

        client = Client()
        observed = audit._discover_tunnel_id(client, "a" * 32)
        self.assertEqual(observed, tunnel_id)
        self.assertEqual(
            client.calls,
            [(
                "/accounts/" + "a" * 32 + "/cfd_tunnel",
                {
                    "name": "rpi5-tunnel",
                    "is_deleted": "false",
                    "per_page": 100,
                },
            )],
        )

    def test_runtime_boundary_uses_tunnel_secret_and_no_external_tunnel_id(self) -> None:
        boundary = self.contract["runtime_boundary"]
        self.assertEqual(
            boundary["credential_path"],
            "/etc/rpi5-secrets/cloudflare/tunnel-writer.json",
        )
        self.assertFalse(boundary["access_credential_reuse_allowed"])
        self.assertEqual(boundary["token_transport_to_audit"], "stdin-only")
        cloud = self.contract["cloudflare_component"]
        self.assertFalse(cloud["tunnel_id_environment_allowed"])
        self.assertIn("/accounts/{account_id}/cfd_tunnel", cloud["allowed_get_surfaces"])
        self.assertEqual(
            cloud["tunnel_id_binding"],
            "discover-single-remotely-managed-rpi5-tunnel-by-name",
        )


    def test_phase7_account_owned_token_uses_account_verify_endpoint(self) -> None:
        source = (ROOT / "scripts" / "ingress_drift_audit.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'client.get(f"/accounts/{account_id}/tokens/verify")',
            source,
        )
        self.assertNotIn('client.get("/user/tokens/verify")', source)
        surfaces = self.contract["cloudflare_component"]["allowed_get_surfaces"]
        self.assertIn("/accounts/{account_id}/tokens/verify", surfaces)
        self.assertNotIn("/user/tokens/verify", surfaces)

    def test_weather_wildcard_publish_remains_drift_against_loopback_policy(self) -> None:
        target = copy.deepcopy(self.targets["weather-public"])
        self.assertEqual(target["hostname"], "weather.rozkalns.net")
        self.assertEqual(target["desired_origin_class"], "loopback")
        report = host._service_report(
            target,
            listener_classes={"wildcard"},
            docker_classes={"wildcard"},
            firewall_class="none",
        )
        self.assertEqual(report["result"], "DRIFT")
        self.assertIn("expected_loopback_missing", report["drift_codes"])
        self.assertIn("listener_bind_drift", report["drift_codes"])
        self.assertIn("docker_publish_drift", report["drift_codes"])
        self.assertIn("unexpected_wildcard_publish", report["drift_codes"])

    def test_weather_probe_target_is_bound_to_reviewed_public_runtime_source(self) -> None:
        target = next(
            item
            for item in self.contract["host_component"]["public_probe_targets"]
            if item["service_id"] == "weather-public"
        )
        self.assertEqual(target["probe_port"], 9180)
        self.assertIn(
            "rozkalnsandris/rozkalns_weather@",
            target["port_source_ref"],
        )
        self.assertTrue(target["port_source_ref"].endswith("deploy/docker-compose.public.yml"))

if __name__ == "__main__":
    unittest.main()