#!/usr/bin/env python3
"""V08 bounded, sanitized, read-only memory-pressure diagnostic collector."""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

from memory_pressure_core import (
    COLLECTOR_VERSION,
    MEMINFO_KEYS,
    SCHEMA,
    VMSTAT_KEYS,
    build_report,
    canonical_json,
    render_markdown,
)

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
TEST_MODE = os.environ.get("MEMORY_DIAG_TEST_MODE") == "1"
TIMEOUT_SECONDS = int(os.environ.get("MEMORY_DIAG_TIMEOUT_SECONDS", "15"))
MAX_SECTION_BYTES = int(os.environ.get("MEMORY_DIAG_MAX_SECTION_BYTES", "262144"))
SAMPLE_SECONDS = int(os.environ.get("MEMORY_DIAG_SAMPLE_SECONDS", "0" if TEST_MODE else "5"))
PROC_ROOT = pathlib.Path(os.environ.get("MEMORY_DIAG_PROC_ROOT", "/proc"))

ASSIGNMENT_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|credential|cookie|authorization|private[_-]?key)[A-Za-z0-9_-]*\s*[:=]\s*([^\s;,]+)"
)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Za-z ]*PRIVATE KEY-----.*?-----END [A-Za-z ]*PRIVATE KEY-----", re.S)
TOKEN_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"AKIA[0-9A-Z]+"),
)
AUTH_RE = re.compile(r"(?i)\b(Bearer|Basic)\s+\S+")
URL_USERINFO_RE = re.compile(r"https?://[^/@\s]+:[^/@\s]+@")
MAC_RE = re.compile(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")
IPV4_RE = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
LONG_HEX_RE = re.compile(r"(?i)\b(?=[0-9a-f]{12,64}\b)(?=[0-9a-f]*[a-f])[0-9a-f]{12,64}\b")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$")


def die(message: str, code: int = 1) -> None:
    print(f"collect-memory-pressure-diagnostic: {message}", file=sys.stderr)
    raise SystemExit(code)


def utc_now() -> str:
    if TEST_MODE and os.environ.get("MEMORY_DIAG_FIXED_UTC"):
        return os.environ["MEMORY_DIAG_FIXED_UTC"]
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def effective_uid() -> int:
    if TEST_MODE and os.environ.get("MEMORY_DIAG_TEST_UID"):
        return int(os.environ["MEMORY_DIAG_TEST_UID"])
    return os.geteuid()


def git_commit() -> str:
    if TEST_MODE and os.environ.get("MEMORY_DIAG_TEST_COMMIT"):
        return os.environ["MEMORY_DIAG_TEST_COMMIT"]
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return "unavailable"


def ensure_no_symlink_components(path: pathlib.Path) -> None:
    current = pathlib.Path(path.anchor or "/")
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current = current / part
        if current.is_symlink():
            die("refusing a path containing a symlink")


def safe_output_base(value: str) -> pathlib.Path:
    requested = pathlib.Path(value)
    if not requested.is_absolute():
        requested = pathlib.Path.cwd() / requested
    ensure_no_symlink_components(requested)
    resolved = requested.resolve(strict=False)
    allowed = False
    for name in ("evidence", "exports"):
        try:
            resolved.relative_to(REPO / name)
            allowed = True
        except ValueError:
            pass
    if not allowed:
        die("output directory must resolve below this repository evidence/ or exports/ tree")
    if resolved.exists() and not resolved.is_dir():
        die("output path is not a directory")
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    ensure_no_symlink_components(resolved)
    return resolved


def sanitize_text(value: str) -> str:
    value = PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY BLOCK]", value)
    value = ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
    for pattern in TOKEN_PATTERNS:
        value = pattern.sub("[REDACTED_TOKEN]", value)
    value = AUTH_RE.sub(lambda m: f"{m.group(1)} [REDACTED]", value)
    value = URL_USERINFO_RE.sub("https://[REDACTED]@", value)
    value = MAC_RE.sub("[REDACTED_MAC]", value)
    value = IPV4_RE.sub("[REDACTED_IP]", value)
    value = LONG_HEX_RE.sub("[REDACTED_HEX_ID]", value)
    return value


def cap_bytes(value: str) -> str:
    encoded = value.encode("utf-8", errors="replace")[:MAX_SECTION_BYTES]
    return encoded.decode("utf-8", errors="ignore")


def command_available(name: str) -> bool:
    missing = {item for item in os.environ.get("MEMORY_DIAG_TEST_MISSING_COMMANDS", "").split(",") if item}
    return name not in missing and shutil.which(name) is not None


def run_command(args: list[str]) -> tuple[bool, int, str]:
    if not command_available(args[0]):
        return False, 127, f"command unavailable: {args[0]}\n"
    try:
        proc = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return True, 124, "command timed out\n"
    if proc.returncode != 0:
        return True, proc.returncode, f"command failed: exit {proc.returncode}\n"
    return True, 0, cap_bytes(sanitize_text(proc.stdout))


def phase_path(relative: str, phase: str) -> pathlib.Path:
    base = PROC_ROOT / relative
    if TEST_MODE:
        candidate = pathlib.Path(str(base) + f".{phase}")
        if candidate.exists():
            return candidate
    return base


def read_proc(relative: str, phase: str = "start") -> tuple[bool, int, str]:
    path = phase_path(relative, phase)
    try:
        if path.is_symlink() or not path.is_file():
            return False, 127, f"proc entry unavailable: {relative}\n"
        return True, 0, cap_bytes(sanitize_text(path.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False, 1, f"proc entry unreadable: {relative}\n"


def parse_meminfo(raw: str) -> str:
    found: dict[str, int] = {}
    for line in raw.splitlines():
        match = re.fullmatch(r"([A-Za-z0-9_()]+):\s+([0-9]+)\s+kB", line)
        if match and match.group(1) in MEMINFO_KEYS:
            found[match.group(1)] = int(match.group(2))
    return "key\tvalue_kib\n" + "".join(f"{key}\t{found[key]}\n" for key in MEMINFO_KEYS if key in found)


def parse_vmstat(raw: str) -> str:
    found: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in VMSTAT_KEYS and parts[1].isdigit():
            found[parts[0]] = int(parts[1])
    return "key\tvalue\n" + "".join(f"{key}\t{found[key]}\n" for key in VMSTAT_KEYS if key in found)


def parse_swap(raw: str) -> str:
    rows: list[str] = []
    for index, line in enumerate(raw.splitlines()):
        if index == 0:
            continue
        parts = line.split()
        if len(parts) >= 5 and all(re.fullmatch(r"-?[0-9]+", value) for value in parts[2:5]):
            swap_type = re.sub(r"[^A-Za-z0-9_.:@+-]", "_", parts[1]) or "unknown"
            rows.append(f"{swap_type}\t{parts[2]}\t{parts[3]}\t{parts[4]}")
    return "type\tsize_kib\tused_kib\tpriority\n" + "\n".join(rows) + ("\n" if rows else "")


def parse_processes(raw: str) -> str:
    aggregate: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[-1].isdigit():
            continue
        name = re.sub(r"[^A-Za-z0-9_.:@+-]", "_", "_".join(parts[:-1]))[:128]
        if not SAFE_NAME.fullmatch(name):
            continue
        aggregate[name] = aggregate.get(name, 0) + int(parts[-1])
    rows = sorted(aggregate.items(), key=lambda item: (-item[1], item[0]))[:25]
    return "name\trss_kib\n" + "".join(f"{name}\t{rss}\n" for name, rss in rows)


def parse_containers(raw: str) -> str:
    rows: list[tuple[str, str, str, str, str]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        name, usage_pair, percent, pids = parts
        if " / " not in usage_pair:
            continue
        usage, limit = usage_pair.split(" / ", 1)
        if SAFE_NAME.fullmatch(name) and pids.isdigit():
            rows.append((name, usage.replace(" ", ""), limit.replace(" ", ""), percent.replace(" ", ""), pids))
    rows.sort(key=lambda row: row[0])
    return "name\tusage\tlimit\tpercent\tpids\n" + "".join("\t".join(row) + "\n" for row in rows)


def parse_zram(raw: str) -> str:
    rows: list[tuple[str, ...]] = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 6 or not all(value.isdigit() for value in parts[1:]):
            continue
        name = pathlib.Path(parts[0]).name
        if SAFE_NAME.fullmatch(name):
            rows.append((name, *parts[1:]))
    rows.sort(key=lambda row: row[0])
    return "name\tdisksize_bytes\tdata_bytes\tcompressed_bytes\ttotal_bytes\tstreams\n" + "".join("\t".join(row) + "\n" for row in rows)


def parse_kernel_events(raw: str) -> str:
    keywords = ("out of memory", "oom", "memory cgroup", "killed process")
    rows = [line for line in raw.splitlines() if any(word in line.lower() for word in keywords)]
    return "\n".join(rows[-100:]) + ("\n" if rows else "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if effective_uid() == 0:
        die("refusing to run as root")
    if TIMEOUT_SECONDS < 1 or MAX_SECTION_BYTES < 1024:
        die("invalid collector limits")
    if SAMPLE_SECONDS < 0 or SAMPLE_SECONDS > 30 or (SAMPLE_SECONDS == 0 and not TEST_MODE):
        die("invalid sample window")
    if not TEST_MODE and PROC_ROOT != pathlib.Path("/proc"):
        die("custom proc root is test-only")

    output_base = safe_output_base(args.output)
    os.umask(0o077)
    timestamp = utc_now()
    result = pathlib.Path(tempfile.mkdtemp(prefix=f"v08-{timestamp.replace(':', '-')}-", dir=output_base))
    sections = result / "sections"
    sections.mkdir(mode=0o700)
    statuses: list[tuple[str, str, bool, int, int]] = []
    limitations = {
        "PSS, per-cgroup peak memory and per-cgroup OOM counters are not collected by this least-privilege version.",
        "Process arguments, container environments, Docker inspect data and raw DNS queries are intentionally excluded.",
        "A short sample can miss intermittent pressure; compare repeated bundles before concluding that retained swap is active pressure.",
    }

    def write_section(filename: str, category: str, available: bool, rc: int, content: str) -> None:
        safe = cap_bytes(sanitize_text(content))
        path = sections / filename
        path.write_text(safe, encoding="utf-8", newline="\n")
        os.chmod(path, 0o600)
        statuses.append((filename.rsplit(".", 1)[0], category, available, rc, path.stat().st_size))

    available, rc, raw = read_proc("meminfo", "start")
    write_section("meminfo.tsv", "host-memory", available, rc, parse_meminfo(raw) if rc == 0 else "key\tvalue_kib\n")

    psi_available, psi_start_rc, psi_start_raw = read_proc("pressure/memory", "start")
    write_section("psi_start.txt", "memory-pressure", psi_available, psi_start_rc, psi_start_raw if psi_start_rc == 0 else "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
    vm_available, vm_start_rc, vm_start_raw = read_proc("vmstat", "start")
    write_section("vmstat_start.tsv", "memory-counters", vm_available, vm_start_rc, parse_vmstat(vm_start_raw) if vm_start_rc == 0 else "key\tvalue\n")

    if SAMPLE_SECONDS:
        time.sleep(SAMPLE_SECONDS)

    psi_end_available, psi_end_rc, psi_end_raw = read_proc("pressure/memory", "end")
    write_section("psi_end.txt", "memory-pressure", psi_end_available, psi_end_rc, psi_end_raw if psi_end_rc == 0 else "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
    vm_end_available, vm_end_rc, vm_end_raw = read_proc("vmstat", "end")
    write_section("vmstat_end.tsv", "memory-counters", vm_end_available, vm_end_rc, parse_vmstat(vm_end_raw) if vm_end_rc == 0 else "key\tvalue\n")

    swap_available, swap_rc, swap_raw = read_proc("swaps", "start")
    write_section("swap.tsv", "swap", swap_available, swap_rc, parse_swap(swap_raw) if swap_rc == 0 else "type\tsize_kib\tused_kib\tpriority\n")

    z_available, z_rc, z_raw = run_command(["zramctl", "--bytes", "--raw", "--noheadings", "--output", "NAME,DISKSIZE,DATA,COMPR,TOTAL,STREAMS"])
    write_section("zram.tsv", "swap", z_available, z_rc, parse_zram(z_raw) if z_rc == 0 else "name\tdisksize_bytes\tdata_bytes\tcompressed_bytes\ttotal_bytes\tstreams\n")
    if z_rc != 0:
        limitations.add("zram device metrics were unavailable in this collection context.")

    p_available, p_rc, p_raw = run_command(["ps", "-e", "-o", "comm=,rss=", "--sort=-rss"])
    write_section("process_rss.tsv", "process-memory", p_available, p_rc, parse_processes(p_raw) if p_rc == 0 else "name\trss_kib\n")
    if p_rc != 0:
        limitations.add("Safe process-name/RSS aggregation was unavailable in this collection context.")

    d_available, d_rc, d_raw = run_command(["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}"])
    write_section("container_memory.tsv", "container-memory", d_available, d_rc, parse_containers(d_raw) if d_rc == 0 else "name\tusage\tlimit\tpercent\tpids\n")
    if d_rc != 0:
        limitations.add("Per-container current memory was unavailable; no Docker access change was attempted.")

    j_available, j_rc, j_raw = run_command(["journalctl", "-k", "-b", "--no-pager", "-o", "short-iso", "-n", "500"])
    write_section("kernel_memory_events.txt", "kernel-memory", j_available, j_rc, parse_kernel_events(j_raw) if j_rc == 0 else "")
    if j_rc != 0:
        limitations.add("Recent kernel memory-event lines were unavailable in this collection context.")

    write_section("limitations.txt", "limitations", True, 0, "\n".join(sorted(limitations)) + "\n")

    metadata = {
        "schema": SCHEMA,
        "collector_version": COLLECTOR_VERSION,
        "git_commit": git_commit(),
        "collected_at_utc": timestamp,
        "sample_seconds": SAMPLE_SECONDS,
    }
    (result / "metadata.json").write_text(canonical_json(metadata), encoding="utf-8", newline="\n")
    os.chmod(result / "metadata.json", 0o600)

    status_path = result / "section-status.tsv"
    status_path.write_text(
        "section\tcategory\tcommand_available\texit_status\tbytes\n"
        + "".join(f"{name}\t{category}\t{str(available).lower()}\t{rc}\t{size}\n" for name, category, available, rc, size in statuses),
        encoding="utf-8", newline="\n",
    )
    os.chmod(status_path, 0o600)

    report = build_report(result, metadata)
    (result / "report.json").write_text(canonical_json(report), encoding="utf-8", newline="\n")
    (result / "report.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
    os.chmod(result / "report.json", 0o600)
    os.chmod(result / "report.md", 0o600)

    inventory = sorted(str(path.relative_to(result)) for path in result.rglob("*") if path.is_file())
    (result / "file-inventory.txt").write_text("\n".join(inventory) + "\n", encoding="utf-8", newline="\n")
    os.chmod(result / "file-inventory.txt", 0o600)

    manifest_files = sorted(str(path.relative_to(result)) for path in result.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    sums = []
    for name in manifest_files:
        digest = hashlib.sha256((result / name).read_bytes()).hexdigest()
        sums.append(f"{digest}  {name}")
    (result / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    os.chmod(result / "SHA256SUMS", 0o600)

    print(f"Memory diagnostic result: {result}")
    print(f"Observation level: {report['observation']['level']}")


if __name__ == "__main__":
    main()
