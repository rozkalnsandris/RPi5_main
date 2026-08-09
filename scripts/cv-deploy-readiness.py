#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile

SCHEMA_VERSION = 1
STATE_FILENAME = "readiness.json"
LOCK_FILENAME = "readiness.lock"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REASONS = {
    "CURRENT",
    "WAIT_CI",
    "MANUAL_ROLLOUT_REQUIRED",
    "DB_HOST_APPLY_REQUIRED",
    "NO_DEPLOY",
    "WAIT_HELPER_ACTIVATION",
    "WAIT_PULL_TRANSPORT_ACTIVATION",
    "AUTO_DEPLOY_READY",
    "PREFLIGHT_FAILED",
    "DEPLOY_FAILED",
}
DEPLOY_IMPACTS = {
    "NO_DEPLOY",
    "AUTO_DEPLOY_SAFE",
    "MANUAL_ROLLOUT_REQUIRED",
    "DB_HOST_APPLY_REQUIRED",
    "UNCLASSIFIED",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_sha(value: str, *, label: str, allow_empty: bool = False) -> None:
    if allow_empty and not value:
        return
    if SHA_RE.fullmatch(value) is None:
        raise ValueError(f"invalid {label} SHA")


def load_state(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("readiness state path is unsafe")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("unsupported readiness state")
    return payload


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()


@contextmanager
def state_lock(state_root: Path):
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_root, 0o700)
    lock_path = state_root / LOCK_FILENAME
    if lock_path.exists() and (not lock_path.is_file() or lock_path.is_symlink()):
        raise RuntimeError("readiness lock path is unsafe")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def record(
    *,
    state_root: Path,
    reason: str,
    target_sha: str,
    production_sha: str,
    deploy_impact: str,
    control_plane_changed: bool,
    ci_run_id: int | None,
) -> dict[str, object]:
    if reason not in REASONS:
        raise ValueError("unsupported readiness reason")
    if deploy_impact not in DEPLOY_IMPACTS:
        raise ValueError("unsupported deploy impact")

    allow_empty = reason == "PREFLIGHT_FAILED"
    validate_sha(target_sha, label="target", allow_empty=allow_empty)
    validate_sha(production_sha, label="production", allow_empty=allow_empty)
    if reason == "CURRENT" and target_sha != production_sha:
        raise ValueError("CURRENT requires target SHA to equal production SHA")
    if ci_run_id is not None and ci_run_id <= 0:
        raise ValueError("CI run id must be positive")

    now = utc_now()
    state_path = state_root / STATE_FILENAME
    with state_lock(state_root):
        previous = load_state(state_path)
        key = (reason, target_sha, production_sha, deploy_impact, control_plane_changed)
        previous_key = None
        if previous:
            previous_key = (
                str(previous.get("reason", "")),
                str(previous.get("target_sha", "")),
                str(previous.get("production_sha", "")),
                str(previous.get("deploy_impact", "")),
                bool(previous.get("control_plane_changed", False)),
            )
        first_seen = (
            str(previous.get("first_seen_utc"))
            if previous is not None and previous_key == key
            else now
        )
        payload: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "reason": reason,
            "deploy_impact": deploy_impact,
            "target_sha": target_sha,
            "production_sha": production_sha,
            "control_plane_changed": control_plane_changed,
            "ci_run_id": ci_run_id,
            "first_seen_utc": first_seen,
            "last_seen_utc": now,
            "production_mutation_authorized": False,
        }
        atomic_write_json(state_path, payload)
        return payload


def parse_bool(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist sanitized CV pull-deploy readiness state")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--state-root", required=True, type=Path)
    record_parser.add_argument("--reason", required=True, choices=sorted(REASONS))
    record_parser.add_argument("--target-sha", default="")
    record_parser.add_argument("--production-sha", default="")
    record_parser.add_argument("--deploy-impact", required=True, choices=sorted(DEPLOY_IMPACTS))
    record_parser.add_argument("--control-plane-changed", required=True, type=parse_bool)
    record_parser.add_argument("--ci-run-id", type=int)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--state-root", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "record":
        payload = record(
            state_root=args.state_root,
            reason=args.reason,
            target_sha=args.target_sha,
            production_sha=args.production_sha,
            deploy_impact=args.deploy_impact,
            control_plane_changed=args.control_plane_changed,
            ci_run_id=args.ci_run_id,
        )
        print("CV_DEPLOY_READINESS_RECORD=PASS")
        print(f"READINESS_REASON={payload['reason']}")
        return 0

    state = load_state(args.state_root / STATE_FILENAME)
    print(json.dumps(state or {"state": "ABSENT"}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
