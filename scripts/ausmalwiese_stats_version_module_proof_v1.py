#!/usr/bin/env python3
"""Offline, version-specific Stats Worker byte proof design (#1045).

No Cloudflare request, token, installed operator, deployment or LIVE proof.
The input envelope and independent inventory are NOT authenticated by this code.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-stats-version-module-proof-v1.json"
ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
WORKER = "coloring-pages-stats-v1"
SOURCE_REPO = "rozkalnsandris/coloring-pages"
SOURCE_COMMIT = "9590be4276ac1781eafe38cf662b8d224653c9aa"
SOURCE_BLOB = "dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4"
MODULE = "stats-worker.js"
MIME = "application/javascript+module"
HOST = "api.cloudflare.com"
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
IDENTIFIER = re.compile(r"[0-9a-f]{32}\Z")
B64 = re.compile(r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?\Z")
MAX_REPLY = 2_097_152
MAX_MODULE = 120_000
STOP = "STOP_STATS_VERSION_MODULE_SOURCE_ONLY"
# Only documented response fields; unneeded fields are not copied into proof.
VERSION_FIELDS = {
    "id", "created_on", "number", "urls", "annotations", "assets", "bindings",
    "cache_options", "compatibility_date", "compatibility_flags", "containers",
    "exports", "exports_reconciliation", "limits", "main_module",
    "migration_tag", "migrations", "modules", "package_dependencies",
    "placement", "source", "startup_time_ms", "usage_model",
}

class Blocked(Exception):
    """One fixed error code; never echo provider data or code bytes."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def fixed_get(account_id: Any, version_id: Any) -> dict[str, Any]:
    """Non-executable HTTPS GET blueprint, never a network client."""
    need(type(account_id) is str and IDENTIFIER.fullmatch(account_id) is not None,
         "ACCOUNT_FORMAT")
    need(hashlib.sha256(account_id.encode("ascii")).hexdigest() == ACCOUNT_SHA256,
         "ACCOUNT_IDENTITY")
    need(type(version_id) is str and UUID.fullmatch(version_id) is not None,
         "VERSION_FORMAT")
    return {
        "method": "GET", "scheme": "https", "host": HOST, "port": 443,
        "path": (f"/client/v4/accounts/{account_id}/workers/workers/{WORKER}"
                 f"/versions/{version_id}?include=modules"),
        "tls_verify": True, "redirects": 0, "retries": 0,
        "credential_access": False, "dispatch_enabled": False,
    }


def strict_json(raw: Any) -> Any:
    need(type(raw) is bytes and 0 < len(raw) <= MAX_REPLY, "RESPONSE_BOUNDS")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate")
            out[key] = value
        return out

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, TypeError):
        raise Blocked("JSON_INVALID") from None


def read_module(raw: Any, expected_version: Any) -> bytes:
    """Parse a bounded provider-shaped response; return only exact module bytes."""
    version = strict_json(raw)
    need(type(version) is dict
         and set(version) <= {"success", "errors", "messages", "result"}
         and version.get("success") is True
         and version.get("errors") == [] and type(version.get("errors")) is list
         and type(version.get("messages", [])) is list
         and type(version.get("result")) is dict, "RESPONSE_STATUS")
    item = version["result"]
    need(set(item) <= VERSION_FIELDS
         and item.get("id") == expected_version
         and type(item.get("id")) is str
         and UUID.fullmatch(item["id"]) is not None
         and item.get("main_module") == MODULE
         and type(item.get("modules")) is list
         and len(item["modules"]) == 1, "VERSION_MODULE_IDENTITY")
    entry = item["modules"][0]
    need(type(entry) is dict
         and set(entry) == {"name", "content_type", "content_base64"}
         and entry["name"] == MODULE and entry["content_type"] == MIME,
         "MODULE_SHAPE")
    data = entry["content_base64"]
    need(type(data) is str and 0 < len(data) <= ((MAX_MODULE + 2) // 3) * 4
         and B64.fullmatch(data) is not None, "MODULE_BASE64")
    try:
        blob = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise Blocked("MODULE_BASE64") from None
    need(0 < len(blob) <= MAX_MODULE
         and base64.b64encode(blob).decode("ascii") == data, "MODULE_BYTES")
    return blob


def verify_source(source_bytes: Any) -> str:
    """Git blob SHA-1 *binds* original bytes; their SHA-256 is the comparison."""
    need(type(source_bytes) is bytes and 0 < len(source_bytes) <= MAX_MODULE,
         "SOURCE_BOUNDS")
    blob = hashlib.sha1(b"blob " + str(len(source_bytes)).encode("ascii")
                        + b"\0" + source_bytes).hexdigest()
    need(blob == SOURCE_BLOB, "SOURCE_BLOB_MISMATCH")
    return hashlib.sha256(source_bytes).hexdigest()


def verify_offline(account_id: Any, version_id: Any, raw: Any,
                   source_bytes: Any, inventory: Any) -> dict[str, str]:
    """Synthetic/unauthenticated comparison, NEVER deploy readiness.

    A future protected collector must independently authenticate this inventory,
    account->Worker mapping, active/latest version, full Cloudflare response and
    source origin. A caller-supplied dict cannot serve as that proof.
    """
    fixed_get(account_id, version_id)
    expected = {
        "account_sha256": ACCOUNT_SHA256, "worker": WORKER,
        "environment": "production", "active_version": version_id,
        "latest_uploaded_version": version_id, "source_repo": SOURCE_REPO,
        "source_commit": SOURCE_COMMIT, "source_blob": SOURCE_BLOB,
    }
    need(type(inventory) is dict and inventory == expected,
         "INDEPENDENT_INVENTORY_REQUIRED")
    expected_hash = verify_source(source_bytes)
    decoded = read_module(raw, version_id)
    need(hashlib.sha256(decoded).hexdigest() == expected_hash
         and decoded == source_bytes, "VERSION_CODE_DRIFT")
    return {"worker": WORKER, "version_id": version_id,
            "module_sha256": expected_hash,
            "state": "OFFLINE_BYTES_MATCH_NOT_AUTHENTICATED_NO_LIVE"}


def check_contract(contract: Any) -> None:
    fixed = {
        "schema_version": 1, "status": "SOURCE_ONLY_OFFLINE_PROOF_NO_LIVE",
        "issue": 1045, "repository": "rozkalnsandris/RPi5_main",
        "account_sha256": ACCOUNT_SHA256, "worker": WORKER,
        "source_repo": SOURCE_REPO, "source_commit": SOURCE_COMMIT,
        "source_path": "cloudflare/stats-worker.js", "source_blob": SOURCE_BLOB,
        "module": MODULE, "mime": MIME, "max_reply_bytes": MAX_REPLY,
        "max_module_bytes": MAX_MODULE,
        "get_path": "/client/v4/accounts/{account_id}/workers/workers/coloring-pages-stats-v1/versions/{version_id}?include=modules",
        "trusted_collector_installed": False, "authenticated_evidence_available": False,
        "merge_authorized": False, "live_authorized": False,
        "worker_writes_enabled": False,
    }
    need(type(contract) is dict and contract == fixed, "CONTRACT_DRIFT")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        check_contract(strict_json(CONTRACT.read_bytes()))
    except (Blocked, OSError):
        print(STOP)
        return 2
    print("SOURCE_CONTRACT_OK_OFFLINE_ONLY_NO_LIVE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
