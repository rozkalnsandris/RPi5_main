from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

import control_phase5_production_visibility as visibility

CONTRACT = "CONTROL_PHASE5_PRODUCTION_VISIBILITY_PRODUCER_V1"
PROJECT_ID = "rpi5-main"
REPOSITORY = "rozkalnsandris/RPi5_main"
EVIDENCE_ROOT = Path("/var/lib/dashboard-rpi5/evidence")
EVIDENCE_FILENAME = "phase5-production-visibility.json"
EVIDENCE_SCHEMA = "rpi5.phase5-production-visibility-evidence.v1"
MAX_EVIDENCE_BYTES = 4096
TRANSACTION_ID = re.compile(r"^(\d{8}T\d{12}Z)-([0-9a-f]{12})$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SNAPSHOT_FIELDS = {
    "schema", "status", "repository", "transactionId", "productionSha",
    "completedAt", "observedAt",
}
PROVENANCE = {
    "consumer_repository": visibility.CONTROL_CONSUMER_REPOSITORY,
    "consumer_main_sha": visibility.CONTROL_CONSUMER_MAIN_SHA,
    "consumer_path": visibility.CONTROL_CONSUMER_PATH,
    "consumer_blob_sha": visibility.CONTROL_CONSUMER_BLOB_SHA,
    "contract_mode": "SOURCE_ONLY_NO_OBSERVATION_AUTHORITY",
}
BASE_BLOCKERS = (
    "RUNTIME_OBSERVATION_UNAVAILABLE",
    "HEALTH_OBSERVATION_UNAVAILABLE",
    "ROLLBACK_OBSERVATION_UNAVAILABLE",
)


class ProductionVisibilityProducerError(RuntimeError):
    def __init__(self, code: str):
        super().__init__("production visibility producer failed closed")
        self.code = code


def fail(code: str) -> None:
    raise ProductionVisibilityProducerError(code)


def canonical_now(now: datetime | None = None) -> str:
    value = now if now is not None else datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        fail("CLOCK_INVALID")
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _is_production_root(path: Path) -> bool:
    return path == EVIDENCE_ROOT


def _assert_safe_directory(path: Path, *, production: bool) -> None:
    try:
        info = os.lstat(path)
    except OSError:
        fail("BROKER_EVIDENCE_MISSING")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        fail("BROKER_EVIDENCE_UNSAFE")
    if production and (info.st_uid != 0 or (info.st_mode & 0o022) != 0):
        fail("BROKER_EVIDENCE_UNSAFE")


def _read_fixed(path: Path, *, production: bool, max_bytes: int) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        fail("BROKER_EVIDENCE_MISSING")
    except OSError:
        fail("BROKER_EVIDENCE_UNSAFE")
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            fail("BROKER_EVIDENCE_UNSAFE")
        if production and (info.st_uid != 0 or (info.st_mode & 0o022) != 0):
            fail("BROKER_EVIDENCE_UNSAFE")
        data = b""
        while True:
            remaining = max_bytes + 1 - len(data)
            if remaining <= 0:
                fail("BROKER_EVIDENCE_UNSAFE")
            chunk = os.read(fd, min(4096, remaining))
            if not chunk:
                break
            data += chunk
            if len(data) > max_bytes:
                fail("BROKER_EVIDENCE_UNSAFE")
    finally:
        os.close(fd)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        fail("BROKER_EVIDENCE_INVALID")


def _strict_json(raw: str) -> dict[str, Any]:
    def pairs(values):
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                fail("BROKER_EVIDENCE_INVALID")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (json.JSONDecodeError, TypeError, ValueError):
        fail("BROKER_EVIDENCE_INVALID")
    if type(value) is not dict:
        fail("BROKER_EVIDENCE_INVALID")
    return value


def _parse_canonical_time(value: Any) -> datetime:
    if type(value) is not str:
        fail("BROKER_EVIDENCE_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("BROKER_EVIDENCE_INVALID")
    offset = parsed.utcoffset() if parsed.tzinfo is not None else None
    if offset is None or offset.total_seconds() != 0:
        fail("BROKER_EVIDENCE_INVALID")
    canonical = parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if value != canonical:
        fail("BROKER_EVIDENCE_INVALID")
    return parsed


def read_production_observation(evidence_root: Path = EVIDENCE_ROOT) -> tuple[str, str]:
    production = _is_production_root(evidence_root)
    _assert_safe_directory(evidence_root, production=production)
    snapshot = _strict_json(
        _read_fixed(
            evidence_root / EVIDENCE_FILENAME,
            production=production,
            max_bytes=MAX_EVIDENCE_BYTES,
        )
    )
    if set(snapshot) != SNAPSHOT_FIELDS:
        fail("BROKER_EVIDENCE_INVALID")
    if snapshot.get("schema") != EVIDENCE_SCHEMA or snapshot.get("repository") != REPOSITORY:
        fail("BROKER_EVIDENCE_INVALID")
    observed = _parse_canonical_time(snapshot.get("observedAt"))
    status = snapshot.get("status")
    if status == "UNAVAILABLE":
        if any(snapshot.get(key) is not None for key in ("transactionId", "productionSha", "completedAt")):
            fail("BROKER_EVIDENCE_INVALID")
        fail("BROKER_EVIDENCE_UNAVAILABLE")
    if status != "AVAILABLE":
        fail("BROKER_EVIDENCE_INVALID")

    transaction_id = snapshot.get("transactionId")
    production_sha = snapshot.get("productionSha")
    match = TRANSACTION_ID.fullmatch(transaction_id) if type(transaction_id) is str else None
    if (
        match is None
        or type(production_sha) is not str
        or FULL_SHA.fullmatch(production_sha) is None
        or not production_sha.startswith(match.group(2))
    ):
        fail("BROKER_EVIDENCE_INVALID")
    completed = _parse_canonical_time(snapshot.get("completedAt"))
    if completed > observed:
        fail("BROKER_EVIDENCE_INVALID")
    return production_sha, snapshot["observedAt"]


def observe_production_visibility(
    *,
    expected_main_sha: str,
    evidence_root: Path = EVIDENCE_ROOT,
    now: datetime | None = None,
) -> dict[str, Any]:
    if type(expected_main_sha) is not str or FULL_SHA.fullmatch(expected_main_sha) is None:
        fail("EXPECTED_MAIN_SHA_INVALID")
    now_iso = canonical_now(now)
    production_sha, observed_at = read_production_observation(evidence_root)
    blockers = list(BASE_BLOCKERS)
    deploy_impact = "NO_DEPLOY"
    if production_sha != expected_main_sha:
        deploy_impact = "UNKNOWN"
        blockers = [
            "PRODUCTION_SHA_DIFFERS_FROM_MAIN",
            "DEPLOY_IMPACT_OBSERVATION_UNAVAILABLE",
            *blockers,
        ]
    candidate = {
        "projectId": PROJECT_ID,
        "repository": REPOSITORY,
        "mainSha": expected_main_sha,
        "productionSha": production_sha,
        "deployImpact": deploy_impact,
        "runtime": "UNKNOWN",
        "health": "UNKNOWN",
        "rollback": "UNKNOWN",
        "blockerCodes": blockers,
        "observedAt": observed_at,
    }
    try:
        return visibility.normalize_production_visibility(
            candidate,
            expected_project_id=PROJECT_ID,
            expected_repository=REPOSITORY,
            expected_main_sha=expected_main_sha,
            now_iso=now_iso,
            provenance=PROVENANCE,
        )
    except visibility.ProductionVisibilityContractError as exc:
        fail(f"VISIBILITY_{exc.code}")
