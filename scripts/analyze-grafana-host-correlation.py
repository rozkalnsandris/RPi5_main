#!/usr/bin/env python3
"""Offline-only, stdout-only V08/V02 composition after independent verification."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from grafana_host_correlation_core import CorrelationError, canonical_json, summarize

REPO = Path(__file__).resolve().parent.parent
MAX_JSON = 262144


def rejected() -> None:
    raise CorrelationError("invalid correlation input")


def safe_bundle(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    if ".." in path.parts:
        rejected()
    part = Path(path.anchor)
    for name in path.parts[1:]:
        part /= name
        if part.is_symlink():
            rejected()
    if not path.is_dir() or not any(path.is_relative_to(REPO / name)
                                    for name in ("evidence", "exports")):
        rejected()
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        rejected()
    return path


def safe_report(bundle: Path) -> bytes:
    path = bundle / "report.json"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & stat.S_IWOTH
            or info.st_size > MAX_JSON):
            rejected()
        data = os.read(fd, MAX_JSON + 1)
        if not data or len(data) > MAX_JSON:
            rejected()
        return data
    finally:
        os.close(fd)


def checked(bundle: Path, verifier: str) -> dict:
    before = safe_report(bundle)
    r = subprocess.run(
        [sys.executable, "-B", str(REPO / "scripts" / verifier), str(bundle)],
        capture_output=True, timeout=20, check=False,
    )
    if r.returncode or safe_report(bundle) != before:
        rejected()
    return json.loads(before.decode("utf-8", "strict"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline V08/Grafana V02 descriptive correlation")
    parser.add_argument("--grafana-bundle", required=True)
    parser.add_argument("--host-bundle", action="append", required=True)
    args = parser.parse_args()
    try:
        if not 2 <= len(args.host_bundle) <= 8:
            rejected()
        grafana = safe_bundle(args.grafana_bundle)
        hosts = [safe_bundle(x) for x in args.host_bundle]
        if len(set((grafana, *hosts))) != len(hosts) + 1:
            rejected()
        g = checked(grafana, "verify-grafana-continuity.py")
        h = [checked(p, "verify-memory-pressure-diagnostic.py") for p in hosts]
        result = summarize(h, g)
    except (CorrelationError, ValueError, OSError, UnicodeError,
            subprocess.SubprocessError, KeyError, TypeError):
        print("Grafana/host offline correlation: FAIL (sanitized)", file=sys.stderr)
        raise SystemExit(1)
    sys.stdout.write(canonical_json(result))


if __name__ == "__main__":
    main()
