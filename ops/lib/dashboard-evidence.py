#!/usr/bin/env python3
"""Write bounded sanitized evidence consumed by dashboard_RPi5.

Production CLI is root-only and writes only fixed files beneath
/var/lib/dashboard-rpi5/evidence. The module functions accept alternate roots
for repository tests; they never read raw logs, secrets, or configuration.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVIDENCE_ROOT = Path("/var/lib/dashboard-rpi5/evidence")
DEPLOY_STATE_ROOT = Path("/var/lib/rpi5-deploy")
MAX_BYTES = 64 * 1024
BACKUP_MAX_RUNS = 32
EVENT_MAX_ITEMS = 64
BACKUP_SCHEMA = "dashboard-rpi5.backup-evidence.v1"
ENDPOINT_SCHEMA = "dashboard-rpi5.endpoint-evidence.v1"
THROTTLE_SCHEMA = "dashboard-rpi5.throttle-evidence.v1"
DEPLOY_TRANSACTION_SCHEMA = "rpi5.controlled-deploy-transaction.v1"
DEPLOY_REPOSITORY = "rozkalnsandris/RPi5_main"
FILES = {
    "backup": "backups.json",
    "endpoint": "endpoints.json",
    "maintenance": "maintenance.json",
    "deploy": "deployments.json",
    "throttle": "throttle.json",
}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,119}$")
SAFE_ENDPOINT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SAFE_UNIT_RESULT = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
INVOCATION_ID = re.compile(r"^[0-9a-f]{32}$")
TRANSACTION_ID = re.compile(r"^(\d{8}T\d{12}Z)-([0-9a-f]{12})$")
COMMIT = re.compile(r"^[0-9a-f]{12}$")
FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")
RAW_HEX = re.compile(r"^0x[0-9a-f]+$")
STATES = {"UP", "DOWN", "DEGRADED", "UNKNOWN"}


def parse_iso(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be canonical UTC ISO")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    canonical = parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if value != canonical and value != canonical.replace(".000Z", "Z"):
        raise ValueError("timestamp must be canonical UTC ISO")
    return parsed


def canonical_iso(value: str) -> str:
    return parse_iso(value).astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_controlled_deploy_iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid controlled-deploy timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid controlled-deploy timestamp") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError("controlled-deploy timestamp must be UTC")
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _assert_safe_directory(path: Path, *, production: bool) -> None:
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise RuntimeError("evidence directory must be a real directory")
    if production and (st.st_uid != 0 or (st.st_mode & 0o022) != 0):
        raise RuntimeError("evidence directory must be root-owned and not group/world writable")


def ensure_root(root: Path = EVIDENCE_ROOT) -> None:
    production = root == EVIDENCE_ROOT
    if production and os.geteuid() != 0:
        raise PermissionError("production evidence writer must run as root")
    if production:
        _assert_safe_directory(root.parent, production=True)
    root.mkdir(mode=0o755, parents=False, exist_ok=True)
    _assert_safe_directory(root, production=production)


def _read_existing(path: Path, default: dict[str, Any], *, production: bool) -> dict[str, Any]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return default
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
            raise RuntimeError("unsafe evidence file")
        if production and (st.st_uid != 0 or (st.st_mode & 0o022) != 0):
            raise RuntimeError("unsafe evidence file metadata")
        raw = b""
        while True:
            chunk = os.read(fd, min(8192, MAX_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
            if len(raw) > MAX_BYTES:
                raise RuntimeError("oversized evidence file")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("evidence file must be object")
        return value
    finally:
        os.close(fd)


def _read_fixed_text(path: Path, *, production: bool, max_bytes: int = MAX_BYTES) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_nlink != 1:
            raise RuntimeError("unsafe source file")
        if st.st_size > max_bytes:
            raise RuntimeError("oversized source file")
        if production and (st.st_uid != 0 or (st.st_mode & 0o022) != 0):
            raise RuntimeError("unsafe source file metadata")
        raw = b""
        while True:
            chunk = os.read(fd, min(8192, max_bytes + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
            if len(raw) > max_bytes:
                raise RuntimeError("oversized source file")
        return raw.decode("utf-8")
    finally:
        os.close(fd)


def _atomic_write(path: Path, value: dict[str, Any], *, production: bool) -> None:
    encoded = (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_BYTES:
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


def _path(kind: str, root: Path) -> Path:
    return root / FILES[kind]


def _bounded_label(value: str) -> str:
    if not isinstance(value, str) or not (1 <= len(value) <= 80) or value.strip() != value:
        raise ValueError("invalid label")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ValueError("invalid label")
    return value


def _validate_backup_run(item: Any) -> None:
    keys = {"runId", "startedAt", "completedAt", "result", "durationSeconds", "sizeBytes", "exitCode"}
    if not isinstance(item, dict) or set(item) != keys:
        raise ValueError("invalid existing backup run")
    if not isinstance(item["runId"], str) or len(item["runId"]) > 80 or not SAFE_ID.fullmatch(item["runId"]):
        raise ValueError("invalid existing backup run id")
    started = parse_iso(item["startedAt"])
    completed = parse_iso(item["completedAt"])
    duration = (completed - started).total_seconds()
    if not isinstance(item["durationSeconds"], int) or item["durationSeconds"] < 0 or item["durationSeconds"] > 172800 or abs(duration - item["durationSeconds"]) > 2:
        raise ValueError("invalid existing backup duration")
    if not isinstance(item["exitCode"], int) or not 0 <= item["exitCode"] <= 255:
        raise ValueError("invalid existing backup exit code")
    if item["result"] == "SUCCESS":
        if item["exitCode"] != 0 or not isinstance(item["sizeBytes"], int) or item["sizeBytes"] < 1:
            raise ValueError("invalid existing backup success")
    elif item["result"] == "FAILED":
        if item["exitCode"] == 0 or item["sizeBytes"] is not None:
            raise ValueError("invalid existing backup failure")
    else:
        raise ValueError("invalid existing backup result")


def _validate_endpoint_event(item: Any) -> None:
    keys = {"eventId", "endpointId", "label", "occurredAt", "fromState", "toState", "statusCode", "latencyMs"}
    if not isinstance(item, dict) or set(item) != keys:
        raise ValueError("invalid existing endpoint event")
    if not isinstance(item["eventId"], str) or len(item["eventId"]) > 120 or not SAFE_ID.fullmatch(item["eventId"]):
        raise ValueError("invalid existing endpoint event id")
    if not isinstance(item["endpointId"], str) or not SAFE_ENDPOINT_ID.fullmatch(item["endpointId"]):
        raise ValueError("invalid existing endpoint id")
    _bounded_label(item["label"])
    parse_iso(item["occurredAt"])
    if item["fromState"] not in STATES or item["toState"] not in STATES or item["fromState"] == item["toState"]:
        raise ValueError("invalid existing endpoint transition")
    code = item["statusCode"]
    latency = item["latencyMs"]
    if code is not None and (not isinstance(code, int) or not 100 <= code <= 599):
        raise ValueError("invalid existing endpoint status")
    if latency is not None and (not isinstance(latency, int) or not 0 <= latency <= 300000):
        raise ValueError("invalid existing endpoint latency")


def _validate_maintenance_event(item: Any) -> None:
    if not isinstance(item, dict) or set(item) != {"invocationId", "occurredAt", "result", "unitResult"}:
        raise ValueError("invalid existing maintenance event")
    if not isinstance(item["invocationId"], str) or not INVOCATION_ID.fullmatch(item["invocationId"]):
        raise ValueError("invalid existing maintenance invocation")
    parse_iso(item["occurredAt"])
    if item["result"] == "SUCCESS":
        if item["unitResult"] is not None:
            raise ValueError("invalid existing maintenance success")
    elif item["result"] == "FAILED":
        if not isinstance(item["unitResult"], str) or not SAFE_UNIT_RESULT.fullmatch(item["unitResult"]):
            raise ValueError("invalid existing maintenance failure")
    else:
        raise ValueError("invalid existing maintenance result")


def _validate_deploy_event(item: Any) -> None:
    if not isinstance(item, dict) or set(item) != {"transactionId", "commit", "occurredAt"}:
        raise ValueError("invalid existing deploy event")
    if not isinstance(item["transactionId"], str) or not isinstance(item["commit"], str):
        raise ValueError("invalid existing deploy identity")
    match = TRANSACTION_ID.fullmatch(item["transactionId"])
    if match is None or not COMMIT.fullmatch(item["commit"]) or match.group(2) != item["commit"]:
        raise ValueError("invalid existing deploy identity")
    parse_iso(item["occurredAt"])


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        events,
        key=lambda item: (
            parse_iso(str(item["occurredAt"])).timestamp(),
            str(item.get("invocationId") or item.get("transactionId") or ""),
        ),
        reverse=True,
    )


def record_backup(*, run_id: str, started_at: str, completed_at: str, exit_code: int,
                  size_bytes: int | None, root: Path = EVIDENCE_ROOT) -> bool:
    ensure_root(root)
    production = root == EVIDENCE_ROOT
    if not SAFE_ID.fullmatch(run_id) or len(run_id) > 80:
        raise ValueError("invalid backup run id")
    started = parse_iso(started_at)
    completed = parse_iso(completed_at)
    duration = int((completed - started).total_seconds())
    if duration < 0 or duration > 172800:
        raise ValueError("invalid backup duration")
    if not isinstance(exit_code, int) or not 0 <= exit_code <= 255:
        raise ValueError("invalid backup exit code")
    if exit_code == 0:
        if not isinstance(size_bytes, int) or size_bytes < 1:
            raise ValueError("successful backup requires positive size")
        result = "SUCCESS"
    else:
        if size_bytes is not None:
            raise ValueError("failed backup must not claim size")
        result = "FAILED"
    path = _path("backup", root)
    value = _read_existing(path, {"schema": BACKUP_SCHEMA, "runs": []}, production=production)
    if set(value) != {"schema", "runs"} or value.get("schema") != BACKUP_SCHEMA or not isinstance(value.get("runs"), list):
        raise ValueError("invalid existing backup evidence")
    runs = value["runs"]
    if len(runs) > BACKUP_MAX_RUNS:
        raise ValueError("existing backup history exceeds bound")
    for item in runs:
        _validate_backup_run(item)
    if any(item.get("runId") == run_id for item in runs):
        return False
    event = {
        "runId": run_id,
        "startedAt": canonical_iso(started_at),
        "completedAt": canonical_iso(completed_at),
        "result": result,
        "durationSeconds": duration,
        "sizeBytes": size_bytes,
        "exitCode": exit_code,
    }
    _atomic_write(path, {"schema": BACKUP_SCHEMA, "runs": [event, *runs][:BACKUP_MAX_RUNS]}, production=production)
    return True


def record_endpoint(*, endpoint_id: str, label: str, state: str, status_code: int | None,
                    latency_ms: int | None, occurred_at: str, root: Path = EVIDENCE_ROOT) -> bool:
    ensure_root(root)
    production = root == EVIDENCE_ROOT
    if not SAFE_ENDPOINT_ID.fullmatch(endpoint_id):
        raise ValueError("invalid endpoint id")
    label = _bounded_label(label)
    if state not in STATES or state == "UNKNOWN":
        raise ValueError("collector observation must be concrete")
    if status_code is not None and (not isinstance(status_code, int) or not 100 <= status_code <= 599):
        raise ValueError("invalid status code")
    if latency_ms is not None and (not isinstance(latency_ms, int) or not 0 <= latency_ms <= 300000):
        raise ValueError("invalid latency")
    occurred_at = canonical_iso(occurred_at)
    path = _path("endpoint", root)
    value = _read_existing(path, {"schema": ENDPOINT_SCHEMA, "events": []}, production=production)
    if set(value) != {"schema", "events"} or value.get("schema") != ENDPOINT_SCHEMA or not isinstance(value.get("events"), list):
        raise ValueError("invalid existing endpoint evidence")
    events = value["events"]
    if len(events) > EVENT_MAX_ITEMS:
        raise ValueError("existing endpoint history exceeds bound")
    for item in events:
        _validate_endpoint_event(item)
    previous_state = "UNKNOWN"
    for event in events:
        if event.get("endpointId") == endpoint_id:
            previous_state = event.get("toState")
            break
    if previous_state == state:
        return False
    if previous_state not in STATES:
        raise ValueError("invalid existing endpoint state")
    stamp = occurred_at.replace("-", "").replace(":", "").replace(".", "")
    event_id = f"{endpoint_id}:{stamp}:{state.lower()}"
    if len(event_id) > 120 or not SAFE_ID.fullmatch(event_id):
        raise ValueError("generated endpoint event id is invalid")
    event = {
        "eventId": event_id,
        "endpointId": endpoint_id,
        "label": label,
        "occurredAt": occurred_at,
        "fromState": previous_state,
        "toState": state,
        "statusCode": status_code,
        "latencyMs": latency_ms,
    }
    _atomic_write(path, {"schema": ENDPOINT_SCHEMA, "events": [event, *events][:EVENT_MAX_ITEMS]}, production=production)
    return True


def record_maintenance(*, invocation_id: str, service_result: str, occurred_at: str,
                       root: Path = EVIDENCE_ROOT) -> bool:
    ensure_root(root)
    production = root == EVIDENCE_ROOT
    if not INVOCATION_ID.fullmatch(invocation_id):
        raise ValueError("invalid invocation id")
    if not SAFE_UNIT_RESULT.fullmatch(service_result):
        raise ValueError("invalid service result")
    occurred_at = canonical_iso(occurred_at)
    result = "SUCCESS" if service_result == "success" else "FAILED"
    unit_result = None if result == "SUCCESS" else service_result
    path = _path("maintenance", root)
    value = _read_existing(path, {"observedAt": occurred_at, "events": []}, production=production)
    if set(value) != {"observedAt", "events"} or not isinstance(value.get("events"), list):
        raise ValueError("invalid existing maintenance evidence")
    events = value["events"]
    if len(events) > EVENT_MAX_ITEMS:
        raise ValueError("existing maintenance history exceeds bound")
    for item in events:
        _validate_maintenance_event(item)

    event = {
        "invocationId": invocation_id,
        "occurredAt": occurred_at,
        "result": result,
        "unitResult": unit_result,
    }
    same = [item for item in events if item.get("invocationId") == invocation_id]
    if len(same) > 1:
        raise ValueError("duplicate maintenance invocation")
    if same:
        existing = same[0]
        if existing.get("result") != result or existing.get("unitResult") != unit_result:
            raise ValueError("maintenance invocation result conflict")
        if existing.get("occurredAt") == occurred_at:
            return False
        events = [item for item in events if item.get("invocationId") != invocation_id]
    events = _sort_events([event, *events])[:EVENT_MAX_ITEMS]
    _atomic_write(path, {"observedAt": occurred_at, "events": events}, production=production)
    return True


def record_deploy(*, transaction_id: str, commit: str, occurred_at: str,
                  root: Path = EVIDENCE_ROOT) -> bool:
    ensure_root(root)
    production = root == EVIDENCE_ROOT
    match = TRANSACTION_ID.fullmatch(transaction_id)
    if match is None or not COMMIT.fullmatch(commit) or match.group(2) != commit:
        raise ValueError("invalid deploy identity")
    occurred_at = canonical_iso(occurred_at)
    path = _path("deploy", root)
    value = _read_existing(path, {"observedAt": occurred_at, "events": []}, production=production)
    if set(value) != {"observedAt", "events"} or not isinstance(value.get("events"), list):
        raise ValueError("invalid existing deploy evidence")
    events = value["events"]
    if len(events) > EVENT_MAX_ITEMS:
        raise ValueError("existing deploy history exceeds bound")
    for item in events:
        _validate_deploy_event(item)
    if any(item.get("transactionId") == transaction_id for item in events):
        return False
    event = {"transactionId": transaction_id, "commit": commit, "occurredAt": occurred_at}
    events = _sort_events([event, *events])[:EVENT_MAX_ITEMS]
    _atomic_write(path, {"observedAt": occurred_at, "events": events}, production=production)
    return True


def sync_deploy_state(*, state_root: Path = DEPLOY_STATE_ROOT, root: Path = EVIDENCE_ROOT,
                      observed_at: str | None = None) -> bool:
    """Rebuild evidence from the authoritative controlled-deploy latest-success transaction."""
    ensure_root(root)
    production_state = state_root == DEPLOY_STATE_ROOT
    if production_state and os.geteuid() != 0:
        raise PermissionError("production deploy evidence sync must run as root")

    _assert_safe_directory(state_root, production=production_state)
    latest = state_root / "latest-success"
    try:
        pointer = _read_fixed_text(latest, production=production_state, max_bytes=128).strip()
    except FileNotFoundError:
        pointer = ""

    observed = canonical_iso(observed_at) if observed_at is not None else utc_now_iso()
    evidence_path = _path("deploy", root)
    evidence_production = root == EVIDENCE_ROOT

    if pointer == "":
        _atomic_write(
            evidence_path,
            {"observedAt": observed, "events": []},
            production=evidence_production,
        )
        return True

    match = TRANSACTION_ID.fullmatch(pointer)
    if match is None:
        raise ValueError("invalid latest controlled-deploy pointer")
    short_commit = match.group(2)

    transactions_root = state_root / "transactions"
    _assert_safe_directory(transactions_root, production=production_state)
    transaction_root = transactions_root / pointer
    _assert_safe_directory(transaction_root, production=production_state)
    raw = _read_fixed_text(
        transaction_root / "transaction.json",
        production=production_state,
        max_bytes=MAX_BYTES,
    )
    try:
        transaction = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid controlled-deploy transaction json") from exc
    if not isinstance(transaction, dict):
        raise ValueError("invalid controlled-deploy transaction")
    full_commit = transaction.get("commit")
    completed_at = transaction.get("completed_at")
    if (
        transaction.get("schema") != DEPLOY_TRANSACTION_SCHEMA
        or transaction.get("id") != pointer
        or transaction.get("repository") != DEPLOY_REPOSITORY
        or transaction.get("status") != "success"
        or not isinstance(full_commit, str)
        or FULL_COMMIT.fullmatch(full_commit) is None
        or not full_commit.startswith(short_commit)
        or not isinstance(completed_at, str)
    ):
        raise ValueError("invalid controlled-deploy transaction")
    completed_at = canonical_controlled_deploy_iso(completed_at)
    event = {
        "transactionId": pointer,
        "commit": short_commit,
        "occurredAt": completed_at,
    }
    _atomic_write(
        evidence_path,
        {"observedAt": observed, "events": [event]},
        production=evidence_production,
    )
    return True


def record_throttle(*, raw_hex: str, observed_at: str, root: Path = EVIDENCE_ROOT) -> bool:
    ensure_root(root)
    production = root == EVIDENCE_ROOT
    raw_hex = raw_hex.lower()
    if not RAW_HEX.fullmatch(raw_hex):
        raise ValueError("invalid throttle value")
    if int(raw_hex[2:], 16) > 0xFFFFFFFF:
        raise ValueError("throttle value out of range")
    value = {
        "schema": THROTTLE_SCHEMA,
        "observedAt": canonical_iso(observed_at),
        "rawHex": raw_hex,
    }
    _atomic_write(_path("throttle", root), value, production=production)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write sanitized dashboard evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup-record")
    backup.add_argument("--run-id", required=True)
    backup.add_argument("--started-at", required=True)
    backup.add_argument("--completed-at", required=True)
    backup.add_argument("--exit-code", type=int, required=True)
    backup.add_argument("--size-bytes", type=int)
    endpoint = sub.add_parser("endpoint-observe")
    endpoint.add_argument("--endpoint-id", required=True)
    endpoint.add_argument("--label", required=True)
    endpoint.add_argument("--state", choices=sorted(STATES - {"UNKNOWN"}), required=True)
    endpoint.add_argument("--status-code", type=int)
    endpoint.add_argument("--latency-ms", type=int)
    endpoint.add_argument("--occurred-at", required=True)
    maintenance = sub.add_parser("maintenance-record")
    maintenance.add_argument("--invocation-id", required=True)
    maintenance.add_argument("--service-result", required=True)
    maintenance.add_argument("--occurred-at", required=True)
    deploy = sub.add_parser("deploy-record")
    deploy.add_argument("--transaction-id", required=True)
    deploy.add_argument("--commit", required=True)
    deploy.add_argument("--occurred-at", required=True)
    sub.add_parser("deploy-sync")
    throttle = sub.add_parser("throttle-record")
    throttle.add_argument("--raw-hex", required=True)
    throttle.add_argument("--observed-at", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if os.geteuid() != 0:
        raise PermissionError("dashboard evidence writer must run as root")
    if args.command == "backup-record":
        record_backup(
            run_id=args.run_id,
            started_at=args.started_at,
            completed_at=args.completed_at,
            exit_code=args.exit_code,
            size_bytes=args.size_bytes,
        )
    elif args.command == "endpoint-observe":
        record_endpoint(
            endpoint_id=args.endpoint_id,
            label=args.label,
            state=args.state,
            status_code=args.status_code,
            latency_ms=args.latency_ms,
            occurred_at=args.occurred_at,
        )
    elif args.command == "maintenance-record":
        record_maintenance(
            invocation_id=args.invocation_id,
            service_result=args.service_result,
            occurred_at=args.occurred_at,
        )
    elif args.command == "deploy-record":
        record_deploy(
            transaction_id=args.transaction_id,
            commit=args.commit,
            occurred_at=args.occurred_at,
        )
    elif args.command == "deploy-sync":
        sync_deploy_state()
    elif args.command == "throttle-record":
        record_throttle(raw_hex=args.raw_hex, observed_at=args.observed_at)
    else:
        raise AssertionError("unreachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
