#!/usr/bin/env python3
"""Fixed three-component sitemap/ingest cutover. Source only; exact owner LIVE separately required."""
from __future__ import annotations
import argparse
import importlib.machinery
import json
import os
from pathlib import Path
import pwd
import grp
import re
import subprocess
import sys

HELPER_FILE = Path(__file__).absolute().parent / "upgrade-coloring-pages-sitemap-publisher-v1.py"
helper = importlib.machinery.SourceFileLoader("ausmalwiese_pair_upgrade_helper", str(HELPER_FILE)).load_module()
OWNER = "andris"
HOME = Path("/home/andris")
ROOT = HOME / "RPi5_main"
SELF = "scripts/upgrade-ausmalwiese-coordinated-v1.py"
HELPER_REL = "scripts/upgrade-coloring-pages-sitemap-publisher-v1.py"
GEN = "ops/vendor/coloring-pages-sitemap"
PUBLISH = "ops/bin/coloring-pages-sitemap-publish"
INGEST = "ops/bin/coloring-pages-drive-ingest"
OLD = {
    GEN: "5644c8fd366c0c57f6339fddd163c5091ea134c5",
    PUBLISH: "0da51ef361f9ce815ebde3e4cc6cae19a2c2ffe8",
    INGEST: "b1e796696307dcdbc9f92c1caf190c38032ccd71",
}
NEW = {
    GEN: "49c8ba34cf0a4c4ab100463df9adacc4c6e90c2c",
    PUBLISH: "7b0330f30e27d6fe9c5f3e4fbf81fc6473ade660",
    INGEST: "6aba3414af9cc484bde40171f6dd815485c18e22",
}
MARKER_BYTES = b"coloring-pages-sitemap-post-publish-v1\n"
QUIESCENCE_BYTES = b"ausmalwiese-sitemap-ingest-quiesced-v1\n"
SHA = re.compile(r"^[0-9a-f]{40}$")


class Stop(helper.UpgradeError):
    pass


class Paths:
    def __init__(self, bin_dir: Path, vendor_dir: Path, lock: Path):
        self.bin_dir, self.vendor_dir, self.lock = bin_dir, vendor_dir, lock

    @property
    def marker(self):
        return self.vendor_dir / "post-publish-v1.enabled"

    @property
    def quiescence(self):
        return self.vendor_dir / "sitemap-ingest-quiesced-v1.confirmed"

    @property
    def installed(self):
        return {GEN: self.vendor_dir / "coloring-pages-sitemap",
                PUBLISH: self.bin_dir / "coloring-pages-sitemap-publish",
                INGEST: self.bin_dir / "coloring-pages-drive-ingest"}

    @property
    def stages(self):
        return {GEN: self.vendor_dir / ".coloring-pages-sitemap.coordinated.partial",
                PUBLISH: self.bin_dir / ".coloring-pages-sitemap-publish.coordinated.partial",
                INGEST: self.bin_dir / ".coloring-pages-drive-ingest.coordinated.partial"}


def marker_identity(path: Path, uid: int, gid: int, desired: bytes):
    old = path.lstat()
    if helper.trusted_file(path, uid, gid, 0o444) != desired:
        raise Stop("trusted marker or quiescence proof bytes invalid")
    new = path.lstat()
    if (old.st_dev, old.st_ino, old.st_mtime_ns) != (
        new.st_dev, new.st_ino, new.st_mtime_ns
    ):
        raise Stop("trusted marker identity drift")
    return old.st_dev, old.st_ino, old.st_mtime_ns


def preflight(paths: Paths, sources: dict[str, bytes], *, root_uid: int,
              root_gid: int, owner_uid: int, owner_gid: int):
    helper.directory(paths.bin_dir, root_uid, root_gid)
    helper.directory(paths.vendor_dir, root_uid, root_gid)
    helper.directory(paths.lock.parent, owner_uid, owner_gid)
    # The already-enabled post-publish hook stays enabled. Its exact identity
    # and a distinct owner-LIVE-controlled quiescence attestation are REQUIRED.
    marker = marker_identity(paths.marker, root_uid, root_gid, MARKER_BYTES)
    gate = marker_identity(paths.quiescence, root_uid, root_gid, QUIESCENCE_BYTES)
    if any(os.path.lexists(f) for f in paths.stages.values()):
        raise Stop("partial upgrade exists: no cleanup and no retry")
    modes = {GEN: 0o444, PUBLISH: 0o755, INGEST: 0o755}
    for name, location in paths.installed.items():
        if helper.blob(helper.trusted_file(location, root_uid, root_gid, modes[name])) != OLD[name]:
            raise Stop("installed component not exact old release")
        blob = sources.get(name)
        if (not isinstance(blob, bytes) or not 0 < len(blob) <= helper.MAX_BYTES
            or helper.blob(blob) != NEW[name]):
            raise Stop("candidate bytes or Git blob mismatch")
    return marker, gate


def execute(paths: Paths, sources: dict[str, bytes], *, root_uid: int, root_gid: int,
            owner_uid: int, owner_gid: int, apply: bool, reconfirm=None):
    with helper.locked(paths.lock, owner_uid, owner_gid):
        baseline = preflight(paths, sources, root_uid=root_uid, root_gid=root_gid,
                             owner_uid=owner_uid, owner_gid=owner_gid)
        if not apply:
            return {"result": "CHECK_PASS", "mutation_started": False,
                    "components": 3, "enabled_marker_preserved": True}
        if reconfirm is None or reconfirm() != sources:
            raise Stop("source snapshot changed or not reconfirmed")
        if preflight(paths, sources, root_uid=root_uid, root_gid=root_gid,
                     owner_uid=owner_uid, owner_gid=owner_gid) != baseline:
            raise Stop("trusted gate identity drift")
        modes = {GEN: 0o444, PUBLISH: 0o755, INGEST: 0o755}
        # First O_EXCL stage creation is the first LIVE mutation. Fail closed.
        for name in (GEN, PUBLISH, INGEST):
            helper.stage(paths.stages[name], sources[name], modes[name],
                         uid=root_uid, gid=root_gid)
        for name in (GEN, PUBLISH, INGEST):
            current = (
                marker_identity(paths.marker, root_uid, root_gid, MARKER_BYTES),
                marker_identity(paths.quiescence, root_uid, root_gid, QUIESCENCE_BYTES),
            )
            if current != baseline:
                raise Stop("enabled marker or quiescence changed during replacement")
            existing, partial = paths.installed[name], paths.stages[name]
            if helper.blob(helper.trusted_file(existing, root_uid, root_gid, modes[name])) != OLD[name]:
                raise Stop("old installed file changed before replacement")
            if helper.blob(helper.trusted_file(partial, root_uid, root_gid, modes[name])) != NEW[name]:
                raise Stop("candidate stage changed before replacement")
            os.replace(partial, existing)
            helper.sync_directory(existing.parent)
            if helper.blob(helper.trusted_file(existing, root_uid, root_gid, modes[name])) != NEW[name]:
                raise Stop("replacement verification failed")
        if (marker_identity(paths.marker, root_uid, root_gid, MARKER_BYTES),
            marker_identity(paths.quiescence, root_uid, root_gid, QUIESCENCE_BYTES)) != baseline:
            raise Stop("final marker identity changed")
        if any(os.path.lexists(p) for p in paths.stages.values()):
            raise Stop("unexpected partial at successful completion")
        return {"result": "UPGRADE_PASS", "mutation_started": True,
                "enabled_marker_preserved": True, "components": 3,
                "new_ingester_blob": NEW[INGEST]}


def source_snapshot(expected_sha: str, owner_uid: int, owner_gid: int):
    if not SHA.fullmatch(expected_sha):
        raise Stop("exact source revision required")
    helper.directory(HOME, owner_uid, owner_gid, 0o700)
    helper.directory(ROOT, owner_uid, owner_gid)
    helper.directory(ROOT / ".git", owner_uid, owner_gid)

    def require_checkout():
        if (helper.owner_git("rev-parse", "HEAD").decode("ascii").strip() != expected_sha
            or helper.owner_git("branch", "--show-current").decode("utf-8").strip() != "main"
            or helper.owner_git("status", "--porcelain=v1", "--untracked-files=all")):
            raise Stop("source checkout not clean exact main")
    require_checkout()
    sources = {}
    for name, digest in NEW.items():
        mode = "100755" if name == INGEST else "100644"
        track = helper.owner_git("ls-tree", "HEAD", "--", name).decode("ascii").strip()
        if track != mode + " blob " + digest + "\t" + name:
            raise Stop("tracked candidate blob/mode mismatch")
        raw = helper.owner_git("show", "HEAD:" + name)
        if not raw or helper.blob(raw) != digest:
            raise Stop("candidate source bytes mismatched")
        sources[name] = raw
    for name in (SELF, HELPER_REL):
        raw = helper.owner_git("show", "HEAD:" + name)
        entry = helper.owner_git("ls-tree", "HEAD", "--", name).decode("ascii").strip()
        path = ROOT / name
        if (not raw or entry != "100644 blob " + helper.blob(raw) + "\t" + name
            or path.is_symlink() or path.read_bytes() != raw):
            raise Stop("trusted program identity mismatch")
    if Path(__file__).absolute() != ROOT / SELF or HELPER_FILE != ROOT / HELPER_REL:
        raise Stop("trusted source path mismatch")
    require_checkout()
    return sources


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--apply", action="store_true")
    p.add_argument("--expected-rpi5-main-sha", required=True)
    args = p.parse_args(argv)
    try:
        if os.geteuid() != 0 or os.getuid() != 0:
            raise Stop("root identity required")
        root = pwd.getpwnam("root")
        owner = pwd.getpwnam(OWNER)
        group = grp.getgrnam(OWNER)
        if owner.pw_dir != str(HOME) or owner.pw_gid != group.gr_gid:
            raise Stop("source owner invalid")
        sources = source_snapshot(args.expected_rpi5_main_sha, owner.pw_uid, group.gr_gid)
        result = execute(
            Paths(Path("/usr/local/bin"), Path("/usr/local/share/coloring-pages"),
                  Path("/srv/coloring-pages-content/state/drive-ingest/.lock")),
            sources, root_uid=root.pw_uid, root_gid=root.pw_gid,
            owner_uid=owner.pw_uid, owner_gid=group.gr_gid, apply=args.apply,
            reconfirm=lambda: source_snapshot(args.expected_rpi5_main_sha,
                                              owner.pw_uid, group.gr_gid),
        )
        result["source_sha"] = args.expected_rpi5_main_sha
        print("AUSMALWIESE_COORDINATED_UPGRADE " + json.dumps(result, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError, Stop, helper.UpgradeError,
            subprocess.SubprocessError) as exc:
        print("AUSMALWIESE_COORDINATED_UPGRADE=STOP error_class=" + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
