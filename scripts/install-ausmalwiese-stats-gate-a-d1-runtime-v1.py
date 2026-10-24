#!/usr/bin/env python3
"""Source-only installer for the Ausmalwiese Stats Gate A D1 runtime (#996)."""
from __future__ import annotations

import argparse
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
INSTALL = "/usr/bin/install"
STAT = "/usr/bin/stat"
TEST = "/usr/bin/test"
SHA256SUM = "/usr/bin/sha256sum"

SOURCE_REL = "scripts/ausmalwiese_stats_gate_a_d1_runtime_v1.py"
SOURCE_BLOB = "dde75bb1566ecdceaf146c80aa21fc60e0c70d7a"
TARGET = "/usr/local/sbin/rpi5-ausmalwiese-stats-gate-a-d1-migrate"
CONFIRM = "INSTALL-AUSMALWIESE-STATS-GATE-A-D1-RUNTIME"
UPGRADE_CONFIRM = "UPGRADE-AUSMALWIESE-STATS-GATE-A-D1-RUNTIME"
OLD_SOURCE_REF = "936760d99b2fbb492a0a0fabee0fcc7e27377ae8"
OLD_SOURCE_BLOB = "d1191e913e565965dc1c4d153179f702bf2a79d4"
# The exact installed runtime identified by #996 read-only classification. No arbitrary predecessor.
CURRENT_SOURCE_REF = "65acff4a644fe685db880c46aedca93ead56f241"
CURRENT_OLD_BLOB = "be8f6604b432e08d2877fc126a91fa88adbe749e"
UPGRADE_SOURCES = {
    OLD_SOURCE_BLOB: OLD_SOURCE_REF,
    CURRENT_OLD_BLOB: CURRENT_SOURCE_REF,
}
PARENTS = ("/usr", "/usr/local", "/usr/local/sbin")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
MAX_SOURCE = 196608


class Stop(Exception):
    pass


def invoke(argv, *, runner=subprocess.run, stdin=None, timeout=25):
    try:
        return runner(
            list(argv),
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env=CLEAN_ENV,
        )
    except Exception:
        raise Stop("command_unavailable") from None


def output(argv, *, runner=subprocess.run, max_bytes=262144):
    result = invoke(argv, runner=runner)
    if (
        result.returncode
        or type(result.stdout) is not bytes
        or len(result.stdout) > max_bytes
    ):
        raise Stop("preflight_command_failed")
    return result.stdout


def git(args, *, runner=subprocess.run) -> bytes:
    return output([GIT, "-C", str(ROOT), *args], runner=runner)


def git_text(args, *, runner=subprocess.run) -> str:
    try:
        return git(args, runner=runner).decode("ascii").strip()
    except UnicodeError:
        raise Stop("git_output_invalid") from None


def exact_checkout(expected_main, *, runner=subprocess.run) -> None:
    if os.geteuid() == 0:
        raise Stop("must_run_unprivileged")
    if not isinstance(expected_main, str) or SHA40.fullmatch(expected_main) is None:
        raise Stop("expected_main_invalid")
    if git_text(["rev-parse", "--show-toplevel"], runner=runner) != str(ROOT):
        raise Stop("checkout_invalid")
    if git_text(
        ["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner
    ) != "main":
        raise Stop("branch_invalid")
    if git_text(["rev-parse", "HEAD"], runner=runner) != expected_main:
        raise Stop("main_drift")
    if git(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        runner=runner,
    ):
        raise Stop("dirty_checkout")
    origin = git_text(["remote", "get-url", "origin"], runner=runner).rstrip("/")
    https_ok = origin in {
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
    }
    user, sep, remainder = origin.partition("@")
    host, colon, project = remainder.partition(":") if sep else ("", "", "")
    ssh_ok = (
        user == "git"
        and sep == "@"
        and host == "github.com"
        and colon == ":"
        and project in {
            "rozkalnsandris/RPi5_main",
            "rozkalnsandris/RPi5_main.git",
        }
    )
    if not (https_ok or ssh_ok):
        raise Stop("untrusted_origin")


def tracked_runtime(*, runner=subprocess.run) -> bytes:
    path = ROOT / SOURCE_REL
    try:
        info = path.lstat()
        raw = path.read_bytes()
    except OSError:
        raise Stop("runtime_source_unavailable") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or not 0 < info.st_size <= MAX_SOURCE
    ):
        raise Stop("runtime_source_invalid")
    canonical = git(["show", "HEAD:" + SOURCE_REL], runner=runner)
    tree = git_text(["ls-tree", "HEAD", "--", SOURCE_REL], runner=runner)
    if (
        raw != canonical
        or tree != f"100644 blob {SOURCE_BLOB}\t{SOURCE_REL}"
    ):
        raise Stop("runtime_source_mismatch")
    return raw


def historical_runtime(old_source_blob=OLD_SOURCE_BLOB, *, runner=subprocess.run) -> bytes:
    ref = UPGRADE_SOURCES.get(old_source_blob)
    if ref is None:
        raise Stop("invalid_upgrade_source")
    raw = git(["show", ref + ":" + SOURCE_REL], runner=runner)
    tree = git_text(["ls-tree", ref, "--", SOURCE_REL], runner=runner)
    if (
        not 0 < len(raw) <= MAX_SOURCE
        or tree != f"100644 blob {old_source_blob}\t{SOURCE_REL}"
    ):
        raise Stop("old_runtime_source_mismatch")
    return raw


def sudo_metadata(args, *, runner=subprocess.run) -> str:
    try:
        return output(
            [SUDO, "-n", *args], runner=runner, max_bytes=1024
        ).decode("ascii").strip()
    except UnicodeError:
        raise Stop("sudo_metadata_invalid") from None


def absent(*, runner=subprocess.run) -> None:
    for option in ("-e", "-L"):
        result = invoke([SUDO, "-n", TEST, option, TARGET], runner=runner)
        if result.returncode == 0:
            raise Stop("target_exists")
        if result.returncode != 1:
            raise Stop("target_absence_unknown")


def cp_copy_options(version: str) -> tuple[str, ...]:
    header = version.split("\n", 1)[0]
    match = re.fullmatch(
        r"cp \(GNU coreutils\) ([0-9]+)\.([0-9]+)(?:\.[0-9]+)?",
        header,
    )
    if not match:
        raise Stop("cp_atomic_capability_unverified")
    major, minor = map(int, match.groups())
    if (major, minor) == (9, 1):
        return ("--no-clobber", "--verbose")
    if (major, minor) >= (9, 6):
        return ("--update=none-fail",)
    raise Stop("cp_atomic_capability_unverified")


def cp_command(version: str) -> list[str]:
    return [
        CP,
        *cp_copy_options(version),
        "--preserve=mode",
        "-T",
        "--",
        "/dev/stdin",
        TARGET,
    ]


def root_preflight(*, runner=subprocess.run) -> list[str]:
    version = sudo_metadata([CP, "--version"], runner=runner)
    command = cp_command(version)
    for path in PARENTS:
        value = sudo_metadata(
            [STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner
        )
        parts = value.split(":")
        if (
            len(parts) != 4
            or parts[:2] != ["0", "0"]
            or parts[3] != "directory"
        ):
            raise Stop("unsafe_parent")
        try:
            mode = int(parts[2], 8)
        except ValueError:
            raise Stop("unsafe_parent") from None
        if mode & 0o022 or mode & 0o700 != 0o700:
            raise Stop("unsafe_parent")
    absent(runner=runner)
    if invoke([SUDO, "-n", "-l", "--", *command], runner=runner).returncode:
        raise Stop("sudo_exact_copy_not_allowed")
    return command


def upgrade_command() -> list[str]:
    return [
        INSTALL,
        "-T",
        "-o",
        "root",
        "-g",
        "root",
        "-m",
        "0500",
        "--",
        "/dev/stdin",
        TARGET,
    ]


def upgrade_root_preflight(old_payload: bytes, *, runner=subprocess.run) -> list[str]:
    for path in PARENTS:
        value = sudo_metadata(
            [STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner
        )
        parts = value.split(":")
        if (
            len(parts) != 4
            or parts[:2] != ["0", "0"]
            or parts[3] != "directory"
        ):
            raise Stop("unsafe_parent")
        try:
            mode = int(parts[2], 8)
        except ValueError:
            raise Stop("unsafe_parent") from None
        if mode & 0o022 or mode & 0o700 != 0o700:
            raise Stop("unsafe_parent")

    symlink = invoke([SUDO, "-n", TEST, "-L", TARGET], runner=runner)
    if symlink.returncode == 0:
        raise Stop("upgrade_target_symlink")
    if symlink.returncode != 1:
        raise Stop("upgrade_target_unknown")

    metadata = sudo_metadata(
        [STAT, "-c", "%u:%g:%a:%F:%h", "--", TARGET],
        runner=runner,
    )
    if metadata != "0:0:500:regular file:1":
        raise Stop("upgrade_target_metadata_mismatch")

    checksum = sudo_metadata([SHA256SUM, "--", TARGET], runner=runner)
    digest = hashlib.sha256(old_payload).hexdigest()
    if checksum != digest + "  " + TARGET:
        raise Stop("upgrade_target_digest_mismatch")

    command = upgrade_command()
    if invoke([SUDO, "-n", "-l", "--", *command], runner=runner).returncode:
        raise Stop("sudo_exact_upgrade_not_allowed")
    return command


def upgrade_preflight(expected_main, old_source_blob, *, runner=subprocess.run) -> bytes:
    if old_source_blob not in UPGRADE_SOURCES:
        raise Stop("invalid_upgrade_source")
    exact_checkout(expected_main, runner=runner)
    payload = tracked_runtime(runner=runner)
    old_payload = historical_runtime(old_source_blob, runner=runner)
    upgrade_root_preflight(old_payload, runner=runner)
    return payload


def sealed_memfd(data: bytes) -> int:
    fd = -1
    try:
        fd = os.memfd_create(
            "ausmalwiese-stats-gate-a-d1-runtime",
            os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
        )
        if os.write(fd, data) != len(data):
            raise Stop("memfd_invalid")
        os.fchmod(fd, 0o500)
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(
            fd,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_WRITE
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_SEAL,
        )
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o500
            or info.st_size != len(data)
        ):
            raise Stop("memfd_invalid")
        return fd
    except Exception:
        if fd >= 0:
            os.close(fd)
        raise Stop("memfd_unavailable") from None


def prove_copy(result, options: tuple[str, ...]) -> None:
    if (
        result.returncode
        or type(result.stdout) is not bytes
        or len(result.stdout) > 512
    ):
        raise Stop("post_dispatch_unknown_state")
    if options == ("--no-clobber", "--verbose"):
        expected = ("'/dev/stdin' -> '" + TARGET + "'\n").encode("ascii")
        if result.stdout != expected:
            raise Stop("post_dispatch_unknown_state")
    elif options != ("--update=none-fail",):
        raise Stop("post_dispatch_unknown_state")


def post_verify(payload: bytes, *, runner=subprocess.run) -> None:
    metadata = sudo_metadata(
        [STAT, "-c", "%u:%g:%a:%F:%h", "--", TARGET],
        runner=runner,
    )
    if metadata != "0:0:500:regular file:1":
        raise Stop("post_verify_metadata_mismatch")
    digest = hashlib.sha256(payload).hexdigest()
    checksum = sudo_metadata([SHA256SUM, "--", TARGET], runner=runner)
    if checksum != digest + "  " + TARGET:
        raise Stop("post_verify_hash_mismatch")


def preflight(expected_main, *, runner=subprocess.run) -> bytes:
    exact_checkout(expected_main, runner=runner)
    payload = tracked_runtime(runner=runner)
    root_preflight(runner=runner)
    return payload


def apply(expected_main, *, runner=subprocess.run) -> None:
    payload = preflight(expected_main, runner=runner)
    fd = sealed_memfd(payload)
    try:
        exact_checkout(expected_main, runner=runner)
        command = root_preflight(runner=runner)
        options = tuple(command[1:-5])
        try:
            result = invoke(
                [SUDO, "-n", *command],
                runner=runner,
                stdin=fd,
                timeout=35,
            )
            prove_copy(result, options)
            post_verify(payload, runner=runner)
        except Exception:
            raise Stop("post_dispatch_unknown_state") from None
    finally:
        os.close(fd)


def upgrade(expected_main, old_source_blob, *, runner=subprocess.run) -> None:
    payload = upgrade_preflight(expected_main, old_source_blob, runner=runner)
    fd = sealed_memfd(payload)
    try:
        exact_checkout(expected_main, runner=runner)
        old_payload = historical_runtime(old_source_blob, runner=runner)
        command = upgrade_root_preflight(old_payload, runner=runner)
        try:
            result = invoke(
                [SUDO, "-n", *command],
                runner=runner,
                stdin=fd,
                timeout=35,
            )
            if result.returncode:
                raise Stop("post_dispatch_unknown_state")
            post_verify(payload, runner=runner)
        except Exception:
            raise Stop("post_dispatch_unknown_state") from None
    finally:
        os.close(fd)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--upgrade-from", default="")
    args = parser.parse_args(argv)
    try:
        if args.upgrade_from:
            if args.upgrade_from not in UPGRADE_SOURCES:
                raise Stop("invalid_upgrade_source")
            if args.apply:
                if args.confirm != UPGRADE_CONFIRM:
                    raise Stop("confirmation_missing")
                upgrade(args.expected_main, args.upgrade_from)
                result = {
                    "status": "PASS",
                    "operation": "upgrade",
                    "mutation_started": True,
                }
            else:
                if args.confirm:
                    raise Stop("confirm_requires_apply")
                raw = upgrade_preflight(args.expected_main, args.upgrade_from)
                result = {
                    "status": "UPGRADE_PREFLIGHT_PASS",
                    "mutation_started": False,
                    "old_runtime_blob": args.upgrade_from,
                    "runtime_sha256": hashlib.sha256(raw).hexdigest(),
                }
        elif args.apply:
            if args.confirm != CONFIRM:
                raise Stop("confirmation_missing")
            apply(args.expected_main)
            result = {"status": "PASS", "mutation_started": True}
        else:
            if args.confirm:
                raise Stop("confirm_requires_apply")
            raw = preflight(args.expected_main)
            result = {
                "status": "PREFLIGHT_PASS",
                "mutation_started": False,
                "runtime_sha256": hashlib.sha256(raw).hexdigest(),
            }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Stop as exc:
        after = str(exc) == "post_dispatch_unknown_state"
        print(
            json.dumps(
                {
                    "status": "STOP_ERROR" if after else "BLOCKED",
                    "reason": str(exc),
                    "mutation_state": "unknown" if after else "not_started",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 4 if after else 3


if __name__ == "__main__":
    sys.exit(main())
