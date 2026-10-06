#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re

from cloudflare_phase5_deals_access_inventory_diagnostic import (
    AUDIT_NAME,
    CANARY_ID,
    CANONICAL_ISSUE,
    build_report,
    collect_visibility,
)
from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    DEFAULT_API_BASE,
    AuditError,
    CloudflareGetClient,
)
from github_p1d04_exact_main_gate import GateError, fetch_and_validate_exact_main

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def emit_blocked(reason: str) -> None:
    print(
        json.dumps(
            {
                "schema_version": 1,
                "audit": AUDIT_NAME,
                "canonical_issue": CANONICAL_ISSUE,
                "canary": CANARY_ID,
                "target": "deals.rozkalns.net",
                "result": "BLOCKED",
                "reason": reason,
                "mutation_performed": False,
                "cloudflare_write_requests_performed": 0,
                "privacy": {
                    "account_id_emitted": False,
                    "app_id_emitted": False,
                    "api_token_emitted": False,
                    "github_token_emitted": False,
                    "raw_api_payload_emitted": False,
                    "identity_value_emitted": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


def _validate_token(value: str, reason: str) -> None:
    if len(value) < 20 or len(value) > 4096 or any(ch.isspace() for ch in value):
        raise AuditError(reason)


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        emit_blocked("github_actions_required")
        return 2
    if os.environ.get("GITHUB_EVENT_NAME") != "issue_comment":
        emit_blocked("issue_comment_event_required")
        return 2
    if os.environ.get("P5_DEALS_ACCESS_DIAG_CANARY") != CANARY_ID:
        emit_blocked("canary_binding_mismatch")
        return 2

    expected_sha = os.environ.get("P5_DEALS_ACCESS_DIAG_EXPECTED_SHA", "")
    github_sha = os.environ.get("GITHUB_SHA", "")
    if not SHA_RE.fullmatch(expected_sha) or github_sha != expected_sha:
        emit_blocked("exact_main_sha_binding_invalid")
        return 2
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        emit_blocked("workflow_rerun_forbidden")
        return 2
    if os.environ.get("CLOUDFLARE_API_BASE"):
        emit_blocked("custom_cloudflare_api_base_forbidden")
        return 2

    for forbidden_name in (
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_WRITE_API_TOKEN",
        "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
        "CLOUDFLARE_TUNNEL_API_TOKEN",
    ):
        if os.environ.get(forbidden_name):
            emit_blocked("write_or_legacy_cloudflare_env_forbidden")
            return 2

    github_token = os.environ.pop("GITHUB_TOKEN", "")
    try:
        fetch_and_validate_exact_main(
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            expected_sha=expected_sha,
            github_sha=github_sha,
            run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            github_token=github_token,
        )
    except GateError as exc:
        github_token = ""
        emit_blocked(f"exact_main_gate_failed:{exc}")
        return 2
    github_token = ""

    p1d03_account = os.environ.pop("CLOUDFLARE_P1D03_ACCOUNT_ID", "")
    p1d03_token = os.environ.pop("CLOUDFLARE_P1D03_READ_API_TOKEN", "")
    p1d04_account = os.environ.pop("CLOUDFLARE_P1D04_ACCOUNT_ID", "")
    p1d04_token = os.environ.pop("CLOUDFLARE_P1D04_READ_API_TOKEN", "")

    try:
        if not ACCOUNT_ID_RE.fullmatch(p1d03_account):
            raise AuditError("p1d03_account_binding_invalid")
        if not ACCOUNT_ID_RE.fullmatch(p1d04_account):
            raise AuditError("p1d04_account_binding_invalid")
        _validate_token(p1d03_token, "p1d03_read_api_token_invalid")
        _validate_token(p1d04_token, "p1d04_read_api_token_invalid")

        p1d03_client = CloudflareGetClient(p1d03_token, DEFAULT_API_BASE)
        p1d04_client = CloudflareGetClient(p1d04_token, DEFAULT_API_BASE)

        try:
            p1d03 = collect_visibility(p1d03_client, p1d03_account)
        except AuditError as exc:
            raise AuditError(f"p1d03_visibility_failed:{exc}") from exc
        try:
            p1d04 = collect_visibility(p1d04_client, p1d04_account)
        except AuditError as exc:
            raise AuditError(f"p1d04_visibility_failed:{exc}") from exc

        p1d03_token = ""
        p1d04_token = ""

        report = build_report(
            p1d03_account_id=p1d03_account,
            p1d03=p1d03,
            p1d04_account_id=p1d04_account,
            p1d04=p1d04,
        )
        p1d03_account = ""
        p1d04_account = ""
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 3
    except AuditError as exc:
        p1d03_token = ""
        p1d04_token = ""
        p1d03_account = ""
        p1d04_account = ""
        emit_blocked(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
