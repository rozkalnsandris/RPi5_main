#!/usr/bin/env python3
"""Fixed-path sitemap operator upgrade; source only until an exact LIVE owner gate."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

OWNER = "andris"
OWNER_HOME = Path("/home/andris")
SOURCE_ROOT = OWNER_HOME / "RPi5_main"
SCRIPT_REL = "scripts/upgrade-coloring-pages-sitemap-publisher-v1.py"
OPERATOR = "ops/bin/coloring-pages-sitemap-publish"
GENERATOR = "ops/vendor/coloring-pages-sitemap"
OLD = {
    OPERATOR: "0da51ef361f9ce815ebde3e4cc6cae19a2c2ffe8",
    GENERATOR: "5644c8fd366c0c57f6339fddd163c5091ea134c5",
}
NEW = {
    OPERATOR: "7b0330f30e27d6fe9c5f3e4fbf81fc6473ade660",
    GENERATOR: "49c8ba34cf0a4c4ab100463df9adacc4c6e90c2c",
}
MAX_BYTES = 100_000
SHA = re.compile(r"^[0-9a-f]{40}$")


class UpgradeError(RuntimeError):
    """Stop without retry, rollback or cleanup."""


@dataclass(frozen=True)
class Paths:
    bin_dir: Path
    vendor_dir: Path
    lock: Path

    @property
    def operator(self):
        return self.bin_dir / "coloring-pages-sitemap-publish"

    @property
    def generator(self):
        return self.vendor_dir / "coloring-pages-sitemap"

    @property
    def operator_stage(self):
        return self.bin_dir / ".coloring-pages-sitemap-publish.upgrade.partial"

    @property
    def generator_stage(self):
        return self.vendor_dir / ".coloring-pages-sitemap.upgrade.partial"

    @property
    def marker(self):
        return self.vendor_dir / "post-publish-v1.enabled"


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def directory(path: Path, uid: int, gid: int, mode=0o755):
    info = path.lstat()
    if (path.is_symlink() or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != uid or info.st_gid != gid
        or stat.S_IMODE(info.st_mode) != mode):
        raise UpgradeError("unsafe directory identity")
    return info


def trusted_file(path: Path, uid: int, gid: int, mode: int) -> bytes:
    before = path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(before.st_mode)
        or before.st_uid != uid or before.st_gid != gid
        or stat.S_IMODE(before.st_mode) != mode
        or not 0 < before.st_size <= MAX_BYTES):
        raise UpgradeError("unsafe installed file identity")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size) != (
            after.st_dev, after.st_ino, after.st_size
        ):
            raise UpgradeError("file identity drift")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            content = handle.read(MAX_BYTES + 1)
        if len(content) != before.st_size:
            raise UpgradeError("installed file changed during read")
        return content
    finally:
        os.close(fd)


def no_existing_stage_or_marker(paths: Paths):
    if any(os.path.lexists(p) for p in (
        paths.marker, paths.generator_stage, paths.operator_stage
    )):
        raise UpgradeError("preexisting stage or enabled post-publish hook")


@contextmanager
def locked(path: Path, uid: int, gid: int):
    before = path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(before.st_mode)
        or before.st_uid != uid or before.st_gid != gid
        or stat.S_IMODE(before.st_mode) != 0o600):
        raise UpgradeError("unsafe shared lock identity")
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise UpgradeError("shared lock inode drift")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UpgradeError("shared lock busy") from exc
        yield
    finally:
        os.close(fd)


def preflight(paths: Paths, sources: dict[str, bytes], *,
              root_uid: int, root_gid: int, owner_uid: int, owner_gid: int):
    directory(paths.bin_dir, root_uid, root_gid)
    directory(paths.vendor_dir, root_uid, root_gid)
    directory(paths.lock.parent, owner_uid, owner_gid)
    no_existing_stage_or_marker(paths)
    for rel, installed, mode in (
        (GENERATOR, paths.generator, 0o444),
        (OPERATOR, paths.operator, 0o755),
    ):
        if blob(trusted_file(installed, root_uid, root_gid, mode)) != OLD[rel]:
            raise UpgradeError("installed file is not the exact old version")
        candidate = sources.get(rel)
        if (not isinstance(candidate, bytes) or not 0 < len(candidate) <= MAX_BYTES
            or blob(candidate) != NEW[rel]):
            raise UpgradeError("candidate source SHA mismatch")
    return {"result": "CHECK_PASS", "mutation_started": False,
            "old_operator": OLD[OPERATOR], "old_generator": OLD[GENERATOR],
            "new_operator": NEW[OPERATOR], "new_generator": NEW[GENERATOR]}


def sync_directory(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stage(path: Path, content: bytes, mode: int, *, uid: int, gid: int):
    if os.path.lexists(path):
        raise UpgradeError("staged upgrade already exists")
    # FIRST LIVE MUTATION (when separately authorized). No cleanup after failure.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        os.fchown(fd, uid, gid)
        written = 0
        while written < len(content):
            n = os.write(fd, content[written:])
            if n <= 0:
                raise UpgradeError("staged write failed")
            written += n
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    if trusted_file(path, uid, gid, mode) != content:
        raise UpgradeError("staged source bytes changed")
    sync_directory(path.parent)


def execute(paths: Paths, sources: dict[str, bytes], *,
            root_uid: int, root_gid: int, owner_uid: int, owner_gid: int,
            apply: bool, reconfirm=None):
    with locked(paths.lock, owner_uid, owner_gid):
        check = preflight(paths, sources, root_uid=root_uid, root_gid=root_gid,
                          owner_uid=owner_uid, owner_gid=owner_gid)
        if not apply:
            return check
        if reconfirm is None or reconfirm() != sources:
            raise UpgradeError("source confirmation missing or drifted")
        preflight(paths, sources, root_uid=root_uid, root_gid=root_gid,
                  owner_uid=owner_uid, owner_gid=owner_gid)
        # Both source files are staged and verified first; replacing two files is
        # not an atomic pair. Every catalogue writer must be independently paused.
        stage(paths.generator_stage, sources[GENERATOR], 0o444,
              uid=root_uid, gid=root_gid)
        stage(paths.operator_stage, sources[OPERATOR], 0o755,
              uid=root_uid, gid=root_gid)
        for rel, old_path, temporary, mode in (
            (GENERATOR, paths.generator, paths.generator_stage, 0o444),
            (OPERATOR, paths.operator, paths.operator_stage, 0o755),
        ):
            if os.path.lexists(paths.marker):
                raise UpgradeError("post-publish marker changed")
            if blob(trusted_file(old_path, root_uid, root_gid, mode)) != OLD[rel]:
                raise UpgradeError("old installed file changed before replacement")
            if blob(trusted_file(temporary, root_uid, root_gid, mode)) != NEW[rel]:
                raise UpgradeError("staged bytes drift")
            os.replace(temporary, old_path)
            sync_directory(old_path.parent)
            if blob(trusted_file(old_path, root_uid, root_gid, mode)) != NEW[rel]:
                raise UpgradeError("installed new file verification failed")
        no_existing_stage_or_marker(paths)
        return {"result": "UPGRADE_PASS", "mutation_started": True,
                "new_operator": NEW[OPERATOR], "new_generator": NEW[GENERATOR]}


def owner_git(*args: str) -> bytes:
    cmd = [
        "/usr/sbin/runuser", "-u", OWNER, "--", "/usr/bin/env", "-i",
        "HOME=" + str(OWNER_HOME), "PATH=/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null",
        "/usr/bin/git", "-c", "core.hooksPath=/dev/null",
        "-C", str(SOURCE_ROOT), *args,
    ]
    result = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=20, check=False)
    if result.returncode or len(result.stdout) > MAX_BYTES:
        raise UpgradeError("trusted source git check failed")
    return result.stdout


def source_snapshot(expected_sha: str, uid: int, gid: int):
    if not SHA.fullmatch(expected_sha):
        raise UpgradeError("exact main SHA required")
    directory(OWNER_HOME, uid, gid, 0o700)
    directory(SOURCE_ROOT, uid, gid)
    directory(SOURCE_ROOT / ".git", uid, gid)

    def checkout():
        if (owner_git("rev-parse", "HEAD").decode("ascii").strip() != expected_sha
            or owner_git("branch", "--show-current").decode("utf-8").strip() != "main"
            or owner_git("status", "--porcelain=v1", "--untracked-files=all")):
            raise UpgradeError("dirty, wrong-branch or drifted source checkout")

    checkout()
    sources = {}
    for path, digest in NEW.items():
        tracked = owner_git("ls-tree", "HEAD", "--", path).decode("ascii").strip()
        if tracked != "100644 blob " + digest + "\t" + path:
            raise UpgradeError("new source Git blob or mode mismatch")
        content = owner_git("show", "HEAD:" + path)
        if not content or blob(content) != digest:
            raise UpgradeError("new source byte identity mismatch")
        sources[path] = content
    own = SOURCE_ROOT / SCRIPT_REL
    entry = owner_git("ls-tree", "HEAD", "--", SCRIPT_REL).decode("ascii").strip()
    tracked_program = owner_git("show", "HEAD:" + SCRIPT_REL)
    if (not tracked_program or own.is_symlink()
        or entry != "100644 blob " + blob(tracked_program) + "\t" + SCRIPT_REL
        or own.read_bytes() != tracked_program or Path(__file__).absolute() != own):
        raise UpgradeError("upgrade script identity mismatch")
    checkout()
    return sources


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--check", action="store_true")
    command.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-rpi5-main-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if os.geteuid() != 0 or os.getuid() != 0:
            raise UpgradeError("only root may invoke the fixed upgrade")
        root = pwd.getpwnam("root")
        owner = pwd.getpwnam(OWNER)
        group = grp.getgrnam(OWNER)
        if owner.pw_dir != str(OWNER_HOME) or owner.pw_gid != group.gr_gid:
            raise UpgradeError("owner account mismatch")
        candidates = source_snapshot(args.expected_rpi5_main_sha, owner.pw_uid, group.gr_gid)
        paths = Paths(
            Path("/usr/local/bin"),
            Path("/usr/local/share/coloring-pages"),
            Path("/srv/coloring-pages-content/state/drive-ingest/.lock"),
        )
        result = execute(
            paths, candidates, root_uid=root.pw_uid, root_gid=root.pw_gid,
            owner_uid=owner.pw_uid, owner_gid=group.gr_gid, apply=args.apply,
            reconfirm=lambda: source_snapshot(args.expected_rpi5_main_sha,
                                              owner.pw_uid, group.gr_gid),
        )
        result["source_sha"] = args.expected_rpi5_main_sha
        print("COLORING_SITEMAP_UPGRADE " + json.dumps(result, sort_keys=True))
        return 0
    except (UpgradeError, OSError, UnicodeError, ValueError, KeyError,
            subprocess.SubprocessError) as exc:
        print("COLORING_SITEMAP_UPGRADE=STOP error_class=" + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
