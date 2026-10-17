#!/usr/bin/env python3
"""Report Worker protected operator SOURCE package (#1044).

This file is deliberately NOT an installed operator. No network connections,
credentials, Cloudflare requests, root operations or LIVE entrypoints exist.
Only pinned offline policies, nonexecuting release plans and synthetic replay
checks are provided. Live trust must be supplied by a separately authorized,
independently reviewed protected installation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import ausmalwiese_report_trusted_transport as t

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-report-protected-operator-v1.json"
BASE = "aefd6bd7614cf5a0538c14093224cac22ea78bc1"
STOP = "STOP_REPORT_PROTECTED_OPERATOR_SOURCE_ONLY"
INSTALL_ROOT = "/usr/local/libexec/rpi5-ausmalwiese-report-protected"
LAUNCHER = "/usr/local/sbin/rpi5-ausmalwiese-report-protected"
FILES = {
    "adapter.py": "0644",
    "transport.py": "0644",
    "operator.py": "0644",
    "contract.json": "0644",
    "release.json": "0644",
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class Stop(Exception):
    """Fixed reason only. Never copy external error text to output."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Stop(reason)


def sha_ok(value: Any) -> bool:
    return type(value) is str and SHA256.fullmatch(value) is not None


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def expected_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": "SOURCE_ONLY_NOT_INSTALLED",
        "repository": "rozkalnsandris/RPi5_main",
        "issue": 1044,
        "base_main": BASE,
        "worker": t.WORKER,
        "zone": t.ZONE,
        "account_sha256": t.ACCOUNT_FINGERPRINT,
        "worker_source_sha256": t.SOURCE_SHA256,
        "worker_git_blob": t.SOURCE_BLOB,
        "routes": list(t.ROUTES),
        "binding_kinds": dict(t.KINDS),
        "rates": t.RATES,
        "steps": list(t.STEPS),
        "installation_root": INSTALL_ROOT,
        "launcher": LAUNCHER,
        "files": FILES,
        "rules": {
            "may_install": False,
            "may_send": False,
            "may_read_credentials": False,
            "may_contact_cloudflare": False,
            "may_merge": False,
            "may_live": False,
            "may_retry": False,
            "may_rollback": False,
            "may_cleanup": False,
            "require_separate_root_installer": True,
            "require_separate_private_binding_provider": True,
            "require_authenticated_independent_collector": True,
            "require_owner_authenticated_single_use_gate": True,
        },
    }


def check_contract(value: Any) -> None:
    need(type(value) is dict and value == expected_contract(),
         "CONTRACT_DRIFT")


def verify_worker_bytes(raw: Any) -> str:
    """Verify immutable application Worker bytes; not a Cloudflare proof."""
    need(type(raw) is bytes and 1 <= len(raw) <= 120000, "SOURCE_SIZE")
    sha = hashlib.sha256(raw).hexdigest()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") +
                        b"\x00" + raw).hexdigest()
    need(sha == t.SOURCE_SHA256 and blob == t.SOURCE_BLOB,
         "SOURCE_BYTES_DRIFT")
    return sha


def installation_plan(source_hashes: Any) -> dict[str, Any]:
    """Nonexecuting release layout; supplied hashes are NOT trusted proof.

    A future privileged collector must independently bind the hashes to a
    reviewed exact Git commit, root-owned installed bytes and owner gate.
    """
    need(type(source_hashes) is dict and set(source_hashes) == set(FILES),
         "INSTALL_FILE_SET")
    need(all(sha_ok(value) for value in source_hashes.values()),
         "INSTALL_HASH_FORMAT")
    return {
        "state": "PLAN_ONLY_NOT_INSTALLED",
        "target": t.WORKER,
        "root": INSTALL_ROOT,
        "launcher": LAUNCHER,
        "owner": "root:root",
        "root_mode": "0755",
        "launcher_mode": "0755",
        "files": [
            {"path": INSTALL_ROOT + "/" + name, "sha256": source_hashes[name],
             "mode": FILES[name]}
            for name in FILES
        ],
        "require_root_owned_trusted_ancestors": True,
        "require_no_symlinks_or_hardlinks": True,
        "require_pinned_release_bytes": True,
        "may_install": False,
    }


def validate_install_layout(layout: Any, plan: Any) -> str:
    """Shape-only lstat evidence validation, NEVER proof of actual install."""
    need(type(plan) is dict and plan.get("state") == "PLAN_ONLY_NOT_INSTALLED"
         and plan.get("root") == INSTALL_ROOT
         and plan.get("launcher") == LAUNCHER,
         "INSTALL_PLAN_DRIFT")
    need(type(layout) is dict and set(layout) == {"ancestors", "nodes"},
         "INSTALL_EVIDENCE_FIELDS")
    ancestor_names = ("/", "/usr", "/usr/local", "/usr/local/libexec",
                      "/usr/local/sbin")
    chain = layout["ancestors"]
    need(type(chain) is dict and set(chain) == set(ancestor_names),
         "INSTALL_ANCESTORS")
    for node in chain.values():
        need(type(node) is dict and set(node) == {
            "kind", "uid", "gid", "mode", "symlink",
        } and node["kind"] == "directory" and type(node["uid"]) is int
             and type(node["gid"]) is int and node["uid"] == node["gid"] == 0
             and type(node["mode"]) is int and node["mode"] & 0o022 == 0
             and node["symlink"] is False, "INSTALL_ANCESTOR_UNTRUSTED")
    expected = {INSTALL_ROOT: ("directory", 0o755, None),
                LAUNCHER: ("file", 0o755, None)}
    for entry in plan["files"]:
        expected[entry["path"]] = ("file", int(entry["mode"], 8),
                                    entry["sha256"])
    nodes = layout["nodes"]
    need(type(nodes) is dict and set(nodes) == set(expected),
         "INSTALL_NODE_SET")
    for path, (kind, mode, sha) in expected.items():
        item = nodes[path]
        need(type(item) is dict and set(item) == {
            "kind", "uid", "gid", "mode", "nlink", "symlink", "sha256",
        }, "INSTALL_NODE_FIELDS")
        need(item["kind"] == kind and type(item["uid"]) is int
             and type(item["gid"]) is int and item["uid"] == item["gid"] == 0
             and type(item["mode"]) is int and item["mode"] == mode
             and item["symlink"] is False, "INSTALL_NODE_UNTRUSTED")
        need(type(item["nlink"]) is int and
             (item["nlink"] == 1 if kind == "file"
              else item["nlink"] >= 2), "INSTALL_LINK_COUNT")
        need(item["sha256"] == sha, "INSTALL_DIGEST_DRIFT")
    return "SANITIZED_INSTALL_SHAPE_ONLY_NOT_AUTHORITY"


def https_intent(operation: Any, account_id: Any, zone_id: Any,
                 *, version: Any = None, route: Any = None) -> dict[str, Any]:
    """Fixed-purpose, networkless HTTPS/TLS intent; no HTTP sender or token."""
    request = t.blueprint(operation, account_id, zone_id,
                          version=version, route=route)
    need(request["host"] == "api.cloudflare.com" and
         request["port"] == 443 and request["scheme"] == "https"
         and request["tls_verified"] is True and
         request["method"] == "POST" and
         request["proxy"] is None and request["redirects"] is False
         and request["retries"] == 0, "HTTPS_POLICY_DRIFT")
    return {
        "state": "NOT_DISPATCHABLE_SOURCE_INTENT",
        "request": request,
        "tls_hostname": "api.cloudflare.com",
        "tls_certificate_verification": "REQUIRED",
        "ambient_proxy": "FORBIDDEN",
        "redirects": "FORBIDDEN",
        "automatic_retries": 0,
        "timeout_seconds": 10,
        "maximum_response_bytes": 16384,
        "authorization": "FUTURE_INSTALLED_PRIVATE_PROVIDER_REQUIRED",
    }


def check_provisioning_shape(sanitized: Any) -> str:
    t.validate_provisioning_attestation(sanitized)
    return "SANITIZED_BINDING_SHAPE_ONLY_NOT_AUTHORITY"


def check_version_shape(sanitized: Any, version: Any,
                        unchanged_routes_sha256: Any) -> str:
    t.verify_independent_version(sanitized, version, unchanged_routes_sha256)
    return "SANITIZED_VERSION_SHAPE_ONLY_NOT_AUTHORITY"


def immutable_step(step: Any, owner_gate_sha256: Any,
                   baseline_sha256: Any,
                   previous_proof_sha256: Any = None) -> dict[str, str]:
    """Create a synthetic six-step replay fingerprint.

    A SHA-256 looking owner gate is not owner authentication. This is only an
    offline format for a future separately reviewed root-owned journal.
    """
    need(type(step) is int and 0 <= step < len(t.STEPS), "STEP_OUT_OF_SCOPE")
    need(sha_ok(owner_gate_sha256) and sha_ok(baseline_sha256),
         "OWNER_OR_BASELINE_FORMAT")
    need((previous_proof_sha256 is None if step == 0
          else sha_ok(previous_proof_sha256)), "PRIOR_PROOF_FORMAT")
    envelope = {
        "operation": t.STEPS[step],
        "step": step,
        "worker": t.WORKER,
        "account_sha256": t.ACCOUNT_FINGERPRINT,
        "source_sha256": t.SOURCE_SHA256,
        "routes": list(t.ROUTES),
        "owner_gate_sha256": owner_gate_sha256,
        "baseline_sha256": baseline_sha256,
        "previous_proof_sha256": previous_proof_sha256,
    }
    return {
        "step": t.STEPS[step],
        "sha256": hashlib.sha256(canonical(envelope)).hexdigest(),
        "state": "SYNTHETIC_ENVELOPE_NOT_OWNER_AUTHORITY",
    }


def synthetic_reserve(journal: t.OfflineDurableGate, index: int,
                      envelope: dict[str, str],
                      previous_proof_sha256: str | None = None) -> str:
    need(type(journal) is t.OfflineDurableGate
         and type(envelope) is dict
         and envelope.get("state") == "SYNTHETIC_ENVELOPE_NOT_OWNER_AUTHORITY"
         and envelope.get("step") == t.STEPS[index]
         and sha_ok(envelope.get("sha256")), "OFFLINE_JOURNAL_ONLY")
    return journal.reserve(index, envelope["sha256"], previous_proof_sha256)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        check_contract(json.loads(CONTRACT.read_text(encoding="utf-8")))
    except (Stop, OSError, TypeError, ValueError):
        print(STOP)
        return 2
    print("REPORT_PROTECTED_OPERATOR_SOURCE_OK_NOT_INSTALLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
