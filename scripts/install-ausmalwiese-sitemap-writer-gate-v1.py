#!/usr/bin/env python3
"""First-install-only Ausmalwiese sitemap writer gate installer; SOURCE ONLY.

No host change occurs in --check mode. --apply requires a separate exact LIVE
owner authorization and never overwrites, repairs, retries, cleans up or rolls
back an existing/partial target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import grp
import re
import stat
import subprocess
import sys

OWNER = "andris"
OWNER_HOME = Path("/home/andris")
SOURCE_ROOT = OWNER_HOME / "RPi5_main"
SOURCE_REL = "ops/bin/ausmalwiese-sitemap-writer-gate"
SOURCE_BLOB = "f189665fa7fbbe18f0b2ef748a7d6f588956fe91"
SOURCE_MODE = "100755"
DESTINATION = Path("/usr/local/bin/ausmalwiese-sitemap-writer-gate")
GIT = "/usr/bin/git"
RUNUSER = "/usr/sbin/runuser"
ENV = "/usr/bin/env"
SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_BYTES = 100_000


class Stop(RuntimeError):
    """Fail closed without retry, cleanup, repair or rollback."""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def require_directory(path: Path, uid: int, gid: int, mode: int) -> None:
    try:
        entry = path.lstat()
    except FileNotFoundError as exc:
        raise Stop("required directory absent") from exc
    if (not stat.S_ISDIR(entry.st_mode) or path.is_symlink()
            or entry.st_uid != uid or entry.st_gid != gid
            or stat.S_IMODE(entry.st_mode) != mode):
        raise Stop("directory identity mismatch")


def require_absent(path: Path) -> None:
    if os.path.lexists(path):
        raise Stop("destination exists; no overwrite or repair")


def owner_git(*args: str) -> bytes:
    argv = [
        RUNUSER, "-u", OWNER, "--", ENV, "-i",
        "HOME=" + str(OWNER_HOME), "PATH=/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null",
        "GIT_OPTIONAL_LOCKS=0",
        GIT, "-c", "core.hooksPath=/dev/null",
        "-C", str(SOURCE_ROOT), *args,
    ]
    try:
        proc = subprocess.run(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stop("unprivileged Git read unavailable") from exc
    if proc.returncode or len(proc.stdout) > MAX_BYTES:
        raise Stop("Git read rejected")
    return proc.stdout


def trusted_source(expected_main: str, owner_uid: int, owner_gid: int) -> bytes:
    if not SHA.fullmatch(expected_main):
        raise Stop("expected full main SHA required")
    require_directory(Path("/home"), 0, 0, 0o755)
    require_directory(OWNER_HOME, owner_uid, owner_gid, 0o700)
    require_directory(SOURCE_ROOT, owner_uid, owner_gid, 0o755)
    require_directory(SOURCE_ROOT / ".git", owner_uid, owner_gid, 0o755)

    def stable_checkout() -> None:
        head = owner_git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
        branch = owner_git("branch", "--show-current").decode("ascii").strip()
        changes = owner_git("status", "--porcelain=v1", "--untracked-files=all")
        if head != expected_main or branch != "main" or changes:
            raise Stop("checkout SHA/branch/cleanliness mismatch")

    stable_checkout()
    entry = owner_git("ls-tree", "HEAD", "--", SOURCE_REL).decode("ascii").strip()
    if entry != f"{SOURCE_MODE} blob {SOURCE_BLOB}\t{SOURCE_REL}":
        raise Stop("source tree blob or executable mode mismatch")
    data = owner_git("show", "HEAD:" + SOURCE_REL)
    if not data or len(data) > MAX_BYTES or git_blob(data) != SOURCE_BLOB:
        raise Stop("trusted source byte identity mismatch")
    stable_checkout()
    return data


def preflight(dest: Path, source: bytes, root_uid: int, root_gid: int) -> None:
    require_directory(dest.parent.parent.parent, root_uid, root_gid, 0o755)
    require_directory(dest.parent.parent, root_uid, root_gid, 0o755)
    require_directory(dest.parent, root_uid, root_gid, 0o755)
    require_absent(dest)
    if not source or len(source) > MAX_BYTES or git_blob(source) != SOURCE_BLOB:
        raise Stop("trusted source bytes changed")


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def install_once(dest: Path, source: bytes, root_uid: int, root_gid: int) -> None:
    preflight(dest, source, root_uid, root_gid)
    # First LIVE mutation. Any later failure is STOP with partial state preserved.
    fd = os.open(
        dest,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        os.fchown(fd, root_uid, root_gid)
        written = 0
        while written < len(source):
            count = os.write(fd, source[written:])
            if count <= 0:
                raise Stop("write incomplete")
            written += count
        os.fsync(fd)
        os.fchmod(fd, 0o755)
        os.fsync(fd)
        created = os.fstat(fd)
    finally:
        os.close(fd)

    current = dest.lstat()
    if (not stat.S_ISREG(current.st_mode) or dest.is_symlink()
            or (current.st_dev, current.st_ino) != (created.st_dev, created.st_ino)
            or (current.st_uid, current.st_gid) != (root_uid, root_gid)
            or stat.S_IMODE(current.st_mode) != 0o755):
        raise Stop("installed operator inode/owner/mode mismatch")

    read_fd = os.open(dest, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(read_fd)
        if (opened.st_dev, opened.st_ino) != (created.st_dev, created.st_ino):
            raise Stop("installed operator inode drift")
        with os.fdopen(read_fd, "rb", closefd=False) as handle:
            installed = handle.read(len(source) + 1)
    finally:
        os.close(read_fd)
    if installed != source or git_blob(installed) != SOURCE_BLOB:
        raise Stop("installed bytes mismatch")
    fsync_dir(dest.parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-rpi5-main-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if os.getuid() != 0 or os.geteuid() != 0:
            raise Stop("root identity required")
        root = pwd.getpwnam("root")
        owner = pwd.getpwnam(OWNER)
        owner_group = grp.getgrnam(OWNER)
        if root.pw_uid != 0 or root.pw_gid != 0 or owner.pw_uid == 0:
            raise Stop("user identity mismatch")
        if owner.pw_dir != str(OWNER_HOME) or owner.pw_gid != owner_group.gr_gid:
            raise Stop("source owner mismatch")
        for tool in (GIT, RUNUSER, ENV):
            if not Path(tool).is_file():
                raise Stop("trusted tool missing")

        source = trusted_source(
            args.expected_rpi5_main_sha, owner.pw_uid, owner_group.gr_gid
        )
        preflight(DESTINATION, source, root.pw_uid, root.pw_gid)
        if args.apply:
            source = trusted_source(
                args.expected_rpi5_main_sha, owner.pw_uid, owner_group.gr_gid
            )
            install_once(DESTINATION, source, root.pw_uid, root.pw_gid)

        print("AUSMALWIESE_WRITER_GATE_INSTALL=" + json.dumps({
            "result": "INSTALL_PASS" if args.apply else "CHECK_PASS",
            "mutation_started": bool(args.apply),
            "main": args.expected_rpi5_main_sha,
            "operator_git_blob": SOURCE_BLOB,
            "installed": bool(args.apply),
        }, sort_keys=True))
        return 0
    except (Stop, OSError, ValueError, UnicodeError) as exc:
        print(
            "AUSMALWIESE_WRITER_GATE_INSTALL=STOP error_class=" + type(exc).__name__,
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
