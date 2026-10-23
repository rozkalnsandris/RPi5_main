"""Sanitize one fixed Cloudflare Worker script-settings GET (source-only adapter).

The trusted runtime supplies an authenticated, GET-only transport and a pinned
account ID. This module never reads credentials, opens sockets, or manages OAuth.
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable

WORKER_NAME = "coloring-pages-stats-v1"
API_BASE = "https://api.cloudflare.com/client/v4/accounts"
ACCOUNT_ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z")


class ReviewStop(Exception):
    """Expected fail-closed classification; never includes upstream payloads."""


def fixed_url(trusted_account_id: str) -> str:
    """Return exactly the GET URL for the already pinned account and Worker."""
    if not isinstance(trusted_account_id, str) or not ACCOUNT_ID_PATTERN.fullmatch(trusted_account_id):
        raise ReviewStop("account_binding_invalid")
    return (
        f"{API_BASE}/{trusted_account_id}/workers/scripts/"
        f"{WORKER_NAME}/script-settings"
    )


def optional_object(container: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = container.get(key)
    if value is None:
        return None
    if type(value) is not dict:
        raise ReviewStop("unexpected_settings_shape")
    return value


def optional_bool(container: dict[str, Any] | None, key: str) -> bool | None:
    if container is None or container.get(key) is None:
        return None
    value = container[key]
    if type(value) is not bool:
        raise ReviewStop("unexpected_settings_shape")
    return value


def optional_rate(container: dict[str, Any] | None, key: str) -> float | None:
    if container is None or container.get(key) is None:
        return None
    value = container[key]
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ReviewStop("unexpected_settings_shape")
    return float(value)


def optional_destinations_count(container: dict[str, Any] | None) -> int | None:
    if container is None or container.get("destinations") is None:
        return None
    value = container["destinations"]
    if not isinstance(value, list) or len(value) > 128 or any(type(x) is not str for x in value):
        raise ReviewStop("unexpected_settings_shape")
    return len(value)


def sanitize_settings(payload: object) -> dict[str, Any]:
    """Only explicitly listed booleans/rates/counts survive the trust boundary."""
    if type(payload) is not dict or payload.get("success") is not True or payload.get("errors"):
        raise ReviewStop("cloudflare_response_unverified")
    result = payload.get("result")
    if type(result) is not dict:
        raise ReviewStop("cloudflare_response_unverified")
    obs = optional_object(result, "observability")
    logs = optional_object(obs, "logs") if obs is not None else None
    traces = optional_object(obs, "traces") if obs is not None else None
    return {
        "worker": WORKER_NAME,
        "source": "cloudflare-script-settings-get",
        "verified_get": True,
        "logpush": optional_bool(result, "logpush"),
        "observability": {
            "enabled": optional_bool(obs, "enabled"),
            "head_sampling_rate": optional_rate(obs, "head_sampling_rate"),
            "logs": {
                "enabled": optional_bool(logs, "enabled"),
                "invocation_logs": optional_bool(logs, "invocation_logs"),
                "persist": optional_bool(logs, "persist"),
                "redact_query_string": optional_bool(logs, "redact_query_string"),
                "head_sampling_rate": optional_rate(logs, "head_sampling_rate"),
                "destination_count": optional_destinations_count(logs),
            },
            "traces": {
                "enabled": optional_bool(traces, "enabled"),
                "persist": optional_bool(traces, "persist"),
                "head_sampling_rate": optional_rate(traces, "head_sampling_rate"),
                "destination_count": optional_destinations_count(traces),
            },
        },
    }


def collect_once(*, trusted_account_id: str, trusted_get: Callable[[str], object]) -> dict[str, Any]:
    """Call one trusted GET; never retry or expose an upstream error/body."""
    url = fixed_url(trusted_account_id)
    if not callable(trusted_get):
        raise ReviewStop("trusted_get_unavailable")
    try:
        payload = trusted_get(url)
    except Exception:
        raise ReviewStop("trusted_get_failed") from None
    return sanitize_settings(payload)


if __name__ == "__main__":
    raise SystemExit("SOURCE_ONLY: no standalone authentication, GET, or deploy")
