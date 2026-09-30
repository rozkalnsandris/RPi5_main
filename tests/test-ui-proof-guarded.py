#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ops" / "bin" / "ui-proof-guarded"
ROUTING = ROOT / ".github" / "start-mode-routing.json"

loader = SourceFileLoader("ui_proof_guarded", str(LAUNCHER))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec and spec.loader
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


class FakeRunner:
    def __init__(self, returncodes: list[int]) -> None:
        self.returncodes = list(returncodes)
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], *, check: bool) -> subprocess.CompletedProcess[object]:
        self.calls.append(list(command))
        if not self.returncodes:
            raise AssertionError("unexpected runner call")
        return subprocess.CompletedProcess(command, self.returncodes.pop(0))


class GuardedUiProofTests(unittest.TestCase):
    def trusted_paths(self, root: Path) -> tuple[Path, Path]:
        guard = root / "rpi5-browser-lifecycle"
        renderer = root / "ui-proof"
        guard.write_text("guard\n", encoding="utf-8")
        renderer.write_text("renderer\n", encoding="utf-8")
        guard.chmod(0o700)
        renderer.chmod(0o700)
        return guard, renderer

    def test_missing_guard_fails_before_runner(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            renderer = root / "ui-proof"
            renderer.write_text("renderer\n", encoding="utf-8")
            renderer.chmod(0o700)
            fake = FakeRunner([])
            with mock.patch.object(launcher, "GUARD", root / "missing"), mock.patch.object(
                launcher, "RENDERER", renderer
            ):
                self.assertEqual(launcher.main(["https://example.invalid"], runner=fake), 75)
            self.assertEqual(fake.calls, [])

    def test_pre_health_blocked_does_not_start_renderer(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            guard, renderer = self.trusted_paths(root)
            fake = FakeRunner([3])
            with mock.patch.object(launcher, "GUARD", guard), mock.patch.object(
                launcher, "RENDERER", renderer
            ):
                self.assertEqual(launcher.main(["https://example.invalid"], runner=fake), 3)
            self.assertEqual(fake.calls, [[str(launcher.PYTHON), "-I", str(guard), "health"]])

    def test_exact_guarded_invocation_keeps_renderer_arguments_after_separator(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            guard, renderer = self.trusted_paths(root)
            fake = FakeRunner([0, 0, 0])
            args = ["https://example.invalid/a?x=1&y=$two", "label with spaces", str(root / "out dir")]
            with mock.patch.object(launcher, "GUARD", guard), mock.patch.object(
                launcher, "RENDERER", renderer
            ):
                self.assertEqual(launcher.main(args, runner=fake), 0)
            self.assertEqual(len(fake.calls), 3)
            run = fake.calls[1]
            expected_prefix = [
                str(launcher.PYTHON), "-I", str(guard), "run", "--label", "ui-proof",
                "--timeout-seconds", "180", "--", str(renderer),
            ]
            self.assertEqual(run[: len(expected_prefix)], expected_prefix)
            self.assertEqual(run[len(expected_prefix) :], args)
            separator = run.index("--")
            for value in args:
                self.assertNotIn(value, run[:separator])

    def test_renderer_timeout_is_preserved_and_post_health_still_runs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            guard, renderer = self.trusted_paths(root)
            fake = FakeRunner([0, 124, 0])
            with mock.patch.object(launcher, "GUARD", guard), mock.patch.object(
                launcher, "RENDERER", renderer
            ):
                self.assertEqual(launcher.main(["https://example.invalid"], runner=fake), 124)
            self.assertEqual(len(fake.calls), 3)
            self.assertEqual(fake.calls[2], [str(launcher.PYTHON), "-I", str(guard), "health"])

    def test_post_health_failure_overrides_apparent_renderer_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            guard, renderer = self.trusted_paths(root)
            fake = FakeRunner([0, 0, 3])
            with mock.patch.object(launcher, "GUARD", guard), mock.patch.object(
                launcher, "RENDERER", renderer
            ):
                self.assertEqual(launcher.main(["https://example.invalid"], runner=fake), 76)

    def test_repeated_synthetic_runs_do_not_create_launcher_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            guard, renderer = self.trusted_paths(root)
            before = sorted(path.name for path in root.iterdir())
            fake = FakeRunner([0, 0, 0, 0, 0, 0])
            with mock.patch.object(launcher, "GUARD", guard), mock.patch.object(
                launcher, "RENDERER", renderer
            ):
                self.assertEqual(launcher.main(["https://one.invalid"], runner=fake), 0)
                self.assertEqual(launcher.main(["https://two.invalid"], runner=fake), 0)
            self.assertEqual(sorted(path.name for path in root.iterdir()), before)

    def test_launcher_contains_no_broad_cleanup_or_raw_chromium_path(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        for forbidden in ("pkill", "killall", "cleanup-stale", "chromium"):
            self.assertNotIn(forbidden, source)

    def test_routing_manifest_uses_guarded_launcher(self) -> None:
        routing = json.loads(ROUTING.read_text(encoding="utf-8"))
        visual = routing["visual_verification"]
        self.assertEqual(visual["default_host_tool"], "~/.local/bin/ui-proof-guarded")
        self.assertIn("guarded", visual["rule"].lower())


if __name__ == "__main__":
    unittest.main()
