#!/usr/bin/env python3
"""Strict, descriptive-only correlation of independently verified V08 and V02 reports.

No Docker, host reads or evidence writes. Nominal UTC overlap never proves
simultaneous sampling, event causation or Grafana performance.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any

from grafana_continuity_core import check_report as check_grafana_report

SCHEMA = "rpi5.grafana-host-correlation.v1"
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
HOST_SCHEMA = "rpi5.memory-pressure-diagnostic.v1"
HOST_VERSIONS = frozenset(("v08.0.0", "v08.1.0"))
COUNTERS = ("pswpin_pages", "pswpout_pages", "pgmajfault", "oom_kill")
PSI = ("psi_some_total_usec", "psi_full_total_usec")
LIMITATIONS = (
    "V08 collected_at_utc is a coarse run-start timestamp, not the exact vmstat or PSI read time.",
    "Overlap is nominal only; a V08 short window cannot attribute Grafana events or host swap.",
    "Grafana V02 cgroup identity is checked within one invocation, not across bundles.",
    "No same-window Grafana HTTP error, request duration or dashboard performance was measured.",
    "PSI absent or legacy v08.0.0 is unknown, not zero.",
    "memory.events.local max is a boundary attempt, not an OOM or a latency measurement.",
)


class CorrelationError(ValueError):
    """Invalid or unsafe correlation source."""


def reject() -> None:
    raise CorrelationError("invalid sanitized correlation evidence")


def timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not UTC.fullmatch(value):
        reject()
    try:
        result = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if result.year < 2020 or result.year > 2100:
            reject()
        return result
    except ValueError:
        reject()


def integer(value: object, *, nullable: bool = False) -> bool:
    return (value is None and nullable) or (type(value) is int and 0 <= value <= (1 << 63) - 1)


def normalized_host(report: object) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schema") != HOST_SCHEMA:
        reject()
    meta, obs = report.get("metadata"), report.get("observation")
    if not isinstance(meta, dict) or not isinstance(obs, dict):
        reject()
    if meta.get("collector_version") not in HOST_VERSIONS:
        reject()
    source = meta.get("git_commit")
    if not isinstance(source, str) or not re.fullmatch(r"[a-f0-9]{40}|unavailable", source):
        reject()
    seconds = meta.get("sample_seconds")
    if type(seconds) is not int or not 1 <= seconds <= 30:
        # Zero-second test-only runs are not evidence for an interval.
        reject()
    start = timestamp(meta.get("collected_at_utc"))
    end = start + timedelta(seconds=seconds)
    total, available, swap = (obs.get(key) for key in
                              ("mem_total_kib", "mem_available_kib", "swap_used_kib"))
    if not all(integer(n) for n in (total, available, swap)) or total == 0 or available > total:
        reject()
    delta = obs.get("sample_delta")
    if not isinstance(delta, dict) or not all(integer(delta.get(k)) for k in COUNTERS):
        reject()
    if not all(integer(delta.get(k), nullable=True) for k in PSI):
        reject()
    # Legacy PSI uses placeholders, never treat a legacy zero as a measurement.
    psi_valid = meta["collector_version"] == "v08.1.0" and all(delta[k] is not None for k in PSI)
    return {
        "start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nominal_end_utc": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample_seconds": seconds,
        "source_revision": source,
        "mem_available_kib": available,
        "mem_total_kib": total,
        "swap_used_kib": swap,
        "pswpin_pages": delta["pswpin_pages"],
        "pswpout_pages": delta["pswpout_pages"],
        "pgmajfault": delta["pgmajfault"],
        "host_oom_kill": delta["oom_kill"],
        "psi_some_usec": delta["psi_some_total_usec"] if psi_valid else None,
        "psi_full_usec": delta["psi_full_total_usec"] if psi_valid else None,
    }


def summarize(host_reports: list[dict], grafana_report: dict) -> dict:
    if not isinstance(host_reports, list) or not 2 <= len(host_reports) <= 8:
        reject()
    try:
        check_grafana_report(grafana_report)
    except (ValueError, TypeError, KeyError):
        reject()
    synthetic = grafana_report["synthetic"]
    hosts = [normalized_host(r) for r in host_reports]
    stamps = [timestamp(h["start_utc"]) for h in hosts]
    if any(b <= a for a, b in zip(stamps, stamps[1:])):
        reject()
    gf = grafana_report["observations"][0]
    gl = grafana_report["observations"][-1]
    start, end = timestamp(gf["utc"]), timestamp(gl["utc"])
    if end <= start:
        reject()
    for h in hosts:
        a, b = timestamp(h["start_utc"]), timestamp(h["nominal_end_utc"])
        h["nominal_overlap"] = a < end and b > start
    d = grafana_report["event_deltas"]["local"]
    return {
        "schema": SCHEMA,
        "synthetic": synthetic,
        "classification": "nominal_overlap_not_alignment" if any(h["nominal_overlap"] for h in hosts)
                          else "no_nominal_overlap",
        "proven_causation": False,
        "verified_same_window": False,
        "grafana": {
            "source_revision": grafana_report["source_commit"],
            "first_utc": gf["utc"],
            "last_utc": gl["utc"],
            "samples": len(grafana_report["observations"]),
            "memory_limit_bytes": gf["memory_max_bytes"],
            "memory_current_first_bytes": gf["memory_current_bytes"],
            "memory_current_last_bytes": gl["memory_current_bytes"],
            "memory_swap_last_bytes": gl["memory_swap_current_bytes"],
            "max_events": d["max"], "oom_events": d["oom"],
            "oom_kill_events": d["oom_kill"],
            "health_latency_verified": False,
        },
        "host_windows": hosts,
        "limitations": list(LIMITATIONS),
    }


def canonical_json(report: dict) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
