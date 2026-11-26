#!/usr/bin/env python3
"""Render one successor from the immutable reviewed backup core, offline.

The exact private DB path is supplied only in the separately authorized
installation procedure. No host discovery, writes, or backup execution here.
"""
import argparse
import hashlib
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

BASE_SHA256 = "5ca85ae53bdf4fa3b99e21e1a30ddaa077d9e1791505b1e8389ee8587d011735"
ROOT = Path(__file__).resolve().parents[1]
ANCHOR = 'mkdir -p "$PAYLOAD/backup-metadata"\n'
MEMBER_ANCHOR = "    './etc/rpi-update.conf'; do\n"
MEMBER = '    ".$JOBSCANNER_DB" \\\n'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("unexpected source anchor")
    return text.replace(old, new, 1)


def render(base, template, private_db):
    if hashlib.sha256(base).hexdigest() != BASE_SHA256:
        raise ValueError("unexpected predecessor")
    path = PurePosixPath(private_db)
    if (not path.is_absolute() or str(path) != private_db
            or ".." in path.parts or len(path.parts) < 4
            or path.parts[-2:] != ("data", "jobs.db")
            or not re.fullmatch(r"/[A-Za-z0-9._/-]+", private_db)):
        raise ValueError("invalid private DB binding")
    block = replace_once(template, "__PRIVATE_DB_PATH__", shlex.quote(private_db))
    source = base.decode("utf-8")
    source = replace_once(source, "# RPi5 šifrētais backup runneris V12.",
                          "# RPi5 šifrētais backup runneris V13 (Job Scanner).")
    source = replace_once(source, 'echo "backup_version=12"', 'echo "backup_version=13"')
    source = replace_once(source, ANCHOR, block + ANCHOR)
    source = replace_once(source, MEMBER_ANCHOR, MEMBER + MEMBER_ANCHOR)
    return source.encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-db", required=True)
    args = parser.parse_args()
    try:
        base = (ROOT / "ops/bin/rpi5-backup").read_bytes()
        template = (ROOT / "ops/backup/jobscanner-snapshot.sh.in").read_text(encoding="utf-8")
        result = render(base, template, args.job_db)
    except (ValueError, OSError):
        print("Job Scanner backup materialization rejected", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
