#!/usr/bin/env python3
"""Fixed report-only Cloudflare API adapter SOURCE. No transport or credentials.

Exports immutable method/path/payload specifications and response sanitizers.
Future protected transport MUST authenticate Cloudflare and owner authority,
and MUST privately provision all six bindings. Nothing here performs I/O.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-report-protected-adapter-v1.json"
STOP = "STOP_REPORT_ADAPTER_SOURCE_ONLY"
WORKER = "coloring-pages-report-v1"
ZONE = "ausmalwiese.de"
ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
BLOB_SHA1 = "6d2359752d12f4a40847008fc7fdcc457124e893"
SOURCE_SHA256 = "26d4e597d8c2c961c3a637957ea566654c97c5657a4b2595129c410e9fae22a1"
ROUTES = (
    "ausmalwiese.de/api/report",
    "ausmalwiese.de/api/report/config",
    "www.ausmalwiese.de/api/report",
    "www.ausmalwiese.de/api/report/config",
)
KINDS = {
    "TURNSTILE_SITE_KEY": "plain_text",
    "TURNSTILE_SECRET": "secret_text",
    "BREVO_API_KEY": "secret_text",
    "REPORT_TO": "secret_text",
    "REPORT_RATE": "ratelimit",
    "REPORT_DUP": "ratelimit",
}
LIMITS = {
    "REPORT_RATE": {"limit": 12, "period": 60},
    "REPORT_DUP": {"limit": 1, "period": 60},
}
APIS = {
    "upload": "/client/v4/accounts/{account_id}/workers/scripts/coloring-pages-report-v1/versions",
    "deploy": "/client/v4/accounts/{account_id}/workers/scripts/coloring-pages-report-v1/deployments",
    "add_route": "/client/v4/zones/{zone_id}/workers/routes",
}
METHODS = {"upload": "POST", "deploy": "POST", "add_route": "POST"}
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
DECIMAL = re.compile(r"[1-9][0-9]{0,9}\Z")
EXPECTED_BOUNDARIES = {
    "max_uploads": 1, "max_deployments": 1, "max_route_creates": 4,
    "report_only": True, "allow_legacy_script_put": False,
    "allow_extra_routes": False, "allow_secrets_in_source": False,
    "allow_credential_access": False, "allow_network_from_checkout": False,
    "allow_live": False, "allow_merge": False, "allow_install": False,
    "allow_retry": False, "allow_rollback": False, "allow_cleanup": False,
}
EXPECTED_INSTALLER = {
    "installed_program": "/usr/local/libexec/rpi5-ausmalwiese-report-protected/adapter.py",
    "installed_contract": "/usr/local/libexec/rpi5-ausmalwiese-report-protected/contract.json",
    "release_manifest": "/usr/local/libexec/rpi5-ausmalwiese-report-protected/release.json",
    "entrypoint": "/usr/local/sbin/rpi5-ausmalwiese-report-protected",
    "owner": "root:root",
    "directory_mode": "0755",
    "file_mode": "0644",
    "entrypoint_mode": "0755",
    "only_dry_run_source": True,
}


class Stop(Exception):
    """Fixed failure reason without raw responses or secret values."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Stop(reason)


def expected_contract() -> dict[str, Any]:
    return {
        "schema_version": 1, "state": "SOURCE_ONLY_NOT_INSTALLED",
        "repository": "rozkalnsandris/RPi5_main", "issue": 1039,
        "target": {"worker": WORKER, "zone": ZONE, "account_sha256": ACCOUNT_SHA256},
        "source": {
            "path": "cloudflare/report-worker.mjs",
            "blob": BLOB_SHA1,
            "sha256": SOURCE_SHA256,
        },
        "routes": list(ROUTES), "bindings": KINDS, "rates": LIMITS,
        "api_paths": APIS, "methods": METHODS,
        "boundaries": EXPECTED_BOUNDARIES, "installer": EXPECTED_INSTALLER,
    }


def check_contract(data: Any) -> None:
    need(type(data) is dict and data == expected_contract(), "CONTRACT_DRIFT")


def verify_worker_bytes(raw: Any) -> None:
    need(type(raw) is bytes and 0 < len(raw) <= 120000, "SOURCE_INVALID")
    need(hashlib.sha256(raw).hexdigest() == SOURCE_SHA256, "SOURCE_HASH_MISMATCH")
    need(hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw
    ).hexdigest() == BLOB_SHA1, "GIT_BLOB_MISMATCH")


def validate_namespaces(bindings: Any, rates: Any, ids: Any) -> None:
    need(type(bindings) is dict and bindings == KINDS, "BINDING_DRIFT")
    need(type(rates) is dict and rates == LIMITS, "RATE_DRIFT")
    need(type(ids) is dict and set(ids) == {"REPORT_RATE", "REPORT_DUP"},
         "NAMESPACE_SET")
    for value in ids.values():
        need(type(value) is str and DECIMAL.fullmatch(value) is not None
             and int(value) <= 4294967295, "NAMESPACE_FORMAT")
    need(ids["REPORT_RATE"] != ids["REPORT_DUP"], "NAMESPACE_COLLISION")


def account_id_guard(value: Any) -> str:
    """ID is PRIVATE operator input, never printed or persisted in source."""
    need(type(value) is str and HEX32.fullmatch(value) is not None, "ACCOUNT_FORMAT")
    need(hashlib.sha256(value.encode("ascii")).hexdigest() == ACCOUNT_SHA256,
         "ACCOUNT_MISMATCH")
    return value


def zone_id_guard(value: Any) -> str:
    """Shape only. Actual zone identity must come from authenticated GET."""
    need(type(value) is str and HEX32.fullmatch(value) is not None, "ZONE_FORMAT")
    return value


def request_spec(operation: str, account_id: str, zone_id: str,
                 *, route: str | None = None, version_id: str | None = None) -> dict[str, Any]:
    """A non-executable exact URI blueprint. Never contains tokens/secrets.

    The returned object is NOT an authenticated operation or execution authority.
    """
    account_id_guard(account_id)
    zone_id_guard(zone_id)
    need(type(operation) is str and operation in APIS, "OPERATION_FORBIDDEN")
    if operation == "upload":
        need(route is None and version_id is None, "UPLOAD_PARAMETERS")
        policy = "SEALED_MULTIPART_PRIVATE_PROVISIONER_REQUIRED"
        body = None
    elif operation == "deploy":
        need(route is None and type(version_id) is str
             and UUID.fullmatch(version_id) is not None, "DEPLOY_VERSION")
        policy = "EXACT_JSON"
        body = {
            "strategy": "percentage",
            "versions": [{"version_id": version_id, "percentage": 100}],
        }
    else:
        need(version_id is None and type(route) is str and route in ROUTES,
             "ROUTE_OUT_OF_SCOPE")
        policy = "EXACT_JSON"
        body = {"pattern": route, "script": WORKER}
    path = APIS[operation].format(account_id=account_id, zone_id=zone_id)
    need(path.startswith("/client/v4/") and "?" not in path
         and all(c not in path for c in "\r\n\\#"), "API_PATH_DRIFT")
    return {"method": METHODS[operation], "path": path, "body_policy": policy,
            "body": body}


def validate_response(operation: str, response: Any,
                      *, route: str | None = None) -> dict[str, str]:
    """Extract only a whitelisted identifier, never log raw Cloudflare JSON."""
    need(operation in APIS, "REPLY_OPERATION")
    need(type(response) is dict and set(response) == {
        "success", "errors", "messages", "result",
    }, "REPLY_ENVELOPE")
    need(response["success"] is True and response["errors"] == []
         and type(response["messages"]) is list and response["messages"] == [],
         "REPLY_FAILURE")
    result = response["result"]
    need(type(result) is dict, "REPLY_RESULT")
    if operation == "upload":
        # Future adapter must separately prove version belongs to the pinned
        # source bytes and all six bindings. An ID alone is NOT enough.
        need(type(result.get("id")) is str
             and UUID.fullmatch(result["id"]) is not None,
             "REPLY_VERSION")
        return {"version_id": result["id"]}
    if operation == "deploy":
        need(type(result.get("id")) is str
             and UUID.fullmatch(result["id"]) is not None,
             "REPLY_DEPLOYMENT")
        return {"deployment_id": result["id"]}
    need(type(route) is str and route in ROUTES
         and result.get("pattern") == route
         and result.get("script") == WORKER
         and type(result.get("id")) is str
         and HEX32.fullmatch(result["id"]) is not None, "REPLY_ROUTE")
    return {"route": route, "worker": WORKER}


class SingleDispatchLedger:
    """Offline bound for a future privileged adapter. NOT a runtime auth gate.

    A protected external gate must enforce the *persistent* per-operation
    nonce and stop all future attempts after any dispatch/unknown result.
    """

    def __init__(self) -> None:
        self._spent = False
        self._done: set[str] = set()
        self._next = 0
        self._order = ["upload", "deploy"] + ["route:" + r for r in ROUTES]

    def reserve(self, operation: str, route: str | None = None) -> None:
        need(not self._spent and self._next < len(self._order),
             "DISPATCH_EXHAUSTED")
        target = operation if operation != "add_route" else "route:" + str(route)
        need(target == self._order[self._next] and target not in self._done,
             "OUT_OF_ORDER_OR_REPEATED")
        # Reservation happens before the FIRST external send.
        self._done.add(target)
        self._next += 1

    def freeze(self) -> None:
        self._spent = True


def main(argv: list[str] | None = None) -> int:
    # No Cloudflare access, installer, transport or apply option.
    if (sys.argv[1:] if argv is None else argv) != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        check_contract(json.loads(CONTRACT.read_text(encoding="utf-8")))
    except (Stop, OSError, ValueError, TypeError):
        print(STOP)
        return 2
    print("REPORT_ADAPTER_SOURCE_OK_NOT_LIVE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
