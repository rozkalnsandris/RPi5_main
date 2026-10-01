#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


collector = load("adguard_dns_preflight", ROOT / "ops/bin/adguard-dns-preflight")
verifier = load("adguard_dns_preflight_verify", ROOT / "ops/bin/adguard-dns-preflight-verify")


class AdGuardDnsHardeningTests(unittest.TestCase):
    def ready_payload(self):
        return {
            "schema": collector.SCHEMA,
            "status": "PASS",
            "mutation_started": False,
            "authorization_consumed": False,
            "privacy": {
                "raw_query_log_read": False,
                "client_identity_exported": False,
                "raw_adguard_config_read": False,
                "container_environment_read": False,
                "docker_inspect_used": False,
                "credentials_read": False,
                "raw_network_addresses_emitted": False,
            },
            "adguard": {"running": True, "version": "v0.107.79"},
            "dns_listeners": {"tcp_53": True, "udp_53": True},
            "host_resolver_classes": ["default_gateway", "ipv4_public", "ipv6_link_local", "loopback"],
            "ufw": {
                "available": True,
                "dns_lan_allow_present": True,
                "dns_world_allow_present": False,
            },
            "ordinary_dns": {"adguard_loopback_answered": True},
            "private_ptr": {
                "direct_gateway_answered": True,
                "adguard_loopback_answered": False,
                "defect_confirmed": True,
            },
        }

    def test_route_and_resolver_classification(self):
        gateway, device = collector.parse_default_route("default via 192.0.2.1 dev eth0 metric 100\n")
        self.assertEqual((gateway, device), ("192.0.2.1", "eth0"))
        raw = "127.0.0.1\n1.1.1.1\nfe80::1\n"
        self.assertEqual(
            collector.parse_nmcli_dns(raw, gateway),
            ["ipv4_public", "ipv6_link_local", "loopback"],
        )

    def test_nmcli_dns_values_only_format_fails_closed_on_labels(self):
        with self.assertRaisesRegex(collector.PreflightError, "resolver_address_invalid"):
            collector.parse_nmcli_dns("IP4.DNS[1]:127.0.0.1\n", "192.0.2.1")

    def test_listener_and_ufw_reduction(self):
        listeners = collector.parse_dns_listeners(
            "udp UNCONN 0 0 *:53 *:*\n"
            "tcp LISTEN 0 4096 *:53 *:*\n"
        )
        self.assertEqual(listeners, {"tcp_53": True, "udp_53": True})
        ufw = collector.parse_ufw_dns_exposure(
            "53/tcp ALLOW 10.23.0.0/24\n53/udp ALLOW 10.23.0.0/24\n"
        )
        self.assertTrue(ufw["dns_lan_allow_present"])
        self.assertFalse(ufw["dns_world_allow_present"])

    def test_ready_payload_verifies(self):
        result = verifier.verify(self.ready_payload())
        self.assertEqual(result["status"], "READY_PHASE1")
        self.assertTrue(result["private_ptr_defect_confirmed"])
        self.assertTrue(result["phase2_parallel_host_resolver_present"])
        self.assertTrue(result["phase3_ipv6_router_resolver_present"])
        self.assertFalse(result["mutation_started"])
        self.assertFalse(result["authorization_consumed"])

    def test_defect_must_be_behaviorally_proven(self):
        payload = self.ready_payload()
        payload["private_ptr"]["direct_gateway_answered"] = False
        payload["private_ptr"]["defect_confirmed"] = False
        with self.assertRaisesRegex(verifier.VerifyError, "private_ptr_defect_not_proven"):
            verifier.verify(payload)

    def test_privacy_and_read_only_boundaries_fail_closed(self):
        payload = self.ready_payload()
        payload["privacy"]["raw_adguard_config_read"] = True
        with self.assertRaisesRegex(verifier.VerifyError, "privacy_boundary_invalid"):
            verifier.verify(payload)
        payload = self.ready_payload()
        payload["mutation_started"] = True
        with self.assertRaisesRegex(verifier.VerifyError, "read_only_boundary_invalid"):
            verifier.verify(payload)

    def test_phase1_contract_is_source_disabled_and_narrow(self):
        contract = json.loads(
            (ROOT / "ops/contracts/adguard-private-ptr-phase1-v1.json").read_text(encoding="utf-8")
        )
        self.assertTrue(contract["source_only"])
        self.assertFalse(contract["execution_enabled"])
        mutation = contract["mutation"]
        self.assertEqual(mutation["max_forward_writes"], 1)
        self.assertEqual(mutation["allowed_request_keys"], ["local_ptr_upstreams"])
        self.assertEqual(mutation["required_request_keys"], ["local_ptr_upstreams"])
        self.assertTrue(mutation["partial_update_only"])
        self.assertTrue(mutation["other_fields_must_be_omitted"])
        self.assertFalse(mutation["protected_full_dns_config_read_allowed"])
        self.assertTrue(mutation["application_internal_reconfigure_expected"])
        self.assertFalse(mutation["container_restart_allowed"])
        self.assertFalse(contract["failure"]["automatic_retry"])
        self.assertFalse(contract["failure"]["automatic_rollback"])

    def test_collect_emits_no_raw_network_addresses(self):
        def fake(command):
            cmd = tuple(command)
            if cmd == ("ip", "-4", "route", "show", "default"):
                return collector.CommandResult(0, "default via 192.0.2.1 dev eth0 metric 100\n")
            if cmd[:2] == ("docker", "ps"):
                return collector.CommandResult(0, "adguard\n")
            if cmd[:2] == ("docker", "exec"):
                return collector.CommandResult(0, "AdGuard Home, version v0.107.79\n")
            if cmd[:4] == ("ss", "-H", "-lntu"):
                return collector.CommandResult(0, "udp UNCONN 0 0 *:53 *:*\ntcp LISTEN 0 4096 *:53 *:*\n")
            if cmd[:3] == ("nmcli", "-e", "no"):
                self.assertEqual(
                    cmd,
                    ("nmcli", "-e", "no", "-g", "IP4.DNS,IP6.DNS", "device", "show", "eth0"),
                )
                return collector.CommandResult(0, "127.0.0.1\n1.1.1.1\nfe80::1\n")
            if cmd[:3] == ("sudo", "-n", "/usr/sbin/ufw"):
                return collector.CommandResult(0, "Status: active\n")
            if cmd[0] == "dig" and "example.com." in cmd:
                return collector.CommandResult(0, "93.184.216.34\n")
            if cmd[0] == "dig" and "@192.0.2.1" in cmd:
                return collector.CommandResult(0, "gateway.example.\n")
            if cmd[0] == "dig" and "@127.0.0.1" in cmd:
                return collector.CommandResult(0, "")
            raise AssertionError(cmd)

        payload = collector.collect(fake)
        rendered = json.dumps(payload, sort_keys=True)
        self.assertNotIn("192.0.2.1", rendered)
        self.assertNotIn("1.1.1.1", rendered)
        self.assertNotIn("fe80::1", rendered)
        self.assertTrue(payload["private_ptr"]["defect_confirmed"])

    def test_ufw_metadata_must_be_available(self):
        payload = self.ready_payload()
        payload["ufw"]["available"] = False
        with self.assertRaisesRegex(verifier.VerifyError, "ufw_metadata_unavailable"):
            verifier.verify(payload)


if __name__ == "__main__":
    unittest.main()
