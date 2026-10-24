#!/usr/bin/env python3
"""Pure source-only #1211 protocol; NO CLI, network, secrets or host access.

A separate, root-owned future adapter must authenticate the provider, enforce
an independent exact owner LIVE gate, and consume one-shot write budgets.
"""
from __future__ import annotations
import hashlib
import json
import re

WORKER = "coloring-pages-stats-v1"
ZONE = "ausmalwiese.de"
BINDING = "CF_ZONE_TAG"
SOURCE_BLOB = "8790a8ddc3b83771088c4cceb16a3b57ce5d1c8b"
CONFIG_BLOB = "3733263a391274f2b6b0f2023c8656565bde8e1a"
CODE_SHA = "47f7490918d25e8f1dcc683cebe3c4d3d9a75230f33ae5a1d26cbd6bd3ec1173"
ID32 = re.compile("[0-9a-f]{32}\\Z")
SHA64 = re.compile("[0-9a-f]{64}\\Z")
UUID = re.compile("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\Z")


class Blocked(Exception):
    """Only fixed, public-safe error categories."""


def need(condition, code):
    if not condition:
        raise Blocked(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def checked_before(core, trusted, source):
    need(type(source) is bytes and hashlib.sha256(source).hexdigest() == CODE_SHA,
         "SOURCE_SHA_DRIFT")
    try:
        core.verify_source(source)
        # verified_zone_id MUST independently prove official zone name, active
        # status and allowlisted ID via authenticated provider API.
        zone = trusted.verified_zone_id(ZONE)
        first = core.validate_snapshot(trusted.read_snapshot())
        zone_again = trusted.verified_zone_id(ZONE)
        second = core.validate_snapshot(trusted.read_snapshot())
    except Exception:
        raise Blocked("PROVENANCE_OR_PROVIDER_READ_STOP") from None
    need(type(zone) is str and ID32.fullmatch(zone) is not None and
         zone == zone_again, "ZONE_IDENTITY_STOP")
    need(first == second, "DOUBLE_READ_DRIFT")
    need(first["active_version"] == first["latest_uploaded_version"] and
         first["active_bindings"] == first["latest_bindings"] and
         first["active_configuration"] == first["latest_configuration"],
         "ACTIVE_LATEST_DRIFT")
    need(first["active_code_sha256"] == first["latest_code_sha256"] == CODE_SHA,
         "PROVIDER_CODE_DRIFT")
    target_hash = hashlib.sha256(zone.encode("ascii")).hexdigest()
    need(first["active_bindings"][BINDING]["fingerprint"] != target_hash,
         "ZONE_ALREADY_CORRECT_NO_WRITE")
    return first, zone, target_hash


def preflight(core, trusted, source):
    before, _, _ = checked_before(core, trusted, source)
    return {"schema": "rozkalns.stats-zone-binding-preflight.v1",
            "status": "PASS", "worker": WORKER,
            "active_version": before["active_version"],
            "snapshot_sha256": digest(before), "zone_mismatch": True,
            "candidate_sha256": CODE_SHA, "provider_writes": 0}


def preserved_bindings(old, new, target_hash):
    need(set(old) == set(new), "BINDING_SET_CHANGED")
    for name, desc in old.items():
        want = {"kind": "plain_text", "fingerprint": target_hash} if name == BINDING else desc
        need(new[name] == want, "BINDING_PRESERVATION_FAILED")


def verify_after(core, before, state, version, zone_hash, *, deployed, deployment=None):
    core.validate_snapshot(state, allow_latest_difference=not deployed)
    need(state["routes"] == before["routes"] and
         state["active_configuration"] == state["latest_configuration"] ==
         before["active_configuration"], "CONFIG_OR_ROUTES_CHANGED")
    need(state["active_code_sha256"] == state["latest_code_sha256"] == CODE_SHA,
         "WORKER_CODE_CHANGED")
    need(state["latest_uploaded_version"] == version and
         state["traffic_percent"] == 100, "LATEST_OR_TRAFFIC_DRIFT")
    if deployed:
        need(state["active_version"] == version and
             state["deployment_id"] == deployment and
             deployment != before["deployment_id"], "DEPLOY_PROOF_FAILED")
        preserved_bindings(before["active_bindings"], state["active_bindings"], zone_hash)
        preserved_bindings(before["active_bindings"], state["latest_bindings"], zone_hash)
    else:
        need(state["active_version"] == before["active_version"] and
             state["deployment_id"] == before["deployment_id"] and
             state["active_bindings"] == before["active_bindings"],
             "POST_UPLOAD_ACTIVE_DRIFT")
        preserved_bindings(before["active_bindings"], state["latest_bindings"], zone_hash)


def apply_once(core, trusted, source, approval):
    """Future installed trust boundary ONLY; approval dict is not owner identity."""
    keys = {"worker", "source_blob", "config_blob", "candidate_sha256",
            "active_version", "preflight_sha256", "allow_upload_once", "allow_deploy_once"}
    need(type(approval) is dict and set(approval) == keys and
         approval["worker"] == WORKER and
         approval["source_blob"] == SOURCE_BLOB and
         approval["config_blob"] == CONFIG_BLOB and
         approval["candidate_sha256"] == CODE_SHA and
         type(approval["active_version"]) is str and
         UUID.fullmatch(approval["active_version"]) is not None and
         type(approval["preflight_sha256"]) is str and
         SHA64.fullmatch(approval["preflight_sha256"]) is not None and
         approval["allow_upload_once"] is True and
         approval["allow_deploy_once"] is True, "OWNER_ENVELOPE_INVALID")
    before, zone, target_hash = checked_before(core, trusted, source)
    need(approval["active_version"] == before["active_version"] and
         approval["preflight_sha256"] == digest(before), "APPROVED_SNAPSHOT_DRIFT")
    metadata = core.upload_metadata(before)
    need(set(metadata) == {"main_module", "compatibility_date",
         "compatibility_flags", "bindings"}, "METADATA_DRIFT")
    inherited = metadata["bindings"]
    need(type(inherited) is list and len(inherited) == 7 and
         {b.get("name") for b in inherited} == set(before["active_bindings"]) and
         all(set(b) == {"name", "type", "version_id"} and
             b["type"] == "inherit" and b["version_id"] == "latest"
             for b in inherited), "STRICT_INHERIT_DRIFT")
    metadata["bindings"] = [
        {"name": BINDING, "type": "plain_text", "text": zone}
        if b["name"] == BINDING else dict(b) for b in inherited]
    # First provider write. No retry, rollback, cleanup or fallback after dispatch.
    try:
        result = trusted.upload_version_once(module_name="stats-worker.js",
             module_bytes=source, metadata=metadata, bindings_inherit="strict")
    except Exception:
        raise Blocked("UPLOAD_OUTCOME_UNKNOWN_STOP") from None
    need(type(result) is dict and set(result) == {"version_id"} and
         type(result["version_id"]) is str and
         UUID.fullmatch(result["version_id"]) is not None and
         result["version_id"] != before["active_version"],
         "UPLOAD_REPLY_UNKNOWN_STOP")
    version = result["version_id"]
    try:
        verify_after(core, before, trusted.read_snapshot(allow_latest_difference=True),
                     version, target_hash, deployed=False)
    except Exception:
        raise Blocked("UPLOAD_POSTVERIFY_STOP") from None
    # Second provider write, exactly 100% of the newly uploaded UUID.
    try:
        result = trusted.deploy_version_once(payload=core.deployment_payload(version))
    except Exception:
        raise Blocked("DEPLOY_OUTCOME_UNKNOWN_STOP") from None
    need(type(result) is dict and set(result) == {"deployment_id"} and
         type(result["deployment_id"]) is str and
         UUID.fullmatch(result["deployment_id"]) is not None,
         "DEPLOY_REPLY_UNKNOWN_STOP")
    try:
        verify_after(core, before, trusted.read_snapshot(), version,
                     target_hash, deployed=True, deployment=result["deployment_id"])
    except Exception:
        raise Blocked("DEPLOY_POSTVERIFY_STOP") from None
    return {"schema": "rozkalns.stats-zone-binding-apply.v1",
            "status": "PASS", "new_version": version,
            "changed_binding": BINDING, "provider_writes": 2}
