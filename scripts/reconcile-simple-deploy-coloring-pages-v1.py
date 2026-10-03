#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
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
ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
SCRIPT_RELATIVE = "scripts/reconcile-simple-deploy-coloring-pages-v1.py"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

ROOT_UID = 0
ROOT_GID = 0

BASELINE_REGISTRY_SHA256 = "46667f60470d032cd60f356d1fcc32596c75d6dfc38f9d9539531768733c8e6c"
BASELINE_IDENTITY_SHA256 = "68be71f09292496bd4ff5dbe8f322804df59065bc41cfa52bdb5a72ddc99e3a2"
BASELINE_COLORING_COMPOSE_SHA256 = "77c71da44896b393002b7a13449d6fbaca76b38c6d982580d23156b674fe2941"

DESIRED_REGISTRY_SHA256 = "e68fb9d674dbc044454563c8c8ba74c757c958ea78ff980dd0003b64d7e7bd7d"
DESIRED_COLORING_COMPOSE_SHA256 = "142c30bdd1080de90360f287e5b6fae27611c535caef0a41a09a998528bcbbc2"

IDENTITY_SCHEMA = "rozkalns.rpi5-main.simple-deploy.identity.v1"
HOST_REPOSITORY = "rozkalnsandris/RPi5_main"
TARGET_ALIAS = "coloring-pages-public-rpi5"

REGISTRY_SOURCE = "ops/deploy/simple-deploy-targets-v1.json"
COLORING_COMPOSE_SOURCE = "ops/deploy/simple-deploy-compose/coloring-pages-public.yml"


class ReconcileError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstallPaths:
    root: Path
    registry: Path
    identity: Path
    compose_root: Path
    coloring_compose: Path
    registry_stage: Path
    identity_stage: Path
    coloring_compose_stage: Path


PRODUCTION_PATHS = InstallPaths(
    root=Path("/etc/rozkalns-simple-deployer"),
    registry=Path("/etc/rozkalns-simple-deployer/targets.json"),
    identity=Path("/etc/rozkalns-simple-deployer/identity.json"),
    compose_root=Path("/etc/rozkalns-simple-deployer/compose"),
    coloring_compose=Path("/etc/rozkalns-simple-deployer/compose/coloring-pages-public.yml"),
    registry_stage=Path("/etc/rozkalns-simple-deployer/.targets.json.coloring-pages-v1.staged"),
    identity_stage=Path("/etc/rozkalns-simple-deployer/.identity.json.coloring-pages-v1.staged"),
    coloring_compose_stage=Path(
        "/etc/rozkalns-simple-deployer/compose/.coloring-pages-public.yml.reconcile-v1.staged"
    ),
)


@dataclass(frozen=True)
class Baseline:
    registry_sha256: str = BASELINE_REGISTRY_SHA256
    identity_sha256: str = BASELINE_IDENTITY_SHA256
    coloring_compose_sha256: str = BASELINE_COLORING_COMPOSE_SHA256


@dataclass(frozen=True)
class Desired:
    registry: bytes
    identity: bytes
    coloring_compose: bytes


@dataclass(frozen=True)
class InstalledSnapshot:
    registry: bytes
    identity: bytes
    coloring_compose: bytes


@dataclass
class Progress:
    mutation_started: bool = False
    staged_files_created: int = 0
    installed_files_replaced: int = 0


class ApplyFailure(ReconcileError):
    def __init__(self, message: str, progress: Progress):
        super().__init__(message)
        self.progress = progress


def _fail(message: str) -> None:
    raise ReconcileError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run(argv: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return _run(
        (str(GIT), "-c", f"safe.directory={ROOT}", "-C", str(ROOT), *args),
        cwd=ROOT,
    )


def _git_stdout(*args: str) -> bytes:
    result = _git(*args)
    if result.returncode != 0:
        _fail("Git source validation failed")
    return result.stdout


def _require_source_checkout(expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail("expected source SHA must be lowercase 40-character hex")
    if _git_stdout("rev-parse", "HEAD").decode("ascii").strip() != expected_sha:
        _fail("checkout HEAD does not match expected source SHA")
    if _git_stdout("branch", "--show-current").decode("utf-8").strip() != "main":
        _fail("checkout must be on main")
    if _git_stdout("remote", "get-url", "origin").decode("utf-8").strip() != ORIGIN:
        _fail("checkout origin drifted")
    if _git_stdout("status", "--porcelain=v1", "--untracked-files=all"):
        _fail("source checkout must be clean")
    if _git_stdout("show", f"{expected_sha}:{SCRIPT_RELATIVE}") != Path(__file__).read_bytes():
        _fail("reconciliation script working-tree bytes differ from expected source")


def _identity_bytes(source_sha: str) -> bytes:
    if FULL_SHA.fullmatch(source_sha) is None:
        _fail("identity source SHA must be lowercase 40-character hex")
    value = {
        "schema": IDENTITY_SCHEMA,
        "repository": HOST_REPOSITORY,
        "source_sha": source_sha,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _validate_desired_registry(value: bytes) -> None:
    if _sha256_bytes(value) != DESIRED_REGISTRY_SHA256:
        _fail("reviewed desired target registry hash drifted")
    try:
        parsed = json.loads(value.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReconcileError("reviewed desired target registry is not valid UTF-8 JSON") from exc

    matches = [
        target
        for target in parsed.get("targets", [])
        if target.get("target_alias") == TARGET_ALIAS
    ]
    if len(matches) != 1:
        _fail("reviewed desired target registry does not contain exactly one Coloring Pages target")
    target = matches[0]
    if target.get("consumer_repository") != "rozkalnsandris/coloring-pages":
        _fail("Coloring Pages consumer repository drifted")
    compose = target.get("compose", {})
    if compose.get("file") != "coloring-pages-public.yml":
        _fail("Coloring Pages compose filename drifted")
    if compose.get("file_sha256") != DESIRED_COLORING_COMPOSE_SHA256:
        _fail("Coloring Pages compose hash binding drifted")
    if target.get("persistent_volumes") != ["coloring_pages_content"]:
        _fail("Coloring Pages persistence identity drifted")
    health = target.get("health", {})
    if health.get("liveness_url") != "http://127.0.0.1:9191/health":
        _fail("Coloring Pages liveness URL drifted")
    if health.get("readiness_url") != "http://127.0.0.1:9191/ready":
        _fail("Coloring Pages readiness URL drifted")
    if target.get("registry_pull_profile") != "public-anonymous-pull":
        _fail("Coloring Pages registry pull profile drifted")


def _prepare_source(expected_sha: str) -> Desired:
    _require_source_checkout(expected_sha)
    registry = _git_stdout("show", f"{expected_sha}:{REGISTRY_SOURCE}")
    compose = _git_stdout("show", f"{expected_sha}:{COLORING_COMPOSE_SOURCE}")
    _validate_desired_registry(registry)
    if _sha256_bytes(compose) != DESIRED_COLORING_COMPOSE_SHA256:
        _fail("reviewed desired Coloring Pages compose source hash drifted")
    return Desired(
        registry=registry,
        identity=_identity_bytes(expected_sha),
        coloring_compose=compose,
    )


def _require_directory(path: Path, *, mode: int, uid: int, gid: int) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required installed directory is absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(f"required installed directory is not a real directory: {path}")
    if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
        _fail(f"installed directory metadata drifted: {path}")


def _read_regular(path: Path, *, mode: int, uid: int, gid: int) -> bytes:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required installed file is absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail(f"required installed file is not a real regular file: {path}")
    if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
        _fail(f"installed file metadata drifted: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        _fail(f"required installed file could not be read: {path}: {exc.strerror}")
    raise AssertionError("unreachable")


def _require_absent(path: Path) -> None:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    _fail(f"fixed staging path must be absent before first mutation: {path}")


def _preflight(
    paths: InstallPaths,
    desired: Desired,
    *,
    baseline: Baseline = Baseline(),
    uid: int = ROOT_UID,
    gid: int = ROOT_GID,
) -> InstalledSnapshot:
    _require_directory(paths.root, mode=0o755, uid=uid, gid=gid)
    _require_directory(paths.compose_root, mode=0o755, uid=uid, gid=gid)

    registry = _read_regular(paths.registry, mode=0o444, uid=uid, gid=gid)
    identity = _read_regular(paths.identity, mode=0o444, uid=uid, gid=gid)
    compose = _read_regular(paths.coloring_compose, mode=0o644, uid=uid, gid=gid)

    if _sha256_bytes(registry) != baseline.registry_sha256:
        _fail("installed target registry does not match the reviewed baseline")
    if _sha256_bytes(identity) != baseline.identity_sha256:
        _fail("installed SIMPLE-DEPLOY identity does not match the reviewed baseline")
    if _sha256_bytes(compose) != baseline.coloring_compose_sha256:
        _fail("installed Coloring Pages compose does not match the reviewed baseline")

    _validate_desired_registry(desired.registry)
    if _sha256_bytes(desired.coloring_compose) != DESIRED_COLORING_COMPOSE_SHA256:
        _fail("desired Coloring Pages compose hash drifted")

    for path in (
        paths.registry_stage,
        paths.identity_stage,
        paths.coloring_compose_stage,
    ):
        _require_absent(path)

    return InstalledSnapshot(
        registry=registry,
        identity=identity,
        coloring_compose=compose,
    )


def _write_stage(
    path: Path,
    content: bytes,
    *,
    mode: int,
    uid: int,
    gid: int,
    progress: Progress,
) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ApplyFailure(f"staged file creation failed: {path}: {exc.strerror}", progress) from exc

    progress.mutation_started = True
    progress.staged_files_created += 1
    try:
        view = memoryview(content)
        offset = 0
        while offset < len(content):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise ApplyFailure(f"short write while staging {path}", progress)
            offset += written
        os.fsync(fd)
        os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
    except OSError as exc:
        raise ApplyFailure(f"staged file write failed: {path}: {exc.strerror}", progress) from exc
    finally:
        os.close(fd)


def _fsync_dir(path: Path, progress: Progress) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ApplyFailure(f"directory fsync failed: {path}: {exc.strerror}", progress) from exc


def _require_unchanged(
    paths: InstallPaths,
    snapshot: InstalledSnapshot,
    *,
    uid: int,
    gid: int,
) -> None:
    if _read_regular(paths.registry, mode=0o444, uid=uid, gid=gid) != snapshot.registry:
        _fail("installed target registry changed after preflight")
    if _read_regular(paths.identity, mode=0o444, uid=uid, gid=gid) != snapshot.identity:
        _fail("installed SIMPLE-DEPLOY identity changed after preflight")
    if _read_regular(paths.coloring_compose, mode=0o644, uid=uid, gid=gid) != snapshot.coloring_compose:
        _fail("installed Coloring Pages compose changed after preflight")


def _replace(stage: Path, target: Path, parent: Path, progress: Progress) -> None:
    try:
        os.replace(stage, target)
    except OSError as exc:
        raise ApplyFailure(f"atomic installed-file replacement failed: {target}: {exc.strerror}", progress) from exc
    progress.installed_files_replaced += 1
    _fsync_dir(parent, progress)


def _apply(
    paths: InstallPaths,
    desired: Desired,
    snapshot: InstalledSnapshot,
    *,
    uid: int = ROOT_UID,
    gid: int = ROOT_GID,
) -> Progress:
    progress = Progress()
    try:
        _write_stage(
            paths.coloring_compose_stage,
            desired.coloring_compose,
            mode=0o644,
            uid=uid,
            gid=gid,
            progress=progress,
        )
        _write_stage(
            paths.registry_stage,
            desired.registry,
            mode=0o444,
            uid=uid,
            gid=gid,
            progress=progress,
        )
        _write_stage(
            paths.identity_stage,
            desired.identity,
            mode=0o444,
            uid=uid,
            gid=gid,
            progress=progress,
        )

        _require_unchanged(paths, snapshot, uid=uid, gid=gid)

        _replace(
            paths.coloring_compose_stage,
            paths.coloring_compose,
            paths.compose_root,
            progress,
        )
        if _read_regular(paths.coloring_compose, mode=0o644, uid=uid, gid=gid) != desired.coloring_compose:
            raise ApplyFailure("Coloring Pages compose postcondition failed", progress)

        if _read_regular(paths.registry, mode=0o444, uid=uid, gid=gid) != snapshot.registry:
            raise ApplyFailure("installed target registry changed before replacement", progress)
        if _read_regular(paths.identity, mode=0o444, uid=uid, gid=gid) != snapshot.identity:
            raise ApplyFailure("installed identity changed before registry replacement", progress)

        _replace(paths.registry_stage, paths.registry, paths.root, progress)
        if _read_regular(paths.registry, mode=0o444, uid=uid, gid=gid) != desired.registry:
            raise ApplyFailure("target registry postcondition failed", progress)

        if _read_regular(paths.identity, mode=0o444, uid=uid, gid=gid) != snapshot.identity:
            raise ApplyFailure("installed identity changed before final replacement", progress)

        _replace(paths.identity_stage, paths.identity, paths.root, progress)
        if _read_regular(paths.identity, mode=0o444, uid=uid, gid=gid) != desired.identity:
            raise ApplyFailure("identity postcondition failed", progress)

        if paths.coloring_compose_stage.exists() or paths.registry_stage.exists() or paths.identity_stage.exists():
            raise ApplyFailure("staging postcondition failed", progress)

        _validate_desired_registry(desired.registry)
        return progress
    except ApplyFailure:
        raise
    except ReconcileError as exc:
        raise ApplyFailure(str(exc), progress) from exc
    except OSError as exc:
        raise ApplyFailure(f"unexpected filesystem error: {exc.strerror}", progress) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile the exact installed SIMPLE-DEPLOY files required by the Coloring Pages target."
    )
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if os.geteuid() != ROOT_UID:
            _fail("production reconciliation entrypoint must run as root")
        desired = _prepare_source(args.expected_source_sha)
        snapshot = _preflight(PRODUCTION_PATHS, desired)
        if not args.apply:
            print("SIMPLE_DEPLOY_COLORING_PAGES_RECONCILE_PREFLIGHT_READY")
            return 0
        progress = _apply(PRODUCTION_PATHS, desired, snapshot)
    except ApplyFailure as exc:
        print(
            "SIMPLE_DEPLOY_COLORING_PAGES_RECONCILE_FAILED "
            f"mutation_started={str(exc.progress.mutation_started).lower()} "
            f"staged_files_created={exc.progress.staged_files_created} "
            f"installed_files_replaced={exc.progress.installed_files_replaced} "
            f"error={exc}",
            file=sys.stderr,
        )
        return 1
    except ReconcileError as exc:
        print(
            "SIMPLE_DEPLOY_COLORING_PAGES_RECONCILE_FAILED "
            "mutation_started=false staged_files_created=0 installed_files_replaced=0 "
            f"error={exc}",
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "result": "SIMPLE_DEPLOY_COLORING_PAGES_RECONCILE_COMPLETE",
                "mutation_started": progress.mutation_started,
                "staged_files_created": progress.staged_files_created,
                "installed_files_replaced": progress.installed_files_replaced,
                "target_alias": TARGET_ALIAS,
                "identity_source_sha": args.expected_source_sha,
                "docker_mutation": False,
                "systemd_mutation": False,
                "database_or_data_mutation": False,
                "secret_or_permission_mutation": False,
                "network_mutation": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
