#!/usr/bin/env python3
"""SOURCE ONLY: future installer for the fixed Stats Worker deploy runtime.

No credential is read, created or modified. No Cloudflare request is made.
Repository execution is unprivileged; root writes use fixed sudo commands only
after exact RPi5_main and application-source preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

SOURCE_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = SOURCE_ROOT.parent / "coloring-pages"
REPO = "rozkalnsandris/RPi5_main"
APP_REPO = "rozkalnsandris/coloring-pages"
APP_SHA = "e6c1a4a4fa9f8a9c82dc73babd6b4a2a1bdd4d63"

LAUNCHER_REL = "scripts/ausmalwiese_stats_worker_runtime_v1.py"
PROVISIONER_REL = "scripts/ausmalwiese_stats_worker_provisioner_v1.py"
CORE_REL = "scripts/ausmalwiese_stats_worker_exact_deploy.py"
SOURCE_PATHS = (LAUNCHER_REL, PROVISIONER_REL, CORE_REL)

WORKER_REL = "cloudflare/stats-worker.js"
CONFIG_REL = "cloudflare/wrangler.stats-worker.jsonc"
WORKER_BLOB = "c2ac9da6e0701103e0041b30db7dfbea4298f96c"
CONFIG_BLOB = "3733263a391274f2b6b0f2023c8656565bde8e1a"

GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
STAT = "/usr/bin/stat"
TEST = "/usr/bin/test"
TRUE = "/usr/bin/true"
MKDIR = "/usr/bin/mkdir"
INSTALL = "/usr/bin/install"
SHA256SUM = "/usr/bin/sha256sum"

EXE = "/usr/local/sbin/rpi5-ausmalwiese-stats-worker-deploy"
PROVISION = "/usr/local/sbin/rpi5-ausmalwiese-stats-worker-deploy-provision"
LIB = "/usr/local/libexec/rpi5-ausmalwiese-stats-worker-deploy"
CORE = LIB + "/core.py"
WORKER = LIB + "/stats-worker.js"
CONFIG = LIB + "/wrangler.stats-worker.jsonc"
RELEASE = LIB + "/release.json"

PARENTS = ("/usr", "/usr/local", "/usr/local/sbin", "/usr/local/libexec")
TARGETS = (EXE, PROVISION, LIB, CORE, WORKER, CONFIG, RELEASE)
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
CONFIRM = "INSTALL-AUSMALWIESE-STATS-WORKER-RUNTIME"
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


class Stop(Exception):
    """Stable non-sensitive installer failure."""


def invoke(argv, data=None, *, runner=subprocess.run, timeout=25):
    try:
        return runner(
            list(argv),
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env=CLEAN_ENV,
        )
    except Exception:
        raise Stop("command_unavailable") from None


def git(root: Path, args, *, runner=subprocess.run) -> bytes:
    result = invoke([GIT, "-C", str(root), *args], runner=runner)
    if (
        result.returncode != 0
        or type(result.stdout) is not bytes
        or len(result.stdout) > 524288
    ):
        raise Stop("git_preflight_failed")
    return result.stdout


def text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8").strip()
    except UnicodeError:
        raise Stop("git_output_invalid") from None


def trusted_origin(root: Path, repository: str, *, runner=subprocess.run) -> None:
    origin = text(git(root, ["remote", "get-url", "origin"], runner=runner)).rstrip("/")
    https_ok = origin in (
        "https://github.com/" + repository,
        "https://github.com/" + repository + ".git",
    )
    user, sep, remote = origin.partition("@")
    host, colon, project = remote.partition(":") if sep else ("", "", "")
    ssh_ok = (
        user == "git"
        and sep == "@"
        and host == "github.com"
        and colon == ":"
        and project in (repository, repository + ".git")
    )
    if not (https_ok or ssh_ok):
        raise Stop("origin_mismatch")


def checkout(expected_main: str, *, runner=subprocess.run) -> None:
    if os.geteuid() == 0:
        raise Stop("must_be_unprivileged")
    if not isinstance(expected_main, str) or SHA40.fullmatch(expected_main) is None:
        raise Stop("expected_main_invalid")
    if text(git(SOURCE_ROOT, ["rev-parse", "--show-toplevel"], runner=runner)) != str(SOURCE_ROOT):
        raise Stop("checkout_mismatch")
    if text(git(SOURCE_ROOT, ["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner)) != "main":
        raise Stop("not_main")
    if text(git(SOURCE_ROOT, ["rev-parse", "HEAD"], runner=runner)) != expected_main:
        raise Stop("main_drift")
    if git(SOURCE_ROOT, ["status", "--porcelain=v1", "-z", "--untracked-files=all"], runner=runner):
        raise Stop("dirty_checkout")
    trusted_origin(SOURCE_ROOT, REPO, runner=runner)


def application_checkout(*, runner=subprocess.run) -> None:
    if text(git(APP_ROOT, ["rev-parse", "--show-toplevel"], runner=runner)) != str(APP_ROOT):
        raise Stop("application_checkout_mismatch")
    if text(git(APP_ROOT, ["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner)) != "main":
        raise Stop("application_not_main")
    if text(git(APP_ROOT, ["rev-parse", "HEAD"], runner=runner)) != APP_SHA:
        raise Stop("application_main_drift")
    if git(
        APP_ROOT,
        [
            "status", "--porcelain=v1", "-z", "--untracked-files=all", "--",
            WORKER_REL, CONFIG_REL,
        ],
        runner=runner,
    ):
        raise Stop("application_relevant_paths_dirty")
    trusted_origin(APP_ROOT, APP_REPO, runner=runner)


def tracked(root: Path, rel: str, allowed: tuple[str, ...], *, runner=subprocess.run) -> bytes:
    if rel not in allowed:
        raise Stop("path_scope_invalid")
    path = root / rel
    try:
        info = path.lstat()
        raw = path.read_bytes()
    except OSError:
        raise Stop("source_unavailable") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or not 0 < info.st_size <= 196608
        or raw != git(root, ["show", "HEAD:" + rel], runner=runner)
    ):
        raise Stop("source_identity_mismatch")
    return raw


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def release_bytes(
    expected_main: str,
    launcher: bytes,
    provisioner: bytes,
    core: bytes,
    worker: bytes,
    config: bytes,
) -> bytes:
    if git_blob(worker) != WORKER_BLOB or git_blob(config) != CONFIG_BLOB:
        raise Stop("application_blob_mismatch")
    record = {
        "schema_version": 1,
        "repository": REPO,
        "source_sha": expected_main,
        "app_repository": APP_REPO,
        "app_sha": APP_SHA,
        "worker": "coloring-pages-stats-v1",
        "worker_blob": WORKER_BLOB,
        "config_blob": CONFIG_BLOB,
        "launcher_sha256": hashlib.sha256(launcher).hexdigest(),
        "provisioner_sha256": hashlib.sha256(provisioner).hexdigest(),
        "core_sha256": hashlib.sha256(core).hexdigest(),
        "worker_sha256": hashlib.sha256(worker).hexdigest(),
        "config_sha256": hashlib.sha256(config).hexdigest(),
    }
    return (
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def sudo_read(args, *, runner=subprocess.run) -> str:
    result = invoke([SUDO, "-n", *args], runner=runner)
    if result.returncode or type(result.stdout) is not bytes or len(result.stdout) > 512:
        raise Stop("sudo_read_failed")
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeError:
        raise Stop("sudo_read_failed") from None


def host_preflight(*, runner=subprocess.run) -> None:
    sudo_read([TRUE], runner=runner)
    for path in PARENTS:
        value = sudo_read([STAT, "-c", "%u:%g:%a:%F", "--", path], runner=runner)
        parts = value.split(":")
        if len(parts) != 4 or parts[:2] != ["0", "0"] or parts[3] != "directory":
            raise Stop("unsafe_parent")
        try:
            mode = int(parts[2], 8)
        except ValueError:
            raise Stop("unsafe_parent") from None
        if mode & 0o022:
            raise Stop("unsafe_parent")
    for path in TARGETS:
        for flag in ("-e", "-L"):
            result = invoke([SUDO, "-n", TEST, flag, path], runner=runner)
            if result.returncode == 0:
                raise Stop("target_already_exists")
            if result.returncode != 1:
                raise Stop("target_state_unknown")


def preflight(expected_main: str, *, runner=subprocess.run):
    checkout(expected_main, runner=runner)
    application_checkout(runner=runner)
    launcher = tracked(SOURCE_ROOT, LAUNCHER_REL, SOURCE_PATHS, runner=runner)
    provisioner = tracked(SOURCE_ROOT, PROVISIONER_REL, SOURCE_PATHS, runner=runner)
    core = tracked(SOURCE_ROOT, CORE_REL, SOURCE_PATHS, runner=runner)
    worker = tracked(APP_ROOT, WORKER_REL, (WORKER_REL, CONFIG_REL), runner=runner)
    config = tracked(APP_ROOT, CONFIG_REL, (WORKER_REL, CONFIG_REL), runner=runner)
    if git_blob(worker) != WORKER_BLOB or git_blob(config) != CONFIG_BLOB:
        raise Stop("application_blob_mismatch")
    release = release_bytes(
        expected_main, launcher, provisioner, core, worker, config
    )
    host_preflight(runner=runner)
    return launcher, provisioner, core, worker, config, release


def write_once(args, payload=None, *, runner=subprocess.run) -> None:
    result = invoke([SUDO, "-n", *args], payload, runner=runner)
    if result.returncode != 0:
        raise Stop("post_dispatch_unknown_state")


def post_verify(entries, *, runner=subprocess.run) -> None:
    for path, mode, payload in entries:
        value = sudo_read(
            [STAT, "-c", "%u:%g:%a:%F:%h", "--", path],
            runner=runner,
        )
        if payload is None:
            if value.split(":")[:4] != ["0", "0", mode, "directory"]:
                raise Stop("post_dispatch_unknown_state")
            continue
        if value != f"0:0:{mode}:regular file:1":
            raise Stop("post_dispatch_unknown_state")
        expected = hashlib.sha256(payload).hexdigest()
        observed = sudo_read([SHA256SUM, "--", path], runner=runner)
        if observed != f"{expected}  {path}":
            raise Stop("post_dispatch_unknown_state")


def apply(expected_main: str, *, runner=subprocess.run) -> None:
    launcher, provisioner, core, worker, config, release = preflight(
        expected_main, runner=runner
    )
    files = (
        (EXE, "500", launcher),
        (PROVISION, "500", provisioner),
        (CORE, "400", core),
        (WORKER, "400", worker),
        (CONFIG, "400", config),
        (RELEASE, "400", release),
    )
    try:
        write_once([MKDIR, "-m", "0700", "--", LIB], runner=runner)
        for path, mode, payload in files:
            write_once(
                [
                    INSTALL, "-T", "-o", "root", "-g", "root",
                    "-m", "0" + mode, "--", "/dev/stdin", path,
                ],
                payload,
                runner=runner,
            )
        post_verify(((LIB, "700", None), *files), runner=runner)
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Source-only Stats Worker deploy runtime installer"
    )
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            if args.confirm != CONFIRM:
                raise Stop("confirmation_missing")
            apply(args.expected_main)
            result = {"status": "PASS", "mutation_started": True}
        else:
            if args.confirm:
                raise Stop("confirm_requires_apply")
            values = preflight(args.expected_main)
            result = {
                "status": "PREFLIGHT_PASS",
                "mutation_started": False,
                "release_sha256": hashlib.sha256(values[-1]).hexdigest(),
                "app_sha": APP_SHA,
                "worker_blob": WORKER_BLOB,
                "config_blob": CONFIG_BLOB,
            }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Stop as exc:
        uncertain = str(exc) == "post_dispatch_unknown_state"
        print(json.dumps({
            "status": "STOP_ERROR" if uncertain else "BLOCKED",
            "reason": str(exc),
            "mutation_state": "unknown" if uncertain else "not_started",
        }, sort_keys=True, separators=(",", ":")))
        return 4 if uncertain else 3


if __name__ == "__main__":
    raise SystemExit(main())
