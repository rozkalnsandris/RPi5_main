#!/usr/bin/env python3
"""Strict descriptive-only series of independently verified Grafana snapshots."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SOURCE_VERIFIER = HERE / "verify-grafana-memory-attribution.py"
SCHEMA = "rpi5.grafana-memory-series.v1"
VERSION = "v01.0.0"
LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
LIMITS = (
    "Cgroup instance continuity is unproven from independently sanitized snapshots.",
    "Cumulative OOM counters are historical, not attributable event deltas.",
    "memory.peak is a cgroup historical high-water mark; Docker CLI subtracts cache.",
    "Workload equivalence, service health and host swap activity were not measured.",
)


class SeriesError(ValueError):
    pass


def canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def allowed_path(raw: str | Path, *, existing: bool) -> Path:
    p = Path(raw)
    p = p if p.is_absolute() else Path.cwd() / p
    current = Path(p.anchor or "/")
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise SeriesError("symlink path component")
    result = p.resolve(strict=existing)
    if not any(result.is_relative_to(REPO / n) for n in ("evidence", "exports")):
        raise SeriesError("path outside repository ignored evidence/exports")
    if result.name in ("evidence", "exports"):
        raise SeriesError("invalid output root")
    return result


def verify_snapshot(path: Path) -> tuple[dict, str]:
    if not path.is_dir() or path.is_symlink() or not LABEL.fullmatch(path.name):
        raise SeriesError("invalid snapshot directory")
    process = subprocess.run(
        [sys.executable, "-B", str(SOURCE_VERIFIER), str(path)],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
    )
    if process.returncode:
        raise SeriesError("source bundle verification failed")
    content = (path / "report.json").read_bytes()
    return json.loads(content), hashlib.sha256(content).hexdigest()


def build_series(bundles: list[Path]) -> dict:
    if not 2 <= len(bundles) <= 8 or len(set(bundles)) != len(bundles):
        raise SeriesError("expected 2–8 distinct snapshots")
    if len({p.parent for p in bundles}) != 1:
        raise SeriesError("snapshot parents must match")
    if not all(LABEL.fullmatch(p.name) for p in bundles):
        raise SeriesError("invalid source label")
    sources = [verify_snapshot(p) for p in bundles]
    reports = [r for r, _ in sources]
    revisions = {r["metadata"]["git_commit"] for r in reports}
    versions = {r["metadata"]["collector_version"] for r in reports}
    if len(revisions) != 1 or not SHA.fullmatch(next(iter(revisions))) or versions != {"v11.0.0"}:
        raise SeriesError("mixed or unknown collector source revisions")
    times = [datetime.fromisoformat(r["metadata"]["collected_at_utc"].replace("Z", "+00:00")) for r in reports]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise SeriesError("snapshots out of chronological order")
    observations = []
    for path, (r, digest) in zip(bundles, sources):
        cg, dock = r["cgroup"], r["container"]
        scalars, events, local = cg["scalars"], cg["memory_events"], cg["memory_events_local"]
        if not cg["available"] or not dock["available"]:
            raise SeriesError("missing cgroup or Docker evidence")
        if not all(k in scalars for k in ("memory_current_bytes", "memory_max_bytes")):
            raise SeriesError("required memory counters missing")
        if not all(k in events for k in ("max", "oom", "oom_kill")):
            raise SeriesError("required hierarchical OOM counters missing")
        observations.append({
            "source": path.name,
            "source_report_sha256": digest,
            "utc": r["metadata"]["collected_at_utc"],
            "docker_usage_kib": dock["usage_kib"],
            "docker_limit_kib": dock["limit_kib"],
            "memory_current_bytes": scalars["memory_current_bytes"],
            "memory_peak_bytes": scalars.get("memory_peak_bytes"),
            "memory_max_bytes": scalars["memory_max_bytes"],
            "memory_swap_current_bytes": scalars.get("memory_swap_current_bytes"),
            "historical_events": {key: events[key] for key in ("max", "oom", "oom_kill")},
            "historical_local_events": None if local is None else {
                key: local[key] for key in ("max", "oom", "oom_kill") if key in local
            },
        })
    peak = [x["memory_peak_bytes"] for x in observations if x["memory_peak_bytes"] is not None]
    return {
        "schema": SCHEMA,
        "analyzer_version": VERSION,
        "source_commit": next(iter(revisions)),
        "sample_count": len(observations),
        "comparison": "descriptive_only",
        "same_cgroup_identity": "unproven",
        "cgroup_oom_event_deltas": None,
        "observations": observations,
        "summary": {
            "docker_min_kib": min(x["docker_usage_kib"] for x in observations),
            "docker_max_kib": max(x["docker_usage_kib"] for x in observations),
            "cgroup_current_min_bytes": min(x["memory_current_bytes"] for x in observations),
            "cgroup_current_max_bytes": max(x["memory_current_bytes"] for x in observations),
            "historical_peak_max_bytes": max(peak) if peak else None,
            "missing_local_events": sum(x["historical_local_events"] is None for x in observations),
            "different_limits_observed": len({x["memory_max_bytes"] for x in observations}) > 1,
            "counter_regression_observed": any(
                b["historical_events"][k] < a["historical_events"][k]
                for a, b in zip(observations, observations[1:])
                for k in ("max", "oom", "oom_kill")
            ),
        },
        "limitations": list(LIMITS),
    }


def render_markdown(r: dict) -> str:
    s = r["summary"]
    lines = [
        "# Grafana memory snapshots (descriptive only)", "",
        f"Samples: {r['sample_count']}; collector SHA: `{r['source_commit']}`.",
        "**Cgroup identity unknown; event deltas = null. No new Grafana OOM inferred.**",
        "",
        "| UTC | Docker MiB | cgroup current MiB | historical peak MiB | local events |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for x in r["observations"]:
        peak = x["memory_peak_bytes"]
        local = "unknown" if x["historical_local_events"] is None else "historical"
        lines.append(
            f"| {x['utc']} | {x['docker_usage_kib']/1024:.2f} | "
            f"{x['memory_current_bytes']/1048576:.2f} | "
            f"{peak/1048576:.2f}" + f" | {local} |" if peak is not None
            else f"| {x['utc']} | {x['docker_usage_kib']/1024:.2f} | {x['memory_current_bytes']/1048576:.2f} | unknown | {local} |"
        )
    lines.extend(["", f"Highest sampled Docker usage: {s['docker_max_kib']/1024:.2f} MiB.",
                  f"Local event samples unavailable: {s['missing_local_events']}/{r['sample_count']}.",
                  "", "## Limitations", ""])
    lines.extend("- " + item for item in r["limitations"])
    return "\n".join(lines) + "\n"


def manifest(bundle: Path) -> str:
    names = sorted(("file-inventory.txt", "report.json", "report.md"))
    return "".join(f"{hashlib.sha256((bundle / n).read_bytes()).hexdigest()}  {n}\n" for n in names)
