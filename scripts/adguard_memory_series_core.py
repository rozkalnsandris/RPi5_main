#!/usr/bin/env python3
"""Deterministic summary logic for four verified V11 AdGuard memory bundles."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from adguard_memory_core import SCHEMA as SAMPLE_SCHEMA

SERIES_SCHEMA = "rpi5.adguard-memory-series.v1"
SERIES_SAMPLE_COUNT = 4


class SeriesError(ValueError):
    pass


def _utc(value: str) -> datetime:
    try:
        result = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise SeriesError("invalid sample UTC timestamp") from exc
    return result


def build_series(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if len(reports) != SERIES_SAMPLE_COUNT:
        raise SeriesError(f"exactly {SERIES_SAMPLE_COUNT} verified samples are required")

    rows: list[dict[str, Any]] = []
    commits: set[str] = set()
    previous: datetime | None = None
    for index, report in enumerate(reports, start=1):
        if report.get("schema") != SAMPLE_SCHEMA:
            raise SeriesError("unexpected V11 sample schema")
        metadata = report.get("metadata")
        attribution = report.get("attribution")
        container = report.get("container")
        cgroup = report.get("cgroup")
        if not all(isinstance(item, dict) for item in (metadata, attribution, container, cgroup)):
            raise SeriesError("malformed V11 sample report")

        stamp_text = str(metadata.get("collected_at_utc", ""))
        stamp = _utc(stamp_text)
        if previous is not None and stamp <= previous:
            raise SeriesError("sample timestamps must be strictly increasing")
        previous = stamp
        commit = str(metadata.get("git_commit", ""))
        if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
            raise SeriesError("sample commit is not an exact 40-character Git SHA")
        commits.add(commit)

        events = cgroup.get("memory_events")
        if not isinstance(events, dict):
            raise SeriesError("malformed cgroup event map")
        rows.append({
            "sample": index,
            "collected_at_utc": stamp_text,
            "observation_level": str(report.get("observation_level", "")),
            "basis": str(attribution.get("basis", "")),
            "dominant_component": str(attribution.get("dominant_component", "")),
            "basis_total_kib": int(attribution.get("basis_total_kib", 0)),
            "anonymous_kib": int(attribution.get("anonymous_kib", 0)),
            "file_kib": int(attribution.get("file_kib", 0)),
            "shared_kib": int(attribution.get("shared_kib", 0)),
            "process_swap_kib": int(attribution.get("process_swap_kib", 0)),
            "cgroup_swap_kib": int(attribution.get("cgroup_swap_kib", 0)),
            "kernel_kib": int(attribution.get("kernel_kib", 0)),
            "container_available": bool(container.get("available", False)),
            "container_usage_kib": int(container.get("usage_kib", 0)),
            "container_limit_kib": int(container.get("limit_kib", 0)),
            "container_percent_basis_points": int(container.get("percent_basis_points", 0)),
            "oom": int(events.get("oom", 0)),
            "oom_kill": int(events.get("oom_kill", 0)),
            "limitations_count": len(report.get("limitations", [])),
        })

    if len(commits) != 1:
        raise SeriesError("all four samples must bind to the same Git commit")

    dominant_values = [row["dominant_component"] for row in rows]
    stable_dominant = dominant_values[0] if len(set(dominant_values)) == 1 else "mixed"
    usages = [row["container_usage_kib"] for row in rows if row["container_available"]]
    limits = [row["container_limit_kib"] for row in rows if row["container_available"]]
    container_all_available = len(usages) == SERIES_SAMPLE_COUNT
    if container_all_available and len(set(limits)) != 1:
        raise SeriesError("container limit changed during the four-sample series")

    reason_codes: list[str] = []
    if stable_dominant == "anonymous":
        reason_codes.append("stable_anonymous_dominance")
    elif stable_dominant == "file":
        reason_codes.append("stable_file_dominance")
    elif stable_dominant == "shared":
        reason_codes.append("stable_shared_dominance")
    elif stable_dominant == "mixed":
        reason_codes.append("memory_class_varied_across_samples")
    else:
        reason_codes.append("stable_mixed_component_attribution")
    if any(row["oom"] > 0 or row["oom_kill"] > 0 for row in rows):
        reason_codes.append("cgroup_oom_history_present")
    if container_all_available:
        if all(usages[index] >= usages[index - 1] for index in range(1, len(usages))) and usages[-1] > usages[0]:
            reason_codes.append("container_usage_non_decreasing")
        if max(row["container_percent_basis_points"] for row in rows) >= 9000:
            reason_codes.append("container_limit_usage_ge_90_percent")
        elif max(row["container_percent_basis_points"] for row in rows) >= 7500:
            reason_codes.append("container_limit_usage_ge_75_percent")
    else:
        reason_codes.append("container_stats_incomplete")

    return {
        "schema": SERIES_SCHEMA,
        "git_commit": next(iter(commits)),
        "sample_count": SERIES_SAMPLE_COUNT,
        "first_collected_at_utc": rows[0]["collected_at_utc"],
        "last_collected_at_utc": rows[-1]["collected_at_utc"],
        "stable_dominant_component": stable_dominant,
        "container_all_samples_available": container_all_available,
        "container_usage_first_kib": usages[0] if container_all_available else None,
        "container_usage_last_kib": usages[-1] if container_all_available else None,
        "container_usage_min_kib": min(usages) if container_all_available else None,
        "container_usage_max_kib": max(usages) if container_all_available else None,
        "container_usage_change_kib": (usages[-1] - usages[0]) if container_all_available else None,
        "container_limit_kib": limits[0] if container_all_available else None,
        "max_container_percent_basis_points": max(
            (row["container_percent_basis_points"] for row in rows), default=0
        ),
        "max_oom": max(row["oom"] for row in rows),
        "max_oom_kill": max(row["oom_kill"] for row in rows),
        "reason_codes": reason_codes,
        "samples": rows,
        "interpretation_boundary": (
            "This series establishes Linux memory-class and bounded trend evidence only. "
            "It does not identify an internal AdGuard Home heap owner or prove a memory leak."
        ),
    }


def _mib(value: int | None) -> str:
    return "unavailable" if value is None else f"{value / 1024.0:.2f} MiB"


def render_series_markdown(series: dict[str, Any]) -> str:
    lines = [
        "# AdGuard memory attribution series",
        "",
        f"Schema: `{series['schema']}`",
        f"Commit: `{series['git_commit']}`",
        f"Samples: `{series['sample_count']}`",
        f"Window: `{series['first_collected_at_utc']}` → `{series['last_collected_at_utc']}`",
        f"Stable dominant component: `{series['stable_dominant_component']}`",
        "",
        "## Container trend",
        "",
        f"- First: {_mib(series['container_usage_first_kib'])}",
        f"- Last: {_mib(series['container_usage_last_kib'])}",
        f"- Minimum: {_mib(series['container_usage_min_kib'])}",
        f"- Maximum: {_mib(series['container_usage_max_kib'])}",
        f"- Change: {_mib(series['container_usage_change_kib'])}",
        f"- Maximum limit use: {series['max_container_percent_basis_points'] / 100.0:.2f}%",
        f"- Maximum cgroup OOM/OOM-kill counters: {series['max_oom']}/{series['max_oom_kill']}",
        "",
        "## Samples",
        "",
        "| # | UTC | Basis | Dominant | Anonymous MiB | File MiB | Shared MiB | Container MiB | Process swap MiB |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in series["samples"]:
        lines.append(
            f"| {row['sample']} | {row['collected_at_utc']} | {row['basis']} | "
            f"{row['dominant_component']} | {row['anonymous_kib'] / 1024.0:.2f} | "
            f"{row['file_kib'] / 1024.0:.2f} | {row['shared_kib'] / 1024.0:.2f} | "
            f"{row['container_usage_kib'] / 1024.0:.2f} | {row['process_swap_kib'] / 1024.0:.2f} |"
        )
    lines.extend(["", "## Reason codes", ""])
    lines.extend(f"- `{reason}`" for reason in series["reason_codes"])
    lines.extend(["", series["interpretation_boundary"], ""])
    return "\n".join(lines)
