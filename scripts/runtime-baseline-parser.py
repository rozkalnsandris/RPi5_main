#!/usr/bin/env python3
"""Project fixed read-only command output into the V02B safe TSV schema."""
from __future__ import annotations

import ipaddress
import json
import re
import sys
from typing import Iterable

UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:-]{1,128}\.(?:service|timer)$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,254}$")
INTERFACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}$")
VERSION_RE = re.compile(r"^[vV]?[0-9][A-Za-z0-9.+:_-]{0,63}$")
HEX_ID_RE = re.compile(r"^[0-9a-fA-F]{12,64}$")
ERRORS = (
    ("unsupported_syntax", ("unknown flag", "unknown option", "unsupported", "invalid format", "invalid template", "unrecognized option")),
    ("permission_denied", ("permission denied", "access denied")),
    ("daemon_unreachable", ("cannot connect to the docker daemon", "connection refused", "daemon is not running", "no such file or directory")),
    ("system_bus_unreachable", ("failed to connect to bus", "system has not been booted", "host is down")),
    ("restricted_or_not_permitted", ("operation not permitted", "not permitted", "namespace")),
    ("service_absent", ("not found", "socket_absent")),
)


def has_network_literal(value: str) -> bool:
    for candidate in re.findall(r"[0-9A-Fa-f:.%]+", value):
        candidate = candidate.split("%", 1)[0]
        try:
            ipaddress.ip_address(candidate)
            return True
        except ValueError:
            pass
    return bool(re.search(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", value))


def error_marker(raw: str) -> str | None:
    lower = raw.lower()
    for marker, terms in ERRORS:
        if any(term in lower for term in terms):
            return marker
    return None


def emit(lines: Iterable[str], raw: str) -> None:
    safe_lines = list(lines)
    marker = error_marker(raw)
    if marker and not safe_lines:
        print(f"__runtime_error={marker}")
    for line in safe_lines:
        print(line)


def safe_atom(value: str, pattern: re.Pattern[str] = NAME_RE, default: str = "unknown") -> str:
    value = value.strip()
    if pattern.fullmatch(value) and not has_network_literal(value):
        return value
    return default


def normalized_compose_status(value: str) -> str:
    match = re.search(r"[A-Za-z]+", value)
    if not match:
        return "unknown"
    candidate = match.group(0).lower()
    return candidate if candidate in {"running", "stopped", "exited", "paused", "restarting", "unknown"} else "unknown"


def version(raw: str) -> list[str]:
    for token in re.findall(r"[vV]?[0-9][A-Za-z0-9.+:_-]*", raw):
        if VERSION_RE.fullmatch(token):
            return [f"version\t{token}"]
    return []


def containers(raw: str) -> list[str]:
    rows: set[tuple[str, str, str, str]] = set()
    for line in raw.splitlines():
        fields = line.split("\t")
        if len(fields) != 4:
            continue
        name, image, state, status = (item.strip() for item in fields)
        if not (safe_atom(name) == name and safe_atom(image) == image and not HEX_ID_RE.fullmatch(name) and not HEX_ID_RE.fullmatch(image)):
            continue
        state = state.lower()
        if not re.fullmatch(r"[a-z][a-z_-]{0,31}", state):
            continue
        lower_status = status.lower()
        if "unhealthy" in lower_status:
            health = "unhealthy"
        elif "healthy" in lower_status:
            health = "healthy"
        elif "starting" in lower_status:
            health = "starting"
        elif re.fullmatch(r"[A-Za-z0-9 ():_+.,-]{0,160}", status) and not has_network_literal(status):
            health = "none"
        else:
            health = "unknown"
        rows.add((name, image, state, health))
    return ["\t".join(row) for row in sorted(rows)]


def networks(raw: str) -> list[str]:
    rows: set[tuple[str, str, str]] = set()
    for line in raw.splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        name, driver, scope = (item.strip() for item in fields)
        if all(safe_atom(item) == item and not HEX_ID_RE.fullmatch(item) for item in (name, driver, scope)):
            rows.add((name, driver, scope))
    return ["\t".join(row) for row in sorted(rows)]


def compose_json(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = value if isinstance(value, list) else [value]
    rows: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("Name")
        status = item.get("Status")
        if isinstance(name, str) and isinstance(status, str):
            name = name.strip()
            if safe_atom(name) == name and not HEX_ID_RE.fullmatch(name):
                rows.add((name, normalized_compose_status(status)))
    return ["\t".join(row) for row in sorted(rows)]


def compose_fallback(raw: str) -> list[str]:
    rows: set[tuple[str, str]] = set()
    for line in raw.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        name = fields[0].strip()
        if safe_atom(name) == name and not HEX_ID_RE.fullmatch(name):
            rows.add((name, normalized_compose_status(fields[1])))
    return ["\t".join(row) for row in sorted(rows)]


def system_state(raw: str) -> list[str]:
    states = {"running", "degraded", "maintenance", "starting", "stopping", "initializing", "offline", "unknown"}
    for line in raw.splitlines():
        state = line.strip().lower()
        if state in states:
            return [f"state\t{state}"]
    return []


def enabled_units(raw: str) -> list[str]:
    rows: set[tuple[str, str]] = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) >= 2 and UNIT_RE.fullmatch(fields[0]):
            state = safe_atom(fields[1], re.compile(r"^[a-z][a-z_-]{0,31}$"))
            rows.add((fields[0], state))
    return ["\t".join(row) for row in sorted(rows)]


def failed_units(raw: str) -> list[str]:
    rows: set[tuple[str, str, str, str]] = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) >= 4 and UNIT_RE.fullmatch(fields[0]):
            values = [safe_atom(item, re.compile(r"^[a-z][a-z_-]{0,31}$")) for item in fields[1:4]]
            rows.add((fields[0], *values))
    return ["\t".join(row) for row in sorted(rows)]


def timer_units(raw: str) -> list[str]:
    rows: set[tuple[str, str]] = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) >= 2 and re.fullmatch(r"[A-Za-z0-9@_.:-]{1,128}\.timer", fields[0]):
            rows.add((fields[0], safe_atom(fields[1], re.compile(r"^[a-z][a-z_-]{0,31}$"))))
    return ["\t".join(row) for row in sorted(rows)]


def safe_time(value: str) -> str:
    value = " ".join(value.split())
    if not value or len(value) > 96 or has_network_literal(value):
        return "unknown"
    return value if re.fullmatch(r"[A-Za-z0-9:,+ ._/-]+", value) else "unknown"


def timer_properties(raw: str, expected_id: str) -> list[str]:
    if not re.fullmatch(r"[A-Za-z0-9@_.:-]{1,128}\.timer", expected_id):
        return []
    allowed = {"Id", "LoadState", "ActiveState", "SubState", "Unit", "NextElapseUSecRealtime", "LastTriggerUSec"}
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in allowed:
            values[key] = value
    identifier = values.get("Id", expected_id).strip()
    if identifier != expected_id or not re.fullmatch(r"[A-Za-z0-9@_.:-]{1,128}\.timer", identifier):
        return []
    load = safe_atom(values.get("LoadState", "unknown"), re.compile(r"^[a-z][a-z_-]{0,31}$"))
    active = safe_atom(values.get("ActiveState", "unknown"), re.compile(r"^[a-z][a-z_-]{0,31}$"))
    sub = safe_atom(values.get("SubState", "unknown"), re.compile(r"^[a-z][a-z_-]{0,31}$"))
    activates = values.get("Unit", "unknown").strip()
    if activates != "n/a" and not UNIT_RE.fullmatch(activates):
        activates = "unknown"
    return ["\t".join((identifier, load, active, sub, activates, safe_time(values.get("NextElapseUSecRealtime", "unknown")), safe_time(values.get("LastTriggerUSec", "unknown"))))]


def address_scope(host: str) -> str:
    host = host.strip("[]")
    if host in {"*", "0.0.0.0", "::"}:
        return "wildcard"
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return "unknown"
    if address.is_loopback:
        return "loopback"
    if address.is_private or address.is_link_local:
        return "private_or_local"
    return "specific_other"


def socket_rows(raw: str) -> list[str]:
    rows: set[tuple[str, str, int]] = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        protocol = fields[0].lower()
        if protocol not in {"tcp", "tcp6", "udp", "udp6"}:
            continue
        local = fields[-2] if len(fields) >= 5 else ""
        if local.startswith("["):
            match = re.fullmatch(r"\[([^]]+)\]:(\d+)", local)
            if not match:
                continue
            host, port_text = match.groups()
        elif ":" in local:
            host, port_text = local.rsplit(":", 1)
        else:
            continue
        if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            continue
        rows.add((protocol, address_scope(host), int(port_text)))
    return [f"{protocol}\t{scope}\t{port}" for protocol, scope, port in sorted(rows)]


def scope_name(value: object) -> str:
    return str(value).lower() if str(value).lower() in {"host", "link", "global"} else "other"


def interface_rows_json(raw: str) -> list[str]:
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    rows: set[tuple[str, str, str, str, int, int, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("ifname", "")).strip()
        if not INTERFACE_RE.fullmatch(name):
            continue
        operstate = safe_atom(str(item.get("operstate", "unknown")).lower(), re.compile(r"^[a-z][a-z_-]{0,31}$"))
        link_type = safe_atom(str(item.get("link_type", "unknown")).lower(), re.compile(r"^[a-z][a-z_-]{0,31}$"))
        loopback = "true" if name == "lo" or "LOOPBACK" in item.get("flags", []) else "false"
        ipv4 = ipv6 = 0
        scopes = {"host": 0, "link": 0, "global": 0, "other": 0}
        addresses = item.get("addr_info", [])
        if isinstance(addresses, list):
            for address in addresses:
                if not isinstance(address, dict):
                    continue
                family = address.get("family")
                if family == "inet":
                    ipv4 += 1
                elif family == "inet6":
                    ipv6 += 1
                else:
                    continue
                scopes[scope_name(address.get("scope", "other"))] += 1
        scope_text = ",".join(f"{key}={scopes[key]}" for key in ("host", "link", "global", "other"))
        rows.add((name, operstate, link_type, loopback, ipv4, ipv6, scope_text))
    return ["\t".join(map(str, row)) for row in sorted(rows)]


def interface_rows_fallback(raw: str) -> list[str]:
    rows: set[tuple[str, str, str, str, int, int, str]] = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) < 2 or not INTERFACE_RE.fullmatch(fields[0]):
            continue
        name = fields[0]
        operstate = safe_atom(fields[1].lower(), re.compile(r"^[a-z][a-z_-]{0,31}$"))
        ipv4 = ipv6 = 0
        scopes = {"host": 0, "link": 0, "global": 0, "other": 0}
        for token in fields[2:]:
            address_text = token.split("/", 1)[0].split("%", 1)[0]
            try:
                address = ipaddress.ip_address(address_text)
            except ValueError:
                continue
            if address.version == 4:
                ipv4 += 1
            else:
                ipv6 += 1
            if address.is_loopback:
                scopes["host"] += 1
            elif address.is_link_local:
                scopes["link"] += 1
            elif address.is_global:
                scopes["global"] += 1
            else:
                scopes["other"] += 1
        scope_text = ",".join(f"{key}={scopes[key]}" for key in ("host", "link", "global", "other"))
        rows.add((name, operstate, "unknown", "true" if name == "lo" else "false", ipv4, ipv6, scope_text))
    return ["\t".join(map(str, row)) for row in sorted(rows)]


PARSERS = {
    "docker-version": version,
    "compose-version": version,
    "containers": containers,
    "networks": networks,
    "compose-json": compose_json,
    "compose-fallback": compose_fallback,
    "system-state": system_state,
    "enabled-units": enabled_units,
    "failed-units": failed_units,
    "timer-units": timer_units,
    "sockets": socket_rows,
    "interfaces-json": interface_rows_json,
    "interfaces-fallback": interface_rows_fallback,
}


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        return 2
    mode = sys.argv[1]
    raw = sys.stdin.read()
    if mode == "timer-properties":
        if len(sys.argv) != 3:
            return 2
        lines = timer_properties(raw, sys.argv[2])
    else:
        if len(sys.argv) != 2 or mode not in PARSERS:
            return 2
        lines = PARSERS[mode](raw)
    emit(lines, raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
