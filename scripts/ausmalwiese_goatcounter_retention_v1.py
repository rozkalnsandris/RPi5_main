#!/usr/bin/env python3
"""Offline, empty-site-only native retention configuration; no service control."""

import argparse
import json
import os
from pathlib import Path
import pwd
import socket
import sqlite3
import stat
import subprocess

DB = Path('/var/lib/ausmalwiese-goatcounter/goatcounter.sqlite3')
ACCOUNT = 'ausmalwiese-goatcounter'
HOST = 'goatcounter.ausmalwiese.invalid'
DAYS = 365
READ = 'READ_GOATCOUNTER_RETENTION'
APPLY = 'SET_PRIVATE_GOATCOUNTER_RETENTION_365'
UNITS = ('ausmalwiese-goatcounter-pageview.service',
         'ausmalwiese-goatcounter.service')
EMPTY_TABLES = ('hits', 'bots', 'paths', 'hit_counts', 'ref_counts',
                'hit_stats', 'browser_stats', 'system_stats', 'location_stats',
                'size_stats', 'language_stats', 'campaign_stats', 'campaigns',
                'exports')


class Stop(Exception):
    """Never expose underlying DB, OS, or subprocess error text."""


def require(condition):
    if not condition:
        raise Stop()


def services_stopped():
    for unit in UNITS:
        result = subprocess.run(
            ['/usr/bin/systemctl', 'show', unit, '--no-pager',
             '--property=LoadState,ActiveState,SubState,MainPID'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=10,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
        require(result.returncode == 0)
        expected = {'LoadState=loaded', 'ActiveState=inactive',
                    'SubState=dead', 'MainPID=0'}
        lines = result.stdout.splitlines()
        require(len(lines) == 4 and set(lines) == expected)


def safe_path(path, uid):
    # The private directory prevents other unprivileged users replacing the DB.
    # An exclusive operator window is still required for service/root writers.
    for parent in reversed(path.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode))
        require(info.st_uid in (0, uid) and not info.st_mode & 0o022)
    directory = path.parent.stat()
    require(directory.st_uid == uid and stat.S_IMODE(directory.st_mode) == 0o700)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    require(info.st_uid == uid and not info.st_mode & 0o077)
    # Never ignore an uncheckpointed WAL or recovery journal with immutable=1.
    for suffix in ('-wal', '-shm', '-journal'):
        require(not os.path.lexists(str(path) + suffix))
    return (info.st_dev, info.st_ino)


def inspect_database(con):
    # Refuse triggers/views: the only permitted write must have no hidden effect.
    require(con.execute("SELECT count(*) FROM sqlite_schema WHERE type IN ('trigger','view')").fetchone()[0] == 0)
    required = ('sites',) + EMPTY_TABLES
    for name in required:
        require(con.execute("SELECT count(*) FROM sqlite_schema WHERE type='table' AND name=?", (name,)).fetchone()[0] == 1)
    require(con.execute('SELECT count(*) FROM sites').fetchone()[0] == 1)
    require(con.execute("SELECT count(*) FROM sites WHERE cname=? AND parent IS NULL AND state='a' AND received_data=0", (HOST,)).fetchone()[0] == 1)
    require(con.execute("SELECT count(*) FROM sites WHERE json_valid(settings) AND json_type(settings)='object'").fetchone()[0] == 1)
    # Reject duplicate keys rather than relying on SQLite/Go parser differences.
    require(con.execute('SELECT count(*) FROM (SELECT key FROM sites, json_each(sites.settings) GROUP BY key HAVING count(*) > 1)').fetchone()[0] == 0)
    require(con.execute("SELECT count(*) FROM sites WHERE json_type(settings,'$.collect')='integer' AND json_extract(settings,'$.collect')=1 AND json_type(settings,'$.ignore_ips')='text' AND json_extract(settings,'$.ignore_ips')='' ").fetchone()[0] == 1)
    kind, days = con.execute("SELECT json_type(settings,'$.data_retention'), json_extract(settings,'$.data_retention') FROM sites").fetchone()
    require((kind is None and days is None) or (kind == 'integer' and days in (0, DAYS)))
    for table in EMPTY_TABLES:
        # Identifiers are fixed source constants, never operator input.
        require(con.execute('SELECT EXISTS(SELECT 1 FROM ' + table + ' LIMIT 1)').fetchone()[0] == 0)
    return days or 0


def configure(path, apply=False, guard=lambda: None):
    """Testable DB core. CLI alone binds the real host, user, path and services."""
    guard()
    uri = path.as_uri() + ('?mode=rw' if apply else '?mode=ro&immutable=1')
    con = sqlite3.connect(uri, uri=True, timeout=0, isolation_level=None)
    try:
        con.execute('PRAGMA trusted_schema=OFF')
        if not apply:
            con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
        before = inspect_database(con)
        changed = apply and before != DAYS
        if changed:
            # JSON is updated inside SQLite; no complete settings value is read.
            row = con.execute("UPDATE sites SET settings=json_set(settings,'$.data_retention',?) WHERE cname=?", (DAYS, HOST))
            require(row.rowcount == 1 and con.total_changes == 1)
            require(inspect_database(con) == DAYS)
        guard()
        con.execute('COMMIT')
        return {'result': 'PASS', 'retention_days': DAYS if apply else before,
                'changed': bool(changed), 'analytics_empty': True,
                'public_readiness_verified': False}
    finally:
        # SQLite closes an uncommitted transaction atomically on error. This is
        # not a post-commit rollback, retry, cleanup or recovery attempt.
        con.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-read', choices=[READ], required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-apply', choices=[APPLY])
    args = parser.parse_args(argv)
    stage = 'PREFLIGHT'
    try:
        require(args.apply == (args.confirm_apply == APPLY))
        require(socket.gethostname() == 'rpi5')
        uid = pwd.getpwnam(ACCOUNT).pw_uid
        require(os.geteuid() == uid and uid != 0)
        os.umask(0o077)
        services_stopped()
        identity = safe_path(DB, uid)

        def guard():
            services_stopped()
            # During an UPDATE the transaction's own rollback journal may exist;
            # check identity/ownership without mistaking it for a stale journal.
            info = DB.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
            require(info.st_uid == uid and not info.st_mode & 0o077)
            require((info.st_dev, info.st_ino) == identity)

        stage = 'DATABASE_OPERATION'
        result = configure(DB, args.apply, guard)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({'result': 'STOP', 'stage': stage,
                          'outcome_may_require_reconciliation': stage == 'DATABASE_OPERATION'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
