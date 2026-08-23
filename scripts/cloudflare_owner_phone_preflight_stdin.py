#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys

from cloudflare_owner_phone_preflight import build_report, collect_state, validate_owner_email
from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    DEFAULT_API_BASE,
    AuditError,
    CloudflareGetClient,
)


def emit_blocked(reason: str) -> None:
    print(
        json.dumps(
            {
                "schema_version": 1,
                "audit": "cloudflare-p1d-owner-phone-readonly-preflight",
                "canonical_issue": 179,
                "result": "BLOCKED",
                "mutation_performed": False,
                "reason": reason,
            },
            indent=2,
            sort_keys=True,
        )
    )


def main() -> int:
    if len(sys.argv) != 1:
        emit_blocked("usage_error")
        return 2

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        emit_blocked("missing_or_invalid_account_id")
        return 2

    token_line = sys.stdin.readline(4097)
    owner_line = sys.stdin.readline(1025)
    api_token = token_line.rstrip("\r\n")
    owner_email = owner_line.rstrip("\r\n")
    token_line = ""
    owner_line = ""
    if len(api_token) < 20 or len(api_token) > 4096 or any(ch.isspace() for ch in api_token):
        emit_blocked("missing_or_invalid_api_token")
        return 2

    try:
        owner_email = validate_owner_email(owner_email)
    except AuditError as exc:
        api_token = ""
        owner_email = ""
        emit_blocked(str(exc))
        return 2

    api_base = os.environ.get("CLOUDFLARE_API_BASE", DEFAULT_API_BASE)
    try:
        client = CloudflareGetClient(api_token, api_base)
        state = collect_state(client, account_id)
        api_token = ""
        report = build_report(owner_email, state)
        owner_email = ""
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 3
    except AuditError as exc:
        api_token = ""
        owner_email = ""
        emit_blocked(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
