from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "ops/lib/deploy_executor"
sys.path.insert(0, str(LIB))
import control_phase5_observation_delivery as delivery
import control_phase5_signer_handoff as handoff_source

SOURCE_SHA = handoff_source.REVIEWED_CONTROL_SOURCE_SHA
DEPLOYMENT = "11111111-1111-4111-8111-111111111111"
VERSION = "22222222-2222-4222-8222-222222222222"
KEY_ID = "synthetic-rpi5-key-v1"
PROJECT_SHA = "5" * 40
NOW = "2026-09-13T12:04:59.000Z"
DELIVERY_ID = "123e4567-e89b-42d3-a456-426614174000"
SECRET_TEXT = "TOP_SECRET_PRIVATE_KEY_MATERIAL"


def handoff():
    return {
        "schema_version": 1,
        "contract": "PHASE5_RPI5_SIGNER_HANDOFF_V1",
        "source_repository": "rozkalnsandris/rozkalns-control-center",
        "control_source_sha": SOURCE_SHA,
        "worker": "rozkalns-control",
        "expected_worker": {
            "deployment_id": DEPLOYMENT,
            "version_id": VERSION,
            "traffic_percent": 100,
            "ingest_state": "PRESENT_TRUE",
        },
        "key_id": KEY_ID,
        "observation_contract_version": "control-phase5-rpi5-observation-v1",
        "generated_at": "2026-09-13T12:00:00.000Z",
        "receiver": {
            "repository": "rozkalnsandris/RPi5_main",
            "lane": "RPI5_SIGNER_RUNTIME",
            "authority_owner": "RPi5_main",
        },
        "authority": {
            "evidence_only": True,
            "grants_live_authority": False,
            "grants_cross_repo_write": False,
            "grants_rpi5_runtime_mutation": False,
        },
    }


def expected():
    return {
        "control_source_sha": SOURCE_SHA,
        "deployment_id": DEPLOYMENT,
        "version_id": VERSION,
        "key_id": KEY_ID,
        "project_id": "rpi5-main",
        "repository": "rozkalnsandris/RPi5_main",
        "main_sha": PROJECT_SHA,
    }


def visibility():
    return {
        "projectId": "rpi5-main",
        "repository": "rozkalnsandris/RPi5_main",
        "mainSha": PROJECT_SHA,
        "productionSha": "6" * 40,
        "deployImpact": "NO_DEPLOY",
        "runtime": "HEALTHY",
        "health": "PASS",
        "rollback": "AVAILABLE",
        "blockerCodes": [],
        "observedAt": "2026-09-13T12:04:00.000Z",
    }


class FakeResponse:
    def __init__(self, status=202, body=b'{"status":"AUTHENTICATED_AND_CLAIMED"}'):
        self.status = status
        self.body = body

    def read(self, limit):
        return self.body[:limit]


class FakeConnection:
    def __init__(self, *, status=202, body=b'{"status":"AUTHENTICATED_AND_CLAIMED"}', fail=False):
        self.status = status
        self.body = body
        self.fail = fail
        self.method = None
        self.path = None
        self.headers = []
        self.payload = None
        self.closed = False

    def putrequest(self, method, path, skip_accept_encoding=False):
        if self.fail:
            raise TimeoutError(SECRET_TEXT)
        self.method = method
        self.path = path
        self.skip_accept_encoding = skip_accept_encoding

    def putheader(self, name, value):
        self.headers.append((name, value))

    def endheaders(self, payload):
        self.payload = payload

    def getresponse(self):
        return FakeResponse(self.status, self.body)

    def close(self):
        self.closed = True


def fake_signer_loader(*, key_id, environ=None):
    if key_id != KEY_ID:
        raise AssertionError("unexpected key id")
    return lambda _signing_input: bytes(range(64))


class Phase5ObservationDeliveryTests(unittest.TestCase):
    def deliver(self, connection):
        return delivery.deliver_phase5_observation(
            handoff=handoff(), expected=expected(), visibility=visibility(),
            environ={"CREDENTIALS_DIRECTORY": SECRET_TEXT}, now_iso=NOW,
            delivery_id=DELIVERY_ID, signer_loader=fake_signer_loader,
            connection_factory=lambda: connection,
        )

    def test_validate_only_receipt_has_no_network_or_credential_access(self):
        receipt = delivery.public_preflight_receipt(
            handoff=handoff(), expected=expected(), visibility=visibility(), now_iso=NOW,
        )
        self.assertEqual(receipt["status"], "SOURCE_INPUT_READY")
        self.assertEqual(receipt["network_request"], "NO")
        self.assertEqual(receipt["credential_access"], "NO")
        self.assertEqual(receipt["live_authority"], "NOT_GRANTED")
        self.assertNotIn("signature", json.dumps(receipt).lower())

    def test_delivery_uses_fixed_post_path_exact_metadata_and_raw_payload(self):
        connection = FakeConnection()
        receipt = self.deliver(connection)
        self.assertEqual(connection.method, "POST")
        self.assertEqual(connection.path, "/api/rpi5/observation")
        self.assertTrue(connection.skip_accept_encoding)
        header_names = [name for name, _ in connection.headers]
        self.assertEqual(header_names, [
            "x-rpi5-observation-version",
            "x-rpi5-observation-delivery-id",
            "x-rpi5-observation-sent-at",
            "x-rpi5-observation-key-id",
            "x-rpi5-observation-signature",
            "Content-Length",
        ])
        self.assertEqual(int(dict(connection.headers)["Content-Length"]), len(connection.payload))
        self.assertEqual(json.loads(connection.payload), visibility())
        self.assertTrue(connection.closed)
        self.assertEqual(receipt["status"], "DELIVERED")
        self.assertEqual(receipt["http_status"], 202)
        self.assertNotIn("signature", json.dumps(receipt).lower())
        self.assertNotIn(SECRET_TEXT, json.dumps(receipt))

    def test_connection_factory_failure_is_sanitized(self):
        def failing_factory():
            raise OSError("synthetic connection setup failure")

        with self.assertRaises(delivery.Phase5ObservationDeliveryError) as caught:
            delivery.deliver_phase5_observation(
                handoff=handoff(),
                expected=expected(),
                visibility=visibility(),
                now_iso=NOW,
                delivery_id=DELIVERY_ID,
                signer_loader=fake_signer_loader,
                connection_factory=failing_factory,
            )
        self.assertEqual(caught.exception.code, "CONTROL_TRANSPORT_FAILED")
        self.assertNotIn("synthetic", str(caught.exception))

    def test_http_error_redirect_network_and_malformed_success_fail_closed(self):
        cases = [
            (FakeConnection(status=400), "CONTROL_HTTP_NOT_ACCEPTED", 400),
            (FakeConnection(status=401), "CONTROL_HTTP_NOT_ACCEPTED", 401),
            (FakeConnection(status=409), "CONTROL_HTTP_NOT_ACCEPTED", 409),
            (FakeConnection(status=503), "CONTROL_HTTP_NOT_ACCEPTED", 503),
            (FakeConnection(status=302), "CONTROL_HTTP_NOT_ACCEPTED", 302),
            (FakeConnection(status=202, body=b'{"status":"OTHER"}'), "CONTROL_RESPONSE_INVALID", None),
            (FakeConnection(status=202, body=b'{"status":"AUTHENTICATED_AND_CLAIMED","status":"OTHER"}'), "CONTROL_RESPONSE_INVALID", None),
            (FakeConnection(status=202, body=b'not-json'), "CONTROL_RESPONSE_INVALID", None),
            (FakeConnection(fail=True), "CONTROL_TRANSPORT_FAILED", None),
        ]
        for connection, code, status in cases:
            with self.subTest(code=code, status=status):
                with self.assertRaises(delivery.Phase5ObservationDeliveryError) as caught:
                    self.deliver(connection)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.http_status, status)
                self.assertNotIn(SECRET_TEXT, str(caught.exception))

    def test_unreviewed_control_or_project_identity_drift_fails_before_signer(self):
        bad_expected = expected(); bad_expected["control_source_sha"] = "a" * 40
        with self.assertRaises(handoff_source.Phase5SignerHandoffError):
            delivery.validate_phase5_runtime_request(
                handoff=handoff(), expected=bad_expected, visibility=visibility(), now_iso=NOW,
            )
        bad_project = expected(); bad_project["repository"] = "rozkalnsandris/other"
        with self.assertRaises(delivery.Phase5ObservationDeliveryError) as caught:
            delivery.validate_phase5_runtime_request(
                handoff=handoff(), expected=bad_project, visibility=visibility(), now_iso=NOW,
            )
        self.assertEqual(caught.exception.code, "INVALID_PROJECT_IDENTITY")

        malformed = expected(); malformed["project_id"] = []
        with self.assertRaises(delivery.Phase5ObservationDeliveryError) as caught:
            delivery.validate_phase5_runtime_request(
                handoff=handoff(), expected=malformed, visibility=visibility(), now_iso=NOW,
            )
        self.assertEqual(caught.exception.code, "INVALID_PROJECT_IDENTITY")

    def test_endpoint_and_network_authority_are_fixed_in_source(self):
        source = (LIB / "control_phase5_observation_delivery.py").read_text()
        self.assertIn('CONTROL_HOST = "control.rozkalns.net"', source)
        self.assertIn('CONTROL_PATH = "/api/rpi5/observation"', source)
        self.assertNotIn("url=", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)

    def test_validate_only_cli_rejects_duplicate_json_keys(self):
        child = subprocess.run(
            [str(ROOT / "ops/bin/rpi5-control-phase5-observation-deliver"), "--validate-only"],
            input='{ "handoff": {}, "handoff": {}, "expected": {}, "visibility": {} }',
            text=True, capture_output=True, timeout=5,
        )
        self.assertEqual(child.returncode, 2)
        self.assertEqual(json.loads(child.stdout)["code"], "INPUT_INVALID")

    def test_validate_only_cli_requires_strict_envelope_and_never_needs_credential(self):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        request_handoff = handoff(); request_handoff["generated_at"] = now
        request_visibility = visibility(); request_visibility["observedAt"] = now
        envelope = {"handoff": request_handoff, "expected": expected(), "visibility": request_visibility}
        env = dict(os.environ); env.pop("CREDENTIALS_DIRECTORY", None)
        child = subprocess.run(
            [str(ROOT / "ops/bin/rpi5-control-phase5-observation-deliver"), "--validate-only"],
            input=json.dumps(envelope), text=True, capture_output=True, env=env, timeout=5,
        )
        self.assertEqual(child.returncode, 0, child.stderr)
        receipt = json.loads(child.stdout)
        self.assertEqual(receipt["status"], "SOURCE_INPUT_READY")
        self.assertEqual(receipt["network_request"], "NO")
        self.assertEqual(receipt["credential_access"], "NO")
        self.assertNotIn("signature", child.stdout.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
