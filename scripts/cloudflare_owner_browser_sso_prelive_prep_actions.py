#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re

from cloudflare_owner_browser_sso_prelive_prep import AUDIT_NAME, CANARY_ID, execute_prep
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
                "canonical_issue": 179,
                "canary": CANARY_ID,
                "result": "BLOCKED",
                "forward_request_attempted": False,
                "forward_request_count": 0,
                "mutation_performed": False,
                "reason": reason,
                "privacy": {
                    "account_id_emitted": False,
                    "api_token_emitted": False,
                    "github_token_emitted": False,
                    "auth_domain_emitted": False,
                    "organization_preimage_emitted": False,
                    "intended_payload_emitted": False,
                    "response_only_values_emitted": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


def _token_active(client: CloudflareGetClient, reason: str) -> None:
    payload = client.get("/user/tokens/verify")
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict) or result.get("status") != "active":
        raise AuditError(reason)


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
    if os.environ.get("P1D04_PRELIVE_CANARY") != CANARY_ID:
        emit_blocked("canary_binding_mismatch")
        return 2
    expected_sha = os.environ.get("P1D04_PRELIVE_EXPECTED_SHA", "")
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
    for legacy_name in (
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_WRITE_API_TOKEN",
    ):
        if os.environ.get(legacy_name):
            emit_blocked("legacy_cloudflare_env_forbidden")
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

    account_id = os.environ.pop("CLOUDFLARE_P1D04_ACCOUNT_ID", "")
    read_token = os.environ.pop("CLOUDFLARE_P1D04_READ_API_TOKEN", "")
    write_token = os.environ.pop("CLOUDFLARE_P1D04_WRITE_API_TOKEN", "")

    try:
        if not ACCOUNT_ID_RE.fullmatch(account_id):
            raise AuditError("missing_or_invalid_account_id")
        _validate_token(read_token, "missing_or_invalid_read_api_token")
        _validate_token(write_token, "missing_or_invalid_write_api_token")
        if read_token == write_token:
            raise AuditError("read_and_write_tokens_must_differ")

        read_client = CloudflareGetClient(read_token, DEFAULT_API_BASE)
        write_verify_client = CloudflareGetClient(write_token, DEFAULT_API_BASE)
        _token_active(read_client, "read_api_token_not_active")
        _token_active(write_verify_client, "write_api_token_not_active")

        read_token = ""
        write_token = ""
        result = execute_prep(read_client, account_id)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["result"] == "PASS" else 3
    except AuditError as exc:
        read_token = ""
        write_token = ""
        emit_blocked(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
