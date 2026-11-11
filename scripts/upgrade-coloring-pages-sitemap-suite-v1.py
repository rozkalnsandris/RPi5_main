#!/usr/bin/env python3
"""Three-file fixed-path sitemap upgrade; source only until exact LIVE owner gate."""
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
SCRIPT_REL = "scripts/upgrade-coloring-pages-sitemap-suite-v1.py"
OPERATOR = "ops/bin/coloring-pages-sitemap-publish"
GENERATOR = "ops/vendor/coloring-pages-sitemap"
INGEST = "ops/bin/coloring-pages-drive-ingest"
OLD = {
    OPERATOR: "4ade38f1225f4c1bc102fda8d5538f9262695d43",
    GENERATOR: "5d1d37c32573aa8ac0d91f45b73938638fd183e9",
    INGEST: "b10dc43bceb8ac3b77d8af47661b11a4ca50ea90",
}
NEW = {
    OPERATOR: "3263845045f6d38f31ff359158be90ab59006240",
    GENERATOR: "f4ffaa4293f9c46f475f96d4409f05ff347a7590",
    INGEST: "c4e2f67e0154f705e2d46db9dcc87e6a69b108fd",
}
MARKER_BYTES = b"coloring-pages-sitemap-post-publish-v1\n"
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
    def ingest(self):
        return self.bin_dir / "coloring-pages-drive-ingest"

    @property
    def ingest_stage(self):
        return self.bin_dir / ".coloring-pages-drive-ingest.sitemap-suite.partial"

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


def no_existing_stage(paths: Paths):
    if any(os.path.lexists(p) for p in (
        paths.generator_stage, paths.operator_stage, paths.ingest_stage
    )):
        raise UpgradeError("preexisting stage")


def marker_state(paths: Paths, root_uid: int, root_gid: int) -> str:
    if not os.path.lexists(paths.marker):
        return "absent"
    content = trusted_file(paths.marker, root_uid, root_gid, 0o444)
    if content != MARKER_BYTES:
        raise UpgradeError("unsafe post-publish marker")
    return "enabled"


def require_writer_quiescence() -> bool:
    """Read-only fixed systemd guard; owner must ALSO exclude direct writers.

    The shared flock blocks only cooperating ingesters. These unit checks do
    not prevent an unrelated direct Docker importer or later manual invocation.
    A separate, currently valid owner LIVE gate must cover that risk.
    """
    for unit in (
        "coloring-pages-admin-publish.service",
        "coloring-pages-publish-request-bridge.service",
    ):
        result = subprocess.run(
            ["/usr/bin/systemctl", "show", unit,
             "--property=LoadState,ActiveState,Job", "--no-pager"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=8, check=False,
        )
        if result.returncode or len(result.stdout) > 4096:
            raise UpgradeError("quiescence systemd observation failed")
        lines = result.stdout.strip().splitlines()
        if len(lines) != 3 or any(line.count("=") != 1 for line in lines):
            raise UpgradeError("quiescence unit state ambiguous")
        state = dict(line.split("=", 1) for line in lines)
        if (set(state) != {"LoadState", "ActiveState", "Job"}
            or state["LoadState"] != "loaded"
            or state["ActiveState"] != "inactive"
            or state["Job"] not in ("", "0")):
            raise UpgradeError("catalogue writer entrance is not quiescent")
    return True


def assert_writer_quiescence(probe):
    if probe is None or probe() is not True:
        raise UpgradeError("independent writer quiescence required")


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
              root_uid: int, root_gid: int, owner_uid: int, owner_gid: int,
              expected_marker: str):
    directory(paths.bin_dir, root_uid, root_gid)
    directory(paths.vendor_dir, root_uid, root_gid)
    directory(paths.lock.parent, owner_uid, owner_gid)
    no_existing_stage(paths)
    marker = marker_state(paths, root_uid, root_gid)
    if expected_marker not in ("enabled", "absent") or marker != expected_marker:
        raise UpgradeError("post-publish marker expected state mismatch")
    for rel, installed, mode in (
        (GENERATOR, paths.generator, 0o444),
        (OPERATOR, paths.operator, 0o755),
        (INGEST, paths.ingest, 0o755),
    ):
        if blob(trusted_file(installed, root_uid, root_gid, mode)) != OLD[rel]:
            raise UpgradeError("installed file is not the exact old version")
        candidate = sources.get(rel)
        if (not isinstance(candidate, bytes) or not 0 < len(candidate) <= MAX_BYTES
            or blob(candidate) != NEW[rel]):
            raise UpgradeError("candidate source SHA mismatch")
    return {"result": "CHECK_PASS", "mutation_started": False,
            "old_operator": OLD[OPERATOR], "old_generator": OLD[GENERATOR],
            "old_ingest": OLD[INGEST], "new_ingest": NEW[INGEST],
            "new_operator": NEW[OPERATOR], "new_generator": NEW[GENERATOR],
            "marker": marker, "quiescence": "unit-guard-only"}


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
            apply: bool, expected_marker: str, quiescence=None, reconfirm=None):
    with locked(paths.lock, owner_uid, owner_gid):
        assert_writer_quiescence(quiescence)
        check = preflight(paths, sources, root_uid=root_uid, root_gid=root_gid,
                          owner_uid=owner_uid, owner_gid=owner_gid,
                          expected_marker=expected_marker)
        if not apply:
            return check
        if reconfirm is None or reconfirm() != sources:
            raise UpgradeError("source confirmation missing or drifted")
        marker = check["marker"]
        assert_writer_quiescence(quiescence)
        recheck = preflight(paths, sources, root_uid=root_uid, root_gid=root_gid,
                            owner_uid=owner_uid, owner_gid=owner_gid,
                            expected_marker=expected_marker)
        if recheck["marker"] != marker:
            raise UpgradeError("post-publish marker state drift")
        # All 3 candidate files staged + fsynced before first replacement.
        # Replacing 3 files is NOT atomic as a group. All catalogue writers
        # must remain independently quiescent during this entire window.
        stage(paths.generator_stage, sources[GENERATOR], 0o444,
              uid=root_uid, gid=root_gid)
        stage(paths.operator_stage, sources[OPERATOR], 0o755,
              uid=root_uid, gid=root_gid)
        stage(paths.ingest_stage, sources[INGEST], 0o755,
              uid=root_uid, gid=root_gid)
        for rel, old_path, temporary, mode in (
            (GENERATOR, paths.generator, paths.generator_stage, 0o444),
            (OPERATOR, paths.operator, paths.operator_stage, 0o755),
            (INGEST, paths.ingest, paths.ingest_stage, 0o755),
        ):
            assert_writer_quiescence(quiescence)
            if marker_state(paths, root_uid, root_gid) != marker:
                raise UpgradeError("post-publish marker state drift")
            if blob(trusted_file(old_path, root_uid, root_gid, mode)) != OLD[rel]:
                raise UpgradeError("old installed file changed before replacement")
            if blob(trusted_file(temporary, root_uid, root_gid, mode)) != NEW[rel]:
                raise UpgradeError("staged bytes drift")
            os.replace(temporary, old_path)
            sync_directory(old_path.parent)
            if blob(trusted_file(old_path, root_uid, root_gid, mode)) != NEW[rel]:
                raise UpgradeError("installed new file verification failed")
        no_existing_stage(paths)
        assert_writer_quiescence(quiescence)
        if marker_state(paths, root_uid, root_gid) != marker:
            raise UpgradeError("post-publish marker state drift")
        return {"result": "UPGRADE_PASS", "mutation_started": True,
                "new_operator": NEW[OPERATOR], "new_generator": NEW[GENERATOR],
                "new_ingest": NEW[INGEST], "marker": marker}


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
    parser.add_argument("--expected-marker-state", required=True,
                        choices=("enabled", "absent"))
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
            expected_marker=args.expected_marker_state,
            quiescence=require_writer_quiescence,
            reconfirm=lambda: source_snapshot(args.expected_rpi5_main_sha,
                                              owner.pw_uid, group.gr_gid),
        )
        result["source_sha"] = args.expected_rpi5_main_sha
        print("COLORING_SITEMAP_SUITE_UPGRADE " + json.dumps(result, sort_keys=True))
        return 0
    except (UpgradeError, OSError, UnicodeError, ValueError, KeyError,
            subprocess.SubprocessError) as exc:
        print("COLORING_SITEMAP_SUITE_UPGRADE=STOP error_class=" + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
