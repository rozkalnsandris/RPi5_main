#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://api.cloudflare.com/client/v4"
TUNNEL_NAME = "rpi5-tunnel"
HOSTNAME = "deals.rozkalns.net"
OLD_SERVICE = "http://192.168.0.180:9128"
NEW_SERVICE = "http://127.0.0.1:9128"
EXPECTED_HOSTNAMES = {
    "rozkalns.net",
    "tech.rozkalns.net",
    "deals.rozkalns.net",
    "hermes.rozkalns.net",
    "portainer.rozkalns.net",
    "grafana.rozkalns.net",
    "ha.rozkalns.net",
    "adguard.rozkalns.net",
    "kuma.rozkalns.net",
    "prometheus.rozkalns.net",
}
MODES = {"check", "cutover", "verify-loopback"}


class RouteError(RuntimeError):
    pass


def emit(name: str, value: str) -> None:
    print(f"{name}={value}")


def require_credentials() -> tuple[str, str, str]:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    tunnel_id = os.environ.get("CLOUDFLARE_TUNNEL_ID", "")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")

    if not re.fullmatch(r"[0-9a-fA-F]{32}", account_id):
        raise RouteError("missing_or_invalid_account_id")
    if not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
        tunnel_id,
    ):
        raise RouteError("missing_or_invalid_tunnel_id")
    if len(api_token) < 20 or any(character.isspace() for character in api_token):
        raise RouteError("missing_or_invalid_api_token")
    return account_id, tunnel_id, api_token


def api_request(
    *,
    account_id: str,
    tunnel_id: str,
    api_token: str,
    suffix: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{API_BASE}/accounts/{account_id}/cfd_tunnel/{tunnel_id}{suffix}"
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "rpi5-main-deals-route-61",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RouteError("cloudflare_api_request_failed") from exc

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RouteError("cloudflare_api_unsuccessful")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RouteError("cloudflare_api_result_shape_invalid")
    return payload


def get_tunnel(account_id: str, tunnel_id: str, api_token: str) -> dict[str, Any]:
    payload = api_request(
        account_id=account_id,
        tunnel_id=tunnel_id,
        api_token=api_token,
        suffix="",
    )
    result = payload["result"]
    if result.get("name") != TUNNEL_NAME:
        raise RouteError("tunnel_name_mismatch")
    if result.get("config_src") != "cloudflare":
        raise RouteError("tunnel_is_not_remotely_managed")
    return result


def get_configuration(account_id: str, tunnel_id: str, api_token: str) -> tuple[dict[str, Any], Any]:
    payload = api_request(
        account_id=account_id,
        tunnel_id=tunnel_id,
        api_token=api_token,
        suffix="/configurations",
    )
    result = payload["result"]
    config = result.get("config")
    if not isinstance(config, dict):
        raise RouteError("tunnel_config_missing")
    return config, result.get("version")


def put_configuration(
    account_id: str,
    tunnel_id: str,
    api_token: str,
    config: dict[str, Any],
) -> None:
    api_request(
        account_id=account_id,
        tunnel_id=tunnel_id,
        api_token=api_token,
        suffix="/configurations",
        method="PUT",
        body={"config": config},
    )


def validate_configuration(config: dict[str, Any], expected_service: str) -> int:
    ingress = config.get("ingress")
    if not isinstance(ingress, list) or len(ingress) != 11:
        raise RouteError("unexpected_ingress_count")

    hostname_entries: list[tuple[int, dict[str, Any]]] = []
    catchalls: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(ingress):
        if not isinstance(item, dict):
            raise RouteError("invalid_ingress_entry")
        hostname = item.get("hostname")
        if hostname is None:
            catchalls.append((index, item))
        elif isinstance(hostname, str):
            hostname_entries.append((index, item))
        else:
            raise RouteError("invalid_ingress_hostname")

    if {item["hostname"] for _, item in hostname_entries} != EXPECTED_HOSTNAMES:
        raise RouteError("hostname_set_mismatch")
    if len(hostname_entries) != len(EXPECTED_HOSTNAMES):
        raise RouteError("duplicate_hostname_entry")
    if len(catchalls) != 1:
        raise RouteError("catchall_count_mismatch")
    catchall_index, catchall = catchalls[0]
    if catchall_index != len(ingress) - 1 or catchall.get("service") != "http_status:404":
        raise RouteError("catchall_contract_mismatch")

    target = [(index, item) for index, item in hostname_entries if item["hostname"] == HOSTNAME]
    if len(target) != 1:
        raise RouteError("deals_route_count_mismatch")
    target_index, target_item = target[0]
    if target_item.get("service") != expected_service:
        raise RouteError("deals_origin_mismatch")
    return target_index


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def verify_access_edge() -> None:
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(
        f"https://{HOSTNAME}/",
        method="GET",
        headers={"User-Agent": "rpi5-main-deals-route-61-edge-check"},
    )
    status: int
    location: str
    try:
        with opener.open(request, timeout=20) as response:
            status = response.status
            location = response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        status = exc.code
        location = exc.headers.get("Location", "")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RouteError("access_edge_request_failed") from exc

    if status not in {301, 302, 303, 307, 308}:
        raise RouteError("access_edge_status_mismatch")
    parsed = urllib.parse.urlparse(location)
    redirect_host = (parsed.hostname or "").lower()
    if not redirect_host.endswith(".cloudflareaccess.com"):
        raise RouteError("access_edge_redirect_mismatch")


def rollback(
    account_id: str,
    tunnel_id: str,
    api_token: str,
    original_config: dict[str, Any],
) -> bool:
    try:
        put_configuration(account_id, tunnel_id, api_token, original_config)
        restored, _ = get_configuration(account_id, tunnel_id, api_token)
        if restored != original_config:
            return False
        validate_configuration(restored, OLD_SERVICE)
        verify_access_edge()
        return True
    except RouteError:
        return False


def check_mode(account_id: str, tunnel_id: str, api_token: str, expected_service: str, state: str) -> None:
    get_tunnel(account_id, tunnel_id, api_token)
    config, _ = get_configuration(account_id, tunnel_id, api_token)
    validate_configuration(config, expected_service)
    verify_access_edge()
    emit("RESULT", "PASS")
    emit("MODE", "check" if state == "LAN" else "verify-loopback")
    emit("ROUTE_STATE", state)
    emit("ACCESS_EDGE", "PASS")
    emit("CONFIG_MUTATED", "false")


def cutover_mode(account_id: str, tunnel_id: str, api_token: str) -> None:
    get_tunnel(account_id, tunnel_id, api_token)
    original_config, original_version = get_configuration(account_id, tunnel_id, api_token)
    target_index = validate_configuration(original_config, OLD_SERVICE)
    verify_access_edge()

    # Repeat the remote preflight immediately before the write to narrow the drift window.
    latest_config, latest_version = get_configuration(account_id, tunnel_id, api_token)
    if latest_config != original_config or latest_version != original_version:
        raise RouteError("configuration_changed_during_preflight")
    target_index = validate_configuration(latest_config, OLD_SERVICE)

    desired_config = copy.deepcopy(latest_config)
    desired_config["ingress"][target_index]["service"] = NEW_SERVICE
    proof = copy.deepcopy(desired_config)
    proof["ingress"][target_index]["service"] = OLD_SERVICE
    if proof != latest_config:
        raise RouteError("mutation_scope_proof_failed")

    put_configuration(account_id, tunnel_id, api_token, desired_config)
    try:
        post_config, _ = get_configuration(account_id, tunnel_id, api_token)
        if post_config != desired_config:
            raise RouteError("post_write_configuration_mismatch")
        validate_configuration(post_config, NEW_SERVICE)
        verify_access_edge()
    except RouteError as exc:
        rollback_ok = rollback(account_id, tunnel_id, api_token, latest_config)
        emit("RESULT", "FAILED_ROLLBACK_VERIFIED" if rollback_ok else "FAILED_STATE_REQUIRES_REVIEW")
        emit("MODE", "cutover")
        emit("REASON", str(exc))
        emit("AUTO_ROLLBACK", "PASS" if rollback_ok else "FAILED")
        raise SystemExit(1) from exc

    emit("RESULT", "PASS")
    emit("MODE", "cutover")
    emit("ROUTE_STATE", "LOOPBACK")
    emit("ACCESS_EDGE", "PASS")
    emit("ONLY_DEALS_SERVICE_CHANGED", "true")
    emit("AUTO_ROLLBACK", "not_needed")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        emit("RESULT", "BLOCKED")
        emit("REASON", "usage_error")
        raise SystemExit(2)

    mode = sys.argv[1]
    try:
        account_id, tunnel_id, api_token = require_credentials()
        if mode == "check":
            check_mode(account_id, tunnel_id, api_token, OLD_SERVICE, "LAN")
        elif mode == "verify-loopback":
            check_mode(account_id, tunnel_id, api_token, NEW_SERVICE, "LOOPBACK")
        else:
            cutover_mode(account_id, tunnel_id, api_token)
    except RouteError as exc:
        emit("RESULT", "BLOCKED" if mode != "verify-loopback" else "FAIL")
        emit("MODE", mode)
        emit("REASON", str(exc))
        emit("CONFIG_MUTATED", "false")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
