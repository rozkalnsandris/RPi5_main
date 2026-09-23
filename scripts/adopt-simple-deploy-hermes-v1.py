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
SCRIPT_RELATIVE = "scripts/adopt-simple-deploy-hermes-v1.py"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ROOT_UID = 0
ROOT_GID = 0

BASELINE_SOURCE_SHA = "7c6c7a8a80ca62d783c7f378b5865fae348a3fe9"
BASELINE_REGISTRY_SHA256 = "c8b97e3274b732cdd0cdd2ddedb79515ebd9a6a433b094443594bdd8f74114ad"
WEATHER_COMPOSE_SHA256 = "80e2b47e4ed039c38285094e0b273fbc884f0a34ff34d8b201d8e93323af1f32"
DESIRED_REGISTRY_SHA256 = "75660aefcf82bbc2b0b9d91cada515d9777804a7be2752f86d9d071c0ad9dbba"
HERMES_COMPOSE_SHA256 = "644dc72da5dc13ee532dd29693db31358451669bb44de4df4b62c41736903f1c"
IDENTITY_SCHEMA = "rozkalns.rpi5-main.simple-deploy.identity.v1"
HOST_REPOSITORY = "rozkalnsandris/RPi5_main"
WEATHER_ALIAS = "rozkalns-weather-public-rpi5"
HERMES_ALIAS = "hermes-deals"

BASELINE_FIXTURE = ROOT / "ops/deploy/baselines/simple-deploy-targets-weather-only-v1.json"
DESIRED_REGISTRY_SOURCE = ROOT / "ops/deploy/simple-deploy-targets-v1.json"
HERMES_COMPOSE_SOURCE = ROOT / "ops/deploy/simple-deploy-compose/hermes-deals-api.yml"


@dataclass(frozen=True)
class InstallPaths:
    root: Path
    registry: Path
    identity: Path
    compose_root: Path
    weather_compose: Path
    hermes_compose: Path
    executor: Path
    erroneous_public_registry: Path
    registry_stage: Path
    hermes_stage: Path


PRODUCTION_PATHS = InstallPaths(
    root=Path("/etc/rozkalns-simple-deployer"),
    registry=Path("/etc/rozkalns-simple-deployer/targets.json"),
    identity=Path("/etc/rozkalns-simple-deployer/identity.json"),
    compose_root=Path("/etc/rozkalns-simple-deployer/compose"),
    weather_compose=Path("/etc/rozkalns-simple-deployer/compose/rozkalns-weather-public.yml"),
    hermes_compose=Path("/etc/rozkalns-simple-deployer/compose/hermes-deals-api.yml"),
    executor=Path("/usr/local/libexec/rozkalns-simple-deployer/simple_deploy_v1.py"),
    erroneous_public_registry=Path("/etc/rozkalns-simple-deployer/public_targets.json"),
    registry_stage=Path("/etc/rozkalns-simple-deployer/.targets.json.hermes-adoption-v1.staged"),
    hermes_stage=Path("/etc/rozkalns-simple-deployer/compose/.hermes-deals-api.yml.adoption-v1.staged"),
)


class AdoptionError(RuntimeError):
    pass


@dataclass
class Progress:
    mutation_started: bool = False
    staged_files_created: int = 0
    installed_targets_changed: int = 0


class ApplyFailure(AdoptionError):
    def __init__(self, message: str, progress: Progress):
        super().__init__(message)
        self.progress = progress


@dataclass(frozen=True)
class Prepared:
    desired_registry: bytes
    desired_hermes_compose: bytes
    baseline_registry: bytes
    identity_bytes: bytes
    weather_bytes: bytes
    executor_sha256: str


def _fail(message: str) -> None:
    raise AdoptionError(message)


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
    return _run((str(GIT), "-c", f"safe.directory={ROOT}", "-C", str(ROOT), *args), cwd=ROOT)


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
    if _git_stdout("remote", "get-url", "origin").decode("utf-8").strip() != ORIGIN:
        _fail("checkout origin drifted")
    if _git_stdout("status", "--porcelain=v1", "--untracked-files=all"):
        _fail("source checkout must be clean")
    if _git_stdout("show", f"{expected_sha}:{SCRIPT_RELATIVE}") != Path(__file__).read_bytes():
        _fail("adoption script working-tree bytes differ from expected source")


def _identity_bytes() -> bytes:
    value = {
        "schema": IDENTITY_SCHEMA,
        "repository": HOST_REPOSITORY,
        "source_sha": BASELINE_SOURCE_SHA,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _lstat_regular(path: Path, *, mode: int, uid: int, gid: int) -> os.stat_result:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required installed file is absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail(f"required installed file is not a real regular file: {path}")
    if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
        _fail(f"installed file metadata drifted: {path}")
    return info


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
    _lstat_regular(path, mode=mode, uid=uid, gid=gid)
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
    _fail(f"adoption target must be absent before first mutation: {path}")


def _validate_registry_bytes(*, baseline: bytes, desired: bytes) -> None:
    if _sha256_bytes(baseline) != BASELINE_REGISTRY_SHA256:
        _fail("reviewed Weather-only baseline fixture hash drifted")
    if _sha256_bytes(desired) != DESIRED_REGISTRY_SHA256:
        _fail("reviewed two-target source registry hash drifted")
    try:
        old = json.loads(baseline.decode("utf-8"))
        new = json.loads(desired.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AdoptionError("reviewed registry source is not valid UTF-8 JSON") from exc
    if [item.get("target_alias") for item in old.get("targets", [])] != [WEATHER_ALIAS]:
        _fail("Weather-only baseline target set drifted")
    if [item.get("target_alias") for item in new.get("targets", [])] != [WEATHER_ALIAS, HERMES_ALIAS]:
        _fail("two-target postcondition target set drifted")
    if old["targets"][0] != new["targets"][0]:
        _fail("Weather target semantics drifted across Hermes adoption")


def _prepare_source() -> tuple[bytes, bytes, bytes]:
    try:
        baseline = BASELINE_FIXTURE.read_bytes()
        desired_registry = DESIRED_REGISTRY_SOURCE.read_bytes()
        desired_hermes = HERMES_COMPOSE_SOURCE.read_bytes()
    except OSError as exc:
        raise AdoptionError("reviewed adoption source artifact is unavailable") from exc
    _validate_registry_bytes(baseline=baseline, desired=desired_registry)
    if _sha256_bytes(desired_hermes) != HERMES_COMPOSE_SHA256:
        _fail("reviewed Hermes compose source hash drifted")
    return baseline, desired_registry, desired_hermes


def _preflight(paths: InstallPaths, *, uid: int = ROOT_UID, gid: int = ROOT_GID) -> Prepared:
    baseline, desired_registry, desired_hermes = _prepare_source()
    _require_directory(paths.root, mode=0o755, uid=uid, gid=gid)
    _require_directory(paths.compose_root, mode=0o755, uid=uid, gid=gid)

    identity = _read_regular(paths.identity, mode=0o444, uid=uid, gid=gid)
    expected_identity = _identity_bytes()
    if identity != expected_identity:
        _fail("installed SIMPLE-DEPLOY identity does not match the reviewed Weather baseline provenance")

    installed_registry = _read_regular(paths.registry, mode=0o444, uid=uid, gid=gid)
    if installed_registry != baseline:
        _fail("installed registry does not match the exact reviewed Weather-only baseline")

    weather_bytes = _read_regular(paths.weather_compose, mode=0o444, uid=uid, gid=gid)
    if _sha256_bytes(weather_bytes) != WEATHER_COMPOSE_SHA256:
        _fail("installed Weather compose adapter drifted")

    executor_bytes = _read_regular(paths.executor, mode=0o444, uid=uid, gid=gid)
    executor_sha256 = _sha256_bytes(executor_bytes)

    _require_absent(paths.hermes_compose)
    _require_absent(paths.erroneous_public_registry)
    _require_absent(paths.registry_stage)
    _require_absent(paths.hermes_stage)

    return Prepared(
        desired_registry=desired_registry,
        desired_hermes_compose=desired_hermes,
        baseline_registry=baseline,
        identity_bytes=identity,
        weather_bytes=weather_bytes,
        executor_sha256=executor_sha256,
    )


def _write_stage(path: Path, content: bytes, *, mode: int, uid: int, gid: int, progress: Progress) -> None:
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
        offset = 0
        view = memoryview(content)
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


def _apply(paths: InstallPaths, prepared: Prepared, *, uid: int = ROOT_UID, gid: int = ROOT_GID) -> Progress:
    progress = Progress()
    try:
        _write_stage(
            paths.hermes_stage,
            prepared.desired_hermes_compose,
            mode=0o444,
            uid=uid,
            gid=gid,
            progress=progress,
        )
        _write_stage(
            paths.registry_stage,
            prepared.desired_registry,
            mode=0o444,
            uid=uid,
            gid=gid,
            progress=progress,
        )

        _require_absent(paths.hermes_compose)
        current_registry = _read_regular(paths.registry, mode=0o444, uid=uid, gid=gid)
        if current_registry != prepared.baseline_registry:
            raise ApplyFailure("installed registry changed after preflight", progress)

        try:
            os.link(paths.hermes_stage, paths.hermes_compose, follow_symlinks=False)
        except OSError as exc:
            raise ApplyFailure(
                f"atomic Hermes compose publication failed: {paths.hermes_compose}: {exc.strerror}", progress
            ) from exc
        progress.installed_targets_changed += 1
        _fsync_dir(paths.compose_root, progress)

        try:
            os.unlink(paths.hermes_stage)
        except OSError as exc:
            raise ApplyFailure(f"staging unlink failed after Hermes publication: {exc.strerror}", progress) from exc
        _fsync_dir(paths.compose_root, progress)

        current_registry = _read_regular(paths.registry, mode=0o444, uid=uid, gid=gid)
        if current_registry != prepared.baseline_registry:
            raise ApplyFailure("installed registry changed before atomic replacement", progress)
        try:
            os.replace(paths.registry_stage, paths.registry)
        except OSError as exc:
            raise ApplyFailure(f"atomic target registry replacement failed: {exc.strerror}", progress) from exc
        progress.installed_targets_changed += 1
        _fsync_dir(paths.root, progress)

        if _read_regular(paths.registry, mode=0o444, uid=uid, gid=gid) != prepared.desired_registry:
            raise ApplyFailure("postcondition failed for installed target registry", progress)
        if _read_regular(paths.hermes_compose, mode=0o444, uid=uid, gid=gid) != prepared.desired_hermes_compose:
            raise ApplyFailure("postcondition failed for installed Hermes compose adapter", progress)
        if _read_regular(paths.identity, mode=0o444, uid=uid, gid=gid) != prepared.identity_bytes:
            raise ApplyFailure("installed identity changed during adoption", progress)
        if _read_regular(paths.weather_compose, mode=0o444, uid=uid, gid=gid) != prepared.weather_bytes:
            raise ApplyFailure("Weather compose adapter changed during adoption", progress)
        executor = _read_regular(paths.executor, mode=0o444, uid=uid, gid=gid)
        if _sha256_bytes(executor) != prepared.executor_sha256:
            raise ApplyFailure("SIMPLE-DEPLOY executor changed during adoption", progress)
        if paths.registry_stage.exists() or paths.hermes_stage.exists():
            raise ApplyFailure("staging postcondition failed", progress)

        _validate_registry_bytes(baseline=prepared.baseline_registry, desired=prepared.desired_registry)
        return progress
    except ApplyFailure:
        raise
    except AdoptionError as exc:
        raise ApplyFailure(str(exc), progress) from exc
    except OSError as exc:
        raise ApplyFailure(f"unexpected filesystem error: {exc.strerror}", progress) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Adopt the reviewed Hermes SIMPLE-DEPLOY target into the exact existing Weather installation."
    )
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if os.geteuid() != ROOT_UID:
            _fail("production adoption entrypoint must run as root")
        _require_source_checkout(args.expected_source_sha)
        prepared = _preflight(PRODUCTION_PATHS)
        if not args.apply:
            print("SIMPLE_DEPLOY_HERMES_ADOPTION_PREFLIGHT_READY")
            return 0
        progress = _apply(PRODUCTION_PATHS, prepared)
    except ApplyFailure as exc:
        print(
            "SIMPLE_DEPLOY_HERMES_ADOPTION_FAILED "
            f"mutation_started={str(exc.progress.mutation_started).lower()} "
            f"staged_files_created={exc.progress.staged_files_created} "
            f"installed_targets_changed={exc.progress.installed_targets_changed} "
            f"error={exc}",
            file=sys.stderr,
        )
        return 1
    except AdoptionError as exc:
        print(
            "SIMPLE_DEPLOY_HERMES_ADOPTION_FAILED "
            f"mutation_started=false staged_files_created=0 installed_targets_changed=0 error={exc}",
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "result": "SIMPLE_DEPLOY_HERMES_ADOPTION_COMPLETE",
                "mutation_started": progress.mutation_started,
                "staged_files_created": progress.staged_files_created,
                "installed_targets_changed": progress.installed_targets_changed,
                "target_aliases": [WEATHER_ALIAS, HERMES_ALIAS],
                "docker_mutation": False,
                "systemd_mutation": False,
                "database_or_data_mutation": False,
                "secret_or_permission_mutation": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
