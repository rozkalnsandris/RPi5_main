#!/usr/bin/env python3
"""Pure, offline source preflight for #895. Does not call Cloudflare or authorize writes."""
from __future__ import annotations

import re
from typing import Any

TARGET = "deals.rozkalns.net"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _result(reason: str, *, candidate: bool = False) -> dict[str, Any]:
    """Never expose IDs, selector values, private policy details or live authority."""
    return {
        "audit": "phase5-deals-ip-bypass-source-preflight",
        "result": "SOURCE_ONLY_CANDIDATE" if candidate else "BLOCKED",
        "reason": reason,
        "mutation_authorized": False,
        "cloudflare_requests_performed": 0,
        "identity_or_policy_ids_emitted": False,
    }


def _action(policy: dict[str, Any]) -> str:
    value = policy.get("decision", policy.get("action"))
    return value.casefold() if isinstance(value, str) else "unknown"


def _valid_policy_id(value: Any) -> bool:
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def _validate_application_policy_identities(
    apps: list[dict[str, Any]],
    policies_by_app: dict[str, Any],
) -> str | None:
    """Application-policy list IDs are optional in Cloudflare's schema.

    For this destructive capability, missing/invalid IDs are not normalized into
    a usable candidate: they remain a hard proof gap because cross-application
    sharing cannot be excluded without stable identities.
    """
    for app in apps:
        app_id = app.get("id")
        if not isinstance(app_id, str):
            return "per_application_inventory_incomplete"
        policies = policies_by_app.get(app_id)
        if not isinstance(policies, list):
            return "per_application_inventory_incomplete"
        if any(not isinstance(policy, dict) for policy in policies):
            return "snapshot_shape_invalid"
        if any(not _valid_policy_id(policy.get("id")) for policy in policies):
            return "application_policy_identity_unproven"
    return None


def _reusable_policy_ids(reusable: list[dict[str, Any]]) -> tuple[set[str], str | None]:
    """Normalize documented optional reusable-policy IDs without weakening proof.

    A reusable policy without an ID is harmless only when Cloudflare explicitly
    reports app_count == 0. Missing/invalid ID with unknown or positive app_count
    cannot prove that the Deals candidate is not reusable/shared.
    """
    ids: set[str] = set()
    for policy in reusable:
        if not isinstance(policy, dict):
            return set(), "snapshot_shape_invalid"
        policy_id = policy.get("id")
        if policy_id is None:
            app_count = policy.get("app_count")
            if type(app_count) is int and app_count == 0:
                continue
            return set(), "reusable_policy_identity_unproven"
        if not _valid_policy_id(policy_id):
            return set(), "reusable_policy_identity_unproven"
        ids.add(policy_id)
    return ids, None


def assess(
    state: dict[str, Any],
    *,
    expected_main: str,
    observed_main: str,
    service_token_required: bool | None,
) -> dict[str, Any]:
    """Classify a complete, privately-held fresh GET snapshot; never dispatch a write.

    state is ephemeral caller-supplied data: apps, policies_by_app,
    account_reusable_policies, organization, inventory_complete.
    Never log, serialize or persist the input outside its authorized boundary.
    """
    if not SHA_RE.fullmatch(expected_main) or observed_main != expected_main:
        return _result("exact_main_unproven")
    if type(service_token_required) is not bool:
        return _result("service_token_dependency_unknown")
    if not isinstance(state, dict) or state.get("inventory_complete") is not True:
        return _result("inventory_incomplete")

    apps = state.get("apps")
    policies_by_app = state.get("policies_by_app")
    reusable = state.get("account_reusable_policies")
    organization = state.get("organization")
    if (
        not isinstance(apps, list)
        or not apps
        or any(not isinstance(app, dict) for app in apps)
        or not isinstance(policies_by_app, dict)
        or not isinstance(reusable, list)
        or not isinstance(organization, dict)
    ):
        return _result("snapshot_shape_invalid")

    app_identity_reason = _validate_application_policy_identities(apps, policies_by_app)
    if app_identity_reason is not None:
        return _result(app_identity_reason)

    reusable_ids, reusable_reason = _reusable_policy_ids(reusable)
    if reusable_reason is not None:
        return _result(reusable_reason)

    selected = [app for app in apps if app.get("domain") == TARGET]
    if len(selected) != 1:
        return _result("exact_application_not_unique")
    app = selected[0]
    if app.get("type") != "self_hosted" or app.get("destinations") not in (None, []):
        return _result("application_scope_unproven")

    policies = policies_by_app[app["id"]]
    if not policies:
        return _result("application_policy_identity_unproven")

    ids = [p["id"] for p in policies]
    precedence = [p.get("precedence") for p in policies]
    if (
        len(ids) != len(set(ids))
        or any(type(x) is not int for x in precedence)
        or len(set(precedence)) != len(precedence)
    ):
        return _result("policy_order_ambiguous")

    bypass = [p for p in policies if _action(p) == "bypass"]
    if len(bypass) != 1:
        return _result("bypass_not_unique")
    policy = bypass[0]
    include = policy.get("include")
    if (
        not isinstance(include, list)
        or len(include) != 1
        or not isinstance(include[0], dict)
        or set(include[0]) != {"ip"}
        or not isinstance(include[0]["ip"], dict)
        or not include[0]["ip"]
        or policy.get("require") not in (None, [])
        or policy.get("exclude") not in (None, [])
    ):
        return _result("ip_bypass_scope_unproven")

    if policy["id"] in reusable_ids:
        return _result("reusable_policy_requires_separate_design")
    if any(
        other.get("id") != app["id"]
        and any(p.get("id") == policy["id"] for p in policies_by_app[other["id"]])
        for other in apps
    ):
        return _result("policy_shared_with_other_app")

    human_allow = [
        p
        for p in policies
        if _action(p) == "allow"
        and isinstance(p.get("include"), list)
        and p["include"]
        and all(
            isinstance(rule, dict) and set(rule) == {"email"}
            for rule in p["include"]
        )
    ]
    if not human_allow:
        return _result("family_allow_unproven")

    if service_token_required:
        if type(organization.get("strict_service_token_auth")) is not bool:
            return _result("strict_service_token_state_unknown")
        if not any(_action(p) == "service_auth" for p in policies):
            return _result("service_auth_not_proven")

    return _result("legacy_target_only_preflight_shape", candidate=True)
