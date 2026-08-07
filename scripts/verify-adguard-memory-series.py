#!/usr/bin/env python3
"""Strict verifier for a four-sample V11 AdGuard memory-attribution series."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
import sys

from adguard_memory_core import canonical_json
from adguard_memory_series_core import (
    SERIES_SAMPLE_COUNT,
    build_series,
    render_series_markdown,
)

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
SAMPLE_VERIFIER = HERE / "verify-adguard-memory-attribution.py"
MAX_TOP_FILE_BYTES = 1024 * 1024


def fail(message: str) -> None:
    print(f"AdGuard memory series verification: FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def no_symlink_components(path: pathlib.Path) -> None:
    current = pathlib.Path(path.anchor or "/") if path.is_absolute() else pathlib.Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            fail("symlink path component rejected")


def allowed_series(path: pathlib.Path) -> pathlib.Path:
    requested = path if path.is_absolute() else pathlib.Path.cwd() / path
    no_symlink_components(requested)
    resolved = requested.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink():
        fail("series target is not a regular directory")
    for name in ("evidence", "exports"):
        try:
            resolved.relative_to((REPO / name).resolve())
            return resolved
        except ValueError:
            continue
    fail("series is outside repository evidence/exports")


def safe_regular(path: pathlib.Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        fail(f"not a regular file: {path.name}")
    if info.st_nlink != 1:
        fail(f"hard-linked file rejected: {path.name}")
    if info.st_uid != os.getuid():
        fail(f"unexpected owner: {path.name}")
    if info.st_mode & stat.S_IWOTH:
        fail(f"world-writable file rejected: {path.name}")
    if info.st_size > MAX_TOP_FILE_BYTES:
        fail(f"series file too large: {path.name}")


def verify_checksums(series: pathlib.Path) -> None:
    expected_names = {"series.json", "series.md"}
    expected_names.update(
        f"samples/{index:02d}/report.json"
        for index in range(1, SERIES_SAMPLE_COUNT + 1)
    )
    entries: dict[str, str] = {}
    for line in (series / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_./-]+)", line)
        if not match or match.group(2) in entries:
            fail("invalid series checksum manifest")
        entries[match.group(2)] = match.group(1)
    if set(entries) != expected_names:
        fail("series checksum coverage mismatch")
    for relative, digest in entries.items():
        path = series / relative
        safe_regular(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            fail(f"series checksum mismatch: {relative}")


def verify_sample(path: pathlib.Path) -> dict:
    if path.is_symlink() or not path.is_dir():
        fail("sample path is unsafe")
    completed = subprocess.run(
        [sys.executable, str(SAMPLE_VERIFIER), str(path)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    if completed.returncode != 0:
        fail(f"sample verification failed: {path.name}")
    return json.loads((path / "report.json").read_text(encoding="utf-8"))


def verify(series: pathlib.Path) -> dict:
    required_root = {"samples", "series.json", "series.md", "SHA256SUMS"}
    if {path.name for path in series.iterdir()} != required_root:
        fail("unexpected series root entries")
    samples_dir = series / "samples"
    if samples_dir.is_symlink() or not samples_dir.is_dir():
        fail("samples directory is unsafe")
    expected_sample_names = {f"{index:02d}" for index in range(1, SERIES_SAMPLE_COUNT + 1)}
    if {path.name for path in samples_dir.iterdir()} != expected_sample_names:
        fail("unexpected sample directory set")

    for name in ("series.json", "series.md", "SHA256SUMS"):
        safe_regular(series / name)
    reports = [
        verify_sample(samples_dir / f"{index:02d}")
        for index in range(1, SERIES_SAMPLE_COUNT + 1)
    ]
    expected = build_series(reports)
    series_text = (series / "series.json").read_text(encoding="utf-8")
    actual = json.loads(series_text)
    if actual != expected or series_text != canonical_json(expected):
        fail("series JSON mismatch")
    if (series / "series.md").read_text(encoding="utf-8") != render_series_markdown(expected):
        fail("series Markdown mismatch")
    verify_checksums(series)
    return expected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("series")
    args = parser.parse_args()
    try:
        result = verify(allowed_series(pathlib.Path(args.series)))
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        fail(type(exc).__name__)
    print(
        "AdGuard memory series verification: PASS "
        f"(samples={result['sample_count']}, "
        f"dominant={result['stable_dominant_component']}, "
        f"change_kib={result['container_usage_change_kib']})"
    )


if __name__ == "__main__":
    main()
