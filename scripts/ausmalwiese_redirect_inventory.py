#!/usr/bin/env python3
"""Fixed-zone Cloudflare Redirect Rules GET-only inventory core (#996).

Source-only. No HTTP client, executable CLI, token handling, filesystem access,
logs or Cloudflare writes. The separately authorized adapter is NOT provided.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

ZONE_NAME = "rozkalns.net"
LEGACY_HOST = "coloring.rozkalns.net"
PHASE = "http_request_dynamic_redirect"
ZONE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
HOST_EQ_RE = re.compile(r'^\s*\(?\s*http\.host\s+eq\s+"([a-z0-9.-]+)"\s*\)?\s*$')
MAX_RULES = 1000
MAX_SERIALIZED_BYTES = 1_000_000


class InventoryBlocked(Exception):
    """Blocked: evidence incomplete or untrusted; never return raw data."""


def _extract(status: Any, payload: Any, label: str) -> Any:
    if type(status) is not int or status != 200 or not isinstance(payload, dict):
        raise InventoryBlocked(label + "_unavailable")
    if payload.get("success") is not True or "result" not in payload:
        raise InventoryBlocked(label + "_invalid")
    return payload["result"]


def _digest(value: Any) -> str:
    try:
        serialized = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, OverflowError):
        raise InventoryBlocked("invalid_inventory_serialization") from None
    if len(serialized) > MAX_SERIALIZED_BYTES:
        raise InventoryBlocked("oversize_inventory")
    return hashlib.sha256(serialized).hexdigest()


def _scope(rule: dict[str, Any]) -> str:
    # Only a FULL anchored host equality can prove exclusion or inclusion.
    # Combined OR, functions, regex, wildcard and path rules are UNKNOWN.
    expression = rule.get("expression")
    if not isinstance(expression, str):
        return "unknown"
    match = HOST_EQ_RE.fullmatch(expression)
    if match is None:
        return "unknown"
    return "legacy_host" if match.group(1) == LEGACY_HOST else "other_exact_host"


def inspect_redirect_inventory(
    read: Callable[[str, str], tuple[int, dict[str, Any]]],
    zone_id: str,
) -> dict[str, Any]:
    """Make exactly three GET-only calls via a future trusted injected adapter.

    This module deliberately supplies NO adapter and NO credential reader.
    Even successful inventory evidence never authorizes a redirect write.
    """
    if not isinstance(zone_id, str) or not ZONE_ID_RE.fullmatch(zone_id):
        raise InventoryBlocked("invalid_zone_identity")

    paths = (
        f"/zones/{zone_id}",
        f"/zones/{zone_id}/rulesets",
        f"/zones/{zone_id}/rulesets/phases/{PHASE}/entrypoint",
    )

    def get(path: str) -> tuple[int, dict[str, Any]]:
        try:
            status, payload = read("GET", path)
        except Exception:
            raise InventoryBlocked("read_only_transport_failed") from None
        if type(status) is not int or not isinstance(payload, dict):
            raise InventoryBlocked("invalid_transport_result")
        return status, payload

    status, payload = get(paths[0])
    zone = _extract(status, payload, "zone")
    if (
        not isinstance(zone, dict)
        or zone.get("id") != zone_id
        or zone.get("name") != ZONE_NAME
        or zone.get("status") != "active"
    ):
        raise InventoryBlocked("zone_mismatch")

    status, payload = get(paths[1])
    listed = _extract(status, payload, "ruleset_list")
    # This fixed three-GET reader must never accept a cursor-truncated list.
    info = payload.get("result_info")
    if info is not None:
        if not isinstance(info, dict):
            raise InventoryBlocked("invalid_ruleset_pagination")
        cursors = info.get("cursors")
        if cursors is not None:
            if not isinstance(cursors, dict):
                raise InventoryBlocked("invalid_ruleset_pagination")
            if cursors.get("after") is not None:
                raise InventoryBlocked("incomplete_ruleset_list")
    if not isinstance(listed, list) or len(listed) > MAX_RULES:
        raise InventoryBlocked("ruleset_list_invalid")
    entrypoint_ids: list[str] = []
    for item in listed:
        if not isinstance(item, dict):
            raise InventoryBlocked("ruleset_list_invalid")
        if item.get("kind") == "zone" and item.get("phase") == PHASE:
            identifier = item.get("id")
            if not isinstance(identifier, str) or not ZONE_ID_RE.fullmatch(identifier):
                raise InventoryBlocked("ruleset_list_invalid")
            entrypoint_ids.append(identifier)
    if len(entrypoint_ids) > 1:
        raise InventoryBlocked("multiple_entrypoints")

    status, payload = get(paths[2])
    if status == 404:
        if entrypoint_ids:
            raise InventoryBlocked("entrypoint_list_disagreement")
        result = {
            "entrypoint": "absent", "rule_count": 0,
            "enabled_count": 0, "disabled_count": 0,
            "active_exact_legacy_positions": [],
            "active_ambiguous_positions": [],
            "other_exact_host_count": 0,
            "disabled_scope_unknown_count": 0,
        }
        inventory_digest = _digest({"list": listed, "entrypoint": None})
    else:
        entry = _extract(status, payload, "entrypoint")
        if (
            not isinstance(entry, dict)
            or entry.get("kind") != "zone"
            or entry.get("phase") != PHASE
            or not isinstance(entry.get("id"), str)
            or not ZONE_ID_RE.fullmatch(entry["id"])
            or entrypoint_ids != [entry["id"]]
            or not isinstance(entry.get("rules"), list)
            or len(entry["rules"]) > MAX_RULES
        ):
            raise InventoryBlocked("entrypoint_mismatch")
        legacy: list[int] = []
        ambiguous: list[int] = []
        other = disabled = disabled_unknown = 0
        for position, rule in enumerate(entry["rules"], 1):
            if not isinstance(rule, dict):
                raise InventoryBlocked("invalid_rule_shape")
            enabled = rule.get("enabled", True)
            if type(enabled) is not bool:
                raise InventoryBlocked("invalid_rule_enabled")
            classification = _scope(rule)
            if not enabled:
                disabled += 1
                if classification == "unknown":
                    disabled_unknown += 1
            elif classification == "legacy_host":
                legacy.append(position)
            elif classification == "other_exact_host":
                other += 1
            else:
                ambiguous.append(position)
        result = {
            "entrypoint": "present",
            "rule_count": len(entry["rules"]),
            "enabled_count": len(entry["rules"]) - disabled,
            "disabled_count": disabled,
            "active_exact_legacy_positions": legacy,
            "active_ambiguous_positions": ambiguous,
            "other_exact_host_count": other,
            "disabled_scope_unknown_count": disabled_unknown,
        }
        inventory_digest = _digest({"list": listed, "entrypoint": entry})

    return {
        "schema": "rozkalns.rpi5-main.redirect-inventory-sanitized.v1",
        "zone_name": ZONE_NAME,
        "phase": PHASE,
        **result,
        "baseline_sha256": inventory_digest,
        "account_level_checked": False,
        "safe_to_apply": False,
    }


# No CLI, direct HTTP calls, network requests, credential handling, or write code.
