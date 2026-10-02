#!/usr/bin/env python3
from __future__ import annotations

import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/adopt-simple-deploy-rozkalns-cv-data-v1.py"
CONTRACT_RELATIVE = "ops/contracts/simple-deploy-rozkalns-cv-data-adoption-v1.json"
CUTOVER_RELATIVE = "ops/deploy/rozkalns-cv-simple-deploy-cutover-v1.json"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
GIT = Path("/usr/bin/git")
DOCKER = Path("/usr/bin/docker")

LEGACY_STATE = Path("/var/lib/rozkalns-cv-deploy/current-sha")
LEGACY_SHA = "4986a6d80460bd6d7681c70e09e61a15e31007f4"
SOURCE_OWNER = "andris"
SOURCE_DATA_RELATIVE = Path("docker/cv/bot/data")
DEST_ROOT = Path("/var/lib/rozkalns-simple-deployer/rozkalns-cv")
DEST_DATA = DEST_ROOT / "data"
STAGING_ROOT = Path("/var/lib/rozkalns-simple-deployer/.rozkalns-cv-data-adoption-v1.staged")
STATE_PARENT = Path("/var/lib/rozkalns-simple-deployer")
CONTAINER_NAME = "cvbot"
CONTAINER_IMAGE = "rozkalns-cv-cvbot:4986a6d80460bd6d7681c70e09e61a15e31007f4"
APP_UID = 10001
APP_GID = 10001
RUNTIME_GROUP = "rozkalns-simple-deployer"
PUBLIC_SCHEMA = "rozkalns.rpi5-main.simple-deploy-rozkalns-cv-data-adoption-result.v1"


class AdoptionError(RuntimeError):
    pass


class ApplyFailure(AdoptionError):
    def __init__(self, message: str, *, mutation_started: bool) -> None:
        super().__init__(message)
        self.mutation_started = mutation_started


def _fail(message: str) -> None:
    raise AdoptionError(message)


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        (
            str(GIT),
            "--no-optional-locks",
            "-c",
            f"safe.directory={ROOT}",
            "-C",
            str(ROOT),
            *args,
        ),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "GIT_OPTIONAL_LOCKS": "0",
        },
    )


def _git_stdout(*args: str) -> bytes:
    result = _git(*args)
    if result.returncode != 0:
        _fail("Git source validation failed")
    return result.stdout


def _require_source_checkout(expected_sha: str) -> None:
    if len(expected_sha) != 40 or any(c not in "0123456789abcdef" for c in expected_sha):
        _fail("expected source SHA must be lowercase 40-character hex")
    head = _git_stdout("rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if head != expected_sha:
        _fail("checkout HEAD does not match expected source SHA")
    origin = _git_stdout("remote", "get-url", "origin").decode("utf-8").strip()
    if origin != ORIGIN:
        _fail("checkout origin drifted")
    for args in (
        ("diff-files", "--quiet", "--"),
        ("diff-index", "--cached", "--quiet", "HEAD", "--"),
    ):
        result = _git(*args)
        if result.returncode == 1:
            _fail("source checkout must be clean")
        if result.returncode != 0:
            _fail("Git source validation failed")
    if _git_stdout("ls-files", "--others", "--exclude-standard"):
        _fail("source checkout must be clean")
    for relative in (SCRIPT_RELATIVE, CONTRACT_RELATIVE, CUTOVER_RELATIVE):
        if _git_stdout("show", f"{expected_sha}:{relative}") != (ROOT / relative).read_bytes():
            _fail("reviewed adoption source differs from expected Git source")


def _lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise AdoptionError("required fixed path metadata is unavailable") from exc


def _require_directory(path: Path) -> None:
    mode = _lstat(path).st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        _fail("required fixed directory metadata drifted")


def _require_absent(path: Path, *, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise AdoptionError(f"{label} metadata is unavailable") from exc
    _fail(f"{label} must be absent")


def _read_legacy_state() -> str:
    mode = _lstat(LEGACY_STATE).st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        _fail("legacy production state metadata drifted")
    try:
        value = LEGACY_STATE.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise AdoptionError("legacy production state is unreadable") from exc
    if value != LEGACY_SHA:
        _fail("legacy production SHA drifted")
    return value


def _docker_cvbot_state() -> str:
    result = subprocess.run(
        (
            str(DOCKER),
            "ps",
            "-a",
            "--filter",
            f"name=^/{CONTAINER_NAME}$",
            "--format",
            "{{.Names}}\t{{.Image}}\t{{.State}}",
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    if result.returncode != 0:
        _fail("legacy cvbot metadata query failed")
    try:
        lines = result.stdout.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise AdoptionError("legacy cvbot metadata is invalid") from exc
    if len(lines) != 1:
        _fail("exact legacy cvbot container is not uniquely present")
    fields = lines[0].split("\t")
    if len(fields) != 3 or fields[0] != CONTAINER_NAME or fields[1] != CONTAINER_IMAGE:
        _fail("legacy cvbot identity drifted")
    return fields[2]


def _source_data_path() -> Path:
    try:
        home = Path(pwd.getpwnam(SOURCE_OWNER).pw_dir)
    except KeyError as exc:
        raise AdoptionError("fixed legacy source owner is absent") from exc
    if not home.is_absolute():
        _fail("fixed legacy source home is invalid")
    return home / SOURCE_DATA_RELATIVE


def _runtime_gid() -> int:
    try:
        return grp.getgrnam(RUNTIME_GROUP).gr_gid
    except KeyError as exc:
        raise AdoptionError("generic deployer runtime group is absent") from exc


def _public_preflight() -> dict[str, object]:
    _read_legacy_state()
    source_data = _source_data_path()
    _require_directory(source_data)
    _require_directory(STATE_PARENT)
    _require_absent(DEST_ROOT, label="destination root")
    _require_absent(STAGING_ROOT, label="staging root")
    state = _docker_cvbot_state()
    if state != "running":
        _fail("legacy cvbot must be running before cutover mutation starts")
    _runtime_gid()
    return {
        "schema": PUBLIC_SCHEMA,
        "status": "READY_FOR_CUTOVER_DATA_ADOPTION",
        "legacy_cvbot_state": "running",
        "destination_state": "absent",
        "staging_state": "absent",
        "protected_data_read": False,
        "mutation_started": False,
        "protected_values_emitted": False,
    }


def _copy_regular_file(src: Path, dst: Path, *, app_uid: int, app_gid: int) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(src, flags)
    except OSError as exc:
        raise AdoptionError("protected data source file could not be opened safely") from exc
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            _fail("protected data tree contains a non-regular file")
        try:
            dest_fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as exc:
            raise AdoptionError("protected data staging file could not be created") from exc
        try:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                view = memoryview(chunk)
                while view:
                    written = os.write(dest_fd, view)
                    view = view[written:]
            os.fsync(dest_fd)
            os.fchmod(dest_fd, 0o600)
            os.fchown(dest_fd, app_uid, app_gid)
        finally:
            os.close(dest_fd)
    finally:
        os.close(source_fd)


def _copy_directory_contents(
    src: Path,
    dst: Path,
    *,
    app_uid: int,
    app_gid: int,
    runtime_gid: int,
) -> None:
    try:
        entries = list(os.scandir(src))
    except OSError as exc:
        raise AdoptionError("protected data source directory could not be enumerated") from exc
    for entry in entries:
        source = src / entry.name
        target = dst / entry.name
        try:
            if entry.is_symlink():
                _fail("protected data tree contains a symlink")
            if entry.is_dir(follow_symlinks=False):
                os.mkdir(target, 0o710)
                os.chown(target, app_uid, runtime_gid)
                os.chmod(target, 0o710)
                _copy_directory_contents(
                    source,
                    target,
                    app_uid=app_uid,
                    app_gid=app_gid,
                    runtime_gid=runtime_gid,
                )
                continue
            if entry.is_file(follow_symlinks=False):
                _copy_regular_file(source, target, app_uid=app_uid, app_gid=app_gid)
                continue
        except OSError as exc:
            raise AdoptionError("protected data tree copy failed") from exc
        _fail("protected data tree contains a special file")


def _apply() -> dict[str, object]:
    if os.geteuid() != 0:
        _fail("--apply requires root and exact LIVE authority")
    _read_legacy_state()
    source_data = _source_data_path()
    _require_directory(source_data)
    _require_directory(STATE_PARENT)
    _require_absent(DEST_ROOT, label="destination root")
    _require_absent(STAGING_ROOT, label="staging root")
    if _docker_cvbot_state() != "exited":
        _fail("legacy cvbot must be stopped before protected data copy")
    runtime_gid = _runtime_gid()

    mutation_started = False
    try:
        os.mkdir(STAGING_ROOT, 0o710)
        mutation_started = True
        os.chown(STAGING_ROOT, APP_UID, runtime_gid)
        os.chmod(STAGING_ROOT, 0o710)

        staging_data = STAGING_ROOT / "data"
        os.mkdir(staging_data, 0o710)
        os.chown(staging_data, APP_UID, runtime_gid)
        os.chmod(staging_data, 0o710)

        _copy_directory_contents(
            source_data,
            staging_data,
            app_uid=APP_UID,
            app_gid=APP_GID,
            runtime_gid=runtime_gid,
        )
        os.replace(STAGING_ROOT, DEST_ROOT)
        parent_fd = os.open(STATE_PARENT, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except AdoptionError as exc:
        raise ApplyFailure(str(exc), mutation_started=mutation_started) from exc
    except OSError as exc:
        raise ApplyFailure(
            "protected data adoption failed after mutation start",
            mutation_started=mutation_started,
        ) from exc

    return {
        "schema": PUBLIC_SCHEMA,
        "status": "EXACT_READY",
        "mutation_started": True,
        "source_tree_mutated": False,
        "database_queries": False,
        "database_schema_migrations": False,
        "protected_values_emitted": False,
        "legacy_cvbot_restarted": False,
    }


def _validate_machine_contract() -> None:
    try:
        contract = json.loads((ROOT / CONTRACT_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdoptionError("machine-readable data-adoption contract is unavailable") from exc
    if contract.get("schema") != "rozkalns.rpi5-main.simple-deploy-rozkalns-cv-data-adoption.v1":
        _fail("data-adoption contract schema drifted")
    if contract.get("issue") != 808:
        _fail("data-adoption issue binding drifted")
    source = contract.get("source", {})
    if source.get("owner_user") != SOURCE_OWNER:
        _fail("data-adoption source owner drifted")
    if source.get("home_resolution") != "passwd_database":
        _fail("data-adoption source home-resolution drifted")
    if source.get("data_relative_path") != SOURCE_DATA_RELATIVE.as_posix():
        _fail("data-adoption source relative path drifted")
    if source.get("home_is_caller_selectable") is not False:
        _fail("data-adoption source home authority drifted")
    if contract.get("destination", {}).get("app_root") != str(DEST_ROOT):
        _fail("data-adoption destination path drifted")
    if contract.get("helper", {}).get("entrypoint") != SCRIPT_RELATIVE:
        _fail("data-adoption entrypoint drifted")
    if contract.get("helper", {}).get("options") != ["--expected-source-sha", "--apply"]:
        _fail("data-adoption CLI authority drifted")
    if contract.get("materialization", {}).get("cvbot_lifecycle_managed_by_helper") is not False:
        _fail("data-adoption Docker lifecycle boundary drifted")
    if contract.get("private_runtime_config_boundary", {}).get("handled_by_this_helper") is not False:
        _fail("data-adoption private-config boundary drifted")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed rozkalns-cv durable-data adoption for SIMPLE-DEPLOY cutover"
    )
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _require_source_checkout(args.expected_source_sha)
        _validate_machine_contract()
        result = _apply() if args.apply else _public_preflight()
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except ApplyFailure as exc:
        print(
            json.dumps(
                {
                    "schema": PUBLIC_SCHEMA,
                    "status": "ERROR",
                    "error": str(exc),
                    "mutation_started": exc.mutation_started,
                    "automatic_retry": False,
                    "automatic_cleanup": False,
                    "automatic_rollback": False,
                    "protected_values_emitted": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 4
    except AdoptionError as exc:
        print(
            json.dumps(
                {
                    "schema": PUBLIC_SCHEMA,
                    "status": "ERROR",
                    "error": str(exc),
                    "mutation_started": False,
                    "protected_values_emitted": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
