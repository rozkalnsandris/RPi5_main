#!/usr/bin/env python3
"""Shared parsing, attribution, and rendering for V11 AdGuard memory bundles."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import pathlib
import re
from typing import Any

SCHEMA = "rpi5.adguard-memory-attribution.v1"
COLLECTOR_VERSION = "v11.0.0"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SIZE_RE = re.compile(r"^(0|[0-9]+(?:\.[0-9]+)?)(B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)$")
PERCENT_RE = re.compile(r"^(0|[0-9]+(?:\.[0-9]+)?)%$")

STATUS_MEMORY_KEYS = (
    "VmSize", "VmRSS", "RssAnon", "RssFile", "RssShmem", "VmData",
    "VmStk", "VmExe", "VmLib", "VmPTE", "VmSwap",
)
STATUS_COUNT_KEYS = ("process_count", "Threads", "fd_count")
SMAPS_KEYS = (
    "Rss", "Pss", "Pss_Anon", "Pss_File", "Pss_Shmem",
    "Shared_Clean", "Shared_Dirty", "Private_Clean", "Private_Dirty",
    "Anonymous", "AnonHugePages", "Swap", "SwapPss", "Locked",
)
CGROUP_SCALAR_KEYS = (
    "memory_current_bytes",
    "memory_peak_bytes",
    "memory_swap_current_bytes",
    "memory_max_bytes",
)
CGROUP_STAT_KEYS = (
    "anon", "file", "kernel", "kernel_stack", "pagetables", "percpu",
    "sock", "shmem", "file_mapped", "file_dirty", "file_writeback",
    "swapcached", "slab_reclaimable", "slab_unreclaimable",
    "workingset_refault_anon", "workingset_refault_file",
    "workingset_activate_anon", "workingset_activate_file",
    "pgfault", "pgmajfault", "pgrefill", "pgscan", "pgsteal",
    "thp_fault_alloc",
)
CGROUP_EVENT_KEYS = ("low", "high", "max", "oom", "oom_kill", "oom_group_kill")
SECTION_FILES = (
    "process-status.tsv",
    "smaps-rollup.tsv",
    "cgroup-scalars.tsv",
    "cgroup-memory-stat.tsv",
    "cgroup-memory-events.tsv",
    "container-memory.tsv",
    "limitations.txt",
)


class BundleError(ValueError):
    pass


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _read_map(
    path: pathlib.Path,
    *,
    header: str,
    allowed: tuple[str, ...],
    allow_missing: bool = True,
) -> dict[str, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != header:
        raise BundleError(f"invalid header: {path.name}")
    result: dict[str, int] = {}
    for line in lines[1:]:
        parts = line.split("\t")
        if (
            len(parts) != 2
            or parts[0] not in allowed
            or parts[0] in result
            or not re.fullmatch(r"-?[0-9]+", parts[1])
        ):
            raise BundleError(f"invalid row: {path.name}")
        result[parts[0]] = int(parts[1])
    expected_order = tuple(key for key in allowed if key in result)
    if tuple(result) != expected_order:
        raise BundleError(f"unexpected ordering: {path.name}")
    if not allow_missing and tuple(result) != allowed:
        raise BundleError(f"missing fields: {path.name}")
    return result


def read_process_status(path: pathlib.Path) -> dict[str, int]:
    return _read_map(
        path,
        header="key\tvalue",
        allowed=STATUS_COUNT_KEYS + STATUS_MEMORY_KEYS,
        allow_missing=False,
    )


def read_smaps(path: pathlib.Path) -> dict[str, int]:
    return _read_map(
        path,
        header="key\tvalue_kib",
        allowed=SMAPS_KEYS,
        allow_missing=True,
    )


def read_cgroup_scalars(path: pathlib.Path) -> dict[str, int]:
    return _read_map(
        path,
        header="key\tvalue",
        allowed=CGROUP_SCALAR_KEYS,
        allow_missing=True,
    )


def read_cgroup_stat(path: pathlib.Path) -> dict[str, int]:
    return _read_map(
        path,
        header="key\tvalue_bytes",
        allowed=CGROUP_STAT_KEYS,
        allow_missing=True,
    )


def read_cgroup_events(path: pathlib.Path) -> dict[str, int]:
    return _read_map(
        path,
        header="key\tvalue",
        allowed=CGROUP_EVENT_KEYS,
        allow_missing=True,
    )


def size_to_kib(value: str) -> int:
    match = SIZE_RE.fullmatch(value)
    if not match:
        raise BundleError("invalid container size")
    try:
        number = Decimal(match.group(1))
    except InvalidOperation as error:
        raise BundleError("invalid container size") from error
    unit = match.group(2)
    factors = {
        "B": Decimal(1) / Decimal(1024),
        "KB": Decimal(1000) / Decimal(1024),
        "MB": Decimal(1000**2) / Decimal(1024),
        "GB": Decimal(1000**3) / Decimal(1024),
        "TB": Decimal(1000**4) / Decimal(1024),
        "KiB": Decimal(1),
        "MiB": Decimal(1024),
        "GiB": Decimal(1024**2),
        "TiB": Decimal(1024**3),
    }
    return int((number * factors[unit]).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def percent_to_basis_points(value: str) -> int:
    match = PERCENT_RE.fullmatch(value)
    if not match:
        raise BundleError("invalid container percentage")
    try:
        number = Decimal(match.group(1))
    except InvalidOperation as error:
        raise BundleError("invalid container percentage") from error
    result = int((number * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if result < 0 or result > 10000:
        raise BundleError("container percentage outside 0..100")
    return result


def read_container(path: pathlib.Path) -> dict[str, int | bool]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = "available\tusage\tlimit\tpercent\tpids"
    if not lines or lines[0] != header or len(lines) != 2:
        raise BundleError("invalid container memory table")
    parts = lines[1].split("\t")
    if len(parts) != 5 or parts[0] not in {"true", "false"}:
        raise BundleError("invalid container memory row")
    if parts[0] == "false":
        if parts[1:] != ["0", "0", "0%", "0"]:
            raise BundleError("invalid unavailable container row")
        return {
            "available": False,
            "usage_kib": 0,
            "limit_kib": 0,
            "percent_basis_points": 0,
            "pids": 0,
        }
    if not parts[4].isdigit():
        raise BundleError("invalid container pids")
    usage_kib = size_to_kib(parts[1])
    limit_kib = size_to_kib(parts[2])
    percent = percent_to_basis_points(parts[3])
    if limit_kib <= 0 or usage_kib < 0 or usage_kib > limit_kib:
        raise BundleError("invalid container memory totals")
    return {
        "available": True,
        "usage_kib": usage_kib,
        "limit_kib": limit_kib,
        "percent_basis_points": percent,
        "pids": int(parts[4]),
    }


def _kib_from_bytes(value: int) -> int:
    return (value + 512) // 1024


def _percent_basis_points(part: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(
        (Decimal(part) * Decimal(10000) / Decimal(total)).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def build_report(bundle: pathlib.Path, metadata: dict[str, Any]) -> dict[str, Any]:
    sections = bundle / "sections"
    status = read_process_status(sections / "process-status.tsv")
    smaps = read_smaps(sections / "smaps-rollup.tsv")
    cgroup_scalars = read_cgroup_scalars(sections / "cgroup-scalars.tsv")
    cgroup_stat = read_cgroup_stat(sections / "cgroup-memory-stat.tsv")
    cgroup_events = read_cgroup_events(sections / "cgroup-memory-events.tsv")
    container = read_container(sections / "container-memory.tsv")
    limitations = [
        line
        for line in (sections / "limitations.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if limitations != sorted(set(limitations)):
        raise BundleError("limitations must be sorted and unique")

    if status["process_count"] <= 0 or status["process_count"] > 8:
        raise BundleError("invalid process count")
    if status["Threads"] < status["process_count"] or status["fd_count"] < 0:
        raise BundleError("invalid process counters")
    for key in STATUS_MEMORY_KEYS:
        if status[key] < 0:
            raise BundleError("negative process memory")
    for mapping in (smaps, cgroup_scalars, cgroup_stat, cgroup_events):
        if any(value < -1 for value in mapping.values()):
            raise BundleError("invalid negative metric")

    if smaps.get("Pss", 0) > 0:
        basis = "process_pss"
        total_kib = smaps["Pss"]
        anon_kib = smaps.get("Pss_Anon", smaps.get("Anonymous", 0))
        file_kib = smaps.get("Pss_File", 0)
        shmem_kib = smaps.get("Pss_Shmem", 0)
    elif cgroup_scalars.get("memory_current_bytes", 0) > 0:
        basis = "cgroup_current"
        total_kib = _kib_from_bytes(cgroup_scalars["memory_current_bytes"])
        anon_kib = _kib_from_bytes(cgroup_stat.get("anon", 0))
        file_kib = _kib_from_bytes(cgroup_stat.get("file", 0))
        shmem_kib = _kib_from_bytes(cgroup_stat.get("shmem", 0))
    else:
        basis = "process_rss"
        total_kib = status["VmRSS"]
        anon_kib = status["RssAnon"]
        file_kib = status["RssFile"]
        shmem_kib = status["RssShmem"]

    if total_kib <= 0:
        raise BundleError("missing attribution basis")
    if any(value < 0 for value in (anon_kib, file_kib, shmem_kib)):
        raise BundleError("invalid attribution component")

    anon_bp = _percent_basis_points(anon_kib, total_kib)
    file_bp = _percent_basis_points(file_kib, total_kib)
    shmem_bp = _percent_basis_points(shmem_kib, total_kib)
    components = {
        "anonymous": anon_kib,
        "file": file_kib,
        "shared": shmem_kib,
    }
    largest_name, largest_value = max(components.items(), key=lambda item: (item[1], item[0]))
    largest_bp = _percent_basis_points(largest_value, total_kib)
    dominant = largest_name if largest_bp >= 5000 else "mixed"

    process_swap_kib = smaps.get("SwapPss") or smaps.get("Swap") or status["VmSwap"]
    cgroup_swap_kib = _kib_from_bytes(cgroup_scalars.get("memory_swap_current_bytes", 0))
    kernel_kib = _kib_from_bytes(cgroup_stat.get("kernel", 0))
    sock_kib = _kib_from_bytes(cgroup_stat.get("sock", 0))
    slab_reclaimable_kib = _kib_from_bytes(cgroup_stat.get("slab_reclaimable", 0))
    slab_unreclaimable_kib = _kib_from_bytes(cgroup_stat.get("slab_unreclaimable", 0))

    event_oom = cgroup_events.get("oom", 0)
    event_oom_kill = cgroup_events.get("oom_kill", 0)
    percent = int(container["percent_basis_points"])
    if event_oom > 0 or event_oom_kill > 0 or percent >= 9000:
        level = "attention"
    elif percent >= 7500 or cgroup_swap_kib > 0 or process_swap_kib > 0:
        level = "informational"
    else:
        level = "none"

    reason_codes: list[str] = []
    if dominant == "anonymous":
        reason_codes.append("anonymous_memory_dominant")
    elif dominant == "file":
        reason_codes.append("file_memory_dominant")
    elif dominant == "shared":
        reason_codes.append("shared_memory_dominant")
    else:
        reason_codes.append("mixed_memory_components")
    if percent >= 9000:
        reason_codes.append("container_limit_usage_ge_90_percent")
    elif percent >= 7500:
        reason_codes.append("container_limit_usage_ge_75_percent")
    if process_swap_kib > 0 or cgroup_swap_kib > 0:
        reason_codes.append("adguard_memory_present_in_swap")
    if event_oom > 0 or event_oom_kill > 0:
        reason_codes.append("cgroup_oom_history_present")
    if not smaps:
        reason_codes.append("process_smaps_unavailable")

    headroom_kib = (
        int(container["limit_kib"]) - int(container["usage_kib"])
        if bool(container["available"])
        else 0
    )

    return {
        "schema": SCHEMA,
        "metadata": metadata,
        "observation_level": level,
        "process": {
            "count": status["process_count"],
            "threads": status["Threads"],
            "fd_count": status["fd_count"],
            "status_kib": {key: status[key] for key in STATUS_MEMORY_KEYS},
            "smaps_kib": smaps,
        },
        "cgroup": {
            "available": bool(cgroup_scalars or cgroup_stat or cgroup_events),
            "scalars": cgroup_scalars,
            "memory_stat_bytes": cgroup_stat,
            "memory_events": cgroup_events,
        },
        "container": container,
        "attribution": {
            "basis": basis,
            "basis_total_kib": total_kib,
            "anonymous_kib": anon_kib,
            "file_kib": file_kib,
            "shared_kib": shmem_kib,
            "anonymous_percent_basis_points": anon_bp,
            "file_percent_basis_points": file_bp,
            "shared_percent_basis_points": shmem_bp,
            "dominant_component": dominant,
            "process_swap_kib": process_swap_kib,
            "cgroup_swap_kib": cgroup_swap_kib,
            "kernel_kib": kernel_kib,
            "sock_kib": sock_kib,
            "slab_reclaimable_kib": slab_reclaimable_kib,
            "slab_unreclaimable_kib": slab_unreclaimable_kib,
            "container_headroom_kib": headroom_kib,
            "reason_codes": reason_codes,
        },
        "limitations": limitations,
    }


def _mib(kib: int) -> str:
    return f"{kib / 1024.0:.2f}"


def _pct(bp: int) -> str:
    return f"{bp / 100.0:.2f}%"


def render_markdown(report: dict[str, Any]) -> str:
    meta = report["metadata"]
    process = report["process"]
    cgroup = report["cgroup"]
    container = report["container"]
    attr = report["attribution"]
    lines = [
        "# AdGuard memory attribution",
        "",
        f"Schema: `{report['schema']}`",
        f"Collected: `{meta['collected_at_utc']}`",
        f"Observation level: `{report['observation_level']}`",
        "",
        "## Process and container",
        "",
        f"- Exact `AdGuardHome` processes: {process['count']}; threads: {process['threads']}; visible FD count: {process['fd_count']}.",
        f"- Process RSS: {_mib(process['status_kib']['VmRSS'])} MiB; process swap: {_mib(attr['process_swap_kib'])} MiB.",
    ]
    if container["available"]:
        lines.append(
            f"- Container usage: {_mib(container['usage_kib'])} MiB of "
            f"{_mib(container['limit_kib'])} MiB "
            f"({_pct(container['percent_basis_points'])}); "
            f"headroom {_mib(attr['container_headroom_kib'])} MiB."
        )
    else:
        lines.append("- Container usage: unavailable.")
    lines.extend([
        "",
        "## Attribution",
        "",
        f"- Attribution basis: `{attr['basis']}` ({_mib(attr['basis_total_kib'])} MiB).",
        f"- Anonymous: {_mib(attr['anonymous_kib'])} MiB ({_pct(attr['anonymous_percent_basis_points'])}).",
        f"- File-backed: {_mib(attr['file_kib'])} MiB ({_pct(attr['file_percent_basis_points'])}).",
        f"- Shared/shmem: {_mib(attr['shared_kib'])} MiB ({_pct(attr['shared_percent_basis_points'])}).",
        f"- Dominant component: `{attr['dominant_component']}`.",
        f"- Cgroup swap: {_mib(attr['cgroup_swap_kib'])} MiB; kernel: {_mib(attr['kernel_kib'])} MiB; socket: {_mib(attr['sock_kib'])} MiB.",
        f"- Slab reclaimable/unreclaimable: {_mib(attr['slab_reclaimable_kib'])}/{_mib(attr['slab_unreclaimable_kib'])} MiB.",
        "",
        "## Reason codes",
        "",
    ])
    lines.extend(f"- `{reason}`" for reason in attr["reason_codes"])
    lines.extend([
        "",
        "## Cgroup",
        "",
        f"- Available: `{str(cgroup['available']).lower()}`.",
        f"- OOM/OOM-kill counters: {cgroup['memory_events'].get('oom', 0)}/{cgroup['memory_events'].get('oom_kill', 0)}.",
        "",
        "## Limitations",
        "",
    ])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend([
        "",
        "This report attributes Linux memory classes only. It cannot distinguish AdGuard Home's DNS cache, query-log buffer, statistics, filter structures, runtime clients, or another Go heap owner without application-level metrics or a separately approved heap profile.",
    ])
    return "\n".join(lines) + "\n"
