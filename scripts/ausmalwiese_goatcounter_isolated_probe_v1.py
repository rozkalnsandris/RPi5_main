"""RPi5-only opt-in GoatCounter v2.7.0 isolated proof with synthetic data only.

No downloads, Docker, real users, public traffic, production data, protected
runtime/config access, or GitHub workflow mutations. Running this program on
the RPi5 is itself a separately owner-authorized synthetic runtime operation. Requires a separately obtained
official GoatCounter v2.7.0 Linux release .gz asset whose GitHub-published
name, size and SHA-256 are pinned below. The harness verifies that archive
before extracting the binary into its private temporary directory, then starts
one loopback listener, writes ONLY synthetic test data, shuts down, and invokes
the read-only SQLite probe.

The result is NOT a legal clearance, proof of GitHub release immutability,
Cloudflare/proxy-log assessment, or LIVE authorization.
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import os
import platform
import re
import secrets
import signal
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from ausmalwiese_goatcounter_offline_privacy_probe_v1 import (
    DB_NAME, MARKER, MARKER_BYTES, PREFIX, ProbeStop, inspect_fixture,
)

HOST = "stats.example.test"
EMAIL = "goatcounter-probe@example.com"
PAGE_ID = "0427183"
PAGE_PATH = "/coloring-page/" + PAGE_ID
VIEWS = 2
MAX_BINARY_BYTES = 128 * 1024 * 1024
RELEASE_ASSETS = {
    "arm64": {
        "name": "goatcounter-v2.7.0-linux-arm64.gz",
        "size": 12770791,
        "sha256": "ff5b2670b858bbe48802dfdc74130b6dcde2de9f5c1229b838eb9132769307dd",
    },
}


class RuntimeStop(Exception):
    """Stable failure code: never include tokens, paths or raw DB records."""


def _stop(code: str) -> None:
    raise RuntimeStop(code)


def _host_guard() -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        _stop("ROOT_FORBIDDEN")
    if platform.node().split(".", 1)[0].casefold() != "rpi5":
        _stop("WRONG_TEST_HOST")
    if platform.system().casefold() != "linux":
        _stop("UNSUPPORTED_RELEASE_HOST")
    if platform.machine().casefold() not in {"aarch64", "arm64"}:
        _stop("UNSUPPORTED_RELEASE_HOST")


def _release_asset_for_host() -> dict[str, object]:
    return RELEASE_ASSETS[_expected_goarch()]


def _verified_release_archive(path_arg: str, root: Path) -> Path:
    path = Path(path_arg)
    asset = _release_asset_for_host()
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.parent.resolve() != Path("/tmp")
            or path.name != asset["name"]):
        _stop("RELEASE_ARCHIVE_INPUT_INVALID")
    if path.stat().st_size != asset["size"]:
        _stop("RELEASE_ARCHIVE_SIZE_MISMATCH")

    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            hasher.update(block)
    if hasher.hexdigest() != asset["sha256"]:
        _stop("RELEASE_ARCHIVE_DIGEST_MISMATCH")

    binary = root / "goatcounter"
    total = 0
    try:
        with gzip.open(path, "rb") as source, binary.open("xb") as target:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_BINARY_BYTES:
                    _stop("RELEASE_BINARY_TOO_LARGE")
                target.write(block)
    except (OSError, EOFError, gzip.BadGzipFile):
        _stop("RELEASE_ARCHIVE_EXTRACT_FAILED")
    if total == 0:
        _stop("RELEASE_ARCHIVE_EXTRACT_FAILED")
    os.chmod(binary, 0o700)
    return binary


def _isolated_env(root: Path) -> dict[str, str]:
    # No proxy, inherited auth token, production HOME or GOATCOUNTER_ flags.
    return {
        "HOME": str(root), "TMPDIR": str(root), "TZ": "UTC",
        "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
    }


def _run(binary: Path, root: Path, env: dict[str, str], *argv: str) -> None:
    try:
        result = subprocess.run(
            [str(binary), *argv], cwd=root, env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _stop("BINARY_COMMAND_ERROR")
    if result.returncode != 0:
        _stop("BINARY_COMMAND_REJECTED")


def _expected_goarch() -> str:
    if platform.system().casefold() != "linux":
        _stop("UNSUPPORTED_RELEASE_HOST")
    machine = platform.machine().casefold()
    mapping = {
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    if machine not in mapping:
        _stop("UNSUPPORTED_RELEASE_HOST")
    return mapping[machine]


def _version(binary: Path, root: Path, env: dict[str, str]) -> None:
    try:
        p = subprocess.run(
            [str(binary), "version", "-json"], cwd=root, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=10, check=False,
        )
        data = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        _stop("VERSION_READ_FAILED")
    if (p.returncode != 0 or not isinstance(data, dict)
            or data.get("version") not in ("2.7.0", "v2.7.0")):
        _stop("WRONG_GOATCOUNTER_VERSION")

    # Pinned v2.7.0 .gogo-release publishes Linux amd64/arm64 with
    # CGO_ENABLED=1. version -json exposes these runtime build facts but
    # NOT the source commit; this narrows the build profile and does not
    # replace independent artifact provenance/digest review.
    if set(data) != {"version", "go", "GOOS", "GOARCH", "race", "cgo"}:
        _stop("RELEASE_BUILD_PROFILE_MISMATCH")
    if (data["GOOS"] != "linux"
            or data["GOARCH"] != _expected_goarch()
            or type(data["race"]) is not bool or data["race"] is not False
            or type(data["cgo"]) is not bool or data["cgo"] is not True
            or not isinstance(data["go"], str)
            or re.fullmatch(r"go1\.[0-9]+(?:\.[0-9]+)?(?:[^ ]*)?", data["go"]) is None):
        _stop("RELEASE_BUILD_PROFILE_MISMATCH")


def _make_site(binary: Path, root: Path, env: dict[str, str], db: Path) -> str:
    db_arg = "sqlite+" + str(db)
    _run(binary, root, env, "db", "newdb", "-db=" + db_arg)
    # Test credentials exist only inside this temporary synthetic database.
    site_passphrase = secrets.token_hex(20)
    _run(binary, root, env, "db", "create", "site",
         "-vhost=" + HOST, "-user.email=" + EMAIL,
         "-user.password=" + password, "-db=" + db_arg)
    site_passphrase = ""
    _run(binary, root, env, "db", "create", "apitoken",
         "-user=" + EMAIL, "-name=synthetic-count-only",
         "-perm=count", "-db=" + db_arg)
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
                _stop("SYNTHETIC_SITE_OR_TOKEN_COUNT")
            settings = json.loads(sites[0]["settings"])
            if not isinstance(settings, dict):
                _stop("SYNTHETIC_SETTINGS_INVALID")
            settings["collect"] = 1  # CollectNothing, not zero/defaults.
            settings["ignore_ips"] = []
            con.execute(
                "UPDATE sites SET settings=? WHERE site_id=?",
                (json.dumps(settings, separators=(",", ":")), sites[0]["site_id"]),
            )
            con.commit()
            token = tokens[0]["token"]
            if not isinstance(token, str) or len(token) < 16:
                _stop("SYNTHETIC_TOKEN_INVALID")
            return token
    except (sqlite3.DatabaseError, ValueError, TypeError):
        _stop("SYNTHETIC_DATABASE_SETUP")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _tcp_ready(port: int, proc: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            _stop("SERVER_EARLY_EXIT")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    _stop("LOOPBACK_NOT_READY")


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow 30x; a redirect can forward synthetic bearer credentials."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _count_once(port: int, token: str) -> None:
    # Never forward caller-supplied JSON, UA, IP, referrer or UTM.
    body = json.dumps(
        {"no_sessions": True, "hits": [{"path": PAGE_PATH}]},
        separators=(",", ":"),
    ).encode("ascii")
    request = urllib.request.Request(
        "http://127.0.0.1:" + str(port) + "/api/v0/count",
        data=body, method="POST",
        headers={
            "Host": HOST,
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
    )
    try:
        # Exactly one HTTP transmission. Never resend after ambiguity.
        # Never use environment proxies or follow redirects. urllib's
        # OpenerDirector otherwise adds "User-Agent: Python-urllib/..."
        # and its default redirect handler may forward Authorization.
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _RejectRedirects()
        )
        opener.addheaders = []
        with opener.open(request, timeout=5) as response:
            if response.status != 202:
                _stop("BACKEND_NOT_ACCEPTED")
            response.read(1024)
    except (OSError, urllib.error.HTTPError, ValueError):
        _stop("BACKEND_RESPONSE_UNCERTAIN")


def _stop_server(proc: subprocess.Popen[bytes]) -> None:
    """Require a clean, completed upstream shutdown before inspecting SQLite.

    GoatCounter v2.7.0 cmd/goatcounter/serve.go performs a final
    cron.TaskPersistAndStat() during graceful shutdown. HTTP 202 alone
    does not prove persistence; a crashed/unclean server cannot pass.
    """
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            exit_code = proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _stop("SERVER_PROCESS_STUCK")
            _stop("SERVER_SHUTDOWN_TIMEOUT")
    else:
        exit_code = proc.returncode
    if exit_code != 0:
        _stop("SERVER_UNCLEAN_EXIT")


def run_isolated(release_archive_arg: str) -> str:
    _host_guard()
    with tempfile.TemporaryDirectory(prefix=PREFIX, dir="/tmp") as temp:
        root = Path(temp)
        os.chmod(root, 0o700)
        binary = _verified_release_archive(release_archive_arg, root)
        env = _isolated_env(root)
        _version(binary, root, env)
        db = root / DB_NAME
        token = _make_site(binary, root, env, db)
        (root / MARKER).write_bytes(MARKER_BYTES)
        port = _free_loopback_port()
        proc = None
        try:
            proc = subprocess.Popen(
                [str(binary), "serve", "-db=sqlite+" + str(db),
                 "-listen=127.0.0.1:" + str(port), "-tls=http",
                 "-store-every=1"],
                cwd=root, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            _tcp_ready(port, proc)
            for _ in range(VIEWS):
                _count_once(port, token)
            token = ""  # Never output or retain credential after submission.
            # HTTP 202 is only acceptance. Graceful SIGINT below flushes
            # pending events and must exit with status 0 before DB inspection.
        except OSError:
            _stop("LOOPBACK_PROCESS_ERROR")
        finally:
            if proc is not None:
                _stop_server(proc)
        try:
            inspect_fixture(root, page_id=PAGE_ID, expected_views=VIEWS)
        except ProbeStop:
            _stop("ISOLATED_SQLITE_PRIVACY_GATE")
    return "PASS_SYNTHETIC_GOATCOUNTER_RUNTIME_ONLY_NOT_LIVE_OR_LEGAL_PROOF"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-archive", required=True)
    args = parser.parse_args()
    try:
        result = run_isolated(args.release_archive)
    except (RuntimeStop, OSError) as exc:
        code = str(exc) if isinstance(exc, RuntimeStop) else "ISOLATION_IO_ERROR"
        print("GOATCOUNTER_ISOLATED=STOP CODE=" + code)
        return 2
    print("GOATCOUNTER_ISOLATED=" + result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
