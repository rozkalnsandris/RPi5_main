#!/usr/bin/env python3
"""Source-only exact-release zone WAF installer. No privileged Python evaluator.

Default mode is read-only. The apply mode requires separate owner LIVE authority.
It only invokes fixed GNU coreutils, never executes checkout bytes as root.
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
from typing import Callable

REPOSITORY = "rozkalnsandris/RPi5_main"
ROOT = Path(__file__).resolve().parents[1]
SOURCE_REL = "scripts/cloudflare_zone_bot_waf.py"
SOURCE = ROOT / SOURCE_REL
INSTALLED = "/usr/local/sbin/rpi5-cloudflare-zone-bot-waf"
RELEASE_DIR = "/usr/local/libexec/rpi5-cloudflare-zone-bot-waf"
RELEASE = RELEASE_DIR + "/release.json"
PARENTS = ("/usr", "/usr/local", "/usr/local/sbin", "/usr/local/libexec")
EXPECTED_CONFIRM = "INSTALL-ROZKALNS-ZONE-BOT-WAF"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
STAT = "/usr/bin/stat"
TEST = "/usr/bin/test"
MKDIR = "/usr/bin/mkdir"
INSTALL = "/usr/bin/install"
SHA256SUM = "/usr/bin/sha256sum"
RUNNER = Callable[..., subprocess.CompletedProcess]


class InstallError(Exception):
    """Only sanitized, predefined failure reasons are surfaced."""


def run(argv: list[str], *, input_bytes: bytes | None = None,
        runner: RUNNER = subprocess.run) -> subprocess.CompletedProcess:
    return runner(argv, input=input_bytes, stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE, check=False)


def git(args: list[str], *, runner: RUNNER = subprocess.run) -> str:
    try:
        completed = run([GIT, "-C", str(ROOT), *args], runner=runner)
    except OSError:
        raise InstallError("git_preflight_failed") from None
    if completed.returncode != 0:
        raise InstallError("git_preflight_failed")
    try:
        return completed.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise InstallError("git_output_invalid") from None


def checked_source(expected_main: str, *, runner: RUNNER = subprocess.run) -> bytes:
    if os.geteuid() == 0:
        raise InstallError("installer_must_not_run_as_root")
    if not SHA40.fullmatch(expected_main):
        raise InstallError("invalid_expected_main")
    if git(["rev-parse", "--show-toplevel"], runner=runner) != str(ROOT):
        raise InstallError("unexpected_checkout")
    if git(["branch", "--show-current"], runner=runner) != "main":
        raise InstallError("not_main")
    if git(["rev-parse", "HEAD"], runner=runner) != expected_main:
        raise InstallError("main_drift")
    if git(["status", "--porcelain=v1", "--untracked-files=all"], runner=runner):
        raise InstallError("dirty_checkout")
    origin = git(["remote", "get-url", "origin"], runner=runner)
    if origin.rstrip("/") not in (
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
    ):
        raise InstallError("wrong_origin")
    if git(["ls-files", "--error-unmatch", SOURCE_REL], runner=runner) != SOURCE_REL:
        raise InstallError("untracked_operator")
    try:
        source = SOURCE.read_bytes()
    except OSError:
        raise InstallError("source_unreadable") from None
    if not source or len(source) > 131072:
        raise InstallError("source_size_invalid")
    return source


def metadata_for(expected_main: str, source: bytes) -> bytes:
    return (json.dumps({"source_sha": expected_main,
                        "operator_sha256": hashlib.sha256(source).hexdigest()},
                       sort_keys=True, separators=(",", ":")) + "\n").encode()


def root_read(argv: list[str], *, runner: RUNNER = subprocess.run) -> str:
    try:
        completed = run([SUDO, "-n", *argv], runner=runner)
    except OSError:
        raise InstallError("root_preflight_unavailable") from None
    if completed.returncode != 0:
        raise InstallError("root_preflight_failed")
    try:
        return completed.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        raise InstallError("root_preflight_invalid") from None


def require_targets_absent(*, runner: RUNNER = subprocess.run) -> None:
    root_read(["/usr/bin/true"], runner=runner)
    for parent in PARENTS:
        observed = root_read([STAT, "-c", "%u:%g:%a:%F", "--", parent],
                             runner=runner)
        parts = observed.split(":")
        if len(parts) != 4 or parts[:2] != ["0", "0"] or parts[3] != "directory":
            raise InstallError("unsafe_install_parent")
        try:
            mode = int(parts[2], 8)
        except ValueError:
            raise InstallError("unsafe_install_parent") from None
        if mode & 0o022 or mode & 0o700 != 0o700:
            raise InstallError("unsafe_install_parent")

    for path in (INSTALLED, RELEASE_DIR, RELEASE):
        # Detect files, directories AND dangling symlinks. No write on preflight.
        for flag in ("-e", "-L"):
            try:
                completed = run([SUDO, "-n", TEST, flag, path], runner=runner)
            except OSError:
                raise InstallError("target_check_failed") from None
            if completed.returncode == 0:
                raise InstallError("target_already_exists")
            if completed.returncode != 1:
                raise InstallError("target_check_failed")


def preflight(expected_main: str, *, runner: RUNNER = subprocess.run) -> tuple[bytes, bytes]:
    source = checked_source(expected_main, runner=runner)
    require_targets_absent(runner=runner)
    return source, metadata_for(expected_main, source)


def root_step(argv: list[str], *, input_bytes: bytes | None,
              runner: RUNNER) -> None:
    """After the first sudo write is dispatched, *any* problem means STOP."""
    try:
        completed = run([SUDO, "-n", *argv], input_bytes=input_bytes,
                        runner=runner)
        if completed.returncode != 0:
            raise InstallError("post_dispatch_unknown_state")
    except Exception:
        raise InstallError("post_dispatch_unknown_state") from None


def verify_install(source: bytes, metadata: bytes, *,
                   runner: RUNNER = subprocess.run) -> None:
    for path, mode, expected in (
        (RELEASE_DIR, "700", None),
        (INSTALLED, "500", hashlib.sha256(source).hexdigest()),
        (RELEASE, "400", hashlib.sha256(metadata).hexdigest()),
    ):
        observed = root_read([STAT, "-c", "%u:%g:%a:%F", "--", path],
                             runner=runner)
        kind = "directory" if expected is None else "regular file"
        if observed != f"0:0:{mode}:{kind}":
            raise InstallError("post_install_metadata_mismatch")
        if expected is not None:
            checksum = root_read([SHA256SUM, "--", path], runner=runner)
            if checksum != f"{expected}  {path}":
                raise InstallError("post_install_digest_mismatch")


def install(expected_main: str, *, runner: RUNNER = subprocess.run) -> None:
    source, metadata = preflight(expected_main, runner=runner)
    # Commit to the frozen source bytes, not a later read of the checkout.
    # First command is the first mutation. No sudo shell, Python -c,
    # caller-supplied command, alternate path, retry or automatic rollback.
    try:
        root_step([MKDIR, "-m", "0700", "--", RELEASE_DIR],
                  input_bytes=None, runner=runner)
        root_step([INSTALL, "-T", "-o", "root", "-g", "root", "-m",
                   "0500", "--", "/dev/stdin", INSTALLED],
                  input_bytes=source, runner=runner)
        root_step([INSTALL, "-T", "-o", "root", "-g", "root", "-m",
                   "0400", "--", "/dev/stdin", RELEASE],
                  input_bytes=metadata, runner=runner)
        verify_install(source, metadata, runner=runner)
    except Exception:
        # Cannot assume what happened to any of the three root-owned targets.
        raise InstallError("post_dispatch_unknown_state") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            if args.confirm != EXPECTED_CONFIRM:
                raise InstallError("confirmation_missing")
            install(args.expected_main)
            result = {"status": "PASS", "mutation_started": True}
        else:
            if args.confirm:
                raise InstallError("confirmation_requires_apply")
            source, _ = preflight(args.expected_main)
            result = {"status": "PREFLIGHT_PASS", "mutation_started": False,
                      "operator_sha256": hashlib.sha256(source).hexdigest()}
        print(json.dumps(result, sort_keys=True))
        return 0
    except InstallError as exc:
        unknown = str(exc) == "post_dispatch_unknown_state"
        print(json.dumps({"status": "STOP_ERROR" if unknown else "BLOCKED",
                          "reason": str(exc),
                          "mutation_state": "unknown" if unknown else "not_started"}))
        return 4 if unknown else 3


if __name__ == "__main__":
    sys.exit(main())
