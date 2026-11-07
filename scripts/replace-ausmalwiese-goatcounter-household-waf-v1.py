#!/usr/bin/env python3
"""First-replacement-only installer for the Ausmalwiese household WAF operator.

Default mode is read-only. Apply stages an exact candidate release and replaces
only the fixed operator/release files. The dedicated Cloudflare credential is
outside this installer and is never read or modified.
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
SOURCE_REL = "scripts/ausmalwiese_goatcounter_household_waf_v1.py"
SOURCE = ROOT / SOURCE_REL

TARGET = "/usr/local/sbin/rpi5-ausmalwiese-household-waf"
RELEASE_DIR = "/usr/local/libexec/rpi5-ausmalwiese-household-waf"
RELEASE = RELEASE_DIR + "/release.json"
STAGE_OPERATOR = TARGET + ".stage-1427"
STAGE_RELEASE = RELEASE + ".stage-1427"

OLD_MAIN = "6abc94ded6b1737beb322ee09ef19c57f1e95794"
OLD_OPERATOR_SHA = "7ebc7b3e6e79a60334242f2258e11abcef266a063899e7a69ec0f794a9bd59e8"
OLD_RELEASE_SHA = "3ed4805405a5767faf79fea0aef2bb0c0f33a05646532e32a3d50dd9b6f66889"

ROOT_DIRS = (
    "/usr",
    "/usr/local",
    "/usr/local/sbin",
    "/usr/local/libexec",
    RELEASE_DIR,
)
GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
STAT = "/usr/bin/stat"
TEST = "/usr/bin/test"
TRUE = "/usr/bin/true"
SHA256SUM = "/usr/bin/sha256sum"
INSTALL = "/usr/bin/install"
MV = "/usr/bin/mv"

CONFIRM = "REPLACE-AUSMALWIESE-HOUSEHOLD-WAF-RELEASE"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
RUNNER = Callable[..., subprocess.CompletedProcess]


class ReplaceError(Exception):
    """Sanitized fixed-code replacement failure."""


def run(argv: list[str], *, input_bytes: bytes | None = None,
        runner: RUNNER = subprocess.run) -> subprocess.CompletedProcess:
    try:
        return runner(
            argv,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        raise ReplaceError("command_unavailable") from None


def read(argv: list[str], *, runner: RUNNER = subprocess.run) -> str:
    result = run(argv, runner=runner)
    if result.returncode:
        raise ReplaceError("read_only_preflight_failed")
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        raise ReplaceError("invalid_preflight_output") from None


def git(args: list[str], *, runner: RUNNER = subprocess.run) -> str:
    return read([GIT, "-C", str(ROOT), *args], runner=runner)


def source_bytes(expected_main: str, *,
                 runner: RUNNER = subprocess.run) -> bytes:
    if os.geteuid() == 0:
        raise ReplaceError("must_run_unprivileged")
    if not SHA40.fullmatch(expected_main) or expected_main == OLD_MAIN:
        raise ReplaceError("invalid_candidate_main")
    if git(["rev-parse", "--show-toplevel"], runner=runner) != str(ROOT):
        raise ReplaceError("unexpected_checkout")
    if git(["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner) != "main":
        raise ReplaceError("not_main")
    if git(["rev-parse", "HEAD"], runner=runner) != expected_main:
        raise ReplaceError("main_drift")
    if git(["status", "--porcelain=v1", "--untracked-files=all"], runner=runner):
        raise ReplaceError("dirty_checkout")
    origin = git(["remote", "get-url", "origin"], runner=runner)
    if origin.rstrip("/") not in (
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
    ):
        raise ReplaceError("wrong_origin")
    if git(["ls-files", "--error-unmatch", SOURCE_REL], runner=runner) != SOURCE_REL:
        raise ReplaceError("source_not_tracked")
    try:
        source = SOURCE.read_bytes()
    except OSError:
        raise ReplaceError("source_unavailable") from None
    if not source or len(source) > 131072:
        raise ReplaceError("candidate_source_size_invalid")
    return source


def metadata_for(expected_main: str, source: bytes) -> bytes:
    return (json.dumps(
        {
            "source_sha": expected_main,
            "operator_sha256": hashlib.sha256(source).hexdigest(),
        },
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n").encode("ascii")


def root_text(argv: list[str], *, runner: RUNNER = subprocess.run) -> str:
    return read([SUDO, "-n", *argv], runner=runner)


def require_safe_root_dirs(*, runner: RUNNER = subprocess.run) -> None:
    root_text([TRUE], runner=runner)
    for path in ROOT_DIRS:
        observed = root_text(
            [STAT, "-c", "%u:%g:%a:%F", "--", path],
            runner=runner,
        )
        parts = observed.split(":")
        if (
            len(parts) != 4
            or parts[0:2] != ["0", "0"]
            or parts[3] != "directory"
        ):
            raise ReplaceError("unsafe_parent")
        try:
            mode = int(parts[2], 8)
        except ValueError:
            raise ReplaceError("unsafe_parent") from None
        if mode & 0o022 or mode & 0o700 != 0o700:
            raise ReplaceError("unsafe_parent")


def existing(path: str, mode: str, digest: str, *,
             runner: RUNNER = subprocess.run) -> None:
    observed = root_text(
        [STAT, "-c", "%u:%g:%a:%F", "--", path],
        runner=runner,
    )
    if observed != f"0:0:{mode}:regular file":
        raise ReplaceError("incumbent_metadata_drift")
    checksum = root_text([SHA256SUM, "--", path], runner=runner)
    if checksum != f"{digest}  {path}":
        raise ReplaceError("incumbent_digest_drift")


def require_staging_absent(*, runner: RUNNER = subprocess.run) -> None:
    for path in (STAGE_OPERATOR, STAGE_RELEASE):
        for flag in ("-e", "-L"):
            result = run([SUDO, "-n", TEST, flag, path], runner=runner)
            if result.returncode != 1:
                raise ReplaceError("staging_path_not_proven_absent")


def preflight(expected_main: str, *,
              runner: RUNNER = subprocess.run) -> tuple[bytes, bytes]:
    source = source_bytes(expected_main, runner=runner)
    release = metadata_for(expected_main, source)
    require_safe_root_dirs(runner=runner)
    existing(TARGET, "500", OLD_OPERATOR_SHA, runner=runner)
    existing(RELEASE, "400", OLD_RELEASE_SHA, runner=runner)
    require_staging_absent(runner=runner)
    return source, release


def root_mutation(argv: list[str], *, input_bytes: bytes | None = None,
                  runner: RUNNER = subprocess.run) -> None:
    """After dispatch, any non-success is terminal and must not be retried."""
    try:
        result = run(
            [SUDO, "-n", *argv],
            input_bytes=input_bytes,
            runner=runner,
        )
        if result.returncode:
            raise ReplaceError("post_dispatch_unknown_state")
    except Exception:
        raise ReplaceError("post_dispatch_unknown_state") from None


def verify_file(path: str, mode: str, digest: str, *,
                runner: RUNNER = subprocess.run) -> None:
    observed = root_text(
        [STAT, "-c", "%u:%g:%a:%F", "--", path],
        runner=runner,
    )
    if observed != f"0:0:{mode}:regular file":
        raise ReplaceError("replacement_metadata_mismatch")
    checksum = root_text([SHA256SUM, "--", path], runner=runner)
    if checksum != f"{digest}  {path}":
        raise ReplaceError("replacement_digest_mismatch")


def replace(expected_main: str, *,
            runner: RUNNER = subprocess.run) -> None:
    source, release = preflight(expected_main, runner=runner)
    source_digest = hashlib.sha256(source).hexdigest()
    release_digest = hashlib.sha256(release).hexdigest()

    try:
        root_mutation(
            [INSTALL, "-T", "-o", "root", "-g", "root", "-m", "0500",
             "--", "/dev/stdin", STAGE_OPERATOR],
            input_bytes=source,
            runner=runner,
        )
        root_mutation(
            [INSTALL, "-T", "-o", "root", "-g", "root", "-m", "0400",
             "--", "/dev/stdin", STAGE_RELEASE],
            input_bytes=release,
            runner=runner,
        )

        verify_file(STAGE_OPERATOR, "500", source_digest, runner=runner)
        verify_file(STAGE_RELEASE, "400", release_digest, runner=runner)

        # Re-prove the exact incumbent immediately before the fixed renames.
        existing(TARGET, "500", OLD_OPERATOR_SHA, runner=runner)
        existing(RELEASE, "400", OLD_RELEASE_SHA, runner=runner)

        root_mutation([MV, "-T", "--", STAGE_OPERATOR, TARGET], runner=runner)
        root_mutation([MV, "-T", "--", STAGE_RELEASE, RELEASE], runner=runner)

        verify_file(TARGET, "500", source_digest, runner=runner)
        verify_file(RELEASE, "400", release_digest, runner=runner)
    except Exception:
        raise ReplaceError("post_dispatch_unknown_state") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            if args.confirm != CONFIRM:
                raise ReplaceError("confirmation_missing")
            replace(args.expected_main)
            result = {"status": "PASS", "mutation_started": True}
        else:
            if args.confirm:
                raise ReplaceError("confirmation_requires_apply")
            source, _ = preflight(args.expected_main)
            result = {
                "status": "PREFLIGHT_PASS",
                "mutation_started": False,
                "candidate_sha256": hashlib.sha256(source).hexdigest(),
                "incumbent_release": OLD_MAIN,
            }
        print(json.dumps(result, sort_keys=True))
        return 0
    except ReplaceError as exc:
        unknown = str(exc) == "post_dispatch_unknown_state"
        print(json.dumps({
            "status": "STOP_ERROR" if unknown else "BLOCKED",
            "reason": str(exc),
            "mutation_state": "unknown" if unknown else "not_started",
        }, sort_keys=True))
        return 4 if unknown else 3


if __name__ == "__main__":
    sys.exit(main())
