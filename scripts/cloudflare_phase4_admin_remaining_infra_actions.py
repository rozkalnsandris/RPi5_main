#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from cloudflare_owner_browser_sso_preflight import collect_state
from cloudflare_phase4_admin_access_scope_actions import build_report as build_access_report
from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    DEFAULT_API_BASE,
    AuditError,
    CloudflareGetClient,
    load_registry,
)
from github_p1d04_exact_main_gate import GateError, fetch_and_validate_exact_main

AUDIT_NAME = "phase4-admin-remaining-infra-external"
CANARY_ID = "phase4-admin-remaining-infra-external-v1"
ISSUE_NUMBER = 819
REPOSITORY = "rozkalnsandris/RPi5_main"
CONTRACT_PATH = Path("ops/contracts/admin-zone-verification-v1.json")
VERIFIER_PATH = Path("ops/contracts/admin-zone-remaining-infra-verifier-v1.json")
REGISTRY_PATH = Path("ops/contracts/ingress-registry-v1.json")
HOST_POLICY_PATH = Path("ops/contracts/cloudflare-hostname-policy.yaml")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ACCESS_REDIRECT_SUFFIX = ".cloudflareaccess.com"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _emit_blocked(reason: str) -> None:
    print(json.dumps({
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "canonical_issue": ISSUE_NUMBER,
        "result": "BLOCKED",
        "mutation_performed": False,
        "reason": reason,
        "privacy": {
            "response_body_read": False,
            "redirect_location_emitted": False,
            "account_id_emitted": False,
            "api_token_emitted": False,
            "app_or_policy_id_emitted": False,
            "cookie_or_identity_material_emitted": False,
            "private_coordinate_emitted": False,
        },
    }, indent=2, sort_keys=True))


def _validate_token(value: str) -> None:
    if len(value) < 20 or len(value) > 4096 or any(ch.isspace() for ch in value):
        raise AuditError("missing_or_invalid_read_api_token")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError("contract_shape_invalid")
    return value


def _load_contracts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    admin = _load_json(CONTRACT_PATH)
    verifier = _load_json(VERIFIER_PATH)
    registry = _load_json(REGISTRY_PATH)

    if admin.get("schema") != "rozkalns.rpi5-main.admin-zone-verification.v1":
        raise AuditError("admin_contract_invalid")
    if verifier.get("schema") != "rozkalns.rpi5-main.phase4-admin-remaining-infra-verifier.v1":
        raise AuditError("remaining_infra_contract_invalid")
    if verifier.get("status") != "source-defined":
        raise AuditError("remaining_infra_contract_invalid")

    selection = admin.get("admin_service_selection")
    projections = admin.get("service_projections")
    services = registry.get("services")
    if not isinstance(selection, dict) or not isinstance(projections, list) or not isinstance(services, list):
        raise AuditError("contract_shape_invalid")

    expected_hosts = selection.get("expected_hostnames")
    if not isinstance(expected_hosts, list) or len(expected_hosts) != 8:
        raise AuditError("admin_host_set_invalid")

    projection_hosts = [item.get("hostname") for item in projections if isinstance(item, dict)]
    if projection_hosts != expected_hosts:
        raise AuditError("admin_projection_order_mismatch")

    admin_registry = [item for item in services if isinstance(item, dict) and item.get("zone") == "ADMIN"]
    if [item.get("hostname") for item in admin_registry] != expected_hosts:
        raise AuditError("registry_admin_set_mismatch")

    return admin, verifier, registry


def _classify_http_status(status: int, location: str | None) -> str:
    if status in {401, 403}:
        return "denied"
    if status in {301, 302, 303, 307, 308} and isinstance(location, str):
        parsed = urllib.parse.urlparse(location)
        host = (parsed.hostname or "").casefold()
        if host == "cloudflareaccess.com" or host.endswith(ACCESS_REDIRECT_SUFFIX):
            return "access-challenge"
    if 200 <= status < 500:
        return "public"
    return "unknown"


def _unauthenticated_class(hostname: str) -> str:
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(
        f"https://{hostname}/",
        method="GET",
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "RPi5-Phase4-Unauthenticated-Check/1",
        },
    )
    try:
        response = opener.open(request, timeout=8)
        try:
            return _classify_http_status(response.status, response.headers.get("Location"))
        finally:
            response.close()
    except urllib.error.HTTPError as exc:
        try:
            return _classify_http_status(exc.code, exc.headers.get("Location"))
        finally:
            exc.close()
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        return "network-error"


def _source_checks(
    admin: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, tuple[bool, bool]]:
    registry_by_id = {
        item.get("service_id"): item
        for item in registry["services"]
        if isinstance(item, dict)
    }
    out: dict[str, tuple[bool, bool]] = {}
    for projected in admin["service_projections"]:
        service_id = projected["service_id"]
        current = registry_by_id.get(service_id)
        owner_matches = (
            isinstance(current, dict)
            and projected.get("runtime_owner") == REPOSITORY
            and current.get("runtime_owner") == REPOSITORY
        )
        recovery_ref = projected.get("recovery_ref")
        recovery_present = (
            isinstance(recovery_ref, str)
            and bool(recovery_ref)
            and not recovery_ref.startswith("/")
            and ".." not in Path(recovery_ref).parts
            and Path(recovery_ref).is_file()
        )
        out[service_id] = (owner_matches, recovery_present)
    return out


def build_report(
    admin: dict[str, Any],
    verifier: dict[str, Any],
    registry: dict[str, Any],
    access_report: dict[str, Any],
    http_classes: dict[str, str],
) -> dict[str, Any]:
    external = verifier.get("external_component")
    if not isinstance(external, dict):
        raise AuditError("remaining_infra_contract_invalid")
    pass_classes = external.get("pass_classes")
    if pass_classes != ["access-challenge", "denied"]:
        raise AuditError("remaining_infra_contract_invalid")

    access_by_host = {
        item.get("hostname"): item
        for item in access_report.get("services", [])
        if isinstance(item, dict)
    }
    source_checks = _source_checks(admin, registry)

    services: list[dict[str, Any]] = []
    for projected in admin["service_projections"]:
        service_id = projected["service_id"]
        hostname = projected["hostname"]
        access_item = access_by_host.get(hostname, {})
        unauthenticated = http_classes.get(hostname, "unknown")
        bypass_present = access_item.get("bypass_present")
        owner_matches, recovery_present = source_checks[service_id]

        passed = (
            unauthenticated in pass_classes
            and bypass_present is False
            and access_item.get("result") == "PASS"
            and owner_matches
            and recovery_present
        )
        result = "PASS" if passed else ("UNKNOWN" if unauthenticated in {"unknown", "network-error"} else "FAIL")

        services.append({
            "service_id": service_id,
            "hostname": hostname,
            "unauthenticated_external_class": unauthenticated,
            "alternate_public_bypass_present": bypass_present if isinstance(bypass_present, bool) else True,
            "runtime_owner_matches": owner_matches,
            "recovery_ref_present": recovery_present,
            "result": result,
        })

    overall = "PASS" if all(item["result"] == "PASS" for item in services) else "BLOCKED"
    return {
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "canonical_issue": ISSUE_NUMBER,
        "verification_class": "unauthenticated-infrastructure",
        "result": overall,
        "mutation_performed": False,
        "services": services,
        "privacy": {
            "response_body_read": False,
            "redirect_location_emitted": False,
            "account_id_emitted": False,
            "api_token_emitted": False,
            "app_or_policy_id_emitted": False,
            "cookie_or_identity_material_emitted": False,
            "private_coordinate_emitted": False,
        },
    }


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        _emit_blocked("github_actions_required")
        return 2
    if os.environ.get("GITHUB_EVENT_NAME") != "issue_comment":
        _emit_blocked("issue_comment_event_required")
        return 2
    if os.environ.get("PHASE4_REMAINING_INFRA_CANARY") != CANARY_ID:
        _emit_blocked("canary_binding_mismatch")
        return 2

    expected_sha = os.environ.get("PHASE4_EXPECTED_SHA", "")
    github_sha = os.environ.get("GITHUB_SHA", "")
    if not SHA_RE.fullmatch(expected_sha) or github_sha != expected_sha:
        _emit_blocked("exact_main_sha_binding_invalid")
        return 2
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        _emit_blocked("workflow_rerun_forbidden")
        return 2
    if os.environ.get("CLOUDFLARE_API_BASE"):
        _emit_blocked("custom_cloudflare_api_base_forbidden")
        return 2

    for forbidden_name in (
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_WRITE_API_TOKEN",
        "CLOUDFLARE_TUNNEL_ACCOUNT_ID",
        "CLOUDFLARE_TUNNEL_API_TOKEN",
        "CLOUDFLARE_P1D04_ACCOUNT_ID",
        "CLOUDFLARE_P1D04_READ_API_TOKEN",
        "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
    ):
        if os.environ.get(forbidden_name):
            _emit_blocked("non_p1d03_cloudflare_env_forbidden")
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
    except GateError:
        github_token = ""
        _emit_blocked("exact_main_gate_failed")
        return 2
    github_token = ""

    account_id = os.environ.pop("CLOUDFLARE_P1D03_ACCOUNT_ID", "")
    read_token = os.environ.pop("CLOUDFLARE_P1D03_READ_API_TOKEN", "")

    try:
        if not ACCOUNT_ID_RE.fullmatch(account_id):
            raise AuditError("missing_or_invalid_account_id")
        _validate_token(read_token)
        admin, verifier, registry_json = _load_contracts()
        registry = load_registry(HOST_POLICY_PATH)
        client = CloudflareGetClient(read_token, DEFAULT_API_BASE)
        state = collect_state(client, account_id)
        read_token = ""
        account_id = ""
        access_report = build_access_report(admin, registry, state)

        http_classes = {
            item["hostname"]: _unauthenticated_class(item["hostname"])
            for item in admin["service_projections"]
        }
        report = build_report(admin, verifier, registry_json, access_report, http_classes)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 3
    except (AuditError, json.JSONDecodeError, OSError) as exc:
        read_token = ""
        account_id = ""
        _emit_blocked(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
