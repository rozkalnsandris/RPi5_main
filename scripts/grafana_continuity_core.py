#!/usr/bin/env python3
"""Strict offline contract for bounded within-run Grafana cgroup event evidence."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

SCHEMA = "rpi5.grafana-cgroup-continuity.v1"
VERSION = "v01.0.0"
EVENTS = ("max", "oom", "oom_kill")
SAMPLE_FIELDS = frozenset((
    "utc", "elapsed_ms", "memory_current_bytes", "memory_max_bytes",
    "memory_swap_current_bytes", "memory_peak_bytes",
    "events_local", "events_hierarchical",
))
SHA = re.compile(r"[0-9a-f]{40}\Z")
UTC = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")

class EvidenceError(ValueError):
    """Invalid or unsafe continuity evidence."""

def invalid() -> None:
    raise EvidenceError("invalid bounded Grafana continuity evidence")

def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n"

def u64(v: object, nullable: bool = False) -> bool:
    return (v is None and nullable) or (
        type(v) is int and 0 <= v <= (1 << 63) - 1)

def utc(v: object) -> datetime:
    if not isinstance(v, str) or not UTC.fullmatch(v):
        invalid()
    try:
        return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        invalid()

def check_report(report: object) -> None:
    if not isinstance(report, dict) or set(report) != {
        "schema", "collector_version", "source_commit", "synthetic",
        "identity_assertion", "identity_scope", "interval_seconds",
        "observations", "event_deltas",
    }:
        invalid()
    if (report["schema"] != SCHEMA or report["collector_version"] != VERSION
        or not isinstance(report["source_commit"], str)
        or not SHA.fullmatch(report["source_commit"])
        or type(report["synthetic"]) is not bool
        or report["identity_assertion"] != "collector_checked_in_process"
        or report["identity_scope"] != "single_invocation"):
        invalid()
    interval = report["interval_seconds"]
    obs = report["observations"]
    if (type(interval) is not int or not 15 <= interval <= 300
        or not isinstance(obs, list) or not 2 <= len(obs) <= 8
        or (len(obs) - 1) * interval > 2400):
        invalid()
    first_time = None
    previous = None
    for sample in obs:
        if not isinstance(sample, dict) or set(sample) != SAMPLE_FIELDS:
            invalid()
        stamp = utc(sample["utc"])
        if (not u64(sample["elapsed_ms"])
            or not u64(sample["memory_current_bytes"])
            or not u64(sample["memory_max_bytes"], True)
            or not u64(sample["memory_swap_current_bytes"], True)
            or not u64(sample["memory_peak_bytes"], True)):
            invalid()
        for name in ("events_local", "events_hierarchical"):
            obj = sample[name]
            if (not isinstance(obj, dict) or set(obj) != set(EVENTS)
                or not all(u64(v) for v in obj.values())):
                invalid()
        if previous is None:
            if sample["elapsed_ms"] != 0:
                invalid()
            first_time = stamp
        else:
            if (stamp < utc(previous["utc"])
                or sample["elapsed_ms"] <= previous["elapsed_ms"]
                or sample["memory_max_bytes"] != previous["memory_max_bytes"]):
                invalid()
            if (not report["synthetic"]
                and sample["elapsed_ms"] - previous["elapsed_ms"]
                    < interval * 1000 - 1000):
                invalid()
            for name in ("events_local", "events_hierarchical"):
                if any(sample[name][key] < previous[name][key] for key in EVENTS):
                    invalid()
        previous = sample
    if (obs[-1]["elapsed_ms"] > 2400000
        or (utc(obs[-1]["utc"]) - first_time).total_seconds() > 2401):
        invalid()
    deltas = report["event_deltas"]
    if not isinstance(deltas, dict) or set(deltas) != {"local", "hierarchical"}:
        invalid()
    for name, field in (("local", "events_local"),
                        ("hierarchical", "events_hierarchical")):
        values = deltas[name]
        if not isinstance(values, dict) or set(values) != set(EVENTS):
            invalid()
        for key in EVENTS:
            expected = obs[-1][field][key] - obs[0][field][key]
            if type(values[key]) is not int or values[key] != expected:
                invalid()

def event_deltas(samples: list[dict]) -> dict:
    result = {
        name: {
            key: samples[-1][field][key] - samples[0][field][key]
            for key in EVENTS
        }
        for name, field in (("local", "events_local"),
                            ("hierarchical", "events_hierarchical"))
    }
    return result

def render_markdown(report: dict) -> str:
    check_report(report)
    samples = report["observations"]
    first, last = samples[0], samples[-1]
    d = report["event_deltas"]["local"]
    return (
        "# Grafana single-invocation cgroup event evidence\n\n"
        f"- Samples: {len(samples)}; interval: {report['interval_seconds']}s.\n"
        f"- First/last UTC: {first['utc']} / {last['utc']}.\n"
        f"- memory.current: {first['memory_current_bytes']} / "
        f"{last['memory_current_bytes']} bytes.\n"
        f"- Within-run local max/oom/oom_kill deltas: "
        f"{d['max']}/{d['oom']}/{d['oom_kill']}.\n\n"
        "The offline verifier checks arithmetic and bundle integrity only. "
        "It cannot independently replay historical kernel FD/process/container "
        "identity; that claim relies on the future collector's in-process checks. "
        "These readings do not establish host swap pressure, health degradation, "
        "or RAM savings; a max event is not necessarily OOM.\n"
    )

def inventory() -> str:
    return "report.json\nreport.md\n"

def checksums(report_json: bytes, report_md: bytes) -> str:
    entries = {"report.json": report_json, "report.md": report_md}
    return "".join(
        f"{hashlib.sha256(entries[name]).hexdigest()}  {name}\n"
        for name in sorted(entries)
    )
