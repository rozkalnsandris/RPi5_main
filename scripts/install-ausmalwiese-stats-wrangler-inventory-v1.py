#!/usr/bin/env python3
"""Source-only no-overwrite installer for #1056 protected inventory runtime.

No privileged repository Python. --apply is reserved for a future separately
authorized LIVE installation. This source never reads credentials or calls
Cloudflare.
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
EXECUTOR_REL = "scripts/ausmalwiese_stats_wrangler_inventory_executor_v1.py"
NORMALIZER_REL = "scripts/ausmalwiese_stats_wrangler_inventory_v1.py"
BINDING_REL = "ops/contracts/ausmalwiese-worker-settings-account-binding-v1.json"

EXECUTOR = "/usr/local/sbin/rpi5-ausmalwiese-stats-wrangler-inventory"
RELEASE_DIR = "/usr/local/libexec/rpi5-ausmalwiese-stats-wrangler-inventory"
NORMALIZER = RELEASE_DIR + "/normalizer.py"
RELEASE = RELEASE_DIR + "/release.json"
PARENTS = ("/usr", "/usr/local", "/usr/local/sbin", "/usr/local/libexec")
TARGETS = (EXECUTOR, RELEASE_DIR, NORMALIZER, RELEASE)

ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
ACCOUNT_EVIDENCE = (
    "https://github.com/rozkalnsandris/RPi5_main/issues/"
    "1004#issuecomment-6153841286"
)
WORKER = "coloring-pages-stats-v1"
CONFIRM = "INSTALL-AUSMALWIESE-STATS-WRANGLER-INVENTORY"
UPGRADE_CONFIRM = "UPGRADE-AUSMALWIESE-STATS-WRANGLER-INVENTORY"
OLD_RELEASE_SHA = "a48744ae941c5e5cfcbe4a01da0bd4a1618e266d"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")


class Stop(Exception):
    """Static safe error code only."""


def invoke(argv, *, input_bytes=None, runner=subprocess.run):
    try:
        return runner(
            list(argv),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=25,
        )
    except Exception:
        raise Stop("command_unavailable") from None


def git(argv, *, runner=subprocess.run) -> bytes:
    result = invoke([GIT, "-C", str(ROOT), *argv], runner=runner)
    if result.returncode:
        raise Stop("git_preflight_failed")
    if type(result.stdout) is not bytes or len(result.stdout) > 262144:
        raise Stop("git_output_invalid")
    return result.stdout


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
    if (
        text(
            git(
                ["symbolic-ref", "--quiet", "--short", "HEAD"],
                runner=runner,
            )
        )
        != "main"
    ):
        raise Stop("not_main")
    if text(git(["rev-parse", "HEAD"], runner=runner)) != expected_main:
        raise Stop("main_drift")
    if git(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        runner=runner,
    ):
        raise Stop("dirty_checkout")
    origin = text(git(["remote", "get-url", "origin"], runner=runner)).rstrip("/")
    https_ok = origin in {
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
    }
    username, sep, remaining = origin.partition("@")
    hostname, colon, project = (
        remaining.partition(":") if sep else ("", "", "")
    )
    ssh_ok = (
        username == "git"
        and sep == "@"
        and hostname == "github.com"
        and colon == ":"
        and project
        in {
            "rozkalnsandris/RPi5_main",
            "rozkalnsandris/RPi5_main.git",
        }
    )
    if not (https_ok or ssh_ok):
        raise Stop("origin_mismatch")


def tracked_snapshot(
    rel: str,
    *,
    runner=subprocess.run,
    max_size: int = 196608,
) -> bytes:
    if rel not in {EXECUTOR_REL, NORMALIZER_REL, BINDING_REL}:
        raise Stop("source_scope_invalid")
    path = ROOT / rel
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or not 0 < info.st_size <= max_size
        ):
            raise Stop("source_invalid")
        actual = path.read_bytes()
    except OSError:
        raise Stop("source_unreadable") from None
    canonical = git(["show", "HEAD:" + rel], runner=runner)
    if canonical != actual:
        raise Stop("source_digest_mismatch")
    return actual


def historical_snapshot(
    rel: str,
    ref: str,
    *,
    runner=subprocess.run,
    max_size: int = 196608,
) -> bytes:
    if rel not in {EXECUTOR_REL, NORMALIZER_REL}:
        raise Stop("historical_scope_invalid")
    if not isinstance(ref, str) or not SHA40.fullmatch(ref):
        raise Stop("historical_ref_invalid")
    raw = git(["show", f"{ref}:{rel}"], runner=runner)
    if not 0 < len(raw) <= max_size:
        raise Stop("historical_source_invalid")
    return raw


def approved_account_fingerprint(binding_raw: bytes) -> str:
    try:
        obj = json.loads(binding_raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise Stop("account_binding_unverified") from None
    if type(obj) is not dict or set(obj) != {
        "schema_version",
        "worker",
        "status",
        "account_sha256",
        "verification_evidence",
    }:
        raise Stop("account_binding_unverified")
    if (
        obj["schema_version"] != 1
        or obj["worker"] != WORKER
        or obj["status"] != "INDEPENDENTLY_VERIFIED"
        or obj["account_sha256"] != ACCOUNT_SHA256
        or obj["verification_evidence"] != ACCOUNT_EVIDENCE
    ):
        raise Stop("account_binding_unverified")
    return ACCOUNT_SHA256


def release_bytes(
    expected_main: str,
    executor: bytes,
    normalizer: bytes,
    account_digest: str,
) -> bytes:
    if (
        not SHA40.fullmatch(expected_main)
        or not SHA64.fullmatch(account_digest)
    ):
        raise Stop("release_identity_invalid")
    payload = {
        "schema_version": 1,
        "repository": REPO,
        "source_sha": expected_main,
        "worker": WORKER,
        "executor_sha256": hashlib.sha256(executor).hexdigest(),
        "normalizer_sha256": hashlib.sha256(normalizer).hexdigest(),
        "account_sha256": account_digest,
    }
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


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
        result = invoke(
            [SUDO, "-n", TEST, flag, path],
            runner=runner,
        )
        if result.returncode == 0:
            raise Stop("target_already_exists")
        if result.returncode != 1:
            raise Stop("target_preflight_failed")


def parents_preflight(*, runner=subprocess.run) -> None:
    sudo_read([TRUE], runner=runner)
    for path in PARENTS:
        value = sudo_read(
            [STAT, "-c", "%u:%g:%a:%F", "--", path],
            runner=runner,
        )
        parts = value.split(":")
        if (
            len(parts) != 4
            or parts[0:2] != ["0", "0"]
            or parts[3] != "directory"
        ):
            raise Stop("unsafe_parent")
        try:
            mode = int(parts[2], 8)
        except ValueError:
            raise Stop("unsafe_parent") from None
        if mode & 0o022 or mode & 0o700 != 0o700:
            raise Stop("unsafe_parent")


def exact_target(
    path: str,
    *,
    mode: str,
    kind: str,
    runner=subprocess.run,
) -> None:
    symlink = invoke(
        [SUDO, "-n", TEST, "-L", path],
        runner=runner,
    )
    if symlink.returncode == 0:
        raise Stop("upgrade_target_symlink")
    if symlink.returncode != 1:
        raise Stop("upgrade_target_preflight_failed")
    value = sudo_read(
        [STAT, "-c", "%u:%g:%a:%F", "--", path],
        runner=runner,
    )
    if value != f"0:0:{mode}:{kind}":
        raise Stop("upgrade_target_metadata_mismatch")


def exact_digest(path: str, payload: bytes, *, runner=subprocess.run) -> None:
    digest = hashlib.sha256(payload).hexdigest()
    checksum = sudo_read(
        [SHA256SUM, "--", path],
        runner=runner,
    )
    if checksum != f"{digest}  {path}":
        raise Stop("installed_release_mismatch")


def roots_preflight(*, runner=subprocess.run) -> None:
    parents_preflight(runner=runner)
    for path in TARGETS:
        absent(path, runner=runner)


def upgrade_roots_preflight(
    old_release_sha: str,
    account_digest: str,
    *,
    runner=subprocess.run,
) -> None:
    if old_release_sha != OLD_RELEASE_SHA:
        raise Stop("invalid_upgrade_source")
    parents_preflight(runner=runner)
    exact_target(
        RELEASE_DIR,
        mode="700",
        kind="directory",
        runner=runner,
    )
    exact_target(
        EXECUTOR,
        mode="500",
        kind="regular file",
        runner=runner,
    )
    exact_target(
        NORMALIZER,
        mode="400",
        kind="regular file",
        runner=runner,
    )
    exact_target(
        RELEASE,
        mode="400",
        kind="regular file",
        runner=runner,
    )
    old_executor = historical_snapshot(
        EXECUTOR_REL,
        old_release_sha,
        runner=runner,
    )
    old_normalizer = historical_snapshot(
        NORMALIZER_REL,
        old_release_sha,
        runner=runner,
    )
    old_release = release_bytes(
        old_release_sha,
        old_executor,
        old_normalizer,
        account_digest,
    )
    exact_digest(EXECUTOR, old_executor, runner=runner)
    exact_digest(NORMALIZER, old_normalizer, runner=runner)
    exact_digest(RELEASE, old_release, runner=runner)


def preflight(expected_main: str, *, runner=subprocess.run):
    checked_checkout(expected_main, runner=runner)
    executor = tracked_snapshot(EXECUTOR_REL, runner=runner)
    normalizer = tracked_snapshot(
        NORMALIZER_REL,
        runner=runner,
        max_size=196608,
    )
    binding = tracked_snapshot(
        BINDING_REL,
        runner=runner,
        max_size=8192,
    )
    account_digest = approved_account_fingerprint(binding)
    metadata = release_bytes(
        expected_main,
        executor,
        normalizer,
        account_digest,
    )
    roots_preflight(runner=runner)
    return executor, normalizer, metadata


def upgrade_preflight(
    expected_main: str,
    old_release_sha: str,
    *,
    runner=subprocess.run,
):
    if old_release_sha != OLD_RELEASE_SHA:
        raise Stop("invalid_upgrade_source")
    checked_checkout(expected_main, runner=runner)
    executor = tracked_snapshot(EXECUTOR_REL, runner=runner)
    normalizer = tracked_snapshot(
        NORMALIZER_REL,
        runner=runner,
        max_size=196608,
    )
    binding = tracked_snapshot(
        BINDING_REL,
        runner=runner,
        max_size=8192,
    )
    account_digest = approved_account_fingerprint(binding)
    metadata = release_bytes(
        expected_main,
        executor,
        normalizer,
        account_digest,
    )
    upgrade_roots_preflight(
        old_release_sha,
        account_digest,
        runner=runner,
    )
    return executor, normalizer, metadata


def write_once(args, data=None, *, runner=subprocess.run) -> None:
    try:
        result = invoke(
            [SUDO, "-n", *args],
            input_bytes=data,
            runner=runner,
        )
        if result.returncode:
            raise Stop("post_dispatch_unknown_state")
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def post_verify(files, *, runner=subprocess.run) -> None:
    for path, mode, payload in files:
        kind = "directory" if payload is None else "regular file"
        try:
            exact_target(
                path,
                mode=mode,
                kind=kind,
                runner=runner,
            )
        except Stop:
            raise Stop("post_verify_metadata_mismatch") from None
        if payload is not None:
            digest = hashlib.sha256(payload).hexdigest()
            checksum = sudo_read(
                [SHA256SUM, "--", path],
                runner=runner,
            )
            if checksum != f"{digest}  {path}":
                raise Stop("post_verify_digest_mismatch")


def apply(expected_main: str, *, runner=subprocess.run) -> None:
    executor, normalizer, metadata = preflight(
        expected_main,
        runner=runner,
    )
    try:
        write_once(
            [MKDIR, "-m", "0700", "--", RELEASE_DIR],
            runner=runner,
        )
        write_once(
            [
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
                EXECUTOR,
            ],
            executor,
            runner=runner,
        )
        write_once(
            [
                INSTALL,
                "-T",
                "-o",
                "root",
                "-g",
                "root",
                "-m",
                "0400",
                "--",
                "/dev/stdin",
                NORMALIZER,
            ],
            normalizer,
            runner=runner,
        )
        write_once(
            [
                INSTALL,
                "-T",
                "-o",
                "root",
                "-g",
                "root",
                "-m",
                "0400",
                "--",
                "/dev/stdin",
                RELEASE,
            ],
            metadata,
            runner=runner,
        )
        post_verify(
            (
                (RELEASE_DIR, "700", None),
                (EXECUTOR, "500", executor),
                (NORMALIZER, "400", normalizer),
                (RELEASE, "400", metadata),
            ),
            runner=runner,
        )
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def upgrade(
    expected_main: str,
    old_release_sha: str,
    *,
    runner=subprocess.run,
) -> None:
    executor, normalizer, metadata = upgrade_preflight(
        expected_main,
        old_release_sha,
        runner=runner,
    )
    try:
        for path, mode, payload in (
            (EXECUTOR, "0500", executor),
            (NORMALIZER, "0400", normalizer),
            (RELEASE, "0400", metadata),
        ):
            write_once(
                [
                    INSTALL,
                    "-T",
                    "-o",
                    "root",
                    "-g",
                    "root",
                    "-m",
                    mode,
                    "--",
                    "/dev/stdin",
                    path,
                ],
                payload,
                runner=runner,
            )
        post_verify(
            (
                (RELEASE_DIR, "700", None),
                (EXECUTOR, "500", executor),
                (NORMALIZER, "400", normalizer),
                (RELEASE, "400", metadata),
            ),
            runner=runner,
        )
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Source-only protected inventory runtime installer"
    )
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--upgrade-from", default="")
    args = parser.parse_args(argv)
    try:
        if args.upgrade_from:
            if args.upgrade_from != OLD_RELEASE_SHA:
                raise Stop("invalid_upgrade_source")
            if args.apply:
                if args.confirm != UPGRADE_CONFIRM:
                    raise Stop("confirmation_missing")
                upgrade(args.expected_main, args.upgrade_from)
                print(
                    json.dumps(
                        {
                            "status": "PASS",
                            "operation": "upgrade",
                            "mutation_started": True,
                        },
                        sort_keys=True,
                    )
                )
            else:
                if args.confirm:
                    raise Stop("confirmation_requires_apply")
                executor, normalizer, _ = upgrade_preflight(
                    args.expected_main,
                    args.upgrade_from,
                )
                print(
                    json.dumps(
                        {
                            "status": "UPGRADE_PREFLIGHT_PASS",
                            "mutation_started": False,
                            "old_release_sha": OLD_RELEASE_SHA,
                            "executor_sha256": hashlib.sha256(
                                executor
                            ).hexdigest(),
                            "normalizer_sha256": hashlib.sha256(
                                normalizer
                            ).hexdigest(),
                        },
                        sort_keys=True,
                    )
                )
        elif args.apply:
            if args.confirm != CONFIRM:
                raise Stop("confirmation_missing")
            apply(args.expected_main)
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "operation": "install",
                        "mutation_started": True,
                    },
                    sort_keys=True,
                )
            )
        else:
            if args.confirm:
                raise Stop("confirmation_requires_apply")
            executor, normalizer, _ = preflight(args.expected_main)
            print(
                json.dumps(
                    {
                        "status": "PREFLIGHT_PASS",
                        "mutation_started": False,
                        "executor_sha256": hashlib.sha256(
                            executor
                        ).hexdigest(),
                        "normalizer_sha256": hashlib.sha256(
                            normalizer
                        ).hexdigest(),
                    },
                    sort_keys=True,
                )
            )
        return 0
    except Stop as exc:
        unknown = str(exc) == "post_dispatch_unknown_state"
        print(
            json.dumps(
                {
                    "status": "STOP_ERROR" if unknown else "BLOCKED",
                    "reason": str(exc),
                    "mutation_state": (
                        "unknown" if unknown else "not_started"
                    ),
                },
                sort_keys=True,
            )
        )
        return 4 if unknown else 3


if __name__ == "__main__":
    sys.exit(main())
