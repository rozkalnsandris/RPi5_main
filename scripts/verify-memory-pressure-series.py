#!/usr/bin/env python3
"""Strict verifier for V09 memory-pressure series reports."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys

from memory_pressure_series import (
    ANALYZER_VERSION,
    LIMITATIONS,
    SAFE_NAME_RE,
    SCHEMA,
    SHA_RE,
    UTC_RE,
    canonical_json,
    classify,
    render_markdown,
)

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
MAX_FILE_BYTES = 1048576
MAX_TOTAL_BYTES = 2097152


def fail(message: str) -> None:
    print(f"Memory series verification: FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def no_symlink_components(path: pathlib.Path) -> None:
    current = pathlib.Path(path.anchor or "/")
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            fail("symlink path component rejected")


def _is_relative_to(path: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def allowed_directory(path: pathlib.Path) -> pathlib.Path:
    requested = path if path.is_absolute() else pathlib.Path.cwd() / path
    no_symlink_components(requested)
    resolved = requested.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink():
        fail("target is not a regular directory")
    if not any(_is_relative_to(resolved, REPO / name) for name in ("evidence", "exports")):
        fail("target is outside repository evidence/exports")
    return resolved


def exact_keys(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        fail(f"invalid {label} fields")
    return value


def require_int(value: object, label: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        fail(f"invalid {label}")
    if minimum is not None and value < minimum:
        fail(f"invalid {label}")
    if maximum is not None and value > maximum:
        fail(f"invalid {label}")
    return value


def verify_manifest(target: pathlib.Path) -> None:
    lines = (target / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    entries: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (report\.json|report\.md)", line)
        if not match or match.group(2) in entries:
            fail("invalid checksum manifest")
        entries[match.group(2)] = match.group(1)
    if set(entries) != {"report.json", "report.md"}:
        fail("checksum manifest coverage mismatch")
    for name, digest in entries.items():
        if hashlib.sha256((target / name).read_bytes()).hexdigest() != digest:
            fail("checksum verification failed")


def validate_report(report: dict) -> None:
    exact_keys(report, {
        "schema", "analyzer_version", "sample_count", "collection_start_utc",
        "collection_end_utc", "classification", "series_level", "sources",
        "samples", "aggregate", "containers", "evidence", "checks", "limitations",
    }, "report")
    if report["schema"] != SCHEMA or report["analyzer_version"] != ANALYZER_VERSION:
        fail("unsupported report version")
    sample_count = require_int(report["sample_count"], "sample count", minimum=2, maximum=64)
    if not isinstance(report["samples"], list) or len(report["samples"]) != sample_count:
        fail("sample count mismatch")
    if not isinstance(report["sources"], list) or len(report["sources"]) != sample_count:
        fail("source count mismatch")

    source_times: list[str] = []
    seen_names: set[str] = set()
    seen_digests: set[str] = set()
    for source in report["sources"]:
        exact_keys(source, {"bundle_name", "collection_utc", "report_sha256"}, "source")
        name = source["bundle_name"]
        timestamp = source["collection_utc"]
        digest = source["report_sha256"]
        if not isinstance(name, str) or not SAFE_NAME_RE.fullmatch(name) or name in seen_names:
            fail("invalid source bundle name")
        if not isinstance(timestamp, str) or not UTC_RE.fullmatch(timestamp):
            fail("invalid source timestamp")
        if not isinstance(digest, str) or not SHA_RE.fullmatch(digest) or digest in seen_digests:
            fail("invalid source digest")
        seen_names.add(name)
        seen_digests.add(digest)
        source_times.append(timestamp)

    samples: list[dict] = []
    sample_times: list[str] = []
    sample_keys = {
        "collection_utc", "source_level", "mem_available_kib",
        "mem_available_basis_points", "swap_used_kib", "pswpin_pages",
        "pswpout_pages", "pgmajfault", "oom_kill", "psi_some_total_usec",
        "psi_full_total_usec",
    }
    for sample in report["samples"]:
        exact_keys(sample, sample_keys, "sample")
        timestamp = sample["collection_utc"]
        if not isinstance(timestamp, str) or not UTC_RE.fullmatch(timestamp):
            fail("invalid sample timestamp")
        if sample["source_level"] not in {"none", "informational", "attention"}:
            fail("invalid source level")
        require_int(sample["mem_available_kib"], "available memory", minimum=0)
        require_int(sample["mem_available_basis_points"], "available percentage", minimum=0, maximum=10000)
        for key in (
            "swap_used_kib", "pswpin_pages", "pswpout_pages", "pgmajfault",
            "oom_kill", "psi_some_total_usec", "psi_full_total_usec",
        ):
            require_int(sample[key], key, minimum=0)
        sample_times.append(timestamp)
        samples.append(sample)
    if sample_times != sorted(sample_times) or len(set(sample_times)) != sample_count:
        fail("sample timestamps are not strictly increasing")
    if source_times != sample_times:
        fail("source/sample timestamp mismatch")
    if report["collection_start_utc"] != sample_times[0] or report["collection_end_utc"] != sample_times[-1]:
        fail("series window mismatch")

    expected_classification, expected_level, expected_evidence = classify(samples)
    if report["classification"] != expected_classification or report["series_level"] != expected_level:
        fail("classification mismatch")
    if report["evidence"] != expected_evidence:
        fail("classification evidence mismatch")

    aggregate = exact_keys(report["aggregate"], {
        "mem_available_min_basis_points", "mem_available_max_basis_points",
        "swap_used_first_kib", "swap_used_latest_kib", "swap_used_change_kib",
        "pswpin_pages_total", "pswpout_pages_total", "pgmajfault_total",
        "oom_kill_total", "psi_some_total_usec", "psi_full_total_usec",
        "source_attention_samples",
    }, "aggregate")
    expected_aggregate = {
        "mem_available_min_basis_points": min(row["mem_available_basis_points"] for row in samples),
        "mem_available_max_basis_points": max(row["mem_available_basis_points"] for row in samples),
        "swap_used_first_kib": samples[0]["swap_used_kib"],
        "swap_used_latest_kib": samples[-1]["swap_used_kib"],
        "swap_used_change_kib": samples[-1]["swap_used_kib"] - samples[0]["swap_used_kib"],
        "pswpin_pages_total": sum(row["pswpin_pages"] for row in samples),
        "pswpout_pages_total": sum(row["pswpout_pages"] for row in samples),
        "pgmajfault_total": sum(row["pgmajfault"] for row in samples),
        "oom_kill_total": sum(row["oom_kill"] for row in samples),
        "psi_some_total_usec": sum(row["psi_some_total_usec"] for row in samples),
        "psi_full_total_usec": sum(row["psi_full_total_usec"] for row in samples),
        "source_attention_samples": sum(1 for row in samples if row["source_level"] == "attention"),
    }
    if aggregate != expected_aggregate:
        fail("aggregate mismatch")

    if not isinstance(report["containers"], list):
        fail("invalid containers")
    names: list[str] = []
    container_keys = {
        "name", "sample_count", "first_kib", "latest_kib", "min_kib",
        "max_kib", "change_kib", "max_percent_basis_points",
    }
    for row in report["containers"]:
        exact_keys(row, container_keys, "container")
        name = row["name"]
        if not isinstance(name, str) or not SAFE_NAME_RE.fullmatch(name):
            fail("invalid container name")
        names.append(name)
        require_int(row["sample_count"], "container sample count", minimum=1, maximum=sample_count)
        for key in ("first_kib", "latest_kib", "min_kib", "max_kib"):
            require_int(row[key], key, minimum=0)
        require_int(row["change_kib"], "container change")
        require_int(row["max_percent_basis_points"], "container percent", minimum=0, maximum=10000)
        if row["change_kib"] != row["latest_kib"] - row["first_kib"]:
            fail("container change mismatch")
        if not row["min_kib"] <= min(row["first_kib"], row["latest_kib"]):
            fail("container minimum mismatch")
        if not max(row["first_kib"], row["latest_kib"]) <= row["max_kib"]:
            fail("container maximum mismatch")
    if names != sorted(names) or len(names) != len(set(names)):
        fail("container ordering mismatch")

    if report["checks"] != {
        "all_sources_verified": True,
        "timestamps_strictly_increasing": True,
        "units_normalized_to_kib": True,
        "source_bundles_unchanged": True,
    }:
        fail("verification checks mismatch")
    if report["limitations"] != list(LIMITATIONS):
        fail("limitations mismatch")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    args = parser.parse_args()
    try:
        target = allowed_directory(pathlib.Path(args.target))
        if {path.name for path in target.iterdir()} != {"report.json", "report.md", "SHA256SUMS"}:
            fail("unexpected report entries")
        total = 0
        for path in target.iterdir():
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                fail("special or symlink artifact rejected")
            if path.stat().st_nlink != 1 or path.stat().st_uid != os.getuid():
                fail("unsafe artifact ownership")
            if path.stat().st_mode & stat.S_IWOTH:
                fail("world-writable artifact rejected")
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                fail("per-file size limit exceeded")
            total += size
        if total > MAX_TOTAL_BYTES:
            fail("total size limit exceeded")
        verify_manifest(target)
        report_text = (target / "report.json").read_text(encoding="utf-8")
        report = json.loads(report_text)
        if report_text != canonical_json(report):
            fail("report is not canonical JSON")
        validate_report(report)
        if (target / "report.md").read_text(encoding="utf-8") != render_markdown(report):
            fail("report Markdown mismatch")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        fail(type(error).__name__)
    print(
        "Memory series verification: PASS "
        f"(samples={report['sample_count']}, classification={report['classification']})"
    )


if __name__ == "__main__":
    main()
