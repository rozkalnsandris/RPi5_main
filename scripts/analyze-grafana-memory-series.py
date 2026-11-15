#!/usr/bin/env python3
"""Write an immutable offline comparison of 2–8 verified Grafana snapshots."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys
import tempfile

from grafana_memory_series_core import SeriesError, allowed_path, build_series, canonical_json, manifest, render_markdown


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("bundles", nargs="+")
    args = ap.parse_args()
    try:
        output = allowed_path(args.output, existing=False)
        if output.exists() or output.is_symlink() or not output.parent.is_dir():
            raise SeriesError("output exists or parent missing")
        sources = [allowed_path(p, existing=True) for p in args.bundles]
        if any(p.parent != output.parent for p in sources):
            raise SeriesError("source/output parents differ")
        report = build_series(sources)
        staged = Path(tempfile.mkdtemp(prefix=".grafana-series-", dir=str(output.parent)))
        os.chmod(staged, 0o700)
        for name, content in (
            ("report.json", canonical_json(report)),
            ("report.md", render_markdown(report)),
            ("file-inventory.txt", "report.json\nreport.md\n"),
        ):
            f = staged / name
            f.write_text(content, encoding="utf-8")
            os.chmod(f, 0o600)
        f = staged / "SHA256SUMS"
        f.write_text(manifest(staged), encoding="utf-8")
        os.chmod(f, 0o600)
        if output.exists() or output.is_symlink():
            raise SeriesError("output collision during publication")
        staged.rename(output)
    except (OSError, ValueError, TimeoutError) as error:
        print(f"Grafana series analysis: FAIL ({type(error).__name__})", file=sys.stderr)
        raise SystemExit(1)
    print("Grafana series analysis: descriptive-only bundle created")


if __name__ == "__main__":
    main()
