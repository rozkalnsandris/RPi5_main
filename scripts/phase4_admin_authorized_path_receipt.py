#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ADMIN_PATH = ROOT / "ops/contracts/admin-zone-verification-v1.json"
CONTRACT_PATH = ROOT / "ops/contracts/admin-zone-protected-authorized-verifier-v1.json"
SCHEMA = "rozkalns.rpi5-main.phase4-admin-protected-authorized-evidence.v1"
ALLOWED_RESULTS = {"PASS", "FAIL", "UNKNOWN"}


class ReceiptError(RuntimeError):
    pass


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        raise ReceiptError("git_source_check_failed")
    return proc.stdout.strip()


def verify_exact_source(expected_main: str) -> None:
    if len(expected_main) != 40 or any(ch not in "0123456789abcdef" for ch in expected_main):
        raise ReceiptError("expected_main_invalid")
    if _git("rev-parse", "HEAD") != expected_main:
        raise ReceiptError("exact_main_mismatch")
    if _git("branch", "--show-current") != "main":
        raise ReceiptError("main_branch_required")
    for args in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        proc = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        if proc.returncode != 0:
            raise ReceiptError("tracked_source_dirty")


def load_projections() -> list[dict[str, Any]]:
    admin = json.loads(ADMIN_PATH.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if admin.get("schema") != "rozkalns.rpi5-main.admin-zone-verification.v1":
        raise ReceiptError("admin_contract_invalid")
    if contract.get("schema") != "rozkalns.rpi5-main.phase4-admin-protected-authorized-verifier.v1":
        raise ReceiptError("protected_contract_invalid")
    projections = admin.get("service_projections")
    if not isinstance(projections, list) or len(projections) != 8:
        raise ReceiptError("admin_projection_set_invalid")
    return projections


def validate_submission(
    payload: Any,
    projections: list[dict[str, Any]],
    expected_main: str,
) -> list[dict[str, str]]:
    if not isinstance(payload, dict) or set(payload) != {"source_main_sha", "services"}:
        raise ReceiptError("submission_top_level_fields_invalid")
    if payload["source_main_sha"] != expected_main:
        raise ReceiptError("submission_source_sha_mismatch")
    services = payload["services"]
    if not isinstance(services, list) or len(services) != len(projections):
        raise ReceiptError("submission_service_count_invalid")

    by_id: dict[str, dict[str, Any]] = {}
    for item in services:
        if not isinstance(item, dict) or set(item) != {
            "service_id",
            "hostname",
            "authorized_admin_result",
        }:
            raise ReceiptError("submission_service_fields_invalid")
        service_id = item["service_id"]
        if not isinstance(service_id, str) or service_id in by_id:
            raise ReceiptError("submission_service_identity_invalid")
        by_id[service_id] = item

    normalized: list[dict[str, str]] = []
    for projection in projections:
        service_id = projection["service_id"]
        item = by_id.get(service_id)
        if item is None or item["hostname"] != projection["hostname"]:
            raise ReceiptError("submission_service_projection_mismatch")
        result = item["authorized_admin_result"]
        if result not in ALLOWED_RESULTS:
            raise ReceiptError("submission_result_invalid")
        normalized.append(
            {
                "service_id": service_id,
                "hostname": projection["hostname"],
                "authorized_admin_result": result,
                "result": result,
            }
        )
    if set(by_id) != {item["service_id"] for item in projections}:
        raise ReceiptError("submission_service_set_invalid")
    return normalized


def build_report(expected_main: str, services: list[dict[str, str]]) -> dict[str, Any]:
    results = {item["authorized_admin_result"] for item in services}
    if results == {"PASS"}:
        overall = "PASS"
    elif "FAIL" in results:
        overall = "FAIL"
    else:
        overall = "UNKNOWN"
    return {
        "schema": SCHEMA,
        "observed_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "source_main_sha": expected_main,
        "verification_class": "protected-authorized-admin",
        "result": overall,
        "mutation_performed": False,
        "services": services,
        "privacy": {
            "identity_values_persisted": False,
            "session_material_persisted": False,
            "cookie_material_persisted": False,
            "credential_material_persisted": False,
            "token_material_persisted": False,
            "response_content_persisted": False,
            "browser_profile_read_by_operator": False,
        },
    }


def blocked(expected_main: str, reason: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source_main_sha": expected_main,
        "verification_class": "protected-authorized-admin",
        "result": "UNKNOWN",
        "mutation_performed": False,
        "reason": reason,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a sanitized owner-observed Phase 4 ADMIN protected-path receipt."
    )
    parser.add_argument("--expected-main", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        verify_exact_source(args.expected_main)
        payload = json.load(sys.stdin)
        services = validate_submission(payload, load_projections(), args.expected_main)
        report = build_report(args.expected_main, services)
    except (ReceiptError, json.JSONDecodeError, OSError, subprocess.SubprocessError):
        print(json.dumps(blocked(args.expected_main, "protected_receipt_validation_failed"), indent=2, sort_keys=True))
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    if report["result"] == "PASS":
        return 0
    if report["result"] == "FAIL":
        return 3
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
