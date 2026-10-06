#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    APP_ID_RE,
    DEFAULT_API_BASE,
    AuditError,
    CloudflareGetClient,
    NoRedirect,
)
from phase5_deals_ip_bypass_source_preflight import assess

TARGET_HOSTNAME = "deals.rozkalns.net"
CANARY_ID = "phase5-deals-ip-bypass-remove-v1"
AUDIT_NAME = "phase5-deals-ip-bypass-remove"
CANONICAL_ISSUE = 897
POLICY_ID_RE = APP_ID_RE


class CloudflareAccessPolicyDeleteAttemptError(AuditError):
    """Public-safe failure after the only permitted DELETE was dispatched."""

    def __init__(self, reason: str, mutation_performed: bool | None) -> None:
        super().__init__(reason)
        self.mutation_performed = mutation_performed


@dataclass(frozen=True)
class DeletePlan:
    app_id: str
    policy_id: str
    private_prestate_digest: str


class CloudflareAccessApplicationPolicyDeleteClient:
    """Capability-specific client: one app-specific Access policy DELETE only."""

    def __init__(self, api_token: str, api_base: str = DEFAULT_API_BASE, timeout: int = 20) -> None:
        if len(api_token) < 20 or any(ch.isspace() for ch in api_token):
            raise AuditError("missing_or_invalid_write_api_token")
        parsed = urllib.parse.urlparse(api_base)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise AuditError("invalid_api_base")
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
            raise AuditError("non_https_api_base_forbidden")
        self._api_token = api_token
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout
        self._opener = urllib.request.build_opener(NoRedirect)

    def delete_deals_application_policy(
        self, account_id: str, app_id: str, policy_id: str
    ) -> None:
        if not ACCOUNT_ID_RE.fullmatch(account_id):
            raise AuditError("missing_or_invalid_account_id")
        if not APP_ID_RE.fullmatch(app_id) or not POLICY_ID_RE.fullmatch(policy_id):
            raise AuditError("invalid_delete_target_identity")
        request = urllib.request.Request(
            (
                f"{self._api_base}/accounts/{account_id}/access/apps/"
                f"{app_id}/policies/{policy_id}"
            ),
            method="DELETE",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_token}",
                "User-Agent": "rpi5-main-phase5-deals-ip-bypass-897",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise CloudflareAccessPolicyDeleteAttemptError(
                f"cloudflare_access_policy_delete_http_{exc.code}", None
            ) from exc
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
            raise CloudflareAccessPolicyDeleteAttemptError(
                "cloudflare_access_policy_delete_request_failed", None
            ) from exc
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise CloudflareAccessPolicyDeleteAttemptError(
                "cloudflare_access_policy_delete_response_invalid", None
            ) from exc
        if not isinstance(decoded, dict) or decoded.get("success") is not True:
            raise CloudflareAccessPolicyDeleteAttemptError(
                "cloudflare_access_policy_delete_unsuccessful", None
            )
        result = decoded.get("result")
        if result is not None:
            if not isinstance(result, dict) or result.get("id") not in {None, policy_id}:
                raise CloudflareAccessPolicyDeleteAttemptError(
                    "cloudflare_access_policy_delete_result_mismatch", True
                )


def _unwrap_dict(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AuditError(reason)
    return result


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


def collect_state(client: CloudflareGetClient, account_id: str) -> dict[str, Any]:
    """Collect one complete protected GET-only Access snapshot."""
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        raise AuditError("missing_or_invalid_account_id")
    token = _unwrap_dict(client.get("/user/tokens/verify"), "token_verify_shape_invalid")
    if token.get("status") != "active":
        raise AuditError("read_api_token_not_active")
    organization = _unwrap_dict(
        client.get(f"/accounts/{account_id}/access/organizations"),
        "organization_shape_invalid",
    )
    apps = _list_pages(client, f"/accounts/{account_id}/access/apps")
    policies_by_app: dict[str, list[dict[str, Any]]] = {}
    for app in apps:
        app_id = app.get("id")
        if not isinstance(app_id, str) or not APP_ID_RE.fullmatch(app_id):
            raise AuditError("access_application_id_invalid")
        policies_by_app[app_id] = _list_pages(
            client, f"/accounts/{account_id}/access/apps/{app_id}/policies"
        )
    reusable = _list_pages(client, f"/accounts/{account_id}/access/policies")
    return {
        "inventory_complete": True,
        "organization": organization,
        "apps": apps,
        "policies_by_app": policies_by_app,
        "account_reusable_policies": reusable,
    }


def _action(policy: dict[str, Any]) -> str:
    value = policy.get("decision", policy.get("action"))
    return value.casefold() if isinstance(value, str) else "unknown"


def _rules(policy: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    value = policy.get(phase)
    return value if isinstance(value, list) and all(isinstance(x, dict) for x in value) else []


def _phase_empty(policy: dict[str, Any], phase: str) -> bool:
    return policy.get(phase) in (None, [])


def _family_allow_proven(policies: list[dict[str, Any]]) -> bool:
    candidates = [p for p in policies if _action(p) == "allow"]
    return any(
        bool(include := _rules(policy, "include"))
        and all(set(rule) == {"email"} for rule in include)
        and _phase_empty(policy, "require")
        and _phase_empty(policy, "exclude")
        for policy in candidates
    )


def _service_auth_proven(policies: list[dict[str, Any]]) -> bool:
    candidates = [p for p in policies if _action(p) == "service_auth"]
    return any(
        bool(include := _rules(policy, "include"))
        and all(set(rule) == {"service_token"} for rule in include)
        and _phase_empty(policy, "require")
        and _phase_empty(policy, "exclude")
        for policy in candidates
    )


def _policy_projection(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": policy.get("id"),
        "app_count": policy.get("app_count"),
        "action": _action(policy),
        "precedence": policy.get("precedence"),
        "include": policy.get("include"),
        "require": policy.get("require"),
        "exclude": policy.get("exclude"),
    }


def _app_projection(app: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": app.get("id"),
        "type": app.get("type"),
        "domain": app.get("domain"),
        "destinations": app.get("destinations"),
    }


def _protected_projection(state: dict[str, Any]) -> dict[str, Any]:
    apps = state["apps"]
    policies_by_app = state["policies_by_app"]
    reusable = state["account_reusable_policies"]
    organization = state["organization"]
    return {
        "apps": sorted((_app_projection(app) for app in apps), key=lambda x: str(x["id"])),
        "policies_by_app": {
            app_id: sorted(
                (_policy_projection(p) for p in policies_by_app[app_id]),
                key=lambda x: str(x["id"]),
            )
            for app_id in sorted(policies_by_app)
        },
        "reusable": sorted(
            (_policy_projection(policy) for policy in reusable),
            key=lambda x: str(x["id"]),
        ),
        "strict_service_token_auth": organization.get("strict_service_token_auth"),
    }


def _private_digest(state: dict[str, Any]) -> str:
    encoded = json.dumps(
        _protected_projection(state),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _target(state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    apps = [
        app for app in state["apps"]
        if isinstance(app, dict) and app.get("domain") == TARGET_HOSTNAME
    ]
    if len(apps) != 1:
        raise AuditError("exact_application_not_unique")
    app = apps[0]
    app_id = app.get("id")
    policies = state["policies_by_app"].get(app_id)
    if not isinstance(app_id, str) or not isinstance(policies, list):
        raise AuditError("target_policy_inventory_missing")
    return app, policies


def build_delete_plan(
    state: dict[str, Any], *, expected_main: str, observed_main: str
) -> DeletePlan:
    assessment = assess(
        state,
        expected_main=expected_main,
        observed_main=observed_main,
        service_token_required=True,
    )
    if assessment.get("result") != "SOURCE_ONLY_CANDIDATE":
        raise AuditError(f"source_preflight_blocked:{assessment.get('reason', 'unknown')}")
    app, policies = _target(state)
    if not _family_allow_proven(policies):
        raise AuditError("family_allow_not_strictly_proven")
    if not _service_auth_proven(policies):
        raise AuditError("service_auth_not_strictly_proven")
    if type(state["organization"].get("strict_service_token_auth")) is not bool:
        raise AuditError("strict_service_token_state_unknown")
    bypass = [policy for policy in policies if _action(policy) == "bypass"]
    if len(bypass) != 1:
        raise AuditError("bypass_not_unique")
    app_id = app.get("id")
    policy_id = bypass[0].get("id")
    if not isinstance(app_id, str) or not APP_ID_RE.fullmatch(app_id):
        raise AuditError("target_app_id_invalid")
    if not isinstance(policy_id, str) or not POLICY_ID_RE.fullmatch(policy_id):
        raise AuditError("target_policy_id_invalid")
    return DeletePlan(
        app_id=app_id,
        policy_id=policy_id,
        private_prestate_digest=_private_digest(state),
    )


def verify_post_write(
    before: dict[str, Any], after: dict[str, Any], plan: DeletePlan
) -> dict[str, bool]:
    before_projection = _protected_projection(before)
    after_projection = _protected_projection(after)
    before_apps = before_projection["apps"]
    after_apps = after_projection["apps"]
    if before_apps != after_apps:
        raise AuditError("post_write_application_projection_changed")
    if before_projection["reusable"] != after_projection["reusable"]:
        raise AuditError("post_write_reusable_policy_projection_changed")
    if before_projection["strict_service_token_auth"] != after_projection["strict_service_token_auth"]:
        raise AuditError("post_write_strict_service_token_state_changed")
    if set(before_projection["policies_by_app"]) != set(after_projection["policies_by_app"]):
        raise AuditError("post_write_application_policy_inventory_changed")

    for app_id, before_policies in before_projection["policies_by_app"].items():
        after_policies = after_projection["policies_by_app"][app_id]
        if app_id == plan.app_id:
            expected = [p for p in before_policies if p.get("id") != plan.policy_id]
            if after_policies != expected:
                raise AuditError("post_write_target_policy_diff_unexpected")
        elif after_policies != before_policies:
            raise AuditError("post_write_other_application_policy_changed")

    _app, target_policies = _target(after)
    if any(_action(policy) == "bypass" for policy in target_policies):
        raise AuditError("post_write_bypass_still_present")
    if not _family_allow_proven(target_policies):
        raise AuditError("post_write_family_allow_not_preserved")
    if not _service_auth_proven(target_policies):
        raise AuditError("post_write_service_auth_not_preserved")
    return {
        "target_bypass_absent": True,
        "family_allow_preserved": True,
        "service_auth_preserved": True,
        "other_application_policies_unchanged": True,
        "reusable_policies_unchanged": True,
        "strict_service_token_state_unchanged": True,
    }


def _base_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "canonical_issue": CANONICAL_ISSUE,
        "canary": CANARY_ID,
        "target": TARGET_HOSTNAME,
        "result": "BLOCKED",
        "forward_request_attempted": False,
        "forward_request_count": 0,
        "mutation_performed": False,
        "preflight": None,
        "post_write_proof": None,
        "privacy": {
            "account_id_emitted": False,
            "app_or_policy_id_emitted": False,
            "selector_value_emitted": False,
            "identity_value_emitted": False,
            "api_token_emitted": False,
            "raw_api_payload_emitted": False,
            "private_prestate_digest_emitted": False,
        },
    }


def execute_canary(
    read_client: CloudflareGetClient,
    write_client: CloudflareAccessApplicationPolicyDeleteClient,
    account_id: str,
    *,
    expected_main: str,
    observed_main: str,
    collect_state_fn: Callable[[CloudflareGetClient, str], dict[str, Any]] = collect_state,
) -> dict[str, Any]:
    report = _base_report()
    try:
        before = collect_state_fn(read_client, account_id)
        plan = build_delete_plan(
            before, expected_main=expected_main, observed_main=observed_main
        )
        confirm = collect_state_fn(read_client, account_id)
        confirm_plan = build_delete_plan(
            confirm, expected_main=expected_main, observed_main=observed_main
        )
    except AuditError as exc:
        report["reason"] = str(exc)
        return report

    if (
        plan.private_prestate_digest != confirm_plan.private_prestate_digest
        or plan.app_id != confirm_plan.app_id
        or plan.policy_id != confirm_plan.policy_id
    ):
        report["reason"] = "protected_prestate_drifted_before_delete"
        return report

    report["preflight"] = {
        "exact_target_application": True,
        "legacy_app_specific_ip_bypass_unique": True,
        "reusable_or_shared_policy_absent": True,
        "family_allow_preserved_candidate": True,
        "service_auth_preserved_candidate": True,
        "strict_service_token_state_known": True,
        "protected_prestate_stable_across_double_read": True,
    }
    report["forward_request_attempted"] = True
    report["forward_request_count"] = 1
    try:
        write_client.delete_deals_application_policy(
            account_id, plan.app_id, plan.policy_id
        )
    except CloudflareAccessPolicyDeleteAttemptError as exc:
        report["result"] = "STOP_ERROR"
        report["mutation_performed"] = exc.mutation_performed
        report["reason"] = str(exc)
        return report
    except AuditError as exc:
        report["result"] = "STOP_ERROR"
        report["mutation_performed"] = None
        report["reason"] = str(exc)
        return report

    report["mutation_performed"] = True
    try:
        after = collect_state_fn(read_client, account_id)
        report["post_write_proof"] = verify_post_write(confirm, after, confirm_plan)
    except AuditError as exc:
        report["result"] = "STOP_ERROR"
        report["reason"] = f"post_write_proof_failed:{exc}"
        return report

    report["result"] = "PASS"
    return report
