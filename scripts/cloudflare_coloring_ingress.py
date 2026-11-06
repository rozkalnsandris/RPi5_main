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
from pathlib import Path
from typing import Any

import cloudflare_zero_trust_reconcile as zt

API_BASE = "https://api.cloudflare.com/client/v4"
HOSTNAME = "coloring.rozkalns.net"
ZONE_NAME = "rozkalns.net"
ORIGIN = "http://127.0.0.1:9191"
TUNNEL_NAME = "rpi5-tunnel"
MODES = {"check", "apply", "verify"}
REGISTRY = Path("ops/contracts/cloudflare-hostname-policy.yaml")


class IngressError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def emit(name: str, value: str) -> None:
    print(f"{name}={value}")


def require_env() -> tuple[str, str, str, str]:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    tunnel = os.environ.get("CLOUDFLARE_TUNNEL_ID", "")
    write_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    read_token = os.environ.get("CLOUDFLARE_P1D03_READ_API_TOKEN", "")
    read_account = os.environ.get("CLOUDFLARE_P1D03_ACCOUNT_ID", "")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", account) or account != read_account:
        raise IngressError("account_binding_mismatch")
    if not zt.TUNNEL_ID_RE.fullmatch(tunnel):
        raise IngressError("tunnel_binding_invalid")
    for token in (write_token, read_token):
        if len(token) < 20 or any(ch.isspace() for ch in token):
            raise IngressError("token_binding_invalid")
    return account, tunnel, write_token, read_token


def request(token: str, path: str, *, method: str = "GET", body: dict[str, Any] | None = None,
            query: dict[str, str] | None = None) -> Any:
    url = API_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Accept": "application/json", "Content-Type": "application/json",
        "Authorization": f"Bearer {token}", "User-Agent": "rpi5-main-coloring-841",
    })
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise IngressError(f"cloudflare_http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IngressError("cloudflare_request_failed") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise IngressError("cloudflare_api_unsuccessful")
    return payload.get("result")


def expected_present_hosts() -> set[str]:
    registry = zt.load_registry(REGISTRY)
    return {
        host for host, item in registry.items()
        if item.delivery == "shared_rpi5_tunnel" and item.audit_route_presence == "present"
    }


def validate_config(config: dict[str, Any], *, target_present: bool) -> None:
    ingress = config.get("ingress")
    if not isinstance(ingress, list) or not ingress:
        raise IngressError("tunnel_ingress_invalid")
    hosts: list[str] = []
    catchall = []
    for idx, item in enumerate(ingress):
        if not isinstance(item, dict):
            raise IngressError("tunnel_ingress_entry_invalid")
        hostname = item.get("hostname")
        if hostname is None:
            catchall.append((idx, item))
        elif isinstance(hostname, str):
            hosts.append(hostname.lower())
        else:
            raise IngressError("tunnel_hostname_invalid")
    expected = expected_present_hosts() | ({HOSTNAME} if target_present else set())
    if set(hosts) != expected or len(hosts) != len(expected):
        raise IngressError("tunnel_hostname_set_drift")
    if len(catchall) != 1 or catchall[0][0] != len(ingress) - 1 or catchall[0][1].get("service") != "http_status:404":
        raise IngressError("tunnel_catchall_drift")
    matches = [x for x in ingress if x.get("hostname", "").lower() == HOSTNAME]
    if target_present:
        if len(matches) != 1 or matches[0].get("service") != ORIGIN:
            raise IngressError("coloring_origin_mismatch")
        if zt.classify_service(matches[0].get("service")) != "loopback":
            raise IngressError("coloring_origin_not_loopback")
    elif matches:
        raise IngressError("coloring_route_already_exists")


def get_config(account: str, tunnel: str, token: str) -> tuple[dict[str, Any], Any]:
    tunnel_obj = request(token, f"/accounts/{account}/cfd_tunnel/{tunnel}")
    if not isinstance(tunnel_obj, dict) or tunnel_obj.get("name") != TUNNEL_NAME or tunnel_obj.get("config_src") != "cloudflare":
        raise IngressError("tunnel_binding_mismatch")
    result = request(token, f"/accounts/{account}/cfd_tunnel/{tunnel}/configurations")
    if not isinstance(result, dict) or not isinstance(result.get("config"), dict):
        raise IngressError("tunnel_config_invalid")
    return result["config"], result.get("version")


def access_preflight(account: str, read_token: str) -> None:
    org = request(read_token, f"/accounts/{account}/access/organizations")
    if not isinstance(org, dict):
        raise IngressError("access_organization_invalid")
    if org.get("deny_unmatched_requests") is True:
        exempt = org.get("deny_unmatched_requests_exempted_zone_names")
        if not isinstance(exempt, list) or ZONE_NAME not in {str(x).lower() for x in exempt}:
            raise IngressError("require_access_protection_conflict")
    apps = request(read_token, f"/accounts/{account}/access/apps", query={"per_page": "100"})
    if not isinstance(apps, list):
        raise IngressError("access_apps_invalid")
    resolved = zt.resolve_application(apps, HOSTNAME)
    if resolved.get("status") != "none":
        raise IngressError("matching_access_application_present")


def get_zone_and_dns(account: str, token: str, *, require_absent: bool) -> tuple[str, list[dict[str, Any]]]:
    zones = request(token, "/zones", query={"name": ZONE_NAME, "account.id": account, "per_page": "50"})
    if not isinstance(zones, list) or len(zones) != 1 or not isinstance(zones[0].get("id"), str):
        raise IngressError("zone_lookup_mismatch")
    zone_id = zones[0]["id"]
    records = request(token, f"/zones/{zone_id}/dns_records", query={"name": HOSTNAME, "per_page": "100"})
    if not isinstance(records, list):
        raise IngressError("dns_lookup_invalid")
    if require_absent and records:
        raise IngressError("coloring_dns_already_exists")
    return zone_id, records


def preflight(account: str, tunnel: str, write_token: str, read_token: str) -> tuple[dict[str, Any], Any, str]:
    access_preflight(account, read_token)
    config, version = get_config(account, tunnel, write_token)
    validate_config(config, target_present=False)
    zone_id, _ = get_zone_and_dns(account, write_token, require_absent=True)
    return config, version, zone_id


def verify_public() -> None:
    opener = urllib.request.build_opener(NoRedirect)
    for path in ("/", "/health", "/ready"):
        req = urllib.request.Request(f"https://{HOSTNAME}{path}", headers={"User-Agent": "rpi5-main-coloring-841-verify"})
        try:
            with opener.open(req, timeout=20) as response:
                status = response.status
                location = response.headers.get("Location", "")
        except urllib.error.HTTPError as exc:
            status = exc.code
            location = exc.headers.get("Location", "")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise IngressError("public_https_request_failed") from exc
        if status != 200:
            if "cloudflareaccess.com" in location.lower():
                raise IngressError("access_challenge_present")
            raise IngressError(f"public_https_status_{status}")


def verify_state(account: str, tunnel: str, write_token: str, read_token: str) -> None:
    access_preflight(account, read_token)
    config, _ = get_config(account, tunnel, write_token)
    validate_config(config, target_present=True)
    zone_id, records = get_zone_and_dns(account, write_token, require_absent=False)
    expected = f"{tunnel}.cfargotunnel.com"
    matches = [r for r in records if r.get("type") == "CNAME" and str(r.get("content", "")).lower() == expected.lower() and r.get("proxied") is True]
    if len(records) != 1 or len(matches) != 1:
        raise IngressError("coloring_dns_post_state_mismatch")
    verify_public()


def apply(account: str, tunnel: str, write_token: str, read_token: str) -> None:
    original, version, zone_id = preflight(account, tunnel, write_token, read_token)
    latest, latest_version = get_config(account, tunnel, write_token)
    if latest != original or latest_version != version:
        raise IngressError("tunnel_changed_during_preflight")
    _, records = get_zone_and_dns(account, write_token, require_absent=True)
    if records:
        raise IngressError("dns_changed_during_preflight")

    desired = copy.deepcopy(latest)
    desired["ingress"].insert(len(desired["ingress"]) - 1, {"hostname": HOSTNAME, "service": ORIGIN})
    validate_config(desired, target_present=True)
    proof = copy.deepcopy(desired)
    removed = proof["ingress"].pop(-2)
    if removed != {"hostname": HOSTNAME, "service": ORIGIN} or proof != latest:
        raise IngressError("tunnel_mutation_scope_proof_failed")

    request(write_token, f"/accounts/{account}/cfd_tunnel/{tunnel}/configurations",
            method="PUT", body={"config": desired})
    emit("TUNNEL_MUTATED", "true")

    # From this point forward every failure is fail-closed: no retry or rollback.
    post, _ = get_config(account, tunnel, write_token)
    if post != desired:
        raise IngressError("tunnel_post_write_mismatch")
    request(write_token, f"/zones/{zone_id}/dns_records", method="POST", body={
        "type": "CNAME", "name": HOSTNAME, "content": f"{tunnel}.cfargotunnel.com",
        "proxied": True, "ttl": 1,
    })
    emit("DNS_MUTATED", "true")
    verify_state(account, tunnel, write_token, read_token)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode not in MODES:
        emit("RESULT", "BLOCKED"); emit("REASON", "usage_error"); raise SystemExit(2)
    mutated = False
    try:
        account, tunnel, write_token, read_token = require_env()
        if mode == "check":
            preflight(account, tunnel, write_token, read_token)
        elif mode == "apply":
            apply(account, tunnel, write_token, read_token)
            mutated = True
        else:
            verify_state(account, tunnel, write_token, read_token)
        emit("RESULT", "PASS")
        emit("MODE", mode)
        emit("MUTATION_PERFORMED", "true" if mode == "apply" else "false")
    except IngressError as exc:
        emit("RESULT", "BLOCKED" if mode == "check" else "FAIL")
        emit("MODE", mode)
        emit("REASON", str(exc))
        emit("MUTATION_PERFORMED", "unknown" if mode == "apply" else "false")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
