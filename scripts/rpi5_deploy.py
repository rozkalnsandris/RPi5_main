#!/usr/bin/env python3
"""CLI for reviewed, exact-commit RPi5_main deployment."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

from rpi5_deploy_lib import (CTX, ENGINE_INSTALLED_FILES, ENGINE_RELEASES,
    ENGINE_SCHEMA, ENGINE_SOURCE_FILES, EXPECTED_REPOSITORY, DeployError,
    append_log, atomic_json, build_plan, engine_source_preflight, ensure_no_conflicts,
    expected_fingerprint, fingerprint, git, github_checks, host_identity,
    host_preflight, load_plan, operation_lock, read_manifest,
    repository_preflight, require_normal_user, require_root, run, safe_file,
    sha256_file, verify_engine_integrity, verify_plan_targets)
from rpi5_deploy_tx import apply_plan, latest_transaction, manual_rollback


REQUIRED_GITHUB_CHECKS = {"validate"}
APPROVED_TARGET_CONTRACT = {
    "backup-runner": (
        "ops/bin/rpi5-backup-serialized",
        "/usr/local/sbin/rpi5-backup",
        "root",
        "root",
        0o750,
        ("bash-n",),
    ),
    "backup-core": (
        "ops/bin/rpi5-backup",
        "/usr/local/lib/rpi5-maintenance/rpi5-backup-v10-core",
        "root",
        "root",
        0o750,
        ("bash-n",),
    ),
    "maintenance-lock-lib": (
        "ops/lib/rpi5-maintenance-locks.sh",
        "/usr/local/lib/rpi5-maintenance/rpi5-maintenance-locks.sh",
        "root",
        "root",
        0o644,
        ("bash-n",),
    ),
    "backup-cron": (
        "ops/cron.d/rpi5-backup",
        "/etc/cron.d/rpi5-backup",
        "root",
        "root",
        0o644,
        ("cron-contract",),
    ),
    "backup-logrotate": (
        "ops/logrotate.d/rpi5-backup",
        "/etc/logrotate.d/rpi5-backup",
        "root",
        "root",
        0o644,
        ("logrotate-debug",),
    ),
}


def require_target_contract() -> list:
    targets, _ = read_manifest()
    actual = {
        target.id: (
            target.source,
            target.target,
            target.owner,
            target.group,
            target.mode,
            target.validators,
        )
        for target in targets
    }
    if actual != APPROVED_TARGET_CONTRACT:
        raise DeployError("manifest does not match the hard-coded approved current target contract")
    return targets


def require_repo_checks(checks: dict) -> None:
    if CTX.test_mode:
        return
    names = {str(name) for name in checks.get("names", [])}
    missing = sorted(REQUIRED_GITHUB_CHECKS - names)
    if missing:
        raise DeployError(
            f"required exact-commit GitHub checks are missing: {missing}"
        )


def describe_fingerprint(value: dict) -> str:
    if not value.get("exists"):
        return "ABSENT"
    return (
        f"sha={str(value.get('sha256'))[:12]} "
        f"uid={value.get('uid')} gid={value.get('gid')} mode={value.get('mode')}"
    )


def show_plan(plan: dict) -> None:
    print(f"PLAN commit={plan['commit']} expires={plan['expires_epoch']}")
    for row in plan["targets"]:
        print(f"{row['action'].upper():9} {row['id']:18} {row['target']}")
        print(f"  before : {describe_fingerprint(row['before'])}")
        print(f"  desired: {describe_fingerprint(row['desired'])}")
    print(f"CONFIRMATION FOR DEPLOY: {plan['short_commit']}")


def sync() -> None:
    require_normal_user()
    if git("branch", "--show-current") != "main":
        raise DeployError("sync requires branch main")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        raise DeployError("sync refuses a dirty tree")
    git("fetch", "--prune", "origin", "main")
    git("merge", "--ff-only", "origin/main")
    print(f"SYNC PASS {git('rev-parse', 'HEAD')}")


def test() -> None:
    require_normal_user()
    run(["make", "validate"], cwd=CTX.repo, capture=False, timeout=1200)
    print("TEST PASS")


def engine_source_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in ENGINE_SOURCE_FILES:
        path = CTX.repo / relative
        safe_file(path)
        git("ls-files", "--error-unmatch", "--", relative)
        result[relative] = sha256_file(path)
    return result


def stage_engine_release(
    stage: pathlib.Path,
    release: pathlib.Path,
    commit: str,
    source_hashes: dict[str, str],
) -> tuple[pathlib.Path, pathlib.Path]:
    stage.mkdir(parents=True, exist_ok=False)
    installed_files: dict[str, dict[str, str]] = {}
    source_by_name = {
        "rpi5_deploy.py": "scripts/rpi5_deploy.py",
        "rpi5_deploy_lib.py": "scripts/rpi5_deploy_lib.py",
        "rpi5_deploy_tx.py": "scripts/rpi5_deploy_tx.py",
    }
    for name, relative in source_by_name.items():
        source = CTX.repo / relative
        destination = stage / name
        shutil.copyfile(source, destination)
        installed_sha = sha256_file(destination)
        if installed_sha != source_hashes.get(relative):
            raise DeployError(f"staged deploy engine checksum mismatch: {name}")
        installed_files[name] = {
            "sha256": installed_sha,
            "mode": ENGINE_INSTALLED_FILES[name],
        }
    wrapper_path = stage / "rpi5-deploy-wrapper"
    wrapper_path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "exec /usr/bin/env -i "
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
        f"/usr/bin/python3 {release}/rpi5_deploy.py \"$@\"\n",
        encoding="utf-8",
    )
    metadata = {
        "schema": ENGINE_SCHEMA,
        "installed_from_commit": commit,
        "repo_path": str(CTX.repo),
        "repo_owner_uid": CTX.repo.stat().st_uid,
        "source_files": source_hashes,
        "installed_files": installed_files,
        "wrapper_sha256": sha256_file(wrapper_path),
    }
    metadata_path = stage / "engine-source.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata_path, wrapper_path


def install_engine(confirm: str) -> None:
    require_normal_user()
    if CTX.installed_engine:
        raise DeployError("install-engine must run from the repository controller")
    repository = repository_preflight(validate=True)
    require_target_contract()
    checks = github_checks(repository["head"])
    require_repo_checks(checks)
    host_identity(root_required=False)
    short_commit = repository["head"][:12]
    if confirm != short_commit:
        raise DeployError("engine confirmation must equal the exact 12-character main commit")
    source_hashes = engine_source_hashes()
    release = ENGINE_RELEASES / repository["head"]
    staging_release = ENGINE_RELEASES / f".staging-{repository['head']}-{os.getpid()}"
    system_wrapper = pathlib.Path("/usr/local/sbin/rpi5-deploy")
    system_wrapper_tmp = pathlib.Path(f"/usr/local/sbin/.rpi5-deploy-{os.getpid()}")
    with tempfile.TemporaryDirectory(prefix="rpi5-deploy-engine-") as temporary:
        stage = pathlib.Path(temporary) / "release"
        metadata_path, wrapper_path = stage_engine_release(
            stage, release, repository["head"], source_hashes
        )
        if engine_source_hashes() != source_hashes:
            raise DeployError("deploy engine source changed during installation staging")

        run(["sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0700",
             "/usr/local/libexec/rpi5-deploy"], capture=False)
        run(["sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0700",
             str(ENGINE_RELEASES)], capture=False)
        release_exists = run(["sudo", "test", "-e", str(release)], check=False, capture=False).returncode == 0
        if not release_exists:
            if run(["sudo", "test", "-e", str(staging_release)], check=False, capture=False).returncode == 0:
                raise DeployError("unexpected deploy engine staging path already exists")
            run(["sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0700",
                 str(staging_release)], capture=False)
            for name, mode in ENGINE_INSTALLED_FILES.items():
                run(["sudo", "install", "-o", "root", "-g", "root", "-m", mode,
                     str(stage / name), str(staging_release / name)], capture=False)
            run(["sudo", "install", "-o", "root", "-g", "root", "-m", "0400",
                 str(metadata_path), str(staging_release / "engine-source.json")], capture=False)
            run(["sudo", "mv", "--", str(staging_release), str(release)], capture=False)

        direct_engine = ["sudo", "/usr/bin/env", "-i",
                         "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                         "/usr/bin/python3", str(release / "rpi5_deploy.py"), "engine-status",
                         "--release-only"]
        run(direct_engine, capture=False, timeout=300)
        run(["sudo", "install", "-o", "root", "-g", "root", "-m", "0700",
             str(wrapper_path), str(system_wrapper_tmp)], capture=False)
        run(["sudo", "mv", "-f", "--", str(system_wrapper_tmp), str(system_wrapper)], capture=False)
        run(["sudo", str(system_wrapper), "engine-status"], capture=False, timeout=300)
    print(f"ENGINE INSTALL PASS commit={repository['head']} command={system_wrapper}")


def engine_status(release_only: bool) -> None:
    require_root()
    integrity = verify_engine_integrity()
    source = engine_source_preflight()
    scope = "release" if release_only else "system"
    print(f"ENGINE PASS scope={scope} release={integrity['release']} repo={CTX.repo}")
    print(f"source_files={source.get('source_count', 0)} installed_from={integrity['installed_from_commit']}")


def plan() -> None:
    require_root()
    with operation_lock():
        require_target_contract()
        payload = build_plan(write=False)
        require_repo_checks(payload["github_checks"])
        atomic_json(CTX.plan_path, payload)
        append_log(
            f"PLAN PASS commit={payload['short_commit']} "
            f"changed={sum(row['action'] == 'replace' for row in payload['targets'])} "
            f"plan={CTX.plan_path}"
        )
    show_plan(payload)


def deploy(confirm: str) -> None:
    require_root()
    with operation_lock():
        require_target_contract()
        payload = load_plan()
        if confirm != payload["short_commit"]:
            raise DeployError("confirmation must equal the exact 12-character planned commit")
        current = repository_preflight(validate=True)
        if current["head"] != payload["commit"]:
            raise DeployError("repository commit changed after plan")
        checks = github_checks(payload["commit"])
        require_repo_checks(checks)
        host_preflight()
        verify_plan_targets(payload)
        directory = apply_plan(payload)
    print(f"DEPLOY PASS {directory}")


def status() -> None:
    require_root()
    repository_preflight(validate=False)
    targets = require_target_contract()
    print(f"repository={EXPECTED_REPOSITORY}\nhead={git('rev-parse', 'HEAD')}")
    if CTX.plan_path.exists():
        try:
            payload = load_plan()
            print(f"plan={payload['short_commit']} expires_in={payload['expires_epoch'] - int(time.time())}s")
        except DeployError as exc:
            print(f"plan=INVALID ({exc})")
    else:
        print("plan=none")
    if CTX.latest_success_path.exists():
        try:
            _, transaction = latest_transaction()
            print(f"latest_transaction={transaction['id']} status={transaction['status']}")
        except DeployError as exc:
            print(f"latest_transaction=INVALID ({exc})")
    else:
        print("latest_transaction=none")
    for target in targets:
        current = fingerprint(CTX.rooted(target.target))
        source = CTX.repo / target.source
        safe_file(source)
        desired = expected_fingerprint(target, sha256_file(source))
        state = "MATCH" if current == desired else ("ABSENT" if not current["exists"] else "DRIFT")
        print(f"{state:6} {target.id:18} {target.target}")
        if state != "MATCH":
            print(f"  current: {describe_fingerprint(current)}")
            print(f"  desired: {describe_fingerprint(desired)}")


def rollback(confirm: str, latest: bool) -> None:
    require_root()
    if not latest:
        raise DeployError("V12 rollback supports only --latest")
    if confirm != "ROLLBACK":
        raise DeployError("rollback confirmation must be exactly ROLLBACK")
    with operation_lock():
        host_identity()
        if not CTX.test_mode:
            ensure_no_conflicts()
        manual_rollback()
        try:
            host_preflight()
        except DeployError as exc:
            append_log(f"ROLLBACK RESTORED; post-rollback health warning: {str(exc)[:500]}")
            raise DeployError(f"rollback restored the files, but post-rollback health still fails: {exc}") from exc
    print("ROLLBACK PASS")


def logs(lines: int) -> None:
    require_root()
    if not 1 <= lines <= 1000:
        raise DeployError("--lines must be between 1 and 1000")
    print(f"== {CTX.log_file} ==")
    print("\n".join(CTX.log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]) if CTX.log_file.exists() else "no deploy log")
    if shutil.which("journalctl") and not CTX.test_mode:
        print("== journald: rpi5-deploy ==")
        run(["journalctl", "-t", "rpi5-deploy", "-n", str(lines), "--no-pager", "-o", "short-iso"], capture=False, check=False, timeout=30)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="rpi5-deploy")
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("sync", "test", "plan", "status"):
        sub.add_parser(name)
    engine = sub.add_parser("engine-status")
    engine.add_argument("--release-only", action="store_true")
    installer = sub.add_parser("install-engine")
    installer.add_argument("--confirm", required=True)
    apply = sub.add_parser("deploy")
    apply.add_argument("--confirm", required=True)
    undo = sub.add_parser("rollback")
    undo.add_argument("--latest", action="store_true")
    undo.add_argument("--confirm", required=True)
    tail = sub.add_parser("logs")
    tail.add_argument("--lines", type=int, default=100)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "sync":
            sync()
        elif args.command == "test":
            test()
        elif args.command == "install-engine":
            install_engine(args.confirm)
        elif args.command == "engine-status":
            engine_status(args.release_only)
        elif args.command == "plan":
            plan()
        elif args.command == "deploy":
            deploy(args.confirm)
        elif args.command == "status":
            status()
        elif args.command == "rollback":
            rollback(args.confirm, args.latest)
        elif args.command == "logs":
            logs(args.lines)
    except (DeployError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        try:
            append_log(f"FAIL command={args.command} reason={str(exc)[:500]}")
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
