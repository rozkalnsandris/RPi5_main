#!/usr/bin/env python3
"""Pure, source-only Hermes 11:00 intent classifier (#1513).

No host/file/network/CLI access. Caller-supplied bindings are NOT provenance
proof. The production binding contract is intentionally NOT populated from
the changed live job fingerprint. ALL outcomes remain BLOCKED.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA = "rozkalns.balcony-autumn-independent-validator.v1"
MAX_JOBS = 64
MAX_DOCUMENT_CHARS = 100_000
MAX_BINDING_CHARS = 8192

# These schedules are independently specified in reviewed source (#1498).
SLOTS = {
    "legacy_0700": ("0 7 * * *", False),
    "legacy_1400": ("0 14 * * *", False),
    "legacy_2300": ("0 23 * * *", False),
    "autumn_1100": ("0 11 * * *", True),
}
BINDING_FIELDS = frozenset({
    "name", "script_sha256", "prompt_sha256", "deliver",
    "timezone", "grace_minutes",
})
# Only documented, explicitly bounded metadata. An extra unrecognized field
# never becomes "harmless bookkeeping" merely because its name looks familiar.
DEFINITION_FIELDS = frozenset({
    "id", "name", "enabled", "deliver", "script", "prompt", "schedule",
    "timezone", "grace_minutes", "state", "run_count",
    "next_run_at", "last_run_at", "last_dispatch", "pending_slot",
    "created_at",
})
WATERING_MARKERS = (
    "balcon", "balkon", "laist", "watering",
    "laistisana_2x", "balcony-watering-autumn",
)
SHA256_FORMAT = re.compile(r"[a-f0-9]{64}\Z")

# Deliberately absent: the complete independently reviewed four-slot source
# binding contract has NOT been established. Never fill from observed SHA.
PRODUCTION_BINDINGS = None


def _report(reason: str, *, matched: bool = False) -> dict[str, Any]:
    """Only fixed public enum labels and booleans, never input-derived data."""
    return {
        "schema": SCHEMA,
        "result": "BLOCKED",
        "reason": reason,
        "in_memory_contract_match": matched,
        "source_contract_independently_approved": False,
        "host_source_provenance_verified": False,
        "sensor_runtime_verified": False,
        "telegram_delivery_verified": False,
        "live_apply_authorized": False,
        "mutation_started": False,
        "writes_performed": False,
        "raw_payload_emitted": False,
    }


def _bounded(value: Any) -> bool:
    try:
        encoded = json.dumps(
            value, sort_keys=True, ensure_ascii=True,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError, RecursionError):
        return False
    return len(encoded) <= MAX_DOCUMENT_CHARS


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_bindings(bindings: Any) -> bool:
    if type(bindings) is not dict or set(bindings) != set(SLOTS):
        return False
    if not _bounded(bindings):
        return False
    seen_names: set[str] = set()
    for slot, b in bindings.items():
        if type(b) is not dict or set(b) != BINDING_FIELDS:
            return False
        name = b["name"]
        if (type(name) is not str or not 1 <= len(name) <= 128
                or name in seen_names or any(ord(c) < 32 for c in name)):
            return False
        seen_names.add(name)
        if (type(b["script_sha256"]) is not str
                or not SHA256_FORMAT.fullmatch(b["script_sha256"])
                or type(b["prompt_sha256"]) is not str
                or not SHA256_FORMAT.fullmatch(b["prompt_sha256"])):
            return False
        if (type(b["deliver"]) is not str
                or not 1 <= len(b["deliver"]) <= 32
                or (slot == "autumn_1100" and b["deliver"] != "local")):
            return False
        tz = b["timezone"]
        grace = b["grace_minutes"]
        if tz is not None and (
            type(tz) is not str or not 1 <= len(tz) <= 64
        ):
            return False
        if grace is not None and (
            type(grace) is not int or not 0 <= grace <= 120
        ):
            return False
    return True


def _metadata_shape(job: dict[str, Any]) -> bool:
    if "run_count" in job:
        count = job["run_count"]
        if type(count) is not int or not 0 <= count <= 1_000_000:
            return False
    for key in ("next_run_at", "last_run_at", "created_at"):
        if key in job and job[key] is not None:
            value = job[key]
            if type(value) is not str or len(value) > 128:
                return False
    # pending_slot may represent a queued physical watering dispatch.
    # Even structurally valid pending slots cannot be presumed harmless.
    if "pending_slot" in job:
        return False
    for key, allowed in (
        ("last_dispatch", {"kind", "at"}),
    ):
        if key not in job:
            continue
        value = job[key]
        if (type(value) is not dict or not value
                or not set(value) <= allowed):
            return False
        if any(type(v) is not str or len(v) > 128 for v in value.values()):
            return False
    return True


def _potential_watering(job: dict[str, Any]) -> bool:
    for field in ("name", "script", "prompt"):
        value = job.get(field)
        if type(value) is str and any(
            marker in value.casefold() for marker in WATERING_MARKERS
        ):
            return True
    return False


def assess_jobs(jobs: Any, *, bindings: Any = PRODUCTION_BINDINGS) -> dict[str, Any]:
    """Classify an *already supplied* in-memory list against source intent.

    A complete independent binding fixture is mandatory. A caller can
    manufacture one, so even a match is NOT proof of source provenance.
    Never wire this output to a protected reader or installation gate.
    """
    if bindings is None:
        return _report("independent_source_contract_missing")
    if not _valid_bindings(bindings):
        return _report("independent_source_contract_invalid")
    if (type(jobs) is not list or not 1 <= len(jobs) <= MAX_JOBS
            or not _bounded(jobs)):
        return _report("unreviewed_job_collection")

    seen_ids: set[str] = set()
    for job in jobs:
        if type(job) is not dict or len(job) > 64:
            return _report("unreviewed_job_shape")
        identifier = job.get("id")
        if (type(identifier) is not str or not 1 <= len(identifier) <= 128
                or not all(0x21 <= ord(c) <= 0x7e for c in identifier)):
            return _report("unreviewed_job_identity")
        if identifier in seen_ids:
            return _report("duplicate_job_identity")
        seen_ids.add(identifier)

    selected: set[int] = set()
    for slot, (schedule, enabled) in SLOTS.items():
        expected = bindings[slot]
        matching = [(i, job) for i, job in enumerate(jobs)
                    if job.get("name") == expected["name"]]
        if len(matching) != 1:
            return _report("required_slot_missing_or_duplicate")
        index, job = matching[0]
        selected.add(index)
        if set(job) - DEFINITION_FIELDS:
            return _report("unreviewed_definition_field")
        sched = job.get("schedule")
        if (type(sched) is not dict or set(sched) != {"kind", "expr"}
                or sched["kind"] != "cron" or sched["expr"] != schedule):
            return _report("schedule_contract_mismatch")
        if job.get("enabled") is not enabled:
            return _report("enabled_status_mismatch")
        if job.get("deliver") != expected["deliver"]:
            return _report("delivery_contract_mismatch")
        if (("timezone" in job) != (expected["timezone"] is not None)
                or job.get("timezone") != expected["timezone"]
                or ("grace_minutes" in job)
                != (expected["grace_minutes"] is not None)
                or job.get("grace_minutes") != expected["grace_minutes"]):
            return _report("time_contract_mismatch")
        # Running, paused, completed and unknown states are never treated
        # as an innocuous change in a watering scheduling decision.
        if "state" in job and job["state"] != "scheduled":
            return _report("scheduler_state_unreviewed")
        if not _metadata_shape(job):
            return _report("scheduler_metadata_unreviewed")
        script, prompt = job.get("script"), job.get("prompt")
        if (type(script) is not str or type(prompt) is not str
                or len(script) > MAX_BINDING_CHARS
                or len(prompt) > MAX_BINDING_CHARS):
            return _report("binding_shape_unreviewed")
        if (_digest(script) != expected["script_sha256"]
                or _digest(prompt) != expected["prompt_sha256"]):
            return _report("script_or_prompt_binding_mismatch")

    # Marker detection is deliberately only a BLOCKER, not proof that all
    # unnamed watering jobs were discovered. Host inventory is still gated.
    if any(_potential_watering(job)
           for i, job in enumerate(jobs) if i not in selected):
        return _report("unexpected_watering_candidate")
    return _report("in_memory_contract_match_not_authorized", matched=True)
