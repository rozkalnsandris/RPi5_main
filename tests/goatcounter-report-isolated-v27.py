#!/usr/bin/env python3
"""Run ONLY in the network-none CI container with a newly created synthetic DB.

No runtime services or production files are opened. Setup SQL is confined to the
temporary fixture. The production reader itself uses only authenticated GETs.
"""
import contextlib
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import http.client
from importlib.machinery import SourceFileLoader
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import sqlite3
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path("/input/goatcounter-v2.7.0-linux-amd64.gz")
ARCHIVE_SHA = "98d221cb9c8ef2bf76d8daa9cca647839f8d8b0bb5bc7400ff9337c5da834511"
HOST = "goatcounter.ausmalwiese.invalid"


def require(condition, stage):
    if not condition:
        raise RuntimeError(stage)


def run():
    require(os.environ.get("GOATCOUNTER_REPORT_ISOLATED_CI") == "1" and os.geteuid() != 0,
            "ISOLATED_CI_REQUIRED")
    require(ARCHIVE.stat().st_size == 13935060 and hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == ARCHIVE_SHA,
            "ARCHIVE_PIN")
    loader = SourceFileLoader("synthetic_admin", str(ROOT / "ops/bin/coloring-pages-admin-publish"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    admin = importlib.util.module_from_spec(spec)
    loader.exec_module(admin)
    with tempfile.TemporaryDirectory(prefix="goatcounter-report-") as directory:
        root = Path(directory)
        binary = root / "goatcounter"
        with gzip.open(ARCHIVE, "rb") as archive:
            data = archive.read(128 * 1024 * 1024 + 1)
        require(0 < len(data) <= 128 * 1024 * 1024, "BINARY_SIZE")
        binary.write_bytes(data)
        del data
        binary.chmod(0o700)
        env = {"HOME": directory, "TMPDIR": directory, "TZ": "UTC", "PATH": "/usr/bin:/bin"}
        db = root / "synthetic.sqlite3"
        dbarg = "-db=sqlite+" + str(db)

        def cli(*args):
            result = subprocess.run([str(binary), *args], cwd=root, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
            require(result.returncode == 0, "CLI_SETUP")

        cli("db", "newdb", dbarg)
        cli("db", "create", "site", "-vhost=" + HOST, "-user.email=synthetic@example.test",
            "-user.password=" + secrets.token_hex(16), dbarg)
        with contextlib.closing(sqlite3.connect(db)) as con:
            user = con.execute("SELECT user_id FROM users").fetchone()[0]
        for perm in ("count", "stats"):
            cli("db", "create", "apitoken", "-user=" + str(user), "-name=fixture-" + perm, "-perm=" + perm, dbarg)
        with contextlib.closing(sqlite3.connect(db)) as con:
            site, settings = con.execute("SELECT site_id, settings FROM sites").fetchone()
            settings = json.loads(settings)
            settings.update(collect=1, ignore_ips="")
            con.execute("UPDATE sites SET settings=?", (json.dumps(settings),))
            # Only this new synthetic DB is edited; no production provisioning.
            con.execute("UPDATE api_tokens SET sites=?", (json.dumps([site]),))
            tokens = dict(con.execute("SELECT name, token FROM api_tokens"))
            con.commit()
        credential = root / "stats-token"
        credential.write_text(tokens["fixture-stats"])
        credential.chmod(0o400)
        admin.ORIGIN_REPORT_CREDENTIAL = credential

        def start():
            process = subprocess.Popen([str(binary), "serve", dbarg, "-listen=127.0.0.1:9194",
                                        "-tls=http", "-automigrate", "-store-every=1"], cwd=root, env=env,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    require(process.poll() is None, "SERVER_START")
                    try:
                        with socket.create_connection(("127.0.0.1", 9194), timeout=0.1):
                            return process
                    except OSError:
                        time.sleep(0.1)
                raise RuntimeError("SERVER_READY_TIMEOUT")
            except Exception:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                raise

        def stop(process):
            process.send_signal(signal.SIGINT)
            try:
                require(process.wait(timeout=15) == 0, "SERVER_STOP")
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise RuntimeError("SERVER_STOP_TIMEOUT") from None

        process = start()
        try:
            empty = admin.OriginReportReader().snapshot(7)
            require(empty["total"] == 0 and empty["pages"] == [], "EMPTY_NAMESPACE")
            # 28 origin paths force two reader batches; unrelated events never enter the result.
            paths = ["/origin-detail-request/0123456"] * 3 + ["/origin-detail-request/7654321"] * 2
            paths += ["/origin-detail-request/" + str(2000000 + n) for n in range(26)]
            paths += ["/old-browser-counter/0123456"] * 9
            connection = http.client.HTTPConnection("127.0.0.1", 9194, timeout=5)
            try:
                body = json.dumps({"no_sessions": True, "hits": [{"path": p} for p in paths]})
                connection.request("POST", "/api/v0/count", body, {
                    "Host": HOST, "Authorization": "Bearer " + tokens["fixture-count"], "Content-Type": "application/json"})
                require(connection.getresponse().status == 202, "SEED_COUNT")
            finally:
                connection.close()
        finally:
            stop(process)
        # Shift one fixture aggregate into the previous UTC day to prove window boundaries.
        with contextlib.closing(sqlite3.connect(db)) as con:
            path_id = con.execute("SELECT path_id FROM paths WHERE path=?", ("/origin-detail-request/7654321",)).fetchone()[0]
            previous = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
            hour = con.execute("SELECT hour FROM hit_counts WHERE path_id=?", (path_id,)).fetchone()[0]
            day = con.execute("SELECT day FROM hit_stats WHERE path_id=?", (path_id,)).fetchone()[0]
            require(isinstance(hour, str) and isinstance(day, str), "FIXTURE_DATE_FORMAT")
            # Preserve the release's SQLite timestamp representation and hourly bins.
            con.execute("UPDATE hit_counts SET hour=? WHERE path_id=?", (previous + hour[10:], path_id))
            con.execute("UPDATE hit_stats SET day=? WHERE path_id=?", (previous + day[10:], path_id))
            con.commit()
        process = start()
        try:
            for days, total in ((1, 29), (7, 31), (30, 31), (365, 31)):
                result = admin.OriginReportReader().snapshot(days)
                require(result["total"] == total and len(result["daily"]) == days, "RANGE_TOTAL_" + str(days))
                require(sum(row["requests"] for row in result["pages"]) == total, "RANKING_TOTAL")
                require(sum(row["requests"] for row in result["daily"]) == total, "DAILY_TOTAL")
                require(all(set(row) == {"page_id", "requests"} for row in result["pages"]), "REDACTION")
            credential.chmod(0o600)
            credential.write_text(tokens["fixture-count"])
            credential.chmod(0o400)
            try:
                admin.OriginReportReader().snapshot(7)
            except admin.OriginReportUnavailable:
                pass
            else:
                raise RuntimeError("COUNT_TOKEN_NOT_REJECTED")
        finally:
            stop(process)
    print("GOATCOUNTER_REPORT_V27=PASS synthetic-only empty, multi-batch, UTC ranges, daily/ranking totals, separate stats token")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        # No raw upstream response, fixture token, SQL rows or secret in evidence.
        code = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("GOATCOUNTER_REPORT_V27=FAIL stage=" + code)
        raise SystemExit(1) from None
