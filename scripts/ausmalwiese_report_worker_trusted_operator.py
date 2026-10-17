#!/usr/bin/env python3
"""Source-only report Worker deployment protocol core (#1036).

NO authenticated transport, installer, live CLI, credential access, secret
provisioning or host/Cloudflare changes. An independently reviewed trusted
adapter and fresh exact-target owner LIVE authority are always required.
Synthetic inputs are NOT Cloudflare, Brevo, Turnstile or legal evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops/contracts/ausmalwiese-report-worker-trusted-operator-v1.json"
STOP = "STOP_REPORT_WORKER_SOURCE_ONLY"
TARGET = {
    "account_sha256": "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34",
    "zone": "ausmalwiese.de",
    "worker": "coloring-pages-report-v1",
    "environment": "production",
}
SOURCE = {
    "repository": "rozkalnsandris/coloring-pages",
    "commit": "a90c6a6a7ccca2941d99e9edddd5cfa31ac9ed18",
    "path": "cloudflare/report-worker.mjs",
    "blob": "6d2359752d12f4a40847008fc7fdcc457124e893",
    "sha256": "26d4e597d8c2c961c3a637957ea566654c97c5657a4b2595129c410e9fae22a1",
}
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
PROTECTED_ROUTES = (
    "ausmalwiese.de/api/stats/*",
    "www.ausmalwiese.de/api/stats/*",
    "ausmalwiese.de/q",
)
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
NAMESPACE = re.compile(r"[1-9][0-9]{0,9}\Z")


class Blocked(Exception):
    """An intentionally non-sensitive fixed operator failure code."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def contract_expected() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": "SOURCE_CORE_NOT_INSTALLED_NO_AUTH_TRANSPORT",
        "repository": "rozkalnsandris/RPi5_main",
        "issue": 1036,
        "target": TARGET,
        "source": SOURCE,
        "report_routes": list(ROUTES),
        "binding_kinds": KINDS,
        "rate_limits": LIMITS,
        "protected_routes": list(PROTECTED_ROUTES),
        "mode": "PURE_PROTOCOL_FUTURE_PROTECTED_ADAPTER_ONLY",
        "owner_live_approval": False,
        "merge_approval": False,
        "credential_access": False,
        "settings_access": False,
        "host_mutation": False,
        "allow_retry": False,
        "allow_rollback": False,
        "allow_cleanup": False,
    }


def check_contract(value: Any) -> None:
    need(type(value) is dict and value == contract_expected(), "CONTRACT_DRIFT")


def load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def verify_source(raw: Any) -> None:
    need(type(raw) is bytes and 0 < len(raw) <= 120000, "SOURCE_SIZE")
    digest = hashlib.sha256(raw).hexdigest()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw).hexdigest()
    need(digest == SOURCE["sha256"] and blob == SOURCE["blob"], "SOURCE_BYTES_DRIFT")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise Blocked("SOURCE_ENCODING") from None
    need('const BREVO_URL = "https://api.brevo.com/v3/smtp/email";' in text
         and 'const REPORT_FROM = ' in text
         and '"/api/report/config"' in text
         and '"/api/report"' in text, "SOURCE_CONTRACT_DRIFT")


def _uuid(value: Any, reason: str) -> None:
    need(type(value) is str and UUID.fullmatch(value) is not None, reason)


def _sha(value: Any, reason: str) -> None:
    need(type(value) is str and SHA256.fullmatch(value) is not None, reason)


def _namespace(value: Any) -> None:
    need(type(value) is str and NAMESPACE.fullmatch(value) is not None
         and int(value) <= 4294967295, "NAMESPACE_INVALID")


def validate_snapshot(value: Any, stage: str, expected_routes: tuple[str, ...] = ()) -> dict[str, Any]:
    """Accept only synthetic-shape / sanitized protected-collector metadata.

    A forged dict can pass. Only a separately installed protected collector
    can establish account identity, actual bindings, permission and legal
    approvals, all outside this source module. Never supply secret values.
    """
    need(type(value) is dict and set(value) == {
        "schema", "target", "proof", "worker_exists", "active_version",
        "latest_uploaded_version", "deployment_id", "traffic_percent",
        "active_code_sha256", "latest_code_sha256", "binding_kinds",
        "rate_limits", "namespace_ids", "report_routes",
        "unrelated_routes_sha256",
    }, "SNAPSHOT_FIELDS")
    need(value["schema"] == "ausmalwiese.report-worker.sanitized-snapshot.v1"
         and value["target"] == TARGET, "SNAPSHOT_TARGET")
    proof = value["proof"]
    need(type(proof) is dict and proof == {
        "account_verified": True,
        "zone_verified": True,
        "operator_capability_verified": True,
        "turnstile_hostnames_verified": True,
        "brevo_account_eligibility_verified": True,
        "protected_binding_provisioner_ready": True,
        "privacy_review_completed": True,
        "unrelated_routes_inventory_verified": True,
    }, "SNAPSHOT_PROOF_NOT_VERIFIED")
    _sha(value["unrelated_routes_sha256"], "UNRELATED_ROUTES_NOT_PROVEN")
    routes = value["report_routes"]
    need(type(routes) is dict
         and list(routes) == list(expected_routes)
         and all(routes[route] == TARGET["worker"] for route in routes)
         and all(route in ROUTES for route in routes), "ROUTES_DRIFT")
    missing = stage == "absent"
    uploaded = stage == "uploaded"
    active = stage == "active"
    need(missing or uploaded or active, "UNKNOWN_STAGE")
    need(type(value["worker_exists"]) is bool
         and value["worker_exists"] is not missing, "WORKER_STAGE")
    if missing:
        need(all(value[key] is None for key in (
            "active_version", "latest_uploaded_version", "deployment_id",
            "traffic_percent", "active_code_sha256", "latest_code_sha256"))
            and value["binding_kinds"] == {}
            and value["rate_limits"] == {}
            and value["namespace_ids"] == {}, "WORKER_PREEXISTS_OR_BINDINGS_DRIFT")
        need(not expected_routes, "ABSENT_WORKER_ROUTES")
    else:
        _uuid(value["latest_uploaded_version"], "LATEST_VERSION")
        _sha(value["latest_code_sha256"], "LATEST_SOURCE")
        need(value["binding_kinds"] == KINDS, "BINDING_NAMES_OR_KINDS_DRIFT")
        need(value["rate_limits"] == LIMITS, "RATE_POLICY_DRIFT")
        namespaces = value["namespace_ids"]
        need(type(namespaces) is dict
             and set(namespaces) == {"REPORT_RATE", "REPORT_DUP"}, "NAMESPACE_NAMES_DRIFT")
        for namespace in namespaces.values():
            _namespace(namespace)
        need(namespaces["REPORT_RATE"] != namespaces["REPORT_DUP"], "NAMESPACE_COLLISION")
        if uploaded:
            need(value["active_version"] is None
                 and value["deployment_id"] is None
                 and value["traffic_percent"] is None
                 and value["active_code_sha256"] is None, "UNEXPECTED_EARLY_DEPLOY")
        else:
            _uuid(value["active_version"], "ACTIVE_VERSION")
            _uuid(value["deployment_id"], "DEPLOYMENT_ID")
            need(value["active_version"] == value["latest_uploaded_version"]
                 and type(value["traffic_percent"]) is int
                 and value["traffic_percent"] == 100, "ACTIVE_TRAFFIC_DRIFT")
            _sha(value["active_code_sha256"], "ACTIVE_SOURCE")
            need(value["active_code_sha256"] == value["latest_code_sha256"],
                 "ACTIVE_LATEST_SOURCE_DRIFT")
    return value


def upload_intent() -> dict[str, Any]:
    """Only allowed fields sent to future trusted adapter; never secret values."""
    return {
        "target": dict(TARGET),
        "main_module": "report-worker.mjs",
        "source": dict(SOURCE),
        "expected_binding_kinds": dict(KINDS),
        "rate_limits": {name: dict(value) for name, value in LIMITS.items()},
        "report_routes": list(ROUTES),
        "secret_values_in_source": False,
    }


def future_protocol(trusted: Any, approval: Any, source_bytes: bytes) -> dict[str, str]:
    """Non-CLI future protocol: unit tests inject an in-memory fake adapter.

    THIS IS NOT LIVE AUTHORITY. The separately reviewed protected adapter
    must authenticate its exact owner gate, check immutable provenance and
    permissions before any real mutation and manage private secrets outside
    this module. Never use it as a generic Cloudflare API client.
    """
    need(approval == {
        "worker": TARGET["worker"], "zone": TARGET["zone"],
        "source_blob": SOURCE["blob"], "upload_once": True,
        "deploy_once": True, "add_four_exact_routes_once": True,
    } and type(approval) is dict, "OWNER_ENVELOPE_NOT_FROZEN")
    check_contract(load_contract())
    verify_source(source_bytes)
    try:
        before = validate_snapshot(trusted.read_sanitized(), "absent")
        again = validate_snapshot(trusted.read_sanitized(), "absent")
    except Exception:
        raise Blocked("PREFLIGHT_UNAVAILABLE_STOP") from None
    need(before == again, "PREFLIGHT_DRIFT_STOP")
    stable_routes_sha = before["unrelated_routes_sha256"]

    # FIRST dispatch. There are no retries, fallbacks or cleanup after it.
    # The future protected adapter alone handles secret provisioner integration.
    try:
        reply = trusted.upload_report_version_once(
            module_name="report-worker.mjs", module_bytes=source_bytes,
            intent=upload_intent())
    except Exception:
        raise Blocked("UPLOAD_OUTCOME_UNKNOWN_STOP") from None
    need(type(reply) is dict and set(reply) == {"version_id"},
         "UPLOAD_REPLY_AMBIGUOUS_STOP")
    new_version = reply["version_id"]
    _uuid(new_version, "UPLOAD_VERSION_INVALID_STOP")
    try:
        staged = validate_snapshot(trusted.read_sanitized(), "uploaded")
        need(staged["latest_uploaded_version"] == new_version
             and staged["latest_code_sha256"] == SOURCE["sha256"]
             and staged["unrelated_routes_sha256"] == stable_routes_sha,
             "UPLOAD_UNVERIFIED")
    except Exception:
        raise Blocked("POST_UPLOAD_UNVERIFIED_STOP") from None

    try:
        deploy_reply = trusted.deploy_report_version_once(version_id=new_version,
                                                         traffic_percent=100)
    except Exception:
        raise Blocked("DEPLOY_OUTCOME_UNKNOWN_STOP") from None
    need(type(deploy_reply) is dict and set(deploy_reply) == {"deployment_id"},
         "DEPLOY_REPLY_AMBIGUOUS_STOP")
    _uuid(deploy_reply["deployment_id"], "DEPLOY_ID_INVALID_STOP")
    try:
        deployed = validate_snapshot(trusted.read_sanitized(), "active")
        need(deployed["latest_uploaded_version"] == new_version
             and deployed["active_code_sha256"] == SOURCE["sha256"]
             and deployed["deployment_id"] == deploy_reply["deployment_id"]
             and deployed["unrelated_routes_sha256"] == stable_routes_sha,
             "DEPLOY_UNVERIFIED")
    except Exception:
        raise Blocked("POST_DEPLOY_UNVERIFIED_STOP") from None

    for index, route in enumerate(ROUTES):
        try:
            route_reply = trusted.add_exact_report_route_once(route=route,
                                                              worker=TARGET["worker"])
        except Exception:
            raise Blocked("ROUTE_OUTCOME_UNKNOWN_STOP") from None
        need(route_reply == {"route": route, "worker": TARGET["worker"]},
             "ROUTE_REPLY_AMBIGUOUS_STOP")
        expected = ROUTES[:index + 1]
        try:
            state = validate_snapshot(trusted.read_sanitized(), "active", expected)
            need(state["active_version"] == new_version
                 and state["deployment_id"] == deploy_reply["deployment_id"]
                 and state["active_code_sha256"] == SOURCE["sha256"]
                 and state["unrelated_routes_sha256"] == stable_routes_sha,
                 "ROUTE_UNVERIFIED")
        except Exception:
            raise Blocked("POST_ROUTE_UNVERIFIED_STOP") from None

    return {"result": "FUTURE_PROTOCOL_FINISHED_NEEDS_INDEPENDENT_HTTP_AND_MAIL_PROOF",
            "source_sha256": SOURCE["sha256"]}


def main(argv: list[str] | None = None) -> int:
    # No --apply, --deploy, --upload, URL, token, credential or plan-file args.
    if (sys.argv[1:] if argv is None else argv) != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        check_contract(load_contract())
    except (Blocked, KeyError, ValueError, OSError, TypeError):
        print(STOP)
        return 2
    print("SOURCE_CONTRACT_OK_NOT_LIVE_PROOF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
