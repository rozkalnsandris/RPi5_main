#!/usr/bin/env python3
from __future__ import annotations

import re
from typing import Any

from cloudflare_zero_trust_reconcile import ACCOUNT_ID_RE, APP_ID_RE, AuditError, CloudflareGetClient, resolve_application

OWNER_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DASHBOARD_HOSTNAME = "dash.rozkalns.net"
TARGET_GLOBAL_SESSION = "720h"


def validate_owner_email(value: str) -> str:
    candidate = value.strip().casefold()
    if len(candidate) > 254 or not OWNER_EMAIL_RE.fullmatch(candidate):
        raise AuditError("missing_or_invalid_owner_email")
    return candidate


def _unwrap_dict(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AuditError(reason)
    return result


def _unwrap_list(payload: dict[str, Any], reason: str) -> list[dict[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
        raise AuditError(reason)
    return result


def _list_pages(client: CloudflareGetClient, path: str) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while page <= 100:
        payload = client.get(path, {"page": page, "per_page": 100})
        result = _unwrap_list(payload, "cloudflare_page_shape_invalid")
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


def collect_state(client: CloudflareGetClient, account_id: str) -> dict[str, Any]:
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        raise AuditError("missing_or_invalid_account_id")
    token = _unwrap_dict(client.get("/user/tokens/verify"), "token_verify_shape_invalid")
    if token.get("status") != "active":
        raise AuditError("api_token_not_active")
    organization = _unwrap_dict(
        client.get(f"/accounts/{account_id}/access/organizations"),
        "organization_shape_invalid",
    )
    apps = _list_pages(client, f"/accounts/{account_id}/access/apps")
    policies: dict[str, list[dict[str, Any]]] = {}
    for app in apps:
        app_id = app.get("id")
        if not isinstance(app_id, str) or not APP_ID_RE.fullmatch(app_id):
            raise AuditError("access_application_id_invalid")
        policies[app_id] = _list_pages(
            client, f"/accounts/{account_id}/access/apps/{app_id}/policies"
        )
    return {"organization": organization, "apps": apps, "policies": policies}


def _rules(policy: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    value = policy.get(phase)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _action(policy: dict[str, Any]) -> str:
    value = policy.get("decision", policy.get("action"))
    return value.casefold() if isinstance(value, str) else "unknown"


def _email_value(rule: dict[str, Any]) -> str | None:
    value = rule.get("email")
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, dict):
        nested = value.get("email")
        if isinstance(nested, str):
            return nested.strip().casefold()
    return None


def _selector_types(policies: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for policy in policies:
        for phase in ("include", "require", "exclude"):
            for rule in _rules(policy, phase):
                result.update(rule.keys())
    return result


def _owner_only_allow(policies: list[dict[str, Any]], owner: str) -> bool:
    if len(policies) != 1 or _action(policies[0]) != "allow":
        return False
    policy = policies[0]
    include = _rules(policy, "include")
    if len(include) != 1 or set(include[0]) != {"email"}:
        return False
    return (
        _email_value(include[0]) == owner
        and not _rules(policy, "require")
        and not _rules(policy, "exclude")
    )


def _dashboard_summary(
    apps: list[dict[str, Any]],
    policies_by_app: dict[str, list[dict[str, Any]]],
    owner: str,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    resolved = resolve_application(apps, DASHBOARD_HOSTNAME)
    selected = resolved.get("selected")
    policies: list[dict[str, Any]] = []
    app_session: str | None = None
    client_session_override: bool | None = None
    if isinstance(selected, dict):
        app_id = selected.get("id")
        if isinstance(app_id, str):
            policies = policies_by_app.get(app_id, [])
        if isinstance(selected.get("session_duration"), str):
            app_session = selected["session_duration"]
        if isinstance(selected.get("allow_authenticate_via_warp"), bool):
            client_session_override = selected["allow_authenticate_via_warp"]
    resolution = resolved.get("status")
    owner_only = _owner_only_allow(policies, owner)
    actions = sorted({_action(policy) for policy in policies})
    selector_types = _selector_types(policies)
    forbidden = sorted(selector_types.intersection({"everyone", "ip", "email_domain", "service_token"}))
    policy_sessions = sorted({
        value for policy in policies
        if isinstance((value := policy.get("session_duration")), str) and value
    })
    if resolution != "exact":
        blockers.append("dashboard_exact_access_application_missing")
    if not owner_only:
        blockers.append("dashboard_exact_owner_allow_policy_not_proven")
    if "bypass" in actions:
        blockers.append("dashboard_bypass_present")
    if forbidden:
        blockers.append("dashboard_broad_or_nonhuman_selector_present")
    return {
        "resolution": resolution,
        "owner_only_allow": owner_only,
        "policy_actions": actions,
        "forbidden_selector_types": forbidden,
        "application_session_duration": app_session,
        "policy_session_durations": policy_sessions,
        "client_session_auth_override": client_session_override,
    }, blockers


def build_report(owner_email: str, state: dict[str, Any]) -> dict[str, Any]:
    owner = validate_owner_email(owner_email)
    organization = state["organization"]
    apps = state["apps"]
    policies = state["policies"]
    blockers: list[str] = []
    if not organization.get("auth_domain"):
        blockers.append("organization_binding_missing")
    current_global = organization.get("session_duration")
    if not isinstance(current_global, str) or not current_global:
        current_global = None
        blockers.append("global_session_duration_missing")
    dashboard, dashboard_blockers = _dashboard_summary(apps, policies, owner)
    blockers.extend(dashboard_blockers)
    change_required = current_global != TARGET_GLOBAL_SESSION
    remaining_gates = [
        "p1d-04-global-browser-sso-session" if change_required else "p1d-05-a55-browser-sso-canary"
    ]
    return {
        "schema_version": 1,
        "audit": "cloudflare-p1d-browser-sso-readonly-preflight",
        "canonical_issue": 179,
        "result": "BLOCKED" if blockers else "PASS",
        "mutation_performed": False,
        "owner_identity_private_input_used": True,
        "organization_binding_present": bool(organization.get("auth_domain")),
        "global_session": {
            "current_duration": current_global,
            "target_duration": TARGET_GLOBAL_SESSION,
            "change_required": change_required,
        },
        "dashboard": dashboard,
        "remaining_gates": remaining_gates,
        "blockers": sorted(set(blockers)),
        "privacy": {
            "owner_email_emitted": False,
            "account_id_emitted": False,
            "auth_domain_or_team_name_emitted": False,
            "access_app_or_policy_id_emitted": False,
            "aud_cookie_jwt_or_token_emitted": False,
        },
    }
