#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

REPOSITORY = "rozkalnsandris/RPi5_main"
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "cloudflare_rdc_operator.py"
INSTALLED = Path("/usr/local/sbin/rpi5-cloudflare")
RELEASE_DIR = Path("/usr/local/libexec/rpi5-cloudflare")
RELEASE_METADATA = RELEASE_DIR / "release.json"
OPERATOR_STAGE = Path("/usr/local/sbin/rpi5-cloudflare.next")
RELEASE_METADATA_STAGE = RELEASE_DIR / "release.json.next"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CONFIRM_TEXT = "INSTALL-CLOUDFLARE-RDC-OPERATOR"
UPGRADE_CONFIRM_TEXT = "UPGRADE-CLOUDFLARE-RDC-OPERATOR"
SUDO = "/usr/bin/sudo"
INSTALL = "/usr/bin/install"
PYTHON = "/usr/bin/python3"

ROOT_METADATA_WRITER = r"""
import json
import os
import re
import sys

path = "/usr/local/libexec/rpi5-cloudflare/release.json"
raw = sys.stdin.buffer.read(8192)
decoded = json.loads(raw.decode("utf-8"))
if set(decoded) != {"schema_version", "repository", "source_sha", "operator_sha256"}:
    raise SystemExit(31)
if decoded["schema_version"] != 1 or decoded["repository"] != "rozkalnsandris/RPi5_main":
    raise SystemExit(32)
if not re.fullmatch(r"[0-9a-f]{40}", decoded["source_sha"]):
    raise SystemExit(33)
if not re.fullmatch(r"[0-9a-f]{64}", decoded["operator_sha256"]):
    raise SystemExit(34)
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
fd = os.open(path, flags, 0o400)
try:
    view = memoryview(raw)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]
    os.fsync(fd)
finally:
    os.close(fd)
"""

Runner = Callable[..., subprocess.CompletedProcess[Any]]


class InstallError(RuntimeError):
    pass


def _emit(
    result: str,
    *,
    reason: str | None = None,
    mutation_performed: bool = False,
    install_ready: bool | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "installer": "rpi5-cloudflare-rdc-operator-installer-v1",
        "repository": REPOSITORY,
        "result": result,
        "mutation_performed": mutation_performed,
        "sudoers_mutation": False,
    }
    if reason:
        payload["reason"] = reason
    if install_ready is not None:
        payload["install_ready"] = install_ready
    print(json.dumps(payload, indent=2, sort_keys=True))


def _run(
    argv: list[str],
    *,
    runner: Runner = subprocess.run,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[Any]:
    return runner(
        argv,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _git(args: list[str], *, runner: Runner = subprocess.run) -> str:
    completed = _run(
        ["/usr/bin/git", "-C", str(ROOT), *args],
        runner=runner,
    )
    if completed.returncode != 0:
        raise InstallError("git_preflight_failed")
    try:
        return completed.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise InstallError("git_preflight_failed") from exc


def _remote_is_canonical(value: str) -> bool:
    normalized = value.strip().removesuffix("/")
    return normalized in {
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
    }


def verify_exact_checkout(
    expected_main: str, *, runner: Runner = subprocess.run
) -> bytes:
    if os.geteuid() == 0:
        raise InstallError("installer_must_not_run_as_root")
    if not SHA_RE.fullmatch(expected_main):
        raise InstallError("expected_main_invalid")
    if _git(["rev-parse", "--show-toplevel"], runner=runner) != str(ROOT):
        raise InstallError("repository_root_mismatch")
    if _git(["rev-parse", "HEAD"], runner=runner) != expected_main:
        raise InstallError("head_not_expected_main")
    if _git(["branch", "--show-current"], runner=runner) != "main":
        raise InstallError("branch_not_main")
    if _git(["status", "--porcelain=v1", "--untracked-files=all"], runner=runner):
        raise InstallError("working_tree_not_clean")
    remote = _git(["remote", "get-url", "origin"], runner=runner)
    if not _remote_is_canonical(remote):
        raise InstallError("origin_not_canonical")
    if _git(["ls-files", "--error-unmatch", "scripts/cloudflare_rdc_operator.py"], runner=runner) != "scripts/cloudflare_rdc_operator.py":
        raise InstallError("operator_not_tracked")
    try:
        source = SOURCE.read_bytes()
    except OSError as exc:
        raise InstallError("operator_source_unreadable") from exc
    if not source:
        raise InstallError("operator_source_unreadable")
    return source


def build_release_metadata(expected_main: str, source: bytes) -> bytes:
    payload = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "source_sha": expected_main,
        "operator_sha256": hashlib.sha256(source).hexdigest(),
    }
    return (
        json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _sudo_available(*, runner: Runner = subprocess.run) -> None:
    completed = _run([SUDO, "-n", "/usr/bin/true"], runner=runner)
    if completed.returncode != 0:
        raise InstallError("sudo_noninteractive_unavailable")


def _target_absent(path: Path, *, runner: Runner = subprocess.run) -> bool:
    completed = _run(
        [SUDO, "-n", "/usr/bin/test", "-e", str(path)],
        runner=runner,
    )
    if completed.returncode == 0:
        return False
    if completed.returncode == 1:
        return True
    raise InstallError("target_preflight_failed")


def preflight_install(
    expected_main: str, *, runner: Runner = subprocess.run
) -> tuple[bytes, bytes]:
    source = verify_exact_checkout(expected_main, runner=runner)
    metadata = build_release_metadata(expected_main, source)
    _sudo_available(runner=runner)
    for path in (INSTALLED, RELEASE_DIR, RELEASE_METADATA):
        if not _target_absent(path, runner=runner):
            raise InstallError("install_target_already_exists")
    return source, metadata


def _require_success(
    completed: subprocess.CompletedProcess[Any],
    *,
    mutation_started: bool,
) -> None:
    if completed.returncode != 0:
        raise InstallError(
            "post_mutation_failure" if mutation_started else "install_command_failed"
        )


def apply_install(
    expected_main: str, *, runner: Runner = subprocess.run
) -> None:
    source, metadata = preflight_install(expected_main, runner=runner)
    expected_operator_hash = hashlib.sha256(source).hexdigest()
    expected_metadata_hash = hashlib.sha256(metadata).hexdigest()
    mutation_started = False

    completed = _run(
        [
            SUDO,
            "-n",
            INSTALL,
            "-d",
            "-o",
            "root",
            "-g",
            "root",
            "-m",
            "0700",
            str(RELEASE_DIR),
        ],
        runner=runner,
    )
    _require_success(completed, mutation_started=False)
    mutation_started = True

    completed = _run(
        [
            SUDO,
            "-n",
            INSTALL,
            "-o",
            "root",
            "-g",
            "root",
            "-m",
            "0500",
            str(SOURCE),
            str(INSTALLED),
        ],
        runner=runner,
    )
    _require_success(completed, mutation_started=mutation_started)

    completed = _run(
        [SUDO, "-n", PYTHON, "-c", ROOT_METADATA_WRITER],
        runner=runner,
        input_bytes=metadata,
    )
    _require_success(completed, mutation_started=mutation_started)

    checks = [
        (
            [SUDO, "-n", "/usr/bin/stat", "-c", "%U:%G %a", str(INSTALLED)],
            "root:root 500",
        ),
        (
            [SUDO, "-n", "/usr/bin/stat", "-c", "%U:%G %a", str(RELEASE_DIR)],
            "root:root 700",
        ),
        (
            [SUDO, "-n", "/usr/bin/stat", "-c", "%U:%G %a", str(RELEASE_METADATA)],
            "root:root 400",
        ),
        (
            [SUDO, "-n", "/usr/bin/sha256sum", str(INSTALLED)],
            expected_operator_hash,
        ),
        (
            [SUDO, "-n", "/usr/bin/sha256sum", str(RELEASE_METADATA)],
            expected_metadata_hash,
        ),
    ]
    for argv, expected in checks:
        completed = _run(argv, runner=runner)
        _require_success(completed, mutation_started=mutation_started)
        observed = completed.stdout.decode("utf-8", errors="replace").strip()
        if expected not in observed:
            raise InstallError("post_mutation_failure")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.apply:
            if args.confirm != CONFIRM_TEXT:
                raise InstallError("install_confirmation_missing")
            apply_install(args.expected_main)
            _emit("PASS", mutation_performed=True, install_ready=False)
        else:
            preflight_install(args.expected_main)
            _emit("PASS", mutation_performed=False, install_ready=True)
        return 0
    except InstallError as exc:
        reason = str(exc)
        mutation = reason == "post_mutation_failure"
        _emit(
            "STOP_ERROR" if mutation else "BLOCKED",
            reason=reason,
            mutation_performed=mutation,
            install_ready=False,
        )
        return 4 if mutation else 3


if __name__ == "__main__":
    raise SystemExit(main())
