#!/usr/bin/env python3
"""Bounded, unprivileged Grafana cgroup-v2 identity-continuous sampler.

Source-only until separately owner-authorized on the RPi5. No daemon, scheduler,
Docker API, protected configuration, privileged files or runtime mutation.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import errno
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess
import sys
import time

from grafana_continuity_core import (
    SCHEMA, VERSION, EVENTS, EvidenceError, canonical_json, check_report,
    checksums, event_deltas, inventory, render_markdown,
)

REPO = Path(__file__).resolve().parent.parent
TEST_MODE = os.environ.get("GRAFANA_CONT_TEST_MODE") == "1"
PROC = Path(os.environ.get("GRAFANA_CONT_PROC", "/proc"))
CGROUP = Path(os.environ.get("GRAFANA_CONT_CGROUP", "/sys/fs/cgroup"))
SHA = re.compile(r"[0-9a-f]{40}\Z")
CID = re.compile(r"[0-9a-f]{64}\Z")
INTEGER = re.compile(r"(0|[1-9][0-9]*)\Z")
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
MAX_READ = 4096


class CaptureError(RuntimeError):
    """Fail closed without exposing host identifiers or paths."""


def reject() -> None:
    raise CaptureError("sanitized Grafana continuity capture failure")


def safe_components(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        reject()
    current = Path("/")
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            reject()


def output_target(raw: str) -> tuple[Path, int]:
    path = Path(raw)
    path = path if path.is_absolute() else Path.cwd() / path
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", path.name)
        or ".." in path.parts):
        reject()
    safe_components(path)
    if not any(path.is_relative_to(REPO / name) for name in ("evidence", "exports")):
        reject()
    if not path.parent.is_dir() or path.exists() or path.is_symlink():
        reject()
    fd = os.open(path.parent, DIRECTORY_FLAGS)
    if os.fstat(fd).st_ino != path.parent.stat().st_ino or \
       os.fstat(fd).st_dev != path.parent.stat().st_dev:
        os.close(fd)
        reject()
    return path, fd


def source_sha() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, timeout=5, check=False,
    )
    value = result.stdout.decode("ascii", "strict").strip()
    if result.returncode or len(result.stdout) > 128 or not SHA.fullmatch(value):
        reject()
    return value


def docker_id() -> str:
    result = subprocess.run(
        ["docker", "ps", "--no-trunc", "--filter", "name=^/grafana$",
         "--format", "{{.ID}}\t{{.Names}}"],
        capture_output=True, timeout=10, check=False,
    )
    if result.returncode or len(result.stdout) > 1024:
        reject()
    rows = result.stdout.decode("ascii", "strict").splitlines()
    if len(rows) != 1:
        reject()
    parts = rows[0].split("\t")
    if len(parts) != 2 or parts[1] != "grafana" or not CID.fullmatch(parts[0]):
        reject()
    return parts[0]


def limited_text(path: Path) -> str:
    with path.open("rb") as handle:
        data = handle.read(MAX_READ + 1)
    if len(data) > MAX_READ:
        reject()
    return data.decode("ascii", "strict")


def grafana_pid() -> int:
    hits = []
    for item in PROC.iterdir():
        if not item.name.isdecimal() or not item.is_dir():
            continue
        try:
            if limited_text(item / "comm").strip() == "grafana":
                hits.append(int(item.name))
        except (OSError, UnicodeError):
            continue
        if len(hits) > 1:
            reject()
    if len(hits) != 1:
        reject()
    return hits[0]


def process_starttime(pid: int) -> int:
    line = limited_text(PROC / str(pid) / "stat").strip()
    end = line.rfind(") ")
    if not line.startswith(f"{pid} (") or end <= 0:
        reject()
    fields = line[end + 2:].split()
    # /proc/PID/stat field 22 is index 19 after the field-2 "(comm)".
    if len(fields) < 20 or not INTEGER.fullmatch(fields[19]):
        reject()
    value = int(fields[19])
    if value <= 0:
        reject()
    return value


def process_cgroup(pid: int, container: str) -> PurePosixPath:
    lines = limited_text(PROC / str(pid) / "cgroup").splitlines()
    if len(lines) != 1 or not lines[0].startswith("0::"):
        reject()
    raw = lines[0][3:]
    if raw not in (f"/docker/{container}",
                   f"/system.slice/docker-{container}.scope"):
        reject()
    return PurePosixPath(raw)


def pin_cgroup(relative: PurePosixPath) -> tuple[int, Path]:
    safe_components(CGROUP)
    fd = os.open(CGROUP, DIRECTORY_FLAGS)
    try:
        path = CGROUP
        for segment in relative.parts[1:]:
            if not segment or segment in (".", ".."):
                reject()
            child = os.open(segment, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
            path /= segment
        return fd, path
    except BaseException:
        os.close(fd)
        raise


def ensure_identity(container: str, pid: int, start: int, relative: PurePosixPath,
                    cgfd: int, cgpath: Path) -> None:
    if (docker_id() != container or grafana_pid() != pid
        or limited_text(PROC / str(pid) / "comm").strip() != "grafana"
        or process_starttime(pid) != start
        or process_cgroup(pid, container) != relative):
        reject()
    pinned = os.fstat(cgfd)
    current = os.stat(cgpath, follow_symlinks=False)
    if (not stat.S_ISDIR(pinned.st_mode) or not stat.S_ISDIR(current.st_mode)
        or (pinned.st_dev, pinned.st_ino) != (current.st_dev, current.st_ino)):
        reject()


def read_fd_file(cgfd: int, filename: str, *, optional: bool = False) -> str | None:
    try:
        fd = os.open(filename, FILE_FLAGS, dir_fd=cgfd)
    except (FileNotFoundError, PermissionError):
        if optional:
            return None
        raise
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            reject()
        raw = os.read(fd, MAX_READ + 1)
    finally:
        os.close(fd)
    if len(raw) > MAX_READ:
        reject()
    return raw.decode("ascii", "strict").strip()


def number(raw: str | None, *, unlimited: bool = False) -> int | None:
    if raw is None or (unlimited and raw == "max"):
        return None
    if not INTEGER.fullmatch(raw):
        reject()
    result = int(raw)
    if result > (1 << 63) - 1:
        reject()
    return result


def events(cgfd: int, filename: str) -> dict[str, int]:
    raw = read_fd_file(cgfd, filename)
    if raw is None:
        reject()
    found: dict[str, int] = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) != 2 or not re.fullmatch(r"[a-z_]+", fields[0]):
            reject()
        key, value = fields
        if key in found:
            reject()
        found[key] = number(value)
    if not all(key in found for key in EVENTS):
        reject()
    return {key: found[key] for key in EVENTS}


def reading(cgfd: int, stamp: str, elapsed_ms: int) -> dict:
    current = number(read_fd_file(cgfd, "memory.current"))
    maximum = number(read_fd_file(cgfd, "memory.max"), unlimited=True)
    swap = number(read_fd_file(cgfd, "memory.swap.current", optional=True))
    peak = number(read_fd_file(cgfd, "memory.peak", optional=True))
    return {
        "utc": stamp, "elapsed_ms": elapsed_ms,
        "memory_current_bytes": current, "memory_max_bytes": maximum,
        "memory_swap_current_bytes": swap, "memory_peak_bytes": peak,
        "events_local": events(cgfd, "memory.events.local"),
        "events_hierarchical": events(cgfd, "memory.events"),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_member(dirfd: int, name: str, payload: bytes) -> None:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dirfd)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def publish(target: Path, parentfd: int, report: dict,
            identity_check) -> None:
    # All capture and schema validation happen before the first evidence write.
    data = canonical_json(report).encode("ascii")
    markdown = render_markdown(report).encode("ascii")
    outputs = {
        "report.json": data, "report.md": markdown,
        "file-inventory.txt": inventory().encode("ascii"),
        "SHA256SUMS": checksums(data, markdown).encode("ascii"),
    }
    if max(map(len, outputs.values())) > 262144:
        reject()
    stage = "." + target.name + "." + secrets.token_hex(12)
    os.mkdir(stage, 0o700, dir_fd=parentfd)
    stagefd = os.open(stage, DIRECTORY_FLAGS, dir_fd=parentfd)
    try:
        for name, payload in outputs.items():
            write_member(stagefd, name, payload)
        os.fsync(stagefd)
        # The existing offline verifier is independent of this collector.
        check = subprocess.run(
            [sys.executable, "-B", str(REPO / "scripts" /
                                      "verify-grafana-continuity.py"),
             str(target.parent / stage)],
            capture_output=True, timeout=10, check=False,
        )
        if check.returncode:
            reject()
        identity_check()
        # Linux renameat2 RENAME_NOREPLACE: never replace an existing target.
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p,
                           ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(parentfd, os.fsencode(stage), parentfd,
                  os.fsencode(target.name), 1) != 0:
            e = ctypes.get_errno()
            raise OSError(e, os.strerror(e))
        os.fsync(parentfd)
    finally:
        os.close(stagefd)
    # Deliberately preserve staging evidence after any post-write failure.


def collect(raw: str, samples: int, interval: int, *,
            tick=time.monotonic, pause=time.sleep, wall=utc_now) -> Path:
    if (os.geteuid() == 0 or type(samples) is not int or not 2 <= samples <= 8
        or type(interval) is not int or not 15 <= interval <= 300
        or (samples - 1) * interval > 2400):
        reject()
    if TEST_MODE:
        if (not PROC.is_relative_to(REPO / "evidence")
            or not CGROUP.is_relative_to(REPO / "evidence")):
            reject()
    elif (PROC != Path("/proc") or CGROUP != Path("/sys/fs/cgroup")
          or any(key.startswith("GRAFANA_CONT_TEST")
                 for key in os.environ)):
        reject()
    target, parentfd = output_target(raw)
    try:
        commit = source_sha()
        container = docker_id()
        pid = grafana_pid()
        start = process_starttime(pid)
        relative = process_cgroup(pid, container)
        cgfd, cgpath = pin_cgroup(relative)
        try:
            def intact() -> None:
                ensure_identity(container, pid, start, relative, cgfd, cgpath)

            intact()
            first = tick()
            observed: list[dict] = []
            for index in range(samples):
                if index:
                    pause(max(0., first + index * interval - tick()))
                intact()
                elapsed = round((tick() - first) * 1000) if index else 0
                if elapsed > 2400000:
                    reject()
                item = reading(cgfd, wall(), elapsed)
                intact()
                observed.append(item)
            intact()
            if source_sha() != commit:
                reject()
            report = {
                "schema": SCHEMA, "collector_version": VERSION,
                "source_commit": commit, "synthetic": TEST_MODE,
                "identity_assertion": "collector_checked_in_process",
                "identity_scope": "single_invocation", "interval_seconds": interval,
                "observations": observed, "event_deltas": event_deltas(observed),
            }
            check_report(report)
            publish(target, parentfd, report, intact)
        finally:
            os.close(cgfd)
    finally:
        os.close(parentfd)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Owner-gated bounded Grafana capture")
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--interval-seconds", type=int, default=15)
    args = parser.parse_args()
    try:
        collect(args.output, args.samples, args.interval_seconds)
    except (CaptureError, EvidenceError, OSError, ValueError,
            UnicodeError, subprocess.SubprocessError, AttributeError):
        print("Grafana continuity capture: FAIL (sanitized)", file=sys.stderr)
        raise SystemExit(1)
    print("Grafana continuity capture: PASS (bundle sealed; offline verifier PASS)")
    print("Collection is not a proof of host-wide pressure or live service health.")


if __name__ == "__main__":
    main()
