#!/usr/bin/env python3
"""Independent offline verifier; does not inspect host runtime or Docker."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import sys
from grafana_continuity_core import (
    EvidenceError, canonical_json, check_report, checksums, inventory,
    render_markdown,
)

REPO = Path(__file__).resolve().parent.parent

def verify(raw: str) -> dict:
    path = Path(raw)
    path = path if path.is_absolute() else Path.cwd() / path
    current = Path(path.anchor or "/")
    for component in path.parts[1:]:
        current = current / component
        if current.is_symlink():
            raise EvidenceError("symlink evidence root")
    target = path.resolve(strict=True)
    if (not target.is_dir()
        or not any(target.is_relative_to(REPO / name)
                   for name in ("evidence", "exports"))):
        raise EvidenceError("evidence outside ignored root")
    expected = {"report.json", "report.md", "file-inventory.txt", "SHA256SUMS"}
    if {item.name for item in target.iterdir()} != expected:
        raise EvidenceError("unexpected evidence files")
    contents = {}
    for name in expected:
        entry = target / name
        meta = entry.lstat()
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
            or meta.st_uid != os.getuid() or meta.st_mode & stat.S_IWOTH
            or meta.st_size > 262144):
            raise EvidenceError("unsafe evidence member")
        contents[name] = entry.read_bytes()
    if contents["file-inventory.txt"] != inventory().encode("ascii"):
        raise EvidenceError("inventory mismatch")
    if contents["SHA256SUMS"] != checksums(
        contents["report.json"], contents["report.md"]).encode("ascii"):
        raise EvidenceError("checksum mismatch")
    report = json.loads(contents["report.json"].decode("utf-8"))
    check_report(report)
    if contents["report.json"] != canonical_json(report).encode("utf-8"):
        raise EvidenceError("noncanonical JSON")
    if contents["report.md"] != render_markdown(report).encode("utf-8"):
        raise EvidenceError("noncanonical Markdown")
    return report

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    args = parser.parse_args()
    try:
        result = verify(args.bundle)
    except (EvidenceError, OSError, ValueError, TypeError, UnicodeError, KeyError):
        print("Grafana continuity offline verifier: FAIL (sanitized)", file=sys.stderr)
        raise SystemExit(1)
    print("Grafana continuity offline verifier: PASS (schema, integrity, arithmetic)")
    print("Identity is collector-asserted only; not independently re-observed")

if __name__ == "__main__":
    main()
