#!/usr/bin/env python3
"""Strict offline verifier for deterministic runtime-diff reports."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

_spec = importlib.util.spec_from_file_location(
    "runtime_diff", pathlib.Path(__file__).with_name("compare-runtime-baselines.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

FORBIDDEN = re.compile(
    r"(configfiles|environment=|execstart=|authorization:|private key|token=|(?:[0-9a-f]{2}:){5}[0-9a-f]{2})",
    re.IGNORECASE,
)


def fail() -> None:
    print("Runtime diff verification: FAIL", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 3:
        fail()
    repo = pathlib.Path(__file__).resolve().parent.parent
    paths = [pathlib.Path(value) for value in sys.argv[1:]]
    for path in paths:
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            fail()
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_nlink != 1
            or path.stat().st_size > 2_000_000
            or not any(
                str(resolved).startswith(str(root) + "/")
                for root in (
                    repo / "evidence",
                    repo / "exports",
                    repo / "baselines/runtime/archive",
                )
            )
        ):
            fail()
        if any(item.is_symlink() for item in (path, *path.parents)):
            fail()

    try:
        report = json.loads(paths[0].read_text(encoding="utf-8"))
        _module.validate_report(report)
        expected_markdown = _module.markdown(report)
    except Exception:
        fail()

    if paths[1].read_text(encoding="utf-8") != expected_markdown:
        fail()
    raw = paths[0].read_text(encoding="utf-8") + paths[1].read_text(
        encoding="utf-8"
    )
    if FORBIDDEN.search(raw):
        fail()
    print("Runtime diff verification: PASS")


if __name__ == "__main__":
    main()
