#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from cloudflare_owner_browser_sso_preflight import collect_state
from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    DEFAULT_API_BASE,
    AuditError,
    CloudflareGetClient,
    load_registry,
    resolve_application,
)
from github_p1d04_exact_main_gate import GateError, fetch_and_validate_exact_main

AUDIT_NAME = "phase4-admin-access-scope-getonly"
CANARY_ID = "phase4-admin-access-scope-v1"
CONTRACT_PATH = Path("ops/contracts/admin-zone-verification-v1.json")
HOST_POLICY_PATH = Path("ops/contracts/cloudflare-hostname-policy.yaml")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def emit_blocked(reason: str) -> None:
    print(json.dumps({
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "canonical_issue": 819,
        "result": "BLOCKED",
        "mutation_performed": False,
        "reason": reason,
        "privacy": {
            "account_id_emitted": False,
            "api_token_emitted": False,
            "app_or_policy_id_emitted": False,
            "email_or_identity_value_emitted": False,
            "aud_cookie_or_session_emitted": False,
            "raw_api_payload_emitted": False,
        },
    }, indent=2, sort_keys=True))


def _validate_token(value: str) -> None:
    if len(value) < 20 or len(value) > 4096 or any(ch.isspace() for ch in value):
        raise AuditError("missing_or_invalid_read_api_token")


def _policy_action(policy: dict[str, Any]) -> str:
    value = policy.get("decision", policy.get("action"))
    return value.casefold() if isinstance(value, str) else "unknown"


def _rules(policy: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    value = policy.get(phase)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _single_email_allow(policies: list[dict[str, Any]]) -> bool:
    if len(policies) != 1 or _policy_action(policies[0]) != "allow":
        return False
    policy = policies[0]
    include = _rules(policy, "include")
    if len(include) != 1 or set(include[0]) != {"email"}:
        return False
    email_rule = include[0].get("email")
    email_present = (
        isinstance(email_rule, str) and bool(email_rule.strip())
    ) or (
        isinstance(email_rule, dict)
        and isinstance(email_rule.get("email"), str)
        and bool(email_rule["email"].strip())
    )
    return email_present and not _rules(policy, "require") and not _rules(policy, "exclude")


def _application_domains(app: dict[str, Any]) -> list[str]:
    values: list[str] = []
    domain = app.get("domain")
    if isinstance(domain, str) and domain.strip():
        values.append(domain.strip())
    destinations = app.get("destinations")
    if isinstance(destinations, list):
        for item in destinations:
            if isinstance(item, dict):
                uri = item.get("uri")
                if isinstance(uri, str) and uri.strip():
                    values.append(uri.strip())
    return list(dict.fromkeys(values))


def _split_domain(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urllib.parse.urlparse(candidate)
    return (parsed.hostname or "").casefold(), parsed.path or ""


def _root_path(path: str) -> bool:
    return path in {"", "/", "/*"}


def _host_pattern_matches(pattern: str, hostname: str) -> bool:
    labels = pattern.split(".")
    regex_labels = [re.escape(label).replace(r"\*", r"[^.]*") for label in labels]
    regex = r"^" + r"\.".join(regex_labels) + r"$"
    return re.fullmatch(regex, hostname, flags=re.IGNORECASE) is not None


def _application_is_broader_than_admin(
    app: dict[str, Any],
    registry: dict[str, Any],
) -> bool:
    domains = _application_domains(app)
    for raw_domain in domains:
        pattern, path = _split_domain(raw_domain)
        if not pattern or not _root_path(path):
            continue
        for hostname, item in registry.items():
            if item.trust_class == "ADMIN":
                continue
            if _host_pattern_matches(pattern, hostname):
                return True
    return False


def _load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    selection = decoded.get("admin_service_selection")
    projections = decoded.get("service_projections")
    if not isinstance(selection, dict) or not isinstance(projections, list):
        raise AuditError("admin_contract_shape_invalid")
    hostnames = selection.get("expected_hostnames")
    if not isinstance(hostnames, list) or len(hostnames) != 8:
        raise AuditError("admin_contract_host_set_invalid")
    projection_hosts = {
        item.get("hostname")
        for item in projections
        if isinstance(item, dict)
    }
    if set(hostnames) != projection_hosts:
        raise AuditError("admin_contract_projection_mismatch")
    return decoded


def build_report(
    contract: dict[str, Any],
    registry: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    apps = state.get("apps")
    policies_by_app = state.get("policies")
    if not isinstance(apps, list) or not isinstance(policies_by_app, dict):
        raise AuditError("cloudflare_state_shape_invalid")

    services: list[dict[str, Any]] = []
    blockers: list[str] = []

    for projected in contract["service_projections"]:
        hostname = projected["hostname"]
        expected = projected["expected_access_application_scope"]
        resolved = resolve_application(apps, hostname)
        selected = resolved.get("selected")
        bypass_present = False
        scope_class = "unknown"

        if resolved.get("status") == "none":
            scope_class = "missing"
        elif resolved.get("status") == "ambiguous" or not isinstance(selected, dict):
            scope_class = "unknown"
        else:
            app_id = selected.get("id")
            policies = (
                policies_by_app.get(app_id, [])
                if isinstance(app_id, str)
                else []
            )
            bypass_present = any(_policy_action(policy) == "bypass" for policy in policies)
            broader = _application_is_broader_than_admin(selected, registry)

            if broader:
                scope_class = "broader-than-admin"
            elif expected == "exact-owner":
                if resolved.get("status") == "exact" and _single_email_allow(policies):
                    scope_class = "exact-owner"
                elif resolved.get("status") == "wildcard":
                    scope_class = "broader-than-admin"
                else:
                    scope_class = "unknown"
            elif expected == "exact-or-narrow-admin":
                if resolved.get("status") in {"exact", "wildcard"}:
                    scope_class = "exact-or-narrow-admin"
                else:
                    scope_class = "unknown"
            else:
                scope_class = "unknown"

        if scope_class == expected and not bypass_present:
            result = "PASS"
        elif scope_class == "unknown":
            result = "UNKNOWN"
        else:
            result = "FAIL"

        if scope_class != expected:
            blockers.append(f"access_scope_mismatch:{hostname}")
        if bypass_present:
            blockers.append(f"bypass_present:{hostname}")

        services.append({
            "hostname": hostname,
            "access_scope_class": scope_class,
            "bypass_present": bypass_present,
            "result": result,
        })

    overall = "PASS" if all(item["result"] == "PASS" for item in services) else "BLOCKED"
    return {
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "canonical_issue": 819,
        "result": overall,
        "mutation_performed": False,
        "services": services,
        "blockers": sorted(set(blockers)),
        "privacy": {
            "account_id_emitted": False,
            "api_token_emitted": False,
            "app_or_policy_id_emitted": False,
            "email_or_identity_value_emitted": False,
            "aud_cookie_or_session_emitted": False,
            "raw_api_payload_emitted": False,
        },
    }


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        emit_blocked("github_actions_required")
        return 2
    if os.environ.get("GITHUB_EVENT_NAME") != "issue_comment":
        emit_blocked("issue_comment_event_required")
        return 2
    if os.environ.get("PHASE4_CANARY") != CANARY_ID:
        emit_blocked("canary_binding_mismatch")
        return 2

    expected_sha = os.environ.get("PHASE4_EXPECTED_SHA", "")
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

    for forbidden_name in (
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_WRITE_API_TOKEN",
        "CLOUDFLARE_P1D03_OWNER_EMAIL",
        "CLOUDFLARE_P1D04_ACCOUNT_ID",
        "CLOUDFLARE_P1D04_READ_API_TOKEN",
        "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
    ):
        if os.environ.get(forbidden_name):
            emit_blocked("non_phase4_cloudflare_env_forbidden")
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

    account_id = os.environ.pop("CLOUDFLARE_P1D03_ACCOUNT_ID", "")
    read_token = os.environ.pop("CLOUDFLARE_P1D03_READ_API_TOKEN", "")

    try:
        if not ACCOUNT_ID_RE.fullmatch(account_id):
            raise AuditError("missing_or_invalid_account_id")
        _validate_token(read_token)
        contract = _load_contract()
        registry = load_registry(HOST_POLICY_PATH)
        client = CloudflareGetClient(read_token, DEFAULT_API_BASE)
        state = collect_state(client, account_id)
        read_token = ""
        account_id = ""
        report = build_report(contract, registry, state)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 3
    except (AuditError, json.JSONDecodeError, OSError) as exc:
        read_token = ""
        account_id = ""
        emit_blocked(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
