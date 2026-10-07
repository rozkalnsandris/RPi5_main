#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import cloudflare_zero_trust_reconcile as cloudflare
import ingress_drift_host as host

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "ops" / "contracts" / "ingress-registry-v1.json"
AUDIT_PATH = ROOT / "ops" / "contracts" / "ingress-drift-audit-v1.json"
HOSTNAME_POLICY_PATH = ROOT / "ops" / "contracts" / "cloudflare-hostname-policy.yaml"


class AuditError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError("contract_read_failed") from exc
    if not isinstance(value, dict):
        raise AuditError("contract_shape_invalid")
    return value


def _registry_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if registry.get("schema") != "rozkalns.rpi5-main.ingress-registry.v1":
        raise AuditError("registry_invalid")
    services = registry.get("services")
    if not isinstance(services, list) or not services:
        raise AuditError("registry_services_invalid")

    result: dict[str, dict[str, Any]] = {}
    for item in services:
        if not isinstance(item, dict):
            raise AuditError("registry_service_invalid")
        service_id = item.get("service_id")
        hostname = item.get("hostname")
        if not isinstance(service_id, str) or not isinstance(hostname, str):
            raise AuditError("registry_service_identity_invalid")
        if service_id in result:
            raise AuditError("registry_service_duplicate")
        result[service_id] = item
    return result


def _route_class(route: Any) -> str:
    if not isinstance(route, dict):
        return "none"
    value = route.get("origin_class")
    if value == "loopback":
        return "loopback"
    if value == "private-lan":
        return "lan"
    if value in {"other", "unix", "http-status"}:
        return "other"
    return "unknown"


def _relevant_cloudflare_reasons(
    cloudflare_report: dict[str, Any],
    audit: dict[str, Any],
) -> list[str]:
    blockers = cloudflare_report.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        raise AuditError("cloudflare_blockers_invalid")

    cfg = audit.get("cloudflare_component")
    if not isinstance(cfg, dict):
        raise AuditError("cloudflare_contract_invalid")
    prefixes = cfg.get("relevant_blocker_prefixes")
    exact = cfg.get("relevant_blocker_exact")
    if (
        not isinstance(prefixes, list)
        or any(not isinstance(item, str) for item in prefixes)
        or not isinstance(exact, list)
        or any(not isinstance(item, str) for item in exact)
    ):
        raise AuditError("cloudflare_blocker_policy_invalid")

    return sorted(
        {
            item
            for item in blockers
            if item in exact or any(item.startswith(prefix) for prefix in prefixes)
        }
    )


def _cloudflare_drift_codes(reason_codes: list[str]) -> list[str]:
    drift: set[str] = set()
    for reason in reason_codes:
        if reason.startswith(("origin_not_loopback:", "break_glass_origin_not_private_lan:")):
            drift.add("route_origin_class_drift")
        else:
            drift.add("cloudflare_route_inventory_drift")
    return sorted(drift)


def build_report(
    *,
    expected_main: str,
    registry: dict[str, Any],
    audit: dict[str, Any],
    cloudflare_report: dict[str, Any],
    host_report: dict[str, Any],
) -> dict[str, Any]:
    if audit.get("schema") != "rozkalns.rpi5-main.ingress-drift-audit.v1":
        raise AuditError("audit_contract_invalid")
    if cloudflare_report.get("audit") != "phase7-cloudflare-route-reconciliation":
        raise AuditError("cloudflare_report_invalid")
    if cloudflare_report.get("mutation_performed") is not False:
        raise AuditError("cloudflare_report_mutation_invalid")
    if host_report.get("schema") != "rozkalns.rpi5-main.ingress-drift-host-evidence.v1":
        raise AuditError("host_report_invalid")
    if host_report.get("source_main_sha") != expected_main:
        raise AuditError("host_source_sha_mismatch")
    if host_report.get("mutation_performed") is not False:
        raise AuditError("host_report_mutation_invalid")
    if host_report.get("result") not in {"PASS", "DRIFT"}:
        raise AuditError("host_report_result_invalid")

    services = _registry_map(registry)

    cloudflare_rows = cloudflare_report.get("hostnames")
    if not isinstance(cloudflare_rows, list):
        raise AuditError("cloudflare_hostnames_invalid")
    cloudflare_by_hostname: dict[str, dict[str, Any]] = {}
    for item in cloudflare_rows:
        if not isinstance(item, dict) or not isinstance(item.get("hostname"), str):
            raise AuditError("cloudflare_hostname_row_invalid")
        cloudflare_by_hostname[item["hostname"]] = item

    host_rows = host_report.get("services")
    if not isinstance(host_rows, list):
        raise AuditError("host_services_invalid")
    host_by_service: dict[str, dict[str, Any]] = {}
    for item in host_rows:
        if not isinstance(item, dict) or not isinstance(item.get("service_id"), str):
            raise AuditError("host_service_row_invalid")
        host_by_service[item["service_id"]] = item
    if set(host_by_service) != set(services):
        raise AuditError("host_service_set_mismatch")

    reason_codes = _relevant_cloudflare_reasons(cloudflare_report, audit)
    cloudflare_drift = set(_cloudflare_drift_codes(reason_codes))
    output_services: list[dict[str, Any]] = []

    for service_id in sorted(services):
        source = services[service_id]
        hostname = source["hostname"]
        expected_origin = source.get("desired_origin_class")
        if expected_origin not in {"loopback", "lan"}:
            raise AuditError("unsupported_origin_class")

        cloud_row = cloudflare_by_hostname.get(hostname)
        route_class = _route_class(cloud_row.get("route") if cloud_row else None)
        service_drift: set[str] = set(host_by_service[service_id].get("drift_codes", []))

        if route_class == "none":
            service_drift.add("cloudflare_route_inventory_drift")
            cloudflare_drift.add("cloudflare_route_inventory_drift")
        elif route_class != expected_origin:
            service_drift.add("route_origin_class_drift")
            cloudflare_drift.add("route_origin_class_drift")

        host_row = host_by_service[service_id]
        output_services.append(
            {
                "service_id": service_id,
                "hostname": hostname,
                "zone": source["zone"],
                "route_origin_class": route_class,
                "listener_bind_class": host_row["listener_bind_class"],
                "docker_publish_class": host_row["docker_publish_class"],
                "firewall_allow_class": host_row["firewall_allow_class"],
                "drift_codes": sorted(service_drift),
                "result": "PASS" if not service_drift else "DRIFT",
            }
        )

    connector = host_report.get("connector")
    if not isinstance(connector, dict):
        raise AuditError("connector_report_invalid")
    connector_safe = {
        "service_active": connector.get("service_active"),
        "service_enabled": connector.get("service_enabled"),
        "edge_connection_count": connector.get("edge_connection_count"),
        "drift_codes": list(connector.get("drift_codes", [])),
        "result": connector.get("result"),
    }

    cloudflare_safe = {
        "drift_codes": sorted(cloudflare_drift),
        "reason_codes": reason_codes,
        "result": "PASS" if not cloudflare_drift else "DRIFT",
    }
    overall = (
        "PASS"
        if cloudflare_safe["result"] == "PASS"
        and connector_safe["result"] == "PASS"
        and all(item["result"] == "PASS" for item in output_services)
        else "DRIFT"
    )

    return {
        "schema": "rozkalns.rpi5-main.ingress-drift-audit-evidence.v1",
        "schema_version": 1,
        "audit": "phase7-automated-ingress-drift",
        "canonical_issue": 903,
        "source_main_sha": expected_main,
        "mutation_performed": False,
        "cloudflare": cloudflare_safe,
        "connector": connector_safe,
        "services": output_services,
        "result": overall,
        "privacy": {
            "private_addresses_emitted": False,
            "private_subnets_emitted": False,
            "ports_emitted": False,
            "raw_firewall_rules_emitted": False,
            "raw_socket_output_emitted": False,
            "process_identity_emitted": False,
            "container_identity_emitted": False,
            "protected_runtime_content_read": False,
            "cloudflare_identifiers_emitted": False,
            "credential_or_token_material_emitted": False,
        },
    }


def _discover_tunnel_id(
    client: cloudflare.CloudflareGetClient,
    account_id: str,
) -> str:
    payload = client.get(
        f"/accounts/{account_id}/cfd_tunnel",
        {
            "name": cloudflare.EXPECTED_TUNNEL_NAME,
            "is_deleted": "false",
            "per_page": 100,
        },
    )
    result = payload.get("result")
    if not isinstance(result, list):
        raise cloudflare.AuditError("tunnel_list_shape_invalid")
    matches = [
        item
        for item in result
        if isinstance(item, dict)
        and item.get("name") == cloudflare.EXPECTED_TUNNEL_NAME
        and item.get("config_src") == "cloudflare"
    ]
    if len(matches) != 1:
        raise cloudflare.AuditError("tunnel_lookup_ambiguous")
    tunnel_id = matches[0].get("id")
    if not isinstance(tunnel_id, str) or not cloudflare.TUNNEL_ID_RE.fullmatch(tunnel_id):
        raise cloudflare.AuditError("tunnel_id_invalid")
    return tunnel_id


def _collect_cloudflare_report(api_token: str) -> dict[str, Any]:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not cloudflare.ACCOUNT_ID_RE.fullmatch(account_id):
        raise cloudflare.AuditError("missing_or_invalid_account_id")
    if os.environ.get("CLOUDFLARE_TUNNEL_ID"):
        raise cloudflare.AuditError("tunnel_id_env_forbidden")

    registry = cloudflare.load_registry(HOSTNAME_POLICY_PATH)
    client = cloudflare.CloudflareGetClient(api_token)

    token = cloudflare._unwrap_dict(
        client.get(f"/accounts/{account_id}/tokens/verify"),
        "token_verify_shape_invalid",
    )
    if token.get("status") != "active":
        raise cloudflare.AuditError("api_token_not_active")

    tunnel_id = _discover_tunnel_id(client, account_id)
    tunnel = cloudflare._unwrap_dict(
        client.get(f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}"),
        "tunnel_shape_invalid",
    )
    if tunnel.get("name") != cloudflare.EXPECTED_TUNNEL_NAME:
        raise cloudflare.AuditError("tunnel_name_mismatch")
    if tunnel.get("config_src") != "cloudflare":
        raise cloudflare.AuditError("tunnel_not_remotely_managed")

    configuration = cloudflare._unwrap_dict(
        client.get(f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"),
        "tunnel_configuration_shape_invalid",
    )
    config = configuration.get("config")
    if not isinstance(config, dict):
        raise cloudflare.AuditError("tunnel_config_missing")

    api_token = ""
    routes, blockers = cloudflare._build_route_inventory(config, registry, {})
    rows: list[dict[str, Any]] = []

    for hostname, desired in sorted(registry.items()):
        route = routes.get(hostname)
        if desired.delivery == "shared_rpi5_tunnel":
            if desired.audit_route_presence == "present" and route is None:
                blockers.append(f"expected_tunnel_route_missing:{hostname}")
            elif desired.audit_route_presence == "absent" and route is not None:
                blockers.append(f"unexpected_tunnel_route_present:{hostname}")
        elif route is not None:
            blockers.append(f"non_tunnel_delivery_has_tunnel_route:{hostname}")

        if route is not None:
            origin_class = route.get("origin_class")
            if desired.desired_origin_scope == "loopback" and origin_class != "loopback":
                blockers.append(f"origin_not_loopback:{hostname}")
            if (
                desired.desired_origin_scope == "explicit-lan-break-glass"
                and origin_class != "private-lan"
            ):
                blockers.append(f"break_glass_origin_not_private_lan:{hostname}")

        rows.append(
            {
                "hostname": hostname,
                "route": (
                    {"origin_class": route.get("origin_class")}
                    if isinstance(route, dict)
                    else None
                ),
            }
        )

    return {
        "schema_version": 1,
        "audit": "phase7-cloudflare-route-reconciliation",
        "mutation_performed": False,
        "hostnames": rows,
        "blockers": sorted(set(blockers)),
    }


def blocked(expected_main: str, reason: str) -> dict[str, Any]:
    return {
        "schema": "rozkalns.rpi5-main.ingress-drift-audit-evidence.v1",
        "schema_version": 1,
        "audit": "phase7-automated-ingress-drift",
        "canonical_issue": 903,
        "source_main_sha": expected_main,
        "mutation_performed": False,
        "result": "BLOCKED",
        "reason": reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-main", required=True)
    args = parser.parse_args()
    expected_main = args.expected_main
    if len(expected_main) != 40 or any(ch not in "0123456789abcdef" for ch in expected_main):
        print(json.dumps(blocked(expected_main, "expected_main_invalid"), indent=2, sort_keys=True))
        return 2

    try:
        host_report = host.collect_report(expected_main)
        if os.environ.get("CLOUDFLARE_API_TOKEN"):
            raise AuditError("cloudflare_token_env_forbidden")
        token_line = sys.stdin.readline(4097)
        api_token = token_line.rstrip("\r\n")
        token_line = ""
        if (
            len(api_token) < 20
            or len(api_token) > 4096
            or any(ch.isspace() for ch in api_token)
        ):
            raise AuditError("missing_or_invalid_api_token")
        cloudflare_report = _collect_cloudflare_report(api_token)
        api_token = ""
        report = build_report(
            expected_main=expected_main,
            registry=_load_json(REGISTRY_PATH),
            audit=_load_json(AUDIT_PATH),
            cloudflare_report=cloudflare_report,
            host_report=host_report,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 3
    except (
        AuditError,
        cloudflare.AuditError,
        host.AuditError,
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
    ):
        print(
            json.dumps(
                blocked(expected_main, "read_only_ingress_drift_audit_failed"),
                indent=2,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())