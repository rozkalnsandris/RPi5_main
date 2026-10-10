#!/usr/bin/env python3
"""Source-only design: fail-closed replacement of one existing zone WAF release.

No automatic execution. A separate exact owner LIVE authorization is required.
Unprivileged orchestrator uses fixed sudo GNU coreutils; never runs source as root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REL = "scripts/cloudflare_zone_bot_waf.py"
SOURCE = ROOT / SOURCE_REL
TARGET = "/usr/local/sbin/rpi5-cloudflare-zone-bot-waf"
RELEASE_DIR = "/usr/local/libexec/rpi5-cloudflare-zone-bot-waf"
RELEASE = RELEASE_DIR + "/release.json"
STAGE_OPERATOR = TARGET + ".stage-969"
STAGE_RELEASE = RELEASE + ".stage-969"
OLD_MAIN = "861c1da26caba215ef05a1681a6bcd190641c43f"
OLD_OPERATOR_SHA = "95adf48824f24a381b7691b078afbbe9948578e338dab69099848e42e4a61e42"
OLD_RELEASE_SHA = "dd71c7ce33430c465af7ada9e15981c8e38c4c0e2d4d94b26e20786059782ccc"
ROOT_DIRS = ("/usr", "/usr/local", "/usr/local/sbin", "/usr/local/libexec", RELEASE_DIR)
GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
STAT = "/usr/bin/stat"
TEST = "/usr/bin/test"
SHA256SUM = "/usr/bin/sha256sum"
INSTALL = "/usr/bin/install"
MV = "/usr/bin/mv"
TRUE = "/usr/bin/true"
CONFIRM = "REPLACE-EXACT-ROZKALNS-ZONE-WAF-RELEASE"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class Stop(Exception):
    """Sanitized failure marker (no file contents, credentials or provider responses)."""


def run(argv, *, data=None, runner=subprocess.run):
    try:
        result = runner(argv, input=data, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, check=False)
    except OSError:
        raise Stop("command_unavailable") from None
    return result


def read(argv, *, runner=subprocess.run):
    result = run(argv, runner=runner)
    if result.returncode:
        raise Stop("read_only_preflight_failed")
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        raise Stop("invalid_preflight_output") from None


def git(*args, runner=subprocess.run):
    return read([GIT, "-C", str(ROOT), *args], runner=runner)


def source_bytes(expected_main, *, runner=subprocess.run):
    if os.geteuid() == 0:
        raise Stop("must_run_unprivileged")
    if not SHA40.fullmatch(expected_main) or expected_main == OLD_MAIN:
        raise Stop("invalid_candidate_main")
    if git("rev-parse", "--show-toplevel", runner=runner) != str(ROOT):
        raise Stop("unexpected_checkout")
    if git("symbolic-ref", "--quiet", "--short", "HEAD", runner=runner) != "main":
        raise Stop("not_main")
    if git("rev-parse", "HEAD", runner=runner) != expected_main:
        raise Stop("main_drift")
    if git("status", "--porcelain=v1", "--untracked-files=all", runner=runner):
        raise Stop("dirty_checkout")
    if git("remote", "get-url", "origin", runner=runner).rstrip("/") not in (
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
    ):
        raise Stop("wrong_origin")
    if git("ls-files", "--error-unmatch", SOURCE_REL, runner=runner) != SOURCE_REL:
        raise Stop("source_not_tracked")
    try:
        source = SOURCE.read_bytes()
    except OSError:
        raise Stop("source_unavailable") from None
    if not source or len(source) > 131072:
        raise Stop("candidate_source_size_invalid")
    return source


def metadata(expected_main, source):
    return (json.dumps({"operator_sha256": hashlib.sha256(source).hexdigest(),
                        "source_sha": expected_main},
                       separators=(",", ":"), sort_keys=True) + "\n").encode("ascii")


def root_text(argv, *, runner=subprocess.run):
    return read([SUDO, "-n", *argv], runner=runner)


def existing(path, mode, digest, *, runner=subprocess.run):
    observed = root_text([STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner)
    if observed != f"0:0:{mode}:regular file":
        raise Stop("incumbent_metadata_drift")
    actual = root_text([SHA256SUM, "--", path], runner=runner)
    if actual != f"{digest}  {path}":
        raise Stop("incumbent_digest_drift")


def preflight(expected_main, *, runner=subprocess.run):
    source = source_bytes(expected_main, runner=runner)
    release = metadata(expected_main, source)
    root_text([TRUE], runner=runner)
    for path in ROOT_DIRS:
        meta = root_text([STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner)
        parts = meta.split(":")
        if len(parts) != 4 or parts[0:2] != ["0", "0"] or parts[3] != "directory":
            raise Stop("unsafe_parent")
        try:
            bits = int(parts[2], 8)
        except ValueError:
            raise Stop("unsafe_parent") from None
        if bits & 0o022 or bits & 0o700 != 0o700:
            raise Stop("unsafe_parent")
    existing(TARGET, "500", OLD_OPERATOR_SHA, runner=runner)
    existing(RELEASE, "400", OLD_RELEASE_SHA, runner=runner)
    # 'test -e' plus '-L' also catches dangling symlinks.
    for path in (STAGE_OPERATOR, STAGE_RELEASE):
        for flag in ("-e", "-L"):
            result = run([SUDO, "-n", TEST, flag, path], runner=runner)
            if result.returncode != 1:
                raise Stop("staging_path_not_proven_absent")
    return source, release


def privileged_write(argv, *, data=None, runner=subprocess.run):
    # Any error after first write dispatch is terminal; never retry/cleanup.
    try:
        result = run([SUDO, "-n", *argv], data=data, runner=runner)
        if result.returncode:
            raise Stop("mutation_outcome_unknown")
    except Exception:
        raise Stop("mutation_outcome_unknown") from None


def replace(expected_main, *, runner=subprocess.run):
    source, release = preflight(expected_main, runner=runner)
    try:
        privileged_write([INSTALL, "-T", "-o", "root", "-g", "root", "-m", "0500",
                          "--", "/dev/stdin", STAGE_OPERATOR], data=source, runner=runner)
        privileged_write([INSTALL, "-T", "-o", "root", "-g", "root", "-m", "0400",
                          "--", "/dev/stdin", STAGE_RELEASE], data=release, runner=runner)
        existing(STAGE_OPERATOR, "500", hashlib.sha256(source).hexdigest(), runner=runner)
        existing(STAGE_RELEASE, "400", hashlib.sha256(release).hexdigest(), runner=runner)
        existing(TARGET, "500", OLD_OPERATOR_SHA, runner=runner)
        existing(RELEASE, "400", OLD_RELEASE_SHA, runner=runner)
        # Two individually atomic renames, NOT one atomic release transaction.
        privileged_write([MV, "-T", "--", STAGE_OPERATOR, TARGET], runner=runner)
        privileged_write([MV, "-T", "--", STAGE_RELEASE, RELEASE], runner=runner)
        existing(TARGET, "500", hashlib.sha256(source).hexdigest(), runner=runner)
        existing(RELEASE, "400", hashlib.sha256(release).hexdigest(), runner=runner)
    except Exception:
        raise Stop("mutation_outcome_unknown") from None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            if args.confirm != CONFIRM:
                raise Stop("confirmation_missing")
            replace(args.expected_main)
            result = {"status": "PASS", "mutation_started": True}
        else:
            if args.confirm:
                raise Stop("confirmation_requires_apply")
            source, _ = preflight(args.expected_main)
            result = {"status": "PREFLIGHT_PASS", "mutation_started": False,
                      "candidate_sha256": hashlib.sha256(source).hexdigest()}
        print(json.dumps(result, sort_keys=True))
        return 0
    except Stop as exc:
        print(json.dumps({"status": "STOP", "reason": str(exc)}))
        return 4


if __name__ == "__main__":
    sys.exit(main())
