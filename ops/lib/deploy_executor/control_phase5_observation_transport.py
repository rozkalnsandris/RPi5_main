from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

CONTROL_TRANSPORT_REPOSITORY = "rozkalnsandris/rozkalns-control-center"
CONTROL_TRANSPORT_MAIN_SHA = "1da96b628054a32c79cc6e2f201f5a4a5036c12c"
CONTROL_TRANSPORT_PATH = "src/shared/rpi5-observation-transport.ts"
CONTROL_TRANSPORT_BLOB_SHA = "cae7864f9a1053b5141353ac192c9c2d512f955a"
CONTROL_TRANSPORT_CONTRACT_MODE = "SOURCE_ONLY_NO_RUNTIME_TRANSPORT_AUTHORITY"

RPI5_OBSERVATION_TRANSPORT_VERSION = "control-phase5-rpi5-observation-v1"
RPI5_OBSERVATION_SIGNING_DOMAIN = (
    "rozkalns-control-center.phase5.rpi5-production-visibility.v1"
)
MAX_RPI5_OBSERVATION_PAYLOAD_BYTES = 16 * 1024
SANITIZED_PRODUCTION_VISIBILITY_FIELDS = (
    "projectId",
    "repository",
    "mainSha",
    "productionSha",
    "deployImpact",
    "runtime",
    "health",
    "rollback",
    "blockerCodes",
    "observedAt",
)

DELIVERY_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
CANONICAL_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
)

Signer = Callable[[bytes], bytes]


class ObservationTransportContractError(RuntimeError):
    def __init__(self, code: str):
        super().__init__("observation transport source contract failed closed")
        self.code = code


@dataclass(frozen=True)
class SignedRpi5ObservationDelivery:
    metadata: dict[str, str]
    payload: bytes


def _fail(code: str) -> None:
    raise ObservationTransportContractError(code)


def _require_canonical_timestamp(value: Any) -> str:
    if type(value) is not str or CANONICAL_TIMESTAMP_PATTERN.fullmatch(value) is None:
        _fail("INVALID_INPUT")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _fail("INVALID_INPUT")
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" != value:
        _fail("INVALID_INPUT")
    return value


def validate_transport_provenance(provenance: Mapping[str, Any]) -> None:
    expected = {
        "control_repository": CONTROL_TRANSPORT_REPOSITORY,
        "control_main_sha": CONTROL_TRANSPORT_MAIN_SHA,
        "control_path": CONTROL_TRANSPORT_PATH,
        "control_blob_sha": CONTROL_TRANSPORT_BLOB_SHA,
        "contract_mode": CONTROL_TRANSPORT_CONTRACT_MODE,
    }
    if type(provenance) is not dict or provenance != expected:
        _fail("PROVENANCE_MISMATCH")


def serialize_sanitized_production_visibility_payload(
    normalized_visibility: Mapping[str, Any],
) -> bytes:
    if type(normalized_visibility) is not dict:
        _fail("INVALID_INPUT")
    keys = set(normalized_visibility)
    expected = set(SANITIZED_PRODUCTION_VISIBILITY_FIELDS)
    if keys != expected:
        _fail("UNEXPECTED_FIELD" if keys - expected else "INVALID_INPUT")

    ordered = {
        field: normalized_visibility[field]
        for field in SANITIZED_PRODUCTION_VISIBILITY_FIELDS
    }
    try:
        payload = json.dumps(
            ordered,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _fail("INVALID_INPUT")
    if not payload:
        _fail("INVALID_INPUT")
    if len(payload) > MAX_RPI5_OBSERVATION_PAYLOAD_BYTES:
        _fail("PAYLOAD_TOO_LARGE")
    return payload


def build_rpi5_observation_signing_input(
    *,
    delivery_id: str,
    sent_at: str,
    key_id: str,
    payload: bytes,
) -> bytes:
    if type(delivery_id) is not str or DELIVERY_ID_PATTERN.fullmatch(delivery_id) is None:
        _fail("INVALID_INPUT")
    normalized_sent_at = _require_canonical_timestamp(sent_at)
    if type(key_id) is not str or KEY_ID_PATTERN.fullmatch(key_id) is None:
        _fail("INVALID_INPUT")
    if type(payload) is not bytes or not payload:
        _fail("INVALID_INPUT")
    if len(payload) > MAX_RPI5_OBSERVATION_PAYLOAD_BYTES:
        _fail("PAYLOAD_TOO_LARGE")

    prefix = (
        f"{RPI5_OBSERVATION_SIGNING_DOMAIN}\n"
        f"{RPI5_OBSERVATION_TRANSPORT_VERSION}\n"
        f"{delivery_id}\n"
        f"{normalized_sent_at}\n"
        f"{key_id}\n"
        f"{len(payload)}\n"
    ).encode("utf-8")
    return prefix + payload


def build_signed_rpi5_observation_delivery(
    normalized_visibility: Mapping[str, Any],
    *,
    delivery_id: str,
    sent_at: str,
    key_id: str,
    signer: Signer,
    transport_provenance: Mapping[str, Any],
) -> SignedRpi5ObservationDelivery:
    validate_transport_provenance(transport_provenance)
    payload = serialize_sanitized_production_visibility_payload(normalized_visibility)
    signing_input = build_rpi5_observation_signing_input(
        delivery_id=delivery_id,
        sent_at=sent_at,
        key_id=key_id,
        payload=payload,
    )
    if not callable(signer):
        _fail("INVALID_INPUT")
    try:
        signature = signer(signing_input)
    except Exception:
        _fail("SIGNER_FAILURE")
    if type(signature) is not bytes or len(signature) != 64:
        _fail("INVALID_SIGNER_RESULT")

    signature_text = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    if len(signature_text) != 86:
        _fail("INVALID_SIGNER_RESULT")

    metadata = {
        "version": RPI5_OBSERVATION_TRANSPORT_VERSION,
        "deliveryId": delivery_id,
        "sentAt": sent_at,
        "keyId": key_id,
        "signature": signature_text,
    }
    return SignedRpi5ObservationDelivery(metadata=metadata, payload=payload)
