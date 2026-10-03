#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

REGISTRY_SRC = "ops/deploy/simple-deploy-targets-v1.json"
COMPOSE_SRC = "ops/deploy/simple-deploy-compose/coloring-pages-public.yml"

REGISTRY = Path("/etc/rozkalns-simple-deployer/targets.json")
IDENTITY = Path("/etc/rozkalns-simple-deployer/identity.json")
COMPOSE = Path("/etc/rozkalns-simple-deployer/compose/coloring-pages-public.yml")

REGISTRY_STAGE = Path("/etc/rozkalns-simple-deployer/.targets.json.coloring-pages.staged")
IDENTITY_STAGE = Path("/etc/rozkalns-simple-deployer/.identity.json.coloring-pages.staged")
COMPOSE_STAGE = Path("/etc/rozkalns-simple-deployer/compose/.coloring-pages-public.yml.staged")

BASELINE_REGISTRY = "46667f60470d032cd60f356d1fcc32596c75d6dfc38f9d9539531768733c8e6c"
BASELINE_IDENTITY = "68be71f09292496bd4ff5dbe8f322804df59065bc41cfa52bdb5a72ddc99e3a2"
BASELINE_COMPOSE = "77c71da44896b393002b7a13449d6fbaca76b38c6d982580d23156b674fe2941"

DESIRED_REGISTRY = "e68fb9d674dbc044454563c8c8ba74c757c958ea78ff980dd0003b64d7e7bd7d"
DESIRED_COMPOSE = "142c30bdd1080de90360f287e5b6fae27611c535caef0a41a09a998528bcbbc2"

TARGET_ALIAS = "coloring-pages-public-rpi5"


class AlignError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise AlignError(message)


def git(*args: str) -> bytes:
    result = subprocess.run(
        ["/usr/bin/git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    if result.returncode != 0:
        fail("Git source validation failed")
    return result.stdout


def require_source(expected_sha: str) -> None:
    if not SHA_RE.fullmatch(expected_sha):
        fail("expected source SHA must be lowercase 40-character hex")
    if git("rev-parse", "HEAD").decode().strip() != expected_sha:
        fail("checkout HEAD does not match expected source SHA")
    if git("branch", "--show-current").decode().strip() != "main":
        fail("checkout must be on main")
    if git("remote", "get-url", "origin").decode().strip() != ORIGIN:
        fail("checkout origin drifted")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        fail("checkout must be clean")


def identity_bytes(source_sha: str) -> bytes:
    value = {
        "schema": "rozkalns.rpi5-main.simple-deploy.identity.v1",
        "repository": "rozkalnsandris/RPi5_main",
        "source_sha": source_sha,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def validate_registry(data: bytes) -> None:
    if sha256(data) != DESIRED_REGISTRY:
        fail("desired registry source hash drifted")
    value = json.loads(data)
    matches = [x for x in value["targets"] if x["target_alias"] == TARGET_ALIAS]
    if len(matches) != 1:
        fail("Coloring Pages target identity drifted")
    target = matches[0]
    expected = {
        "consumer_repository": "rozkalnsandris/coloring-pages",
        "persistent_volumes": ["coloring_pages_content"],
        "registry_pull_profile": "public-anonymous-pull",
    }
    for key, wanted in expected.items():
        if target.get(key) != wanted:
            fail(f"Coloring Pages target field drifted: {key}")
    if target["compose"].get("file") != "coloring-pages-public.yml":
        fail("Coloring Pages compose filename drifted")
    if target["compose"].get("file_sha256") != DESIRED_COMPOSE:
        fail("Coloring Pages compose hash binding drifted")
    if target["health"].get("liveness_url") != "http://127.0.0.1:9191/health":
        fail("Coloring Pages liveness URL drifted")
    if target["health"].get("readiness_url") != "http://127.0.0.1:9191/ready":
        fail("Coloring Pages readiness URL drifted")


def desired_bytes(expected_sha: str) -> tuple[bytes, bytes, bytes]:
    require_source(expected_sha)
    registry = git("show", f"{expected_sha}:{REGISTRY_SRC}")
    compose = git("show", f"{expected_sha}:{COMPOSE_SRC}")
    validate_registry(registry)
    if sha256(compose) != DESIRED_COMPOSE:
        fail("desired Coloring Pages Compose source hash drifted")
    return registry, identity_bytes(expected_sha), compose


def read_fixed(path: Path, mode: int, expected_hash: str, uid: int, gid: int) -> bytes:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        fail(f"required installed file is absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        fail(f"required installed file type drifted: {path}")
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (uid, gid, mode):
        fail(f"required installed file metadata drifted: {path}")
    data = path.read_bytes()
    if sha256(data) != expected_hash:
        fail(f"required installed file hash drifted: {path}")
    return data


def require_dir(path: Path, uid: int, gid: int) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        fail(f"required directory type drifted: {path}")
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (uid, gid, 0o755):
        fail(f"required directory metadata drifted: {path}")


def preflight(
    *,
    uid: int = 0,
    gid: int = 0,
    registry: Path = REGISTRY,
    identity: Path = IDENTITY,
    compose: Path = COMPOSE,
    registry_stage: Path = REGISTRY_STAGE,
    identity_stage: Path = IDENTITY_STAGE,
    compose_stage: Path = COMPOSE_STAGE,
) -> tuple[bytes, bytes, bytes]:
    require_dir(registry.parent, uid, gid)
    require_dir(compose.parent, uid, gid)
    current = (
        read_fixed(registry, 0o444, BASELINE_REGISTRY, uid, gid),
        read_fixed(identity, 0o444, BASELINE_IDENTITY, uid, gid),
        read_fixed(compose, 0o644, BASELINE_COMPOSE, uid, gid),
    )
    for stage in (registry_stage, identity_stage, compose_stage):
        if os.path.lexists(stage):
            fail(f"fixed staging path already exists: {stage}")
    return current


def stage(path: Path, data: bytes, mode: int, uid: int, gid: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
    finally:
        os.close(fd)


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def apply(
    wanted: tuple[bytes, bytes, bytes],
    current: tuple[bytes, bytes, bytes],
    *,
    uid: int = 0,
    gid: int = 0,
    registry: Path = REGISTRY,
    identity: Path = IDENTITY,
    compose: Path = COMPOSE,
    registry_stage: Path = REGISTRY_STAGE,
    identity_stage: Path = IDENTITY_STAGE,
    compose_stage: Path = COMPOSE_STAGE,
) -> None:
    wanted_registry, wanted_identity, wanted_compose = wanted

    # All staging is completed before replacing any installed file.
    stage(compose_stage, wanted_compose, 0o644, uid, gid)
    stage(registry_stage, wanted_registry, 0o444, uid, gid)
    stage(identity_stage, wanted_identity, 0o444, uid, gid)

    if (
        registry.read_bytes(),
        identity.read_bytes(),
        compose.read_bytes(),
    ) != current:
        fail("installed baseline changed after preflight")

    os.replace(compose_stage, compose)
    fsync_dir(compose.parent)
    os.replace(registry_stage, registry)
    fsync_dir(registry.parent)
    os.replace(identity_stage, identity)
    fsync_dir(identity.parent)

    if compose.read_bytes() != wanted_compose:
        fail("Compose postcondition failed")
    if registry.read_bytes() != wanted_registry:
        fail("registry postcondition failed")
    if identity.read_bytes() != wanted_identity:
        fail("identity postcondition failed")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Align exactly three installed Coloring Pages SIMPLE-DEPLOY files.")
    p.add_argument("--expected-source-sha", required=True)
    p.add_argument("--apply", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if os.geteuid() != 0:
            fail("alignment helper must run as root")
        wanted = desired_bytes(args.expected_source_sha)
        current = preflight()
        if not args.apply:
            print("COLORING_PAGES_SIMPLE_DEPLOY_ALIGNMENT=READY")
            return 0
        apply(wanted, current)
    except (AlignError, OSError, json.JSONDecodeError) as exc:
        print(f"COLORING_PAGES_SIMPLE_DEPLOY_ALIGNMENT=FAIL error={exc}", file=sys.stderr)
        return 1

    print(
        "COLORING_PAGES_SIMPLE_DEPLOY_ALIGNMENT=PASS "
        f"source_sha={args.expected_source_sha} files_replaced=3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
