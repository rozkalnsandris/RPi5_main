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
DEPLOY_STATE_ROOT = Path("/var/lib/rpi5-deploy")
DEPLOY_TRANSACTION_SCHEMA = "rpi5.controlled-deploy-transaction.v1"
MAX_TRANSACTION_BYTES = 64 * 1024
MAX_POINTER_BYTES = 128
TRANSACTION_ID = re.compile(r"^(\d{8}T\d{12}Z)-([0-9a-f]{12})$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
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
    return path == DEPLOY_STATE_ROOT


def _assert_safe_directory(path: Path, *, production: bool) -> None:
    try:
        info = os.lstat(path)
    except OSError:
        fail("DEPLOY_STATE_MISSING")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        fail("DEPLOY_STATE_UNSAFE")
    if production and (info.st_uid != 0 or (info.st_mode & 0o022) != 0):
        fail("DEPLOY_STATE_UNSAFE")


def _read_fixed(path: Path, *, production: bool, max_bytes: int) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        fail("DEPLOY_STATE_MISSING")
    except OSError:
        fail("DEPLOY_STATE_UNSAFE")
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            fail("DEPLOY_STATE_UNSAFE")
        if production and (info.st_uid != 0 or (info.st_mode & 0o022) != 0):
            fail("DEPLOY_STATE_UNSAFE")
        data = b""
        while True:
            remaining = max_bytes + 1 - len(data)
            if remaining <= 0:
                fail("DEPLOY_STATE_UNSAFE")
            chunk = os.read(fd, min(8192, remaining))
            if not chunk:
                break
            data += chunk
            if len(data) > max_bytes:
                fail("DEPLOY_STATE_UNSAFE")
    finally:
        os.close(fd)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        fail("DEPLOY_STATE_INVALID")


def _strict_json(raw: str) -> dict[str, Any]:
    def pairs(values):
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                fail("DEPLOY_STATE_INVALID")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (json.JSONDecodeError, TypeError, ValueError):
        fail("DEPLOY_STATE_INVALID")
    if type(value) is not dict:
        fail("DEPLOY_STATE_INVALID")
    return value


def _validate_completed_at(value: Any) -> None:
    if type(value) is not str:
        fail("DEPLOY_STATE_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("DEPLOY_STATE_INVALID")
    offset = parsed.utcoffset() if parsed.tzinfo is not None else None
    if offset is None or offset.total_seconds() != 0:
        fail("DEPLOY_STATE_INVALID")


def read_production_sha(state_root: Path = DEPLOY_STATE_ROOT) -> str:
    production = _is_production_root(state_root)
    _assert_safe_directory(state_root, production=production)
    pointer = _read_fixed(
        state_root / "latest-success",
        production=production,
        max_bytes=MAX_POINTER_BYTES,
    ).strip()
    match = TRANSACTION_ID.fullmatch(pointer)
    if match is None:
        fail("DEPLOY_STATE_INVALID")

    transactions_root = state_root / "transactions"
    transaction_root = transactions_root / pointer
    _assert_safe_directory(transactions_root, production=production)
    _assert_safe_directory(transaction_root, production=production)
    transaction = _strict_json(
        _read_fixed(
            transaction_root / "transaction.json",
            production=production,
            max_bytes=MAX_TRANSACTION_BYTES,
        )
    )
    commit = transaction.get("commit")
    if (
        transaction.get("schema") != DEPLOY_TRANSACTION_SCHEMA
        or transaction.get("id") != pointer
        or transaction.get("repository") != REPOSITORY
        or transaction.get("status") != "success"
        or type(commit) is not str
        or FULL_SHA.fullmatch(commit) is None
        or not commit.startswith(match.group(2))
    ):
        fail("DEPLOY_STATE_INVALID")
    _validate_completed_at(transaction.get("completed_at"))
    return commit


def observe_production_visibility(
    *,
    expected_main_sha: str,
    state_root: Path = DEPLOY_STATE_ROOT,
    now: datetime | None = None,
) -> dict[str, Any]:
    if type(expected_main_sha) is not str or FULL_SHA.fullmatch(expected_main_sha) is None:
        fail("EXPECTED_MAIN_SHA_INVALID")
    now_iso = canonical_now(now)
    production_sha = read_production_sha(state_root)
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
        "observedAt": now_iso,
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
