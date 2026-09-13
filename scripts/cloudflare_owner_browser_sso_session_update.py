#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    DEFAULT_API_BASE,
    AuditError,
    CloudflareGetClient,
    NoRedirect,
)

CANARY_ID = "p1d-04-global-browser-sso-session"
AUDIT_NAME = "cloudflare-p1d04-global-browser-sso-session"
CANONICAL_ISSUE = 179
TARGET_GLOBAL_SESSION = "720h"
DOCUMENTED_DEFAULT_GLOBAL_SESSION = "24h"

WRITABLE_FIELDS = frozenset(
    {
        "allow_authenticate_via_warp",
        "auth_domain",
        "auto_redirect_to_identity",
        "custom_pages",
        "deny_unmatched_requests",
        "deny_unmatched_requests_exempted_zone_names",
        "is_ui_read_only",
        "login_design",
        "mfa_config",
        "mfa_piv_key_requirements",
        "mfa_required_for_all_apps",
        "name",
        "session_duration",
        "ui_read_only_toggle_reason",
        "user_seat_expiration_inactive_time",
        "warp_auth_non_browser_401",
        "warp_auth_session_duration",
    }
)

RESPONSE_ONLY_FIELDS = frozenset(
    {
        "created_at",
        "updated_at",
        "cache_device_posture",
        "has_migrated_private_apps",
        "trusted_accounts",
    }
)

_BOOL_FIELDS = frozenset(
    {
        "allow_authenticate_via_warp",
        "auto_redirect_to_identity",
        "deny_unmatched_requests",
        "is_ui_read_only",
        "mfa_required_for_all_apps",
        "warp_auth_non_browser_401",
    }
)
_STRING_FIELDS = frozenset(
    {
        "auth_domain",
        "name",
        "session_duration",
        "ui_read_only_toggle_reason",
        "user_seat_expiration_inactive_time",
        "warp_auth_session_duration",
    }
)
_DICT_FIELDS = frozenset(
    {
        "custom_pages",
        "login_design",
        "mfa_config",
        "mfa_piv_key_requirements",
    }
)
_STRING_LIST_FIELDS = frozenset({"deny_unmatched_requests_exempted_zone_names"})


class CloudflareOrganizationUpdateAttemptError(AuditError):
    """Public-safe failure after the one allowed PUT was attempted."""

    def __init__(self, reason: str, mutation_performed: bool | None) -> None:
        super().__init__(reason)
        self.mutation_performed = mutation_performed


@dataclass(frozen=True)
class UpdatePlan:
    payload: dict[str, Any]
    before_writable: dict[str, Any]
    response_only_binding: dict[str, dict[str, Any]]
    current_effective_session: str
    current_session_source: str


class CloudflareOrganizationSessionUpdateClient:
    """Narrow client exposing exactly one fixed Organization session PUT."""

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

    def update_global_session(self, account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not ACCOUNT_ID_RE.fullmatch(account_id):
            raise AuditError("missing_or_invalid_account_id")
        _validate_payload(payload)
        request = urllib.request.Request(
            f"{self._api_base}/accounts/{account_id}/access/organizations",
            data=json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"),
            method="PUT",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
                "User-Agent": "rpi5-main-cloudflare-p1d04-179",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise CloudflareOrganizationUpdateAttemptError(
                f"cloudflare_organization_update_http_{exc.code}", None
            ) from exc
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
            raise CloudflareOrganizationUpdateAttemptError(
                "cloudflare_organization_update_request_failed", None
            ) from exc
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise CloudflareOrganizationUpdateAttemptError(
                "cloudflare_organization_update_response_invalid", None
            ) from exc
        if not isinstance(decoded, dict) or decoded.get("success") is not True:
            raise CloudflareOrganizationUpdateAttemptError(
                "cloudflare_organization_update_unsuccessful", None
            )
        result = decoded.get("result")
        if not isinstance(result, dict):
            raise CloudflareOrganizationUpdateAttemptError(
                "cloudflare_organization_update_result_missing", True
            )
        return result


def _unwrap_organization(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AuditError("organization_shape_invalid")
    return result


def collect_organization(client: CloudflareGetClient, account_id: str) -> dict[str, Any]:
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        raise AuditError("missing_or_invalid_account_id")
    return _unwrap_organization(client.get(f"/accounts/{account_id}/access/organizations"))


def _validate_writable_value(key: str, value: Any) -> None:
    if value is None:
        raise AuditError("organization_writable_field_null")
    if key in _BOOL_FIELDS:
        if not isinstance(value, bool):
            raise AuditError("organization_writable_field_type_invalid")
        return
    if key in _STRING_FIELDS:
        if not isinstance(value, str) or not value:
            raise AuditError("organization_writable_field_type_invalid")
        return
    if key in _DICT_FIELDS:
        if not isinstance(value, dict):
            raise AuditError("organization_writable_field_type_invalid")
        return
    if key in _STRING_LIST_FIELDS:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise AuditError("organization_writable_field_type_invalid")
        return
    raise AuditError("organization_writable_field_unclassified")


def _validate_organization_shape(organization: dict[str, Any]) -> None:
    if not isinstance(organization, dict):
        raise AuditError("organization_shape_invalid")
    if any(not isinstance(key, str) for key in organization):
        raise AuditError("organization_response_field_name_invalid")
    unknown = set(organization) - WRITABLE_FIELDS - RESPONSE_ONLY_FIELDS
    if unknown:
        raise AuditError("organization_response_field_unclassified")
    auth_domain = organization.get("auth_domain")
    if not isinstance(auth_domain, str) or not auth_domain:
        raise AuditError("organization_binding_missing")
    for key in WRITABLE_FIELDS.intersection(organization):
        _validate_writable_value(key, organization[key])


def _writable_projection(organization: dict[str, Any]) -> dict[str, Any]:
    _validate_organization_shape(organization)
    return {
        key: deepcopy(organization[key])
        for key in sorted(WRITABLE_FIELDS)
        if key in organization
    }


def _response_only_binding(organization: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _validate_organization_shape(organization)
    return {
        key: {
            "present": key in organization,
            "value": deepcopy(organization.get(key)),
        }
        for key in sorted(RESPONSE_ONLY_FIELDS)
    }


def _effective_session(organization: dict[str, Any]) -> tuple[str, str]:
    if "session_duration" not in organization:
        return DOCUMENTED_DEFAULT_GLOBAL_SESSION, "cloudflare_documented_default"
    value = organization["session_duration"]
    if not isinstance(value, str) or not value:
        raise AuditError("global_session_duration_invalid")
    return value, "api_explicit"


def _semantic_diff(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    keys = set(before) | set(after)
    return {key for key in keys if before.get(key) != after.get(key) or (key in before) != (key in after)}


def build_update_plan(organization: dict[str, Any]) -> UpdatePlan:
    before = _writable_projection(organization)
    current_effective, current_source = _effective_session(organization)
    if current_effective == TARGET_GLOBAL_SESSION:
        raise AuditError("global_session_already_target")
    payload = deepcopy(before)
    payload["session_duration"] = TARGET_GLOBAL_SESSION
    if _semantic_diff(before, payload) != {"session_duration"}:
        raise AuditError("organization_update_diff_not_session_only")
    _validate_payload(payload)
    return UpdatePlan(
        payload=payload,
        before_writable=before,
        response_only_binding=_response_only_binding(organization),
        current_effective_session=current_effective,
        current_session_source=current_source,
    )


def _validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or not payload:
        raise AuditError("organization_update_payload_invalid")
    if set(payload) - WRITABLE_FIELDS:
        raise AuditError("organization_update_payload_contains_nonwritable_field")
    for key, value in payload.items():
        _validate_writable_value(key, value)
    if payload.get("session_duration") != TARGET_GLOBAL_SESSION:
        raise AuditError("organization_update_target_invalid")


def verify_post_write(plan: UpdatePlan, organization: dict[str, Any]) -> dict[str, bool]:
    after = _writable_projection(organization)
    if after.get("session_duration") != TARGET_GLOBAL_SESSION:
        raise AuditError("post_write_global_session_not_target")
    if after != plan.payload:
        raise AuditError("post_write_writable_projection_changed")
    response_only_unchanged = _response_only_binding(organization) == plan.response_only_binding
    if not response_only_unchanged:
        raise AuditError("post_write_response_only_state_changed")
    return {
        "global_session_target_applied": True,
        "writable_projection_matches_intended_payload": True,
        "response_only_fields_unchanged": True,
    }


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
        "preflight": None,
        "post_write_proof": None,
        "privacy": {
            "account_id_emitted": False,
            "auth_domain_emitted": False,
            "api_token_emitted": False,
            "organization_preimage_emitted": False,
            "response_only_values_emitted": False,
        },
    }


def execute_canary(
    read_client: CloudflareGetClient,
    write_client: CloudflareOrganizationSessionUpdateClient,
    account_id: str,
    *,
    collect_organization_fn: Callable[[CloudflareGetClient, str], dict[str, Any]] = collect_organization,
) -> dict[str, Any]:
    report = _base_report()
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        report["reason"] = "missing_or_invalid_account_id"
        return report
    try:
        before = collect_organization_fn(read_client, account_id)
        plan = build_update_plan(before)
    except AuditError as exc:
        report["reason"] = str(exc)
        return report

    report["preflight"] = {
        "organization_binding_present": True,
        "current_effective_session": plan.current_effective_session,
        "current_session_source": plan.current_session_source,
        "target_session": TARGET_GLOBAL_SESSION,
        "writable_field_count": len(plan.before_writable),
        "response_only_field_count": len(plan.response_only_binding),
        "response_only_fields_bound_separately": True,
        "payload_contains_response_only_fields": False,
        "semantic_diff": ["session_duration"],
    }

    report["forward_request_attempted"] = True
    report["forward_request_count"] = 1
    try:
        write_client.update_global_session(account_id, plan.payload)
    except CloudflareOrganizationUpdateAttemptError as exc:
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
        after = collect_organization_fn(read_client, account_id)
        report["post_write_proof"] = verify_post_write(plan, after)
    except AuditError as exc:
        report["result"] = "STOP_ERROR"
        report["reason"] = f"post_write_proof_failed:{exc}"
        return report

    report["result"] = "PASS"
    return report
