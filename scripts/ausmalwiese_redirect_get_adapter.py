#!/usr/bin/env python3
"""Source-only, fixed-zone Cloudflare Rulesets GET adapter for issue #996.

NOT installed. This module cannot obtain credentials. A future separately
authorized, root-owned caller must supply an already validated in-memory
read-scoped token and exact zone ID; this file has no CLI or secret reader.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from ausmalwiese_redirect_inventory import PHASE, InventoryBlocked, inspect_redirect_inventory

API_ORIGIN = "https://api.cloudflare.com/client/v4"
ZONE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_BODY_BYTES = 1_000_000
TIMEOUT_SECONDS = 8


class AdapterBlocked(Exception):
    """Stable diagnostic codes only. Do not include token, body or response."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _json_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AdapterBlocked("duplicate_json_field")
        result[key] = value
    return result


def _validate_token(token: str) -> None:
    # No argv, env, stdin or filesystem source: the trusted future launcher
    # must explicitly pass this in memory, after independent owner approval.
    if not isinstance(token, str) or not 16 <= len(token) <= 512:
        raise AdapterBlocked("invalid_in_memory_credential")
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in token):
        raise AdapterBlocked("invalid_in_memory_credential")


class FixedZoneGetAdapter:
    """Only the three fixed GET routes for one zone; no write or redirect API."""

    def __init__(self, zone_id: str, in_memory_read_token: str, *, opener=None):
        if not isinstance(zone_id, str) or ZONE_PATTERN.fullmatch(zone_id) is None:
            raise AdapterBlocked("invalid_zone_identity")
        _validate_token(in_memory_read_token)
        self._zone_id = zone_id
        self._token = in_memory_read_token
        # Ignore environment proxy configuration; do not follow redirects.
        self._opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )
        prefix = f"/zones/{zone_id}"
        self._allowed = frozenset((
            prefix,
            prefix + "/rulesets",
            prefix + f"/rulesets/phases/{PHASE}/entrypoint",
        ))

    def __call__(self, method: str, path: str) -> tuple[int, dict[str, Any]]:
        if method != "GET" or type(path) is not str or path not in self._allowed:
            raise AdapterBlocked("non_allowlisted_request")
        expected_url = API_ORIGIN + path
        request = urllib.request.Request(
            expected_url,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            # Exactly one request per call; urllib redirect handler rejects 30x.
            with self._opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                if response.status != 200 or response.geturl() != expected_url:
                    raise AdapterBlocked("unexpected_response")
                body = response.read(MAX_BODY_BYTES + 1)
        except urllib.error.HTTPError as exc:
            # A 404 is meaningful only for the precise phase endpoint,
            # and only if the inventory core independently verifies absence
            # in the rulesets list. Never read/print an HTTP error body.
            if exc.code == 404 and path.endswith(f"/phases/{PHASE}/entrypoint"):
                return (404, {"success": False})
            raise AdapterBlocked("provider_http_unavailable") from None
        except AdapterBlocked:
            raise
        except Exception:
            raise AdapterBlocked("provider_transport_failed") from None
        if len(body) > MAX_BODY_BYTES:
            raise AdapterBlocked("oversize_response")
        try:
            value = json.loads(body.decode("utf-8"), object_pairs_hook=_json_no_duplicates)
        except AdapterBlocked:
            raise
        except (UnicodeError, ValueError, TypeError):
            raise AdapterBlocked("invalid_provider_json") from None
        if not isinstance(value, dict) or value.get("success") is not True:
            raise AdapterBlocked("invalid_provider_envelope")
        return (200, value)


def sanitized_redirect_inventory(zone_id: str, in_memory_read_token: str, *, opener=None) -> dict[str, Any]:
    """Pure invocation boundary. NOT authorized/installed by source merge."""
    adapter = FixedZoneGetAdapter(zone_id, in_memory_read_token, opener=opener)
    try:
        return inspect_redirect_inventory(adapter, zone_id)
    except InventoryBlocked as exc:
        raise AdapterBlocked(str(exc)) from None


# Intentionally no __main__, argparse, secret-path reader, print or write code.
