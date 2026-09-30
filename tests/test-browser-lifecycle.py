#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops" / "lib" / "browser_lifecycle.py"
CLI = ROOT / "ops" / "bin" / "rpi5-browser-lifecycle"

spec = importlib.util.spec_from_file_location("browser_lifecycle", MODULE_PATH)
assert spec and spec.loader
bl = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bl
spec.loader.exec_module(bl)


def wait_gone(pid: int, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}").exists():
            return True
        time.sleep(0.05)
    return not Path(f"/proc/{pid}").exists()


class BrowserLifecycleTests(unittest.TestCase):
    def run_cli(self, *args: str, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
        )

    def test_success_reaps_descendant_and_leaves_no_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pid_file = root / "child.pid"
            helper = root / "helper.py"
            helper.write_text(
                "import pathlib,subprocess,sys\n"
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
                f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid))\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "run",
                "--state-dir",
                str(root / "state"),
                "--timeout-seconds",
                "5",
                "--term-grace-seconds",
                "0.2",
                "--min-mem-available-mib",
                "1",
                "--max-swap-used-percent",
                "100",
                "--",
                sys.executable,
                str(helper),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            child_pid = int(pid_file.read_text())
            self.assertTrue(wait_gone(child_pid))
            self.assertEqual(list((root / "state").glob("*.json")), [])

    def test_timeout_reaps_leader(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pid_file = root / "leader.pid"
            helper = root / "sleep.py"
            helper.write_text(
                f"import os,pathlib,time\npathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "run",
                "--state-dir",
                str(root / "state"),
                "--timeout-seconds",
                "1.2",
                "--term-grace-seconds",
                "0.2",
                "--poll-seconds",
                "0.05",
                "--min-mem-available-mib",
                "1",
                "--max-swap-used-percent",
                "100",
                "--",
                sys.executable,
                str(helper),
            )
            self.assertEqual(result.returncode, 124, result.stderr)
            leader_pid = int(pid_file.read_text())
            self.assertTrue(wait_gone(leader_pid))
            self.assertEqual(list((root / "state").glob("*.json")), [])

    def test_unrelated_chromium_named_process_is_preserved_and_reported(self) -> None:
        code = (
            "import ctypes,time\n"
            "libc=ctypes.CDLL(None)\n"
            "libc.prctl(15, b'chromium', 0, 0, 0)\n"
            "time.sleep(30)\n"
        )
        unrelated = subprocess.Popen(
            [sys.executable, "-c", code],
            start_new_session=True,
        )
        try:
            time.sleep(0.15)
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                result = self.run_cli(
                    "run",
                    "--state-dir",
                    str(root / "state"),
                    "--timeout-seconds",
                    "3",
                    "--min-mem-available-mib",
                    "1",
                    "--max-swap-used-percent",
                    "100",
                    "--",
                    sys.executable,
                    "-c",
                    "pass",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsNone(unrelated.poll())
                health = self.run_cli(
                    "health",
                    "--state-dir",
                    str(root / "state"),
                    "--min-mem-available-mib",
                    "1",
                    "--max-swap-used-percent",
                    "100",
                )
                self.assertEqual(health.returncode, 0, health.stderr)
                report = json.loads(health.stdout)
                self.assertGreaterEqual(report["unrelated_browser_processes"], 1)
                self.assertFalse(report["process_cmdline_read"])
                self.assertFalse(report["process_environment_read"])
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=3)

    def test_pid_reuse_is_ambiguous_and_not_owned(self) -> None:
        record = bl.RunRecord(
            run_id="a" * 32,
            label="test",
            owner_pid=100,
            owner_start_ticks=10,
            leader_pid=200,
            leader_start_ticks=20,
            created_at=time.time(),
            timeout_seconds=30,
            members={200: 20},
        )
        snapshot = {
            200: bl.ProcInfo(
                pid=200,
                ppid=1,
                pgrp=200,
                sid=200,
                start_ticks=999,
                comm="chromium",
            )
        }
        view = bl.collect_owned(record, snapshot)
        self.assertEqual(view.owned, {})
        self.assertIn("leader_pid_reuse", view.blockers)
        self.assertIn("member_pid_reuse:200", view.blockers)

    def test_crash_recovery_is_exact_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_dir = root / "state"
            guard = subprocess.Popen(
                [
                    sys.executable,
                    str(CLI),
                    "run",
                    "--state-dir",
                    str(state_dir),
                    "--timeout-seconds",
                    "30",
                    "--min-mem-available-mib",
                    "1",
                    "--max-swap-used-percent",
                    "100",
                    "--",
                    sys.executable,
                    "-c",
                    "import time; time.sleep(30)",
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                deadline = time.monotonic() + 3
                state_files: list[Path] = []
                while time.monotonic() < deadline:
                    state_files = list(state_dir.glob("*.json"))
                    if state_files:
                        break
                    time.sleep(0.05)
                self.assertEqual(len(state_files), 1)
                record = bl.RunRecord.from_dict(json.loads(state_files[0].read_text()))
                leader_pid = record.leader_pid

                os.kill(guard.pid, signal.SIGKILL)
                guard.wait(timeout=3)
                self.assertTrue(Path(f"/proc/{leader_pid}").exists())

                clean = self.run_cli(
                    "cleanup-stale",
                    "--state-dir",
                    str(state_dir),
                    "--min-age-seconds",
                    "0",
                    "--term-grace-seconds",
                    "0.2",
                )
                self.assertEqual(clean.returncode, 0, clean.stderr)
                self.assertTrue(wait_gone(leader_pid))
                report = json.loads(clean.stdout)
                self.assertEqual(report["cleaned_records"], 1)

                again = self.run_cli(
                    "cleanup-stale",
                    "--state-dir",
                    str(state_dir),
                    "--min-age-seconds",
                    "0",
                )
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertEqual(json.loads(again.stdout)["cleaned_records"], 0)
            finally:
                if guard.poll() is None:
                    guard.kill()
                    guard.wait(timeout=3)

    def test_repeated_runs_do_not_accumulate_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            for _ in range(4):
                result = self.run_cli(
                    "run",
                    "--state-dir",
                    str(state_dir),
                    "--timeout-seconds",
                    "3",
                    "--min-mem-available-mib",
                    "1",
                    "--max-swap-used-percent",
                    "100",
                    "--",
                    sys.executable,
                    "-c",
                    "pass",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(list(state_dir.glob("*.json")), [])

    def test_source_has_no_broad_process_killer(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8") + CLI.read_text(encoding="utf-8")
        self.assertNotIn("pkill", source)
        self.assertNotIn("killall", source)


if __name__ == "__main__":
    unittest.main()
