#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
INSTALLER = ROOT / "scripts/install-coloring-pages-admin-publish-v1.sh"
INSTALL_CONFIRM = "OWNER-AUTHORIZED-AUSMALWIESE-ADMIN-ZIP-PUBLISHER-INSTALL"
SERVICE = "coloring-pages-admin-publish.service"
BASE_URL = "http://127.0.0.1:8765"
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


class DeployError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise DeployError(message)


def run_command(argv: list[str], timeout_seconds: int = 30) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout_seconds,
        env=ENV,
    )


def git(*args: str) -> str:
    result = run_command([
        "/usr/bin/git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), *args
    ], 10)
    if result.returncode != 0:
        fail("Git source validation failed")
    return result.stdout.decode("utf-8", "strict").strip()


def require_source(expected_sha: str) -> None:
    if not SHA_RE.fullmatch(expected_sha):
        fail("expected source SHA must be lowercase 40-character hex")
    if git("rev-parse", "HEAD") != expected_sha:
        fail("checkout HEAD does not match expected source SHA")
    if git("branch", "--show-current") != "main":
        fail("checkout must be on main")
    if git("remote", "get-url", "origin") != ORIGIN:
        fail("checkout origin drifted")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        fail("checkout must be clean")


def installer_argv(expected_sha: str) -> list[str]:
    if not SHA_RE.fullmatch(expected_sha):
        fail("expected source SHA must be lowercase 40-character hex")
    return [
        "/usr/bin/bash",
        str(INSTALLER),
        expected_sha,
        INSTALL_CONFIRM,
        "full",
    ]


def http_bytes(path: str) -> bytes:
    request = Request(
        BASE_URL + path,
        headers={"X-Ausmalwiese-Admin": "1"},
        method="GET",
    )
    with urlopen(request, timeout=3) as response:
        if response.status != 200:
            fail(f"local endpoint failed: {path}")
        data = response.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024:
        fail(f"local endpoint response too large: {path}")
    return data


def http_json(path: str):
    try:
        return json.loads(http_bytes(path))
    except (UnicodeError, json.JSONDecodeError):
        fail(f"local endpoint JSON invalid: {path}")


def validate_catalog(payload) -> None:
    if not isinstance(payload, dict):
        fail("catalog response model invalid")
    if not isinstance(payload.get("count"), int) or payload["count"] < 0:
        fail("catalog count invalid")
    if not isinstance(payload.get("entries"), list) or len(payload["entries"]) != payload["count"]:
        fail("catalog entries invalid")
    if not isinstance(payload.get("catalog_sha256"), str) or not HASH_RE.fullmatch(payload["catalog_sha256"]):
        fail("catalog hash invalid")


def validate_archive(payload) -> None:
    if not isinstance(payload, dict):
        fail("archive response model invalid")
    if not isinstance(payload.get("count"), int) or payload["count"] < 0:
        fail("archive count invalid")
    if not isinstance(payload.get("entries"), list) or len(payload["entries"]) != payload["count"]:
        fail("archive entries invalid")
    if not isinstance(payload.get("catalog_sha256"), str) or not HASH_RE.fullmatch(payload["catalog_sha256"]):
        fail("archive catalog hash invalid")


def validate_activity(payload) -> None:
    if not isinstance(payload, dict):
        fail("activity response model invalid")
    if not isinstance(payload.get("count"), int) or not (0 <= payload["count"] <= 200):
        fail("activity count invalid")
    if not isinstance(payload.get("events"), list) or len(payload["events"]) != payload["count"]:
        fail("activity events invalid")


def post_verify(command_runner=run_command, http_get=http_json, homepage_get=http_bytes) -> None:
    service = command_runner(["/usr/bin/systemctl", "is-active", "--quiet", SERVICE], 10)
    if service.returncode != 0:
        fail("admin service is not active")
    homepage_get("/")
    validate_catalog(http_get("/api/catalog"))
    validate_archive(http_get("/api/archive"))
    validate_activity(http_get("/api/activity"))


def deploy(expected_sha: str, command_runner=run_command, verifier=post_verify) -> None:
    result = command_runner(installer_argv(expected_sha), 60)
    if result.returncode != 0:
        fail("reviewed ADMIN installer failed")
    verifier(command_runner=command_runner)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Deploy exactly the reviewed Ausmalwiese ADMIN service.")
    p.add_argument("--expected-source-sha", required=True)
    p.add_argument("--apply", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if os.geteuid() != 0:
            fail("ADMIN deploy wrapper must run as root")
        if not args.apply:
            fail("--apply is required")
        require_source(args.expected_source_sha)
        deploy(args.expected_source_sha)
    except (DeployError, OSError, subprocess.SubprocessError) as exc:
        print(f"AUSMALWIESE_ADMIN_SIMPLE_DEPLOY=FAIL error={exc}", file=sys.stderr)
        return 1

    print(
        "AUSMALWIESE_ADMIN_SIMPLE_DEPLOY=PASS "
        f"source_sha={args.expected_source_sha} service=active "
        "catalog=valid archive=valid activity=valid"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
