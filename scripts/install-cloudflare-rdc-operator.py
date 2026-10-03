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


ROOT_RELEASE_INSPECTOR = r"""
import hashlib
import json
import os
import re
import stat

repository = "rozkalnsandris/RPi5_main"
operator = "/usr/local/sbin/rpi5-cloudflare"
release_dir = "/usr/local/libexec/rpi5-cloudflare"
metadata = release_dir + "/release.json"

def check(path, kind, mode):
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise SystemExit(41)
    if kind == "file" and not stat.S_ISREG(st.st_mode):
        raise SystemExit(42)
    if kind == "dir" and not stat.S_ISDIR(st.st_mode):
        raise SystemExit(43)
    if st.st_uid != 0 or st.st_gid != 0 or stat.S_IMODE(st.st_mode) != mode:
        raise SystemExit(44)

check(operator, "file", 0o500)
check(release_dir, "dir", 0o700)
check(metadata, "file", 0o400)

raw = open(metadata, "rb").read(8192)
decoded = json.loads(raw.decode("utf-8"))
if set(decoded) != {"schema_version", "repository", "source_sha", "operator_sha256"}:
    raise SystemExit(45)
if decoded["schema_version"] != 1 or decoded["repository"] != repository:
    raise SystemExit(46)
if not re.fullmatch(r"[0-9a-f]{40}", decoded["source_sha"]):
    raise SystemExit(47)
if not re.fullmatch(r"[0-9a-f]{64}", decoded["operator_sha256"]):
    raise SystemExit(48)

digest = hashlib.sha256()
with open(operator, "rb") as handle:
    for chunk in iter(lambda: handle.read(65536), b""):
        digest.update(chunk)
operator_sha = digest.hexdigest()
if operator_sha != decoded["operator_sha256"]:
    raise SystemExit(49)

print(json.dumps({
    "source_sha": decoded["source_sha"],
    "operator_sha256": operator_sha,
    "metadata_sha256": hashlib.sha256(raw).hexdigest(),
}, separators=(",", ":"), sort_keys=True))
"""

ROOT_UPGRADE_WRITER = r"""
import base64
import hashlib
import json
import os
import re
import stat
import sys

repository = "rozkalnsandris/RPi5_main"
operator = "/usr/local/sbin/rpi5-cloudflare"
operator_stage = "/usr/local/sbin/rpi5-cloudflare.next"
release_dir = "/usr/local/libexec/rpi5-cloudflare"
metadata = release_dir + "/release.json"
metadata_stage = release_dir + "/release.json.next"
expected_old = sys.argv[1]
expected_new = sys.argv[2]

if not re.fullmatch(r"[0-9a-f]{40}", expected_old):
    raise SystemExit(51)
if not re.fullmatch(r"[0-9a-f]{40}", expected_new):
    raise SystemExit(52)
if expected_old == expected_new:
    raise SystemExit(53)

def check(path, kind, mode):
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise SystemExit(54)
    if kind == "file" and not stat.S_ISREG(st.st_mode):
        raise SystemExit(55)
    if kind == "dir" and not stat.S_ISDIR(st.st_mode):
        raise SystemExit(56)
    if st.st_uid != 0 or st.st_gid != 0 or stat.S_IMODE(st.st_mode) != mode:
        raise SystemExit(57)

def file_sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

def ensure_absent(path):
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    raise SystemExit(58)

def write_exclusive(path, data, mode):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, mode)
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)

def fsync_dir(path):
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

check(operator, "file", 0o500)
check(release_dir, "dir", 0o700)
check(metadata, "file", 0o400)
current_raw = open(metadata, "rb").read(8192)
current = json.loads(current_raw.decode("utf-8"))
if set(current) != {"schema_version", "repository", "source_sha", "operator_sha256"}:
    raise SystemExit(59)
if current["schema_version"] != 1 or current["repository"] != repository:
    raise SystemExit(60)
if current["source_sha"] != expected_old:
    raise SystemExit(61)
if not re.fullmatch(r"[0-9a-f]{64}", current["operator_sha256"]):
    raise SystemExit(62)
if file_sha(operator) != current["operator_sha256"]:
    raise SystemExit(63)

ensure_absent(operator_stage)
ensure_absent(metadata_stage)

payload_raw = sys.stdin.buffer.read(262144)
payload = json.loads(payload_raw.decode("utf-8"))
if set(payload) != {"operator_b64", "metadata_b64"}:
    raise SystemExit(64)
new_operator = base64.b64decode(payload["operator_b64"], validate=True)
new_metadata = base64.b64decode(payload["metadata_b64"], validate=True)
if not new_operator or len(new_operator) > 131072:
    raise SystemExit(65)
if not new_metadata or len(new_metadata) > 8192:
    raise SystemExit(66)

new_decoded = json.loads(new_metadata.decode("utf-8"))
if set(new_decoded) != {"schema_version", "repository", "source_sha", "operator_sha256"}:
    raise SystemExit(67)
if new_decoded["schema_version"] != 1 or new_decoded["repository"] != repository:
    raise SystemExit(68)
if new_decoded["source_sha"] != expected_new:
    raise SystemExit(69)
if hashlib.sha256(new_operator).hexdigest() != new_decoded["operator_sha256"]:
    raise SystemExit(70)

write_exclusive(operator_stage, new_operator, 0o500)
write_exclusive(metadata_stage, new_metadata, 0o400)
check(operator_stage, "file", 0o500)
check(metadata_stage, "file", 0o400)
if file_sha(operator_stage) != new_decoded["operator_sha256"]:
    raise SystemExit(71)
if hashlib.sha256(open(metadata_stage, "rb").read()).hexdigest() != hashlib.sha256(new_metadata).hexdigest():
    raise SystemExit(72)

fsync_dir("/usr/local/sbin")
fsync_dir(release_dir)
os.replace(operator_stage, operator)
fsync_dir("/usr/local/sbin")
os.replace(metadata_stage, metadata)
fsync_dir(release_dir)
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
