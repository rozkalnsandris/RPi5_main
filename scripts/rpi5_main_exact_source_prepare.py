#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

REPOSITORY = "rozkalnsandris/RPi5_main"
CHECKOUT_PATH = Path("/home/andris/RPi5_main")
GIT = "/usr/bin/git"
CONFIRM_TEXT = "PREPARE-RPI5-MAIN-EXACT-SOURCE"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CANONICAL_ORIGINS = {
    "git@github.com:rozkalnsandris/RPi5_main.git",
    "https://github.com/rozkalnsandris/RPi5_main.git",
}
Runner = Callable[..., subprocess.CompletedProcess[Any]]


class PrepareError(RuntimeError):
    def __init__(self, reason: str, *, mutation_started: bool = False) -> None:
        super().__init__(reason)
        self.mutation_started = mutation_started


def _run(
    git_args: list[str],
    *,
    runner: Runner = subprocess.run,
    timeout: int = 30,
) -> subprocess.CompletedProcess[Any]:
    return runner(
        [GIT, "-C", str(CHECKOUT_PATH), *git_args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout,
    )


def _must(
    git_args: list[str],
    *,
    runner: Runner = subprocess.run,
    mutation_started: bool = False,
) -> str:
    completed = _run(git_args, runner=runner)
    if completed.returncode != 0:
        raise PrepareError("git_command_failed", mutation_started=mutation_started)
    return completed.stdout.strip()


def _identity(
    expected_main: str,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    if not SHA_RE.fullmatch(expected_main):
        raise PrepareError("expected_main_invalid")
    if not CHECKOUT_PATH.is_dir():
        raise PrepareError("checkout_missing")

    top = _must(["rev-parse", "--show-toplevel"], runner=runner)
    if Path(top).resolve() != CHECKOUT_PATH.resolve():
        raise PrepareError("checkout_identity_mismatch")
    if _must(["branch", "--show-current"], runner=runner) != "main":
        raise PrepareError("branch_not_main")
    if _must(["remote", "get-url", "origin"], runner=runner) not in CANONICAL_ORIGINS:
        raise PrepareError("origin_not_canonical")
    if _must(["status", "--porcelain=v1", "--untracked-files=all"], runner=runner):
        raise PrepareError("checkout_dirty")

    current = _must(["rev-parse", "HEAD"], runner=runner)
    if not SHA_RE.fullmatch(current):
        raise PrepareError("current_head_invalid")

    target_check = _run(["cat-file", "-e", f"{expected_main}^{{commit}}"], runner=runner)
    target_present = target_check.returncode == 0
    if target_check.returncode not in {0, 1, 128}:
        raise PrepareError("target_object_check_failed")
    if target_present:
        ancestor = _run(
            ["merge-base", "--is-ancestor", current, expected_main],
            runner=runner,
        )
        if ancestor.returncode != 0:
            raise PrepareError("target_not_fast_forward")

    return {
        "current_sha": current,
        "target_present": target_present,
        "fetch_required": current != expected_main,
        "already_current": current == expected_main,
    }


def preflight(
    expected_main: str,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    state = _identity(expected_main, runner=runner)
    return {
        "schema": "rozkalns.rpi5-main.exact-source-preparation-evidence.v1",
        "repository": REPOSITORY,
        "expected_main": expected_main,
        "current_sha": state["current_sha"],
        "result": "PASS",
        "apply_ready": True,
        "fetch_required": state["fetch_required"],
        "mutation_performed": False,
    }


def apply(
    expected_main: str,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    before = _identity(expected_main, runner=runner)
    if before["already_current"]:
        return {
            "schema": "rozkalns.rpi5-main.exact-source-preparation-evidence.v1",
            "repository": REPOSITORY,
            "expected_main": expected_main,
            "current_sha": expected_main,
            "result": "PASS",
            "apply_ready": False,
            "fetch_required": False,
            "mutation_performed": False,
        }

    fetched = _run(
        ["fetch", "--no-tags", "origin", "main"],
        runner=runner,
        timeout=120,
    )
    if fetched.returncode != 0:
        raise PrepareError("fetch_failed", mutation_started=True)

    if _must(
        ["branch", "--show-current"],
        runner=runner,
        mutation_started=True,
    ) != "main":
        raise PrepareError("branch_drift_after_fetch", mutation_started=True)
    if _must(
        ["remote", "get-url", "origin"],
        runner=runner,
        mutation_started=True,
    ) not in CANONICAL_ORIGINS:
        raise PrepareError("origin_drift_after_fetch", mutation_started=True)
    if _must(
        ["status", "--porcelain=v1", "--untracked-files=all"],
        runner=runner,
        mutation_started=True,
    ):
        raise PrepareError("checkout_dirty_after_fetch", mutation_started=True)

    current = _must(["rev-parse", "HEAD"], runner=runner, mutation_started=True)
    if current != before["current_sha"]:
        raise PrepareError("head_drift_after_fetch", mutation_started=True)

    remote_main = _must(
        ["rev-parse", "refs/remotes/origin/main"],
        runner=runner,
        mutation_started=True,
    )
    if remote_main != expected_main:
        raise PrepareError("origin_main_target_mismatch", mutation_started=True)

    ancestor = _run(
        ["merge-base", "--is-ancestor", current, expected_main],
        runner=runner,
    )
    if ancestor.returncode != 0:
        raise PrepareError("target_not_fast_forward", mutation_started=True)

    merged = _run(
        ["merge", "--ff-only", expected_main],
        runner=runner,
        timeout=120,
    )
    if merged.returncode != 0:
        raise PrepareError("ff_only_merge_failed", mutation_started=True)

    after = _identity(expected_main, runner=runner)
    if after["current_sha"] != expected_main:
        raise PrepareError("postcondition_failed", mutation_started=True)

    return {
        "schema": "rozkalns.rpi5-main.exact-source-preparation-evidence.v1",
        "repository": REPOSITORY,
        "expected_main": expected_main,
        "current_sha": expected_main,
        "result": "PASS",
        "apply_ready": False,
        "fetch_required": True,
        "mutation_performed": True,
    }


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
                raise PrepareError("apply_confirmation_missing")
            report = apply(args.expected_main)
        else:
            report = preflight(args.expected_main)
    except PrepareError as exc:
        print(
            json.dumps(
                {
                    "schema": "rozkalns.rpi5-main.exact-source-preparation-evidence.v1",
                    "repository": REPOSITORY,
                    "expected_main": args.expected_main,
                    "result": "STOP_ERROR" if exc.mutation_started else "BLOCKED",
                    "reason": str(exc),
                    "apply_ready": False,
                    "mutation_performed": exc.mutation_started,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 4 if exc.mutation_started else 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
