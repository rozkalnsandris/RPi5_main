"""Canonical failure-preserving GoatCounter v2.7.0 isolated proof operator.

This v2 entrypoint supersedes the v1 runtime entrypoint for any future proof.
It reuses the already-reviewed v1 pin, archive verification, HTTP count path
and SQLite privacy gate, but hardens setup diagnostics and failure evidence.

SOURCE ONLY. Running this program on rpi5 requires a fresh exact LIVE owner
authorization. No retry, fallback, install, service, production DB, secret or
Cloudflare authority is implied.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import ausmalwiese_goatcounter_isolated_probe_v1 as base


PASS = "PASS_SYNTHETIC_GOATCOUNTER_RUNTIME_ONLY_NOT_LIVE_OR_LEGAL_PROOF"

_STAGE_FAILURES = {
    ("db", "newdb"): "SYNTHETIC_DB_CREATE_FAILED",
    ("db", "create", "site"): "SYNTHETIC_SITE_CREATE_FAILED",
    ("db", "create", "apitoken"): "SYNTHETIC_API_TOKEN_CREATE_FAILED",
}


def _stage_failure_code(argv: tuple[str, ...]) -> str:
    for prefix, code in _STAGE_FAILURES.items():
        if argv[:len(prefix)] == prefix:
            return code
    return "SYNTHETIC_SETUP_STAGE_INVALID"


def _run_stage(
    binary: Path,
    root: Path,
    env: dict[str, str],
    *argv: str,
) -> None:
    """Run exactly one synthetic setup command and emit no upstream output."""
    failure_code = _stage_failure_code(tuple(argv))
    try:
        result = subprocess.run(
            [str(binary), *argv],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise base.RuntimeStop(failure_code)
    if result.returncode != 0:
        raise base.RuntimeStop(failure_code)


def _new_fixture_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix=base.PREFIX, dir="/tmp"))
    os.chmod(root, 0o700)
    return root


def _cleanup_success_fixture(root: Path) -> None:
    shutil.rmtree(root)


def _make_site_with_stage_diagnostics(
    binary: Path,
    root: Path,
    env: dict[str, str],
    db: Path,
) -> str:
    original_runner = base._run
    base._run = _run_stage
    try:
        return base._make_site(binary, root, env, db)
    finally:
        base._run = original_runner


def _run_fixture(release_archive_arg: str, root: Path) -> None:
    binary = base._verified_release_archive(release_archive_arg, root)
    env = base._isolated_env(root)
    base._version(binary, root, env)

    db = root / base.DB_NAME
    token = _make_site_with_stage_diagnostics(binary, root, env, db)
    (root / base.MARKER).write_bytes(base.MARKER_BYTES)

    port = base._free_loopback_port()
    proc = None
    try:
        proc = subprocess.Popen(
            [
                str(binary),
                "serve",
                "-db=sqlite+" + str(db),
                "-listen=127.0.0.1:" + str(port),
                "-tls=http",
                "-store-every=1",
            ],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        base._tcp_ready(port, proc)
        for _ in range(base.VIEWS):
            base._count_once(port, token)
        token = ""
    except OSError:
        raise base.RuntimeStop("LOOPBACK_PROCESS_ERROR")
    finally:
        if proc is not None:
            base._stop_server(proc)

    try:
        base.inspect_fixture(
            root,
            page_id=base.PAGE_ID,
            expected_views=base.VIEWS,
        )
    except base.ProbeStop:
        raise base.RuntimeStop("ISOLATED_SQLITE_PRIVACY_GATE")


def run_isolated(release_archive_arg: str) -> str:
    base._host_guard()
    root = _new_fixture_root()

    # Intentionally no finally cleanup. A setup/runtime/privacy failure leaves
    # the private 0700 synthetic fixture in /tmp for a later separately
    # authorized inspection or cleanup decision. Only a complete PASS reaches
    # the success cleanup call below.
    _run_fixture(release_archive_arg, root)
    _cleanup_success_fixture(root)
    return PASS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-archive", required=True)
    args = parser.parse_args()

    try:
        result = run_isolated(args.release_archive)
    except (base.RuntimeStop, OSError) as exc:
        code = str(exc) if isinstance(exc, base.RuntimeStop) else "ISOLATION_IO_ERROR"
        print("GOATCOUNTER_ISOLATED=STOP CODE=" + code)
        return 2

    print("GOATCOUNTER_ISOLATED=" + result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
