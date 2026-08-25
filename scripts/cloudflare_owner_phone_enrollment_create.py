#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from typing import Any, Callable

from cloudflare_owner_phone_preflight import build_report, collect_state, validate_owner_email
from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    APP_ID_RE,
    DEFAULT_API_BASE,
    AuditError,
    CloudflareGetClient,
    NoRedirect,
)

CANARY_ID = "p1d-01a-create-owner-only-enrollment-application"
APPLICATION_NAME = "RPi5 Owner Device Enrollment"
AUDIT_NAME = "cloudflare-p1d01a-owner-enrollment-create"
CANONICAL_ISSUE = 179

_VOLATILE_KEYS = {
    "created_at",
    "updated_at",
    "last_seen",
    "last_seen_at",
    "last_connected_at",
    "last_updated",
}


class CloudflareCreateAttemptError(AuditError):
    """Public-safe failure after the one allowed forward POST was attempted."""

    def __init__(self, reason: str, mutation_performed: bool | None) -> None:
        super().__init__(reason)
        self.mutation_performed = mutation_performed


class CloudflareAccessAppCreateClient:
    """Narrow client exposing only one fixed Access-application create primitive."""

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

    def create_owner_enrollment_application(
        self,
        account_id: str,
        owner_email: str,
    ) -> dict[str, Any]:
        if not ACCOUNT_ID_RE.fullmatch(account_id):
            raise AuditError("missing_or_invalid_account_id")
        payload = build_create_payload(owner_email)
        request = urllib.request.Request(
            f"{self._api_base}/accounts/{account_id}/access/apps",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
                "User-Agent": "rpi5-main-cloudflare-p1d01a-179",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise CloudflareCreateAttemptError(f"cloudflare_create_http_{exc.code}", None) from exc
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
            raise CloudflareCreateAttemptError("cloudflare_create_request_failed", None) from exc

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise CloudflareCreateAttemptError("cloudflare_create_response_invalid", None) from exc
        if not isinstance(decoded, dict) or decoded.get("success") is not True:
            raise CloudflareCreateAttemptError("cloudflare_create_unsuccessful", None)
        result = decoded.get("result")
        if not isinstance(result, dict):
            raise CloudflareCreateAttemptError("cloudflare_create_result_missing", True)
        return result


def build_create_payload(owner_email: str) -> dict[str, Any]:
    owner_email = validate_owner_email(owner_email)
    return {
        "type": "warp",
        "name": APPLICATION_NAME,
        "policies": [
            {
                "name": APPLICATION_NAME,
                "decision": "allow",
                "precedence": 1,
                "include": [{"email": {"email": owner_email}}],
                "require": [],
                "exclude": [],
            }
        ],
    }


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _stable(item)
            for key, item in sorted(value.items())
            if key not in _VOLATILE_KEYS
        }
    if isinstance(value, list):
        items = [_stable(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    return value


def _unrelated_state_snapshot(
    state: dict[str, Any],
    excluded_app_id: str | None = None,
) -> Any:
    apps: list[dict[str, Any]] = []
    for app in state.get("apps", []):
        if not isinstance(app, dict):
            continue
        if excluded_app_id and app.get("id") == excluded_app_id:
            continue
        apps.append(deepcopy(app))

    policies: dict[str, Any] = {}
    raw_policies = state.get("policies", {})
    if isinstance(raw_policies, dict):
        for app_id, app_policies in raw_policies.items():
            if excluded_app_id and app_id == excluded_app_id:
                continue
            policies[str(app_id)] = deepcopy(app_policies)

    return _stable(
        {
            "organization": deepcopy(state.get("organization")),
            "apps": apps,
            "policies": policies,
            "posture": deepcopy(state.get("posture")),
            "registrations": deepcopy(state.get("registrations")),
            "devices": deepcopy(state.get("devices")),
            "default_profile": deepcopy(state.get("default_profile")),
            "custom_profiles": deepcopy(state.get("custom_profiles")),
        }
    )


def _preflight_summary(report: dict[str, Any]) -> dict[str, Any]:
    enrollment = report.get("enrollment") if isinstance(report.get("enrollment"), dict) else {}
    gateway = report.get("gateway_posture") if isinstance(report.get("gateway_posture"), dict) else {}
    owner_device = report.get("owner_device") if isinstance(report.get("owner_device"), dict) else {}
    return {
        "result": report.get("result"),
        "blocker_count": len(report.get("blockers", [])) if isinstance(report.get("blockers"), list) else None,
        "enrollment_application_count": enrollment.get("application_count"),
        "enrollment_application_state": enrollment.get("application_state"),
        "gateway_posture_ready": gateway.get("ready"),
        "owner_android_active_registration_count": owner_device.get(
            "owner_android_active_registration_count"
        ),
    }


def validate_preconditions(report: dict[str, Any]) -> None:
    if report.get("result") != "PASS":
        raise AuditError("fresh_preflight_not_pass")
    blockers = report.get("blockers")
    if not isinstance(blockers, list) or blockers:
        raise AuditError("fresh_preflight_has_blockers")
    enrollment = report.get("enrollment")
    if not isinstance(enrollment, dict):
        raise AuditError("fresh_preflight_enrollment_missing")
    if enrollment.get("application_count") != 0 or enrollment.get("application_state") != "missing":
        raise AuditError("fresh_preflight_enrollment_not_zero")
    remaining = report.get("remaining_gates")
    if not isinstance(remaining, list) or CANARY_ID not in remaining:
        raise AuditError("fresh_preflight_does_not_route_to_p1d01a")


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
        "created_application_attributable": False,
        "preflight": None,
        "post_write_proof": None,
        "privacy": {
            "account_id_emitted": False,
            "owner_email_emitted": False,
            "api_token_emitted": False,
            "access_application_id_emitted": False,
            "access_policy_id_emitted": False,
        },
    }


def execute_canary(
    read_client: CloudflareGetClient,
    write_client: CloudflareAccessAppCreateClient,
    account_id: str,
    owner_email: str,
    *,
    collect_state_fn: Callable[[CloudflareGetClient, str], dict[str, Any]] = collect_state,
    build_report_fn: Callable[[str, dict[str, Any]], dict[str, Any]] = build_report,
) -> dict[str, Any]:
    report = _base_report()
    owner_email = validate_owner_email(owner_email)
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        report["reason"] = "missing_or_invalid_account_id"
        return report

    try:
        before_state = collect_state_fn(read_client, account_id)
        before_report = build_report_fn(owner_email, before_state)
        report["preflight"] = _preflight_summary(before_report)
        validate_preconditions(before_report)
    except AuditError as exc:
        report["reason"] = str(exc)
        return report

    before_unrelated = _unrelated_state_snapshot(before_state)
    report["forward_request_attempted"] = True
    report["forward_request_count"] = 1

    try:
        created = write_client.create_owner_enrollment_application(account_id, owner_email)
    except CloudflareCreateAttemptError as exc:
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
    created_app_id = created.get("id") if isinstance(created, dict) else None
    if not isinstance(created_app_id, str) or not APP_ID_RE.fullmatch(created_app_id):
        report["result"] = "STOP_ERROR"
        report["reason"] = "created_application_attribution_missing"
        return report
    report["created_application_attributable"] = True

    try:
        after_state = collect_state_fn(read_client, account_id)
        after_report = build_report_fn(owner_email, after_state)
    except AuditError as exc:
        report["result"] = "STOP_ERROR"
        report["reason"] = f"post_write_read_failed:{exc}"
        return report

    warp_apps = [
        app for app in after_state.get("apps", [])
        if isinstance(app, dict) and app.get("type") == "warp"
    ]
    created_matches_response = len(warp_apps) == 1 and warp_apps[0].get("id") == created_app_id
    enrollment = after_report.get("enrollment") if isinstance(after_report.get("enrollment"), dict) else {}
    require_types = enrollment.get("require_selector_types")
    exclude_types = enrollment.get("exclude_selector_types")
    unrelated_state_unchanged = before_unrelated == _unrelated_state_snapshot(
        after_state, created_app_id
    )

    report["post_write_proof"] = {
        "enrollment_application_count": enrollment.get("application_count"),
        "enrollment_application_state": enrollment.get("application_state"),
        "owner_only": enrollment.get("owner_only"),
        "owner_exact_email_match": enrollment.get("owner_exact_email_match"),
        "policy_count": enrollment.get("policy_count"),
        "policy_actions": enrollment.get("policy_actions"),
        "require_selector_types": require_types,
        "exclude_selector_types": exclude_types,
        "created_application_matches_response": created_matches_response,
        "unrelated_state_unchanged": unrelated_state_unchanged,
    }

    accepted = (
        after_report.get("result") == "PASS"
        and enrollment.get("application_count") == 1
        and enrollment.get("application_state") == "single"
        and enrollment.get("owner_only") is True
        and enrollment.get("owner_exact_email_match") is True
        and enrollment.get("policy_count") == 1
        and enrollment.get("policy_actions") == ["allow"]
        and require_types == []
        and exclude_types == []
        and created_matches_response
        and unrelated_state_unchanged
    )
    if not accepted:
        report["result"] = "STOP_ERROR"
        report["reason"] = "post_write_proof_failed"
        return report

    report["result"] = "PASS"
    return report
