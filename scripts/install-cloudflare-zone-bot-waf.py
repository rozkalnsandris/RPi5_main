#!/usr/bin/env python3
"""Source-only, exact-release installer for the independent zone WAF operator.

Default mode is read-only. Applying is separately owner-gated and intentionally
does not install sudoers, credentials, or any Cloudflare rule.
"""
from __future__ import annotations

import argparse
import base64
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
SOURCE = ROOT / "scripts/cloudflare_zone_bot_waf.py"
SOURCE_REL = "scripts/cloudflare_zone_bot_waf.py"
INSTALLED = "/usr/local/sbin/rpi5-cloudflare-zone-bot-waf"
RELEASE_DIR = "/usr/local/libexec/rpi5-cloudflare-zone-bot-waf"
RELEASE = RELEASE_DIR + "/release.json"
EXPECTED_CONFIRM = "INSTALL-ROZKALNS-ZONE-BOT-WAF"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
PYTHON = "/usr/bin/python3"

# Fixed root helper, no external arguments selecting paths, modes or actions.
# One gated call may create exactly one directory and two exclusive files.
# After dispatch, any error is STOP; never clean, retry, overwrite or roll back.
ROOT_INSTALL_WRITER = r"""
import base64
import hashlib
import json
import os
import re
import stat
import sys

operator = "/usr/local/sbin/rpi5-cloudflare-zone-bot-waf"
release_dir = "/usr/local/libexec/rpi5-cloudflare-zone-bot-waf"
release = release_dir + "/release.json"

def absent(path):
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    raise SystemExit(31)

def safe_parent(path):
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_gid != 0:
        raise SystemExit(32)
    if stat.S_IMODE(st.st_mode) & 0o022:
        raise SystemExit(33)

def exclusive(path, data, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            amount = os.write(fd, view)
            if amount < 1:
                raise OSError("short write")
            view = view[amount:]
        os.fsync(fd)
    finally:
        os.close(fd)

safe_parent("/usr/local/sbin")
safe_parent("/usr/local/libexec")
absent(operator)
absent(release_dir)
absent(release)
raw = sys.stdin.buffer.read(262145)
if len(raw) > 262144:
    raise SystemExit(34)
doc = json.loads(raw.decode("utf-8"))
if set(doc) != {"source_b64", "metadata_b64"}:
    raise SystemExit(35)
source = base64.b64decode(doc["source_b64"], validate=True)
metadata = base64.b64decode(doc["metadata_b64"], validate=True)
if not source or len(source) > 131072 or not metadata or len(metadata) > 8192:
    raise SystemExit(36)
release_json = json.loads(metadata.decode("utf-8"))
if set(release_json) != {"source_sha", "operator_sha256"}:
    raise SystemExit(37)
if not re.fullmatch(r"[0-9a-f]{40}", release_json["source_sha"]):
    raise SystemExit(38)
if hashlib.sha256(source).hexdigest() != release_json["operator_sha256"]:
    raise SystemExit(39)

# FIRST MUTATION: one dedicated release directory (no parent directory changes).
os.mkdir(release_dir, 0o700)
os.chmod(release_dir, 0o700)
exclusive(operator, source, 0o500)
exclusive(release, metadata, 0o400)

for path, mode, digest in (
    (operator, 0o500, hashlib.sha256(source).hexdigest()),
    (release, 0o400, hashlib.sha256(metadata).hexdigest()),
):
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_gid != 0:
        raise SystemExit(40)
    if stat.S_IMODE(st.st_mode) != mode:
        raise SystemExit(41)
    with open(path, "rb") as handle:
        if hashlib.sha256(handle.read(131073)).hexdigest() != digest:
            raise SystemExit(42)
st = os.lstat(release_dir)
if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o700:
    raise SystemExit(43)
print('{"status":"installed","files_verified":2}')
"""


class InstallError(Exception):
    pass


def run(argv: list[str], *, input_bytes: bytes | None = None, runner: Callable = subprocess.run):
    return runner(argv, input=input_bytes, stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE, check=False)


def git(args: list[str], *, runner: Callable = subprocess.run) -> str:
    result = run([GIT, "-C", str(ROOT), *args], runner=runner)
    if result.returncode != 0:
        raise InstallError("git_preflight_failed")
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise InstallError("git_output_invalid") from None


def checked_source(expected_main: str, *, runner: Callable = subprocess.run) -> bytes:
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


def require_targets_absent(*, runner: Callable = subprocess.run):
    available = run([SUDO, "-n", "/usr/bin/true"], runner=runner)
    if available.returncode != 0:
        raise InstallError("sudo_unavailable")
    for path in (INSTALLED, RELEASE_DIR, RELEASE):
        # -e does not detect dangling symlinks; combine with -L.
        for flag in ("-e", "-L"):
            result = run([SUDO, "-n", "/usr/bin/test", flag, path], runner=runner)
            if result.returncode == 0:
                raise InstallError("target_already_exists")
            if result.returncode != 1:
                raise InstallError("target_check_failed")


def preflight(expected_main: str, *, runner: Callable = subprocess.run) -> tuple[bytes, bytes]:
    source = checked_source(expected_main, runner=runner)
    require_targets_absent(runner=runner)
    return source, metadata_for(expected_main, source)


def install(expected_main: str, *, runner: Callable = subprocess.run):
    source, metadata = preflight(expected_main, runner=runner)
    data = (json.dumps({"source_b64": base64.b64encode(source).decode(),
                        "metadata_b64": base64.b64encode(metadata).decode()},
                       separators=(",", ":")) + "\n").encode()
    # Mutation dispatch: caller must STOP on any return code or ambiguity.
    try:
        result = run([SUDO, "-n", PYTHON, "-c", ROOT_INSTALL_WRITER],
                     input_bytes=data, runner=runner)
    except Exception:
        raise InstallError("post_dispatch_unknown_state") from None
    if result.returncode != 0:
        raise InstallError("post_dispatch_unknown_state")
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise InstallError("post_dispatch_unknown_state") from None
    if payload != {"status": "installed", "files_verified": 2}:
        raise InstallError("post_dispatch_unknown_state")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expected-main", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm", default="")
    args = p.parse_args(argv)
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
                          "reason": str(exc), "mutation_state": "unknown" if unknown else "not_started"}))
        return 4 if unknown else 3


if __name__ == "__main__":
    sys.exit(main())
