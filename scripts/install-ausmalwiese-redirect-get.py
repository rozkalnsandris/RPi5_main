#!/usr/bin/env python3
"""Source-only fail-closed installer for fixed Redirect Rules GET inventory.

This installer is NOT authorized for runtime use by source merge. Any --apply
requires new exact owner LIVE authority, an approved source SHA and privileges.
Never reads credentials, calls Cloudflare, changes permissions or sudoers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[1]
REPO = "rozkalnsandris/RPi5_main"
LAUNCHER_REL = "scripts/ausmalwiese_redirect_trusted_launcher.py"
INVENTORY_REL = "scripts/ausmalwiese_redirect_inventory.py"
ADAPTER_REL = "scripts/ausmalwiese_redirect_get_adapter.py"
SOURCE_PATHS = (LAUNCHER_REL, INVENTORY_REL, ADAPTER_REL)
GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
STAT = "/usr/bin/stat"
TEST = "/usr/bin/test"
TRUE = "/usr/bin/true"
MKDIR = "/usr/bin/mkdir"
INSTALL = "/usr/bin/install"
SHA256SUM = "/usr/bin/sha256sum"
EXE = "/usr/local/sbin/rpi5-ausmalwiese-redirect-get"
LIB = "/usr/local/libexec/rpi5-ausmalwiese-redirect-get"
INV = LIB + "/inventory.py"
ADAPT = LIB + "/adapter.py"
RELEASE = LIB + "/release.json"
PARENTS = ("/usr", "/usr/local", "/usr/local/sbin", "/usr/local/libexec")
TARGETS = (EXE, LIB, INV, ADAPT, RELEASE)
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
CONFIRM = "INSTALL-AUSMALWIESE-REDIRECT-GET"


class Stop(Exception):
    """Fixed public-safe failure code only."""


def invoke(argv, data=None, *, runner=subprocess.run):
    try:
        return runner(list(argv), input=data, stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE, check=False, timeout=25)
    except Exception:
        raise Stop("command_unavailable") from None


def checked_git(argv, *, runner=subprocess.run) -> bytes:
    result = invoke([GIT, "-C", str(SOURCE_ROOT), *argv], runner=runner)
    if result.returncode != 0 or type(result.stdout) is not bytes or len(result.stdout) > 262144:
        raise Stop("git_preflight_failed")
    return result.stdout


def ascii_text(raw):
    try:
        return raw.decode("utf-8").strip()
    except UnicodeError:
        raise Stop("git_output_invalid") from None


def checkout(expected_main, *, runner=subprocess.run):
    if os.geteuid() == 0:
        raise Stop("must_be_unprivileged")
    if not isinstance(expected_main, str) or not SHA40.fullmatch(expected_main):
        raise Stop("invalid_main_sha")
    if ascii_text(checked_git(["rev-parse", "--show-toplevel"], runner=runner)) != str(SOURCE_ROOT):
        raise Stop("checkout_mismatch")
    if ascii_text(checked_git(["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner)) != "main":
        raise Stop("not_main")
    if ascii_text(checked_git(["rev-parse", "HEAD"], runner=runner)) != expected_main:
        raise Stop("main_drift")
    if checked_git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], runner=runner):
        raise Stop("dirty_checkout")
    origin = ascii_text(checked_git(["remote", "get-url", "origin"], runner=runner)).rstrip("/")
    valid = origin in (
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
        "git@github.com:rozkalnsandris/RPi5_main",
        "git@github.com:rozkalnsandris/RPi5_main.git",
    )
    if not valid:
        raise Stop("origin_mismatch")


def tracked(rel, *, runner=subprocess.run) -> bytes:
    if rel not in SOURCE_PATHS:
        raise Stop("path_scope_invalid")
    path = SOURCE_ROOT / rel
    try:
        meta = path.lstat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_size < 1 or meta.st_size > 131072:
            raise Stop("source_invalid")
        raw = path.read_bytes()
    except OSError:
        raise Stop("source_unavailable") from None
    if len(raw) != meta.st_size or raw != checked_git(["show", "HEAD:" + rel], runner=runner):
        raise Stop("source_digest_mismatch")
    return raw


def release_bytes(expected_main, launcher, inventory, adapter) -> bytes:
    if not SHA40.fullmatch(expected_main):
        raise Stop("invalid_main_sha")
    return (json.dumps({
        "schema_version": 1,
        "repository": REPO,
        "source_sha": expected_main,
        "zone_name": "rozkalns.net",
        "launcher_sha256": hashlib.sha256(launcher).hexdigest(),
        "inventory_sha256": hashlib.sha256(inventory).hexdigest(),
        "adapter_sha256": hashlib.sha256(adapter).hexdigest(),
    }, separators=(",", ":"), sort_keys=True) + "\n").encode("ascii")


def sudo_read(args, *, runner=subprocess.run) -> str:
    result = invoke([SUDO, "-n", *args], runner=runner)
    if result.returncode or type(result.stdout) is not bytes or len(result.stdout) > 256:
        raise Stop("sudo_read_failed")
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeError:
        raise Stop("sudo_read_failed") from None


def host_preflight(*, runner=subprocess.run):
    sudo_read([TRUE], runner=runner)
    for path in PARENTS:
        out = sudo_read([STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner)
        parts = out.split(":")
        if len(parts) != 4 or parts[:2] != ["0", "0"] or parts[3] != "directory":
            raise Stop("unsafe_parent")
        try:
            bits = int(parts[2], 8)
        except ValueError:
            raise Stop("unsafe_parent") from None
        if bits & 0o022 or bits & 0o700 != 0o700:
            raise Stop("unsafe_parent")
    for path in TARGETS:
        for flag in ("-e", "-L"):
            r = invoke([SUDO, "-n", TEST, flag, path], runner=runner)
            if r.returncode == 0:
                raise Stop("target_already_exists")
            if r.returncode != 1:
                raise Stop("target_preflight_failed")


def preflight(expected_main, *, runner=subprocess.run):
    checkout(expected_main, runner=runner)
    launcher, inventory, adapter = [tracked(x, runner=runner) for x in SOURCE_PATHS]
    manifest = release_bytes(expected_main, launcher, inventory, adapter)
    host_preflight(runner=runner)
    return launcher, inventory, adapter, manifest


def write_once(args, content=None, *, runner=subprocess.run):
    try:
        r = invoke([SUDO, "-n", *args], content, runner=runner)
        if r.returncode:
            raise Stop("post_dispatch_unknown_state")
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def post_verify(entries, *, runner=subprocess.run):
    for path, mode, payload in entries:
        actual = sudo_read([STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner)
        kind = "directory" if payload is None else "regular file"
        if actual != f"0:0:{mode}:{kind}":
            raise Stop("post_verify_metadata_mismatch")
        if payload is not None:
            digest = hashlib.sha256(payload).hexdigest()
            observed = sudo_read([SHA256SUM, "--", path], runner=runner)
            if observed != f"{digest}  {path}":
                raise Stop("post_verify_digest_mismatch")


def apply(expected_main, *, runner=subprocess.run):
    launcher, inventory, adapter, manifest = preflight(expected_main, runner=runner)
    files = ((EXE, "500", launcher), (INV, "400", inventory),
             (ADAPT, "400", adapter), (RELEASE, "400", manifest))
    # FIRST HOST MUTATION is mkdir. No cleanup/retry/rollback after dispatch.
    try:
        write_once([MKDIR, "-m", "0700", "--", LIB], runner=runner)
        for path, mode, raw in files:
            write_once([INSTALL, "-T", "-o", "root", "-g", "root",
                        "-m", "0" + mode, "--", "/dev/stdin", path], raw, runner=runner)
        post_verify(((LIB, "700", None), *files), runner=runner)
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            if args.confirm != CONFIRM:
                raise Stop("owner_confirmation_required")
            apply(args.expected_main)
            result = {"status": "PASS", "mutation_state": "dispatched"}
        else:
            if args.confirm:
                raise Stop("confirm_without_apply")
            launcher, inventory, adapter, manifest = preflight(args.expected_main)
            result = {"status": "PREFLIGHT_PASS", "mutation_state": "not_started",
                      "release_sha256": hashlib.sha256(manifest).hexdigest()}
        print(json.dumps(result, sort_keys=True))
        return 0
    except Stop as e:
        uncertain = str(e) == "post_dispatch_unknown_state"
        print(json.dumps({"status": "STOP", "reason": str(e),
                          "mutation_state": "unknown" if uncertain else "not_started"}))
        return 4 if uncertain else 3


if __name__ == "__main__":
    sys.exit(main())
