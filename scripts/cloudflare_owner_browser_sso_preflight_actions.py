#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re

from cloudflare_owner_browser_sso_preflight import build_report, collect_state, validate_owner_email
from cloudflare_zero_trust_reconcile import ACCOUNT_ID_RE, DEFAULT_API_BASE, AuditError, CloudflareGetClient
from github_p1d04_exact_main_gate import GateError, fetch_and_validate_exact_main

AUDIT_NAME = "cloudflare-p1d-browser-sso-readonly-preflight"
CANARY_ID = "p1d-03-browser-sso-preflight"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def emit_blocked(reason: str) -> None:
    print(
        json.dumps(
            {
                "schema_version": 1,
                "audit": AUDIT_NAME,
                "canonical_issue": 179,
                "canary": CANARY_ID,
                "result": "BLOCKED",
                "mutation_performed": False,
                "reason": reason,
                "privacy": {
                    "owner_email_emitted": False,
                    "account_id_emitted": False,
                    "api_token_emitted": False,
                    "github_token_emitted": False,
                    "auth_domain_or_team_name_emitted": False,
                    "access_app_or_policy_id_emitted": False,
                    "aud_cookie_jwt_or_token_emitted": False
                }
            },
            indent=2,
            sort_keys=True
        )
    )


def _validate_token(value: str) -> None:
    if len(value) < 20 or len(value) > 4096 or any(ch.isspace() for ch in value):
        raise AuditError("missing_or_invalid_read_api_token")


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        emit_blocked("github_actions_required")
        return 2
    if os.environ.get("GITHUB_EVENT_NAME") != "issue_comment":
        emit_blocked("issue_comment_event_required")
        return 2
    if os.environ.get("P1D03_CANARY") != CANARY_ID:
        emit_blocked("canary_binding_mismatch")
        return 2

    expected_sha = os.environ.get("P1D03_EXPECTED_SHA", "")
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
        "CLOUDFLARE_P1D04_ACCOUNT_ID",
        "CLOUDFLARE_P1D04_READ_API_TOKEN",
        "CLOUDFLARE_P1D04_WRITE_API_TOKEN"
    ):
        if os.environ.get(forbidden_name):
            emit_blocked("non_p1d03_cloudflare_env_forbidden")
            return 2

    github_token = os.environ.pop("GITHUB_TOKEN", "")
    try:
        fetch_and_validate_exact_main(
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            expected_sha=expected_sha,
            github_sha=github_sha,
            run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            github_token=github_token
        )
    except GateError as exc:
        github_token = ""
        emit_blocked(f"exact_main_gate_failed:{exc}")
        return 2
    github_token = ""

    account_id = os.environ.pop("CLOUDFLARE_P1D03_ACCOUNT_ID", "")
    read_token = os.environ.pop("CLOUDFLARE_P1D03_READ_API_TOKEN", "")
    owner_email = os.environ.pop("CLOUDFLARE_P1D03_OWNER_EMAIL", "")

    try:
        if not ACCOUNT_ID_RE.fullmatch(account_id):
            raise AuditError("missing_or_invalid_account_id")
        _validate_token(read_token)
        owner_email = validate_owner_email(owner_email)
        client = CloudflareGetClient(read_token, DEFAULT_API_BASE)
        state = collect_state(client, account_id)
        read_token = ""
        report = build_report(owner_email, state)
        owner_email = ""
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 3
    except AuditError as exc:
        read_token = ""
        owner_email = ""
        emit_blocked(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
