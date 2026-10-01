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

collector = load(
    "adguard_resolver_phase2_recovery_preflight",
    ROOT / "ops/bin/adguard-resolver-phase2-recovery-preflight",
)
verifier = load(
    "adguard_resolver_phase2_recovery_preflight_verify",
    ROOT / "ops/bin/adguard-resolver-phase2-recovery-preflight-verify",
)

class AdGuardResolverPhase2RecoveryTests(unittest.TestCase):
    def ready_payload(self):
        return {
            "schema": collector.SCHEMA,
            "status": "PASS",
            "mutation_started": False,
            "authorization_consumed": False,
            "privacy": {
                "raw_network_addresses_emitted": False,
                "connection_identity_emitted": False,
                "raw_networkmanager_profile_read": False,
                "dhcp6_option_values_emitted": False,
                "credentials_read": False,
            },
            "networkmanager": {
                "version": "nmcli tool, version 1.42.4",
                "default_route_device_fingerprint": "0123456789abcdef",
                "active_profile_fingerprint": "fedcba9876543210",
                "profile": {
                    "multi_connect_class": "single_effective",
                    "ipv4_method": "manual",
                    "ipv4_dns_classes": ["loopback"],
                    "ipv4_dns_count": 1,
                    "ipv4_ignore_auto_dns": True,
                    "ipv6_method": "auto",
                    "ipv6_dns_classes": [],
                    "ipv6_dns_count": 0,
                    "ipv6_ignore_auto_dns": True,
                },
                "runtime_dns_classes": ["ipv6_link_local", "loopback"],
                "runtime_dns_count": 2,
                "device_status": {"connected_nonloopback_count": 1},
                "dhcp6": {
                    "option_count": 4,
                    "dhcp6_name_servers_present": True,
                    "values_emitted": False,
                },
            },
            "resolv_conf": {
                "owner_class": "networkmanager_generated",
                "nameserver_classes": ["ipv6_link_local", "loopback"],
                "nameserver_count": 2,
                "rotate_present": False,
            },
            "systemd_resolved_active": False,
            "dns_listeners": {"tcp_53": True, "udp_53": True},
            "ordinary_dns": {"system_resolver_answered": True, "adguard_loopback_answered": True},
        }

    def test_multi_connect_default_and_single_are_effectively_single(self):
        self.assertEqual(collector.parse_multi_connect("0 (default)"), "single_effective")
        self.assertEqual(collector.parse_multi_connect("1"), "single_effective")
        self.assertEqual(collector.parse_multi_connect("2"), "manual_multiple")

    def test_dhcp6_parser_emits_only_metadata(self):
        parsed = collector.parse_dhcp6_options(
            "DHCP6.OPTION[1]:dhcp6_client_id = secret-client-id\n"
            "DHCP6.OPTION[2]:dhcp6_name_servers = fe80::1\n"
        )
        self.assertEqual(parsed["option_count"], 2)
        self.assertTrue(parsed["dhcp6_name_servers_present"])
        self.assertFalse(parsed["values_emitted"])
        self.assertNotIn("fe80::1", json.dumps(parsed))
        self.assertNotIn("secret-client-id", json.dumps(parsed))

    def test_ready_recovery_payload_verifies(self):
        result = verifier.verify(self.ready_payload())
        self.assertEqual(result["status"], "READY_PHASE2_RECOVERY")
        self.assertTrue(result["dhcp6_runtime_dns_stale_confirmed"])
        self.assertEqual(result["networkmanager_version"], "nmcli tool, version 1.42.4")

    def test_verifier_blocks_version_or_topology_drift(self):
        payload = self.ready_payload()
        payload["networkmanager"]["version"] = "nmcli tool, version 1.58.0"
        with self.assertRaisesRegex(verifier.VerifyError, "networkmanager_version_unexpected"):
            verifier.verify(payload)
        payload = self.ready_payload()
        payload["networkmanager"]["device_status"]["connected_nonloopback_count"] = 2
        with self.assertRaisesRegex(verifier.VerifyError, "connected_device_count_unexpected"):
            verifier.verify(payload)

    def test_verifier_requires_dhcp6_dns_provenance(self):
        payload = self.ready_payload()
        payload["networkmanager"]["dhcp6"]["dhcp6_name_servers_present"] = False
        with self.assertRaisesRegex(verifier.VerifyError, "dhcp6_dns_provenance_missing"):
            verifier.verify(payload)

    def test_recovery_contract_is_single_write_and_source_disabled(self):
        contract = json.loads(
            (ROOT / "ops/contracts/adguard-host-resolver-phase2-recovery-v1.json").read_text(encoding="utf-8")
        )
        self.assertTrue(contract["source_only"])
        self.assertFalse(contract["execution_enabled"])
        mutation = contract["mutation"]
        self.assertEqual(mutation["max_forward_writes"], 1)
        self.assertEqual(
            mutation["reactivation_write"]["argv_template"],
            ["--wait", "90", "connection", "up", "uuid", "<fresh-active-profile-uuid>", "ifname", "<fresh-default-route-device>"],
        )
        self.assertTrue(mutation["reactivation_write"]["expected_transient_connectivity_interruption"])
        self.assertFalse(mutation["reactivation_write"]["explicit_connection_down_command_allowed"])
        self.assertFalse(mutation["reactivation_write"]["networkmanager_restart_allowed"])
        self.assertFalse(mutation["package_upgrade_allowed"])
        self.assertFalse(contract["failure"]["automatic_retry"])
        self.assertFalse(contract["transport_failure"]["retry_command_after_transport_drop"])

    def test_collect_emits_no_raw_network_or_dhcp6_values(self):
        profile_uuid = "123e4567-e89b-12d3-a456-426614174000"
        def fake(command):
            cmd = tuple(command)
            if cmd == ("ip", "-4", "route", "show", "default"):
                return collector.CommandResult(0, "default via 192.0.2.1 dev eth0 metric 100\n")
            if cmd == ("nmcli", "--version"):
                return collector.CommandResult(0, "nmcli tool, version 1.42.4\n")
            if cmd == ("nmcli", "-g", "GENERAL.CON-UUID", "device", "show", "eth0"):
                return collector.CommandResult(0, profile_uuid + "\n")
            if cmd[:3] == ("nmcli", "-m", "multiline") and "connection" in cmd:
                return collector.CommandResult(
                    0,
                    "connection.multi-connect:0 (default)\n"
                    "ipv4.method:manual\nipv4.dns:127.0.0.1\nipv4.ignore-auto-dns:yes\n"
                    "ipv6.method:auto\nipv6.dns:\nipv6.ignore-auto-dns:yes\n",
                )
            if cmd[:3] == ("nmcli", "-m", "multiline") and "DHCP6.OPTION" in cmd:
                return collector.CommandResult(
                    0,
                    "DHCP6.OPTION[1]:dhcp6_client_id = private-id\n"
                    "DHCP6.OPTION[2]:dhcp6_name_servers = fe80::1\n",
                )
            if cmd[:3] == ("nmcli", "-m", "multiline") and "device" in cmd:
                return collector.CommandResult(0, "IP4.DNS[1]:127.0.0.1\nIP6.DNS[1]:fe80::1\n")
            if cmd == ("nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"):
                return collector.CommandResult(0, "eth0:ethernet:connected\nlo:loopback:connected\n")
            if cmd == ("systemctl", "is-active", "systemd-resolved"):
                return collector.CommandResult(3, "inactive\n")
            if cmd == ("ss", "-H", "-lntu"):
                return collector.CommandResult(0, "udp UNCONN 0 0 *:53 *:*\ntcp LISTEN 0 4096 *:53 *:*\n")
            if cmd[0] == "dig":
                return collector.CommandResult(0, "203.0.113.10\n")
            raise AssertionError(cmd)

        payload = collector.collect(
            fake,
            lambda: (
                "# Generated by NetworkManager\nnameserver 127.0.0.1\nnameserver fe80::1\n",
                "/run/NetworkManager/resolv.conf",
            ),
        )
        rendered = json.dumps(payload, sort_keys=True)
        for value in ("192.0.2.1", "fe80::1", "eth0", profile_uuid, "private-id"):
            self.assertNotIn(value, rendered)
        self.assertEqual(verifier.verify(payload)["status"], "READY_PHASE2_RECOVERY")

if __name__ == "__main__":
    unittest.main()
