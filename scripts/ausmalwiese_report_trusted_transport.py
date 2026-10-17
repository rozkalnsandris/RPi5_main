#!/usr/bin/env python3
"""Report-only sealed HTTPS transport *source contract*, not a live client (#1042).

This module NEVER connects to the network, reads a credential or dispatches a
Cloudflare mutation. A separate, installed, owner-authorized protected adapter
must supply a TLS-verified channel and private binding provisioner in future.
The durable journal primitives below are exercised ONLY with temporary files
by offline tests. They are not a privileged installer or owner authorization.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-report-trusted-transport-v1.json"
WORKER = "coloring-pages-report-v1"
ZONE = "ausmalwiese.de"
HOST = "api.cloudflare.com"
ACCOUNT_FINGERPRINT = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
SOURCE_SHA256 = "26d4e597d8c2c961c3a637957ea566654c97c5657a4b2595129c410e9fae22a1"
SOURCE_BLOB = "6d2359752d12f4a40847008fc7fdcc457124e893"
PATHS = {
    "upload": "/client/v4/accounts/{account_id}/workers/scripts/coloring-pages-report-v1/versions",
    "deploy": "/client/v4/accounts/{account_id}/workers/scripts/coloring-pages-report-v1/deployments",
    "route": "/client/v4/zones/{zone_id}/workers/routes",
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
RATES = {"REPORT_RATE": {"limit": 12, "period": 60},
         "REPORT_DUP": {"limit": 1, "period": 60}}
SECRET_NAMES = ("BREVO_API_KEY", "REPORT_TO", "TURNSTILE_SECRET")
STEPS = ("upload", "deploy") + tuple("route:" + route for route in ROUTES)
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
DECIMAL = re.compile(r"[1-9][0-9]{0,9}\Z")
STOP = "STOP_REPORT_TRUSTED_TRANSPORT_SOURCE_ONLY"


class Stop(Exception):
    """Only fixed non-sensitive error codes. Never embed external values."""


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise Stop(reason)


def expected_contract() -> dict[str, Any]:
    return {
        "schema_version": 1, "state": "SOURCE_ONLY_NOT_INSTALLED",
        "repository": "rozkalnsandris/RPi5_main", "issue": 1042,
        "base_main": "ca027eb96287a996b3b28ff292860b4f933296e6",
        "worker": WORKER, "zone": ZONE,
        "account_sha256": ACCOUNT_FINGERPRINT,
        "source": {
            "repo": "rozkalnsandris/coloring-pages",
            "commit": "a90c6a6a7ccca2941d99e9edddd5cfa31ac9ed18",
            "path": "cloudflare/report-worker.mjs",
            "blob": SOURCE_BLOB, "sha256": SOURCE_SHA256,
        },
        "host": HOST, "port": 443,
        "protocol": "HTTPS_TLS_VERIFIED_REQUIRED_NO_AMBIENT_PROXY",
        "methods": {"upload": "POST", "deploy": "POST", "route": "POST"},
        "paths": PATHS, "routes": list(ROUTES),
        "bindings": KINDS, "rates": RATES,
        "private_secret_names": list(SECRET_NAMES),
        "intent_sequence": list(STEPS),
        "constraints": {
            "allow_cli_send": False, "allow_in_checkout_network": False,
            "allow_credential_access": False, "allow_secret_values_in_source": False,
            "allow_live": False, "allow_merge": False, "allow_retry": False,
            "allow_rollback": False, "allow_cleanup": False,
            "allow_legacy_put": False,
            "require_durable_reservation_before_send": True,
            "require_independent_verified_proof_between_steps": True,
            "require_private_provisioner_future_gate": True,
        },
    }


def check_contract(obj: Any) -> None:
    need(type(obj) is dict and obj == expected_contract(), "CONTRACT_DRIFT")


def sha_ok(value: Any) -> bool:
    return type(value) is str and HEX64.fullmatch(value) is not None


def account_guard(account_id: Any) -> None:
    need(type(account_id) is str and HEX32.fullmatch(account_id) is not None,
         "ACCOUNT_FORMAT")
    need(hashlib.sha256(account_id.encode("ascii")).hexdigest() ==
         ACCOUNT_FINGERPRINT, "ACCOUNT_IDENTITY_DRIFT")


def zone_guard(zone_id: Any) -> None:
    # Format is NOT identity. Future authenticated collector must prove zone.
    need(type(zone_id) is str and HEX32.fullmatch(zone_id) is not None, "ZONE_FORMAT")


def blueprint(operation: str, account_id: str, zone_id: str,
              *, version: str | None = None, route: str | None = None) -> dict[str, Any]:
    """Networkless exact HTTPS blueprint; never contains credentials/secrets."""
    account_guard(account_id)
    zone_guard(zone_id)
    need(type(operation) is str and operation in PATHS, "OPERATION_DENIED")
    if operation == "upload":
        need(version is None and route is None, "UPLOAD_ARGS")
        body = None
        policy = "SEALED_MULTIPART_NOT_AVAILABLE_IN_THIS_SOURCE"
    elif operation == "deploy":
        need(route is None and type(version) is str
             and UUID.fullmatch(version) is not None, "VERSION_ARGS")
        body = {"strategy": "percentage",
                "versions": [{"version_id": version, "percentage": 100}]}
        policy = "CANONICAL_JSON"
    else:
        need(version is None and type(route) is str and route in ROUTES,
             "ROUTE_ARGS")
        body = {"pattern": route, "script": WORKER}
        policy = "CANONICAL_JSON"
    path = PATHS[operation].format(account_id=account_id, zone_id=zone_id)
    need(path.startswith("/client/v4/") and
         not any(c in path for c in ("?", "#", "\\", "\r", "\n")), "PATH_DRIFT")
    return {"scheme": "https", "host": HOST, "port": 443,
            "tls_verified": True, "proxy": None, "redirects": False,
            "retries": 0, "method": "POST", "path": path,
            "body_policy": policy, "body": body}


def inspect_https_reply(operation: str, status: Any, headers: Any,
                        response_body: Any, *, route: str | None = None) -> dict[str, str]:
    """Parse only small JSON API responses; never return errors, headers or raw body.

    Caller MUST be a separately audited authenticated HTTPS collector; data
    passed directly from a fake/untrusted object is not provider evidence.
    """
    need(type(operation) is str and operation in PATHS, "REPLY_OPERATION")
    need(type(status) is int and status in (200, 201), "REPLY_HTTP_STATUS")
    need(type(headers) is dict and set(headers) == {"content-type"}
         and type(headers["content-type"]) is str
         and headers["content-type"].lower().split(";")[0].strip() ==
         "application/json", "REPLY_CONTENT_TYPE")
    need(type(response_body) is bytes and 1 <= len(response_body) <= 16384,
         "REPLY_BODY_SIZE")
    try:
        packet = json.loads(response_body.decode("utf-8"),
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError):
        raise Stop("REPLY_JSON_INVALID") from None
    need(type(packet) is dict and set(packet) == {
        "success", "errors", "messages", "result",
    } and packet["success"] is True and packet["errors"] == []
         and packet["messages"] == [] and type(packet["result"]) is dict,
         "REPLY_NOT_SUCCESS")
    result = packet["result"]
    if operation in ("upload", "deploy"):
        need(type(result.get("id")) is str
             and UUID.fullmatch(result["id"]) is not None, "REPLY_ID_INVALID")
        return {("version_id" if operation == "upload" else "deployment_id"): result["id"]}
    need(type(route) is str and route in ROUTES
         and result.get("pattern") == route and result.get("script") == WORKER
         and type(result.get("id")) is str and HEX32.fullmatch(result["id"]) is not None,
         "REPLY_ROUTE_INVALID")
    return {"route": route, "worker": WORKER}


def validate_provisioning_attestation(proof: Any) -> dict[str, str]:
    """Only inspect NON-SENSITIVE evidence from *future protected provisioner*.

    No secret values, API keys, recipient addresses or public site key are
    accepted. Attestation can be forged: never authorize operations from it.
    """
    need(type(proof) is dict and set(proof) == {
        "source", "binding_kinds", "rate_limits", "namespace_ids",
        "sealed_private_names", "sitekey_hostname_set", "siteverify_action",
        "private_provider_ready", "account_verified", "zone_verified",
        "atomic_version_upload_capability", "no_reusable_secret_in_evidence",
    }, "PROVISION_FIELDS")
    need(proof["source"] == SOURCE_SHA256 and
         proof["binding_kinds"] == KINDS and proof["rate_limits"] == RATES,
         "PROVISION_POLICY_DRIFT")
    need(type(proof["sealed_private_names"]) is list
         and sorted(proof["sealed_private_names"]) == list(SECRET_NAMES),
         "PRIVATE_NAMES_DRIFT")
    need(proof["sitekey_hostname_set"] == ["ausmalwiese.de", "www.ausmalwiese.de"]
         and proof["siteverify_action"] == "report", "TURNSTILE_POLICY_DRIFT")
    for k in ("private_provider_ready", "account_verified", "zone_verified",
              "atomic_version_upload_capability", "no_reusable_secret_in_evidence"):
        need(proof[k] is True, "PROVISION_CAPABILITY_NOT_PROVEN")
    ids = proof["namespace_ids"]
    need(type(ids) is dict and set(ids) == {"REPORT_RATE", "REPORT_DUP"},
         "NAMESPACE_SET")
    for val in ids.values():
        need(type(val) is str and DECIMAL.fullmatch(val) is not None
             and int(val) <= 4294967295, "NAMESPACE_FORMAT")
    need(ids["REPORT_RATE"] != ids["REPORT_DUP"], "NAMESPACE_COLLISION")
    return {"result": "SANITIZED_PROVISIONING_SHAPE_OK_NOT_AUTHORITY"}


def verify_independent_version(proof: Any, expected_version: Any,
                               protected_routes_digest: str) -> dict[str, str]:
    """Validate sanitized read-only collector *shape*, NOT collector identity.

    Never trust this alone: protected adapter must authenticate the collector,
    GET full version/code and binding evidence from actual Cloudflare account.
    """
    need(type(proof) is dict and set(proof) == {
        "collector", "account_sha256", "zone", "worker", "version",
        "active_version", "source_sha256", "source_git_blob",
        "binding_kinds", "rates", "namespace_ids",
        "unrelated_routes_sha256", "report_routes",
    }, "VERSION_PROOF_FIELDS")
    need(proof["collector"] == "INDEPENDENT_AUTHENTICATED_READ_ONLY_COLLECTOR"
         and proof["account_sha256"] == ACCOUNT_FINGERPRINT
         and proof["zone"] == ZONE and proof["worker"] == WORKER,
         "VERSION_TARGET_DRIFT")
    need(type(expected_version) is str and UUID.fullmatch(expected_version) is not None
         and proof["version"] == expected_version
         and proof["active_version"] == expected_version, "VERSION_NOT_ACTIVE")
    need(proof["source_sha256"] == SOURCE_SHA256
         and proof["source_git_blob"] == SOURCE_BLOB
         and sha_ok(protected_routes_digest)
         and proof["unrelated_routes_sha256"] == protected_routes_digest,
         "VERSION_OR_UNRELATED_CODE_DRIFT")
    need(proof["binding_kinds"] == KINDS and proof["rates"] == RATES,
         "VERSION_BINDINGS_DRIFT")
    ids = proof["namespace_ids"]
    need(type(ids) is dict and set(ids) == {"REPORT_RATE", "REPORT_DUP"},
         "VERSION_NAMESPACE_FIELDS")
    for val in ids.values():
        need(type(val) is str and DECIMAL.fullmatch(val) is not None and
             int(val) <= 4294967295, "VERSION_NAMESPACE_FORMAT")
    need(ids["REPORT_RATE"] != ids["REPORT_DUP"], "VERSION_NAMESPACE_COLLISION")
    routes = proof["report_routes"]
    need(type(routes) is dict and set(routes).issubset(set(ROUTES))
         and all(worker == WORKER for worker in routes.values()),
         "VERSION_ROUTES_DRIFT")
    return {"result": "SANITIZED_VERSION_SHAPE_OK_NOT_LIVE_PROOF",
            "version": expected_version}


class OfflineDurableGate:
    """Local durable replay semantics, only for synthetic offline tests.

    No authenticated owner gate, no Cloudflare sender, no privileged installer.
    A future protected root-owned journal requires separate audit and LIVE
    approval. This class refuses operation unless explicitly in test mode.
    """

    def __init__(self, root: Path, *, synthetic_test_only: bool = False) -> None:
        need(synthetic_test_only is True, "INSTALLED_GATE_NOT_PROVIDED")
        need(type(root) is Path and not root.is_symlink(), "JOURNAL_ROOT")
        try:
            metadata = root.lstat()
            need(stat.S_ISDIR(metadata.st_mode)
                 and metadata.st_uid == os.getuid()
                 and metadata.st_mode & 0o077 == 0, "JOURNAL_DIR_UNTRUSTED")
        except OSError:
            raise Stop("JOURNAL_DIR_UNAVAILABLE") from None
        self.root = root

    def _name(self, index: int, state: str) -> str:
        need(type(index) is int and 0 <= index < len(STEPS)
             and state in ("reserved", "verified"), "JOURNAL_STEP")
        return "step-%02d.%s" % (index, state)

    def _read(self, name: str) -> str:
        directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=directory_fd)
            try:
                s = os.fstat(fd)
                need(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid()
                     and stat.S_IMODE(s.st_mode) == 0o600 and s.st_nlink == 1
                     and s.st_size == 65, "JOURNAL_RECORD_TAMPER")
                raw = os.read(fd, 66)
            finally:
                os.close(fd)
        except OSError:
            raise Stop("JOURNAL_PREVIOUS_MISSING") from None
        finally:
            os.close(directory_fd)
        try:
            value = raw.decode("ascii")
        except UnicodeError:
            raise Stop("JOURNAL_RECORD_TAMPER") from None
        need(len(value) == 65 and value.endswith("\n")
             and sha_ok(value[:-1]), "JOURNAL_RECORD_TAMPER")
        return value[:-1]

    def _create_once(self, name: str, fingerprint: str) -> None:
        need(sha_ok(fingerprint), "JOURNAL_DIGEST")
        directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_CLOEXEC, 0o600,
                             dir_fd=directory_fd)
            except OSError:
                raise Stop("JOURNAL_ALREADY_RESERVED_OR_UNAVAILABLE") from None
            try:
                data = (fingerprint + "\n").encode("ascii")
                need(os.write(fd, data) == len(data), "JOURNAL_SHORT_WRITE")
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def reserve(self, step: int, envelope_sha256: str,
                previous_proof_sha256: str | None = None) -> str:
        need(sha_ok(envelope_sha256), "JOURNAL_ENVELOPE")
        self._name(step, "reserved")
        if step:
            need(sha_ok(previous_proof_sha256), "JOURNAL_PREVIOUS_PROOF")
            need(self._read(self._name(step - 1, "verified")) ==
                 previous_proof_sha256, "JOURNAL_PREVIOUS_DRIFT")
        else:
            need(previous_proof_sha256 is None, "JOURNAL_FIRST_STEP_PROOF")
        # Persists BEFORE future sending: a crash now forever prevents retry.
        self._create_once(self._name(step, "reserved"), envelope_sha256)
        return STEPS[step]

    def mark_verified(self, step: int, envelope_sha256: str,
                      independent_proof_sha256: str) -> None:
        need(sha_ok(independent_proof_sha256)
             and self._read(self._name(step, "reserved")) == envelope_sha256,
             "JOURNAL_VERIFICATION_DRIFT")
        # In tests, proof is synthetic. A real collector must independently
        # attest that the just-sent step succeeded before writing this record.
        self._create_once(self._name(step, "verified"), independent_proof_sha256)


def main(argv: list[str] | None = None) -> int:
    if (sys.argv[1:] if argv is None else argv) != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        check_contract(json.loads(CONTRACT.read_text(encoding="utf-8")))
    except (OSError, ValueError, Stop, TypeError):
        print(STOP)
        return 2
    print("REPORT_TRUSTED_TRANSPORT_SOURCE_OK_NOT_LIVE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
