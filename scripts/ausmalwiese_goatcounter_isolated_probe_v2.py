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
import contextlib
import json
import os
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import ausmalwiese_goatcounter_isolated_probe_v1 as base
import ausmalwiese_goatcounter_offline_privacy_probe_v1 as privacy


PASS = "PASS_SYNTHETIC_GOATCOUNTER_RUNTIME_ONLY_NOT_LIVE_OR_LEGAL_PROOF"

_STARTUP_STDERR_LIMIT = 8192
_STARTUP_STDERR_CHUNK = 1024


class _BoundedStderrCapture:
    """Drain child stderr while retaining only a small startup prefix."""

    def __init__(self, stream, limit: int = _STARTUP_STDERR_LIMIT) -> None:
        self._stream = stream
        self._limit = limit
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._retain = True
        self._thread = threading.Thread(
            target=self._drain,
            name="goatcounter-startup-stderr",
            daemon=True,
        )
        self._thread.start()

    def _drain(self) -> None:
        try:
            while True:
                chunk = self._stream.read(_STARTUP_STDERR_CHUNK)
                if not chunk:
                    return
                with self._lock:
                    if not self._retain or len(self._buffer) >= self._limit:
                        continue
                    remaining = self._limit - len(self._buffer)
                    self._buffer.extend(chunk[:remaining])
        except (OSError, ValueError):
            return

    def snapshot(self) -> bytes:
        with self._lock:
            return bytes(self._buffer)

    def discard(self) -> None:
        with self._lock:
            self._retain = False
            self._buffer.clear()

    def wait(self, timeout: float = 1.0) -> None:
        self._thread.join(timeout)


def _startup_exit_failure_code(exit_code: int, stderr_prefix: bytes) -> str:
    """Reduce a pre-ready child exit to fixed, non-sensitive evidence."""
    lower = stderr_prefix.lower()
    listen_error = b"zhttp.serve: listen tcp" in lower
    if listen_error and b"bind: address already in use" in lower:
        return "SERVER_STARTUP_BIND_ADDRESS_IN_USE"
    if listen_error and b"bind: permission denied" in lower:
        return "SERVER_STARTUP_BIND_PERMISSION_DENIED"
    if exit_code == 1:
        if b"zdb.connect:" in lower or b" database at " in lower:
            return "SERVER_STARTUP_DATABASE_ERROR"
        if b"sites.list:" in lower:
            return "SERVER_STARTUP_SITE_LIST_ERROR"
        if b"template:" in lower:
            return "SERVER_STARTUP_TEMPLATE_ERROR"
        if b"zhttp.serve:" in lower:
            return "SERVER_STARTUP_ZHTTP_SETUP_ERROR"
    if exit_code == 0:
        return "SERVER_STARTUP_CLEAN_EXIT"
    if exit_code == 1:
        return "SERVER_STARTUP_GOATCOUNTER_COMMAND_ERROR"
    if exit_code == 2:
        return "SERVER_STARTUP_GO_RUNTIME_FAILURE"
    if exit_code == 66:
        return "SERVER_STARTUP_ZHTTP_SERVE_ERROR"
    if exit_code == 99:
        return "SERVER_STARTUP_FORCE_KILL_EXIT"
    if exit_code < 0:
        return "SERVER_STARTUP_SIGNAL_EXIT"
    return "SERVER_STARTUP_OTHER_NONZERO_EXIT"


_STAGE_FAILURES = {
    ("db", "newdb"): "SYNTHETIC_DB_CREATE_FAILED",
    ("db", "create", "site"): "SYNTHETIC_SITE_CREATE_FAILED",
    ("db", "create", "apitoken"): "SYNTHETIC_API_TOKEN_CREATE_FAILED",
    ("db", "update", "site"): "SYNTHETIC_SITE_DESERIALIZATION_FAILED",
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


def _pre_shutdown_exit_failure_code(exit_code: int) -> str:
    """Map an already-exited child to one stable pre-shutdown class."""
    if exit_code == 0:
        return "SERVER_PRE_SHUTDOWN_CLEAN_EXIT"
    if exit_code == -signal.SIGINT:
        return "SERVER_PRE_SHUTDOWN_SIGINT_EXIT"
    if exit_code == 1:
        return "SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR"
    if exit_code == 2:
        return "SERVER_PRE_SHUTDOWN_GO_RUNTIME_FAILURE"
    if exit_code == 66:
        return "SERVER_PRE_SHUTDOWN_ZHTTP_SERVE_ERROR"
    if exit_code == 99:
        return "SERVER_PRE_SHUTDOWN_FORCE_KILL_EXIT"
    if exit_code < 0:
        return "SERVER_PRE_SHUTDOWN_OTHER_SIGNAL"
    return "SERVER_PRE_SHUTDOWN_OTHER_NONZERO_EXIT"


def _server_exit_failure_code(exit_code: int) -> str | None:
    """Map a post-SIGINT process exit to one stable, non-sensitive class."""
    if exit_code == 0:
        return None
    if exit_code == -signal.SIGINT:
        return "SERVER_TERMINATED_BY_SIGINT"
    if exit_code == 1:
        return "SERVER_GOATCOUNTER_COMMAND_ERROR"
    if exit_code == 2:
        return "SERVER_GO_RUNTIME_FAILURE"
    if exit_code == 66:
        return "SERVER_ZHTTP_SERVE_ERROR"
    if exit_code == 99:
        return "SERVER_FORCE_KILL_EXIT"
    if exit_code < 0:
        return "SERVER_TERMINATED_BY_OTHER_SIGNAL"
    return "SERVER_OTHER_NONZERO_EXIT"


_SERVER_STOP_EVIDENCE_CODES = frozenset({
    "SERVER_PRE_SHUTDOWN_CLEAN_EXIT",
    "SERVER_PRE_SHUTDOWN_SIGINT_EXIT",
    "SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR",
    "SERVER_PRE_SHUTDOWN_GO_RUNTIME_FAILURE",
    "SERVER_PRE_SHUTDOWN_ZHTTP_SERVE_ERROR",
    "SERVER_PRE_SHUTDOWN_FORCE_KILL_EXIT",
    "SERVER_PRE_SHUTDOWN_OTHER_SIGNAL",
    "SERVER_PRE_SHUTDOWN_OTHER_NONZERO_EXIT",
    "SERVER_TERMINATED_BY_SIGINT",
    "SERVER_GOATCOUNTER_COMMAND_ERROR",
    "SERVER_GO_RUNTIME_FAILURE",
    "SERVER_ZHTTP_SERVE_ERROR",
    "SERVER_FORCE_KILL_EXIT",
    "SERVER_TERMINATED_BY_OTHER_SIGNAL",
    "SERVER_OTHER_NONZERO_EXIT",
    "SERVER_SHUTDOWN_TIMEOUT",
    "SERVER_PROCESS_STUCK",
})


def _secondary_server_stop_code(exc: Exception) -> str:
    """Reduce a finalizer exception to sanitized secondary evidence."""
    if isinstance(exc, base.RuntimeStop):
        code = str(exc)
        if code in _SERVER_STOP_EVIDENCE_CODES:
            return code
    return "SERVER_STOP_SECONDARY_ERROR"


def _tcp_ready_classified(
    port: int,
    proc: subprocess.Popen[bytes],
) -> None:
    """Wait for loopback readiness or classify a pre-ready child exit."""
    if proc.stderr is None:
        raise base.RuntimeStop("SERVER_STARTUP_DIAGNOSTIC_UNAVAILABLE")

    capture = _BoundedStderrCapture(proc.stderr)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            capture.wait()
            code = _startup_exit_failure_code(exit_code, capture.snapshot())
            capture.discard()
            raise base.RuntimeStop(code)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                capture.discard()
                return
        except OSError:
            time.sleep(0.1)

    capture.discard()
    raise base.RuntimeStop("LOOPBACK_NOT_READY")


def _stop_server_classified(proc: subprocess.Popen[bytes]) -> None:
    """Separate pre-shutdown exit evidence from one graceful SIGINT attempt."""
    pre_shutdown_exit = proc.poll()
    if pre_shutdown_exit is not None:
        raise base.RuntimeStop(
            _pre_shutdown_exit_failure_code(pre_shutdown_exit)
        )

    proc.send_signal(signal.SIGINT)
    try:
        exit_code = proc.wait(timeout=12)
    except subprocess.TimeoutExpired:
        # Preserve the existing bounded timeout/stuck semantics. This is
        # termination after the single shutdown attempt, not a retry.
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            raise base.RuntimeStop("SERVER_PROCESS_STUCK")
        raise base.RuntimeStop("SERVER_SHUTDOWN_TIMEOUT")

    failure_code = _server_exit_failure_code(exit_code)
    if failure_code is not None:
        raise base.RuntimeStop(failure_code)


def _synthetic_user_id(db: Path) -> int:
    """Return the one synthetic user ID without emitting fixture contents."""
    try:
        with contextlib.closing(sqlite3.connect(db, timeout=2)) as con:
            rows = con.execute(
                "SELECT user_id FROM users WHERE email=?",
                (base.EMAIL,),
            ).fetchall()
    except sqlite3.DatabaseError:
        raise base.RuntimeStop("SYNTHETIC_DATABASE_SETUP")

    if len(rows) != 1:
        raise base.RuntimeStop("SYNTHETIC_DATABASE_SETUP")
    user_id = rows[0][0]
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise base.RuntimeStop("SYNTHETIC_DATABASE_SETUP")
    return user_id


def _create_count_token(
    binary: Path,
    root: Path,
    env: dict[str, str],
    db: Path,
    db_arg: str,
) -> None:
    """Create the token using GoatCounter v2.7.0's robust numeric selector."""
    user_id = _synthetic_user_id(db)
    _run_stage(
        binary,
        root,
        env,
        "db",
        "create",
        "apitoken",
        "-user=" + str(user_id),
        "-name=synthetic-count-only",
        "-perm=count",
        "-db=" + db_arg,
    )


_COLLECT_NOTHING = 1
_COLLECT_MASK_MAX = (1 << 16) - 1


def _enforce_aggregate_only(settings: dict[str, object]) -> None:
    """Disable visitor dimensions and individual-hit storage for the fixture."""
    collect = settings.get("collect")
    if (
        isinstance(collect, bool)
        or not isinstance(collect, int)
        or collect < 0
        or collect > _COLLECT_MASK_MAX
    ):
        raise base.RuntimeStop("SYNTHETIC_SETTINGS_INVALID")
    settings["collect"] = _COLLECT_NOTHING
    settings["ignore_ips"] = ""


def _verify_site_deserialization(
    binary: Path,
    root: Path,
    env: dict[str, str],
    db_arg: str,
) -> None:
    """Run GoatCounter's Sites.Find path without requesting a site-row update."""
    _run_stage(
        binary,
        root,
        env,
        "db",
        "update",
        "site",
        "-find=" + base.HOST,
        "-db=" + db_arg,
    )


def _make_site_with_stage_diagnostics(
    binary: Path,
    root: Path,
    env: dict[str, str],
    db: Path,
) -> str:
    db_arg = "sqlite+" + str(db)
    _run_stage(binary, root, env, "db", "newdb", "-db=" + db_arg)

    site_passphrase = secrets.token_hex(20)
    _run_stage(
        binary,
        root,
        env,
        "db",
        "create",
        "site",
        "-vhost=" + base.HOST,
        "-user.email=" + base.EMAIL,
        "-user.password=" + site_passphrase,
        "-db=" + db_arg,
    )
    site_passphrase = ""

    _create_count_token(binary, root, env, db, db_arg)

    token = ""
    try:
        with contextlib.closing(sqlite3.connect(db, timeout=2)) as con:
            con.row_factory = sqlite3.Row
            sites = con.execute(
                "SELECT site_id, settings FROM sites"
            ).fetchall()
            tokens = con.execute(
                "SELECT token FROM api_tokens"
            ).fetchall()
            if len(sites) != 1 or len(tokens) != 1:
                raise base.RuntimeStop("SYNTHETIC_SITE_OR_TOKEN_COUNT")
            settings = json.loads(sites[0]["settings"])
            if not isinstance(settings, dict):
                raise base.RuntimeStop("SYNTHETIC_SETTINGS_INVALID")
            _enforce_aggregate_only(settings)
            con.execute(
                "UPDATE sites SET settings=? WHERE site_id=?",
                (json.dumps(settings, separators=(",", ":")), sites[0]["site_id"]),
            )
            con.commit()
            token = tokens[0]["token"]
            if not isinstance(token, str) or len(token) < 16:
                raise base.RuntimeStop("SYNTHETIC_TOKEN_INVALID")
    except base.RuntimeStop:
        raise
    except (sqlite3.DatabaseError, ValueError, TypeError):
        raise base.RuntimeStop("SYNTHETIC_DATABASE_SETUP")

    _verify_site_deserialization(binary, root, env, db_arg)
    return token


def _run_fixture(release_archive_arg: str, root: Path) -> None:
    binary = base._verified_release_archive(release_archive_arg, root)
    env = base._isolated_env(root)
    base._version(binary, root, env)

    db = root / base.DB_NAME
    token = _make_site_with_stage_diagnostics(binary, root, env, db)
    (root / base.MARKER).write_bytes(base.MARKER_BYTES)

    port = base._free_loopback_port()
    proc = None
    primary_failure = None
    try:
        proc = subprocess.Popen(
            [
                str(binary),
                "serve",
                "-db=sqlite+" + str(db),
                "-listen=127.0.0.1:" + str(port),
                "-tls=http",
                "-automigrate",
                "-store-every=1",
            ],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        _tcp_ready_classified(port, proc)
        for _ in range(base.VIEWS):
            base._count_once(port, token)
        token = ""
    except base.RuntimeStop as exc:
        primary_failure = exc
    except OSError:
        primary_failure = base.RuntimeStop("LOOPBACK_PROCESS_ERROR")
    finally:
        if proc is not None:
            try:
                _stop_server_classified(proc)
            except Exception as stop_exc:
                if primary_failure is None:
                    raise
                primary_failure.secondary_server_stop_code = (
                    _secondary_server_stop_code(stop_exc)
                )

    if primary_failure is not None:
        raise primary_failure

    _inspect_fixture_or_raise(root)


def _inspect_fixture_or_raise(root: Path) -> None:
    """Run the structural gate and surface only reviewed operator-safe codes."""
    try:
        base.inspect_fixture(
            root,
            page_id=base.PAGE_ID,
            expected_views=base.VIEWS,
        )
    except base.ProbeStop as exc:
        raise base.RuntimeStop(privacy.operator_safe_stop_code(exc)) from None


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
