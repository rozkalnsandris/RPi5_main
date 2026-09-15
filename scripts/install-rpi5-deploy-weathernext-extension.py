#!/usr/bin/env python3
"""Install the reviewed WeatherNext capability inside the existing V12 deploy boundary."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import tempfile

from rpi5_deploy import require_repo_checks, require_target_contract
from rpi5_deploy_lib import (
    CTX,
    ENGINE_RELEASES,
    DeployError,
    github_checks,
    host_identity,
    repository_preflight,
    require_normal_user,
    run,
    safe_file,
    sha256_file,
)

SCHEMA = "rpi5.controlled-deploy-weathernext-extension.v1"
EXTENSION_RELEASES = pathlib.Path("/usr/local/libexec/rpi5-deploy/weathernext-releases")
ENTRY_SOURCE = "scripts/rpi5_deploy_weathernext_entry.py"
ENTRY_INSTALLED = "rpi5_deploy_weathernext_entry.py"
CAPABILITY_SOURCE = "scripts/rpi5_weathernext_bootstrap.py"
CAPABILITY_INSTALLED = "rpi5_weathernext_bootstrap.py"
SOURCE_CONTRACT = "ops/deploy/weather-private-bigquery-host-privileged-installer.json"
SOURCE_FILES = (
    "scripts/rpi5-deploy",
    "scripts/install-rpi5-deploy-weathernext-extension.py",
    ENTRY_SOURCE,
    CAPABILITY_SOURCE,
    SOURCE_CONTRACT,
)
SOURCE_READY = "SOURCE_READY_V12_ENGINE_UPGRADE_REQUIRED"
HOST_READY = "HOST_V12_WEATHERNEXT_BOOTSTRAP_CAPABILITY_INSTALLED"


def _source_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in SOURCE_FILES:
        path = CTX.repo / relative
        safe_file(path)
        run(["git", "ls-files", "--error-unmatch", "--", relative], cwd=CTX.repo)
        result[relative] = sha256_file(path)
    return result


def _stage(
    stage: pathlib.Path,
    release: pathlib.Path,
    base_release: pathlib.Path,
    commit: str,
    source_hashes: dict[str, str],
) -> tuple[pathlib.Path, pathlib.Path]:
    stage.mkdir(parents=True, exist_ok=False)
    installed_files: dict[str, dict[str, str]] = {}
    for installed, relative in (
        (ENTRY_INSTALLED, ENTRY_SOURCE),
        (CAPABILITY_INSTALLED, CAPABILITY_SOURCE),
    ):
        source = CTX.repo / relative
        destination = stage / installed
        shutil.copyfile(source, destination)
        digest = sha256_file(destination)
        if digest != source_hashes[relative]:
            raise DeployError(f"staged WeatherNext extension checksum mismatch: {installed}")
        installed_files[installed] = {"sha256": digest, "mode": "0400"}

    metadata = {
        "schema": SCHEMA,
        "installed_from_commit": commit,
        "repo_path": str(CTX.repo),
        "repo_owner_uid": CTX.repo.stat().st_uid,
        "base_release": str(base_release),
        "source_files": source_hashes,
        "installed_files": installed_files,
        "source_state": SOURCE_READY,
        "host_state": HOST_READY,
    }
    metadata_path = stage / "weathernext-extension.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    wrapper_path = stage / "rpi5-deploy-wrapper"
    wrapper_path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "exec /usr/bin/env -i "
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
        f"/usr/bin/python3 {release}/{ENTRY_INSTALLED} \"$@\"\n",
        encoding="utf-8",
    )
    return metadata_path, wrapper_path


def _verify_existing_release(path: pathlib.Path) -> None:
    result = run(["sudo", "test", "-d", str(path)], check=False, capture=False)
    if result.returncode != 0:
        raise DeployError("expected versioned V12 base release is missing")


def _direct_status(release: pathlib.Path) -> None:
    command = [
        "sudo", "/usr/bin/env", "-i",
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "/usr/bin/python3", str(release / ENTRY_INSTALLED),
        "engine-status", "--release-only",
    ]
    run(command, capture=False, timeout=300)


def install_extension(confirm: str) -> None:
    require_normal_user()
    repository = repository_preflight(validate=True)
    require_target_contract()
    checks = github_checks(repository["head"])
    require_repo_checks(checks)
    host_identity(root_required=False)
    short_commit = repository["head"][:12]
    if confirm != short_commit:
        raise DeployError("WeatherNext engine extension confirmation must equal exact 12-character main commit")

    source_hashes = _source_hashes()
    commit = repository["head"]
    base_release = ENGINE_RELEASES / commit
    release = EXTENSION_RELEASES / commit
    staging_release = EXTENSION_RELEASES / f".staging-{commit}-{os.getpid()}"
    system_wrapper = pathlib.Path("/usr/local/sbin/rpi5-deploy")
    system_wrapper_tmp = pathlib.Path(f"/usr/local/sbin/.rpi5-deploy-weathernext-{os.getpid()}")

    _verify_existing_release(base_release)
    with tempfile.TemporaryDirectory(prefix="rpi5-deploy-weathernext-") as temporary:
        stage = pathlib.Path(temporary) / "release"
        metadata_path, wrapper_path = _stage(
            stage, release, base_release, commit, source_hashes
        )
        if _source_hashes() != source_hashes:
            raise DeployError("WeatherNext extension source changed during installation staging")

        run([
            "sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0700",
            str(EXTENSION_RELEASES),
        ], capture=False)
        release_exists = run(
            ["sudo", "test", "-e", str(release)], check=False, capture=False
        ).returncode == 0
        if not release_exists:
            if run(
                ["sudo", "test", "-e", str(staging_release)], check=False, capture=False
            ).returncode == 0:
                raise DeployError("unexpected WeatherNext extension staging path already exists")
            run([
                "sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0700",
                str(staging_release),
            ], capture=False)
            for name in (ENTRY_INSTALLED, CAPABILITY_INSTALLED):
                run([
                    "sudo", "install", "-o", "root", "-g", "root", "-m", "0400",
                    str(stage / name), str(staging_release / name),
                ], capture=False)
            run([
                "sudo", "install", "-o", "root", "-g", "root", "-m", "0400",
                str(metadata_path), str(staging_release / "weathernext-extension.json"),
            ], capture=False)
            run(["sudo", "mv", "--", str(staging_release), str(release)], capture=False)

        _direct_status(release)
        run([
            "sudo", "install", "-o", "root", "-g", "root", "-m", "0700",
            str(wrapper_path), str(system_wrapper_tmp),
        ], capture=False)
        run(["sudo", "mv", "-f", "--", str(system_wrapper_tmp), str(system_wrapper)], capture=False)
        run(["sudo", str(system_wrapper), "engine-status"], capture=False, timeout=300)

    print(
        f"WEATHERNEXT V12 EXTENSION INSTALL PASS commit={commit} "
        f"status={HOST_READY} command={system_wrapper}"
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="install-rpi5-deploy-weathernext-extension.py")
    sub = result.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install-engine")
    install.add_argument("--confirm", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "install-engine":
            install_extension(args.confirm)
    except (DeployError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
