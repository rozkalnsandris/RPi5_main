#!/usr/bin/env python3
"""Strict verifier for V11 AdGuard memory-attribution bundles."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys

from adguard_memory_core import (
    COLLECTOR_VERSION,
    COMMIT_RE,
    SCHEMA,
    SECTION_FILES,
    UTC_RE,
    build_report,
    canonical_json,
    render_markdown,
)

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
MAX_FILE_BYTES = 524288
MAX_TOTAL_BYTES = 4194304
MAX_FILES = 32

FORBIDDEN_NAME_RE = re.compile(
    r"(?i)(?:^|/)(?:\.env|id_rsa|id_ed25519|authorized_keys|cert\.json)(?:$|[./])"
)
SECRET_ASSIGN_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|credential|cookie|authorization|private[_-]?key)"
    r"[A-Za-z0-9_-]*\s*[:=]\s*(?!\[REDACTED\])\S+"
)
TOKEN_RE = re.compile(r"gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|AKIA[0-9A-Z]+")
AUTH_RE = re.compile(r"(?i)\b(?:Bearer|Basic)\s+(?!\[REDACTED\])\S+")
URL_USERINFO_RE = re.compile(r"https?://[^/@\s]+:[^/@\s]+@")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Za-z ]*PRIVATE KEY-----")
MAC_RE = re.compile(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")
IPV4_RE = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
LONG_HEX_RE = re.compile(r"(?i)\b(?=[0-9a-f]{12,64}\b)(?=[0-9a-f]*[a-f])[0-9a-f]{12,64}\b")


def fail(message: str) -> None:
    print(f"AdGuard memory verification: FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def no_symlink_components(path: pathlib.Path) -> None:
    current = pathlib.Path(path.anchor or "/") if path.is_absolute() else pathlib.Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            fail("symlink path component rejected")


def allowed_bundle(path: pathlib.Path) -> pathlib.Path:
    requested = path if path.is_absolute() else pathlib.Path.cwd() / path
    no_symlink_components(requested)
    resolved = requested.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_symlink():
        fail("bundle target is not a regular directory")
    allowed = False
    for name in ("evidence", "exports"):
        try:
            resolved.relative_to(REPO / name)
            allowed = True
        except ValueError:
            pass
    if not allowed:
        fail("bundle is outside repository evidence/exports")
    return resolved


def scan_text(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = (
        SECRET_ASSIGN_RE,
        TOKEN_RE,
        AUTH_RE,
        URL_USERINFO_RE,
        PRIVATE_KEY_RE,
        MAC_RE,
        IPV4_RE,
        LONG_HEX_RE,
    )
    if any(pattern.search(text) for pattern in patterns):
        fail("secret-like or identifying content rejected")


def verify_manifest(bundle: pathlib.Path, files: list[pathlib.Path]) -> None:
    manifest = bundle / "SHA256SUMS"
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_./-]+)", line)
        if not match or match.group(2) in entries:
            fail("invalid checksum manifest")
        entries[match.group(2)] = match.group(1)
    expected = {
        str(path.relative_to(bundle))
        for path in files
        if path.name != "SHA256SUMS"
    }
    if set(entries) != expected:
        fail("checksum manifest coverage mismatch")
    for name, digest in entries.items():
        if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != digest:
            fail("checksum verification failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    args = parser.parse_args()
    try:
        bundle = allowed_bundle(pathlib.Path(args.bundle))
        required_root = {
            "metadata.json",
            "report.json",
            "report.md",
            "file-inventory.txt",
            "SHA256SUMS",
            "sections",
        }
        if {path.name for path in bundle.iterdir()} != required_root:
            fail("unexpected bundle root entries")
        sections = bundle / "sections"
        if (
            not sections.is_dir()
            or sections.is_symlink()
            or {path.name for path in sections.iterdir()} != set(SECTION_FILES)
        ):
            fail("unexpected section entries")

        paths = list(bundle.rglob("*"))
        files = [path for path in paths if path.is_file()]
        if len(files) > MAX_FILES:
            fail("file-count limit exceeded")
        total = 0
        for path in paths:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                fail("special or symlink artifact rejected")
            if stat.S_ISREG(mode):
                if path.stat().st_nlink != 1:
                    fail("hard-linked artifact rejected")
                if path.stat().st_uid != os.getuid():
                    fail("unexpected artifact owner")
                if path.stat().st_mode & stat.S_IWOTH:
                    fail("world-writable artifact rejected")
                size = path.stat().st_size
                if size > MAX_FILE_BYTES:
                    fail("per-file size limit exceeded")
                total += size
                relative = str(path.relative_to(bundle))
                if FORBIDDEN_NAME_RE.search(relative):
                    fail("forbidden file name rejected")
        if total > MAX_TOTAL_BYTES:
            fail("total size limit exceeded")

        verify_manifest(bundle, files)
        inventory = (bundle / "file-inventory.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        expected_inventory = sorted(
            str(path.relative_to(bundle))
            for path in files
            if path.name not in {"file-inventory.txt", "SHA256SUMS"}
        )
        if inventory != expected_inventory:
            fail("file inventory mismatch")

        for filename in SECTION_FILES:
            scan_text(sections / filename)

        metadata_text = (bundle / "metadata.json").read_text(encoding="utf-8")
        metadata = json.loads(metadata_text)
        if set(metadata) != {
            "schema",
            "collector_version",
            "git_commit",
            "collected_at_utc",
        }:
            fail("invalid metadata fields")
        if metadata["schema"] != SCHEMA or metadata["collector_version"] != COLLECTOR_VERSION:
            fail("invalid metadata version")
        if metadata["git_commit"] != "unavailable" and not COMMIT_RE.fullmatch(
            metadata["git_commit"]
        ):
            fail("invalid git commit")
        if not UTC_RE.fullmatch(metadata["collected_at_utc"]):
            fail("invalid collection time")
        if metadata_text != canonical_json(metadata):
            fail("metadata is not canonical JSON")

        expected_report = build_report(bundle, metadata)
        report_text = (bundle / "report.json").read_text(encoding="utf-8")
        actual_report = json.loads(report_text)
        if actual_report != expected_report or report_text != canonical_json(expected_report):
            fail("report JSON mismatch")
        if (bundle / "report.md").read_text(encoding="utf-8") != render_markdown(
            expected_report
        ):
            fail("report Markdown mismatch")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        fail(type(error).__name__)

    attr = expected_report["attribution"]
    print(
        "AdGuard memory verification: PASS "
        f"(level={expected_report['observation_level']}, "
        f"basis={attr['basis']}, dominant={attr['dominant_component']}, "
        f"anonymous_kib={attr['anonymous_kib']})"
    )


if __name__ == "__main__":
    main()
