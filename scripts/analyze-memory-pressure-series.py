#!/usr/bin/env python3
"""Analyze a chronological series of verified V08 memory bundles."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from memory_pressure_series import build_report, canonical_json, render_markdown

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
SOURCE_VERIFIER = HERE / "verify-memory-pressure-diagnostic.py"


def fail(message: str) -> None:
    print(f"analyze-memory-pressure-series: {message}", file=sys.stderr)
    raise SystemExit(1)


def no_symlink_components(path: pathlib.Path) -> None:
    current = pathlib.Path(path.anchor or "/")
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            fail("symlink path component rejected")


def resolve_allowed(path: pathlib.Path, *, must_exist: bool) -> pathlib.Path:
    requested = path if path.is_absolute() else pathlib.Path.cwd() / path
    no_symlink_components(requested)
    resolved = requested.resolve(strict=must_exist)
    allowed = False
    for name in ("evidence", "exports"):
        try:
            resolved.relative_to(REPO / name)
            allowed = True
        except ValueError:
            pass
    if not allowed:
        fail("path is outside repository evidence/exports")
    return resolved


def verify_source(bundle: pathlib.Path) -> dict:
    completed = subprocess.run(
        [sys.executable, str(SOURCE_VERIFIER), str(bundle)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        fail("source bundle verification failed")
    try:
        return json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("source report could not be read")


def write_output(target: pathlib.Path, report: dict) -> None:
    if target.exists():
        fail("output target already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    no_symlink_components(target.parent)
    temporary = pathlib.Path(tempfile.mkdtemp(prefix=".v09-series-", dir=target.parent))
    try:
        os.chmod(temporary, 0o700)
        json_path = temporary / "report.json"
        markdown_path = temporary / "report.md"
        json_path.write_text(canonical_json(report), encoding="utf-8")
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        os.chmod(json_path, 0o600)
        os.chmod(markdown_path, 0o600)
        manifest = temporary / "SHA256SUMS"
        entries = []
        for path in (json_path, markdown_path):
            entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
        manifest.write_text("\n".join(entries) + "\n", encoding="utf-8")
        os.chmod(manifest, 0o600)
        os.replace(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("bundles", nargs="+")
    args = parser.parse_args()
    if not 2 <= len(args.bundles) <= 64:
        fail("expected 2 to 64 source bundles")
    try:
        bundles = [resolve_allowed(pathlib.Path(value), must_exist=True) for value in args.bundles]
        if len(set(bundles)) != len(bundles):
            fail("duplicate source bundle")
        reports = [verify_source(bundle) for bundle in bundles]
        report = build_report(bundles, reports)
        target = resolve_allowed(pathlib.Path(args.output), must_exist=False)
        write_output(target, report)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        fail(type(error).__name__)
    print(f"Memory series result: {target}")
    print(f"Classification: {report['classification']}")
    print(f"Series level: {report['series_level']}")


if __name__ == "__main__":
    main()
