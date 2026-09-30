#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import json
import os
import re
import signal
import stat
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA = "rpi5.browser-lifecycle.v1"
STATE_SUFFIX = ".json"
PR_SET_CHILD_SUBREAPER = 36
LABEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
BROWSER_COMMS = frozenset(
    {
        "chromium",
        "chromium-browser",
        "chrome",
        "google-chrome",
        "chrome_crashpad",
    }
)


class LifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcInfo:
    pid: int
    ppid: int
    pgrp: int
    sid: int
    start_ticks: int
    comm: str

    @property
    def identity(self) -> tuple[int, int]:
        return (self.pid, self.start_ticks)


@dataclass
class RunRecord:
    run_id: str
    label: str
    owner_pid: int
    owner_start_ticks: int
    leader_pid: int
    leader_start_ticks: int
    created_at: float
    timeout_seconds: float
    members: dict[int, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "label": self.label,
            "owner_pid": self.owner_pid,
            "owner_start_ticks": self.owner_start_ticks,
            "leader_pid": self.leader_pid,
            "leader_start_ticks": self.leader_start_ticks,
            "created_at": self.created_at,
            "timeout_seconds": self.timeout_seconds,
            "members": {str(pid): ticks for pid, ticks in sorted(self.members.items())},
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "RunRecord":
        expected = {
            "schema",
            "run_id",
            "label",
            "owner_pid",
            "owner_start_ticks",
            "leader_pid",
            "leader_start_ticks",
            "created_at",
            "timeout_seconds",
            "members",
        }
        if set(value) != expected or value.get("schema") != SCHEMA:
            raise LifecycleError("invalid state record shape")
        run_id = value["run_id"]
        label = value["label"]
        if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise LifecycleError("invalid run id")
        if not isinstance(label, str) or LABEL_RE.fullmatch(label) is None:
            raise LifecycleError("invalid label")
        ints: dict[str, int] = {}
        for key in ("owner_pid", "owner_start_ticks", "leader_pid", "leader_start_ticks"):
            raw = value[key]
            if type(raw) is not int or raw <= 0:
                raise LifecycleError(f"invalid {key}")
            ints[key] = raw
        created_at = value["created_at"]
        timeout_seconds = value["timeout_seconds"]
        if not isinstance(created_at, (int, float)) or created_at <= 0:
            raise LifecycleError("invalid created_at")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise LifecycleError("invalid timeout")
        raw_members = value["members"]
        if not isinstance(raw_members, dict):
            raise LifecycleError("invalid members")
        members: dict[int, int] = {}
        for raw_pid, raw_ticks in raw_members.items():
            if not isinstance(raw_pid, str) or not raw_pid.isdigit():
                raise LifecycleError("invalid member pid")
            pid = int(raw_pid)
            if pid <= 0 or type(raw_ticks) is not int or raw_ticks <= 0:
                raise LifecycleError("invalid member identity")
            members[pid] = raw_ticks
        return cls(
            run_id=run_id,
            label=label,
            owner_pid=ints["owner_pid"],
            owner_start_ticks=ints["owner_start_ticks"],
            leader_pid=ints["leader_pid"],
            leader_start_ticks=ints["leader_start_ticks"],
            created_at=float(created_at),
            timeout_seconds=float(timeout_seconds),
            members=members,
        )


@dataclass(frozen=True)
class OwnershipView:
    owned: dict[int, ProcInfo]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class CleanupResult:
    cleaned: bool
    remaining: int
    blockers: tuple[str, ...]


def default_state_dir() -> Path:
    return Path.home() / ".local" / "state" / "rpi5-browser-lifecycle"


def _parse_stat(text: str) -> ProcInfo:
    left = text.find("(")
    right = text.rfind(")")
    if left <= 0 or right <= left:
        raise LifecycleError("invalid proc stat")
    pid = int(text[:left].strip())
    comm = text[left + 1 : right]
    fields = text[right + 1 :].strip().split()
    if len(fields) < 20:
        raise LifecycleError("short proc stat")
    return ProcInfo(
        pid=pid,
        ppid=int(fields[1]),
        pgrp=int(fields[2]),
        sid=int(fields[3]),
        start_ticks=int(fields[19]),
        comm=comm,
    )


def read_proc_info(pid: int, proc_root: Path = Path("/proc")) -> ProcInfo | None:
    try:
        text = (proc_root / str(pid) / "stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return None
    except (PermissionError, OSError) as exc:
        raise LifecycleError(f"cannot read proc metadata for pid {pid}") from exc
    try:
        return _parse_stat(text)
    except (ValueError, LifecycleError) as exc:
        raise LifecycleError(f"cannot parse proc metadata for pid {pid}") from exc


def snapshot_processes(proc_root: Path = Path("/proc")) -> dict[int, ProcInfo]:
    out: dict[int, ProcInfo] = {}
    try:
        entries = list(proc_root.iterdir())
    except OSError as exc:
        raise LifecycleError("cannot enumerate proc metadata") from exc
    for entry in entries:
        if not entry.name.isdigit():
            continue
        info = read_proc_info(int(entry.name), proc_root=proc_root)
        if info is not None:
            out[info.pid] = info
    return out


def _identity_matches(snapshot: Mapping[int, ProcInfo], pid: int, start_ticks: int) -> bool:
    info = snapshot.get(pid)
    return info is not None and info.start_ticks == start_ticks


def collect_owned(record: RunRecord, snapshot: Mapping[int, ProcInfo]) -> OwnershipView:
    owned: dict[int, ProcInfo] = {}
    blockers: set[str] = set()

    owner = snapshot.get(record.owner_pid)
    if owner is not None and owner.start_ticks != record.owner_start_ticks:
        blockers.add("owner_pid_reuse")

    leader = snapshot.get(record.leader_pid)
    if leader is not None and leader.start_ticks != record.leader_start_ticks:
        blockers.add("leader_pid_reuse")

    for pid, start_ticks in record.members.items():
        info = snapshot.get(pid)
        if info is None:
            continue
        if info.start_ticks != start_ticks:
            blockers.add(f"member_pid_reuse:{pid}")
            continue
        owned[pid] = info

    leader_matches = leader is not None and leader.start_ticks == record.leader_start_ticks
    group_candidates = [
        info
        for info in snapshot.values()
        if info.pgrp == record.leader_pid or info.sid == record.leader_pid
    ]
    group_continuity = leader_matches or any(
        info.pgrp == record.leader_pid or info.sid == record.leader_pid
        for info in owned.values()
    )
    if group_continuity and "leader_pid_reuse" not in blockers:
        for info in group_candidates:
            owned[info.pid] = info
    elif group_candidates:
        blockers.add("unproven_group_members")

    owner_matches = owner is not None and owner.start_ticks == record.owner_start_ticks
    if owner_matches:
        parent_ids = {record.owner_pid} | set(owned)
        changed = True
        while changed:
            changed = False
            for info in snapshot.values():
                if info.pid in owned:
                    continue
                if info.ppid in parent_ids:
                    owned[info.pid] = info
                    parent_ids.add(info.pid)
                    changed = True

    owned.pop(record.owner_pid, None)
    return OwnershipView(owned=owned, blockers=tuple(sorted(blockers)))


def _state_path(state_dir: Path, run_id: str) -> Path:
    return state_dir / f"{run_id}{STATE_SUFFIX}"


def _validate_state_dir(state_dir: Path, create: bool) -> None:
    if state_dir.is_symlink():
        raise LifecycleError("state path must not be a symlink")
    if create:
        state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not state_dir.exists():
        return
    st = state_dir.lstat()
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise LifecycleError("state path is not a real directory")
    if st.st_uid != os.getuid():
        raise LifecycleError("state directory owner mismatch")
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise LifecycleError("state directory permissions are too broad")


def write_record(state_dir: Path, record: RunRecord) -> None:
    _validate_state_dir(state_dir, create=True)
    target = _state_path(state_dir, record.run_id)
    tmp = state_dir / f".{record.run_id}.{os.getpid()}.tmp"
    payload = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def remove_record(state_dir: Path, run_id: str) -> None:
    try:
        _state_path(state_dir, run_id).unlink()
    except FileNotFoundError:
        return


def load_records(state_dir: Path) -> tuple[list[RunRecord], list[str]]:
    _validate_state_dir(state_dir, create=False)
    if not state_dir.exists():
        return [], []
    records: list[RunRecord] = []
    blockers: list[str] = []
    for path in sorted(state_dir.glob(f"*{STATE_SUFFIX}")):
        try:
            st = path.lstat()
            if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                raise LifecycleError("not a regular state file")
            if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
                raise LifecycleError("unsafe state file metadata")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise LifecycleError("state record must be object")
            record = RunRecord.from_dict(value)
            if path.name != f"{record.run_id}{STATE_SUFFIX}":
                raise LifecycleError("state filename mismatch")
            records.append(record)
        except (OSError, json.JSONDecodeError, LifecycleError):
            blockers.append("invalid_state_record")
    return records, blockers


def enable_child_subreaper() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    rc = libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)
    if rc != 0:
        err = ctypes.get_errno()
        raise LifecycleError(f"cannot enable child subreaper: errno={err}")


def _signal_exact(info: ProcInfo, sig: int, proc_root: Path = Path("/proc")) -> bool:
    current = read_proc_info(info.pid, proc_root=proc_root)
    if current is None:
        return False
    if current.start_ticks != info.start_ticks:
        raise LifecycleError(f"pid identity changed before signal:{info.pid}")
    try:
        os.kill(info.pid, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise LifecycleError(f"permission denied signalling owned pid:{info.pid}") from exc


def _reap_children() -> None:
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def cleanup_record(
    state_dir: Path,
    record: RunRecord,
    *,
    term_grace_seconds: float = 3.0,
    proc_root: Path = Path("/proc"),
) -> CleanupResult:
    snapshot = snapshot_processes(proc_root)
    view = collect_owned(record, snapshot)
    if view.blockers:
        return CleanupResult(False, len(view.owned), view.blockers)

    changed = False
    for info in view.owned.values():
        if record.members.get(info.pid) != info.start_ticks:
            record.members[info.pid] = info.start_ticks
            changed = True
    if changed:
        write_record(state_dir, record)

    for info in sorted(view.owned.values(), key=lambda item: item.pid, reverse=True):
        _signal_exact(info, signal.SIGTERM, proc_root=proc_root)

    deadline = time.monotonic() + max(0.0, term_grace_seconds)
    while time.monotonic() < deadline:
        time.sleep(0.05)
        snapshot = snapshot_processes(proc_root)
        view = collect_owned(record, snapshot)
        if view.blockers:
            return CleanupResult(False, len(view.owned), view.blockers)
        for info in view.owned.values():
            if record.members.get(info.pid) != info.start_ticks:
                record.members[info.pid] = info.start_ticks
                write_record(state_dir, record)
                _signal_exact(info, signal.SIGTERM, proc_root=proc_root)
        if not view.owned:
            remove_record(state_dir, record.run_id)
            _reap_children()
            return CleanupResult(True, 0, ())

    snapshot = snapshot_processes(proc_root)
    view = collect_owned(record, snapshot)
    if view.blockers:
        return CleanupResult(False, len(view.owned), view.blockers)
    for info in sorted(view.owned.values(), key=lambda item: item.pid, reverse=True):
        _signal_exact(info, signal.SIGKILL, proc_root=proc_root)

    kill_deadline = time.monotonic() + 2.0
    while time.monotonic() < kill_deadline:
        time.sleep(0.05)
        _reap_children()
        snapshot = snapshot_processes(proc_root)
        view = collect_owned(record, snapshot)
        if view.blockers:
            return CleanupResult(False, len(view.owned), view.blockers)
        if not view.owned:
            remove_record(state_dir, record.run_id)
            return CleanupResult(True, 0, ())
    return CleanupResult(False, len(view.owned), ("owned_processes_remain",))


def read_memory_pressure(proc_root: Path = Path("/proc")) -> dict[str, float]:
    try:
        lines = (proc_root / "meminfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise LifecycleError("cannot read memory pressure metadata") from exc
    values: dict[str, int] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        token = rest.strip().split()[0]
        if token.isdigit():
            values[key] = int(token)
    if "MemAvailable" not in values:
        raise LifecycleError("MemAvailable missing")
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    swap_used_pct = 0.0 if swap_total <= 0 else ((swap_total - swap_free) / swap_total) * 100.0
    return {
        "mem_available_mib": values["MemAvailable"] / 1024.0,
        "swap_used_percent": swap_used_pct,
    }


def health_report(
    state_dir: Path,
    *,
    min_mem_available_mib: float = 512.0,
    max_swap_used_percent: float = 85.0,
    proc_root: Path = Path("/proc"),
) -> dict[str, object]:
    records, record_blockers = load_records(state_dir)
    snapshot = snapshot_processes(proc_root)

    active = 0
    stale = 0
    stale_clean = 0
    ambiguous = len(record_blockers)
    blockers: list[str] = list(record_blockers)
    owned_pids: set[int] = set()
    identity_owners: dict[tuple[int, int], str] = {}

    for record in records:
        for pid, ticks in record.members.items():
            ident = (pid, ticks)
            other = identity_owners.get(ident)
            if other is not None and other != record.run_id:
                blockers.append("duplicate_owned_identity")
                ambiguous += 1
            identity_owners[ident] = record.run_id

    for record in records:
        view = collect_owned(record, snapshot)
        owned_pids.update(view.owned)
        if view.blockers:
            ambiguous += 1
            blockers.extend(view.blockers)
            continue
        owner_matches = _identity_matches(snapshot, record.owner_pid, record.owner_start_ticks)
        if owner_matches:
            active += 1
        elif view.owned:
            stale += 1
            blockers.append("stale_owned_session")
        else:
            stale_clean += 1
            blockers.append("stale_clean_state_record")

    unrelated = sum(
        1
        for info in snapshot.values()
        if info.comm in BROWSER_COMMS and info.pid not in owned_pids
    )
    pressure = read_memory_pressure(proc_root)
    if pressure["mem_available_mib"] < min_mem_available_mib:
        blockers.append("low_mem_available")
    if pressure["swap_used_percent"] > max_swap_used_percent:
        blockers.append("high_swap_usage")

    return {
        "schema": SCHEMA,
        "status": "PASS" if not blockers else "BLOCKED",
        "owned_records": len(records),
        "active_owned_sessions": active,
        "stale_owned_sessions": stale,
        "stale_clean_state_records": stale_clean,
        "ambiguous_owned_records": ambiguous,
        "unrelated_browser_processes": unrelated,
        "mem_available_mib": round(float(pressure["mem_available_mib"]), 1),
        "swap_used_percent": round(float(pressure["swap_used_percent"]), 1),
        "blockers": sorted(set(blockers)),
        "state_content_read": True,
        "browser_profile_read": False,
        "process_environment_read": False,
        "process_cmdline_read": False,
    }


def cleanup_stale_records(
    state_dir: Path,
    *,
    min_age_seconds: float,
    term_grace_seconds: float = 3.0,
    proc_root: Path = Path("/proc"),
    now: float | None = None,
) -> dict[str, object]:
    records, blockers = load_records(state_dir)
    if blockers:
        return {
            "schema": SCHEMA,
            "status": "BLOCKED",
            "cleaned_records": 0,
            "blockers": sorted(set(blockers)),
        }
    snapshot = snapshot_processes(proc_root)
    now = time.time() if now is None else now

    identity_owners: dict[tuple[int, int], str] = {}
    for record in records:
        for pid, ticks in record.members.items():
            ident = (pid, ticks)
            if ident in identity_owners and identity_owners[ident] != record.run_id:
                return {
                    "schema": SCHEMA,
                    "status": "BLOCKED",
                    "cleaned_records": 0,
                    "blockers": ["duplicate_owned_identity"],
                }
            identity_owners[ident] = record.run_id

    eligible: list[RunRecord] = []
    skipped_active = 0
    skipped_young = 0
    for record in records:
        age = max(0.0, now - record.created_at)
        if age < min_age_seconds:
            skipped_young += 1
            continue
        if _identity_matches(snapshot, record.owner_pid, record.owner_start_ticks):
            skipped_active += 1
            continue
        view = collect_owned(record, snapshot)
        if view.blockers:
            return {
                "schema": SCHEMA,
                "status": "BLOCKED",
                "cleaned_records": 0,
                "blockers": list(view.blockers),
            }
        eligible.append(record)

    cleaned = 0
    for record in eligible:
        view = collect_owned(record, snapshot_processes(proc_root))
        if view.blockers:
            return {
                "schema": SCHEMA,
                "status": "BLOCKED",
                "cleaned_records": cleaned,
                "blockers": list(view.blockers),
            }
        if not view.owned:
            remove_record(state_dir, record.run_id)
            cleaned += 1
            continue
        result = cleanup_record(
            state_dir,
            record,
            term_grace_seconds=term_grace_seconds,
            proc_root=proc_root,
        )
        if not result.cleaned:
            return {
                "schema": SCHEMA,
                "status": "BLOCKED",
                "cleaned_records": cleaned,
                "blockers": list(result.blockers),
            }
        cleaned += 1

    return {
        "schema": SCHEMA,
        "status": "CLEAN",
        "cleaned_records": cleaned,
        "skipped_active_records": skipped_active,
        "skipped_young_records": skipped_young,
        "blockers": [],
    }


def run_guarded(
    command: Sequence[str],
    *,
    label: str,
    state_dir: Path,
    timeout_seconds: float,
    term_grace_seconds: float = 3.0,
    poll_seconds: float = 0.2,
    min_mem_available_mib: float = 512.0,
    max_swap_used_percent: float = 85.0,
) -> int:
    if not command:
        raise LifecycleError("command is required")
    if LABEL_RE.fullmatch(label) is None:
        raise LifecycleError("invalid label")
    if timeout_seconds <= 0 or poll_seconds <= 0 or term_grace_seconds < 0:
        raise LifecycleError("invalid timing value")

    preflight = health_report(
        state_dir,
        min_mem_available_mib=min_mem_available_mib,
        max_swap_used_percent=max_swap_used_percent,
    )
    if preflight["status"] != "PASS":
        raise LifecycleError(
            "browser lifecycle preflight blocked:" + ",".join(preflight["blockers"])
        )

    _validate_state_dir(state_dir, create=True)
    enable_child_subreaper()
    owner = read_proc_info(os.getpid())
    if owner is None:
        raise LifecycleError("cannot identify lifecycle owner")

    import subprocess

    child = subprocess.Popen(list(command), start_new_session=True)
    leader = read_proc_info(child.pid)
    if leader is None:
        child.wait()
        raise LifecycleError("child exited before identity capture")
    if leader.pgrp != child.pid or leader.sid != child.pid:
        child.terminate()
        child.wait()
        raise LifecycleError("child did not enter a dedicated session")

    record = RunRecord(
        run_id=uuid.uuid4().hex,
        label=label,
        owner_pid=owner.pid,
        owner_start_ticks=owner.start_ticks,
        leader_pid=leader.pid,
        leader_start_ticks=leader.start_ticks,
        created_at=time.time(),
        timeout_seconds=float(timeout_seconds),
        members={leader.pid: leader.start_ticks},
    )
    write_record(state_dir, record)

    interrupted: list[int] = []

    def on_signal(signum: int, _frame: object) -> None:
        if not interrupted:
            interrupted.append(signum)

    previous_handlers: dict[int, object] = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[sig] = signal.getsignal(sig)
        signal.signal(sig, on_signal)

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    child_code: int | None = None
    try:
        while True:
            snapshot = snapshot_processes()
            view = collect_owned(record, snapshot)
            if view.blockers:
                raise LifecycleError("ownership became ambiguous:" + ",".join(view.blockers))
            changed = False
            for info in view.owned.values():
                if record.members.get(info.pid) != info.start_ticks:
                    record.members[info.pid] = info.start_ticks
                    changed = True
            if changed:
                write_record(state_dir, record)

            child_code = child.poll()
            if child_code is not None:
                break
            if interrupted:
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(poll_seconds)

        result = cleanup_record(state_dir, record, term_grace_seconds=term_grace_seconds)
        if not result.cleaned:
            raise LifecycleError("owned cleanup blocked:" + ",".join(result.blockers))

        try:
            child.wait(timeout=0.2)
        except Exception:
            pass
        _reap_children()

        if interrupted:
            return 128 + interrupted[0]
        if timed_out:
            return 124
        return int(child_code if child_code is not None else 0)
    except BaseException:
        try:
            cleanup_record(state_dir, record, term_grace_seconds=term_grace_seconds)
        except Exception:
            pass
        raise
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
