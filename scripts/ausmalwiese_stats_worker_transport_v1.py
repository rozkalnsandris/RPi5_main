#!/usr/bin/env python3
"""Exact Stats Worker protected HTTP transport SOURCE ONLY (#1038).

No installed executable, token reader, OAuth fallback or LIVE entry point.
Only a *future* root-owned fixed installation may use the GET transport. The
provider does not currently give this design verifiable version-specific
source bytes; upload and deployment deliberately fail closed before dispatch.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-stats-worker-transport-v1.json"
INSTALLED = Path("/usr/local/libexec/rpi5-ausmalwiese-stats-worker-transport/transport.py")
HOST = "api.cloudflare.com"
WORKER = "coloring-pages-stats-v1"
ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
WORKER_BLOB = "dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4"
UUID_RE = re.compile(r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}\Z")
ID_RE = re.compile(r"[a-f0-9]{32}\Z")
TYPES = {"DB": "d1", "RATE_LIMITER": "ratelimit",
         "PUBLIC_ORIGIN": "plain_text", "CF_ANALYTICS_HOST": "plain_text",
         "CF_ZONE_TAG": "plain_text", "VISITOR_HMAC_KEY": "secret_text",
         "CF_ANALYTICS_API_TOKEN": "secret_text"}
ZONES = {"ausmalwiese.de", "rozkalns.net"}
ROUTES = {
    "ausmalwiese.de/api/stats/*": "ausmalwiese.de",
    "www.ausmalwiese.de/api/stats/*": "ausmalwiese.de",
    "ausmalwiese.de/q": "ausmalwiese.de",
    "coloring.rozkalns.net/api/stats/*": "rozkalns.net",
}
MAX_REPLY = 65536
STOP = "STOP_STATS_WORKER_TRANSPORT_SOURCE_ONLY"

class Blocked(Exception):
    """Never expose provider errors, secrets or raw response bodies."""

def require(condition: bool, code: str) -> None:
    if not condition:
        raise Blocked(code)

def uuid(value: Any) -> str:
    require(type(value) is str and UUID_RE.fullmatch(value) is not None, "INVALID_UUID")
    return value

def identifier(value: Any) -> str:
    require(type(value) is str and ID_RE.fullmatch(value) is not None, "INVALID_ID")
    return value

def account_identity(account_id: str) -> None:
    identifier(account_id)
    require(hashlib.sha256(account_id.encode("ascii")).hexdigest() == ACCOUNT_SHA256,
            "WRONG_ACCOUNT")

def strict_json(raw: bytes) -> Any:
    require(type(raw) is bytes and 0 < len(raw) <= MAX_REPLY, "RESPONSE_SIZE")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate")
            out[key] = value
        return out
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, TypeError):
        raise Blocked("JSON_INVALID") from None

def unwrap(payload: Any) -> Any:
    require(type(payload) is dict
            and set(payload) <= {"success", "errors", "messages", "result", "result_info"}
            and payload.get("success") is True
            and type(payload.get("errors")) is list and not payload["errors"]
            and type(payload.get("result")) in (dict, list),
            "UPSTREAM_UNVERIFIED")
    info = payload.get("result_info")
    if info is not None:
        cursors = info.get("cursors") if type(info) is dict else None
        require(type(info) is dict
                and type(info.get("page")) is int and info["page"] == 1
                and type(info.get("total_pages")) is int and info["total_pages"] == 1
                and (cursors is None or (type(cursors) is dict and
                     cursors.get("after") is None)),
                "PAGINATION_UNVERIFIED")
    return payload["result"]

def allowlisted_get(account: str, path: str, zone_ids: dict[str, str]) -> bool:
    """Hardcoded endpoints only, no arbitrary URL or path query."""
    identifier(account)
    base = f"/client/v4/accounts/{account}/workers/scripts/{WORKER}"
    if path in (base + "/versions?page=1&per_page=100", base + "/deployments"):
        return True
    if path.startswith(base + "/versions/"):
        suffix = path[len(base + "/versions/"):]
        return UUID_RE.fullmatch(suffix) is not None
    if type(zone_ids) is not dict or set(zone_ids) != ZONES:
        return False
    for zone in zone_ids.values():
        if type(zone) is str and ID_RE.fullmatch(zone):
            if path in (f"/client/v4/zones/{zone}",
                        f"/client/v4/zones/{zone}/workers/routes"):
                return True
    return False

def verified_installed_release() -> None:
    """No checkout or symlink can invoke the authenticated network client."""
    try:
        if str(Path(__file__).absolute()) != str(INSTALLED) or os.geteuid() != 0:
            raise Blocked("PROTECTED_INSTALL_REQUIRED")
        st = INSTALLED.lstat()
        require(stat.S_ISREG(st.st_mode) and st.st_uid == 0
                and stat.S_IMODE(st.st_mode) == 0o400 and st.st_nlink == 1,
                "PROTECTED_FILE_IDENTITY")
        # The separate installed launcher MUST additionally bind exact SHA-256,
        # parent ownership, current approved main SHA and one-shot owner gate.
        # Since no launcher is delivered here, networking stays disabled.
        raise Blocked("TRUSTED_LAUNCHER_NOT_IMPLEMENTED")
    except OSError:
        raise Blocked("PROTECTED_INSTALL_REQUIRED") from None

class FixedHTTPS:
    """Future-only GET boundary; impossible to instantiate from this checkout."""

    def __init__(self, account: str, token: str, zone_ids: dict[str, str]):
        verified_installed_release()
        account_identity(account)
        require(type(token) is str and 20 <= len(token) <= 4096
                and all(33 <= ord(c) <= 126 for c in token), "TOKEN_FORMAT")
        require(type(zone_ids) is dict and set(zone_ids) == ZONES
                and all(type(x) is str and ID_RE.fullmatch(x) for x in zone_ids.values())
                and len(set(zone_ids.values())) == 2, "ZONE_PINS")
        self._account, self._token, self._zones = account, token, dict(zone_ids)
        self._calls = 0

    def get(self, path: str) -> Any:
        # Recheck on every invocation: bypassing __init__ must not bypass
        # the protected runtime requirement.
        verified_installed_release()
        require(allowlisted_get(self._account, path, self._zones), "ENDPOINT_NOT_ALLOWED")
        require(self._calls < 12, "REQUEST_BUDGET_EXHAUSTED")
        self._calls += 1  # dispatch budget consumed before connecting
        conn = None
        try:
            conn = http.client.HTTPSConnection(HOST, timeout=10,
                                               context=ssl.create_default_context())
            conn.request("GET", path, headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/json", "Accept-Encoding": "identity",
                "Connection": "close",
            })
            response = conn.getresponse()
            require(response.status == 200, "READ_HTTP_FAILURE")
            require(response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
                    == "application/json", "RESPONSE_TYPE")
            require(response.getheader("Content-Encoding", "identity").lower()
                    == "identity", "RESPONSE_ENCODING")
            advertised = response.getheader("Content-Length")
            require(advertised is None or
                    (advertised.isdecimal() and int(advertised) <= MAX_REPLY),
                    "RESPONSE_LENGTH")
            payload = strict_json(response.read(MAX_REPLY + 1))
            return unwrap(payload)
        except Blocked:
            raise
        except Exception:
            raise Blocked("READ_TRANSPORT_UNCERTAIN") from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

def versions_summary(items: Any) -> dict[str, str]:
    """Version numbers are compared explicitly; ordering in JSON is not trusted."""
    require(type(items) is list and 1 <= len(items) < 100, "VERSIONS_INCOMPLETE")
    entries: dict[int, str] = {}
    for x in items:
        require(type(x) is dict and type(x.get("number")) is int
                and x["number"] > 0 and "id" in x, "VERSION_SHAPE")
        n = x["number"]
        require(n not in entries, "DUPLICATE_VERSION_NUMBER")
        entries[n] = uuid(x["id"])
    require(len(set(entries.values())) == len(entries), "DUPLICATE_VERSION_ID")
    return {"latest_uploaded_version": entries[max(entries)],
            "version_count": str(len(entries))}

def deployment_summary(deployments: Any) -> dict[str, str | int]:
    """One fully active Production version; reject ambiguous deployment ordering."""
    require(type(deployments) is list and 1 <= len(deployments) < 100,
            "DEPLOYMENTS_INCOMPLETE")
    by_stamp: dict[str, dict[str, Any]] = {}
    for d in deployments:
        require(type(d) is dict and type(d.get("created_on")) is str
                and len(d["created_on"]) >= 20 and type(d.get("versions")) is list
                and "id" in d, "DEPLOYMENT_SHAPE")
        uuid(d["id"])
        require(d["created_on"] not in by_stamp, "DEPLOYMENT_ORDER_AMBIGUOUS")
        by_stamp[d["created_on"]] = d
    latest = by_stamp[max(by_stamp)]
    versions = latest["versions"]
    require(len(versions) == 1 and type(versions[0]) is dict
            and set(versions[0]) == {"version_id", "percentage"}
            and type(versions[0]["percentage"]) in (int, float)
            and type(versions[0]["percentage"]) is not bool
            and versions[0]["percentage"] == 100,
            "TRAFFIC_SPLIT")
    return {"deployment_id": uuid(latest["id"]),
            "active_version": uuid(versions[0]["version_id"]), "traffic_percent": 100}

def zone_summary(zone: Any, expected_name: str, expected_id: str) -> None:
    require(type(zone) is dict and expected_name in ZONES
            and zone.get("name") == expected_name
            and zone.get("id") == identifier(expected_id)
            and zone.get("status") == "active", "ZONE_IDENTITY")

def routes_summary(route_lists: Any, zone_ids: dict[str, str]) -> dict[str, str]:
    require(type(route_lists) is dict and set(route_lists) == ZONES
            and type(zone_ids) is dict and set(zone_ids) == ZONES,
            "ZONE_SET")
    found: dict[str, str] = {}
    for zone, lst in route_lists.items():
        require(type(lst) is list and len(lst) < 1000, "ROUTE_LIST_INCOMPLETE")
        identifier(zone_ids[zone])
        for route in lst:
            require(type(route) is dict and type(route.get("pattern")) is str
                    and type(route.get("script")) is (str if route.get("script") is not None else type(None)),
                    "ROUTE_INVALID")
            if route["script"] == WORKER:
                pattern = route["pattern"]
                require(pattern not in found and ROUTES.get(pattern) == zone,
                        "ROUTE_DRIFT")
                found[pattern] = zone
    require(found == ROUTES, "ROUTE_SET_DRIFT")
    return found

def metadata_safety(resources: Any) -> dict[str, str | None]:
    """Accept only known exposed fields; never return values of secrets."""
    require(type(resources) is dict and type(resources.get("bindings")) is list,
            "VERSION_BINDINGS_UNKNOWN")
    bindings = resources["bindings"]
    require(len(bindings) == len(TYPES), "BINDING_COUNT")
    result: dict[str, str | None] = {}
    for b in bindings:
        require(type(b) is dict and type(b.get("name")) is str
                and b.get("name") not in result and b.get("type") == TYPES.get(b.get("name")),
                "BINDING_DRIFT")
        name = b["name"]
        if TYPES[name] == "secret_text":
            require(set(b) == {"name", "type"}, "SECRET_METADATA_UNSAFE")
            result[name] = None
        else:
            require(set(b) == {"name", "type", "fingerprint"}
                    and type(b["fingerprint"]) is str
                    and re.fullmatch("[0-9a-f]{64}", b["fingerprint"]) is not None,
                    "BINDING_FINGERPRINT_UNVERIFIED")
            result[name] = b["fingerprint"]
    require(set(result) == set(TYPES), "BINDING_SET")
    return result

def compare_readonly(versions: Any, deployments: Any, route_lists: Any,
                     zone_ids: dict[str, str]) -> dict[str, str]:
    v, d = versions_summary(versions), deployment_summary(deployments)
    routes_summary(route_lists, zone_ids)
    require(v["latest_uploaded_version"] == d["active_version"],
            "LATEST_NOT_DEPLOYED")
    return {"worker": WORKER, "active_version": d["active_version"],
            "deployment_id": d["deployment_id"],
            "state": "INVENTORY_ONLY_CODE_PROOF_BLOCKED"}

def version_code_proof(version_metadata: Any, expected_code: bytes) -> None:
    """No documented version-scoped raw bytes: etag is NOT source SHA-256."""
    require(type(expected_code) is bytes and expected_code, "SOURCE_BYTES_REQUIRED")
    require(type(version_metadata) is dict, "VERSION_METADATA_INVALID")
    # A provider 'resources.script.etag' is a hashed content identifier;
    # no public contract proves it is SHA-256 of the exact uploaded module.
    raise Blocked("VERSION_SPECIFIC_BYTES_PROOF_UNAVAILABLE")

def plan_live_mutations(*_args: Any, **_kwargs: Any) -> None:
    """Fail BEFORE any upload, including in a hypothetical protected install."""
    raise Blocked("SOURCE_ONLY_NO_MUTATION_CODE_PROOF_UNAVAILABLE")

def check_contract(contract: Any) -> None:
    require(type(contract) is dict and contract.get("schema_version") == 1
            and contract.get("status") == "SOURCE_ONLY_CODE_PROOF_BLOCKED"
            and contract.get("repository") == "rozkalnsandris/RPi5_main"
            and contract.get("issue") == 1038, "CONTRACT_DRIFT")
    t = contract.get("target")
    require(type(t) is dict and t.get("account_sha256") == ACCOUNT_SHA256
            and t.get("worker") == WORKER and t.get("git_blob_sha1") == WORKER_BLOB,
            "CONTRACT_TARGET")
    require(contract.get("routes") == ROUTES and contract.get("bindings") == TYPES,
            "CONTRACT_INVARIANTS")
    require(contract.get("read_procedure", {}).get("installed_only") is True
            and contract["read_procedure"].get("read_only") is True
            and contract.get("code_proof", {}).get("stop_until_proven") is True
            and contract.get("future_write_protocol", {}).get("authorized") is False
            and type(contract.get("actions")) is dict
            and all(v is False for v in contract["actions"].values()),
            "CONTRACT_AUTHORITY")

def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        check_contract(strict_json(CONTRACT.read_bytes()))
    except (Blocked, OSError, ValueError):
        print(STOP)
        return 2
    print("SOURCE_CONTRACT_OK_CODE_PROOF_BLOCKED_NO_LIVE")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
