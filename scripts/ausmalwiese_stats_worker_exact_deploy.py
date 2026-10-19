#!/usr/bin/env python3
"""Ausmalwiese Stats Worker exact-version operator CORE, source only (#1032).

The module has NO authenticated HTTP transport, credential reader or LIVE CLI.
A future root-installed, separately reviewed trust boundary must supply the
narrow read/upload/deploy interface and enforce a fresh owner authorization.
Passing synthetic offline checks cannot authorize, install or run this core.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops/contracts/ausmalwiese-stats-worker-exact-deploy-v1.json"
ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
WORKER = "coloring-pages-stats-v1"
SOURCE_REPO = "rozkalnsandris/coloring-pages"
SOURCE_COMMIT = "e6c1a4a4fa9f8a9c82dc73babd6b4a2a1bdd4d63"
SOURCE_BLOB = "c2ac9da6e0701103e0041b30db7dfbea4298f96c"
ROUTES = {
    "coloring.rozkalns.net/api/stats/*": "rozkalns.net",
    "ausmalwiese.de/api/stats/*": "ausmalwiese.de",
    "www.ausmalwiese.de/api/stats/*": "ausmalwiese.de",
    "ausmalwiese.de/q": "ausmalwiese.de",
}
# Cloudflare multipart upload API kinds, not Dashboard UI labels.
KINDS = {
    "DB": "d1",
    "RATE_LIMITER": "ratelimit",
    "PUBLIC_ORIGIN": "plain_text",
    "CF_ANALYTICS_HOST": "plain_text",
    "CF_ZONE_TAG": "plain_text",
    "VISITOR_HMAC_KEY": "secret_text",
    "CF_ANALYTICS_API_TOKEN": "secret_text",
}
VERSION_ID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
DATE = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]\Z")
CONFIG_BLOB = "3733263a391274f2b6b0f2023c8656565bde8e1a"\nSTOP = "STOP_STATS_WORKER_SOURCE_ONLY"

class Blocked(Exception):
    """Only a fixed, non-sensitive failure class may reach the operator."""

def need(ok: bool, code: str) -> None:
    if not ok:
        raise Blocked(code)

def canonical_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def check_contract(c: Any) -> None:
    fixed = {
        "schema_version": 2,
        "state": "SOURCE_CORE_REPINNED_FOR_INSTALLED_RUNTIME_NO_LIVE",
        "repo": "rozkalnsandris/RPi5_main",
        "issue": 1118,
        "account_sha256": ACCOUNT_SHA256,
        "worker": WORKER,
        "environment": "production",
        "source_repo": SOURCE_REPO,
        "source_commit": SOURCE_COMMIT,
        "source_path": "cloudflare/stats-worker.js",
        "source_blob": SOURCE_BLOB,
        "config_path": "cloudflare/wrangler.stats-worker.jsonc",
        "config_blob": CONFIG_BLOB,
        "routes": ROUTES,
        "bindings": KINDS,
        "mode": "SOURCE_CORE_INSTALLED_RUNTIME_REQUIRED",
        "owner_live_approval": False,
        "merge_approval": True,
        "credential_access": False,
        "allow_retry": False,
        "allow_rollback": False,
        "allow_cleanup": False,
    }
    need(type(c) is dict and c == fixed, "CONTRACT_DRIFT")

def verify_source(worker_bytes: Any) -> None:
    need(type(worker_bytes) is bytes and 0 < len(worker_bytes) <= 120000, "SOURCE_SIZE")
    need(git_blob(worker_bytes) == SOURCE_BLOB, "SOURCE_BLOB_DRIFT")
    try:
        source = worker_bytes.decode("utf-8")
    except UnicodeError:
        raise Blocked("SOURCE_ENCODING") from None
    need('const PRINT_QR_HOST = "ausmalwiese.de";' in source
         and 'const PRINT_QR_DESTINATION = "https://ausmalwiese.de/";' in source,
         "SOURCE_QR_DRIFT")

def _fingerprint(x: Any, code: str) -> str:
    need(type(x) is str and DIGEST.fullmatch(x) is not None, code)
    return x

def _uuid(x: Any, code: str) -> str:
    need(type(x) is str and VERSION_ID.fullmatch(x) is not None, code)
    return x

def validate_snapshot(x: Any, *, allow_latest_difference: bool = False) -> dict[str, Any]:
    """Validate sanitized *trusted-collector* evidence, never a raw CF response.

    A caller-provided dict can be forged; the separately installed protected
    transport must authenticate account, zone, version, pagination and fields.
    No credential or secret value is accepted anywhere in this data schema.
    """
    keys = {
        "schema", "account_sha256", "worker", "environment", "active_version",
        "latest_uploaded_version", "deployment_id", "traffic_percent", "routes",
        "active_bindings", "latest_bindings", "active_configuration",
        "latest_configuration", "active_code_sha256", "latest_code_sha256",
    }
    need(type(x) is dict and set(x) == keys, "SNAPSHOT_FIELDS")
    need(x["schema"] == "ausmalwiese.stats-worker-protected-inventory.v1"
         and x["account_sha256"] == ACCOUNT_SHA256
         and x["worker"] == WORKER and x["environment"] == "production",
         "SNAPSHOT_TARGET")
    active = _uuid(x["active_version"], "ACTIVE_VERSION")
    latest = _uuid(x["latest_uploaded_version"], "LATEST_VERSION")
    _uuid(x["deployment_id"], "DEPLOYMENT_ID")
    need(type(x["traffic_percent"]) is int and x["traffic_percent"] == 100,
         "SPLIT_TRAFFIC")
    if not allow_latest_difference:
        need(latest == active, "LATEST_NOT_ACTIVE")
    _fingerprint(x["active_code_sha256"], "ACTIVE_CODE_PROOF")
    _fingerprint(x["latest_code_sha256"], "LATEST_CODE_PROOF")
    if not allow_latest_difference:
        need(x["active_code_sha256"] == x["latest_code_sha256"], "LATEST_CODE_NOT_ACTIVE")
    routes = x["routes"]
    need(type(routes) is dict and routes == ROUTES, "ROUTE_DRIFT")
    for k in ("active_bindings", "latest_bindings"):
        binding = x[k]
        need(type(binding) is dict and set(binding) == set(KINDS), "BINDING_SET")
        for name, desc in binding.items():
            need(type(desc) is dict and set(desc) == {"kind", "fingerprint"},
                 "BINDING_DESCRIPTOR")
            need(desc["kind"] == KINDS[name], "BINDING_KIND")
            if KINDS[name] == "secret_text":
                need(desc["fingerprint"] is None, "SECRET_DISCLOSURE")
            else:
                _fingerprint(desc["fingerprint"], "BINDING_IDENTITY")
    for key in ("active_configuration", "latest_configuration"):
        config = x[key]
        need(type(config) is dict and set(config) == {
            "compatibility_date", "compatibility_flags", "settings_sha256",
        }, "CONFIG_DESCRIPTOR")
        need(type(config["compatibility_date"]) is str
             and DATE.fullmatch(config["compatibility_date"]) is not None,
             "COMPATIBILITY_DATE")
        flags = config["compatibility_flags"]
        need(type(flags) is list and len(flags) <= 30
             and all(type(f) is str and re.fullmatch("[a-z0-9_]{1,80}", f) for f in flags)
             and len(set(flags)) == len(flags), "COMPATIBILITY_FLAGS")
        _fingerprint(config["settings_sha256"], "SETTINGS_FINGERPRINT")
    return x

def _same_preserved(a: dict[str, Any], b: dict[str, Any]) -> None:
    for name in ("routes", "active_bindings", "latest_bindings",
                 "active_configuration", "latest_configuration"):
        # After upload, latest comes from a new version and must preserve
        # the original active version's target and configuration, too.
        expected = a["active_bindings"] if "bindings" in name else a["active_configuration"] if "configuration" in name else a["routes"]
        need(b[name] == expected, "PRESERVATION_DRIFT")

def upload_metadata(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Exact Cloudflare Version Upload metadata (the trusted adapter serializes)."""
    validate_snapshot(snapshot)
    need(snapshot["active_bindings"] == snapshot["latest_bindings"]
         and snapshot["active_configuration"] == snapshot["latest_configuration"],
         "LATEST_METADATA_DRIFT")
    cfg = snapshot["active_configuration"]
    return {
        "main_module": "stats-worker.js",
        "compatibility_date": cfg["compatibility_date"],
        "compatibility_flags": sorted(cfg["compatibility_flags"]),
        "bindings": [{"type": "inherit", "name": n, "version_id": "latest"}
                     for n in sorted(KINDS)],
    }

def deployment_payload(version_id: str) -> dict[str, Any]:
    _uuid(version_id, "NEW_VERSION")
    return {"strategy": "percentage",
            "versions": [{"version_id": version_id, "percentage": 100}]}

def _confirm_post_upload(old: dict[str, Any], state: dict[str, Any], new_id: str) -> None:
    validate_snapshot(state, allow_latest_difference=True)
    need(state["active_version"] == old["active_version"]
         and state["latest_uploaded_version"] == new_id
         and state["deployment_id"] == old["deployment_id"]
         and state["active_code_sha256"] == old["active_code_sha256"],
         "POST_UPLOAD_VERSION_DRIFT")
    _same_preserved(old, state)

def _confirm_post_deploy(old: dict[str, Any], state: dict[str, Any], new_id: str) -> None:
    validate_snapshot(state)
    need(state["active_version"] == new_id
         and state["latest_uploaded_version"] == new_id
         and state["deployment_id"] != old["deployment_id"],
         "POST_DEPLOY_VERSION_DRIFT")
    _same_preserved(old, state)

def future_run_once(trusted: Any, approved: Any, worker_bytes: bytes) -> dict[str, str]:
    """Two-state future protocol for an independently installed trusted adapter.

    NOT INVOCABLE from this checkout: there is no transport, token access,
    owner-gate issuer, installer, entrypoint or apply CLI. 'approved' cannot
    independently prove owner authority; the protected runtime must enforce it.
    The adapter must send ONLY exact fixed endpoints, one upload, one deploy,
    with no retry, redirect, fallback, token exposure or hidden mutation.
    """
    need(type(approved) is dict and set(approved) == {
        "source_blob", "config_blob", "worker", "preflight_sha256",
        "allow_upload_once", "allow_deploy_once",
    }, "OWNER_GATE_UNBOUND")
    need(
        approved.get("source_blob") == SOURCE_BLOB
        and approved.get("config_blob") == CONFIG_BLOB
        and approved.get("worker") == WORKER
        and type(approved.get("preflight_sha256")) is str
        and DIGEST.fullmatch(approved["preflight_sha256"]) is not None
        and approved.get("allow_upload_once") is True
        and approved.get("allow_deploy_once") is True,
        "OWNER_GATE_UNBOUND",
    )
    verify_source(worker_bytes)
    try:
        before = validate_snapshot(trusted.read_snapshot())
        confirm = validate_snapshot(trusted.read_snapshot())
    except Exception:
        raise Blocked("PREFLIGHT_READ_FAILED") from None
    need(before == confirm, "PREFLIGHT_STATE_DRIFT")
    need(
        canonical_sha256(
            json.dumps(
                before, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("ascii")
        ) == approved["preflight_sha256"],
        "PREFLIGHT_BINDING_DRIFT",
    )
    meta = upload_metadata(before)
    # FIRST mutation. Once dispatched, any error is terminal: no retry.
    try:
        uploaded = trusted.upload_version_once(
            module_name="stats-worker.js", module_bytes=worker_bytes,
            metadata=meta, bindings_inherit="strict")
    except Exception:
        raise Blocked("UPLOAD_OUTCOME_UNKNOWN_STOP") from None
    need(type(uploaded) is dict and set(uploaded) == {"version_id"},
         "UPLOAD_REPLY_AMBIGUOUS_STOP")
    new_id = _uuid(uploaded["version_id"], "UPLOAD_VERSION_INVALID_STOP")
    need(new_id != before["active_version"], "UPLOAD_VERSION_UNCHANGED_STOP")
    try:
        intermediate = trusted.read_snapshot()
        _confirm_post_upload(before, intermediate, new_id)
        need(intermediate["latest_code_sha256"] == canonical_sha256(worker_bytes),
             "UPLOADED_CODE_NOT_PROVEN")
    except Exception:
        raise Blocked("POST_UPLOAD_UNVERIFIED_STOP") from None
    # SECOND separately authorized stage of the same frozen future envelope.
    try:
        deployment = trusted.deploy_version_once(payload=deployment_payload(new_id))
    except Exception:
        raise Blocked("DEPLOY_OUTCOME_UNKNOWN_STOP") from None
    need(type(deployment) is dict and set(deployment) == {"deployment_id"}
         and type(deployment["deployment_id"]) is str
         and VERSION_ID.fullmatch(deployment["deployment_id"]) is not None,
         "DEPLOY_REPLY_AMBIGUOUS_STOP")
    try:
        after = trusted.read_snapshot()
        _confirm_post_deploy(before, after, new_id)
        need(after["active_code_sha256"] == canonical_sha256(worker_bytes)
             and after["latest_code_sha256"] == canonical_sha256(worker_bytes),
             "DEPLOYED_CODE_NOT_PROVEN")
        need(after["deployment_id"] == deployment["deployment_id"],
             "DEPLOYMENT_ID_UNVERIFIED")
    except Exception:
        raise Blocked("POST_DEPLOY_UNVERIFIED_STOP") from None
    return {"result": "DEPLOY_PROTOCOL_CONFIRMED_NEEDS_RUNTIME_HTTP_PROOF",
            "new_version": new_id}

def main(argv: list[str] | None = None) -> int:
    # No --apply / --deploy / credentials / ad hoc JSON-plan argument.
    if (sys.argv[1:] if argv is None else argv) != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        check_contract(json.loads(CONTRACT_PATH.read_text("utf-8")))
    except (OSError, ValueError, TypeError, Blocked):
        print(STOP)
        return 2
    print("SOURCE_CONTRACT_OK_NOT_LIVE_PROOF")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
