#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Sequence

GIT = Path("/usr/bin/git")
SYSTEMCTL = Path("/usr/bin/systemctl")
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/install-hermes-deals-origin-broker.py"
IMMUTABLE_IMPLEMENTATION_BASELINE = "2550e77f6cb811ca6f10b49ef0b2fef554d64869"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

ROOT_UID = 0
ROOT_GID = 0
FILE_MODE = 0o644
EXEC_MODE = 0o755
CREDENTIAL_MODE = 0o600
SOCKET_GROUP = "rozkalns-deploy-executor"
SOURCE_CREDENTIAL = Path(
    "/etc/rozkalns-hermes-deals-origin-broker/source-github-app.pem"
)
SOCKET_UNIT = "rozkalns-hermes-deals-origin-broker.socket"
SYSTEMCTL_MUTATIONS = (
    ("daemon-reload",),
    ("enable", "--now", SOCKET_UNIT),
)

INSTALL_MUTATION_BUDGET = (
    ("trusted-file-materialization", 10),
    ("systemd-daemon-reload", 1),
    ("systemd-socket-enable-start", 1),
)


class HermesOriginBrokerInstallerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    source_path: str
    target_path: Path
    expected_blob: str
    mode: int


TARGETS = (
    Target(
        "ops/lib/deploy_executor/hermes_deals_origin_privileged_broker.py",
        Path("/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_privileged_broker.py"),
        "2543278ee48f184a79ac67c70e7f77c06cfbd7c8",
        FILE_MODE,
    ),
    Target(
        "ops/lib/deploy_executor/hermes_deals_origin_source_auth.py",
        Path("/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_source_auth.py"),
        "43640e9089cc39e96d472beb50e8653a5df5fa78",
        FILE_MODE,
    ),
    Target(
        "ops/lib/deploy_executor/hermes_deals_origin_helper_launch.py",
        Path("/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_helper_launch.py"),
        "5f190ebdcfdbc2a12242843733cb9740202cc9bd",
        FILE_MODE,
    ),
    Target(
        "ops/lib/deploy_executor/hermes_deals_origin_canonical_revalidator.py",
        Path("/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_canonical_revalidator.py"),
        "8c5d9d7746248b485b212cf601786924ba6e4d42",
        FILE_MODE,
    ),
    Target(
        "ops/lib/deploy_executor/hermes_deals_origin_host_evidence.py",
        Path("/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_host_evidence.py"),
        "4358beb65a48ed72c82d0e99e1fc8fd49db88524",
        FILE_MODE,
    ),
    Target(
        "ops/lib/deploy_executor/hermes_deals_origin_broker_composition.py",
        Path("/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_broker_composition.py"),
        "a7a9421527fb5b2ed0f250446dc257f0a9ac8a29",
        FILE_MODE,
    ),
    Target(
        "ops/lib/deploy_executor/p9_source_auth.py",
        Path("/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py"),
        "130fc36a22bb4ace500b022c3defcccbf0893012",
        FILE_MODE,
    ),
    Target(
        "ops/bin/rozkalns-hermes-deals-origin-broker",
        Path("/usr/local/libexec/rozkalns-hermes-deals-origin-broker"),
        "211b968b0c8ef6a0a7d73ce50a53d6bac7d2cc2f",
        EXEC_MODE,
    ),
    Target(
        "ops/systemd/rozkalns-hermes-deals-origin-broker.socket",
        Path("/etc/systemd/system/rozkalns-hermes-deals-origin-broker.socket"),
        "8eb05b83840b13b27e03e2bbb37d6d0bfc3697cb",
        FILE_MODE,
    ),
    Target(
        "ops/systemd/rozkalns-hermes-deals-origin-broker@.service",
        Path("/etc/systemd/system/rozkalns-hermes-deals-origin-broker@.service"),
        "2a304e70550f17092b9cafd365bbf6d05d23893b",
        FILE_MODE,
    ),
)


def _fail(message: str) -> None:
    raise HermesOriginBrokerInstallerError(message)


def _git_blob(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _run(
    argv: Sequence[str],
    *,
    cwd: Path = ROOT,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv),
        cwd=cwd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )


def _git_stdout(*args: str) -> bytes:
    result = _run((str(GIT), *args))
    if result.returncode != 0:
        _fail("reviewed Git source validation failed")
    return result.stdout


def _require_sha(value: str) -> str:
    if FULL_SHA.fullmatch(value) is None:
        _fail("expected source SHA must be a lowercase 40-character Git SHA")
    return value


def _require_exact_checkout(expected_sha: str) -> None:
    head = _git_stdout("rev-parse", "HEAD").decode("ascii", "strict").strip()
    if head != expected_sha:
        _fail("checkout HEAD does not match the authorized source SHA")

    result = _run(
        (
            str(GIT),
            "merge-base",
            "--is-ancestor",
            IMMUTABLE_IMPLEMENTATION_BASELINE,
            expected_sha,
        )
    )
    if result.returncode != 0:
        _fail("authorized source SHA is not descended from the immutable implementation baseline")

    tracked_script = _git_stdout("show", f"{expected_sha}:{SCRIPT_RELATIVE}")
    current_script = Path(__file__).read_bytes()
    if tracked_script != current_script:
        _fail("installer working-tree content differs from the authorized source SHA")


def _source_bytes(expected_sha: str, target: Target) -> bytes:
    value = _git_stdout("show", f"{expected_sha}:{target.source_path}")
    if _git_blob(value) != target.expected_blob:
        _fail(f"frozen source blob drifted for {target.source_path}")
    return value


def _require_secure_directory(path: Path) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required target parent is missing: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(f"target parent is not a real directory: {path}")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID:
        _fail(f"target parent is not root-owned: {path}")
    if stat.S_IMODE(info.st_mode) & 0o022:
        _fail(f"target parent is group/world writable: {path}")


def _require_secure_parent_chain(path: Path) -> None:
    current = path.parent
    chain: list[Path] = []
    while current != current.parent:
        chain.append(current)
        current = current.parent
    chain.append(Path("/"))
    for directory in reversed(chain):
        _require_secure_directory(directory)


def _credential_metadata_preflight() -> None:
    try:
        info = os.lstat(SOURCE_CREDENTIAL)
    except FileNotFoundError:
        _fail("source GitHub App credential path is absent")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail("source GitHub App credential path is not a regular non-symlink file")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID:
        _fail("source GitHub App credential metadata owner/group drifted")
    if stat.S_IMODE(info.st_mode) != CREDENTIAL_MODE:
        _fail("source GitHub App credential metadata mode drifted")


def _group_preflight() -> None:
    try:
        group = grp.getgrnam(SOCKET_GROUP)
    except KeyError:
        _fail("required broker socket group is absent")
    if group.gr_name != SOCKET_GROUP:
        _fail("required broker socket group identity drifted")


def _existing_target_state(target: Target, desired: bytes) -> str:
    del desired
    try:
        os.lstat(target.target_path)
    except FileNotFoundError:
        return "absent"
    # This first-install capability intentionally does not read existing runtime
    # files, including systemd units. Any pre-existing target is ambiguous and
    # therefore requires a separate reconciliation source gate.
    _fail(f"install target already exists and requires separate reconciliation: {target.target_path}")


def _preflight(expected_sha: str) -> tuple[tuple[Target, bytes, str], ...]:
    expected_sha = _require_sha(expected_sha)
    _require_exact_checkout(expected_sha)
    _group_preflight()
    _credential_metadata_preflight()

    prepared: list[tuple[Target, bytes, str]] = []
    for target in TARGETS:
        _require_secure_parent_chain(target.target_path)
        desired = _source_bytes(expected_sha, target)
        state = _existing_target_state(target, desired)
        prepared.append((target, desired, state))
    return tuple(prepared)


def _write_new_target(target: Target, desired: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target.target_path, flags, 0o600)
    try:
        offset = 0
        view = memoryview(desired)
        while offset < len(desired):
            written = os.write(fd, view[offset:])
            if written <= 0:
                _fail(f"short write while materializing {target.target_path}")
            offset += written
        os.fsync(fd)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fchmod(fd, target.mode)
        final = os.fstat(fd)
        if final.st_uid != ROOT_UID or final.st_gid != ROOT_GID:
            _fail(f"post-write owner/group mismatch: {target.target_path}")
        if stat.S_IMODE(final.st_mode) != target.mode:
            _fail(f"post-write mode mismatch: {target.target_path}")
    finally:
        os.close(fd)


def _systemctl(*args: str) -> None:
    if tuple(args) not in SYSTEMCTL_MUTATIONS:
        _fail("systemctl mutation is outside the fixed Hermes installer allowlist")
    result = _run((str(SYSTEMCTL), *args), cwd=Path("/"))
    if result.returncode != 0:
        _fail(f"systemctl mutation failed: {' '.join(args)}")


def _systemctl_query(*args: str) -> None:
    allowed = {
        ("is-enabled", SOCKET_UNIT),
        ("is-active", SOCKET_UNIT),
    }
    if tuple(args) not in allowed:
        _fail("systemctl query is outside the fixed Hermes installer allowlist")
    result = _run((str(SYSTEMCTL), *args), cwd=Path("/"))
    if result.returncode != 0:
        _fail(f"systemctl verification failed: {' '.join(args)}")


def _receipt(
    *,
    result: str,
    expected_sha: str,
    files_materialized: int,
    mutation_started: bool,
    systemd_activated: bool,
) -> str:
    value = {
        "schema": "rozkalns.hermes-deals.origin-broker-install-receipt.v1",
        "result": result,
        "source_sha": expected_sha,
        "immutable_implementation_baseline": IMMUTABLE_IMPLEMENTATION_BASELINE,
        "install_target_count": len(TARGETS),
        "files_materialized": files_materialized,
        "credential_content_read": False,
        "credential_mutated": False,
        "helper_executed": False,
        "genuine_audit_authorized": False,
        "broker_dispatch_enabled": False,
        "host_wiring_enabled": False,
        "systemd_socket_activated": systemd_activated,
        "mutation_started": mutation_started,
        "mutation_budget": [list(item) for item in INSTALL_MUTATION_BUDGET],
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def apply(expected_sha: str) -> str:
    if os.geteuid() != ROOT_UID:
        _fail("--apply requires root and must only be used under a separate explicit LIVE authorization")

    # Repeat every read-only predicate immediately before the first authorized
    # mutation. No retry, rollback, cleanup or alternate mutation path exists.
    prepared = _preflight(expected_sha)

    materialized = 0
    mutation_started = False
    for target, desired, state in prepared:
        if state != "absent":
            _fail("installer preflight returned an unsupported target state")
        mutation_started = True
        _write_new_target(target, desired)
        materialized += 1

    mutation_started = True
    _systemctl("daemon-reload")
    _systemctl("enable", "--now", SOCKET_UNIT)

    # Public-safe postconditions only. The service remains socket-activated and
    # the installed broker entrypoint remains the reviewed fail-closed stub.
    for target, _, _ in prepared:
        info = os.lstat(target.target_path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            _fail(f"post-install target type drifted: {target.target_path}")
        if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID:
            _fail(f"post-install target owner/group drifted: {target.target_path}")
        if stat.S_IMODE(info.st_mode) != target.mode:
            _fail(f"post-install target mode drifted: {target.target_path}")
    _systemctl_query("is-enabled", SOCKET_UNIT)
    _systemctl_query("is-active", SOCKET_UNIT)

    return _receipt(
        result="HERMES_ORIGIN_BROKER_INSTALLED_FAIL_CLOSED",
        expected_sha=expected_sha,
        files_materialized=materialized,
        mutation_started=mutation_started,
        systemd_activated=True,
    )


def preflight(expected_sha: str) -> str:
    prepared = _preflight(expected_sha)
    existing = sum(1 for _, _, state in prepared if state != "absent")
    return _receipt(
        result="HERMES_ORIGIN_BROKER_INSTALL_PREFLIGHT_READY",
        expected_sha=expected_sha,
        files_materialized=0,
        mutation_started=False,
        systemd_activated=False,
    )[:-1] + f',"existing_reviewed_targets":{existing}' + "}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed installer for the reviewed Hermes origin broker source slice."
    )
    parser.add_argument("expected_source_sha")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the fixed LIVE mutation after repeating the complete preflight.",
    )
    args = parser.parse_args(argv)
    try:
        output = (
            apply(args.expected_source_sha)
            if args.apply
            else preflight(args.expected_source_sha)
        )
    except HermesOriginBrokerInstallerError as exc:
        print(
            json.dumps(
                {
                    "schema": "rozkalns.hermes-deals.origin-broker-install-receipt.v1",
                    "result": "FAIL_CLOSED",
                    "reason": str(exc),
                    "credential_content_read": False,
                    "credential_mutated": False,
                    "helper_executed": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
