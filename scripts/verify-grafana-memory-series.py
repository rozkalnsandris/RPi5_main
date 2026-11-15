#!/usr/bin/env python3
"""Strict verification and independent source reanalysis of Grafana series."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import sys
from grafana_memory_series_core import SeriesError, allowed_path, build_series, canonical_json, manifest, render_markdown, LABEL


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    args = ap.parse_args()
    try:
        target = allowed_path(args.bundle, existing=True)
        if not target.is_dir() or target.is_symlink():
            raise SeriesError("invalid target")
        required = {"report.json", "report.md", "file-inventory.txt", "SHA256SUMS"}
        if {p.name for p in target.iterdir()} != required:
            raise SeriesError("unexpected series files")
        for p in target.iterdir():
            st = p.lstat()
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.getuid() or st.st_mode & stat.S_IWOTH
                or st.st_size > 524288):
                raise SeriesError("unsafe series file")
        if (target / "file-inventory.txt").read_text(encoding="utf-8") != "report.json\nreport.md\n":
            raise SeriesError("inventory mismatch")
        if (target / "SHA256SUMS").read_text(encoding="utf-8") != manifest(target):
            raise SeriesError("manifest mismatch")
        data = (target / "report.json").read_text(encoding="utf-8")
        report = json.loads(data)
        if data != canonical_json(report):
            raise SeriesError("noncanonical report")
        names = [obs["source"] for obs in report["observations"]]
        if len(names) != len(set(names)) or not all(LABEL.fullmatch(n) for n in names):
            raise SeriesError("invalid source labels")
        sources = [allowed_path(target.parent / name, existing=True) for name in names]
        rebuilt = build_series(sources)
        if report != rebuilt:
            raise SeriesError("reanalysis mismatch")
        if (target / "report.md").read_text(encoding="utf-8") != render_markdown(rebuilt):
            raise SeriesError("Markdown mismatch")
    except (OSError, ValueError, TimeoutError, KeyError, TypeError) as error:
        print(f"Grafana series verification: FAIL ({type(error).__name__})", file=sys.stderr)
        raise SystemExit(1)
    print("Grafana series verification: PASS (descriptive only, cgroup identity unproven)")


if __name__ == "__main__":
    main()
