from __future__ import annotations

import base64
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISIBILITY_PATH = ROOT / "ops/lib/deploy_executor/control_phase5_production_visibility.py"
TRANSPORT_PATH = ROOT / "ops/lib/deploy_executor/control_phase5_observation_transport.py"
FIXTURE_PATH = ROOT / "tests/fixtures/control_phase5_production_visibility_cases.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


visibility = load_module("control_phase5_visibility_transport_test", VISIBILITY_PATH)
transport = load_module("control_phase5_observation_transport_test", TRANSPORT_PATH)
CASES = json.loads(FIXTURE_PATH.read_text())

VISIBILITY_PROVENANCE = {
    "consumer_repository": visibility.CONTROL_CONSUMER_REPOSITORY,
    "consumer_main_sha": visibility.CONTROL_CONSUMER_MAIN_SHA,
    "consumer_path": visibility.CONTROL_CONSUMER_PATH,
    "consumer_blob_sha": visibility.CONTROL_CONSUMER_BLOB_SHA,
    "contract_mode": "SOURCE_ONLY_NO_OBSERVATION_AUTHORITY",
}
TRANSPORT_PROVENANCE = {
    "control_repository": transport.CONTROL_TRANSPORT_REPOSITORY,
    "control_main_sha": transport.CONTROL_TRANSPORT_MAIN_SHA,
    "control_path": transport.CONTROL_TRANSPORT_PATH,
    "control_blob_sha": transport.CONTROL_TRANSPORT_BLOB_SHA,
    "contract_mode": transport.CONTROL_TRANSPORT_CONTRACT_MODE,
}
DELIVERY_ID = "123e4567-e89b-42d3-a456-426614174000"
SENT_AT = "2026-09-08T18:00:00.000Z"
KEY_ID = "rpi5-prod-2026-09"


def normalized_visibility():
    return visibility.normalize_production_visibility(
        CASES["valid"],
        expected_project_id="rpi5-main",
        expected_repository="rozkalnsandris/RPi5_main",
        expected_main_sha="504239fb8f98b6785c4aeb6d55681a6c4fdf1399",
        now_iso="2026-09-08T18:04:00.000Z",
        provenance=VISIBILITY_PROVENANCE,
    )


def transport_error(code: str):
    return lambda error: (
        isinstance(error, transport.ObservationTransportContractError)
        and error.code == code
    )


class ControlPhase5ObservationTransportTests(unittest.TestCase):
    def test_exact_control_signing_bytes_and_strict_envelope(self):
        normalized = normalized_visibility()
        captured = []
        signature = bytes(range(64))

        delivery = transport.build_signed_rpi5_observation_delivery(
            normalized,
            delivery_id=DELIVERY_ID,
            sent_at=SENT_AT,
            key_id=KEY_ID,
            signer=lambda signing_input: captured.append(signing_input) or signature,
            transport_provenance=TRANSPORT_PROVENANCE,
        )

        expected_payload = (
            '{"projectId":"rpi5-main","repository":"rozkalnsandris/RPi5_main",'
            '"mainSha":"504239fb8f98b6785c4aeb6d55681a6c4fdf1399",'
            '"productionSha":"2222222222222222222222222222222222222222",'
            '"deployImpact":"MANUAL_ROLLOUT_REQUIRED","runtime":"HEALTHY",'
            '"health":"PASS","rollback":"AVAILABLE",'
            '"blockerCodes":["SOURCE_ONLY_SAMPLE"],'
            '"observedAt":"2026-09-08T18:00:00.000Z"}'
        ).encode("utf-8")
        expected_prefix = (
            "rozkalns-control-center.phase5.rpi5-production-visibility.v1\n"
            "control-phase5-rpi5-observation-v1\n"
            f"{DELIVERY_ID}\n{SENT_AT}\n{KEY_ID}\n{len(expected_payload)}\n"
        ).encode("utf-8")

        self.assertEqual(delivery.payload, expected_payload)
        self.assertEqual(captured, [expected_prefix + expected_payload])
        self.assertEqual(
            list(delivery.metadata),
            ["version", "deliveryId", "sentAt", "keyId", "signature"],
        )
        self.assertEqual(delivery.metadata["version"], "control-phase5-rpi5-observation-v1")
        self.assertEqual(delivery.metadata["deliveryId"], DELIVERY_ID)
        self.assertEqual(delivery.metadata["sentAt"], SENT_AT)
        self.assertEqual(delivery.metadata["keyId"], KEY_ID)
        self.assertEqual(
            delivery.metadata["signature"],
            base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
        )
        self.assertNotIn("=", delivery.metadata["signature"])
        self.assertEqual(len(delivery.metadata["signature"]), 86)

    def test_control_transport_provenance_is_exact_and_current(self):
        self.assertEqual(
            transport.CONTROL_TRANSPORT_MAIN_SHA,
            "1da96b628054a32c79cc6e2f201f5a4a5036c12c",
        )
        self.assertEqual(
            transport.CONTROL_TRANSPORT_BLOB_SHA,
            "cae7864f9a1053b5141353ac192c9c2d512f955a",
        )
        bad = dict(TRANSPORT_PROVENANCE)
        bad["control_blob_sha"] = "0" * 40
        with self.assertRaises(transport.ObservationTransportContractError) as caught:
            transport.validate_transport_provenance(bad)
        self.assertEqual(caught.exception.code, "PROVENANCE_MISMATCH")

    def test_metadata_and_payload_bounds_fail_closed(self):
        payload = b"{}"
        invalid_cases = (
            {"delivery_id": "not-a-uuid", "sent_at": SENT_AT, "key_id": KEY_ID},
            {"delivery_id": DELIVERY_ID.upper(), "sent_at": SENT_AT, "key_id": KEY_ID},
            {"delivery_id": DELIVERY_ID, "sent_at": "2026-09-08T18:00:00Z", "key_id": KEY_ID},
            {"delivery_id": DELIVERY_ID, "sent_at": SENT_AT, "key_id": "bad key"},
        )
        for case in invalid_cases:
            with self.subTest(case=case):
                with self.assertRaises(transport.ObservationTransportContractError) as caught:
                    transport.build_rpi5_observation_signing_input(payload=payload, **case)
                self.assertEqual(caught.exception.code, "INVALID_INPUT")

        with self.assertRaises(transport.ObservationTransportContractError) as caught:
            transport.build_rpi5_observation_signing_input(
                delivery_id=DELIVERY_ID,
                sent_at=SENT_AT,
                key_id=KEY_ID,
                payload=b"x" * (transport.MAX_RPI5_OBSERVATION_PAYLOAD_BYTES + 1),
            )
        self.assertEqual(caught.exception.code, "PAYLOAD_TOO_LARGE")

    def test_signer_is_injected_and_only_exact_64_byte_result_is_accepted(self):
        normalized = normalized_visibility()

        for bad_result in (b"x" * 63, b"x" * 65, bytearray(b"x" * 64), "not-bytes"):
            with self.subTest(result_type=type(bad_result).__name__, length=len(bad_result)):
                with self.assertRaises(transport.ObservationTransportContractError) as caught:
                    transport.build_signed_rpi5_observation_delivery(
                        normalized,
                        delivery_id=DELIVERY_ID,
                        sent_at=SENT_AT,
                        key_id=KEY_ID,
                        signer=lambda _signing_input, result=bad_result: result,
                        transport_provenance=TRANSPORT_PROVENANCE,
                    )
                self.assertEqual(caught.exception.code, "INVALID_SIGNER_RESULT")

        def failing_signer(_signing_input):
            raise RuntimeError("synthetic signer failure")

        with self.assertRaises(transport.ObservationTransportContractError) as caught:
            transport.build_signed_rpi5_observation_delivery(
                normalized,
                delivery_id=DELIVERY_ID,
                sent_at=SENT_AT,
                key_id=KEY_ID,
                signer=failing_signer,
                transport_provenance=TRANSPORT_PROVENANCE,
            )
        self.assertEqual(caught.exception.code, "SIGNER_FAILURE")

    def test_source_contract_exposes_no_runtime_or_network_bridge(self):
        source = TRANSPORT_PATH.read_text().lower()
        for forbidden in (
            "subprocess",
            "os.system(",
            "requests",
            "urllib",
            "socket",
            "paramiko",
            "open(",
            "private_key",
            "private key",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
