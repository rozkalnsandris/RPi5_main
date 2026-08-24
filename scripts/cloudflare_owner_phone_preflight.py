#!/usr/bin/env python3
from __future__ import annotations

import re
from typing import Any, Iterable

from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    APP_ID_RE,
    AuditError,
    CloudflareGetClient,
    resolve_application,
    sanitize_application,
)

OWNER_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DASHBOARD_HOSTNAME = "dash.rozkalns.net"
CONTROL_HOSTNAME = "control.rozkalns.net"


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
        result_info = payload.get("result_info")
        total_pages = result_info.get("total_pages") if isinstance(result_info, dict) else None
        if isinstance(total_pages, int):
            if page >= total_pages:
                return items
        elif len(result) < 100:
            return items
        page += 1
    raise AuditError("cloudflare_page_limit_exceeded")


def _list_cursor(
    client: CloudflareGetClient,
    path: str,
    base_query: dict[str, str | int] | None = None,
) -> list[dict[str, Any]]:
    cursor: str | None = None
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for _ in range(100):
        query: dict[str, str | int] = dict(base_query or {})
        query.setdefault("per_page", 100)
        if cursor:
            query["cursor"] = cursor
        payload = client.get(path, query)
        result = _unwrap_list(payload, "cloudflare_cursor_shape_invalid")
        items.extend(result)
        result_info = payload.get("result_info")
        next_cursor = result_info.get("cursor") if isinstance(result_info, dict) else None
        if not isinstance(next_cursor, str) or not next_cursor:
            return items
        if next_cursor in seen:
            raise AuditError("cloudflare_cursor_repeated")
        seen.add(next_cursor)
        cursor = next_cursor
    raise AuditError("cloudflare_cursor_limit_exceeded")


def collect_state(
    client: CloudflareGetClient,
    account_id: str,
) -> dict[str, Any]:
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

    posture = _unwrap_list(
        client.get(f"/accounts/{account_id}/devices/posture"),
        "device_posture_shape_invalid",
    )
    registrations = _list_cursor(
        client,
        f"/accounts/{account_id}/devices/registrations",
        {"include": "policy", "status": "active"},
    )
    devices = _list_cursor(
        client,
        f"/accounts/{account_id}/devices/physical-devices",
    )
    default_profile = _unwrap_dict(
        client.get(f"/accounts/{account_id}/devices/policy"),
        "default_device_profile_shape_invalid",
    )
    custom_profiles = _unwrap_list(
        client.get(f"/accounts/{account_id}/devices/policies"),
        "device_profiles_shape_invalid",
    )

    return {
        "organization": organization,
        "apps": apps,
        "policies": policies,
        "posture": posture,
        "registrations": registrations,
        "devices": devices,
        "default_profile": default_profile,
        "custom_profiles": custom_profiles,
    }


def _policy_action(policy: dict[str, Any]) -> str:
    action = policy.get("decision", policy.get("action"))
    return action.casefold() if isinstance(action, str) else "unknown"


def _rules(policy: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    value = policy.get(phase)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _selector_types(policies: Iterable[dict[str, Any]], phase: str | None = None) -> set[str]:
    result: set[str] = set()
    phases = (phase,) if phase else ("include", "require", "exclude")
    for policy in policies:
        for current_phase in phases:
            for rule in _rules(policy, current_phase):
                result.update(rule.keys())
    return result


def _email_selector_value(rule: dict[str, Any]) -> str | None:
    value = rule.get("email")
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, dict):
        nested = value.get("email")
        if isinstance(nested, str):
            return nested.strip().casefold()
    return None


def _enrollment_shape(
    apps: list[dict[str, Any]],
    policies_by_app: dict[str, list[dict[str, Any]]],
    owner_email: str,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    warp_apps = [app for app in apps if app.get("type") == "warp"]
    application_count = len(warp_apps)
    application_state = (
        "missing"
        if application_count == 0
        else "single"
        if application_count == 1
        else "ambiguous"
    )
    report: dict[str, Any] = {
        "application_count": application_count,
        "application_state": application_state,
        "policy_count": 0,
        "policy_actions": [],
        "include_selector_types": [],
        "require_selector_types": [],
        "exclude_selector_types": [],
        "owner_exact_email_match": False,
        "owner_only": False,
        "allowed_idp_count": None,
        "auto_redirect_to_identity": None,
    }
    if application_count == 0:
        return report, blockers
    if application_count > 1:
        blockers.append("device_enrollment_application_ambiguous")
        return report, blockers

    app = warp_apps[0]
    app_id = app.get("id")
    if not isinstance(app_id, str):
        blockers.append("device_enrollment_application_id_missing")
        return report, blockers
    policies = policies_by_app.get(app_id, [])
    report["policy_count"] = len(policies)
    report["policy_actions"] = sorted({_policy_action(policy) for policy in policies})
    report["include_selector_types"] = sorted(_selector_types(policies, "include"))
    report["require_selector_types"] = sorted(_selector_types(policies, "require"))
    report["exclude_selector_types"] = sorted(_selector_types(policies, "exclude"))
    allowed_idps = app.get("allowed_idps")
    report["allowed_idp_count"] = len(allowed_idps) if isinstance(allowed_idps, list) else None
    report["auto_redirect_to_identity"] = (
        app.get("auto_redirect_to_identity")
        if isinstance(app.get("auto_redirect_to_identity"), bool)
        else None
    )

    if len(policies) != 1 or _policy_action(policies[0]) != "allow":
        return report, blockers
    policy = policies[0]
    include = _rules(policy, "include")
    require = _rules(policy, "require")
    exclude = _rules(policy, "exclude")
    if len(include) != 1 or set(include[0]) != {"email"}:
        return report, blockers
    report["owner_exact_email_match"] = _email_selector_value(include[0]) == owner_email
    if not report["owner_exact_email_match"] or require or exclude:
        return report, blockers
    report["owner_only"] = True
    return report, blockers


def _gateway_posture_shape(posture: list[dict[str, Any]]) -> dict[str, Any]:
    gateway_rules: list[dict[str, Any]] = []
    for rule in posture:
        if rule.get("type") != "gateway" or rule.get("enabled") is False:
            continue
        match = rule.get("match")
        supports_android = True
        if isinstance(match, list) and match:
            platforms = {
                item.get("platform")
                for item in match
                if isinstance(item, dict) and isinstance(item.get("platform"), str)
            }
            supports_android = "android" in platforms
        if supports_android:
            gateway_rules.append(rule)
    return {
        "enabled_android_gateway_check_count": len(gateway_rules),
        "ready": len(gateway_rules) == 1,
        "ambiguous": len(gateway_rules) > 1,
    }


def _active_registration(registration: dict[str, Any]) -> bool:
    return registration.get("revoked_at") is None and registration.get("deleted_at") is None


def _profile_mode(profile: dict[str, Any] | None) -> str | None:
    if not isinstance(profile, dict):
        return None
    service_mode_v2 = profile.get("service_mode_v2")
    if isinstance(service_mode_v2, dict) and isinstance(service_mode_v2.get("mode"), str):
        return service_mode_v2["mode"].casefold()
    service_mode = profile.get("service_mode")
    return service_mode.casefold() if isinstance(service_mode, str) else None


def _selected_profile(
    registration: dict[str, Any],
    default_profile: dict[str, Any],
    custom_profiles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    policy = registration.get("policy")
    if not isinstance(policy, dict):
        return None
    if policy.get("default") is True:
        return default_profile
    policy_id = policy.get("id")
    if not isinstance(policy_id, str):
        return None
    for profile in custom_profiles:
        candidate = profile.get("policy_id", profile.get("id"))
        if candidate == policy_id:
            return profile
    return None


def _owner_device_shape(
    registrations: list[dict[str, Any]],
    devices: list[dict[str, Any]],
    default_profile: dict[str, Any],
    custom_profiles: list[dict[str, Any]],
    owner_email: str,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    device_map = {
        item.get("id"): item
        for item in devices
        if isinstance(item.get("id"), str) and item.get("deleted_at") is None
    }
    owner_active: list[dict[str, Any]] = []
    owner_android: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for registration in registrations:
        if not _active_registration(registration):
            continue
        user = registration.get("user")
        email = user.get("email") if isinstance(user, dict) else None
        if not isinstance(email, str) or email.strip().casefold() != owner_email:
            continue
        owner_active.append(registration)
        embedded_device = registration.get("device")
        device_id = embedded_device.get("id") if isinstance(embedded_device, dict) else None
        device = device_map.get(device_id)
        if not isinstance(device, dict):
            blockers.append("owner_registration_physical_device_missing")
            continue
        device_type = device.get("device_type")
        if isinstance(device_type, str) and device_type.casefold() == "android":
            owner_android.append((registration, device))

    report: dict[str, Any] = {
        "owner_active_registration_count": len(owner_active),
        "owner_android_active_registration_count": len(owner_android),
        "android_registration_unambiguous": len(owner_android) <= 1,
        "selected_android_profile_mode": None,
        "selected_android_gateway_routing_mode": False,
        "selected_android_tunnel_type_present": False,
        "selected_android_client_version_present": False,
    }
    if len(owner_android) > 1:
        blockers.append("owner_android_registration_ambiguous")
        return report, blockers
    if not owner_android:
        return report, blockers

    registration, _device = owner_android[0]
    profile = _selected_profile(registration, default_profile, custom_profiles)
    mode = _profile_mode(profile)
    report["selected_android_profile_mode"] = mode
    report["selected_android_gateway_routing_mode"] = mode == "warp"
    report["selected_android_tunnel_type_present"] = isinstance(
        registration.get("tunnel_type"), str
    )
    embedded_device = registration.get("device")
    report["selected_android_client_version_present"] = (
        isinstance(embedded_device, dict)
        and isinstance(embedded_device.get("client_version"), str)
        and bool(embedded_device.get("client_version"))
    )
    if profile is None:
        blockers.append("owner_android_device_profile_missing")
    elif mode != "warp":
        blockers.append("owner_android_gateway_routing_mode_not_proven")
    return report, blockers


def _selected_application_summary(
    hostname: str,
    apps: list[dict[str, Any]],
    policies_by_app: dict[str, list[dict[str, Any]]],
    organization: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    resolved = resolve_application(apps, hostname)
    selected = resolved.get("selected")
    policies: list[dict[str, Any]] = []
    sanitized = None
    if isinstance(selected, dict):
        app_id = selected.get("id")
        if isinstance(app_id, str):
            policies = policies_by_app.get(app_id, [])
        sanitized = sanitize_application(selected, policies)
    if resolved.get("status") == "ambiguous":
        blockers.append(f"ambiguous_access_application:{hostname}")

    app_override = (
        selected.get("allow_authenticate_via_warp")
        if isinstance(selected, dict)
        and isinstance(selected.get("allow_authenticate_via_warp"), bool)
        else None
    )
    global_value = organization.get("allow_authenticate_via_warp")
    global_enabled = global_value if isinstance(global_value, bool) else None
    effective = app_override if app_override is not None else global_enabled

    return {
        "resolution": resolved.get("status"),
        "selected_application": sanitized,
        "client_session_auth_override": app_override,
        "client_session_auth_effective": effective,
    }, blockers


def build_report(owner_email: str, state: dict[str, Any]) -> dict[str, Any]:
    owner = validate_owner_email(owner_email)
    organization = state["organization"]
    apps = state["apps"]
    policies_by_app = state["policies"]

    enrollment, blockers = _enrollment_shape(apps, policies_by_app, owner)
    if not isinstance(organization.get("auth_domain"), str) or not organization.get("auth_domain"):
        blockers.append("organization_binding_missing")
    device, device_blockers = _owner_device_shape(
        state["registrations"],
        state["devices"],
        state["default_profile"],
        state["custom_profiles"],
        owner,
    )
    blockers.extend(device_blockers)
    gateway = _gateway_posture_shape(state["posture"])
    if gateway["ambiguous"]:
        blockers.append("multiple_android_gateway_posture_checks")

    dashboard, app_blockers = _selected_application_summary(
        DASHBOARD_HOSTNAME, apps, policies_by_app, organization
    )
    blockers.extend(app_blockers)
    control, control_blockers = _selected_application_summary(
        CONTROL_HOSTNAME, apps, policies_by_app, organization
    )
    blockers.extend(control_blockers)

    if dashboard["resolution"] != "exact":
        blockers.append("dashboard_exact_access_application_missing")

    remaining_gates: list[str] = []
    if enrollment["application_state"] == "missing":
        remaining_gates.append("p1d-01a-create-owner-only-enrollment-application")
    elif enrollment["application_state"] == "single" and not enrollment["owner_only"]:
        remaining_gates.append("p1d-01-owner-only-enrollment-policy")
    if device["owner_android_active_registration_count"] == 0:
        remaining_gates.append("p1d-02-owner-phone-enrollment")
    else:
        remaining_gates.append("p1d-02-owner-phone-enrollment-canary")
    if gateway["enabled_android_gateway_check_count"] == 0:
        remaining_gates.append("p1d-02a-enable-gateway-posture-check")
    remaining_gates.append("p1d-03-dash-require-gateway")

    organization_session = {
        "authenticate_with_cloudflare_one_client_default": (
            organization.get("allow_authenticate_via_warp")
            if isinstance(organization.get("allow_authenticate_via_warp"), bool)
            else None
        ),
        "client_session_duration": (
            organization.get("warp_auth_session_duration")
            if isinstance(organization.get("warp_auth_session_duration"), str)
            else None
        ),
    }

    result = "BLOCKED" if blockers else "PASS"
    return {
        "schema_version": 1,
        "audit": "cloudflare-p1d-owner-phone-readonly-preflight",
        "canonical_issue": 179,
        "result": result,
        "mutation_performed": False,
        "owner_identity_private_input_used": True,
        "organization_binding_present": bool(organization.get("auth_domain")),
        "enrollment": enrollment,
        "owner_device": device,
        "gateway_posture": gateway,
        "access": {
            "dashboard": dashboard,
            "control": control,
        },
        "client_session_beta": organization_session,
        "remaining_gates": remaining_gates,
        "blockers": sorted(set(blockers)),
        "privacy": {
            "owner_email_emitted": False,
            "account_id_emitted": False,
            "device_or_registration_id_emitted": False,
            "device_name_emitted": False,
            "public_key_or_virtual_ip_emitted": False,
            "auth_domain_or_team_name_emitted": False,
        },
    }
