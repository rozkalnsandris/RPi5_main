#!/usr/bin/env python3
"""SOURCE ONLY: future installer for the fixed legacy redirect write runtime.

No credential is read, created or modified. No Cloudflare request is made.
Repository execution is unprivileged; root writes use fixed sudo commands only
after exact-main/clean-source and target-absence preflight.
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
LAUNCHER_REL = "scripts/ausmalwiese_redirect_write_runtime_v1.py"
PROVISIONER_REL = "scripts/ausmalwiese_redirect_write_provisioner_v1.py"
INVENTORY_REL = "scripts/ausmalwiese_redirect_inventory.py"
ADAPTER_REL = "scripts/ausmalwiese_redirect_get_adapter.py"
WRITE_REL = "scripts/ausmalwiese_redirect_write_v1.py"
SOURCE_PATHS = (
    LAUNCHER_REL,
    PROVISIONER_REL,
    INVENTORY_REL,
    ADAPTER_REL,
    WRITE_REL,
)
GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
STAT = "/usr/bin/stat"
TEST = "/usr/bin/test"
TRUE = "/usr/bin/true"
MKDIR = "/usr/bin/mkdir"
INSTALL = "/usr/bin/install"
SHA256SUM = "/usr/bin/sha256sum"
EXE = "/usr/local/sbin/rpi5-ausmalwiese-redirect-write"
PROVISION = "/usr/local/sbin/rpi5-ausmalwiese-redirect-write-provision"
LIB = "/usr/local/libexec/rpi5-ausmalwiese-redirect-write"
INV = LIB + "/inventory.py"
ADAPT = LIB + "/adapter.py"
WRITE = LIB + "/write.py"
RELEASE = LIB + "/release.json"
PARENTS = ("/usr", "/usr/local", "/usr/local/sbin", "/usr/local/libexec")
TARGETS = (EXE, PROVISION, LIB, INV, ADAPT, WRITE, RELEASE)
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
CONFIRM = "INSTALL-AUSMALWIESE-REDIRECT-WRITE-RUNTIME"
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


class Stop(Exception):
    """Stable non-sensitive installer failure."""


def invoke(argv, data=None, *, runner=subprocess.run, timeout=25):
    try:
        return runner(
            list(argv),
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env=CLEAN_ENV,
        )
    except Exception:
        raise Stop("command_unavailable") from None


def git(args, *, runner=subprocess.run) -> bytes:
    result = invoke([GIT, "-C", str(SOURCE_ROOT), *args], runner=runner)
    if (
        result.returncode != 0
        or type(result.stdout) is not bytes
        or len(result.stdout) > 524288
    ):
        raise Stop("git_preflight_failed")
    return result.stdout


def text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8").strip()
    except UnicodeError:
        raise Stop("git_output_invalid") from None


def checkout(expected_main: str, *, runner=subprocess.run) -> None:
    if os.geteuid() == 0:
        raise Stop("must_be_unprivileged")
    if not isinstance(expected_main, str) or SHA40.fullmatch(expected_main) is None:
        raise Stop("expected_main_invalid")
    if text(git(["rev-parse", "--show-toplevel"], runner=runner)) != str(SOURCE_ROOT):
        raise Stop("checkout_mismatch")
    if text(git(["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner)) != "main":
        raise Stop("not_main")
    if text(git(["rev-parse", "HEAD"], runner=runner)) != expected_main:
        raise Stop("main_drift")
    if git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], runner=runner):
        raise Stop("dirty_checkout")
    origin = text(git(["remote", "get-url", "origin"], runner=runner)).rstrip("/")
    https_ok = origin in (
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
    )
    user, sep, remote = origin.partition("@")
    host, colon, project = remote.partition(":") if sep else ("", "", "")
    ssh_ok = (
        user == "git"
        and sep == "@"
        and host == "github.com"
        and colon == ":"
        and project in ("rozkalnsandris/RPi5_main", "rozkalnsandris/RPi5_main.git")
    )
    if not (https_ok or ssh_ok):
        raise Stop("origin_mismatch")


def tracked(rel: str, *, runner=subprocess.run) -> bytes:
    if rel not in SOURCE_PATHS:
        raise Stop("path_scope_invalid")
    path = SOURCE_ROOT / rel
    try:
        info = path.lstat()
        raw = path.read_bytes()
    except OSError:
        raise Stop("source_unavailable") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or not 0 < info.st_size <= 196608
        or raw != git(["show", "HEAD:" + rel], runner=runner)
    ):
        raise Stop("source_identity_mismatch")
    return raw


def release_bytes(expected_main: str, payloads: tuple[bytes, ...]) -> bytes:
    if len(payloads) != len(SOURCE_PATHS):
        raise Stop("release_shape_invalid")
    keys = (
        "launcher_sha256",
        "provisioner_sha256",
        "inventory_sha256",
        "adapter_sha256",
        "write_sha256",
    )
    record = {
        "schema_version": 1,
        "repository": REPO,
        "source_sha": expected_main,
        "zone_name": "rozkalns.net",
    }
    record.update({
        key: hashlib.sha256(raw).hexdigest()
        for key, raw in zip(keys, payloads)
    })
    return (
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sudo_read(args, *, runner=subprocess.run) -> str:
    result = invoke([SUDO, "-n", *args], runner=runner)
    if result.returncode or type(result.stdout) is not bytes or len(result.stdout) > 512:
        raise Stop("sudo_read_failed")
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeError:
        raise Stop("sudo_read_failed") from None


def host_preflight(*, runner=subprocess.run) -> None:
    sudo_read([TRUE], runner=runner)
    for path in PARENTS:
        value = sudo_read([STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner)
        parts = value.split(":")
        if len(parts) != 4 or parts[:2] != ["0", "0"] or parts[3] != "directory":
            raise Stop("unsafe_parent")
        try:
            mode = int(parts[2], 8)
        except ValueError:
            raise Stop("unsafe_parent") from None
        if mode & 0o022:
            raise Stop("unsafe_parent")
    for path in TARGETS:
        for flag in ("-e", "-L"):
            result = invoke([SUDO, "-n", TEST, flag, path], runner=runner)
            if result.returncode == 0:
                raise Stop("target_already_exists")
            if result.returncode != 1:
                raise Stop("target_state_unknown")


def preflight(expected_main: str, *, runner=subprocess.run):
    checkout(expected_main, runner=runner)
    payloads = tuple(tracked(path, runner=runner) for path in SOURCE_PATHS)
    release = release_bytes(expected_main, payloads)
    host_preflight(runner=runner)
    return (*payloads, release)


def write_once(args, payload=None, *, runner=subprocess.run) -> None:
    result = invoke([SUDO, "-n", *args], payload, runner=runner)
    if result.returncode != 0:
        raise Stop("post_dispatch_unknown_state")


def post_verify(entries, *, runner=subprocess.run) -> None:
    for path, mode, payload in entries:
        value = sudo_read(
            [STAT, "-c", "%u:%g:%a:%F:%h", "--", path],
            runner=runner,
        )
        if payload is None:
            if value.split(":")[:4] != ["0", "0", mode, "directory"]:
                raise Stop("post_dispatch_unknown_state")
            continue
        if value != f"0:0:{mode}:regular file:1":
            raise Stop("post_dispatch_unknown_state")
        digest = hashlib.sha256(payload).hexdigest()
        observed = sudo_read([SHA256SUM, "--", path], runner=runner)
        if observed != f"{digest}  {path}":
            raise Stop("post_dispatch_unknown_state")


def apply(expected_main: str, *, runner=subprocess.run) -> None:
    launcher, provisioner, inventory, adapter, write, release = preflight(
        expected_main, runner=runner
    )
    files = (
        (EXE, "500", launcher),
        (PROVISION, "500", provisioner),
        (INV, "400", inventory),
        (ADAPT, "400", adapter),
        (WRITE, "400", write),
        (RELEASE, "400", release),
    )
    # First host mutation is mkdir. Any ambiguity after this point is terminal.
    try:
        write_once([MKDIR, "-m", "0700", "--", LIB], runner=runner)
        for path, mode, payload in files:
            write_once(
                [
                    INSTALL, "-T", "-o", "root", "-g", "root",
                    "-m", "0" + mode, "--", "/dev/stdin", path,
                ],
                payload,
                runner=runner,
            )
        post_verify(((LIB, "700", None), *files), runner=runner)
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Source-only redirect write runtime installer")
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            if args.confirm != CONFIRM:
                raise Stop("confirmation_missing")
            apply(args.expected_main)
            result = {"status": "PASS", "mutation_started": True}
        else:
            if args.confirm:
                raise Stop("confirm_requires_apply")
            values = preflight(args.expected_main)
            result = {
                "status": "PREFLIGHT_PASS",
                "mutation_started": False,
                "release_sha256": hashlib.sha256(values[-1]).hexdigest(),
            }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Stop as exc:
        uncertain = str(exc) == "post_dispatch_unknown_state"
        print(json.dumps({
            "status": "STOP_ERROR" if uncertain else "BLOCKED",
            "reason": str(exc),
            "mutation_state": "unknown" if uncertain else "not_started",
        }, sort_keys=True, separators=(",", ":")))
        return 4 if uncertain else 3


if __name__ == "__main__":
    raise SystemExit(main())
