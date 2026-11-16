#!/usr/bin/env python3
"""Offline, fail-closed comparison of two fingerprint-verified Hermes job definitions.

No CLI, no host data access, no network, no Hermes command, no mutation.
A matching historical SHA is essential: a hash alone is NOT a job preimage.
The returned categories are informational and NEVER authorize installation.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
from typing import Any

SCHEMA = "rozkalns.balcony-autumn-verified-definition-compare.v1"
FROZEN_REFERENCE_SHA256 = "bc085927b0a145b947742551c1550e4a875b55fc2c9925148e11c3d5e3123562"
MAX_DOCUMENT_CHARS = 100_000
MAX_TOP_LEVEL_FIELDS = 96

# Deliberately fixed public-safe labels. Never export arbitrary input keys,
# hashes of sensitive fields, values, script bodies, names or job IDs.
FIELD_CATEGORIES = {
    "id": "job_identifier",
    "name": "job_display_name",
    "enabled": "enabled_status",
    "deliver": "delivery_binding",
    "schedule": "schedule_contract",
    "timezone": "timezone_contract",
    "grace_minutes": "grace_contract",
    "script_sha256": "script_binding",
    "prompt_sha256": "prompt_definition",
    "monitor_script_sha256": "monitor_binding",
    "workdir_sha256": "workdir_binding",
    "repeat": "repeat_contract",
    "state": "hermes_scheduler_state",
    "run_count": "hermes_run_count",
    "last_dispatch": "hermes_last_dispatch",
    "pending_slot": "hermes_pending_slot",
    "created_at": "job_created_metadata",
    "skills": "attached_skills",
    "skill": "attached_skills",
    "no_agent": "no_agent_mode",
    "model": "model_binding",
    "provider": "provider_binding",
    "enabled_toolsets": "toolset_binding",
    "request_overrides": "request_overrides",
}


def _report(reason: str, categories: tuple[str, ...] = (),
            *, reference_verified: bool = False) -> dict[str, Any]:
    """Report is a closed public schema: never include untrusted strings."""
    return {
        "schema": SCHEMA,
        "result": "BLOCKED",
        "reason": reason,
        "changed_definition_categories": list(categories),
        "reference_fingerprint_verified": reference_verified,
        "live_apply_authorized": False,
        "mutation_started": False,
        "writes_performed": False,
        "raw_payload_emitted": False,
    }


def _bounded_json_job(job: Any) -> bool:
    if type(job) is not dict or len(job) > MAX_TOP_LEVEL_FIELDS:
        return False
    try:
        encoded = json.dumps(job, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, RecursionError, OverflowError):
        return False
    return len(encoded) <= MAX_DOCUMENT_CHARS


def _reviewed_gate():
    """Load only repository source code, never a protected Hermes data file."""
    source = Path(__file__).resolve().parents[1] / "bin/balcony-watering-hermes-preflight"
    loader = importlib.machinery.SourceFileLoader("balcony_gate_compare_v1", str(source))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise ValueError("gate_unavailable")
    gate = importlib.util.module_from_spec(spec)
    loader.exec_module(gate)
    return gate


def compare_verified_definitions(reference: Any, observed: Any) -> dict[str, Any]:
    """Compare selected job records only if the historical reference is proven.

    The caller must separately verify the records' protected-source provenance,
    job uniqueness, host/source SHA, access authorization, and safe file reads.
    An observed comparison is never controller-ready or LIVE permission.
    """
    if reference is None:
        return _report("verified_reference_unavailable")
    if observed is None:
        return _report("observed_definition_unavailable")
    if not _bounded_json_job(reference) or not _bounded_json_job(observed):
        return _report("unreviewed_definition_shape")

    try:
        gate = _reviewed_gate()
        if gate._fingerprint(reference) != FROZEN_REFERENCE_SHA256:
            return _report("reference_fingerprint_mismatch")
        before = gate._definition_projection(reference)
        after = gate._definition_projection(observed)
        # These must be the exact same projection algorithm as the pinned SHA.
        if not _bounded_json_job(before) or not _bounded_json_job(after):
            return _report("unreviewed_projection_shape", reference_verified=True)
        changed = {FIELD_CATEGORIES.get(field, "other_definition_fields")
                   for field in set(before) | set(after)
                   if before.get(field, _MISSING) != after.get(field, _MISSING)}
        # All results, including equality, remain BLOCKED. No report includes
        # raw keys, values, hashes of private values or arbitrary user strings.
        if gate._fingerprint(observed) == FROZEN_REFERENCE_SHA256:
            if changed:
                return _report("projection_fingerprint_inconsistent",
                               reference_verified=True)
            return _report("definition_fingerprint_unchanged",
                           reference_verified=True)
        if not changed:
            return _report("projection_fingerprint_inconsistent",
                           reference_verified=True)
        return _report("definition_difference_categorized",
                       tuple(sorted(changed)), reference_verified=True)
    except Exception:
        return _report("comparison_unavailable")


_MISSING = object()
