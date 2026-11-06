#!/usr/bin/env python3
"""SOURCE ONLY: bounded, sanitized SQLite Collect readback for GoatCounter SIMPLE.

No CLI, production credential, network, state modification or privileged runner.
An independent owner-authorized runtime must establish the trusted binary,
identity, mount permissions and protected DB-read scope before use.
"""

from pathlib import Path
import os
import sqlite3
import stat

VHOST = "goatcounter.ausmalwiese.invalid"
READ_URI_OPTIONS = "?mode=ro&cache=private"  # Never immutable=1 on a changing WAL.
SQL = (
    "SELECT json_type(s.settings,'$.collect'), "
    "json_extract(s.settings,'$.collect'), "
    "(SELECT count(*) FROM json_each(s.settings) WHERE key='collect') "
    "FROM sites AS s WHERE s.cname=? AND s.parent IS NULL LIMIT 2"
)


class Stop(Exception):
    def __init__(self, code):
        self.code = code


def _require(ok, code):
    if not ok:
        raise Stop(code)


def _meta(path, *, uid):
    """Metadata only. Never read the raw database or sidecars."""
    s = path.lstat()
    _require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1
             and s.st_uid == uid and not (stat.S_IMODE(s.st_mode) & 0o022),
             "STOP_PATH")
    return (s.st_dev, s.st_ino)


def _preflight(path):
    _require(isinstance(path, Path) and path.is_absolute()
             and path.name == "goatcounter.sqlite3", "STOP_PATH")
    folder = path.parent.lstat()
    _require(stat.S_ISDIR(folder.st_mode) and not (folder.st_mode & 0o022),
             "STOP_PATH")
    db_stat = path.lstat()
    identity = _meta(path, uid=db_stat.st_uid)
    _require(db_stat.st_uid == folder.st_uid, "STOP_PATH")
    # A live WAL reader must not create its own -wal/-shm files. Require both
    # pre-existing, readable, regular, pinned-owner sidecars. Any ambiguity STOPs.
    _require(not os.path.lexists(str(path) + "-journal"), "STOP_WAL_SIDECARS")
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        _require(os.path.lexists(sidecar), "STOP_WAL_SIDECARS")
        _meta(sidecar, uid=db_stat.st_uid)
    return identity


def _classify(connection):
    """Exactly one bounded SQL SELECT; never return raw settings or site rows."""
    connection.execute("PRAGMA query_only=ON")
    connection.set_progress_handler(_abort_after_budget(), 200)
    connection.execute("BEGIN")
    rows = connection.execute(SQL, (VHOST,)).fetchall()
    _require(len(rows) == 1 and len(rows[0]) == 3, "STOP_SITE")
    kind, value, count = rows[0]
    _require(kind == "integer" and type(value) is int and count == 1,
             "STOP_COLLECT")
    if value == 1:
        return "COLLECT_DISABLED_1"
    if value == 130:
        return "COLLECT_CANDIDATE_130"
    return "STOP_OTHER_COLLECT_MASK"


def _abort_after_budget():
    remaining = 500
    def progress():
        nonlocal remaining
        remaining -= 1
        return int(remaining < 0)
    return progress


def read_once(path):
    """Read with ordinary SQLite locking; only fixed, sanitized status escapes.

    Even mode=ro may touch SQLite's existing shared-memory index. Future LIVE
    execution must use a separately authorized, restricted read-only runtime.
    This source function by itself is not a zero-host-write attestation.
    """
    try:
        identity = _preflight(path)
        con = sqlite3.connect(path.as_uri() + READ_URI_OPTIONS, uri=True,
                              timeout=0, isolation_level=None)
        try:
            result = _classify(con)
        finally:
            con.close()
        _require((path.lstat().st_dev, path.lstat().st_ino) == identity,
                 "STOP_PATH")
        return result
    except Stop as exc:
        return exc.code
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        return "STOP_DB_READ"


if __name__ == "__main__":
    raise SystemExit("SOURCE_ONLY: no standalone DB read or trusted runner")
