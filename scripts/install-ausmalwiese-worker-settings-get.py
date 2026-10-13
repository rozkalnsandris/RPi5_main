#!/usr/bin/env python3
"""Fixed, source-only, fail-closed Ausmalwiese settings GET release installer.

No privileged repository Python. No secret access or OAuth calls. --apply is
reserved for a future separately owner-authorized one-shot LIVE installation.
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

ROOT = Path(__file__).resolve().parents[1]
GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
TRUE = "/usr/bin/true"
STAT = "/usr/bin/stat"
TEST = "/usr/bin/test"
MKDIR = "/usr/bin/mkdir"
INSTALL = "/usr/bin/install"
SHA256SUM = "/usr/bin/sha256sum"

REPO = "rozkalnsandris/RPi5_main"
EXECUTOR_REL = "scripts/ausmalwiese_worker_settings_executor.py"
SANITIZER_REL = "scripts/ausmalwiese_worker_settings_get.py"
BINDING_REL = "ops/contracts/ausmalwiese-worker-settings-account-binding-v1.json"
EXECUTOR = "/usr/local/sbin/rpi5-ausmalwiese-worker-settings-get"
RELEASE_DIR = "/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get"
SANITIZER = RELEASE_DIR + "/sanitizer.py"
RELEASE = RELEASE_DIR + "/release.json"
PARENTS = ("/usr", "/usr/local", "/usr/local/sbin", "/usr/local/libexec")
TARGETS = (EXECUTOR, RELEASE_DIR, SANITIZER, RELEASE)
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
CONFIRM = "INSTALL-AUSMALWIESE-WORKER-SETTINGS-GET"


class Stop(Exception):
    """Static safe failure classification; never includes upstream output."""


def invoke(argv, *, input_bytes=None, runner=subprocess.run):
    try:
        return runner(list(argv), input=input_bytes, stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE, check=False, timeout=25)
    except Exception:
        raise Stop("command_unavailable") from None


def git(argv, *, runner=subprocess.run) -> bytes:
    p = invoke([GIT, "-C", str(ROOT), *argv], runner=runner)
    if p.returncode:
        raise Stop("git_preflight_failed")
    if type(p.stdout) is not bytes or len(p.stdout) > 262144:
        raise Stop("git_output_invalid")
    return p.stdout


def text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise Stop("git_output_invalid") from None


def checked_checkout(expected_main: str, *, runner=subprocess.run) -> None:
    if os.geteuid() == 0:
        raise Stop("installer_must_be_unprivileged")
    if not isinstance(expected_main, str) or not SHA40.fullmatch(expected_main):
        raise Stop("invalid_expected_main")
    if text(git(["rev-parse", "--show-toplevel"], runner=runner)) != str(ROOT):
        raise Stop("checkout_mismatch")
    if text(git(["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner)) != "main":
        raise Stop("not_main")
    if text(git(["rev-parse", "HEAD"], runner=runner)) != expected_main:
        raise Stop("main_drift")
    if git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], runner=runner):
        raise Stop("dirty_checkout")
    if text(git(["remote", "get-url", "origin"], runner=runner)).rstrip("/") not in (
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
        "git@github.com:rozkalnsandris/RPi5_main",
        "git@github.com:rozkalnsandris/RPi5_main.git",
    ):
        raise Stop("origin_mismatch")


def tracked_snapshot(rel: str, *, runner=subprocess.run, max_size=131072) -> bytes:
    if rel not in {EXECUTOR_REL, SANITIZER_REL, BINDING_REL}:
        raise Stop("source_scope_invalid")
    file = ROOT / rel
    try:
        s = file.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_size < 1 or s.st_size > max_size:
            raise Stop("source_invalid")
        actual = file.read_bytes()
    except OSError:
        raise Stop("source_unreadable") from None
    canonical = git(["show", "HEAD:" + rel], runner=runner)
    if not actual or len(actual) > max_size or canonical != actual:
        raise Stop("source_digest_mismatch")
    return actual


def approved_account_fingerprint(binding_raw: bytes) -> str:
    """Reject until an independently verified SHA-256 is reviewed in git.

    This does not accept, derive, look up or output the account ID or any token.
    """
    try:
        obj = json.loads(binding_raw)
    except (ValueError, UnicodeError):
        raise Stop("account_binding_unverified") from None
    if type(obj) is not dict or set(obj) != {
        "schema_version", "worker", "status", "account_sha256", "verification_evidence"
    }:
        raise Stop("account_binding_unverified")
    digest = obj.get("account_sha256")
    evidence = obj.get("verification_evidence")
    if (obj.get("schema_version") != 1 or obj.get("worker") != "coloring-pages-stats-v1"
        or obj.get("status") != "INDEPENDENTLY_VERIFIED"
        or not isinstance(digest, str) or not SHA64.fullmatch(digest)
        or not isinstance(evidence, str)
        or not re.fullmatch(r"https://github\.com/rozkalnsandris/RPi5_main/issues/[0-9]+#issuecomment-[0-9]+", evidence)):
        raise Stop("account_binding_unverified")
    return digest


def release_bytes(expected_main: str, executor: bytes, sanitizer: bytes, fingerprint: str) -> bytes:
    if not SHA40.fullmatch(expected_main) or not SHA64.fullmatch(fingerprint):
        raise Stop("release_identity_invalid")
    return (json.dumps({
        "schema_version": 1,
        "repository": REPO,
        "source_sha": expected_main,
        "worker": "coloring-pages-stats-v1",
        "executor_sha256": hashlib.sha256(executor).hexdigest(),
        "sanitizer_sha256": hashlib.sha256(sanitizer).hexdigest(),
        "account_sha256": fingerprint,
    }, separators=(",", ":"), sort_keys=True) + "\n").encode("ascii")


def sudo_read(cmd, *, runner=subprocess.run) -> str:
    result = invoke([SUDO, "-n", *cmd], runner=runner)
    if result.returncode:
        raise Stop("sudo_preflight_failed")
    if type(result.stdout) is not bytes or len(result.stdout) > 256:
        raise Stop("sudo_metadata_invalid")
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        raise Stop("sudo_metadata_invalid") from None


def absent(path: str, *, runner=subprocess.run) -> None:
    for flag in ("-e", "-L"):
        result = invoke([SUDO, "-n", TEST, flag, path], runner=runner)
        if result.returncode == 0:
            raise Stop("target_already_exists")
        if result.returncode != 1:
            raise Stop("target_preflight_failed")


def roots_preflight(*, runner=subprocess.run) -> None:
    sudo_read([TRUE], runner=runner)
    for path in PARENTS:
        value = sudo_read([STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner)
        parts = value.split(":")
        if len(parts) != 4 or parts[0:2] != ["0", "0"] or parts[3] != "directory":
            raise Stop("unsafe_parent")
        try:
            mode = int(parts[2], 8)
        except ValueError:
            raise Stop("unsafe_parent") from None
        if mode & 0o022 or mode & 0o700 != 0o700:
            raise Stop("unsafe_parent")
    for path in TARGETS:
        absent(path, runner=runner)


def preflight(expected_main: str, *, runner=subprocess.run):
    checked_checkout(expected_main, runner=runner)
    executor = tracked_snapshot(EXECUTOR_REL, runner=runner)
    sanitizer = tracked_snapshot(SANITIZER_REL, runner=runner, max_size=65536)
    binding = tracked_snapshot(BINDING_REL, runner=runner, max_size=8192)
    fingerprint = approved_account_fingerprint(binding)
    metadata = release_bytes(expected_main, executor, sanitizer, fingerprint)
    roots_preflight(runner=runner)
    return executor, sanitizer, metadata


def write_once(args, data=None, *, runner=subprocess.run):
    """Only fixed coreutils. Any failure after dispatch is terminal."""
    try:
        result = invoke([SUDO, "-n", *args], input_bytes=data, runner=runner)
        if result.returncode:
            raise Stop("post_dispatch_unknown_state")
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def post_verify(files, *, runner=subprocess.run):
    for path, mode, payload in files:
        value = sudo_read([STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner)
        kind = "directory" if payload is None else "regular file"
        if value != f"0:0:{mode}:{kind}":
            raise Stop("post_verify_metadata_mismatch")
        if payload is not None:
            digest = hashlib.sha256(payload).hexdigest()
            checksum = sudo_read([SHA256SUM, "--", path], runner=runner)
            if checksum != f"{digest}  {path}":
                raise Stop("post_verify_digest_mismatch")


def apply(expected_main: str, *, runner=subprocess.run):
    executable, sanitizer, metadata = preflight(expected_main, runner=runner)
    # First dispatched sudo mkdir is the FIRST HOST MUTATION. No auto recovery.
    try:
        write_once([MKDIR, "-m", "0700", "--", RELEASE_DIR], runner=runner)
        write_once([INSTALL, "-T", "-o", "root", "-g", "root", "-m",
                    "0500", "--", "/dev/stdin", EXECUTOR], executable, runner=runner)
        write_once([INSTALL, "-T", "-o", "root", "-g", "root", "-m",
                    "0400", "--", "/dev/stdin", SANITIZER], sanitizer, runner=runner)
        write_once([INSTALL, "-T", "-o", "root", "-g", "root", "-m",
                    "0400", "--", "/dev/stdin", RELEASE], metadata, runner=runner)
        post_verify(((RELEASE_DIR, "700", None), (EXECUTOR, "500", executable),
                     (SANITIZER, "400", sanitizer), (RELEASE, "400", metadata)),
                    runner=runner)
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
                raise Stop("confirmation_missing")
            apply(args.expected_main)
            print(json.dumps({"status": "PASS", "mutation_started": True}))
        else:
            if args.confirm:
                raise Stop("confirmation_requires_apply")
            executable, sanitizer, metadata = preflight(args.expected_main)
            print(json.dumps({"status": "PREFLIGHT_PASS", "mutation_started": False,
                              "executor_sha256": hashlib.sha256(executable).hexdigest(),
                              "sanitizer_sha256": hashlib.sha256(sanitizer).hexdigest()}))
        return 0
    except Stop as exc:
        is_unknown = str(exc) == "post_dispatch_unknown_state"
        print(json.dumps({"status": "STOP_ERROR" if is_unknown else "BLOCKED",
                          "reason": str(exc),
                          "mutation_state": "unknown" if is_unknown else "not_started"}))
        return 4 if is_unknown else 3


if __name__ == "__main__":
    sys.exit(main())
