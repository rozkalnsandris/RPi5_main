#!/usr/bin/env python3
"""Synthetic, disconnected regressions; no real Cloudflare/GoatCounter access."""
from copy import deepcopy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ausmalwiese_goatcounter_simple_readiness_v1 as m


def trusted_ip():
    return {
        "tunnel_peer": "verified_loopback_only",
        "host_header": "verified_pinned_vhost",
        "forwarded_headers": "trusted_proxy_overwrites_untrusted_values",
        "remote_addr": "verified_real_client_after_v2_7_0_processing",
        "spoof_test": "synthetic_spoof_rejected",
        "forwarded_proto": "verified_https",
    }


def sample():
    return {
        "schema_version": 1,
        "service": {
            "version": "v2.7.0", "state": "active",
            "listener": m.LISTENER, "vhost": m.VHOST,
            "collect": 130,
            "collect_provenance": "separately_authorized_sanitized_readback",
        },
        "edge": {
            "remote_tunnel": "verified_exact_config",
            "routes": {h: "absent_safe_before_app_catchall" for h in m.HOSTS},
            "worker_routes": "verified_no_count_interception",
            "worker_custom_domains": "verified_no_count_interception",
        },
        "ip": trusted_ip(),
        "privacy": {
            "approved_collect": 130,
            "notice": "reviewed_actual_processing_flow",
            "frontend": "off",
        },
    }


def household():
    return {
        "schema_version": 1,
        "ip": trusted_ip(),
        "egress": {"ipv4": "shared_stable_exact", "ipv6": "absent"},
        "mutation": {
            "target": "goatcounter_site_settings",
            "field": "ignore_ips",
            "preserve_other_settings": True,
            "direct_db_edit": False,
        },
    }


class ReadinessTests(unittest.TestCase):
    def test_clean_synthetic_only(self):
        self.assertEqual(m.evaluate(sample()), "PASS_SOURCE_ONLY")

    def assert_block(self, group, field, value, code):
        e = sample()
        e[group][field] = value
        self.assertEqual(m.evaluate(e), code)

    def test_malformed_and_extra_fields(self):
        for e in (None, {}, [], {"schema_version": 1}, {"schema_version": True}):
            with self.subTest(e=e):
                self.assertEqual(m.evaluate(e), "STOP_SCHEMA")
        e = sample()
        e["raw_ip"] = "198.51.100.3"
        self.assertEqual(m.evaluate(e), "STOP_SCHEMA")

    def test_service_identity(self):
        for field, value in (("version", "v2.6.0"), ("state", "failed"),
                             ("listener", "0.0.0.0:9194"), ("listener", "127.0.0.1:9193"),
                             ("vhost", "ausmalwiese.de")):
            with self.subTest(field=field, value=value):
                self.assert_block("service", field, value, "STOP_SERVICE_METADATA")

    def test_collect_unknown_without_authorization(self):
        self.assert_block("service", "collect_provenance", "unknown", "STOP_COLLECT_PROOF")
        for value in (None, True, "130", 0, 1, 2, 128, 131, 134, 146, 256, 386):
            with self.subTest(value=value):
                self.assert_block("service", "collect", value, "STOP_COLLECT_FLAGS")

    def test_service_rejects_raw_config(self):
        e = sample()
        e["service"]["private_database_path"] = "forbidden"
        self.assertEqual(m.evaluate(e), "STOP_SERVICE_METADATA")

    def test_edge_metadata_unknown(self):
        self.assert_block("edge", "remote_tunnel", "unknown", "STOP_EDGE_METADATA")
        e = sample()
        e["edge"]["route_config"] = "raw"
        self.assertEqual(m.evaluate(e), "STOP_EDGE_METADATA")

    def test_route_missing_ambiguous_or_live(self):
        for host in m.HOSTS:
            for value in ("unknown", "missing_fallback", "wrong_order",
                          "exact_present", "wildcard_conflict"):
                e = sample()
                e["edge"]["routes"][host] = value
                with self.subTest(host=host, value=value):
                    self.assertEqual(m.evaluate(e), "STOP_ROUTE")
        e = sample()
        del e["edge"]["routes"][m.HOSTS[0]]
        self.assertEqual(m.evaluate(e), "STOP_ROUTE")

    def test_worker_and_custom_domain_interception(self):
        self.assert_block("edge", "worker_routes", "matching_worker", "STOP_WORKER")
        self.assert_block("edge", "worker_custom_domains", "matching_custom_domain", "STOP_WORKER")

    def test_untrusted_forwarding_and_remote_addr(self):
        for field, value in (
            ("tunnel_peer", "unverified"),
            ("host_header", "unverified"),
            ("forwarded_headers", "client_header_forwarded_unchanged"),
            ("remote_addr", "proxy_loopback_address"),
            ("remote_addr", "unverified"),
            ("spoof_test", "unknown"),
            ("spoof_test", "spoof_accepted"),
            ("forwarded_proto", "http"),
        ):
            with self.subTest(field=field):
                self.assert_block("ip", field, value, "STOP_IP_TRUST")

    def test_no_raw_headers_or_address_in_summary(self):
        e = sample()
        e["ip"]["CF-Connecting-IP"] = "198.51.100.10"
        self.assertEqual(m.evaluate(e), "STOP_IP_TRUST")

    def test_legal_and_owner_privacy_gate(self):
        self.assert_block("privacy", "notice", "draft", "STOP_PRIVACY")
        self.assert_block("privacy", "approved_collect", 130 | 16, "STOP_PRIVACY")
        self.assert_block("privacy", "approved_collect", True, "STOP_PRIVACY")
        self.assert_block("privacy", "frontend", "enabled", "STOP_PRIVACY")

    def test_does_not_mutate_evidence(self):
        e = sample()
        before = deepcopy(e)
        self.assertEqual(m.evaluate(e), "PASS_SOURCE_ONLY")
        self.assertEqual(e, before)

    def test_stable_codes_never_reflect_input(self):
        e = sample()
        e["service"]["state"] = "UNTRUSTED_VISITOR_DATA"
        self.assertEqual(m.evaluate(e), "STOP_SERVICE_METADATA")
        self.assertNotIn("UNTRUSTED_VISITOR_DATA", m.evaluate(e))


class HouseholdExclusionTests(unittest.TestCase):
    def test_stable_shared_ipv4_is_native_candidate(self):
        self.assertEqual(m.evaluate_household_exclusion(household()),
                         "PASS_HOUSEHOLD_EXCLUSION_SOURCE_ONLY")

    def test_stable_exact_ipv6_set_is_native_candidate(self):
        e = household()
        e["egress"] = {"ipv4": "absent", "ipv6": "stable_exact_set"}
        self.assertEqual(m.evaluate_household_exclusion(e),
                         "PASS_HOUSEHOLD_EXCLUSION_SOURCE_ONLY")

    def test_dynamic_addresses_fail_closed(self):
        for field, value, code in (
            ("ipv4", "dynamic_or_unknown", "STOP_DYNAMIC_IPV4"),
            ("ipv6", "rotating_or_unknown", "STOP_DYNAMIC_IPV6"),
        ):
            e = household()
            e["egress"][field] = value
            with self.subTest(field=field):
                self.assertEqual(m.evaluate_household_exclusion(e), code)

    def test_requires_reused_client_ip_trust_contract(self):
        for field, value in (
            ("tunnel_peer", "unverified"),
            ("forwarded_headers", "client_header_forwarded_unchanged"),
            ("spoof_test", "spoof_accepted"),
        ):
            e = household()
            e["ip"][field] = value
            with self.subTest(field=field):
                self.assertEqual(m.evaluate_household_exclusion(e), "STOP_IP_TRUST")

    def test_mutation_contract_is_ignore_ips_only(self):
        for field, value in (
            ("target", "database"),
            ("field", "collect"),
            ("preserve_other_settings", False),
            ("direct_db_edit", True),
        ):
            e = household()
            e["mutation"][field] = value
            with self.subTest(field=field):
                self.assertEqual(m.evaluate_household_exclusion(e),
                                 "STOP_MUTATION_CONTRACT")

    def test_exact_ip_validation_rejects_prefixes_and_noncanonical_forms(self):
        self.assertTrue(m.exact_ignore_ips_valid([
            "8.8.8.8", "2606:4700:4700::1111"]))
        for values in (
            ["8.8.8.0/24"],
            ["2606:4700:4700::/48"],
            ["2606:4700:4700:0:0:0:0:1111"],
            ["fe80::1%eth0"],
            ["127.0.0.1"],
            ["8.8.8.8", "8.8.8.8"],
            [],
            "8.8.8.8",
        ):
            with self.subTest(values=values):
                self.assertFalse(m.exact_ignore_ips_valid(values))

    def test_exact_matching_is_coverage_not_prefix_matching(self):
        self.assertTrue(m.exact_ignore_ips_cover(
            ["8.8.8.8"],
            ["8.8.8.8", "2606:4700:4700::1111"],
        ))
        self.assertFalse(m.exact_ignore_ips_cover(
            ["8.8.4.4"],
            ["8.8.8.8", "2606:4700:4700::1111"],
        ))

    def test_household_result_never_contains_address_or_secret(self):
        e = household()
        e["secret"] = "CANARY_SECRET"
        self.assertEqual(m.evaluate_household_exclusion(e), "STOP_HOUSEHOLD_SCHEMA")
        out = m.evaluate_household_exclusion(household())
        self.assertNotIn("8.8.8.8", out)
        self.assertNotIn("CANARY_SECRET", out)

    def test_no_egress_or_unknown_shape_stops(self):
        e = household()
        e["egress"] = {"ipv4": "absent", "ipv6": "absent"}
        self.assertEqual(m.evaluate_household_exclusion(e), "STOP_NO_EGRESS")
        e = household()
        e["egress"]["ipv6"] = "whole_prefix"
        self.assertEqual(m.evaluate_household_exclusion(e), "STOP_EGRESS")


if __name__ == "__main__":
    unittest.main()
