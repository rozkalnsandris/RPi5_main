#!/usr/bin/env python3
"""Root-owned V12 extension entrypoint for the private WeatherNext bootstrap capability."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import stat
import subprocess
import sys
from typing import Any

SCHEMA = "rpi5.controlled-deploy-weathernext-extension.v1"
EXTENSION_RELEASES = pathlib.Path("/usr/local/libexec/rpi5-deploy/weathernext-releases")
BASE_RELEASES = pathlib.Path("/usr/local/libexec/rpi5-deploy/releases")
METADATA_NAME = "weathernext-extension.json"
ENTRY_NAME = "rpi5_deploy_weathernext_entry.py"
CAPABILITY_NAME = "rpi5_weathernext_bootstrap.py"
WEATHER_COMMAND = "weather-private-installer-bootstrap"
HOST_READY = "HOST_V12_WEATHERNEXT_BOOTSTRAP_CAPABILITY_INSTALLED"
SOURCE_READY = "SOURCE_READY_V12_ENGINE_UPGRADE_REQUIRED"


class ExtensionError(RuntimeError):
    pass


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_file(path: pathlib.Path, *, mode: int, root_owned: bool = True) -> os.stat_result:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
        raise ExtensionError(f"unsafe extension file: {path.name}")
    if root_owned and (info.st_uid != 0 or info.st_gid != 0):
        raise ExtensionError(f"extension ownership drifted: {path.name}")
    if stat.S_IMODE(info.st_mode) != mode:
        raise ExtensionError(f"extension mode drifted: {path.name}")
    return info


def _safe_release_dir(path: pathlib.Path) -> os.stat_result:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ExtensionError("extension release path is unsafe")
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ExtensionError("extension release metadata drifted")
    return info


def _metadata() -> tuple[pathlib.Path, dict[str, Any]]:
    release = pathlib.Path(__file__).resolve().parent
    if release.parent != EXTENSION_RELEASES or len(release.name) != 40 or any(c not in "0123456789abcdef" for c in release.name):
        raise ExtensionError("extension is not running from a versioned reviewed release")
    _safe_release_dir(release)
    path = release / METADATA_NAME
    _safe_file(path, mode=0o400)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExtensionError("extension metadata is unreadable") from exc
    expected = {
        "schema", "installed_from_commit", "repo_path", "repo_owner_uid", "base_release",
        "source_files", "installed_files", "source_state", "host_state",
    }
    if type(value) is not dict or set(value) != expected or value.get("schema") != SCHEMA:
        raise ExtensionError("extension metadata schema drifted")
    if value.get("installed_from_commit") != release.name:
        raise ExtensionError("extension release commit binding drifted")
    return release, value


def _verify_source(repo: pathlib.Path, relative: str, expected_sha: str) -> None:
    pure = pathlib.PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise ExtensionError("extension source path is unsafe")
    path = repo / relative
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
        raise ExtensionError(f"extension source is unsafe: {relative}")
    if _sha256(path) != expected_sha:
        raise ExtensionError(f"extension source changed; reinstall reviewed V12 engine: {relative}")


def verify_extension() -> tuple[pathlib.Path, pathlib.Path, dict[str, Any]]:
    release, metadata = _metadata()
    repo = pathlib.Path(str(metadata.get("repo_path", "")))
    if not repo.is_absolute() or ".." in repo.parts:
        raise ExtensionError("extension repository path is unsafe")
    repo_info = repo.stat()
    if repo_info.st_uid != int(metadata.get("repo_owner_uid", -1)) or repo_info.st_uid == 0:
        raise ExtensionError("extension repository owner drifted")
    base = pathlib.Path(str(metadata.get("base_release", "")))
    if base.parent != BASE_RELEASES or base.name != release.name:
        raise ExtensionError("extension base release binding drifted")
    base_info = base.lstat()
    if not stat.S_ISDIR(base_info.st_mode) or stat.S_ISLNK(base_info.st_mode):
        raise ExtensionError("base V12 release is unavailable")
    source_files = metadata.get("source_files")
    installed_files = metadata.get("installed_files")
    if type(source_files) is not dict or type(installed_files) is not dict:
        raise ExtensionError("extension inventory is invalid")
    if set(installed_files) != {ENTRY_NAME, CAPABILITY_NAME}:
        raise ExtensionError("extension installed inventory drifted")
    for name, item in installed_files.items():
        if type(item) is not dict or set(item) != {"sha256", "mode"}:
            raise ExtensionError("extension installed metadata is invalid")
        mode = int(str(item["mode"]), 8)
        path = release / name
        _safe_file(path, mode=mode)
        if _sha256(path) != item.get("sha256"):
            raise ExtensionError(f"extension installed checksum drifted: {name}")
    for relative, expected_sha in source_files.items():
        if type(relative) is not str or type(expected_sha) is not str:
            raise ExtensionError("extension source inventory is invalid")
        _verify_source(repo, relative, expected_sha)
    if metadata.get("source_state") != SOURCE_READY or metadata.get("host_state") != HOST_READY:
        raise ExtensionError("extension activation state metadata drifted")
    return release, base, metadata


def _run_base(base: pathlib.Path, argv: list[str]) -> int:
    command = ["/usr/bin/python3", str(base / "rpi5_deploy.py"), *argv]
    result = subprocess.run(
        command,
        env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
        check=False,
    )
    return result.returncode


def _load_capability(release: pathlib.Path, base: pathlib.Path):
    sys.path.insert(0, str(base))
    path = release / CAPABILITY_NAME
    spec = importlib.util.spec_from_file_location("rpi5_weathernext_bootstrap_installed", path)
    if spec is None or spec.loader is None:
        raise ExtensionError("unable to load installed WeatherNext capability")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


def _weather_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"rpi5-deploy {WEATHER_COMMAND}")
    parser.add_argument("--authorization-issue-number", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        release, base, _ = verify_extension()
        if args and args[0] == WEATHER_COMMAND:
            parsed = _weather_parser().parse_args(args[1:])
            capability = _load_capability(release, base)
            result = capability.execute_weathernext_bootstrap(parsed.authorization_issue_number)
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        if args and args[0] == "engine-status":
            rc = _run_base(base, args)
            if rc != 0:
                return rc
            print(
                f"weathernext_bootstrap_capability={HOST_READY} "
                "operation=rpi5.weathernext-private-installer-boundary.install.v1 "
                "caller_input=authorization_issue_number"
            )
            return 0
        os.execve(
            "/usr/bin/python3",
            ["/usr/bin/python3", str(base / "rpi5_deploy.py"), *args],
            {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
        )
    except (ExtensionError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
