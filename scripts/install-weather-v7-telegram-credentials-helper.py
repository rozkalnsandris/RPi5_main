#!/usr/bin/env python3
"""Source-only, separately LIVE-gated installation of a fixed root credential helper."""
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

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
SOURCE = "scripts/weather-v7-telegram-credentials-helper.py"
TARGET = Path("/usr/local/sbin/rpi5-weather-v7-telegram-credentials")
CONTRACT = "ops/contracts/weather-v7-telegram-credentials-v1.json"


class Stop(Exception):
    """Public-safe static failure category."""


def git(*args: str) -> str:
    try:
        cp = subprocess.run(
            ["/usr/bin/git", "-c", "safe.directory=" + str(ROOT), "-C", str(ROOT), *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, check=True, timeout=15,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError):
        raise Stop("source_git_identity_invalid") from None
    return cp.stdout.strip()


def source_check(expected_sha: str) -> dict[str, object]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise Stop("invalid_expected_main_sha")
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise Stop("source_root_unsafe")
    if (git("rev-parse", "HEAD") != expected_sha or
            git("branch", "--show-current") != "main" or
            git("remote", "get-url", "origin") != ORIGIN or
            git("status", "--porcelain=v1", "--untracked-files=all") != ""):
        raise Stop("source_checkout_mismatch")
    expected_paths = (SOURCE, CONTRACT)
    for path in expected_paths:
        candidate = ROOT / path
        try:
            info = candidate.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise Stop("source_file_unsafe")
            if git("ls-files", "--error-unmatch", "--", path) != path:
                raise Stop("source_file_untracked")
            if git("hash-object", "--", str(candidate)) != git("rev-parse", "HEAD:" + path):
                raise Stop("source_file_identity_drift")
        except OSError:
            raise Stop("source_file_missing") from None
    try:
        contract = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Stop("contract_invalid") from None
    if (contract.get("schema") != "rozkalns.rpi5-main.weather-v7-telegram-credentials.v1"
            or contract.get("installed_helper") != str(TARGET)
            or contract.get("installed_mode") != "0500"
            or contract.get("credential_files") != [
                "/etc/credstore/weather-v7-failure-telegram-token",
                "/etc/credstore/weather-v7-failure-telegram-chat-id",
            ]):
        raise Stop("contract_drift")
    return {
        "result": "SOURCE_PASS", "source_sha": expected_sha,
        "host_inspected": False, "mutation_started": False,
        "live_authorized": False,
    }


def preflight(expected_sha: str) -> dict[str, object]:
    source_check(expected_sha)
    parent = TARGET.parent
    try:
        info = parent.lstat()
    except OSError:
        raise Stop("target_parent_missing") from None
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or info.st_gid != 0 or stat.S_IMODE(info.st_mode) & 0o022):
        raise Stop("target_parent_untrusted")
    if TARGET.exists() or TARGET.is_symlink():
        raise Stop("first_install_only")
    return {
        "result": "HOST_PREFLIGHT_PASS", "source_sha": expected_sha,
        "credential_contents_read": False, "mutation_started": False,
    }


def apply(expected_sha: str) -> dict[str, object]:
    if os.geteuid() != 0:
        raise Stop("separate_owner_live_authorized_root_required")
    preflight(expected_sha)
    # This first O_EXCL consumes the specific owner LIVE authorization.
    # No retry, rollback, cleanup or alternate installation if it fails.
    source = (ROOT / SOURCE).read_bytes()
    if not source:
        raise Stop("source_empty")
    try:
        fd = os.open(TARGET, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | os.O_NOFOLLOW | os.O_CLOEXEC, 0o500)
        try:
            os.fchown(fd, 0, 0)
            os.fchmod(fd, 0o500)
            if os.write(fd, source) != len(source):
                raise Stop("post_mutation_unknown")
            os.fsync(fd)
            info = os.fstat(fd)
            if (info.st_uid, info.st_gid) != (0, 0) or info.st_nlink != 1:
                raise Stop("post_mutation_unknown")
        finally:
            os.close(fd)
    except Exception:
        raise Stop("post_mutation_unknown") from None
    return {
        "result": "INSTALL_PASS", "source_sha": expected_sha,
        "helper_file_created": True, "mode": "0500", "mutation_started": True,
        "credential_files_created": False, "secret_values_read": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixed Weather v7 credential helper install")
    parser.add_argument("--expected-main-sha", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--host-preflight", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        out = (apply(args.expected_main_sha) if args.apply else
               preflight(args.expected_main_sha) if args.host_preflight else
               source_check(args.expected_main_sha))
        print(json.dumps(out, sort_keys=True, separators=(",", ":")))
        return 0
    except Stop as exc:
        print("STOP: " + str(exc), file=sys.stderr)
        return 3
    except Exception:
        print("STOP: unexpected_or_post_mutation_unknown", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
