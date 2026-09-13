from __future__ import annotations

from datetime import datetime, timezone
import http.client
import json
import ssl
from typing import Any, Callable, Mapping
import uuid

import control_phase5_observation_signer as signer_source
import control_phase5_observation_transport as transport
import control_phase5_production_visibility as visibility_source
import control_phase5_signer_handoff as handoff_source

CONTROL_HOST = "control.rozkalns.net"
CONTROL_PORT = 443
CONTROL_PATH = "/api/rpi5/observation"
CONTROL_ENDPOINT = f"https://{CONTROL_HOST}{CONTROL_PATH}"
HTTP_TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 1024
REVIEWED_CONTROL_ROUTE_PATH = "src/worker/rpi5-observation-route.ts"
REVIEWED_CONTROL_ROUTE_BLOB_SHA = "d613c11fbbd32e61062ffd8ea6054d4e86ea6f16"

EXPECTED_FIELDS = (
    "control_source_sha",
    "deployment_id",
    "version_id",
    "key_id",
    "project_id",
    "repository",
    "main_sha",
)

METADATA_HEADERS = (
    ("version", "x-rpi5-observation-version"),
    ("deliveryId", "x-rpi5-observation-delivery-id"),
    ("sentAt", "x-rpi5-observation-sent-at"),
    ("keyId", "x-rpi5-observation-key-id"),
    ("signature", "x-rpi5-observation-signature"),
)


class Phase5ObservationDeliveryError(RuntimeError):
    def __init__(self, code: str, http_status: int | None = None):
        super().__init__("phase5 observation delivery failed closed")
        self.code = code
        self.http_status = http_status if type(http_status) is int else None


def _fail(code: str, http_status: int | None = None) -> None:
    raise Phase5ObservationDeliveryError(code, http_status)


def canonical_now() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _require_expected(value: Any) -> dict[str, str]:
    if type(value) is not dict or set(value) != set(EXPECTED_FIELDS):
        _fail("INVALID_EXPECTED_FIELDS")
    expected = dict(value)
    # Handoff validator owns the exact Control/deployment/version/key syntax.
    handoff_source.assert_phase5_signer_handoff_identity({
        "control_source_sha": expected["control_source_sha"],
        "expected_worker": {
            "deployment_id": expected["deployment_id"],
            "version_id": expected["version_id"],
        },
        "key_id": expected["key_id"],
    }, {
        "control_source_sha": expected["control_source_sha"],
        "deployment_id": expected["deployment_id"],
        "version_id": expected["version_id"],
        "key_id": expected["key_id"],
    })
    if type(expected["project_id"]) is not str or type(expected["repository"]) is not str:
        _fail("INVALID_PROJECT_IDENTITY")
    if visibility_source.PROJECTS.get(expected["project_id"]) != expected["repository"]:
        _fail("INVALID_PROJECT_IDENTITY")
    if type(expected["main_sha"]) is not str or visibility_source.SHA.fullmatch(expected["main_sha"]) is None:
        _fail("INVALID_PROJECT_MAIN_SHA")
    return expected


def _visibility_provenance() -> dict[str, str]:
    return {
        "consumer_repository": visibility_source.CONTROL_CONSUMER_REPOSITORY,
        "consumer_main_sha": visibility_source.CONTROL_CONSUMER_MAIN_SHA,
        "consumer_path": visibility_source.CONTROL_CONSUMER_PATH,
        "consumer_blob_sha": visibility_source.CONTROL_CONSUMER_BLOB_SHA,
        "contract_mode": "SOURCE_ONLY_NO_OBSERVATION_AUTHORITY",
    }


def _transport_provenance() -> dict[str, str]:
    return {
        "control_repository": transport.CONTROL_TRANSPORT_REPOSITORY,
        "control_main_sha": transport.CONTROL_TRANSPORT_MAIN_SHA,
        "control_path": transport.CONTROL_TRANSPORT_PATH,
        "control_blob_sha": transport.CONTROL_TRANSPORT_BLOB_SHA,
        "contract_mode": transport.CONTROL_TRANSPORT_CONTRACT_MODE,
    }


def validate_phase5_runtime_request(
    *, handoff: Any, expected: Any, visibility: Any, now_iso: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    normalized_handoff = handoff_source.normalize_phase5_signer_handoff(handoff, now_iso)
    normalized_expected = _require_expected(expected)
    handoff_source.assert_phase5_signer_handoff_identity(normalized_handoff, {
        "control_source_sha": normalized_expected["control_source_sha"],
        "deployment_id": normalized_expected["deployment_id"],
        "version_id": normalized_expected["version_id"],
        "key_id": normalized_expected["key_id"],
    })
    if visibility_source.CONTROL_CONSUMER_MAIN_SHA != handoff_source.REVIEWED_CONTROL_SOURCE_SHA:
        _fail("VISIBILITY_PROVENANCE_DRIFT")
    if transport.CONTROL_TRANSPORT_MAIN_SHA != handoff_source.REVIEWED_CONTROL_SOURCE_SHA:
        _fail("TRANSPORT_PROVENANCE_DRIFT")
    normalized_visibility = visibility_source.normalize_production_visibility(
        visibility,
        expected_project_id=normalized_expected["project_id"],
        expected_repository=normalized_expected["repository"],
        expected_main_sha=normalized_expected["main_sha"],
        now_iso=now_iso,
        provenance=_visibility_provenance(),
    )
    return normalized_handoff, normalized_expected, normalized_visibility


def public_preflight_receipt(
    *, handoff: Any, expected: Any, visibility: Any, now_iso: str,
) -> dict[str, Any]:
    normalized_handoff, normalized_expected, normalized_visibility = validate_phase5_runtime_request(
        handoff=handoff, expected=expected, visibility=visibility, now_iso=now_iso,
    )
    return {
        "schema_version": 1,
        "status": "SOURCE_INPUT_READY",
        "control_source_sha": normalized_handoff["control_source_sha"],
        "worker_deployment_id": normalized_handoff["expected_worker"]["deployment_id"],
        "worker_version_id": normalized_handoff["expected_worker"]["version_id"],
        "key_id": normalized_handoff["key_id"],
        "project_id": normalized_expected["project_id"],
        "repository": normalized_expected["repository"],
        "main_sha": normalized_expected["main_sha"],
        "production_sha": normalized_visibility["productionSha"],
        "network_request": "NO",
        "credential_access": "NO",
        "live_authority": "NOT_GRANTED",
    }


def _connection_factory():
    context = ssl.create_default_context()
    return http.client.HTTPSConnection(
        CONTROL_HOST, CONTROL_PORT, timeout=HTTP_TIMEOUT_SECONDS, context=context,
    )


def _post_delivery(delivery: transport.SignedRpi5ObservationDelivery, connection_factory: Callable[[], Any]) -> int:
    connection = None
    try:
        connection = connection_factory()
        connection.putrequest("POST", CONTROL_PATH, skip_accept_encoding=True)
        for field, header in METADATA_HEADERS:
            connection.putheader(header, delivery.metadata[field])
        connection.putheader("Content-Length", str(len(delivery.payload)))
        connection.endheaders(delivery.payload)
        response = connection.getresponse()
        status = response.status
        body = response.read(MAX_RESPONSE_BYTES + 1)
    except Exception:
        _fail("CONTROL_TRANSPORT_FAILED")
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
    if type(status) is not int:
        _fail("CONTROL_RESPONSE_INVALID")
    if status != 202:
        _fail("CONTROL_HTTP_NOT_ACCEPTED", status)
    if len(body) > MAX_RESPONSE_BYTES:
        _fail("CONTROL_RESPONSE_TOO_LARGE")
    try:
        parsed = json.loads(body.decode("utf-8"), object_pairs_hook=_strict_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("CONTROL_RESPONSE_INVALID")
    if parsed != {"status": "AUTHENTICATED_AND_CLAIMED"}:
        _fail("CONTROL_RESPONSE_INVALID")
    return status


def deliver_phase5_observation(
    *,
    handoff: Any,
    expected: Any,
    visibility: Any,
    environ: Mapping[str, str] | None = None,
    now_iso: str | None = None,
    delivery_id: str | None = None,
    signer_loader: Callable[..., Any] = signer_source.load_phase5_observation_signer,
    connection_factory: Callable[[], Any] = _connection_factory,
) -> dict[str, Any]:
    effective_now = canonical_now() if now_iso is None else now_iso
    normalized_handoff, normalized_expected, normalized_visibility = validate_phase5_runtime_request(
        handoff=handoff, expected=expected, visibility=visibility, now_iso=effective_now,
    )
    signer = signer_loader(key_id=normalized_handoff["key_id"], environ=environ)
    effective_delivery_id = str(uuid.uuid4()) if delivery_id is None else delivery_id
    delivery = transport.build_signed_rpi5_observation_delivery(
        normalized_visibility,
        delivery_id=effective_delivery_id,
        sent_at=effective_now,
        key_id=normalized_handoff["key_id"],
        signer=signer,
        transport_provenance=_transport_provenance(),
    )
    status = _post_delivery(delivery, connection_factory)
    return {
        "schema_version": 1,
        "status": "DELIVERED",
        "control_source_sha": normalized_handoff["control_source_sha"],
        "worker_deployment_id": normalized_handoff["expected_worker"]["deployment_id"],
        "worker_version_id": normalized_handoff["expected_worker"]["version_id"],
        "key_id": normalized_handoff["key_id"],
        "project_id": normalized_expected["project_id"],
        "repository": normalized_expected["repository"],
        "main_sha": normalized_expected["main_sha"],
        "production_sha": normalized_visibility["productionSha"],
        "delivery_id": delivery.metadata["deliveryId"],
        "sent_at": delivery.metadata["sentAt"],
        "http_status": status,
    }
