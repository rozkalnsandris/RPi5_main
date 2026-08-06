#!/usr/bin/env python3
"""CLI for reviewed, exact-commit RPi5_main deployment."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from rpi5_deploy_lib import (CTX, EXPECTED_REPOSITORY, DeployError, append_log, build_plan,
    ensure_no_conflicts, fingerprint, git, github_checks, host_preflight, load_plan,
    operation_lock, read_manifest, repository_preflight, require_normal_user, require_root,
    run, sha256_file, verify_plan_targets)
from rpi5_deploy_tx import apply_plan, latest_transaction, manual_rollback


def show_plan(plan: dict) -> None:
    print(f"PLAN commit={plan['commit']} expires={plan['expires_epoch']}")
    for row in plan["targets"]:
        before = row["before"]["sha256"] or "ABSENT"
        print(f"{row['action'].upper():9} {row['id']:18} {row['target']} before={before[:12]} source={row['source_sha256'][:12]} mode={row['mode']}")
    print(f"CONFIRMATION FOR DEPLOY: {plan['short_commit']}")


def sync() -> None:
    require_normal_user()
    if git("branch", "--show-current") != "main": raise DeployError("sync requires branch main")
    if git("status", "--porcelain=v1", "--untracked-files=all"): raise DeployError("sync refuses a dirty tree")
    git("fetch", "--prune", "origin", "main"); git("merge", "--ff-only", "origin/main")
    print(f"SYNC PASS {git('rev-parse', 'HEAD')}")


def test() -> None:
    require_normal_user(); run(["make", "validate"], cwd=CTX.repo, capture=False, timeout=1200)
    print("TEST PASS")


def plan() -> None:
    require_root()
    with operation_lock(): payload = build_plan(write=True)
    show_plan(payload)


def deploy(confirm: str) -> None:
    require_root()
    with operation_lock():
        payload = load_plan()
        if confirm != payload["short_commit"]: raise DeployError("confirmation must equal the exact 12-character planned commit")
        current = repository_preflight(validate=True)
        if current["head"] != payload["commit"]: raise DeployError("repository commit changed after plan")
        github_checks(payload["commit"]); host_preflight(); verify_plan_targets(payload)
        directory = apply_plan(payload)
    print(f"DEPLOY PASS {directory}")


def status() -> None:
    require_root(); targets, _ = read_manifest()
    print(f"repository={EXPECTED_REPOSITORY}\nhead={git('rev-parse', 'HEAD')}")
    if CTX.plan_path.exists():
        try:
            payload = load_plan(); print(f"plan={payload['short_commit']} expires_in={payload['expires_epoch'] - int(time.time())}s")
        except DeployError as exc: print(f"plan=INVALID ({exc})")
    else: print("plan=none")
    if CTX.latest_success_path.exists():
        try:
            _, tx = latest_transaction(); print(f"latest_transaction={tx['id']} status={tx['status']}")
        except DeployError as exc: print(f"latest_transaction=INVALID ({exc})")
    else: print("latest_transaction=none")
    for target in targets:
        current, source = fingerprint(CTX.rooted(target.target)), sha256_file(CTX.repo / target.source)
        state = "MATCH" if current["sha256"] == source else ("ABSENT" if not current["exists"] else "DRIFT")
        print(f"{state:6} {target.id:18} {target.target}")


def rollback(confirm: str, latest: bool) -> None:
    require_root()
    if not latest: raise DeployError("V12 rollback supports only --latest")
    if confirm != "ROLLBACK": raise DeployError("rollback confirmation must be exactly ROLLBACK")
    with operation_lock():
        if not CTX.test_mode:
            if os.uname().nodename != "rpi5": raise DeployError(f"unexpected hostname: {os.uname().nodename}")
            ensure_no_conflicts()
        manual_rollback()
        try: host_preflight()
        except DeployError as exc:
            append_log(f"ROLLBACK RESTORED; post-rollback health warning: {str(exc)[:500]}")
            raise DeployError(f"rollback restored the files, but post-rollback health still fails: {exc}") from exc
    print("ROLLBACK PASS")


def logs(lines: int) -> None:
    require_root()
    if not 1 <= lines <= 1000: raise DeployError("--lines must be between 1 and 1000")
    print(f"== {CTX.log_file} ==")
    print("\n".join(CTX.log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]) if CTX.log_file.exists() else "no deploy log")
    if shutil.which("journalctl") and not CTX.test_mode:
        print("== journald: rpi5-deploy ==")
        run(["journalctl", "-t", "rpi5-deploy", "-n", str(lines), "--no-pager", "-o", "short-iso"], capture=False, check=False, timeout=30)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="rpi5-deploy")
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("sync", "test", "plan", "status"): sub.add_parser(name)
    apply = sub.add_parser("deploy"); apply.add_argument("--confirm", required=True)
    undo = sub.add_parser("rollback"); undo.add_argument("--latest", action="store_true"); undo.add_argument("--confirm", required=True)
    tail = sub.add_parser("logs"); tail.add_argument("--lines", type=int, default=100)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "sync": sync()
        elif args.command == "test": test()
        elif args.command == "plan": plan()
        elif args.command == "deploy": deploy(args.confirm)
        elif args.command == "status": status()
        elif args.command == "rollback": rollback(args.confirm, args.latest)
        elif args.command == "logs": logs(args.lines)
    except (DeployError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        try: append_log(f"FAIL command={args.command} reason={str(exc)[:500]}")
        except Exception: pass
        return 1
    return 0


if __name__ == "__main__": raise SystemExit(main())
