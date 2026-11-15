#!/usr/bin/env python3
"""Synthetic, offline-only Grafana continuity report and verifier regressions."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from grafana_continuity_core import (  # noqa: E402
    SCHEMA, VERSION, EvidenceError, canonical_json, check_report, checksums,
    event_deltas, inventory, render_markdown,
)

def sample(utc: str, elapsed: int, max_events: int,
           oom_events: int = 0) -> dict:
    events = {"max": max_events, "oom": oom_events, "oom_kill": 0}
    return {
        "utc": utc, "elapsed_ms": elapsed,
        "memory_current_bytes": 296000000,
        "memory_max_bytes": 314572800,
        "memory_swap_current_bytes": 143000000,
        "memory_peak_bytes": 314572801,
        "events_local": dict(events),
        "events_hierarchical": dict(events),
    }

def expect_rejection(report: dict) -> None:
    try:
        check_report(report)
    except EvidenceError:
        return
    raise AssertionError("invalid continuity evidence accepted")

def verify_bundle(path: Path) -> int:
    return subprocess.run(
        [sys.executable, "-B", str(REPO / "scripts" /
                                   "verify-grafana-continuity.py"), str(path)],
        capture_output=True, timeout=10, check=False,
    ).returncode

def main() -> None:
    observations = [
        sample("2026-11-15T12:29:36Z", 0, 30664),
        sample("2026-11-15T12:29:51Z", 15000, 30670),
    ]
    report = {
        "schema": SCHEMA, "collector_version": VERSION,
        "source_commit": "a" * 40, "synthetic": True,
        "identity_assertion": "collector_checked_in_process",
        "identity_scope": "single_invocation", "interval_seconds": 15,
        "observations": observations, "event_deltas": event_deltas(observations),
    }
    check_report(report)
    assert report["event_deltas"]["local"] == {
        "max": 6, "oom": 0, "oom_kill": 0,
    }
    assert "6/0/0" in render_markdown(report)

    bad = copy.deepcopy(report)
    bad["event_deltas"]["local"]["oom"] = 1
    expect_rejection(bad)
    bad = copy.deepcopy(report)
    bad["observations"][1]["events_local"]["max"] = 30663
    expect_rejection(bad)
    bad = copy.deepcopy(report)
    bad["container_id"] = "0123456789abcdef" * 4
    expect_rejection(bad)
    bad = copy.deepcopy(report)
    bad["identity_scope"] = "independent_snapshots"
    expect_rejection(bad)
    bad = copy.deepcopy(report)
    bad["observations"][1]["elapsed_ms"] = 0
    expect_rejection(bad)
    bad = copy.deepcopy(report)
    bad["observations"][1]["memory_max_bytes"] = 314572799
    expect_rejection(bad)
    bad = copy.deepcopy(report)
    bad["observations"][1]["events_local"].pop("oom_kill")
    expect_rejection(bad)
    bad = copy.deepcopy(report)
    bad["observations"][1]["events_local"]["oom_kill"] = True
    expect_rejection(bad)

    root = Path(tempfile.mkdtemp(prefix="grafana-continuity-test.",
                                 dir=REPO / "evidence"))
    try:
        out = root / "sample"
        out.mkdir(mode=0o700)
        payload = canonical_json(report).encode("utf-8")
        markdown = render_markdown(report).encode("utf-8")
        for name, raw in (
            ("report.json", payload), ("report.md", markdown),
            ("file-inventory.txt", inventory().encode("ascii")),
            ("SHA256SUMS", checksums(payload, markdown).encode("ascii")),
        ):
            path = out / name
            path.write_bytes(raw)
            path.chmod(0o600)
        assert verify_bundle(out) == 0
        (out / "report.md").write_text("tampered\n")
        assert verify_bundle(out) != 0
        (out / "report.md").write_bytes(markdown)
        (out / "report.md").chmod(0o600)
        (out / "report.md").unlink()
        (out / "report.md").symlink_to(out / "report.json")
        assert verify_bundle(out) != 0
        (out / "report.md").unlink()
        (out / "report.md").write_bytes(markdown)
        (out / "report.md").chmod(0o600)
        link = root / "linked"
        link.symlink_to(out, target_is_directory=True)
        assert verify_bundle(link) != 0
        (out / "unexpected.txt").write_text("bad")
        assert verify_bundle(out) != 0
    finally:
        shutil.rmtree(root)
    print("Grafana continuity offline synthetic tests: PASS")

if __name__ == "__main__":
    main()
