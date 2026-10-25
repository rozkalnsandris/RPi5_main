#!/usr/bin/env python3
"""Offline tests for the source-only #1211 trusted zone-binding adapter."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ausmalwiese_stats_zone_binding_adapter_v1 as adapter
import ausmalwiese_stats_zone_binding_v1 as protocol

ZONE_ID = "a" * 32
OTHER_ID = "b" * 32


class FakeTransport:
    def __init__(self, zone_result=None):
        self.zones = {
            "ausmalwiese.de": ZONE_ID,
            "rozkalns.net": OTHER_ID,
        }
        self.allow_deploy_existing = False
        self.candidate_code_sha256 = adapter.CODE_SHA
        self.uploads = 0
        self.deploys = 0
        self.get_calls = []
        self.zone_result = (
            [{"id": ZONE_ID, "name": "ausmalwiese.de", "status": "active"}]
            if zone_result is None
            else zone_result
        )

    def _get(self, path):
        self.get_calls.append(path)
        return self.zone_result

    def read_snapshot(self, **kwargs):
        return {"snapshot": True, "kwargs": kwargs}

    def upload_version_once(self, **kwargs):
        self.uploads += 1
        return {"version_id": "22222222-2222-2222-2222-222222222222"}

    def deploy_version_once(self, **kwargs):
        self.deploys += 1
        return {"deployment_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}


class AdapterTests(unittest.TestCase):
    def test_exact_active_zone_lookup_and_allowlist(self):
        transport = FakeTransport()
        trusted = adapter.TrustedZoneBindingAdapter(transport)
        self.assertEqual(trusted.verified_zone_id("ausmalwiese.de"), ZONE_ID)
        self.assertEqual(
            transport.get_calls,
            [
                "/client/v4/zones?name=ausmalwiese.de&status=active"
                "&match=all&page=1&per_page=2"
            ],
        )
        self.assertNotIn(ZONE_ID, repr({"status": "PASS"}))

    def test_absent_multiple_inactive_wrong_or_allowlist_mismatch_stop(self):
        bad_results = [
            [],
            [
                {"id": ZONE_ID, "name": "ausmalwiese.de", "status": "active"},
                {"id": "c" * 32, "name": "ausmalwiese.de", "status": "active"},
            ],
            [{"id": ZONE_ID, "name": "ausmalwiese.de", "status": "pending"}],
            [{"id": ZONE_ID, "name": "wrong.example", "status": "active"}],
            [{"id": "c" * 32, "name": "ausmalwiese.de", "status": "active"}],
        ]
        for result in bad_results:
            with self.subTest(result=result):
                trusted = adapter.TrustedZoneBindingAdapter(FakeTransport(result))
                with self.assertRaises(adapter.Stop):
                    trusted.verified_zone_id("ausmalwiese.de")

    def test_only_fixed_target_zone_is_accepted(self):
        trusted = adapter.TrustedZoneBindingAdapter(FakeTransport())
        with self.assertRaisesRegex(adapter.Stop, "ZONE_NAME_NOT_ALLOWED"):
            trusted.verified_zone_id("rozkalns.net")

    def test_transport_mode_allowlist_and_fresh_budget_are_bound(self):
        cases = [
            ("allow_deploy_existing", True),
            ("candidate_code_sha256", "f" * 64),
            ("uploads", 1),
            ("deploys", 1),
        ]
        for field, value in cases:
            transport = FakeTransport()
            setattr(transport, field, value)
            with self.subTest(field=field), self.assertRaises(adapter.Stop):
                adapter.TrustedZoneBindingAdapter(transport)

        transport = FakeTransport()
        trusted = adapter.TrustedZoneBindingAdapter(transport)
        transport.zones["ausmalwiese.de"] = "c" * 32
        with self.assertRaisesRegex(adapter.Stop, "ZONE_ALLOWLIST_DRIFT"):
            trusted.read_snapshot()

    def test_write_budget_delegation_is_one_upload_then_one_deploy(self):
        transport = FakeTransport()
        trusted = adapter.TrustedZoneBindingAdapter(transport)
        trusted.upload_version_once(payload="synthetic")
        self.assertEqual((transport.uploads, transport.deploys), (1, 0))
        with self.assertRaisesRegex(adapter.Stop, "UPLOAD_BUDGET_NOT_FRESH"):
            trusted.upload_version_once(payload="synthetic")
        trusted.deploy_version_once(payload={"synthetic": True})
        self.assertEqual((transport.uploads, transport.deploys), (1, 1))
        with self.assertRaisesRegex(adapter.Stop, "DEPLOY_BUDGET_NOT_READY"):
            trusted.deploy_version_once(payload={"synthetic": True})

    def test_confirmation_gate_precedes_protocol_execution(self):
        transport = FakeTransport()
        with mock.patch.object(protocol, "preflight") as pre:
            with self.assertRaisesRegex(adapter.Stop, "PREFLIGHT_CONFIRMATION_INVALID"):
                adapter.preflight(protocol, object(), transport, b"x", "WRONG")
            pre.assert_not_called()
            pre.return_value = {"status": "PASS", "provider_writes": 0}
            result = adapter.preflight(
                protocol,
                object(),
                transport,
                b"x",
                adapter.PRE_CONFIRM,
            )
            self.assertEqual(result["provider_writes"], 0)
            pre.assert_called_once()

        transport = FakeTransport()
        with mock.patch.object(protocol, "apply_once") as apply:
            with self.assertRaisesRegex(adapter.Stop, "APPLY_CONFIRMATION_INVALID"):
                adapter.apply_once(
                    protocol, object(), transport, b"x", {}, "WRONG"
                )
            apply.assert_not_called()
            apply.return_value = {"status": "PASS", "provider_writes": 2}
            result = adapter.apply_once(
                protocol,
                object(),
                transport,
                b"x",
                {},
                adapter.APPLY_CONFIRM,
            )
            self.assertEqual(result["provider_writes"], 2)
            apply.assert_called_once()

    def test_source_has_no_cli_credential_reader_or_network_transport(self):
        source = (
            ROOT / "scripts/ausmalwiese_stats_zone_binding_adapter_v1.py"
        ).read_text()
        for forbidden in (
            "argparse",
            "http.client",
            "ssl.",
            "requests.",
            "credential(",
            "getenv(",
            "environ[",
            "def main(",
        ):
            self.assertNotIn(forbidden, source)

    def test_machine_contract_declares_uninstalled_non_live_adapter(self):
        contract = json.loads(
            (
                ROOT
                / "ops/contracts/ausmalwiese-stats-zone-binding-v1.json"
            ).read_text()
        )
        self.assertEqual(contract["issue"], 1211)
        self.assertEqual(
            contract["trusted_adapter_source"],
            "scripts/ausmalwiese_stats_zone_binding_adapter_v1.py",
        )
        self.assertEqual(
            contract["trusted_adapter_test"],
            "tests/test-ausmalwiese-stats-zone-binding-adapter-v1.py",
        )
        trusted = contract["trusted_adapter"]
        self.assertFalse(trusted["has_cli"])
        self.assertFalse(trusted["reads_credentials"])
        self.assertFalse(trusted["creates_transport"])
        self.assertFalse(trusted["installed"])
        self.assertFalse(contract["source_merge_authorizes_live"])
        self.assertFalse(contract["source_merge_authorizes_install"])


if __name__ == "__main__":
    unittest.main()
