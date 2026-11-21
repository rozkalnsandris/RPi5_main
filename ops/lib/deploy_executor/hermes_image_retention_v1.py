#!/usr/bin/env python3
"""Fixed-target, fail-closed Hermes Deals Docker image retention.

Source-only until separately authorized, reviewed installation/activation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import re
import socket
import stat
import subprocess
import sys
from urllib.request import urlopen

IMAGE = "ghcr.io/rozkalnsandris/hermes-deals"
HOST = "rpi5"
RETENTION = timedelta(days=14)
MAX_REMOVE = 32
HEALTH_URL = "http://127.0.0.1:9128/api/health"
LOCK_PATH = Path("/run/lock/rpi5-maintenance-exclusive.lock")
STATE_DIR = Path("/var/lib/rozkalns-hermes-image-retention")
STATE_PATH = STATE_DIR / "state.json"
PINNED = frozenset({
    "sha256:03c16c206ab28711a0ae9c34f30321570340a07d430e332166945dc640e94243",
    "sha256:69d865fc8becf18395ed7bb38d4a62ff6f0b057033bc3bd5747858f7c410d55c",
})
ID_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
REV_RE = re.compile(r"[0-9a-f]{40}\Z")
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) (?:CET|CEST)\Z")


class Stop(RuntimeError):
    pass


def require(test: bool, reason: str) -> None:
    if not test:
        raise Stop(reason)


def command(args: list[str], timeout: int = 45) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    require(result.returncode == 0, "command_failed:" + args[0] + ":" + args[1])
    return result.stdout


def image_set() -> set[str]:
    raw = command(["docker", "image", "ls", "-aq", "--no-trunc"], 50)
    ids = set(raw.split())
    require(all(ID_RE.fullmatch(item) for item in ids), "invalid_image_id_list")
    return ids


def container_state() -> tuple[set[str], set[str], set[str]]:
    ids = set(command(["docker", "ps", "-aq"], 30).split())
    running = set(command(["docker", "ps", "-q"], 30).split())
    require(running <= ids, "running_container_not_listed")
    refs: set[str] = set()
    if ids:
        rows = command(["docker", "container", "inspect", "--format", "{{.Id}}|{{.Image}}", *sorted(ids)], 60).splitlines()
        require(len(rows) == len(ids), "container_inspect_count_drift")
        for row in rows:
            pair = row.split("|")
            require(len(pair) == 2 and pair[0] in ids and ID_RE.fullmatch(pair[1]) is not None,
                    "invalid_container_reference")
            refs.add(pair[1])
    return ids, running, refs


def volumes() -> set[str]:
    return set(command(["docker", "volume", "ls", "-q"], 30).split())


def image_info(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    # Docker's formatted output exposes only these five public-safe metadata
    # fields; do NOT inspect the full image object (which may expose Env).
    fmt = '{{.Id}}|{{json .RepoTags}}|{{json .RepoDigests}}|{{.Created}}|{{if .Config.Labels}}{{index .Config.Labels "org.opencontainers.image.revision"}}{{end}}'
    raw = command(["docker", "image", "inspect", "--format", fmt, *ids], 90)
    lines = raw.splitlines()
    require(len(lines) == len(ids), "image_inspect_count_drift")
    mapping = {}
    for line in lines:
        fields = line.split("|", 4)
        require(len(fields) == 5 and ID_RE.fullmatch(fields[0]) is not None,
                "image_inspect_malformed")
        ident, tags, digests, created, revision = fields
        mapping[ident] = {
            "Id": ident, "RepoTags": json.loads(tags),
            "RepoDigests": json.loads(digests), "Created": created,
            "Revision": revision,
        }
    require(set(mapping) == set(ids), "image_inspect_id_drift")
    return mapping


def candidate_for(obj: dict, referenced: set[str], now: datetime) -> bool:
    ident = obj.get("Id")
    if not isinstance(ident, str) or ID_RE.fullmatch(ident) is None:
        return False
    if ident in PINNED or ident in referenced:
        return False
    exact = IMAGE + "@" + ident
    if set(obj.get("RepoTags") or ()) != {exact}:
        return False
    if set(obj.get("RepoDigests") or ()) != {exact}:
        return False
    if not REV_RE.fullmatch(str(obj.get("Revision", ""))):
        return False
    try:
        created = datetime.fromisoformat(obj["Created"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        return False
    if created.tzinfo is None or created > now:
        return False
    return now - created >= RETENTION


def select(images: dict[str, dict], referenced: set[str], now: datetime) -> list[str]:
    eligible = [ident for ident, obj in images.items() if candidate_for(obj, referenced, now)]
    eligible.sort(key=lambda ident: (images[ident]["Created"], ident))
    return eligible[:MAX_REMOVE]


def inspect_pins() -> None:
    mapping = image_info(sorted(PINNED))
    require(set(mapping) == PINNED, "protected_image_missing")


def health() -> None:
    with urlopen(HEALTH_URL, timeout=5) as reply:
        require(reply.status == 200, "hermes_health_failed")


def update_success_today(now: datetime) -> None:
    local = now.astimezone(ZoneInfo("Europe/Berlin"))
    require(local.weekday() == 6 and 4 <= local.hour <= 5,
            "outside_sunday_window")
    text = command(["systemctl", "show", "rpi5-update.service", "-p", "Result", "-p",
                    "ExecMainStatus", "-p", "ExecMainExitTimestamp"], 15)
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    require(fields.get("Result") == "success" and fields.get("ExecMainStatus") == "0",
            "weekly_update_not_successful")
    match = DATE_RE.search(fields.get("ExecMainExitTimestamp", ""))
    require(match is not None, "weekly_update_timestamp_unavailable")
    date, clock = match.groups()
    require(date == local.date().isoformat() and "02:20:00" <= clock <= local.strftime("%H:%M:%S"),
            "weekly_update_not_current")


def inspect_state() -> None:
    root = STATE_DIR.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == 0 and stat.S_IMODE(root.st_mode) == 0o700,
            "unsafe_state_directory")
    if STATE_PATH.is_symlink():
        raise Stop("state_symlink")
    if STATE_PATH.exists():
        info = STATE_PATH.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
                "unsafe_state_file")
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        require(state.get("state") == "DONE" and state.get("schema") == 1,
                "previous_attempt_blocked")


def write_state(status: str, manifest: str) -> None:
    payload = json.dumps({"schema": 1, "state": status, "manifest_sha256": manifest}, sort_keys=True) + "\n"
    tmp = STATE_DIR / (".state." + str(os.getpid()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, STATE_PATH)
        directory_fd = os.open(STATE_DIR, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def run(apply: bool) -> None:
    require(socket.gethostname() == HOST and os.geteuid() == 0, "host_or_user_mismatch")
    lock = LOCK_PATH.lstat()
    require(stat.S_ISREG(lock.st_mode) and lock.st_uid == 0 and lock.st_gid == 0 and
            stat.S_IMODE(lock.st_mode) == 0o600, "unsafe_shared_lock")
    lock_fd = os.open(LOCK_PATH, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(lock_fd, "rb+") as fd:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Stop("maintenance_lock_busy") from exc
        now = datetime.now(timezone.utc)
        if apply:
            update_success_today(now)
            inspect_state()
        command(["docker", "info"], 30)
        health()
        all_before = image_set()
        containers_before = container_state()
        volume_before = volumes()
        inspect_pins()
        listing = command(["docker", "image", "ls", "--all", "--no-trunc", "--format", "{{json .}}"], 55)
        suspected: set[str] = set()
        for row in listing.splitlines():
            obj = json.loads(row)
            if obj.get("Repository") == "<none>" and obj.get("Tag") == "<none>":
                ident = obj.get("ID")
                require(isinstance(ident, str) and ID_RE.fullmatch(ident) is not None,
                        "malformed_image_listing")
                suspected.add(ident)
        infos = image_info(sorted(suspected))
        require(set(infos) <= all_before, "listed_image_disappeared")
        chosen = select(infos, containers_before[2], now)
        sha = hashlib.sha256(",".join(chosen).encode("ascii")).hexdigest()
        print(f"PREFLIGHT=PASS count={len(chosen)} manifest_sha256={sha} mode={'apply' if apply else 'check'}", flush=True)
        if not apply or not chosen:
            return
        # Persistent BLOCKED marker is written before the first Docker mutation;
        # a crash/timeout/error leaves later unattended attempts disabled.
        write_state("BLOCKED", sha)
        for index, ident in enumerate(chosen, 1):
            require(container_state() == containers_before, "container_state_drift")
            current = image_info([ident])[ident]
            require(candidate_for(current, containers_before[2], now), "candidate_drift")
            ref = IMAGE + "@" + ident
            command(["docker", "image", "rm", "--no-prune", ref], 120)
            require(ident not in image_set(), "target_remains")
            print(f"REMOVED={index}/{len(chosen)} id={ident}", flush=True)
        require(image_set() == all_before - set(chosen), "non_target_image_change")
        require(container_state() == containers_before and volumes() == volume_before,
                "containers_or_volumes_changed")
        inspect_pins()
        health()
        write_state("DONE", sha)
        print(f"DONE=PASS removed={len(chosen)}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    args = parser.add_mutually_exclusive_group(required=True)
    args.add_argument("--check", action="store_true")
    args.add_argument("--apply", action="store_true")
    options = parser.parse_args()
    try:
        run(apply=options.apply)
    except (Stop, OSError, ValueError, KeyError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        # No retries, rollback, service restart, cache/volume deletion.
        print("STOP=" + (str(exc) if isinstance(exc, Stop) else type(exc).__name__), file=sys.stderr)
        return 75
    return 0


if __name__ == "__main__":
    sys.exit(main())
