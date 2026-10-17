#!/usr/bin/env python3
"""Source-only normalized Stats Wrangler inventory collector/parser (#1054).

This module has no HTTP client, credential reader, installer or LIVE entrypoint.
It validates bounded synthetic/provider response bytes supplied by a future,
separately reviewed protected GET-only transport and emits only the allowlisted
snapshot consumed by the #1052 takeover planner.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-stats-wrangler-inventory-v1.json"
CONFLICT_SOURCE = ROOT / "scripts/ausmalwiese_stats_wrangler_conflict_v1.py"

ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
WORKER = "coloring-pages-stats-v1"
ENVIRONMENT = "production"
WRANGLER_VERSION = "4.135.0"
SOURCE_COMMIT = "699c036b7f952aa98be06e166a9705069b7e9eb2"
SOURCE_BLOB = "94e802ce145dd75f5701c4c9274a4ac7959c7f5e"
CONFIG_BLOB = "3733263a391274f2b6b0f2023c8656565bde8e1a"
BASELINE_VERSION = "e47f145f-1851-4917-be5c-387f96549539"
COMPATIBILITY_DATE = "2026-10-06"

API_HOST = "api.cloudflare.com"
MAX_REQUESTS = 3
REQUEST_TIMEOUT_S = 10
MAX_RESPONSE_BYTES = 65536
RETRIES = 0
REDIRECTS = 0

D1_DATABASE_ID = "f8ac8f1d-a230-4bc4-af13-557c1b91b273"
D1_DATABASE_NAME = "coloring-pages-stats-v1"
RATE_NAMESPACE_ID = "1152026106"
RATE_LIMIT = 100
RATE_PERIOD = 60
SECRET_NAMES = ["CF_ANALYTICS_API_TOKEN", "VISITOR_HMAC_KEY"]
PLAIN_TEXT_NAMES = ["CF_ANALYTICS_HOST", "CF_ZONE_TAG", "PUBLIC_ORIGIN"]

VERSION_ID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
DATE = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]\Z")
SAFE_KEY = re.compile(r"[A-Za-z0-9_./:-]{1,120}\Z")
STOP = "STOP_STATS_WRANGLER_INVENTORY_SOURCE_ONLY"


class Blocked(Exception):
    """Stable source-only failure reason."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def _uuid(value: Any, reason: str) -> str:
    need(type(value) is str and VERSION_ID.fullmatch(value) is not None, reason)
    return value


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_sha256(value: Any) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def request_specs(version_id: str | None = None) -> list[dict[str, Any]]:
    """Fixed future GET-only request plan; no request is executed here."""
    specs = [
        {
            "stage": "versions",
            "method": "GET",
            "host": API_HOST,
            "path": (
                "/client/v4/accounts/{account_id}/workers/scripts/"
                + WORKER
                + "/versions?page=1&per_page=2"
            ),
            "max_response_bytes": MAX_RESPONSE_BYTES,
            "timeout_s": REQUEST_TIMEOUT_S,
            "retries": RETRIES,
            "redirects": REDIRECTS,
        },
        {
            "stage": "deployments",
            "method": "GET",
            "host": API_HOST,
            "path": (
                "/client/v4/accounts/{account_id}/workers/scripts/"
                + WORKER
                + "/deployments?page=1&per_page=2"
            ),
            "max_response_bytes": MAX_RESPONSE_BYTES,
            "timeout_s": REQUEST_TIMEOUT_S,
            "retries": RETRIES,
            "redirects": REDIRECTS,
        },
    ]
    if version_id is not None:
        _uuid(version_id, "VERSION_ID")
        specs.append(
            {
                "stage": "version_detail",
                "method": "GET",
                "host": API_HOST,
                "path": (
                    "/client/v4/accounts/{account_id}/workers/scripts/"
                    + WORKER
                    + "/versions/"
                    + version_id
                ),
                "max_response_bytes": MAX_RESPONSE_BYTES,
                "timeout_s": REQUEST_TIMEOUT_S,
                "retries": RETRIES,
                "redirects": REDIRECTS,
            }
        )
    return specs


def decode_reply(
    status: Any,
    content_type: Any,
    content_encoding: Any,
    body: Any,
) -> dict[str, Any]:
    """Validate one already-received provider reply; never performs I/O."""
    need(type(status) is int and status == 200, "HTTP_STATUS")
    need(
        type(content_type) is str
        and content_type.split(";", 1)[0].strip().lower() == "application/json",
        "CONTENT_TYPE",
    )
    need(
        type(content_encoding) is str
        and content_encoding.strip().lower() in {"", "identity"},
        "CONTENT_ENCODING",
    )
    need(
        type(body) is bytes and 0 < len(body) <= MAX_RESPONSE_BYTES,
        "RESPONSE_SIZE",
    )
    try:
        def reject_constant(_: str) -> None:
            raise ValueError("constant")
        parsed = json.loads(
            body.decode("utf-8"),
            parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError):
        raise Blocked("JSON_INVALID") from None
    need(type(parsed) is dict, "JSON_ROOT")
    return parsed


def _api_result(payload: Any, *, pagination: str) -> Any:
    need(type(payload) is dict, "API_ENVELOPE")
    allowed = {"success", "errors", "messages", "result", "result_info"}
    need(set(payload).issubset(allowed), "API_ENVELOPE_FIELDS")
    need(
        payload.get("success") is True
        and payload.get("errors") == []
        and type(payload.get("messages", [])) is list,
        "API_FAILURE",
    )
    need(pagination in {"forbidden", "optional"}, "PAGINATION_MODE")
    if pagination == "forbidden":
        need("result_info" not in payload, "PAGINATION_UNEXPECTED")
    elif "result_info" in payload:
        need(type(payload["result_info"]) is dict, "PAGINATION")
    return payload.get("result")


def _result_info(payload: dict[str, Any], count: int) -> None:
    info = payload.get("result_info")
    need(type(info) is dict, "PAGINATION")
    required = {"page", "per_page", "count", "total_count"}
    allowed = required | {"total_pages"}
    need(required.issubset(info) and set(info).issubset(allowed), "PAGINATION_FIELDS")
    need(
        type(info["page"]) is int
        and info["page"] == 1
        and type(info["per_page"]) is int
        and info["per_page"] == 2
        and type(info["count"]) is int
        and info["count"] == count
        and 1 <= info["count"] <= 2
        and type(info["total_count"]) is int
        and count <= info["total_count"] <= 1000000,
        "PAGINATION_DRIFT",
    )
    if "total_pages" in info:
        expected_pages = max(1, (info["total_count"] + info["per_page"] - 1) // info["per_page"])
        need(
            type(info["total_pages"]) is int
            and 1 <= info["total_pages"] <= 500000
            and info["total_pages"] == expected_pages,
            "PAGINATION_PAGES",
        )


def _source_class(source: Any, last_deployed_from: Any) -> str:
    need(type(source) is str and type(last_deployed_from) is str, "SOURCE_METADATA")
    need(source == last_deployed_from, "SOURCE_AMBIGUOUS")
    if source == "api":
        return "script_api"
    if source == "wrangler":
        return "wrangler_versions_upload"
    raise Blocked("SOURCE_UNSUPPORTED")


def parse_versions(payload: dict[str, Any]) -> tuple[str, str]:
    result = _api_result(payload, pagination="optional")
    need(
        type(result) is dict and set(result) == {"items"},
        "VERSIONS_RESULT",
    )
    items = result["items"]
    need(type(items) is list and 1 <= len(items) <= 2, "VERSIONS_COUNT")
    if "result_info" in payload:
        _result_info(payload, len(items))
    parsed: list[tuple[str, int | None, str]] = []
    seen: set[str] = set()
    for item in items:
        need(type(item) is dict and len(item) <= 20, "VERSION_ENTRY")
        version_id = _uuid(item.get("id"), "VERSION_ID")
        need(version_id not in seen, "VERSION_DUPLICATE")
        seen.add(version_id)
        number = item.get("number")
        if "number" in item:
            need(
                type(number) is int and 0 <= number <= 2147483647,
                "VERSION_NUMBER",
            )
        else:
            number = None
        meta = item.get("metadata")
        need(type(meta) is dict and len(meta) <= 20, "VERSION_METADATA")
        source = meta.get("source")
        need(
            type(source) is str and 1 <= len(source) <= 64,
            "VERSION_SOURCE",
        )
        parsed.append((version_id, number, source))
    if (
        len(parsed) == 2
        and parsed[0][1] is not None
        and parsed[1][1] is not None
    ):
        need(parsed[0][1] > parsed[1][1], "VERSION_ORDER")
    return parsed[0][0], parsed[0][2]


def parse_deployments(payload: dict[str, Any]) -> dict[str, Any]:
    result = _api_result(payload, pagination="optional")
    need(type(result) is dict and set(result) == {"deployments"}, "DEPLOY_RESULT")
    deployments = result["deployments"]
    need(
        type(deployments) is list and 1 <= len(deployments) <= 2,
        "DEPLOYMENTS_COUNT",
    )
    if "result_info" in payload:
        _result_info(payload, len(deployments))
    current = deployments[0]
    need(type(current) is dict, "DEPLOYMENT_ENTRY")
    _uuid(current.get("id"), "DEPLOYMENT_ID")
    need(current.get("strategy") == "percentage", "DEPLOYMENT_STRATEGY")
    versions = current.get("versions")
    need(type(versions) is list and len(versions) == 1, "ACTIVE_VERSION_COUNT")
    share = versions[0]
    need(type(share) is dict, "ACTIVE_VERSION_ENTRY")
    active_id = _uuid(share.get("version_id"), "ACTIVE_VERSION")
    percentage = share.get("percentage")
    need(
        type(percentage) in {int, float}
        and type(percentage) is not bool
        and float(percentage) == 100.0,
        "SPLIT_TRAFFIC",
    )
    return {"version_id": active_id, "percentage": 100}


def _binding_list(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is list:
        items = raw
    elif type(raw) is dict:
        items = []
        for name, desc in raw.items():
            need(type(name) is str and type(desc) is dict, "BINDING_MAP")
            copied = dict(desc)
            if "name" in copied:
                need(copied["name"] == name, "BINDING_MAP_NAME")
            else:
                copied["name"] = name
            items.append(copied)
    else:
        raise Blocked("BINDINGS_TYPE")
    need(1 <= len(items) <= 20, "BINDINGS_COUNT")
    return items


def _safe_json(value: Any, depth: int = 0) -> Any:
    need(depth <= 6, "SETTINGS_DEPTH")
    if value is None or type(value) is bool:
        return value
    if type(value) in {int, float}:
        need(
            not isinstance(value, float)
            or (value == value and abs(value) != float("inf")),
            "SETTINGS_NUMBER",
        )
        return value
    if type(value) is str:
        need(len(value) <= 512, "SETTINGS_STRING")
        return value
    if type(value) is list:
        need(len(value) <= 100, "SETTINGS_LIST")
        return [_safe_json(v, depth + 1) for v in value]
    if type(value) is dict:
        need(len(value) <= 100, "SETTINGS_MAP")
        out: dict[str, Any] = {}
        for key, item in value.items():
            need(
                type(key) is str and SAFE_KEY.fullmatch(key) is not None,
                "SETTINGS_KEY",
            )
            out[key] = _safe_json(item, depth + 1)
        return out
    raise Blocked("SETTINGS_TYPE")


def _normalize_runtime(
    resources: dict[str, Any],
) -> tuple[str, list[str], str, str]:
    runtime = resources.get("script_runtime")
    script = resources.get("script")
    need(type(runtime) is dict and type(script) is dict, "RUNTIME_METADATA")

    allowed_runtime = {
        "compatibility_date",
        "compatibility_flags",
        "exports",
        "limits",
        "migration_tag",
        "usage_model",
    }
    allowed_script = {
        "etag",
        "handlers",
        "last_deployed_from",
        "named_handlers",
    }
    need(set(runtime).issubset(allowed_runtime), "RUNTIME_FIELDS")
    need(set(script).issubset(allowed_script), "SCRIPT_FIELDS")

    raw_date = runtime.get("compatibility_date")
    need(type(raw_date) is str, "COMPATIBILITY_DATE")
    if DATE.fullmatch(raw_date):
        compatibility_date = raw_date
    elif raw_date.endswith("T00:00:00Z") and DATE.fullmatch(raw_date[:10]):
        compatibility_date = raw_date[:10]
    else:
        raise Blocked("COMPATIBILITY_DATE")

    flags = runtime.get("compatibility_flags", [])
    need(
        type(flags) is list
        and len(flags) <= 30
        and all(
            type(x) is str and SAFE_KEY.fullmatch(x) is not None
            for x in flags
        )
        and len(set(flags)) == len(flags),
        "COMPATIBILITY_FLAGS",
    )
    flags = sorted(flags)

    last_deployed_from = script.get("last_deployed_from")
    need(type(last_deployed_from) is str, "LAST_DEPLOYED_FROM")

    remaining = {
        "script": {
            "handlers": _safe_json(script.get("handlers", [])),
            "named_handlers": _safe_json(script.get("named_handlers", [])),
        },
        "script_runtime": {
            key: _safe_json(runtime[key])
            for key in ("exports", "limits", "migration_tag", "usage_model")
            if key in runtime
        },
    }
    return (
        compatibility_date,
        flags,
        last_deployed_from,
        canonical_sha256(remaining),
    )


def parse_version_detail(
    payload: dict[str, Any],
    *,
    expected_version: str,
    list_source: str,
) -> dict[str, Any]:
    expected_version = _uuid(expected_version, "EXPECTED_VERSION")
    result = _api_result(payload, pagination="forbidden")
    need(type(result) is dict, "DETAIL_RESULT")
    need(result.get("id") == expected_version, "DETAIL_VERSION")
    metadata = result.get("metadata")
    resources = result.get("resources")
    need(type(metadata) is dict and type(resources) is dict, "DETAIL_FIELDS")
    detail_source = metadata.get("source")
    need(detail_source == list_source, "SOURCE_LIST_DETAIL_DRIFT")

    (
        compatibility_date,
        flags,
        last_deployed_from,
        settings_sha256,
    ) = _normalize_runtime(resources)
    source_class = _source_class(detail_source, last_deployed_from)

    bindings = _binding_list(resources.get("bindings"))
    by_name: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        need(type(binding) is dict, "BINDING_ENTRY")
        name = binding.get("name")
        need(
            type(name) is str and name not in by_name,
            "BINDING_DUPLICATE",
        )
        by_name[name] = binding
    expected_names = (
        set(PLAIN_TEXT_NAMES)
        | set(SECRET_NAMES)
        | {"DB", "RATE_LIMITER"}
    )
    need(set(by_name) == expected_names, "BINDING_SET")

    db = by_name["DB"]
    need(db.get("type") == "d1", "D1_TYPE")
    allowed_db = {"name", "type", "database_id", "id"}
    need(set(db).issubset(allowed_db), "D1_FIELDS")
    database_id = db.get("database_id")
    deprecated_id = db.get("id")
    if database_id is None:
        database_id = deprecated_id
    elif deprecated_id is not None:
        need(deprecated_id == database_id, "D1_ID_AMBIGUOUS")
    need(database_id == D1_DATABASE_ID, "D1_ID")

    rate = by_name["RATE_LIMITER"]
    need(rate.get("type") == "ratelimit", "RATE_TYPE")
    need(
        set(rate).issubset({"name", "type", "namespace_id", "simple"}),
        "RATE_FIELDS",
    )
    simple = rate.get("simple")
    need(type(simple) is dict, "RATE_SIMPLE")
    need(
        set(simple).issubset(
            {"limit", "period", "mitigation_timeout"}
        ),
        "RATE_SIMPLE_FIELDS",
    )
    need(
        rate.get("namespace_id") == RATE_NAMESPACE_ID
        and simple.get("limit") == RATE_LIMIT
        and simple.get("period") == RATE_PERIOD,
        "RATE_POLICY",
    )
    if "mitigation_timeout" in simple:
        need(
            simple["mitigation_timeout"] in {0, None},
            "RATE_MITIGATION",
        )

    secret_names: list[str] = []
    for name in SECRET_NAMES:
        desc = by_name[name]
        need(desc.get("type") == "secret_text", "SECRET_TYPE")
        need(set(desc) == {"name", "type"}, "SECRET_VALUE_PRESENT")
        secret_names.append(name)

    plain: dict[str, dict[str, str]] = {}
    for name in PLAIN_TEXT_NAMES:
        desc = by_name[name]
        need(desc.get("type") == "plain_text", "PLAIN_TYPE")
        need(set(desc) == {"name", "type", "text"}, "PLAIN_FIELDS")
        raw_text = desc.get("text")
        need(
            type(raw_text) is str and len(raw_text) <= 4096,
            "PLAIN_TEXT",
        )
        plain[name] = {
            "kind": "plain_text",
            "fingerprint": _sha256_text(raw_text),
        }

    return {
        "source_class": source_class,
        "compatibility_date": compatibility_date,
        "compatibility_flags": flags,
        "d1": {
            "binding": "DB",
            "database_name": D1_DATABASE_NAME,
            "database_id": D1_DATABASE_ID,
        },
        "rate_limit": {
            "binding": "RATE_LIMITER",
            "namespace_id": RATE_NAMESPACE_ID,
            "limit": RATE_LIMIT,
            "period": RATE_PERIOD,
        },
        "secret_names": sorted(secret_names),
        "plain_text_vars": plain,
        "settings_sha256": settings_sha256,
    }


def build_inventory(
    versions_payload: dict[str, Any],
    deployments_payload: dict[str, Any],
    detail_payload: dict[str, Any],
    *,
    stage: str = "before",
    new_version_id: str | None = None,
) -> dict[str, Any]:
    """Build the exact #1052 snapshot from already-sanitizable provider JSON."""
    need(stage in {"before", "after_upload"}, "STAGE")
    latest_id, list_source = parse_versions(versions_payload)
    active = parse_deployments(deployments_payload)
    if stage == "before":
        need(
            latest_id == BASELINE_VERSION
            and active["version_id"] == BASELINE_VERSION,
            "BASELINE_VERSION_DRIFT",
        )
    else:
        expected_new = _uuid(new_version_id, "NEW_VERSION")
        need(
            latest_id == expected_new
            and active["version_id"] == BASELINE_VERSION,
            "POST_UPLOAD_VERSION_DRIFT",
        )
    detail = parse_version_detail(
        detail_payload,
        expected_version=latest_id,
        list_source=list_source,
    )
    return {
        "schema": "ausmalwiese.stats-wrangler-conflict-inventory.v1",
        "worker": WORKER,
        "environment": ENVIRONMENT,
        "wrangler_version": WRANGLER_VERSION,
        "source_commit": SOURCE_COMMIT,
        "source_blob": SOURCE_BLOB,
        "config_blob": CONFIG_BLOB,
        "source_class": detail["source_class"],
        "latest_uploaded_version": latest_id,
        "active_versions": [active],
        "compatibility_date": detail["compatibility_date"],
        "compatibility_flags": detail["compatibility_flags"],
        "d1": detail["d1"],
        "rate_limit": detail["rate_limit"],
        "secret_names": detail["secret_names"],
        "plain_text_vars": detail["plain_text_vars"],
        "settings_sha256": detail["settings_sha256"],
    }


def inventory_output(
    snapshot: dict[str, Any],
    *,
    stage: str,
    new_version_id: str | None = None,
) -> dict[str, Any]:
    """Validate against #1052 and attach only its deterministic digest."""
    spec = importlib.util.spec_from_file_location(
        "stats_wrangler_conflict_1052",
        CONFLICT_SOURCE,
    )
    need(spec is not None and spec.loader is not None, "CONFLICT_IMPORT")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if stage == "before":
        module.validate_snapshot(snapshot, stage="before")
    elif stage == "after_upload":
        module.validate_snapshot(
            snapshot,
            stage="after_upload",
            new_version_id=new_version_id,
        )
    else:
        raise Blocked("STAGE")
    digest = module.canonical_sha256(snapshot)
    need(
        type(digest) is str and DIGEST.fullmatch(digest) is not None,
        "INVENTORY_DIGEST",
    )
    return {"inventory": snapshot, "inventory_sha256": digest}


def check_contract(contract: Any) -> None:
    expected = {
        "schema_version": 1,
        "status": "SOURCE_ONLY_GET_INVENTORY_NO_NETWORK",
        "issue": 1054,
        "repository": "rozkalnsandris/RPi5_main",
        "account_sha256": ACCOUNT_SHA256,
        "worker": WORKER,
        "environment": ENVIRONMENT,
        "wrangler_version": WRANGLER_VERSION,
        "source_commit": SOURCE_COMMIT,
        "source_blob": SOURCE_BLOB,
        "config_blob": CONFIG_BLOB,
        "baseline_version": BASELINE_VERSION,
        "read_plan": {
            "host": API_HOST,
            "method": "GET",
            "max_requests": MAX_REQUESTS,
            "timeout_s": REQUEST_TIMEOUT_S,
            "max_response_bytes": MAX_RESPONSE_BYTES,
            "retries": RETRIES,
            "redirects": REDIRECTS,
            "stages": ["versions", "deployments", "version_detail"],
        },
        "output_schema": (
            "ausmalwiese.stats-wrangler-conflict-inventory.v1"
        ),
        "actions": {
            "cloudflare_request": False,
            "credential_access": False,
            "host_install": False,
            "merge": False,
            "live": False,
            "retry": False,
            "rollback": False,
            "cleanup": False,
        },
    }
    need(type(contract) is dict and contract == expected, "CONTRACT_DRIFT")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        check_contract(json.loads(CONTRACT.read_text("utf-8")))
    except (Blocked, OSError, ValueError, TypeError):
        print(STOP)
        return 2
    print("STATS_WRANGLER_INVENTORY_OK_SOURCE_ONLY_NO_NETWORK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
