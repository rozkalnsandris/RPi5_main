#!/usr/bin/env python3
"""Publish a strict sanitized Phase 5 production-SHA snapshot for non-root readers."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

EVIDENCE_ROOT = Path("/var/lib/dashboard-rpi5/evidence")
DEPLOY_STATE_ROOT = Path("/var/lib/rpi5-deploy")
EVIDENCE_FILENAME = "phase5-production-visibility.json"
SCHEMA = "rpi5.phase5-production-visibility-evidence.v1"
REPOSITORY = "rozkalnsandris/RPi5_main"
MAX_EVIDENCE_BYTES = 4096
MAX_TRANSACTION_BYTES = 64 * 1024
MAX_POINTER_BYTES = 128
TRANSACTION_SCHEMA = "rpi5.controlled-deploy-transaction.v1"
TRANSACTION_ID = re.compile(r"^(\d{8}T\d{12}Z)-([0-9a-f]{12})$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SNAPSHOT_FIELDS = {
    "schema", "status", "repository", "transactionId", "productionSha",
    "completedAt", "observedAt",
}


def canonical_iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    offset = parsed.utcoffset() if parsed.tzinfo is not None else None
    if offset is None or offset.total_seconds() != 0:
        raise ValueError("timestamp must be UTC")
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _assert_safe_directory(path: Path, *, production: bool) -> None:
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise RuntimeError("unsafe evidence directory")
    if production and (st.st_uid != 0 or (st.st_mode & 0o022) != 0):
        raise RuntimeError("unsafe evidence directory metadata")


def _read_fixed(path: Path, *, production: bool, max_bytes: int) -> str:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > max_bytes:
            raise RuntimeError("unsafe source file")
        if production and (st.st_uid != 0 or (st.st_mode & 0o022) != 0):
            raise RuntimeError("unsafe source file metadata")
        data = b""
        while True:
            remaining = max_bytes + 1 - len(data)
            if remaining <= 0:
                raise RuntimeError("oversized source file")
            chunk = os.read(fd, min(8192, remaining))
            if not chunk:
                break
            data += chunk
            if len(data) > max_bytes:
                raise RuntimeError("oversized source file")
    finally:
        os.close(fd)
    return data.decode("utf-8")


def _strict_json(raw: str) -> dict[str, Any]:
    def pairs(values):
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate transaction key")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("transaction must be an object")
    return value


def _atomic_write(path: Path, value: dict[str, Any], *, production: bool) -> None:
    encoded = (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_EVIDENCE_BYTES:
        raise ValueError("evidence output exceeds bound")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o644)
        if production:
            os.fchown(fd, 0, 0)
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(fd)
        fd = -1
        os.replace(temp_name, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def unavailable_snapshot(observed_at: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "UNAVAILABLE",
        "repository": REPOSITORY,
        "transactionId": None,
        "productionSha": None,
        "completedAt": None,
        "observedAt": observed_at,
    }


def sync_phase5_visibility(
    *,
    state_root: Path = DEPLOY_STATE_ROOT,
    evidence_root: Path = EVIDENCE_ROOT,
    observed_at: str | None = None,
) -> bool:
    production_state = state_root == DEPLOY_STATE_ROOT
    production_evidence = evidence_root == EVIDENCE_ROOT
    if (production_state or production_evidence) and os.geteuid() != 0:
        raise PermissionError("production Phase 5 evidence sync must run as root")
    _assert_safe_directory(evidence_root, production=production_evidence)
    observed = canonical_iso(observed_at) if observed_at is not None else utc_now_iso()
    evidence_path = evidence_root / EVIDENCE_FILENAME

    # Invalidate first so any later read/validation failure cannot leave a fresh
    # previously-AVAILABLE snapshot authoritative for non-root consumers.
    _atomic_write(evidence_path, unavailable_snapshot(observed), production=production_evidence)

    _assert_safe_directory(state_root, production=production_state)
    try:
        pointer = _read_fixed(
            state_root / "latest-success",
            production=production_state,
            max_bytes=MAX_POINTER_BYTES,
        ).strip()
    except FileNotFoundError:
        return False
    if pointer == "":
        return False

    match = TRANSACTION_ID.fullmatch(pointer)
    if match is None:
        raise ValueError("invalid latest controlled-deploy pointer")
    transactions_root = state_root / "transactions"
    transaction_root = transactions_root / pointer
    _assert_safe_directory(transactions_root, production=production_state)
    _assert_safe_directory(transaction_root, production=production_state)
    transaction = _strict_json(
        _read_fixed(
            transaction_root / "transaction.json",
            production=production_state,
            max_bytes=MAX_TRANSACTION_BYTES,
        )
    )
    full_commit = transaction.get("commit")
    completed_at = transaction.get("completed_at")
    if (
        transaction.get("schema") != TRANSACTION_SCHEMA
        or transaction.get("id") != pointer
        or transaction.get("repository") != REPOSITORY
        or transaction.get("status") != "success"
        or not isinstance(full_commit, str)
        or FULL_SHA.fullmatch(full_commit) is None
        or not full_commit.startswith(match.group(2))
        or not isinstance(completed_at, str)
    ):
        raise ValueError("invalid controlled-deploy transaction")
    completed = canonical_iso(completed_at)
    if datetime.fromisoformat(completed.replace("Z", "+00:00")) > datetime.fromisoformat(observed.replace("Z", "+00:00")):
        raise ValueError("controlled-deploy completion cannot be after observation")

    snapshot = {
        "schema": SCHEMA,
        "status": "AVAILABLE",
        "repository": REPOSITORY,
        "transactionId": pointer,
        "productionSha": full_commit,
        "completedAt": completed,
        "observedAt": observed,
    }
    if set(snapshot) != SNAPSHOT_FIELDS:
        raise AssertionError("snapshot schema drift")
    _atomic_write(evidence_path, snapshot, production=production_evidence)
    return True


def main() -> int:
    sync_phase5_visibility()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
