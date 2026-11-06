#!/usr/bin/env python3
"""Disconnected GoatCounter SIMPLE read-only preflight handoff (#1362).

This is an offline, dormant source/manifest checker. It has no CLI, install,
credentials, database/Cloudflare calls or privileged runner. It can NEVER
certify LIVE readiness or grant host access.
"""
import hashlib
import re

REPOSITORY = "rozkalnsandris/RPi5_main"
RELEASE_SCOPE = "GOATCOUNTER_SIMPLE_READONLY_PREFLIGHT_SOURCE_V1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
# Reuse the already reviewed modules. The established Cloudflare operator's
# root-owned release layout expects its own source to be named operator.py.
# This plan is NOT a deployable release or an installer.
MODULE_SOURCE = {
    "operator.py": "scripts/ausmalwiese_goatcounter_simple_cloudflare_operator_v1.py",
    "cloudflare_rdc_operator.py": "scripts/cloudflare_rdc_operator.py",
    "ausmalwiese_goatcounter_tunnel_v1.py": "scripts/ausmalwiese_goatcounter_tunnel_v1.py",
    "ausmalwiese_goatcounter_simple_route_v1.py": "scripts/ausmalwiese_goatcounter_simple_route_v1.py",
    "ausmalwiese_goatcounter_simple_readiness_v1.py":
        "scripts/ausmalwiese_goatcounter_simple_readiness_v1.py",
    "ausmalwiese_goatcounter_simple_evidence_v1.py":
        "scripts/ausmalwiese_goatcounter_simple_evidence_v1.py",
    "ausmalwiese_goatcounter_simple_cloudflare_readback_v1.py":
        "scripts/ausmalwiese_goatcounter_simple_cloudflare_readback_v1.py",
    "ausmalwiese_goatcounter_simple_collect_readback_v1.py":
        "scripts/ausmalwiese_goatcounter_simple_collect_readback_v1.py",
    "ausmalwiese_goatcounter_simple_preflight_handoff_v1.py":
        "scripts/ausmalwiese_goatcounter_simple_preflight_handoff_v1.py",
}
ALLOWED_COLLECT = frozenset(("COLLECT_DISABLED_1", "COLLECT_CANDIDATE_130"))
ALLOWED_EDGE = frozenset(("PASS_EDGE_SOURCE_ONLY",))
EXPECTED_EDGE = {
    "remote_tunnel": "verified_exact_config",
    "routes": {
        "ausmalwiese.de": "absent_safe_before_app_catchall",
        "www.ausmalwiese.de": "absent_safe_before_app_catchall",
    },
    "worker_routes": "verified_no_count_interception",
    "worker_custom_domains": "verified_no_count_interception",
}


class Stop(Exception):
    """Never print caller-provided or exception text."""


def _valid_sha(value, pattern):
    return type(value) is str and pattern.fullmatch(value) is not None


def plan_source_release(*, source_sha, source_bytes):
    """Deterministic *offline* digest inventory from injected source bytes.

    No local path access. A future trusted installer MUST independently check
    GitHub provenance, root-owned release metadata, all installed bytes and
    approved runtime identity. This function installs and verifies NOTHING.
    """
    try:
        if not _valid_sha(source_sha, SHA40) or type(source_bytes) is not dict:
            raise Stop()
        if set(source_bytes) != set(MODULE_SOURCE.values()):
            raise Stop()
        digests = {}
        for name, path in MODULE_SOURCE.items():
            value = source_bytes[path]
            if type(value) is not bytes or not 1 <= len(value) <= 196608:
                raise Stop()
            digests[name] = hashlib.sha256(value).hexdigest()
        return {
            "schema": 1,
            "repository": REPOSITORY,
            "source_sha": source_sha,
            "scope": RELEASE_SCOPE,
            "sha256": digests,
            "deployable": False,
        }
    except (Stop, TypeError, ValueError, OverflowError):
        return None


def inspect_offline(*, manifest, source_sha, collect_status, cloudflare_result):
    """Fixed public-safe verdict; cannot ever produce a LIVE PASS.

    Even a synthetic positive result is only a consistency check. Runtime
    provenance, protected read permissions, trusted proxy/IP/HTTPS behavior,
    German privacy notice, and owner approvals remain independent gates.
    """
    status = "STOP_UNVERIFIED"
    try:
        if (type(manifest) is not dict or
                set(manifest) != {"schema", "repository", "source_sha",
                                 "scope", "sha256", "deployable"} or
                manifest["schema"] != 1 or
                manifest["repository"] != REPOSITORY or
                manifest["scope"] != RELEASE_SCOPE or
                manifest["deployable"] is not False or
                not _valid_sha(source_sha, SHA40) or
                manifest["source_sha"] != source_sha or
                type(manifest["sha256"]) is not dict or
                set(manifest["sha256"]) != set(MODULE_SOURCE) or
                not all(_valid_sha(x, SHA64)
                        for x in manifest["sha256"].values())):
            raise Stop()
        if type(collect_status) is not str or collect_status not in ALLOWED_COLLECT:
            status = "STOP_COLLECT_UNVERIFIED"
        elif collect_status == "COLLECT_DISABLED_1":
            status = "STOP_COLLECT_DISABLED"
        elif (type(cloudflare_result) is not tuple or
              len(cloudflare_result) != 2 or
              cloudflare_result[0] not in ALLOWED_EDGE or
              type(cloudflare_result[1]) is not dict or
              cloudflare_result[1] != EXPECTED_EDGE):
            status = "STOP_EDGE_UNVERIFIED"
        else:
            status = "PASS_OFFLINE_SHAPE_ONLY"
    except (Stop, TypeError, ValueError, OverflowError, AttributeError):
        status = "STOP_UNVERIFIED"
    return {"schema_version": 1, "status": status,
            "source_only": True, "live_verified": False}


if __name__ == "__main__":
    raise SystemExit("SOURCE_ONLY: no trusted runtime or CLI")
