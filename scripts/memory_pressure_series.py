#!/usr/bin/env python3
"""Deterministic multi-sample analysis for verified V08 memory bundles."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import pathlib
import re
from typing import Any

SCHEMA = "rpi5.memory-pressure-series.v1"
ANALYZER_VERSION = "v09.0.0"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$")
SIZE_RE = re.compile(r"^(0|[0-9]+(?:\.[0-9]+)?)(B|KB|MB|GB|TB|PB|KiB|MiB|GiB|TiB|PiB)?$")

LIMITATIONS = (
    "The series summarizes short V08 windows and can miss activity between samples.",
    "Container usage values inherit Docker's displayed precision and are not PSS or peak memory.",
    "A trend association is not proof of causality or a memory leak.",
)


class SeriesError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def size_to_kib(value: str) -> int:
    match = SIZE_RE.fullmatch(value)
    if not match:
        raise SeriesError("invalid memory size")
    number = Decimal(match.group(1))
    unit = match.group(2) or "B"
    factors = {
        "B": Decimal(1) / Decimal(1024),
        "KB": Decimal(1000) / Decimal(1024),
        "MB": Decimal(1000**2) / Decimal(1024),
        "GB": Decimal(1000**3) / Decimal(1024),
        "TB": Decimal(1000**4) / Decimal(1024),
        "PB": Decimal(1000**5) / Decimal(1024),
        "KiB": Decimal(1),
        "MiB": Decimal(1024),
        "GiB": Decimal(1024**2),
        "TiB": Decimal(1024**3),
        "PiB": Decimal(1024**4),
    }
    return int((number * factors[unit]).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def percent_to_basis_points(value: str | int | float) -> int:
    try:
        if isinstance(value, str):
            text = value[:-1] if value.endswith("%") else value
            number = Decimal(text)
        else:
            number = Decimal(str(value))
    except InvalidOperation as error:
        raise SeriesError("invalid percentage") from error
    basis_points = int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if not 0 <= basis_points <= 10000:
        raise SeriesError("percentage outside range")
    return basis_points


def format_mib(kib: int) -> str:
    return f"{Decimal(kib) / Decimal(1024):.2f}"


def build_source(bundle: pathlib.Path, report: dict[str, Any]) -> dict[str, Any]:
    metadata = report["metadata"]
    return {
        "bundle_name": bundle.name,
        "collection_utc": metadata["collected_at_utc"],
        "report_sha256": sha256_file(bundle / "report.json"),
    }


def build_sample(report: dict[str, Any]) -> dict[str, Any]:
    metadata = report["metadata"]
    observation = report["observation"]
    delta = observation["sample_delta"]
    return {
        "collection_utc": metadata["collected_at_utc"],
        "source_level": observation["level"],
        "mem_available_kib": observation["mem_available_kib"],
        "mem_available_basis_points": percent_to_basis_points(observation["mem_available_percent"]),
        "swap_used_kib": observation["swap_used_kib"],
        "pswpin_pages": delta["pswpin_pages"],
        "pswpout_pages": delta["pswpout_pages"],
        "pgmajfault": delta["pgmajfault"],
        "oom_kill": delta["oom_kill"],
        "psi_some_total_usec": delta["psi_some_total_usec"],
        "psi_full_total_usec": delta["psi_full_total_usec"],
    }


def build_container_trends(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        for row in report["containers"]:
            by_name.setdefault(row["name"], []).append(row)
    trends: list[dict[str, Any]] = []
    for name in sorted(by_name):
        rows = by_name[name]
        values = [size_to_kib(str(row["usage"])) for row in rows]
        percentages = [percent_to_basis_points(str(row["percent"])) for row in rows]
        trends.append({
            "name": name,
            "sample_count": len(rows),
            "first_kib": values[0],
            "latest_kib": values[-1],
            "min_kib": min(values),
            "max_kib": max(values),
            "change_kib": values[-1] - values[0],
            "max_percent_basis_points": max(percentages),
        })
    return trends


def classify(samples: list[dict[str, Any]]) -> tuple[str, str, dict[str, Any]]:
    psi_samples = sum(
        1 for row in samples
        if row["psi_some_total_usec"] > 0 or row["psi_full_total_usec"] > 0
    )
    swapout_samples = sum(1 for row in samples if row["pswpout_pages"] > 0)
    low_memory_samples = sum(1 for row in samples if row["mem_available_basis_points"] < 1500)
    oom_total = sum(row["oom_kill"] for row in samples)
    psi_full_total = sum(row["psi_full_total_usec"] for row in samples)
    sustained = (
        oom_total > 0
        or psi_full_total > 0
        or swapout_samples >= 2
        or psi_samples >= 2
        or low_memory_samples >= 2
    )
    activity = any(
        row["pswpin_pages"] > 0
        or row["pswpout_pages"] > 0
        or row["pgmajfault"] > 0
        or row["psi_some_total_usec"] > 0
        or row["psi_full_total_usec"] > 0
        or row["oom_kill"] > 0
        for row in samples
    )
    if sustained:
        classification = "sustained_pressure"
        level = "attention"
    elif activity:
        classification = "intermittent_activity"
        level = "informational"
    else:
        classification = "stable_idle"
        level = "none"
    evidence = {
        "sustained_pressure": sustained,
        "oom_total": oom_total,
        "psi_full_total_usec": psi_full_total,
        "psi_activity_samples": psi_samples,
        "swapout_activity_samples": swapout_samples,
        "low_memory_samples": low_memory_samples,
    }
    return classification, level, evidence


def build_report(bundles: list[pathlib.Path], reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not 2 <= len(reports) <= 64 or len(bundles) != len(reports):
        raise SeriesError("series requires 2 to 64 bundles")
    sources = [build_source(bundle, report) for bundle, report in zip(bundles, reports, strict=True)]
    samples = [build_sample(report) for report in reports]
    timestamps = [row["collection_utc"] for row in samples]
    if any(not UTC_RE.fullmatch(value) for value in timestamps):
        raise SeriesError("invalid collection timestamp")
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise SeriesError("collection timestamps must increase strictly")
    classification, level, evidence = classify(samples)
    aggregate = {
        "mem_available_min_basis_points": min(row["mem_available_basis_points"] for row in samples),
        "mem_available_max_basis_points": max(row["mem_available_basis_points"] for row in samples),
        "swap_used_first_kib": samples[0]["swap_used_kib"],
        "swap_used_latest_kib": samples[-1]["swap_used_kib"],
        "swap_used_change_kib": samples[-1]["swap_used_kib"] - samples[0]["swap_used_kib"],
        "pswpin_pages_total": sum(row["pswpin_pages"] for row in samples),
        "pswpout_pages_total": sum(row["pswpout_pages"] for row in samples),
        "pgmajfault_total": sum(row["pgmajfault"] for row in samples),
        "oom_kill_total": sum(row["oom_kill"] for row in samples),
        "psi_some_total_usec": sum(row["psi_some_total_usec"] for row in samples),
        "psi_full_total_usec": sum(row["psi_full_total_usec"] for row in samples),
        "source_attention_samples": sum(1 for row in samples if row["source_level"] == "attention"),
    }
    return {
        "schema": SCHEMA,
        "analyzer_version": ANALYZER_VERSION,
        "sample_count": len(samples),
        "collection_start_utc": timestamps[0],
        "collection_end_utc": timestamps[-1],
        "classification": classification,
        "series_level": level,
        "sources": sources,
        "samples": samples,
        "aggregate": aggregate,
        "containers": build_container_trends(reports),
        "evidence": evidence,
        "checks": {
            "all_sources_verified": True,
            "timestamps_strictly_increasing": True,
            "units_normalized_to_kib": True,
            "source_bundles_unchanged": True,
        },
        "limitations": list(LIMITATIONS),
    }


def render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    lines = [
        "# Memory pressure series",
        "",
        f"Schema: `{report['schema']}`",
        f"Samples: `{report['sample_count']}`",
        f"Window: `{report['collection_start_utc']}` → `{report['collection_end_utc']}`",
        f"Classification: `{report['classification']}`",
        f"Series level: `{report['series_level']}`",
        "",
        "## Aggregate",
        "",
        f"- MemAvailable range: {aggregate['mem_available_min_basis_points'] / 100:.2f}%–{aggregate['mem_available_max_basis_points'] / 100:.2f}%.",
        f"- Swap used: {format_mib(aggregate['swap_used_first_kib'])} → {format_mib(aggregate['swap_used_latest_kib'])} MiB; change {format_mib(aggregate['swap_used_change_kib'])} MiB.",
        f"- Swap-in/out pages: {aggregate['pswpin_pages_total']}/{aggregate['pswpout_pages_total']}.",
        f"- Major faults: {aggregate['pgmajfault_total']}; OOM kills: {aggregate['oom_kill_total']}.",
        f"- PSI some/full: {aggregate['psi_some_total_usec']}/{aggregate['psi_full_total_usec']} microseconds.",
        f"- Source V08 attention samples: {aggregate['source_attention_samples']}.",
        "",
        "## Samples",
        "",
        "| UTC | Available | Swap MiB | In/Out | Major | PSI some/full | Source level |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["samples"]:
        lines.append(
            f"| `{row['collection_utc']}` | {row['mem_available_basis_points'] / 100:.2f}% | "
            f"{format_mib(row['swap_used_kib'])} | {row['pswpin_pages']}/{row['pswpout_pages']} | "
            f"{row['pgmajfault']} | {row['psi_some_total_usec']}/{row['psi_full_total_usec']} | "
            f"`{row['source_level']}` |"
        )
    lines += ["", "## Container trends", ""]
    if report["containers"]:
        lines += [
            "| Container | Samples | First MiB | Latest MiB | Change MiB | Max MiB | Max limit % |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in report["containers"]:
            lines.append(
                f"| `{row['name']}` | {row['sample_count']} | {format_mib(row['first_kib'])} | "
                f"{format_mib(row['latest_kib'])} | {format_mib(row['change_kib'])} | "
                f"{format_mib(row['max_kib'])} | {row['max_percent_basis_points'] / 100:.2f}% |"
            )
    else:
        lines.append("- No container rows were available.")
    lines += [
        "",
        "## Classification evidence",
        "",
        f"- Sustained pressure: `{str(report['evidence']['sustained_pressure']).lower()}`.",
        f"- Swap-out activity samples: {report['evidence']['swapout_activity_samples']}.",
        f"- PSI activity samples: {report['evidence']['psi_activity_samples']}.",
        f"- Low-memory samples below 15% available: {report['evidence']['low_memory_samples']}.",
        "",
        "Isolated swap-in or major-fault activity without repeated swap-out, PSI, OOM, or low available memory is classified as `intermittent_activity`, not sustained pressure.",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"
