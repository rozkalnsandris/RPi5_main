#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "ops" / "contracts" / "ingress-registry-v1.json"
AUDIT_PATH = ROOT / "ops" / "contracts" / "ingress-drift-audit-v1.json"
ADMIN_TARGETS_PATH = ROOT / "ops" / "contracts" / "admin-zone-remaining-infra-verifier-v1.json"
PRIVATE_TARGETS_PATH = ROOT / "ops" / "contracts" / "private-zone-verification-v1.json"

METRICS_URL = "http://127.0.0.1:20241/metrics"
METRIC_RE = re.compile(
    r"^cloudflared_tunnel_ha_connections(?:\{[^}]*\})?\s+([0-9.eE+-]+)\s*$"
)


class AuditError(RuntimeError):
    pass


def _run(args: list[str]) -> str:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        raise AuditError("read_only_command_failed")
    return proc.stdout


def _capture(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=15,
    )
    return proc.returncode, proc.stdout


def _verify_exact_source(expected_main: str) -> None:
    if _run(["git", "rev-parse", "HEAD"]).strip() != expected_main:
        raise AuditError("exact_main_mismatch")
    for args in (["git", "diff", "--quiet"], ["git", "diff", "--cached", "--quiet"]):
        proc = subprocess.run(
            args,
            cwd=ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        if proc.returncode != 0:
            raise AuditError("tracked_source_dirty")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError("contract_read_failed") from exc
    if not isinstance(value, dict):
        raise AuditError("contract_shape_invalid")
    return value


def _derive_targets(
    registry: dict[str, Any],
    audit: dict[str, Any],
    admin: dict[str, Any],
    private: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if registry.get("schema") != "rozkalns.rpi5-main.ingress-registry.v1":
        raise AuditError("registry_invalid")
    if audit.get("schema") != "rozkalns.rpi5-main.ingress-drift-audit.v1":
        raise AuditError("audit_contract_invalid")

    services = registry.get("services")
    if not isinstance(services, list) or not services:
        raise AuditError("registry_services_invalid")
    registry_map: dict[str, dict[str, Any]] = {}
    for item in services:
        if not isinstance(item, dict):
            raise AuditError("registry_service_invalid")
        service_id = item.get("service_id")
        hostname = item.get("hostname")
        if not isinstance(service_id, str) or not isinstance(hostname, str):
            raise AuditError("registry_service_identity_invalid")
        if service_id in registry_map:
            raise AuditError("registry_service_duplicate")
        registry_map[service_id] = item

    targets: dict[str, dict[str, Any]] = {}

    public_targets = audit.get("host_component", {}).get("public_probe_targets")
    if not isinstance(public_targets, list):
        raise AuditError("public_targets_invalid")
    for item in public_targets:
        if not isinstance(item, dict):
            raise AuditError("public_target_invalid")
        service_id = item.get("service_id")
        port = item.get("probe_port")
        if not isinstance(service_id, str) or not isinstance(port, int):
            raise AuditError("public_target_shape_invalid")
        targets[service_id] = {"probe_port": port}

    admin_targets = admin.get("host_component", {}).get("host_probe_targets")
    if admin_targets is None:
        admin_targets = admin.get("host_probe_targets")
    if not isinstance(admin_targets, list):
        raise AuditError("admin_targets_invalid")
    for item in admin_targets:
        if not isinstance(item, dict):
            raise AuditError("admin_target_invalid")
        service_id = item.get("service_id")
        port = item.get("probe_port")
        if not isinstance(service_id, str) or not isinstance(port, int):
            raise AuditError("admin_target_shape_invalid")
        if service_id in targets:
            raise AuditError("target_duplicate")
        targets[service_id] = {"probe_port": port}

    projections = private.get("service_projections")
    host_cfg = private.get("host_verifier")
    if (
        not isinstance(projections, list)
        or len(projections) != 1
        or not isinstance(projections[0], dict)
        or not isinstance(host_cfg, dict)
    ):
        raise AuditError("private_target_invalid")
    private_id = projections[0].get("service_id")
    private_port = host_cfg.get("probe_port")
    if not isinstance(private_id, str) or not isinstance(private_port, int):
        raise AuditError("private_target_shape_invalid")
    if private_id in targets:
        raise AuditError("target_duplicate")
    targets[private_id] = {"probe_port": private_port}

    if set(targets) != set(registry_map):
        raise AuditError("host_target_set_mismatch")

    result: dict[str, dict[str, Any]] = {}
    for service_id, target in targets.items():
        source = registry_map[service_id]
        port = target["probe_port"]
        if not 1 <= port <= 65535:
            raise AuditError("probe_port_invalid")
        origin = source.get("desired_origin_class")
        break_glass = source.get("lan_break_glass")
        zone = source.get("zone")
        firewall = source.get("firewall_expectation")
        hostname = source.get("hostname")
        if origin not in {"loopback", "lan"}:
            raise AuditError("unsupported_origin_class")
        if break_glass not in {"required", "allowed", "forbidden"}:
            raise AuditError("break_glass_invalid")
        if zone not in {"PUBLIC", "ADMIN", "PRIVATE"}:
            raise AuditError("zone_invalid")
        if not isinstance(hostname, str) or not isinstance(firewall, str):
            raise AuditError("registry_projection_invalid")
        if origin == "loopback" and break_glass != "forbidden":
            raise AuditError("loopback_break_glass_conflict")
        if origin == "lan" and zone != "ADMIN":
            raise AuditError("lan_origin_non_admin")
        result[service_id] = {
            "service_id": service_id,
            "hostname": hostname,
            "zone": zone,
            "desired_origin_class": origin,
            "lan_break_glass": break_glass,
            "firewall_expectation": firewall,
            "probe_port": port,
        }
    return result


def _primary_lan_context() -> tuple[str, str]:
    route = json.loads(_run(["ip", "-j", "-4", "route", "get", "1.1.1.1"]))
    if not isinstance(route, list) or len(route) != 1 or not isinstance(route[0], dict):
        raise AuditError("lan_route_shape_invalid")
    address = route[0].get("prefsrc") or route[0].get("src")
    if not isinstance(address, str) or not address:
        raise AuditError("lan_address_unavailable")

    addresses = json.loads(_run(["ip", "-j", "-4", "addr", "show"]))
    prefixlen: int | None = None
    if isinstance(addresses, list):
        for interface in addresses:
            if not isinstance(interface, dict):
                continue
            for info in interface.get("addr_info", []):
                if (
                    isinstance(info, dict)
                    and info.get("family") == "inet"
                    and info.get("local") == address
                    and isinstance(info.get("prefixlen"), int)
                ):
                    prefixlen = info["prefixlen"]
                    break
            if prefixlen is not None:
                break
    if prefixlen is None:
        raise AuditError("lan_prefix_unavailable")
    network = ipaddress.ip_network(f"{address}/{prefixlen}", strict=False)
    return address, str(network)


def _split_endpoint(value: str) -> tuple[str, int] | None:
    text = value.strip()
    if text.startswith("[") and "]:" in text:
        host, port = text[1:].rsplit("]:", 1)
    elif ":" in text:
        host, port = text.rsplit(":", 1)
    else:
        return None
    try:
        return host, int(port)
    except ValueError:
        return None


def _address_class(address: str, lan_address: str) -> str:
    normalized = address.strip("[]")
    if normalized in {"127.0.0.1", "::1"}:
        return "loopback"
    if normalized in {"0.0.0.0", "::", "*"}:
        return "wildcard"
    if normalized == lan_address:
        return "lan"
    return "other"


def _class_name(classes: set[str]) -> str:
    if not classes:
        return "none"
    return next(iter(classes)) if len(classes) == 1 else "mixed"


def _listeners_by_port(ss_text: str, lan_address: str) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for line in ss_text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        endpoint = _split_endpoint(parts[3])
        if endpoint is None:
            continue
        host, port = endpoint
        result.setdefault(port, set()).add(_address_class(host, lan_address))
    return result


def _docker_publishes_by_port(ports_text: str, lan_address: str) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for line in ports_text.splitlines():
        for raw in line.split(","):
            token = raw.strip()
            if "->" not in token or not token.endswith("/tcp"):
                continue
            left = token.split("->", 1)[0].strip()
            endpoint = _split_endpoint(left)
            if endpoint is None:
                continue
            host, port = endpoint
            result.setdefault(port, set()).add(_address_class(host, lan_address))
    return result


def _firewall_class(
    ufw_text: str,
    *,
    port: int,
    lan_address: str,
    lan_network: str,
) -> str:
    classes: set[str] = set()
    pattern = re.compile(rf"(?<!\d){port}(?:/tcp)?(?!\d)")
    for line in ufw_text.splitlines():
        if "ALLOW" not in line or not pattern.search(line):
            continue
        if "Anywhere" in line or "0.0.0.0/0" in line or "::/0" in line:
            classes.add("broad")
        elif lan_network in line or lan_address in line:
            classes.add("lan-only")
        else:
            classes.add("other")
    return _class_name(classes)


def _connector_edge_connections() -> int | None:
    request = urllib.request.Request(METRICS_URL, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read(2_000_000).decode("utf-8", errors="strict")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, OSError):
        return None

    total = 0.0
    found = False
    for line in body.splitlines():
        match = METRIC_RE.match(line)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except ValueError:
            return None
        total += value
        found = True
    if not found or total < 0 or int(total) != total:
        return None
    return int(total)


def _connector_report(audit: dict[str, Any]) -> dict[str, Any]:
    active_rc, active_out = _capture(["systemctl", "is-active", "cloudflared.service"])
    enabled_rc, enabled_out = _capture(["systemctl", "is-enabled", "cloudflared.service"])
    active = active_rc == 0 and active_out.strip() == "active"
    enabled = enabled_rc == 0 and enabled_out.strip() == "enabled"
    edge_count = _connector_edge_connections()
    expected = audit["host_component"]["expected_connector_edge_connections"]

    drift_codes: list[str] = []
    if not active or not enabled:
        drift_codes.append("cloudflared_service_drift")
    if edge_count != expected:
        drift_codes.append("connector_health_drift")

    return {
        "service_active": active,
        "service_enabled": enabled,
        "edge_connection_count": edge_count,
        "drift_codes": drift_codes,
        "result": "PASS" if not drift_codes else "DRIFT",
    }


def _service_report(
    target: dict[str, Any],
    *,
    listener_classes: set[str],
    docker_classes: set[str],
    firewall_class: str,
) -> dict[str, Any]:
    listener = _class_name(listener_classes)
    docker_publish = _class_name(docker_classes)
    expected = target["desired_origin_class"]
    drift: list[str] = []

    if expected == "loopback":
        if listener != "loopback":
            drift.extend(["expected_loopback_missing", "listener_bind_drift"])
        if docker_publish not in {"none", "loopback"}:
            drift.append("docker_publish_drift")
        if "wildcard" in docker_classes:
            drift.append("unexpected_wildcard_publish")
        if firewall_class != "none":
            drift.append("firewall_exposure_drift")
    else:
        if listener not in {"lan", "wildcard"}:
            drift.extend(["admin_break_glass_missing", "listener_bind_drift"])
        if docker_publish not in {"none", "lan"}:
            drift.append("docker_publish_drift")
        if "wildcard" in docker_classes:
            drift.extend(["unexpected_wildcard_publish", "admin_break_glass_broadened"])
        if firewall_class != "lan-only":
            drift.append("firewall_exposure_drift")
            if firewall_class == "none":
                drift.append("admin_break_glass_missing")
            else:
                drift.append("admin_break_glass_broadened")

    unique = sorted(set(drift))
    return {
        "service_id": target["service_id"],
        "hostname": target["hostname"],
        "zone": target["zone"],
        "listener_bind_class": listener,
        "docker_publish_class": docker_publish,
        "firewall_allow_class": firewall_class,
        "drift_codes": unique,
        "result": "PASS" if not unique else "DRIFT",
    }


def build_report(
    *,
    expected_main: str,
    targets: dict[str, dict[str, Any]],
    listeners: dict[int, set[str]],
    docker_publishes: dict[int, set[str]],
    ufw_text: str,
    lan_address: str,
    lan_network: str,
    connector: dict[str, Any],
) -> dict[str, Any]:
    services: list[dict[str, Any]] = []
    for service_id in sorted(targets):
        target = targets[service_id]
        port = target["probe_port"]
        services.append(
            _service_report(
                target,
                listener_classes=listeners.get(port, set()),
                docker_classes=docker_publishes.get(port, set()),
                firewall_class=_firewall_class(
                    ufw_text,
                    port=port,
                    lan_address=lan_address,
                    lan_network=lan_network,
                ),
            )
        )

    result = (
        "PASS"
        if connector["result"] == "PASS"
        and all(item["result"] == "PASS" for item in services)
        else "DRIFT"
    )
    return {
        "schema": "rozkalns.rpi5-main.ingress-drift-host-evidence.v1",
        "schema_version": 1,
        "audit": "phase7-ingress-drift-host",
        "canonical_issue": 903,
        "source_main_sha": expected_main,
        "mutation_performed": False,
        "connector": connector,
        "services": services,
        "result": result,
        "privacy": {
            "private_addresses_emitted": False,
            "private_subnets_emitted": False,
            "ports_emitted": False,
            "raw_firewall_rules_emitted": False,
            "raw_socket_output_emitted": False,
            "process_identity_emitted": False,
            "container_identity_emitted": False,
            "protected_runtime_content_read": False,
        },
    }


def blocked(expected_main: str, reason: str) -> dict[str, Any]:
    return {
        "schema": "rozkalns.rpi5-main.ingress-drift-host-evidence.v1",
        "schema_version": 1,
        "audit": "phase7-ingress-drift-host",
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
        _verify_exact_source(expected_main)
        registry = _load_json(REGISTRY_PATH)
        audit = _load_json(AUDIT_PATH)
        admin = _load_json(ADMIN_TARGETS_PATH)
        private = _load_json(PRIVATE_TARGETS_PATH)
        targets = _derive_targets(registry, audit, admin, private)
        lan_address, lan_network = _primary_lan_context()
        listeners = _listeners_by_port(_run(["ss", "-H", "-lnt"]), lan_address)
        docker_publishes = _docker_publishes_by_port(
            _run(["docker", "ps", "--format", "{{.Ports}}"]),
            lan_address,
        )
        ufw_text = _run(["sudo", "-n", "ufw", "status", "numbered"])
        if "Status: active" not in ufw_text:
            raise AuditError("ufw_not_active")
        connector = _connector_report(audit)
        report = build_report(
            expected_main=expected_main,
            targets=targets,
            listeners=listeners,
            docker_publishes=docker_publishes,
            ufw_text=ufw_text,
            lan_address=lan_address,
            lan_network=lan_network,
            connector=connector,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 3
    except (AuditError, json.JSONDecodeError, OSError, subprocess.SubprocessError):
        print(
            json.dumps(
                blocked(expected_main, "read_only_host_audit_failed"),
                indent=2,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
