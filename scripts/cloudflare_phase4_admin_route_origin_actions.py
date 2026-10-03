#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from cloudflare_zero_trust_reconcile import (
    ACCOUNT_ID_RE,
    DEFAULT_API_BASE,
    TUNNEL_ID_RE,
    AuditError,
    CloudflareGetClient,
)
from github_p1d04_exact_main_gate import GateError, fetch_and_validate_exact_main

AUDIT_NAME = "phase4-admin-route-origin-getonly"
CANARY_ID = "phase4-admin-route-origin-v1"
CONTRACT_PATH = Path("ops/contracts/admin-zone-verification-v1.json")
EXPECTED_TUNNEL_NAME = "rpi5-tunnel"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_CLASSES = {"lan", "loopback", "other", "unknown"}
ALLOWED_FAILURE_CLASSES = {"permission", "tunnel_lookup", "configuration", "mapping", "binding", "unknown"}
ALLOWED_TUNNEL_LOOKUP_DETAILS = {"http_error", "api_unsuccessful", "request_failed", "response_shape", "ambiguous", "id_invalid", "unknown"}
ALLOWED_TUNNEL_LOOKUP_MATCH_STATES = {"none", "multiple", "unknown"}


def _load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    projections = decoded.get("service_projections")
    selection = decoded.get("admin_service_selection")
    if not isinstance(projections, list) or not isinstance(selection, dict):
        raise AuditError("contract_shape_invalid")
    hostnames = selection.get("expected_hostnames")
    if not isinstance(hostnames, list) or len(hostnames) != 8:
        raise AuditError("contract_host_set_invalid")
    projection_hosts = [
        item.get("hostname")
        for item in projections
        if isinstance(item, dict)
    ]
    if projection_hosts != hostnames:
        raise AuditError("contract_projection_mismatch")
    for item in projections:
        if not isinstance(item, dict):
            raise AuditError("contract_projection_invalid")
        if item.get("expected_origin_class") not in {"lan", "loopback"}:
            raise AuditError("contract_origin_class_invalid")
    return decoded


def _unknown_report(
    contract: dict[str, Any],
    failure_class: str,
    tunnel_lookup_detail: str | None = None,
    tunnel_lookup_match_state: str | None = None,
) -> dict[str, Any]:
    if failure_class not in ALLOWED_FAILURE_CLASSES:
        failure_class = "unknown"
    report: dict[str, Any] = {
        "result": "BLOCKED",
        "failure_class": failure_class,
        "services": [
            {
                "hostname": item["hostname"],
                "route_origin_class": "unknown",
                "result": "UNKNOWN",
            }
            for item in contract["service_projections"]
        ],
    }
    if failure_class == "tunnel_lookup":
        if tunnel_lookup_detail not in ALLOWED_TUNNEL_LOOKUP_DETAILS:
            tunnel_lookup_detail = "unknown"
        report["tunnel_lookup_detail"] = tunnel_lookup_detail
        if tunnel_lookup_detail == "ambiguous":
            if tunnel_lookup_match_state not in ALLOWED_TUNNEL_LOOKUP_MATCH_STATES:
                tunnel_lookup_match_state = "unknown"
            report["tunnel_lookup_match_state"] = tunnel_lookup_match_state
    return report


def _failure_class(stage: str, exc: Exception) -> str:
    if isinstance(exc, AuditError) and str(exc) in {"cloudflare_api_http_401", "cloudflare_api_http_403"}:
        return "permission"
    if stage in {"tunnel_lookup", "configuration", "mapping", "binding"}:
        return stage
    return "unknown"


def _tunnel_lookup_detail(exc: Exception) -> str:
    if not isinstance(exc, AuditError):
        return "unknown"
    reason = str(exc)
    if reason.startswith("cloudflare_api_http_"):
        return "http_error"
    if reason == "cloudflare_api_unsuccessful":
        return "api_unsuccessful"
    if reason == "cloudflare_api_request_failed":
        return "request_failed"
    if reason == "tunnel_list_shape_invalid":
        return "response_shape"
    if reason in {"tunnel_lookup_none", "tunnel_lookup_multiple"}:
        return "ambiguous"
    if reason == "tunnel_id_invalid":
        return "id_invalid"
    return "unknown"


def _tunnel_lookup_match_state(exc: Exception) -> str:
    if not isinstance(exc, AuditError):
        return "unknown"
    reason = str(exc)
    if reason == "tunnel_lookup_none":
        return "none"
    if reason == "tunnel_lookup_multiple":
        return "multiple"
    return "unknown"


def _validate_token(value: str) -> None:
    if len(value) < 20 or len(value) > 4096 or any(ch.isspace() for ch in value):
        raise AuditError("read_token_invalid")


def _list_tunnel(client: CloudflareGetClient, account_id: str) -> str:
    payload = client.get(
        f"/accounts/{account_id}/cfd_tunnel",
        {"name": EXPECTED_TUNNEL_NAME, "is_deleted": "false", "per_page": 100},
    )
    result = payload.get("result")
    if not isinstance(result, list):
        raise AuditError("tunnel_list_shape_invalid")
    matches = [
        item
        for item in result
        if isinstance(item, dict)
        and item.get("name") == EXPECTED_TUNNEL_NAME
        and item.get("config_src") == "cloudflare"
    ]
    if not matches:
        raise AuditError("tunnel_lookup_none")
    if len(matches) > 1:
        raise AuditError("tunnel_lookup_multiple")
    tunnel_id = matches[0].get("id")
    if not isinstance(tunnel_id, str) or not TUNNEL_ID_RE.fullmatch(tunnel_id):
        raise AuditError("tunnel_id_invalid")
    return tunnel_id


def _get_config(
    client: CloudflareGetClient,
    account_id: str,
    tunnel_id: str,
) -> dict[str, Any]:
    payload = client.get(
        f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AuditError("configuration_shape_invalid")
    config = result.get("config")
    if not isinstance(config, dict):
        raise AuditError("configuration_missing")
    return config


def classify_service(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "unknown"
    if value.startswith("http_status:"):
        return "other"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https", "tcp", "ssh", "rdp", "smb"}:
        return "other"
    host = parsed.hostname
    if not isinstance(host, str) or not host:
        return "unknown"
    if host.casefold() == "localhost":
        return "loopback"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "other"
    if address.is_loopback:
        return "loopback"
    if address.is_private:
        return "lan"
    return "other"


def build_report(contract: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    ingress = config.get("ingress")
    if not isinstance(ingress, list):
        raise AuditError("ingress_shape_invalid")

    exact_routes: dict[str, list[dict[str, Any]]] = {}
    for entry in ingress:
        if not isinstance(entry, dict):
            raise AuditError("ingress_entry_invalid")
        hostname = entry.get("hostname")
        if hostname is None:
            continue
        if not isinstance(hostname, str):
            raise AuditError("ingress_hostname_invalid")
        exact_routes.setdefault(hostname.casefold(), []).append(entry)

    services: list[dict[str, Any]] = []
    for projected in contract["service_projections"]:
        hostname = projected["hostname"]
        expected = projected["expected_origin_class"]
        matches = exact_routes.get(hostname.casefold(), [])

        if len(matches) != 1:
            route_class = "unknown"
            result = "UNKNOWN"
        else:
            route_class = classify_service(matches[0].get("service"))
            if route_class not in ALLOWED_CLASSES:
                route_class = "unknown"
            if route_class == expected:
                result = "PASS"
            elif route_class == "unknown":
                result = "UNKNOWN"
            else:
                result = "FAIL"

        services.append({
            "hostname": hostname,
            "route_origin_class": route_class,
            "result": result,
        })

    overall = "PASS" if all(item["result"] == "PASS" for item in services) else "BLOCKED"
    report = {"result": overall, "services": services}
    if overall == "BLOCKED":
        report["failure_class"] = "mapping"
    return report


def main() -> int:
    contract: dict[str, Any] | None = None
    stage = "unknown"
    try:
        contract = _load_contract()
        stage = "binding"
        if os.environ.get("GITHUB_ACTIONS") != "true":
            raise AuditError("github_actions_required")
        if os.environ.get("GITHUB_EVENT_NAME") != "issue_comment":
            raise AuditError("issue_comment_required")
        if os.environ.get("PHASE4_ROUTE_CANARY") != CANARY_ID:
            raise AuditError("canary_binding_invalid")

        expected_sha = os.environ.get("PHASE4_EXPECTED_SHA", "")
        github_sha = os.environ.get("GITHUB_SHA", "")
        if not SHA_RE.fullmatch(expected_sha) or github_sha != expected_sha:
            raise AuditError("exact_main_binding_invalid")
        if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
            raise AuditError("workflow_rerun_forbidden")
        if os.environ.get("CLOUDFLARE_API_BASE"):
            raise AuditError("custom_api_base_forbidden")

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
                raise AuditError("non_phase4_cloudflare_env_forbidden")

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
            raise AuditError("exact_main_gate_failed") from exc
        finally:
            github_token = ""

        account_id = os.environ.pop("CLOUDFLARE_P1D03_ACCOUNT_ID", "")
        read_token = os.environ.pop("CLOUDFLARE_P1D03_READ_API_TOKEN", "")
        try:
            if not ACCOUNT_ID_RE.fullmatch(account_id):
                raise AuditError("account_binding_invalid")
            _validate_token(read_token)
            client = CloudflareGetClient(read_token, DEFAULT_API_BASE)
            stage = "tunnel_lookup"
            tunnel_id = _list_tunnel(client, account_id)
            stage = "configuration"
            config = _get_config(client, account_id, tunnel_id)
            read_token = ""
            account_id = ""
            tunnel_id = ""
            stage = "mapping"
            report = build_report(contract, config)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["result"] == "PASS" else 3
        finally:
            read_token = ""
            account_id = ""
    except (AuditError, json.JSONDecodeError, OSError) as exc:
        failure_class = _failure_class(stage, exc)
        tunnel_lookup_detail = (
            _tunnel_lookup_detail(exc) if failure_class == "tunnel_lookup" else None
        )
        tunnel_lookup_match_state = (
            _tunnel_lookup_match_state(exc)
            if failure_class == "tunnel_lookup" and tunnel_lookup_detail == "ambiguous"
            else None
        )
        if contract is None:
            print(json.dumps({"failure_class": "unknown", "result": "BLOCKED"}, sort_keys=True))
        else:
            print(
                json.dumps(
                    _unknown_report(
                        contract,
                        failure_class,
                        tunnel_lookup_detail,
                        tunnel_lookup_match_state,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
