#!/usr/bin/env python3
"""SOURCE ONLY — future installer for the Ausmalwiese report secrets helper.

Never run repository Python as root. No secret file is read. No Cloudflare,
Brevo, Turnstile or Wrangler operation is performed by this source.
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

SOURCE_REL = "scripts/ausmalwiese_report_secrets_provisioner.py"
SOURCE_BLOB = "26a621b1608ae1c378bb274cb53a29fd48c2908c"
INSTALL_TARGET = "/usr/local/sbin/rpi5-ausmalwiese-report-secrets-provision"
PROTECTED_DIRECTORY = "/etc/rpi5-secrets/cloudflare"
PROTECTED_TARGET = PROTECTED_DIRECTORY + "/ausmalwiese-report-wrangler-secrets.json"
WORKER = "coloring-pages-report-v1"
HELPER_CONFIRM = "OWNER-AUTHORIZED-REPORT-SECRETS-PROVISION"
INSTALL_CONFIRM = "INSTALL-AUSMALWIESE-REPORT-SECRETS-PROVISIONER"
SECRET_NAMES = (
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET",
    "BREVO_API_KEY",
    "REPORT_TO",
)
PARENTS = ("/usr", "/usr/local", "/usr/local/sbin")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
MAX_SOURCE = 131072


class Stop(Exception):
    """Fixed non-secret failure classification."""


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


def command_output(argv, *, runner=subprocess.run, max_bytes=262144):
    result = invoke(argv, runner=runner)
    if (
        result.returncode
        or type(result.stdout) is not bytes
        or len(result.stdout) > max_bytes
    ):
        raise Stop("preflight_command_failed")
    return result.stdout


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
    if (
        git_text(["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner)
        != "main"
    ):
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
        and project
        in {
            "rozkalnsandris/RPi5_main",
            "rozkalnsandris/RPi5_main.git",
        }
    )
    if not (https_ok or ssh_ok):
        raise Stop("untrusted_origin")


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw
    ).hexdigest()


def fixed_source_constants(raw: bytes) -> None:
    """Parse the helper without executing it and require the reviewed identity."""
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=SOURCE_REL)
    except (SyntaxError, UnicodeError):
        raise Stop("helper_identity_mismatch") from None

    values: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        key = target.id
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values[key] = value.value
        elif (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "Path"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Constant)
            and isinstance(value.args[0].value, str)
            and not value.keywords
        ):
            values[key] = value.args[0].value
        elif (
            isinstance(value, ast.BinOp)
            and isinstance(value.op, ast.Div)
            and isinstance(value.left, ast.Name)
            and value.left.id == "DIRECTORY"
            and isinstance(value.right, ast.Constant)
            and isinstance(value.right.value, str)
        ):
            directory = values.get("DIRECTORY")
            if isinstance(directory, str):
                values[key] = directory + "/" + value.right.value
        elif isinstance(value, ast.Tuple):
            items = []
            for item in value.elts:
                if not isinstance(item, ast.Constant) or not isinstance(
                    item.value, str
                ):
                    items = []
                    break
                items.append(item.value)
            if items:
                values[key] = tuple(items)

    pinned = {
        "ENTRY": INSTALL_TARGET,
        "DIRECTORY": PROTECTED_DIRECTORY,
        "TARGET": PROTECTED_TARGET,
        "WORKER": WORKER,
        "CONFIRM": HELPER_CONFIRM,
        "SECRET_NAMES": SECRET_NAMES,
    }
    if any(values.get(key) != value for key, value in pinned.items()):
        raise Stop("helper_identity_mismatch")

    functions = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    required = {
        "trusted_entry",
        "guarded_directory",
        "owner_tty_values",
        "secrets_bytes",
        "exclusive_create",
        "run",
        "main",
    }
    if not required.issubset(functions):
        raise Stop("helper_identity_mismatch")


def tracked_helper(*, runner=subprocess.run) -> bytes:
    path = ROOT / SOURCE_REL
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or not 0 < info.st_size <= MAX_SOURCE
            or info.st_nlink != 1
        ):
            raise Stop("helper_source_invalid")
        raw = path.read_bytes()
    except OSError:
        raise Stop("helper_source_unavailable") from None

    canonical = git(["show", "HEAD:" + SOURCE_REL], runner=runner)
    tree_line = git_text(["ls-tree", "HEAD", "--", SOURCE_REL], runner=runner)
    expected_line = f"100644 blob {SOURCE_BLOB}\t{SOURCE_REL}"
    if (
        not raw
        or len(raw) > MAX_SOURCE
        or raw != canonical
        or tree_line != expected_line
        or git_blob(raw) != SOURCE_BLOB
    ):
        raise Stop("helper_source_mismatch")

    fixed_source_constants(raw)
    return raw


def sudo_metadata(args, *, runner=subprocess.run):
    try:
        raw = command_output(
            [SUDO, "-n", *args], runner=runner, max_bytes=1024
        )
        return raw.decode("ascii").strip()
    except UnicodeError:
        raise Stop("sudo_metadata_invalid") from None


def absent(*, runner=subprocess.run):
    for option in ("-e", "-L"):
        result = invoke(
            [SUDO, "-n", TEST, option, INSTALL_TARGET], runner=runner
        )
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
        INSTALL_TARGET,
    ]


def cp_copy_proven(result, options: tuple[str, ...]) -> None:
    if (
        result.returncode
        or type(result.stdout) is not bytes
        or len(result.stdout) > 512
    ):
        raise Stop("post_dispatch_unknown_state")
    if options == ("--no-clobber", "--verbose"):
        expected = (
            "'/dev/stdin' -> '" + INSTALL_TARGET + "'\n"
        ).encode("ascii")
        if result.stdout != expected:
            raise Stop("post_dispatch_unknown_state")
    elif options != ("--update=none-fail",):
        raise Stop("post_dispatch_unknown_state")


def root_preflight(*, runner=subprocess.run):
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

    result = invoke(
        [SUDO, "-n", "-l", "--", *command], runner=runner
    )
    if result.returncode:
        raise Stop("sudo_exact_copy_not_allowed")
    return command


def preflight(expected_main, *, runner=subprocess.run):
    exact_checkout(expected_main, runner=runner)
    payload = tracked_helper(runner=runner)
    root_preflight(runner=runner)
    return payload


def sealed_memfd(data: bytes) -> int:
    fd = -1
    try:
        fd = os.memfd_create(
            "ausmalwiese-report-secrets-helper",
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


def post_verify(payload: bytes, *, runner=subprocess.run):
    metadata = sudo_metadata(
        [STAT, "-c", "%u:%g:%a:%F:%h", "--", INSTALL_TARGET],
        runner=runner,
    )
    if metadata != "0:0:500:regular file:1":
        raise Stop("post_verify_metadata_mismatch")
    digest = hashlib.sha256(payload).hexdigest()
    checksum = sudo_metadata(
        [SHA256SUM, "--", INSTALL_TARGET], runner=runner
    )
    if checksum != digest + "  " + INSTALL_TARGET:
        raise Stop("post_verify_hash_mismatch")


def apply(expected_main, *, runner=subprocess.run):
    payload = preflight(expected_main, runner=runner)
    memfd = sealed_memfd(payload)
    try:
        exact_checkout(expected_main, runner=runner)
        command = root_preflight(runner=runner)
        options = tuple(command[1:-5])
        try:
            result = invoke(
                [SUDO, "-n", *command],
                runner=runner,
                stdin=memfd,
                timeout=35,
            )
            cp_copy_proven(result, options)
            post_verify(payload, runner=runner)
        except Exception:
            raise Stop("post_dispatch_unknown_state") from None
    finally:
        os.close(memfd)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Source-only report secrets helper installer"
    )
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    try:
        if args.apply:
            if args.confirm != INSTALL_CONFIRM:
                raise Stop("confirmation_missing")
            apply(args.expected_main)
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "target": WORKER,
                        "mutation_started": True,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        else:
            if args.confirm:
                raise Stop("confirm_requires_apply")
            raw = preflight(args.expected_main)
            print(
                json.dumps(
                    {
                        "status": "PREFLIGHT_PASS",
                        "mutation_started": False,
                        "helper_sha256": hashlib.sha256(raw).hexdigest(),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
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
