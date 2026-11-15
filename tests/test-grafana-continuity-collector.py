#!/usr/bin/env python3
"""Synthetic only: pinned Grafana cgroup identity, bounded events, publication."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "grafana_continuity_capture",
    REPO / "scripts" / "collect-grafana-continuity.py",
)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)
CID = "0123456789abcdef" * 4
SHA = "a" * 40
PID = 123


class Clock:
    def __init__(self) -> None:
        self.value = 1000.0
        self.after_sleep = None

    def tick(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds
        if self.after_sleep:
            self.after_sleep()

    def wall(self) -> str:
        stamp = datetime(2026, 11, 15, tzinfo=timezone.utc)
        stamp += timedelta(seconds=round(self.value - 1000))
        return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def contents(directory: Path, *, start: int = 999) -> None:
    proc = directory / "proc" / str(PID)
    cg = directory / "cgroup" / "system.slice" / f"docker-{CID}.scope"
    proc.mkdir(parents=True)
    cg.mkdir(parents=True)
    (proc / "comm").write_text("grafana\n", encoding="ascii")
    # The field after the parenthesized comm is #3; starttime is #22.
    tail = ["S"] + ["0"] * 18 + [str(start)] + ["0"] * 24
    (proc / "stat").write_text(
        f"{PID} (grafana worker) " + " ".join(tail) + "\n", encoding="ascii",
    )
    (proc / "cgroup").write_text(
        f"0::/system.slice/docker-{CID}.scope\n", encoding="ascii",
    )
    for filename, value in {
        "memory.current": "296000000\n",
        "memory.max": "314572800\n",
        "memory.swap.current": "14000000\n",
        "memory.peak": "314572801\n",
        "memory.events.local": "low 0\nhigh 0\nmax 12\noom 0\noom_kill 0\n",
        "memory.events": "low 0\nhigh 0\nmax 12\noom 0\noom_kill 0\n",
    }.items():
        (cg / filename).write_text(value, encoding="ascii")


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(
        prefix="test-grafana-continuous.", dir=REPO / "evidence"
    ) as base:
        root = Path(base)
        contents(root)
        with (mock.patch.object(collector, "TEST_MODE", True),
              mock.patch.object(collector, "PROC", root / "proc"),
              mock.patch.object(collector, "CGROUP", root / "cgroup"),
              mock.patch.object(collector.os, "geteuid", return_value=1000),
              mock.patch.object(collector, "source_sha", return_value=SHA),
              mock.patch.object(collector, "docker_id", return_value=CID)):
            yield root


def run(root: Path, output: str = "capture", clock: Clock | None = None) -> Path:
    clock = clock or Clock()
    target = root / output
    collector.collect(
        str(target), samples=2, interval=15,
        tick=clock.tick, pause=clock.sleep, wall=clock.wall,
    )
    return target


def must_fail(action) -> None:
    try:
        action()
    except (collector.CaptureError, collector.EvidenceError, OSError,
            ValueError, UnicodeError, subprocess.SubprocessError):
        return
    raise AssertionError("unsafe continuity collection was accepted")


def verify(path: Path) -> int:
    return subprocess.run([
        sys.executable, "-B",
        str(REPO / "scripts" / "verify-grafana-continuity.py"), str(path),
    ], capture_output=True, timeout=10, check=False).returncode


def main() -> None:
    with fixture() as root:
        cg = root / "cgroup" / "system.slice" / f"docker-{CID}.scope"
        clock = Clock()

        def add_max():
            for name in ("memory.events", "memory.events.local"):
                path = cg / name
                path.write_text(path.read_text().replace("max 12", "max 19"))
        clock.after_sleep = add_max
        out = run(root, clock=clock)
        assert verify(out) == 0
        report = json.loads((out / "report.json").read_text())
        assert report["event_deltas"]["local"] == {
            "max": 7, "oom": 0, "oom_kill": 0,
        }
        assert report["event_deltas"]["hierarchical"]["max"] == 7
        assert report["synthetic"] is True
        assert report["observations"][1]["elapsed_ms"] == 15000
        text = "\n".join(file.read_text() for file in out.iterdir())
        assert CID not in text and f"docker-{CID}" not in text
        assert "grafana worker" not in text
        assert verify(out) == 0
        (out / "report.md").write_text("tampered\n")
        assert verify(out) != 0

    with fixture() as root:
        cg = root / "cgroup" / "system.slice" / f"docker-{CID}.scope"
        (cg / "memory.swap.current").unlink()
        (cg / "memory.peak").unlink()
        target = run(root)
        assert verify(target) == 0
        first = json.loads((target / "report.json").read_text())["observations"][0]
        assert first["memory_swap_current_bytes"] is None
        assert first["memory_peak_bytes"] is None

    with fixture() as root:
        change = {"id": CID}
        clock = Clock()
        clock.after_sleep = lambda: change.update(id="f" * 64)
        with mock.patch.object(collector, "docker_id",
                               side_effect=lambda: change["id"]):
            must_fail(lambda: run(root, "changed-container", clock))
        assert not (root / "changed-container").exists()

    with fixture() as root:
        stat_file = root / "proc" / str(PID) / "stat"
        clock = Clock()
        clock.after_sleep = lambda: stat_file.write_text(
            stat_file.read_text().replace(" 999 ", " 1001 "))
        must_fail(lambda: run(root, "pid-reused", clock))
        assert not (root / "pid-reused").exists()

    with fixture() as root:
        cg = root / "cgroup" / "system.slice" / f"docker-{CID}.scope"
        clock = Clock()
        def replace_cgroup():
            cg.rename(root / "old-cgroup")
            cg.mkdir()
        clock.after_sleep = replace_cgroup
        must_fail(lambda: run(root, "replaced-inode", clock))
        assert not (root / "replaced-inode").exists()

    with fixture() as root:
        cg = root / "cgroup" / "system.slice" / f"docker-{CID}.scope"
        clock = Clock()
        def decrease_counter():
            for name in ("memory.events", "memory.events.local"):
                path = cg / name
                path.write_text(path.read_text().replace("max 12", "max 11"))
        clock.after_sleep = decrease_counter
        must_fail(lambda: run(root, "regression", clock))
        assert not (root / "regression").exists()

    with fixture() as root:
        cg = root / "cgroup" / "system.slice" / f"docker-{CID}.scope"
        (cg / "memory.events.local").unlink()
        must_fail(lambda: run(root, "missing-events"))
        assert not (root / "missing-events").exists()

    with fixture() as root:
        cg = root / "cgroup" / "system.slice" / f"docker-{CID}.scope"
        (cg / "memory.events").unlink()
        (cg / "memory.events").symlink_to(cg / "memory.events.local")
        must_fail(lambda: run(root, "symlink-metric"))
        assert not (root / "symlink-metric").exists()

    with fixture() as root:
        second = root / "proc" / "124"
        second.mkdir()
        (second / "comm").write_text("grafana\n")
        must_fail(lambda: run(root, "ambiguous-process"))

    with fixture() as root:
        (root / "collision").mkdir()
        must_fail(lambda: run(root, "collision"))
        (root / "link").symlink_to(root / "collision", target_is_directory=True)
        must_fail(lambda: run(root, "link/nested"))
        must_fail(lambda: collector.collect(
            "/tmp/untrusted-output", 2, 15, tick=Clock().tick,
        ))
        must_fail(lambda: collector.collect(str(root / "too-few"), 1, 15))
        must_fail(lambda: collector.collect(str(root / "too-fast"), 2, 14))

    with fixture() as root:
        # Simulate a separate actor creating the destination after preflight.
        original_run = collector.subprocess.run
        output = root / "publication-collision"
        def inject_collision(*args, **kwargs):
            argv = args[0]
            if isinstance(argv, list) and "verify-grafana-continuity.py" in " ".join(argv):
                output.mkdir()
            return original_run(*args, **kwargs)
        with mock.patch.object(collector.subprocess, "run",
                               side_effect=inject_collision):
            must_fail(lambda: run(root, "publication-collision"))
        assert output.is_dir() and not list(output.iterdir())
        assert any(p.name.startswith(".publication-collision.") for p in root.iterdir())

    print("Grafana continuous collector synthetic regressions: PASS")


if __name__ == "__main__":
    main()
