#!/usr/bin/env python3
"""First-install-only, exact-source Coloring Pages sitemap operator installer.

This file is source only until an exact owner LIVE gate authorizes execution.
No host changes are made by the read-only --check mode.
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
from dataclasses import dataclass

SOURCE_ROOT = Path("/home/andris/RPi5_main")
OWNER = "andris"
OPERATOR_REL = "ops/bin/coloring-pages-sitemap-publish"
GENERATOR_REL = "ops/vendor/coloring-pages-sitemap"
EXPECTED_BLOBS = {
    OPERATOR_REL: "0da51ef361f9ce815ebde3e4cc6cae19a2c2ffe8",
    GENERATOR_REL: "5644c8fd366c0c57f6339fddd163c5091ea134c5",
}
SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_SOURCE_BYTES = 100_000
GIT = "/usr/bin/git"
RUNUSER = "/usr/sbin/runuser"
ENV = "/usr/bin/env"


class InstallerError(RuntimeError):
    """Fail closed, without cleanup or rollback."""


@dataclass(frozen=True)
class Destinations:
    bin_parent: Path
    share_parent: Path

    @property
    def vendor_dir(self) -> Path:
        return self.share_parent / "coloring-pages"

    @property
    def operator(self) -> Path:
        return self.bin_parent / "coloring-pages-sitemap-publish"

    @property
    def generator(self) -> Path:
        return self.vendor_dir / "coloring-pages-sitemap"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def require_directory(path: Path, uid: int, gid: int, mode: int):
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise InstallerError("required parent directory missing") from exc
    if (not stat.S_ISDIR(info.st_mode) or path.is_symlink()
        or info.st_uid != uid or info.st_gid != gid
        or stat.S_IMODE(info.st_mode) != mode):
        raise InstallerError("parent directory identity invalid")
    return info


def require_absent(path: Path):
    if os.path.lexists(path):
        raise InstallerError("install target already exists; first-install-only")


def fetch_owner_git(*arguments: str) -> bytes:
    # Git is executed without root privileges or inherited environment.
    cmd = [
        RUNUSER, "-u", OWNER, "--", ENV, "-i",
        "HOME=/home/andris", "PATH=/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null",
        GIT, "-c", "core.hooksPath=/dev/null",
        "-C", str(SOURCE_ROOT), *arguments,
    ]
    try:
        done = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallerError("source git lookup failed") from exc
    if done.returncode or len(done.stdout) > MAX_SOURCE_BYTES:
        raise InstallerError("trusted source git lookup rejected")
    return done.stdout


def source_snapshot(expected_sha: str, *, owner_uid: int, owner_gid: int):
    if not SHA.fullmatch(expected_sha):
        raise InstallerError("source SHA must be exact lowercase 40-hex")
    require_directory(SOURCE_ROOT, owner_uid, owner_gid, 0o755)
    require_directory(SOURCE_ROOT / ".git", owner_uid, owner_gid, 0o755)

    def assert_checkout():
        head = fetch_owner_git("rev-parse", "HEAD").decode("ascii").strip()
        branch = fetch_owner_git("branch", "--show-current").decode("utf-8").strip()
        dirty = fetch_owner_git("status", "--porcelain=v1", "--untracked-files=all")
        if head != expected_sha or branch != "main" or dirty:
            raise InstallerError("checkout revision/branch/clean-state mismatch")

    assert_checkout()
    output = {}
    for path, desired_blob in EXPECTED_BLOBS.items():
        entry = fetch_owner_git("ls-tree", "HEAD", "--", path).decode("ascii").strip()
        if entry != "100644 blob " + desired_blob + "\t" + path:
            raise InstallerError("tracked source blob/mode mismatch")
        data = fetch_owner_git("show", "HEAD:" + path)
        if not data or git_blob(data) != desired_blob:
            raise InstallerError("source bytes do not match pinned Git blob")
        output[path] = data
    assert_checkout()
    return output


def preflight(paths: Destinations, *, root_uid: int, root_gid: int,
              sources: dict[str, bytes]):
    require_directory(paths.bin_parent, root_uid, root_gid, 0o755)
    require_directory(paths.share_parent, root_uid, root_gid, 0o755)
    # No modification of any existing object, including symlink or empty directory.
    for path in (paths.vendor_dir, paths.generator, paths.operator):
        require_absent(path)
    for name, blob in EXPECTED_BLOBS.items():
        if name not in sources or git_blob(sources[name]) != blob:
            raise InstallerError("source snapshot does not match pinned blob")


def fsync_directory(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def secure_create(path: Path, content: bytes, mode: int, *,
                  root_uid: int, root_gid: int):
    require_absent(path)
    fd = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        os.fchown(fd, root_uid, root_gid)
        sent = 0
        while sent < len(content):
            length = os.write(fd, content[sent:])
            if length <= 0:
                raise InstallerError("installed file write failed")
            sent += length
        os.fchmod(fd, mode)
        os.fsync(fd)
        st = os.fstat(fd)
    finally:
        os.close(fd)
    verified = path.lstat()
    if (not stat.S_ISREG(verified.st_mode) or path.is_symlink()
        or (verified.st_dev, verified.st_ino) != (st.st_dev, st.st_ino)
        or verified.st_uid != root_uid or verified.st_gid != root_gid
        or stat.S_IMODE(verified.st_mode) != mode):
        raise InstallerError("installed file identity drift")
    if git_blob(path.read_bytes()) != git_blob(content):
        raise InstallerError("installed bytes mismatch")
    fsync_directory(path.parent)


def install(paths: Destinations, *, root_uid: int, root_gid: int,
            sources: dict[str, bytes]):
    preflight(paths, root_uid=root_uid, root_gid=root_gid, sources=sources)
    # First LIVE mutation. No cleanup, retry or rollback is permitted on error.
    os.mkdir(paths.vendor_dir, 0o700)
    # mkdir mode is reduced by the caller's umask. Set the mode on the
    # newly-created inode (never on an existing directory).
    directory_fd = os.open(
        paths.vendor_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        os.fchown(directory_fd, root_uid, root_gid)
        os.fchmod(directory_fd, 0o755)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    require_directory(paths.vendor_dir, root_uid, root_gid, 0o755)
    fsync_directory(paths.share_parent)
    secure_create(paths.generator, sources[GENERATOR_REL], 0o444,
                  root_uid=root_uid, root_gid=root_gid)
    # Expose executable only after the pinned generator is fully materialized.
    secure_create(paths.operator, sources[OPERATOR_REL], 0o755,
                  root_uid=root_uid, root_gid=root_gid)
    return {"result": "INSTALL_PASS", "mutation_started": True,
            "operator_blob": EXPECTED_BLOBS[OPERATOR_REL],
            "generator_blob": EXPECTED_BLOBS[GENERATOR_REL]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-rpi5-main-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if os.geteuid() != 0:
            raise InstallerError("installer requires root identity")
        root = pwd.getpwnam("root")
        owner = pwd.getpwnam(OWNER)
        owner_group = grp.getgrnam(OWNER)
        if owner.pw_gid != owner_group.gr_gid:
            raise InstallerError("source owner identity mismatch")
        if not Path(GIT).is_file() or not Path(RUNUSER).is_file():
            raise InstallerError("required trusted execution tool unavailable")
        sources = source_snapshot(
            args.expected_rpi5_main_sha, owner_uid=owner.pw_uid,
            owner_gid=owner_group.gr_gid,
        )
        paths = Destinations(Path("/usr/local/bin"), Path("/usr/local/share"))
        preflight(paths, root_uid=root.pw_uid, root_gid=root.pw_gid, sources=sources)
        if args.check:
            output = {
                "result": "CHECK_PASS", "mutation_started": False,
                "source_sha": args.expected_rpi5_main_sha,
                "operator_blob": EXPECTED_BLOBS[OPERATOR_REL],
                "generator_blob": EXPECTED_BLOBS[GENERATOR_REL],
                "targets": "absent",
            }
        else:
            # Refresh source before the first mutation and revalidate targets.
            sources = source_snapshot(
                args.expected_rpi5_main_sha, owner_uid=owner.pw_uid,
                owner_gid=owner_group.gr_gid,
            )
            output = install(paths, root_uid=root.pw_uid,
                             root_gid=root.pw_gid, sources=sources)
            output["source_sha"] = args.expected_rpi5_main_sha
        print("COLORING_SITEMAP_INSTALL " + json.dumps(output, sort_keys=True))
        return 0
    except (InstallerError, OSError, UnicodeError, ValueError) as exc:
        print("COLORING_SITEMAP_INSTALL=STOP error_class=" + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
