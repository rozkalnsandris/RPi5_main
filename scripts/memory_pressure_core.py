#!/usr/bin/env python3
"""Shared deterministic parsing and rendering for V08 memory-pressure bundles."""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any

SCHEMA = "rpi5.memory-pressure-diagnostic.v1"
COLLECTOR_VERSION = "v08.0.0"
MEMINFO_KEYS = (
    "MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached",
    "SReclaimable", "Shmem", "SwapTotal", "SwapFree", "Dirty",
    "Writeback", "AnonPages", "Mapped", "Slab", "KernelStack", "PageTables",
)
VMSTAT_KEYS = (
    "pswpin", "pswpout", "pgmajfault", "oom_kill", "allocstall_dma",
    "allocstall_dma32", "allocstall_normal", "allocstall_movable",
    "compact_stall", "kswapd_low_wmark_hit_quickly",
    "kswapd_high_wmark_hit_quickly",
)
SECTION_FILES = (
    "meminfo.tsv", "psi_start.txt", "vmstat_start.tsv", "psi_end.txt",
    "vmstat_end.tsv", "swap.tsv", "zram.tsv", "process_rss.tsv",
    "container_memory.tsv", "kernel_memory_events.txt", "limitations.txt",
)
SECTION_NAMES = tuple(name.rsplit(".", 1)[0] for name in SECTION_FILES)
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$")
SIZE_RE = re.compile(r"^(?:0|[0-9]+(?:\.[0-9]+)?[KMGTP]?i?B)$")
PERCENT_RE = re.compile(r"^(?:0|[0-9]+(?:\.[0-9]+)?)%$")
PSI_LINE_RE = re.compile(
    r"^(some|full) avg10=([0-9]+(?:\.[0-9]+)?) avg60=([0-9]+(?:\.[0-9]+)?) "
    r"avg300=([0-9]+(?:\.[0-9]+)?) total=([0-9]+)$"
)

class BundleError(ValueError):
    pass


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def read_tsv_map(path: pathlib.Path, header: tuple[str, str], allowed: tuple[str, ...]) -> dict[str, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "\t".join(header):
        raise BundleError(f"invalid header: {path.name}")
    result: dict[str, int] = {}
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) != 2 or parts[0] not in allowed or parts[0] in result or not parts[1].isdigit():
            raise BundleError(f"invalid row: {path.name}")
        result[parts[0]] = int(parts[1])
    if tuple(result) != tuple(key for key in allowed if key in result):
        raise BundleError(f"unexpected ordering: {path.name}")
    return result


def parse_psi(path: pathlib.Path) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PSI_LINE_RE.fullmatch(line)
        if not match or match.group(1) in result:
            raise BundleError(f"invalid PSI row: {path.name}")
        result[match.group(1)] = {
            "avg10": float(match.group(2)),
            "avg60": float(match.group(3)),
            "avg300": float(match.group(4)),
            "total_usec": int(match.group(5)),
        }
    if not result or any(key not in {"some", "full"} for key in result):
        raise BundleError(f"missing PSI rows: {path.name}")
    return result


def _delta(after: int, before: int, field: str) -> int:
    if after < before:
        raise BundleError(f"counter regressed: {field}")
    return after - before


def parse_process_rows(path: pathlib.Path) -> list[dict[str, int | str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "name\trss_kib":
        raise BundleError("invalid process header")
    rows: list[dict[str, int | str]] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) != 2 or not SAFE_NAME_RE.fullmatch(parts[0]) or not parts[1].isdigit():
            raise BundleError("invalid process row")
        rows.append({"name": parts[0], "rss_kib": int(parts[1])})
    if len(rows) > 25 or rows != sorted(rows, key=lambda row: (-int(row["rss_kib"]), str(row["name"]))):
        raise BundleError("invalid process ordering")
    return rows


def parse_container_rows(path: pathlib.Path) -> list[dict[str, int | str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "name\tusage\tlimit\tpercent\tpids":
        raise BundleError("invalid container header")
    rows: list[dict[str, int | str]] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if (
            len(parts) != 5
            or not SAFE_NAME_RE.fullmatch(parts[0])
            or not SIZE_RE.fullmatch(parts[1])
            or not SIZE_RE.fullmatch(parts[2])
            or not PERCENT_RE.fullmatch(parts[3])
            or not parts[4].isdigit()
        ):
            raise BundleError("invalid container row")
        rows.append({"name": parts[0], "usage": parts[1], "limit": parts[2], "percent": parts[3], "pids": int(parts[4])})
    if rows != sorted(rows, key=lambda row: str(row["name"])):
        raise BundleError("invalid container ordering")
    return rows


def parse_swap_rows(path: pathlib.Path) -> list[dict[str, int | str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "type\tsize_kib\tused_kib\tpriority":
        raise BundleError("invalid swap header")
    rows: list[dict[str, int | str]] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) != 4 or not SAFE_NAME_RE.fullmatch(parts[0]) or not all(re.fullmatch(r"-?[0-9]+", value) for value in parts[1:]):
            raise BundleError("invalid swap row")
        rows.append({"type": parts[0], "size_kib": int(parts[1]), "used_kib": int(parts[2]), "priority": int(parts[3])})
    return rows


def parse_zram_rows(path: pathlib.Path) -> list[dict[str, int | str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "name\tdisksize_bytes\tdata_bytes\tcompressed_bytes\ttotal_bytes\tstreams":
        raise BundleError("invalid zram header")
    rows: list[dict[str, int | str]] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) != 6 or not SAFE_NAME_RE.fullmatch(parts[0]) or not all(value.isdigit() for value in parts[1:]):
            raise BundleError("invalid zram row")
        rows.append({
            "name": parts[0], "disksize_bytes": int(parts[1]), "data_bytes": int(parts[2]),
            "compressed_bytes": int(parts[3]), "total_bytes": int(parts[4]), "streams": int(parts[5]),
        })
    if rows != sorted(rows, key=lambda row: str(row["name"])):
        raise BundleError("invalid zram ordering")
    return rows


def build_report(bundle: pathlib.Path, metadata: dict[str, Any]) -> dict[str, Any]:
    sections = bundle / "sections"
    meminfo = read_tsv_map(sections / "meminfo.tsv", ("key", "value_kib"), MEMINFO_KEYS)
    vm_start = read_tsv_map(sections / "vmstat_start.tsv", ("key", "value"), VMSTAT_KEYS)
    vm_end = read_tsv_map(sections / "vmstat_end.tsv", ("key", "value"), VMSTAT_KEYS)
    psi_start = parse_psi(sections / "psi_start.txt")
    psi_end = parse_psi(sections / "psi_end.txt")
    processes = parse_process_rows(sections / "process_rss.tsv")
    containers = parse_container_rows(sections / "container_memory.tsv")
    swap_rows = parse_swap_rows(sections / "swap.tsv")
    zram_rows = parse_zram_rows(sections / "zram.tsv")
    limitations = [line for line in (sections / "limitations.txt").read_text(encoding="utf-8").splitlines() if line]
    if limitations != sorted(set(limitations)):
        raise BundleError("limitations must be sorted and unique")

    for required in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
        if required not in meminfo:
            raise BundleError(f"missing meminfo field: {required}")
    mem_total = meminfo["MemTotal"]
    mem_available = meminfo["MemAvailable"]
    if mem_total <= 0 or mem_available > mem_total or meminfo["SwapFree"] > meminfo["SwapTotal"]:
        raise BundleError("invalid memory totals")

    delta_vm = {key: _delta(vm_end.get(key, 0), vm_start.get(key, 0), key) for key in VMSTAT_KEYS}
    psi_delta: dict[str, int] = {}
    for kind in ("some", "full"):
        before = int(psi_start.get(kind, {}).get("total_usec", 0))
        after = int(psi_end.get(kind, {}).get("total_usec", 0))
        psi_delta[kind] = _delta(after, before, f"psi_{kind}")

    swap_used = meminfo["SwapTotal"] - meminfo["SwapFree"]
    available_percent = round((mem_available * 100.0) / mem_total, 2)
    active_swap = delta_vm.get("pswpin", 0) > 0 or delta_vm.get("pswpout", 0) > 0
    if delta_vm.get("oom_kill", 0) > 0 or psi_delta["full"] > 0 or active_swap:
        observation_level = "attention"
    elif swap_used > 0 or available_percent < 20.0:
        observation_level = "informational"
    else:
        observation_level = "none"

    return {
        "schema": SCHEMA,
        "metadata": metadata,
        "observation": {
            "level": observation_level,
            "mem_total_kib": mem_total,
            "mem_available_kib": mem_available,
            "mem_available_percent": available_percent,
            "swap_total_kib": meminfo["SwapTotal"],
            "swap_used_kib": swap_used,
            "sample_delta": {
                "pswpin_pages": delta_vm.get("pswpin", 0),
                "pswpout_pages": delta_vm.get("pswpout", 0),
                "pgmajfault": delta_vm.get("pgmajfault", 0),
                "oom_kill": delta_vm.get("oom_kill", 0),
                "psi_some_total_usec": psi_delta["some"],
                "psi_full_total_usec": psi_delta["full"],
            },
            "process_rows": len(processes),
            "container_rows": len(containers),
            "swap_devices": len(swap_rows),
            "zram_devices": len(zram_rows),
            "kernel_event_lines": len([line for line in (sections / "kernel_memory_events.txt").read_text(encoding="utf-8").splitlines() if line]),
        },
        "top_processes": processes,
        "containers": containers,
        "limitations": limitations,
    }


def render_markdown(report: dict[str, Any]) -> str:
    obs = report["observation"]
    delta = obs["sample_delta"]
    meta = report["metadata"]
    lines = [
        "# Memory pressure diagnostic",
        "",
        f"Schema: `{report['schema']}`",
        f"Collected: `{meta['collected_at_utc']}`",
        f"Sample window: `{meta['sample_seconds']}` seconds",
        f"Observation level: `{obs['level']}`",
        "",
        "## Host memory",
        "",
        f"- MemAvailable: {obs['mem_available_kib']} KiB ({obs['mem_available_percent']}% of {obs['mem_total_kib']} KiB).",
        f"- Swap used: {obs['swap_used_kib']} KiB of {obs['swap_total_kib']} KiB.",
        f"- Swap-in delta: {delta['pswpin_pages']} pages; swap-out delta: {delta['pswpout_pages']} pages.",
        f"- Major-fault delta: {delta['pgmajfault']}; OOM-kill delta: {delta['oom_kill']}.",
        f"- PSI some/full total delta: {delta['psi_some_total_usec']}/{delta['psi_full_total_usec']} microseconds.",
        "",
        "## Safe inventories",
        "",
        f"- Aggregated process-name/RSS rows: {obs['process_rows']}.",
        f"- Container memory rows: {obs['container_rows']}.",
        f"- Swap devices: {obs['swap_devices']}; zram devices: {obs['zram_devices']}.",
        f"- Bounded kernel memory-event lines: {obs['kernel_event_lines']}.",
        "",
        "The level is a deterministic review hint, not a root-cause diagnosis. Active swap movement, full-memory PSI, or an OOM increment produces `attention`; retained swap alone is informational.",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"
