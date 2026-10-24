#!/usr/bin/env python3
"""Offline, no-network #1211 Traffic zone-binding protocol regressions."""
from __future__ import annotations
import copy
import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ausmalwiese_stats_worker_exact_deploy as core
import ausmalwiese_stats_zone_binding_v1 as zone

SOURCE = b"synthetic-offline-traffic-worker"
CODE_SHA = hashlib.sha256(SOURCE).hexdigest()
ZONE_ID = "a" * 32  # synthetic ID, not an actual Cloudflare zone
ZONE_HASH = hashlib.sha256(ZONE_ID.encode("ascii")).hexdigest()
OLD = "11111111-1111-1111-1111-111111111111"
NEW = "22222222-2222-2222-2222-222222222222"
DEPLOY_OLD = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DEPLOY_NEW = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def bindings():
    return {
        "DB": {"kind": "d1", "fingerprint": "1" * 64},
        "RATE_LIMITER": {"kind": "ratelimit", "fingerprint": "2" * 64},
        "PUBLIC_ORIGIN": {"kind": "plain_text", "fingerprint": "3" * 64},
        "CF_ANALYTICS_HOST": {"kind": "plain_text", "fingerprint": "4" * 64},
        "CF_ZONE_TAG": {"kind": "plain_text", "fingerprint": "5" * 64},
        "VISITOR_HMAC_KEY": {"kind": "secret_text", "fingerprint": None},
        "CF_ANALYTICS_API_TOKEN": {"kind": "secret_text", "fingerprint": None},
    }


def fixture():
    current = {
        "schema": "ausmalwiese.stats-worker-protected-inventory.v1",
        "account_sha256": core.ACCOUNT_SHA256,
        "worker": core.WORKER,
        "environment": "production",
        "active_version": OLD,
        "latest_uploaded_version": OLD,
        "deployment_id": DEPLOY_OLD,
        "traffic_percent": 100,
        "routes": copy.deepcopy(core.ROUTES),
        "active_bindings": bindings(),
        "latest_bindings": bindings(),
        "active_configuration": {
            "compatibility_date": "2026-10-06",
            "compatibility_flags": [],
            "settings_sha256": "6" * 64,
        },
        "latest_configuration": {
            "compatibility_date": "2026-10-06",
            "compatibility_flags": [],
            "settings_sha256": "6" * 64,
        },
        "active_code_sha256": CODE_SHA,
        "latest_code_sha256": CODE_SHA,
    }
    uploaded = copy.deepcopy(current)
    uploaded["latest_uploaded_version"] = NEW
    uploaded["latest_bindings"]["CF_ZONE_TAG"]["fingerprint"] = ZONE_HASH
    deployed = copy.deepcopy(uploaded)
    deployed["active_version"] = NEW
    deployed["deployment_id"] = DEPLOY_NEW
    deployed["active_bindings"]["CF_ZONE_TAG"]["fingerprint"] = ZONE_HASH
    return current, uploaded, deployed


class TrustedFake:
    def __init__(self, states, *, fail_upload=False, fail_deploy=False,
                 zone_ids=None):
        self.states = copy.deepcopy(states)
        self.zone_ids = iter(zone_ids or [ZONE_ID] * 4)
        self.fail_upload = fail_upload
        self.fail_deploy = fail_deploy
        self.read_count = self.uploads = self.deploys = 0

    def verified_zone_id(self, name):
        assert name == "ausmalwiese.de"
        return next(self.zone_ids)

    def read_snapshot(self, **kwargs):
        state = self.states[self.read_count]
        self.read_count += 1
        return copy.deepcopy(state)

    def upload_version_once(self, **kwargs):
        self.uploads += 1
        self.upload = kwargs
        if self.fail_upload:
            raise RuntimeError("synthetic provider error must not leak")
        return {"version_id": NEW}

    def deploy_version_once(self, **kwargs):
        self.deploys += 1
        self.deployment = kwargs
        if self.fail_deploy:
            raise RuntimeError("synthetic provider error must not leak")
        return {"deployment_id": DEPLOY_NEW}


class ZoneBindingTests(unittest.TestCase):
    def setUp(self):
        self.patch1 = mock.patch.object(core, "verify_source", return_value=None)
        self.patch2 = mock.patch.object(zone, "CODE_SHA", CODE_SHA)
        self.patch1.start()
        self.patch2.start()
        self.addCleanup(self.patch1.stop)
        self.addCleanup(self.patch2.stop)

    def approval(self, before):
        return {
            "worker": zone.WORKER, "source_blob": zone.SOURCE_BLOB,
            "config_blob": zone.CONFIG_BLOB, "candidate_sha256": CODE_SHA,
            "active_version": before["active_version"],
            "preflight_sha256": zone.digest(before),
            "allow_upload_once": True, "allow_deploy_once": True,
        }

    def test_success_single_binding_override_and_no_output_leak(self):
        before, uploaded, deployed = fixture()
        backend = TrustedFake([before, before, uploaded, deployed])
        result = zone.apply_once(core, backend, SOURCE, self.approval(before))
        self.assertEqual(result["provider_writes"], 2)
        self.assertEqual((backend.uploads, backend.deploys), (1, 1))
        self.assertEqual(backend.upload["bindings_inherit"], "strict")
        self.assertEqual(backend.upload["module_bytes"], SOURCE)
        changes = backend.upload["metadata"]["bindings"]
        self.assertEqual(len(changes), 7)
        self.assertEqual([b for b in changes if b["type"] != "inherit"],
                         [{"name": "CF_ZONE_TAG", "type": "plain_text", "text": ZONE_ID}])
        self.assertEqual(len([b for b in changes if b["type"] == "inherit"]), 6)
        self.assertEqual(backend.deployment["payload"],
                         {"strategy": "percentage",
                          "versions": [{"version_id": NEW, "percentage": 100}]})
        self.assertNotIn(ZONE_ID, str(result))
        self.assertNotIn("secret", str(result).lower())

    def test_readonly_preflight_sanitized_no_provider_write(self):
        before, _, _ = fixture()
        backend = TrustedFake([before, before])
        result = zone.preflight(core, backend, SOURCE)
        self.assertTrue(result["zone_mismatch"])
        self.assertEqual((backend.uploads, backend.deploys), (0, 0))
        self.assertNotIn(ZONE_ID, str(result))

    def test_wrong_zone_or_zone_changes_block_before_write(self):
        before, _, _ = fixture()
        for zones in [["0" * 32, ZONE_ID], ["invalid", "invalid"]]:
            with self.subTest(zones=zones):
                backend = TrustedFake([before, before], zone_ids=zones)
                with self.assertRaises(zone.Blocked):
                    zone.apply_once(core, backend, SOURCE, self.approval(before))
                self.assertEqual(backend.uploads, 0)

    def test_existing_correct_zone_blocks_duplicate(self):
        before, _, _ = fixture()
        before["active_bindings"]["CF_ZONE_TAG"]["fingerprint"] = ZONE_HASH
        before["latest_bindings"]["CF_ZONE_TAG"]["fingerprint"] = ZONE_HASH
        backend = TrustedFake([before, before])
        with self.assertRaisesRegex(zone.Blocked, "ZONE_ALREADY_CORRECT"):
            zone.apply_once(core, backend, SOURCE, self.approval(before))
        self.assertEqual(backend.uploads, 0)

    def test_preflight_rejects_version_route_binding_or_code_drift(self):
        for field in ("version", "routes", "bindings", "code", "split"):
            before, _, _ = fixture()
            if field == "version":
                before["latest_uploaded_version"] = NEW
            elif field == "routes":
                before["routes"] = {}
            elif field == "bindings":
                del before["active_bindings"]["DB"]
            elif field == "code":
                before["active_code_sha256"] = "f" * 64
            else:
                before["traffic_percent"] = 50
            backend = TrustedFake([before, before])
            with self.subTest(field=field), self.assertRaises(zone.Blocked):
                zone.apply_once(core, backend, SOURCE, self.approval(before))
            self.assertEqual(backend.uploads, 0)

    def test_wrong_owner_snapshot_and_code_never_upload(self):
        before, _, _ = fixture()
        for field, bad in (("active_version", NEW), ("preflight_sha256", "f" * 64),
                           ("allow_deploy_once", False)):
            backend = TrustedFake([before, before])
            approval = self.approval(before)
            approval[field] = bad
            with self.subTest(field=field), self.assertRaises(zone.Blocked):
                zone.apply_once(core, backend, SOURCE, approval)
            self.assertEqual(backend.uploads, 0)
        backend = TrustedFake([before, before])
        with self.assertRaises(zone.Blocked):
            zone.apply_once(core, backend, b"tampered worker", self.approval(before))
        self.assertEqual(backend.uploads, 0)

    def test_upload_failure_no_retry_or_deploy(self):
        before, _, _ = fixture()
        backend = TrustedFake([before, before], fail_upload=True)
        with self.assertRaisesRegex(zone.Blocked, "UPLOAD_OUTCOME_UNKNOWN_STOP"):
            zone.apply_once(core, backend, SOURCE, self.approval(before))
        self.assertEqual((backend.uploads, backend.deploys), (1, 0))

    def test_post_upload_tamper_blocks_second_write(self):
        for item in ("binding", "routes", "code"):
            before, uploaded, _ = fixture()
            if item == "binding":
                uploaded["latest_bindings"]["CF_ANALYTICS_HOST"]["fingerprint"] = "e" * 64
            elif item == "routes":
                uploaded["routes"] = {}
            else:
                uploaded["latest_code_sha256"] = "e" * 64
            backend = TrustedFake([before, before, uploaded])
            with self.subTest(item=item), self.assertRaisesRegex(
                    zone.Blocked, "UPLOAD_POSTVERIFY_STOP"):
                zone.apply_once(core, backend, SOURCE, self.approval(before))
            self.assertEqual((backend.uploads, backend.deploys), (1, 0))

    def test_deploy_error_and_postverify_failure_are_terminal(self):
        before, uploaded, deployed = fixture()
        backend = TrustedFake([before, before, uploaded], fail_deploy=True)
        with self.assertRaisesRegex(zone.Blocked, "DEPLOY_OUTCOME_UNKNOWN_STOP"):
            zone.apply_once(core, backend, SOURCE, self.approval(before))
        self.assertEqual((backend.uploads, backend.deploys), (1, 1))
        deployed["active_bindings"]["PUBLIC_ORIGIN"]["fingerprint"] = "e" * 64
        backend = TrustedFake([before, before, uploaded, deployed])
        with self.assertRaisesRegex(zone.Blocked, "DEPLOY_POSTVERIFY_STOP"):
            zone.apply_once(core, backend, SOURCE, self.approval(before))
        self.assertEqual((backend.uploads, backend.deploys), (1, 1))

    def test_no_installer_provider_or_secret_facility(self):
        src = (ROOT / "scripts/ausmalwiese_stats_zone_binding_v1.py").read_text()
        for forbidden in ("urllib", "requests.", "subprocess", "socket.",
                          "getenv(", "environ[", "os.system", "argparse",
                          "from http", "def main("):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
