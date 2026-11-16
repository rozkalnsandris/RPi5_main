#!/usr/bin/env python3
"""Synthetic-only regressions; never inspect RPi5, Docker, or real evidence."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from grafana_host_correlation_core import (  # noqa: E402
    CorrelationError, canonical_json, normalized_host, summarize,
)
from grafana_continuity_core import (  # noqa: E402
    SCHEMA, VERSION, event_deltas,
)

BASE = datetime(2026, 11, 15, 22, 0, tzinfo=timezone.utc)


def utc(sec: int) -> str:
    return (BASE + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")


def host(sec: int, *, span: int = 20, version: str = "v08.1.0",
         psi: int | None = None, pin: int = 0, pout: int = 0) -> dict:
    return {
        "schema": "rpi5.memory-pressure-diagnostic.v1",
        "metadata": {"collector_version": version, "git_commit": "b" * 40,
                     "collected_at_utc": utc(sec), "sample_seconds": span},
        "observation": {"mem_total_kib": 4_000_000, "mem_available_kib": 1_500_000,
                        "swap_used_kib": 1_000_000,
                        "sample_delta": {"pswpin_pages": pin, "pswpout_pages": pout,
                                         "pgmajfault": 3, "oom_kill": 0,
                                         "psi_some_total_usec": psi,
                                         "psi_full_total_usec": psi}},
    }


def grafana(*, start: int = 10, end: int = 70, delta: int = 109) -> dict:
    def reading(sec: int, elapsed: int, max_events: int) -> dict:
        counters = {"max": max_events, "oom": 0, "oom_kill": 0}
        return {"utc": utc(sec), "elapsed_ms": elapsed,
                "memory_current_bytes": 280_000_000,
                "memory_max_bytes": 314_572_800,
                "memory_swap_current_bytes": 100_000_000,
                "memory_peak_bytes": 315_000_000,
                "events_local": counters.copy(), "events_hierarchical": counters.copy()}
    observations = [reading(start, 0, 22), reading(end, (end - start) * 1000, 22 + delta)]
    return {"schema": SCHEMA, "collector_version": VERSION, "source_commit": "a" * 40,
            "synthetic": True, "identity_assertion": "collector_checked_in_process",
            "identity_scope": "single_invocation", "interval_seconds": end - start,
            "observations": observations, "event_deltas": event_deltas(observations)}


def rejects(hosts: list[dict], graph: dict) -> None:
    try:
        summarize(hosts, graph)
    except CorrelationError:
        return
    raise AssertionError("invalid host/Grafana evidence accepted")


def main() -> None:
    hs = [host(5, span=20, psi=0), host(40, span=20, pin=3, pout=1)]
    g = grafana()
    report = summarize(hs, g)
    assert report["synthetic"] and report["classification"] == "nominal_overlap_not_alignment"
    assert not report["verified_same_window"] and not report["proven_causation"]
    assert report["grafana"]["max_events"] == 109
    assert report["grafana"]["oom_events"] == 0
    assert report["host_windows"][0]["psi_full_usec"] == 0
    assert report["host_windows"][1]["psi_full_usec"] is None
    assert report["host_windows"][1]["pswpout_pages"] == 1
    assert report["host_windows"][0]["nominal_overlap"]
    assert canonical_json(report) == canonical_json(summarize(hs, g))
    assert "container" not in canonical_json(report).lower()

    apart = summarize([host(-120), host(-90)], g)
    assert apart["classification"] == "no_nominal_overlap"
    assert not any(x["nominal_overlap"] for x in apart["host_windows"])
    boundary = summarize([host(-10, span=20), host(70, span=20)], g)
    assert boundary["classification"] == "no_nominal_overlap", "touching boundaries are not overlap"
    old = normalized_host(host(10, version="v08.0.0", psi=0))
    assert old["psi_full_usec"] is None and old["psi_some_usec"] is None
    assert normalized_host(host(10, psi=None))["psi_full_usec"] is None
    assert normalized_host(host(10, psi=200))["psi_full_usec"] == 200
    for bad_hosts in ([], [host(0)], [host(i * 30) for i in range(9)],
                      [host(20), host(5)], [host(0), host(0)]):
        rejects(bad_hosts, g)
    malformed = copy.deepcopy(hs)
    malformed[0]["observation"]["sample_delta"]["pswpin_pages"] = True
    rejects(malformed, g)
    malformed = copy.deepcopy(hs)
    malformed[0]["observation"]["mem_available_kib"] = 5_000_000
    rejects(malformed, g)
    malformed = copy.deepcopy(hs)
    malformed[0]["metadata"]["sample_seconds"] = 0
    rejects(malformed, g)
    malformed = copy.deepcopy(hs)
    malformed[0]["metadata"]["collected_at_utc"] = "invalid"
    rejects(malformed, g)
    malformed = copy.deepcopy(hs)
    malformed[0]["metadata"]["git_commit"] = "password-token"
    rejects(malformed, g)
    malformed = copy.deepcopy(hs)
    malformed[0]["metadata"]["collector_version"] = "v08.future"
    rejects(malformed, g)
    bad = copy.deepcopy(g)
    bad["event_deltas"]["local"]["max"] = 110
    rejects(hs, bad)
    bad = copy.deepcopy(g)
    bad["identity_scope"] = "reused_cgroup"
    rejects(hs, bad)
    bad = copy.deepcopy(g)
    bad["observations"][1]["memory_max_bytes"] = 500
    rejects(hs, bad)
    print("Grafana/host offline correlation synthetic tests: PASS")


if __name__ == "__main__":
    main()
