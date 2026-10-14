#!/usr/bin/env python3
"""SOURCE ONLY — future fixed root-owned private TTY helper installer (#1011).

Never run repository Python as root. No secret/Cloudflare access. This source
does NOT grant permission to execute --apply on any host.
"""
from __future__ import annotations

import argparse
import ast
import fcntl
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
CP = "/usr/bin/cp"
STAT = "/usr/bin/stat"
TEST = "/usr/bin/test"
SHA256SUM = "/usr/bin/sha256sum"
SOURCE_REL = "scripts/ausmalwiese_worker_settings_provisioner.py"
TARGET = "/usr/local/sbin/rpi5-ausmalwiese-worker-settings-provision"
PARENTS = ("/usr", "/usr/local", "/usr/local/sbin")
WORKER = "coloring-pages-stats-v1"
ACCOUNT_DIGEST = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
GET_RELEASE = "6c55e46d43889fed2a17770d0f466c79b1db736a"
CREDENTIAL_PATH = "/etc/rpi5-secrets/cloudflare/ausmalwiese-worker-settings-read.json"
CONFIRM = "INSTALL-AUSMALWIESE-PRIVATE-TTY-HELPER"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
MAX_SOURCE = 131072


class Stop(Exception):
    """A static, never-secret, failure classification."""


def invoke(argv, *, runner=subprocess.run, stdin=None, timeout=25):
    try:
        return runner(list(argv), stdin=stdin, stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE, check=False, timeout=timeout,
                      env=CLEAN_ENV)
    except Exception:
        raise Stop("command_unavailable") from None


def command_output(argv, *, runner=subprocess.run, max_bytes=262144):
    p = invoke(argv, runner=runner)
    if p.returncode or type(p.stdout) is not bytes or len(p.stdout) > max_bytes:
        raise Stop("preflight_command_failed")
    return p.stdout


def git(args, *, runner=subprocess.run):
    return command_output([GIT, "-C", str(ROOT), *args], runner=runner)


def git_text(args, *, runner=subprocess.run):
    try:
        return git(args, runner=runner).decode("ascii").strip()
    except UnicodeError:
        raise Stop("git_output_invalid") from None


def exact_checkout(expected_main, *, runner=subprocess.run):
    if os.geteuid() == 0:
        raise Stop("must_run_unprivileged")
    if not isinstance(expected_main, str) or not SHA40.fullmatch(expected_main):
        raise Stop("expected_main_invalid")
    if git_text(["rev-parse", "--show-toplevel"], runner=runner) != str(ROOT):
        raise Stop("checkout_invalid")
    if git_text(["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner) != "main":
        raise Stop("branch_invalid")
    if git_text(["rev-parse", "HEAD"], runner=runner) != expected_main:
        raise Stop("main_drift")
    if git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], runner=runner):
        raise Stop("dirty_checkout")
    origin = git_text(["remote", "get-url", "origin"], runner=runner).rstrip("/")
    https_ok = origin in {
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
    }
    user, sep, remainder = origin.partition("@")
    host, colon, project = remainder.partition(":") if sep else ("", "", "")
    ssh_ok = (user == "git" and sep == "@" and host == "github.com"
              and colon == ":" and project in {
                  "rozkalnsandris/RPi5_main", "rozkalnsandris/RPi5_main.git",
              })
    if not (https_ok or ssh_ok):
        raise Stop("untrusted_origin")


def fixed_source_constants(raw):
    """Parse source without executing untrusted helper Python."""
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=SOURCE_REL)
        obj = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            key = node.targets[0].id
            val = node.value
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                obj[key] = val.value
            elif (isinstance(val, ast.Call) and isinstance(val.func, ast.Name)
                  and val.func.id == "Path" and len(val.args) == 1
                  and isinstance(val.args[0], ast.Constant)
                  and isinstance(val.args[0].value, str) and not val.keywords):
                obj[key] = val.args[0].value
            elif (isinstance(val, ast.BinOp) and isinstance(val.op, ast.Div)
                  and isinstance(val.left, ast.Name)
                  and val.left.id == "DIRECTORY"
                  and isinstance(val.right, ast.Constant)
                  and isinstance(val.right.value, str)):
                obj[key] = obj.get("DIRECTORY", "") + "/" + val.right.value
        pinned = {
            "ENTRY": TARGET, "WORKER": WORKER, "ACCOUNT_SHA256": ACCOUNT_DIGEST,
            "INSTALLED_RELEASE_SHA": GET_RELEASE, "TARGET": CREDENTIAL_PATH,
            "DIRECTORY": "/etc/rpi5-secrets/cloudflare",
            "CONFIRM": "OWNER-AUTHORIZED-ONE-CREDENTIAL-PROVISION",
            "EXECUTOR": "/usr/local/sbin/rpi5-ausmalwiese-worker-settings-get",
            "RELEASE": "/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get/release.json",
        }
        if any(obj.get(k) != v for k, v in pinned.items()):
            raise Stop("helper_identity_mismatch")
        for required in ("trusted_entry", "validated_release", "owner_tty_values",
                         "exclusive_create", "main"):
            if not any(isinstance(n, ast.FunctionDef) and n.name == required for n in tree.body):
                raise Stop("helper_identity_mismatch")
    except (SyntaxError, UnicodeError, ValueError):
        raise Stop("helper_identity_mismatch") from None


def tracked_helper(*, runner=subprocess.run):
    path = ROOT / SOURCE_REL
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_SOURCE or info.st_nlink != 1:
            raise Stop("helper_source_invalid")
        raw = path.read_bytes()
    except OSError:
        raise Stop("helper_source_unavailable") from None
    canonical = git(["show", "HEAD:" + SOURCE_REL], runner=runner)
    if not raw or len(raw) > MAX_SOURCE or raw != canonical:
        raise Stop("helper_source_mismatch")
    fixed_source_constants(raw)
    return raw


def sudo_metadata(args, *, runner=subprocess.run):
    try:
        raw = command_output([SUDO, "-n", *args], runner=runner, max_bytes=1024)
        return raw.decode("ascii").strip()
    except UnicodeError:
        raise Stop("sudo_metadata_invalid") from None


def absent(*, runner=subprocess.run):
    # Includes dangling symlinks; O_EXCL in the future cp is the final guard.
    for option in ("-e", "-L"):
        p = invoke([SUDO, "-n", TEST, option, TARGET], runner=runner)
        if p.returncode == 0:
            raise Stop("target_exists")
        if p.returncode != 1:
            raise Stop("target_absence_unknown")


def root_preflight(*, runner=subprocess.run):
    # Probe the exact bounded future root executable non-mutatively.
    version = sudo_metadata([CP, "--version"], runner=runner)
    header = version.split("\n", 1)[0]
    m = re.fullmatch(r"cp \(GNU coreutils\) ([0-9]+)\.([0-9]+)(?:\.[0-9]+)?", header)
    if not m or tuple(map(int, m.groups())) < (9, 4):
        raise Stop("cp_atomic_capability_unverified")
    for path in PARENTS:
        value = sudo_metadata([STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner)
        parts = value.split(":")
        if len(parts) != 4 or parts[:2] != ["0", "0"] or parts[3] != "directory":
            raise Stop("unsafe_parent")
        try:
            mode = int(parts[2], 8)
        except ValueError:
            raise Stop("unsafe_parent") from None
        if mode & 0o022 or mode & 0o700 != 0o700:
            raise Stop("unsafe_parent")
    absent(runner=runner)
    # Check permission for the exact future sudo cp argv without executing it.
    command = [CP, "--update=none-fail", "--preserve=mode", "-T",
               "--", "/dev/stdin", TARGET]
    result = invoke([SUDO, "-n", "-l", "--", *command], runner=runner)
    if result.returncode:
        raise Stop("sudo_exact_copy_not_allowed")


def preflight(expected_main, *, runner=subprocess.run):
    exact_checkout(expected_main, runner=runner)
    payload = tracked_helper(runner=runner)
    root_preflight(runner=runner)
    return payload


def sealed_memfd(data):
    """Anonymous, nonpersistent, read-only once sealed. Never contains a token."""
    fd = -1
    try:
        fd = os.memfd_create("ausmalwiese-fixed-helper",
                             os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        if os.write(fd, data) != len(data):
            raise Stop("memfd_invalid")
        os.fchmod(fd, 0o500)
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS,
                    fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                    fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode) != 0o500 or s.st_size != len(data):
            raise Stop("memfd_invalid")
        return fd
    except Exception:
        if fd >= 0:
            os.close(fd)
        raise Stop("memfd_unavailable") from None


def post_verify(payload, *, runner=subprocess.run):
    meta = sudo_metadata([STAT, "-c", "%u:%g:%a:%F:%h", "--", TARGET], runner=runner)
    if meta != "0:0:500:regular file:1":
        raise Stop("post_verify_metadata_mismatch")
    digest = hashlib.sha256(payload).hexdigest()
    checksum = sudo_metadata([SHA256SUM, "--", TARGET], runner=runner)
    if checksum != digest + "  " + TARGET:
        raise Stop("post_verify_hash_mismatch")


def apply(expected_main, *, runner=subprocess.run):
    payload = preflight(expected_main, runner=runner)
    memfd = sealed_memfd(payload)
    try:
        # Recheck git and destination before the single root mutation.
        exact_checkout(expected_main, runner=runner)
        absent(runner=runner)
        # GNU cp >=9.4: update=none-fail and O_CREAT|O_EXCL for a new
        # destination; source /dev/stdin is the sealed 0500 memfd, inherited
        # as fd 0. Clean env excludes POSIXLY_CORRECT's symlink fallback.
        # One fixed sudo cp. No repo Python, cleanup, retries or chmod.
        command = [SUDO, "-n", CP, "--update=none-fail",
                   "--preserve=mode", "-T", "--", "/dev/stdin", TARGET]
        try:
            result = invoke(command, runner=runner, stdin=memfd, timeout=35)
            if result.returncode:
                raise Stop("post_dispatch_unknown_state")
            post_verify(payload, runner=runner)
        except Exception:
            raise Stop("post_dispatch_unknown_state") from None
    finally:
        os.close(memfd)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Source-only private TTY helper installer")
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
                raise Stop("confirm_requires_apply")
            raw = preflight(args.expected_main)
            print(json.dumps({"status": "PREFLIGHT_PASS", "mutation_started": False,
                              "helper_sha256": hashlib.sha256(raw).hexdigest()}))
        return 0
    except Stop as exc:
        after = str(exc) == "post_dispatch_unknown_state"
        print(json.dumps({"status": "STOP_ERROR" if after else "BLOCKED",
                          "reason": str(exc),
                          "mutation_state": "unknown" if after else "not_started"}))
        return 4 if after else 3


if __name__ == "__main__":
    sys.exit(main())
