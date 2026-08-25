#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys

from cloudflare_owner_phone_enrollment_create import (
    AUDIT_NAME,
    CANARY_ID,
    CloudflareAccessAppCreateClient,
    execute_canary,
)
from cloudflare_owner_phone_preflight import validate_owner_email
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
                "audit": AUDIT_NAME,
                "canonical_issue": 179,
                "canary": CANARY_ID,
                "result": "BLOCKED",
                "forward_request_attempted": False,
                "forward_request_count": 0,
                "mutation_performed": False,
                "created_application_attributable": False,
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

    read_token = sys.stdin.readline(4097).rstrip("\r\n")
    write_token = sys.stdin.readline(4097).rstrip("\r\n")
    owner_email = sys.stdin.readline(1025).rstrip("\r\n")
    if len(read_token) < 20 or len(read_token) > 4096 or any(ch.isspace() for ch in read_token):
        emit_blocked("missing_or_invalid_read_api_token")
        return 2
    if len(write_token) < 20 or len(write_token) > 4096 or any(ch.isspace() for ch in write_token):
        emit_blocked("missing_or_invalid_write_api_token")
        return 2
    if read_token == write_token:
        emit_blocked("read_and_write_tokens_must_differ")
        return 2
    try:
        owner_email = validate_owner_email(owner_email)
    except AuditError as exc:
        read_token = ""
        write_token = ""
        owner_email = ""
        emit_blocked(str(exc))
        return 2

    api_base = os.environ.get("CLOUDFLARE_API_BASE", DEFAULT_API_BASE)
    try:
        read_client = CloudflareGetClient(read_token, api_base)
        write_verify_client = CloudflareGetClient(write_token, api_base)
        verify = write_verify_client.get("/user/tokens/verify")
        verify_result = verify.get("result") if isinstance(verify, dict) else None
        if not isinstance(verify_result, dict) or verify_result.get("status") != "active":
            raise AuditError("write_api_token_not_active")
        write_client = CloudflareAccessAppCreateClient(write_token, api_base)
        read_token = ""
        write_token = ""
        result = execute_canary(read_client, write_client, account_id, owner_email)
        owner_email = ""
        print(json.dumps(result, indent=2, sort_keys=True))
        if result["result"] == "PASS":
            return 0
        if result["result"] == "BLOCKED":
            return 3
        return 4
    except AuditError as exc:
        read_token = ""
        write_token = ""
        owner_email = ""
        emit_blocked(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
