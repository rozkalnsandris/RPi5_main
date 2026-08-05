#!/usr/bin/env python3
"""Collect a bounded, non-root V11 AdGuard Home memory-attribution bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

from adguard_memory_core import (
    CGROUP_EVENT_KEYS,
    CGROUP_SCALAR_KEYS,
    CGROUP_STAT_KEYS,
    COLLECTOR_VERSION,
    SCHEMA,
    SMAPS_KEYS,
    STATUS_COUNT_KEYS,
    STATUS_MEMORY_KEYS,
    build_report,
    canonical_json,
    render_markdown,
)

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
PROC_ROOT = pathlib.Path(os.environ.get("ADGUARD_ATTR_PROC_ROOT", "/proc"))
CGROUP_ROOT = pathlib.Path(os.environ.get("ADGUARD_ATTR_CGROUP_ROOT", "/sys/fs/cgroup"))
MAX_PROCESSES = 8


def fail(message: str) -> None:
    raise SystemExit(f"collect-adguard-memory-attribution: {message}")


def effective_uid() -> int:
    override = os.environ.get("ADGUARD_ATTR_TEST_UID")
    return int(override) if override is not None else os.geteuid()


def no_symlink_components(path: pathlib.Path) -> None:
    current = pathlib.Path(path.anchor or "/") if path.is_absolute() else pathlib.Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            fail("symlink path component rejected")


def allowed_output(path: pathlib.Path) -> pathlib.Path:
    requested = path if path.is_absolute() else pathlib.Path.cwd() / path
    no_symlink_components(requested)
    parent = requested.parent.resolve(strict=True)
    target = parent / requested.name
    if target.exists() or target.is_symlink():
        fail("output already exists")
    allowed = False
    for name in ("evidence", "exports"):
        try:
            target.relative_to(REPO / name)
            allowed = True
        except ValueError:
            pass
    if not allowed:
        fail("output is outside repository evidence/exports")
    return target


def git_commit() -> str:
    override = os.environ.get("ADGUARD_ATTR_TEST_COMMIT")
    if override:
        return override
    completed = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 else "unavailable"


def collected_utc() -> str:
    override = os.environ.get("ADGUARD_ATTR_FIXED_UTC")
    if override:
        return override
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def find_processes() -> list[pathlib.Path]:
    result: list[pathlib.Path] = []
    for child in sorted(PROC_ROOT.iterdir(), key=lambda path: path.name):
        if not child.name.isdigit() or not child.is_dir():
            continue
        try:
            name = read_text(child / "comm").strip()
        except (OSError, UnicodeError):
            continue
        if name == "AdGuardHome":
            result.append(child)
    if not result:
        fail("no exact AdGuardHome process found")
    if len(result) > MAX_PROCESSES:
        fail("too many exact AdGuardHome processes")
    return result


def parse_status(path: pathlib.Path) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in read_text(path).splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        if key not in STATUS_MEMORY_KEYS and key != "Threads":
            continue
        parts = raw.split()
        if not parts or not parts[0].isdigit():
            fail("invalid process status field")
        values[key] = int(parts[0])
    missing = [key for key in STATUS_MEMORY_KEYS + ("Threads",) if key not in values]
    if missing:
        fail("missing process status fields")
    return values


def parse_smaps(path: pathlib.Path) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in read_text(path).splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        if key not in SMAPS_KEYS:
            continue
        parts = raw.split()
        if not parts or not parts[0].isdigit():
            fail("invalid smaps field")
        values[key] = int(parts[0])
    return values


def cgroup_relative_path(process: pathlib.Path) -> pathlib.PurePosixPath | None:
    try:
        lines = read_text(process / "cgroup").splitlines()
    except OSError:
        return None
    for line in lines:
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[0] == "0" and parts[1] == "":
            relative = pathlib.PurePosixPath(parts[2])
            if ".." in relative.parts:
                fail("unsafe cgroup path")
            return relative
    return None


def read_single_int(path: pathlib.Path) -> int | None:
    try:
        raw = read_text(path).strip()
    except OSError:
        return None
    if raw == "max":
        return -1
    if not raw.isdigit():
        fail("invalid cgroup scalar")
    return int(raw)


def read_keyed_ints(path: pathlib.Path, allowed: tuple[str, ...]) -> dict[str, int]:
    try:
        lines = read_text(path).splitlines()
    except OSError:
        return {}
    result: dict[str, int] = {}
    for line in lines:
        parts = line.split()
        if len(parts) != 2 or parts[0] not in allowed or not parts[1].isdigit():
            if parts and parts[0] in allowed:
                fail("invalid cgroup metric")
            continue
        if parts[0] in result:
            fail("duplicate cgroup metric")
        result[parts[0]] = int(parts[1])
    return result


def docker_stats() -> tuple[bool, str, str, str, int]:
    if os.environ.get("ADGUARD_ATTR_DISABLE_DOCKER") == "1":
        return False, "0", "0", "0%", 0
    completed = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}",
            "adguard",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        return False, "0", "0", "0%", 0
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        return False, "0", "0", "0%", 0
    parts = lines[0].split("\t")
    if len(parts) != 4 or parts[0] != "adguard" or " / " not in parts[1]:
        return False, "0", "0", "0%", 0
    usage, limit = parts[1].split(" / ", 1)
    if not parts[3].isdigit():
        return False, "0", "0", "0%", 0
    return True, usage.strip(), limit.strip(), parts[2].strip(), int(parts[3])


def write_map(
    path: pathlib.Path,
    *,
    header: str,
    allowed: tuple[str, ...],
    values: dict[str, int],
) -> None:
    lines = [header]
    lines.extend(f"{key}\t{values[key]}" for key in allowed if key in values)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_bundle(target: pathlib.Path) -> pathlib.Path:
    processes = find_processes()
    limitations: set[str] = set()

    status_totals = {key: 0 for key in STATUS_MEMORY_KEYS}
    status_totals.update({"process_count": len(processes), "Threads": 0, "fd_count": 0})
    smaps_totals: dict[str, int] = {}
    cgroup_paths: set[pathlib.PurePosixPath] = set()

    for process in processes:
        status = parse_status(process / "status")
        for key in STATUS_MEMORY_KEYS:
            status_totals[key] += status[key]
        status_totals["Threads"] += status["Threads"]
        try:
            status_totals["fd_count"] += sum(1 for _ in (process / "fd").iterdir())
        except OSError:
            limitations.add("Process file-descriptor directories were not readable; FD count may be incomplete.")

        try:
            smaps = parse_smaps(process / "smaps_rollup")
        except OSError:
            smaps = {}
            limitations.add("Process smaps_rollup was not readable without elevated privileges; cgroup or status attribution was used.")
        for key, value in smaps.items():
            smaps_totals[key] = smaps_totals.get(key, 0) + value

        relative = cgroup_relative_path(process)
        if relative is not None:
            cgroup_paths.add(relative)

    scalars: dict[str, int] = {}
    cgroup_stat: dict[str, int] = {}
    cgroup_events: dict[str, int] = {}
    if len(cgroup_paths) == 1:
        relative = next(iter(cgroup_paths))
        relative_parts = [part for part in relative.parts if part not in {"/", ""}]
        cgroup_dir = CGROUP_ROOT.joinpath(*relative_parts)
        scalar_files = {
            "memory_current_bytes": "memory.current",
            "memory_peak_bytes": "memory.peak",
            "memory_swap_current_bytes": "memory.swap.current",
            "memory_max_bytes": "memory.max",
        }
        for key, filename in scalar_files.items():
            value = read_single_int(cgroup_dir / filename)
            if value is not None:
                scalars[key] = value
        cgroup_stat = read_keyed_ints(cgroup_dir / "memory.stat", CGROUP_STAT_KEYS)
        cgroup_events = read_keyed_ints(cgroup_dir / "memory.events", CGROUP_EVENT_KEYS)
        if not scalars and not cgroup_stat and not cgroup_events:
            limitations.add("The AdGuard cgroup-v2 memory files were unavailable in this collection context.")
    elif not cgroup_paths:
        limitations.add("No cgroup-v2 path was available for the exact AdGuardHome process.")
    else:
        limitations.add("Exact AdGuardHome processes appeared in multiple cgroups; cgroup attribution was omitted.")

    available, usage, limit, percent, pids = docker_stats()
    if not available:
        limitations.add("Docker stats for the exact adguard container was unavailable.")

    if not limitations:
        limitations.add("No collection limitations were detected.")

    metadata = {
        "schema": SCHEMA,
        "collector_version": COLLECTOR_VERSION,
        "git_commit": git_commit(),
        "collected_at_utc": collected_utc(),
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = pathlib.Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=str(target.parent)))
    try:
        sections = temp / "sections"
        sections.mkdir()
        write_map(
            sections / "process-status.tsv",
            header="key\tvalue",
            allowed=STATUS_COUNT_KEYS + STATUS_MEMORY_KEYS,
            values=status_totals,
        )
        write_map(
            sections / "smaps-rollup.tsv",
            header="key\tvalue_kib",
            allowed=SMAPS_KEYS,
            values=smaps_totals,
        )
        write_map(
            sections / "cgroup-scalars.tsv",
            header="key\tvalue",
            allowed=CGROUP_SCALAR_KEYS,
            values=scalars,
        )
        write_map(
            sections / "cgroup-memory-stat.tsv",
            header="key\tvalue_bytes",
            allowed=CGROUP_STAT_KEYS,
            values=cgroup_stat,
        )
        write_map(
            sections / "cgroup-memory-events.tsv",
            header="key\tvalue",
            allowed=CGROUP_EVENT_KEYS,
            values=cgroup_events,
        )
        (sections / "container-memory.tsv").write_text(
            "available\tusage\tlimit\tpercent\tpids\n"
            f"{str(available).lower()}\t{usage}\t{limit}\t{percent}\t{pids}\n",
            encoding="utf-8",
        )
        (sections / "limitations.txt").write_text(
            "\n".join(sorted(limitations)) + "\n",
            encoding="utf-8",
        )
        (temp / "metadata.json").write_text(canonical_json(metadata), encoding="utf-8")
        report = build_report(temp, metadata)
        (temp / "report.json").write_text(canonical_json(report), encoding="utf-8")
        (temp / "report.md").write_text(render_markdown(report), encoding="utf-8")

        inventory = sorted(
            str(path.relative_to(temp))
            for path in temp.rglob("*")
            if path.is_file()
        )
        (temp / "file-inventory.txt").write_text(
            "\n".join(inventory) + "\n",
            encoding="utf-8",
        )
        checksum_files = sorted(
            path
            for path in temp.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS"
        )
        (temp / "SHA256SUMS").write_text(
            "".join(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                f"{path.relative_to(temp)}\n"
                for path in checksum_files
            ),
            encoding="utf-8",
        )
        os.chmod(temp, 0o700)
        for path in temp.rglob("*"):
            if path.is_file():
                os.chmod(path, 0o600)
            elif path.is_dir():
                os.chmod(path, 0o700)
        temp.rename(target)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if effective_uid() == 0:
        fail("root execution rejected")
    target = allowed_output(pathlib.Path(args.output))
    result = build_bundle(target)
    report = json.loads((result / "report.json").read_text(encoding="utf-8"))
    print(f"AdGuard memory result: {result}")
    print(f"Observation level: {report['observation_level']}")
    print(f"Dominant component: {report['attribution']['dominant_component']}")


if __name__ == "__main__":
    main()
