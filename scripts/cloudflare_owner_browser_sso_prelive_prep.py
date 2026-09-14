#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from cloudflare_owner_browser_sso_session_update import (
    CANONICAL_ISSUE,
    RESPONSE_ONLY_FIELDS,
    TARGET_GLOBAL_SESSION,
    build_update_plan,
    collect_organization,
)
from cloudflare_zero_trust_reconcile import ACCOUNT_ID_RE, AuditError, CloudflareGetClient

CANARY_ID = "p1d-04-prelive-prep"
AUDIT_NAME = "cloudflare-p1d04-prelive-prep"
_SESSION_RE = re.compile(r"^[1-9][0-9]*[mhd]$")


def _base_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "canonical_issue": CANONICAL_ISSUE,
        "canary": CANARY_ID,
        "result": "BLOCKED",
        "forward_request_attempted": False,
        "forward_request_count": 0,
        "mutation_performed": False,
        "organization": None,
        "rollback": None,
        "privacy": {
            "account_id_emitted": False,
            "api_token_emitted": False,
            "github_token_emitted": False,
            "auth_domain_emitted": False,
            "organization_preimage_emitted": False,
            "intended_payload_emitted": False,
            "response_only_values_emitted": False,
        },
    }


def _preimage_fingerprint(organization: dict[str, Any]) -> str:
    canonical = json.dumps(
        organization,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def execute_prep(
    read_client: CloudflareGetClient,
    account_id: str,
    *,
    collect_organization_fn: Callable[[CloudflareGetClient, str], dict[str, Any]] = collect_organization,
) -> dict[str, Any]:
    report = _base_report()
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        report["reason"] = "missing_or_invalid_account_id"
        return report

    try:
        organization = collect_organization_fn(read_client, account_id)
        plan = build_update_plan(organization)
        if not _SESSION_RE.fullmatch(plan.current_effective_session):
            raise AuditError("global_session_duration_invalid")
        if not _SESSION_RE.fullmatch(TARGET_GLOBAL_SESSION):
            raise AuditError("target_global_session_duration_invalid")
        fingerprint = _preimage_fingerprint(organization)
    except (AuditError, TypeError, ValueError) as exc:
        report["reason"] = str(exc) or "prelive_prep_failed"
        return report

    present_response_only = sum(
        1
        for binding in plan.response_only_binding.values()
        if binding.get("present") is True
    )
    report["organization"] = {
        "preimage_fingerprint": fingerprint,
        "top_level_field_count": len(organization),
        "writable_projection_field_count": len(plan.before_writable),
        "response_only_field_count": present_response_only,
        "known_response_only_field_count": len(RESPONSE_ONLY_FIELDS),
        "current_session_duration": plan.current_effective_session,
        "current_session_source": plan.current_session_source,
        "target_session_duration": TARGET_GLOBAL_SESSION,
        "change_required": True,
        "semantic_diff": ["session_duration"],
    }
    report["rollback"] = {
        "kind": "organization-session-duration",
        "target_session_duration": plan.current_effective_session,
        "automatic": False,
        "fresh_get_required": True,
        "separate_owner_authorization_required": True,
    }
    report["result"] = "PASS"
    return report
