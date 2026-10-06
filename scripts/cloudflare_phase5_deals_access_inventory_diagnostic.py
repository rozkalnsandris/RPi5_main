#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    APP_ID_RE,
    AuditError,
    CloudflareGetClient,
)

TARGET_HOSTNAME = "deals.rozkalns.net"
AUDIT_NAME = "phase5-deals-access-inventory-diagnostic"
CANARY_ID = "phase5-deals-access-inventory-diagnostic-v1"
CANONICAL_ISSUE = 897


def _list_pages(client: CloudflareGetClient, path: str) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while page <= 100:
        payload = client.get(path, {"page": page, "per_page": 100})
        result = payload.get("result")
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise AuditError("cloudflare_page_shape_invalid")
        items.extend(result)
        info = payload.get("result_info")
        total_pages = info.get("total_pages") if isinstance(info, dict) else None
        if isinstance(total_pages, int):
            if page >= total_pages:
                return items
        elif len(result) < 100:
            return items
        page += 1
    raise AuditError("cloudflare_page_limit_exceeded")


def collect_visibility(client: CloudflareGetClient, account_id: str) -> dict[str, Any]:
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        raise AuditError("missing_or_invalid_account_id")

    token = client.get("/user/tokens/verify").get("result")
    if not isinstance(token, dict) or token.get("status") != "active":
        raise AuditError("read_api_token_not_active")

    apps = _list_pages(client, f"/accounts/{account_id}/access/apps")
    valid_ids: list[str] = []
    deals_ids: list[str] = []
    for app in apps:
        app_id = app.get("id")
        if not isinstance(app_id, str) or not APP_ID_RE.fullmatch(app_id):
            raise AuditError("access_application_id_invalid")
        valid_ids.append(app_id)
        if app.get("domain") == TARGET_HOSTNAME:
            deals_ids.append(app_id)

    resolution = "none"
    if len(deals_ids) == 1:
        resolution = "one"
    elif len(deals_ids) > 1:
        resolution = "multiple"

    return {
        "_app_ids": sorted(valid_ids),
        "_deals_ids": sorted(deals_ids),
        "access_apps_visible": bool(apps),
        "deals_app_resolution": resolution,
    }


def build_report(
    *,
    p1d03_account_id: str,
    p1d03: dict[str, Any],
    p1d04_account_id: str,
    p1d04: dict[str, Any],
) -> dict[str, Any]:
    if not ACCOUNT_ID_RE.fullmatch(p1d03_account_id):
        raise AuditError("p1d03_account_binding_invalid")
    if not ACCOUNT_ID_RE.fullmatch(p1d04_account_id):
        raise AuditError("p1d04_account_binding_invalid")

    account_binding_matches = p1d03_account_id == p1d04_account_id
    inventory_matches = p1d03.get("_app_ids") == p1d04.get("_app_ids")
    deals_identity_matches = p1d03.get("_deals_ids") == p1d04.get("_deals_ids")

    p1d03_visible = p1d03.get("access_apps_visible") is True
    p1d04_visible = p1d04.get("access_apps_visible") is True
    p1d03_resolution = p1d03.get("deals_app_resolution")
    p1d04_resolution = p1d04.get("deals_app_resolution")

    reason = "visibility_consistent"
    result = "PASS"
    if not account_binding_matches:
        result = "BLOCKED"
        reason = "p1d03_p1d04_account_binding_mismatch"
    elif not p1d03_visible and not p1d04_visible:
        result = "BLOCKED"
        reason = "both_access_application_inventories_empty"
    elif p1d03_visible and not p1d04_visible:
        result = "BLOCKED"
        reason = "p1d04_access_application_inventory_empty"
    elif not p1d03_visible and p1d04_visible:
        result = "BLOCKED"
        reason = "p1d03_access_application_inventory_empty"
    elif p1d04_resolution == "none":
        result = "BLOCKED"
        reason = "p1d04_deals_application_not_visible"
    elif p1d04_resolution == "multiple":
        result = "BLOCKED"
        reason = "p1d04_deals_application_ambiguous"
    elif p1d03_resolution == "none":
        result = "BLOCKED"
        reason = "p1d03_deals_application_not_visible"
    elif p1d03_resolution == "multiple":
        result = "BLOCKED"
        reason = "p1d03_deals_application_ambiguous"
    elif not inventory_matches:
        result = "BLOCKED"
        reason = "access_application_visibility_differs_between_read_lanes"
    elif not deals_identity_matches:
        result = "BLOCKED"
        reason = "deals_application_identity_differs_between_read_lanes"

    return {
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "canonical_issue": CANONICAL_ISSUE,
        "canary": CANARY_ID,
        "target": TARGET_HOSTNAME,
        "result": result,
        "reason": reason,
        "mutation_performed": False,
        "cloudflare_write_requests_performed": 0,
        "account_binding_matches": account_binding_matches,
        "application_inventory_matches": inventory_matches,
        "deals_application_identity_matches": deals_identity_matches,
        "p1d03": {
            "access_apps_visible": p1d03_visible,
            "deals_app_resolution": p1d03_resolution,
        },
        "p1d04": {
            "access_apps_visible": p1d04_visible,
            "deals_app_resolution": p1d04_resolution,
        },
        "privacy": {
            "account_id_emitted": False,
            "app_id_emitted": False,
            "api_token_emitted": False,
            "raw_api_payload_emitted": False,
            "identity_value_emitted": False,
        },
    }
