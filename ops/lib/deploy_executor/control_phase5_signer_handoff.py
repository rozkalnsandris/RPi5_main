from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Mapping

SCHEMA_VERSION = 1
CONTRACT = "PHASE5_RPI5_SIGNER_HANDOFF_V1"
SOURCE_REPOSITORY = "rozkalnsandris/rozkalns-control-center"
REVIEWED_CONTROL_SOURCE_SHA = "42d2087fc42079cdcfb4a2a1ecbc255f0284080e"
REVIEWED_CONTROL_HANDOFF_PATH = "src/shared/phase5-rpi5-signer-handoff.ts"
REVIEWED_CONTROL_HANDOFF_BLOB_SHA = "a04c34949f7fbbed3fb8eafc37ddca1d5da55842"
WORKER = "rozkalns-control"
RECEIVER_REPOSITORY = "rozkalnsandris/RPi5_main"
RECEIVER_LANE = "RPI5_SIGNER_RUNTIME"
AUTHORITY_OWNER = "RPi5_main"
OBSERVATION_CONTRACT_VERSION = "control-phase5-rpi5-observation-v1"
MAX_AGE_SECONDS = 300

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class Phase5SignerHandoffError(RuntimeError):
    def __init__(self, code: str):
        super().__init__("phase5 signer handoff failed closed")
        self.code = code


def _fail(code: str) -> None:
    raise Phase5SignerHandoffError(code)


def _exact_record(value: Any, fields: tuple[str, ...], code: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(fields):
        _fail(code)
    return value


def _pattern(value: Any, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(code)
    return value


def _timestamp(value: Any) -> tuple[str, datetime]:
    if type(value) is not str or TIMESTAMP_PATTERN.fullmatch(value) is None:
        _fail("INVALID_TIMESTAMP")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail("INVALID_TIMESTAMP")
    canonical = parsed.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    if canonical != value:
        _fail("INVALID_TIMESTAMP")
    return value, parsed


def normalize_phase5_signer_handoff(manifest: Any, now_iso: str) -> dict[str, Any]:
    record = _exact_record(manifest, (
        "schema_version", "contract", "source_repository", "control_source_sha",
        "worker", "expected_worker", "key_id", "observation_contract_version",
        "generated_at", "receiver", "authority",
    ), "INVALID_HANDOFF_FIELDS")
    if record["schema_version"] != SCHEMA_VERSION or record["contract"] != CONTRACT:
        _fail("INVALID_HANDOFF_CONTRACT")
    if record["source_repository"] != SOURCE_REPOSITORY or record["worker"] != WORKER:
        _fail("INVALID_HANDOFF_SOURCE")
    control_source_sha = _pattern(record["control_source_sha"], SHA_PATTERN, "INVALID_CONTROL_SOURCE_SHA")

    worker = _exact_record(record["expected_worker"], (
        "deployment_id", "version_id", "traffic_percent", "ingest_state",
    ), "INVALID_WORKER_FIELDS")
    deployment_id = _pattern(worker["deployment_id"], UUID_PATTERN, "INVALID_DEPLOYMENT_ID")
    version_id = _pattern(worker["version_id"], UUID_PATTERN, "INVALID_VERSION_ID")
    if worker["traffic_percent"] != 100 or worker["ingest_state"] != "PRESENT_TRUE":
        _fail("INVALID_WORKER_STATE")

    key_id = _pattern(record["key_id"], KEY_ID_PATTERN, "INVALID_KEY_ID")
    if record["observation_contract_version"] != OBSERVATION_CONTRACT_VERSION:
        _fail("INVALID_OBSERVATION_CONTRACT")

    generated_at, generated = _timestamp(record["generated_at"])
    _, now = _timestamp(now_iso)
    age = (now - generated).total_seconds()
    if age < 0 or age > MAX_AGE_SECONDS:
        _fail("STALE_HANDOFF")

    receiver = _exact_record(record["receiver"], (
        "repository", "lane", "authority_owner",
    ), "INVALID_RECEIVER_FIELDS")
    if receiver != {
        "repository": RECEIVER_REPOSITORY,
        "lane": RECEIVER_LANE,
        "authority_owner": AUTHORITY_OWNER,
    }:
        _fail("INVALID_RECEIVER")

    authority = _exact_record(record["authority"], (
        "evidence_only", "grants_live_authority", "grants_cross_repo_write",
        "grants_rpi5_runtime_mutation",
    ), "INVALID_AUTHORITY_FIELDS")
    if authority != {
        "evidence_only": True,
        "grants_live_authority": False,
        "grants_cross_repo_write": False,
        "grants_rpi5_runtime_mutation": False,
    }:
        _fail("HANDOFF_GRANTS_AUTHORITY")

    return {
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "source_repository": SOURCE_REPOSITORY,
        "control_source_sha": control_source_sha,
        "worker": WORKER,
        "expected_worker": {
            "deployment_id": deployment_id,
            "version_id": version_id,
            "traffic_percent": 100,
            "ingest_state": "PRESENT_TRUE",
        },
        "key_id": key_id,
        "observation_contract_version": OBSERVATION_CONTRACT_VERSION,
        "generated_at": generated_at,
        "receiver": dict(receiver),
        "authority": dict(authority),
    }


def assert_phase5_signer_handoff_identity(manifest: Mapping[str, Any], expected: Any) -> None:
    identity = _exact_record(expected, (
        "control_source_sha", "deployment_id", "version_id", "key_id",
    ), "INVALID_EXPECTED_IDENTITY")
    control_source_sha = _pattern(identity["control_source_sha"], SHA_PATTERN, "INVALID_CONTROL_SOURCE_SHA")
    deployment_id = _pattern(identity["deployment_id"], UUID_PATTERN, "INVALID_DEPLOYMENT_ID")
    version_id = _pattern(identity["version_id"], UUID_PATTERN, "INVALID_VERSION_ID")
    key_id = _pattern(identity["key_id"], KEY_ID_PATTERN, "INVALID_KEY_ID")
    if control_source_sha != REVIEWED_CONTROL_SOURCE_SHA:
        _fail("UNREVIEWED_CONTROL_SOURCE")
    if (
        manifest.get("control_source_sha") != control_source_sha
        or manifest.get("expected_worker", {}).get("deployment_id") != deployment_id
        or manifest.get("expected_worker", {}).get("version_id") != version_id
        or manifest.get("key_id") != key_id
    ):
        _fail("HANDOFF_IDENTITY_MISMATCH")
