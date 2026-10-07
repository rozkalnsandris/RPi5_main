#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "rpi5_main_exact_source_prepare.py"
CONTRACT = ROOT / "ops" / "contracts" / "rpi5-main-exact-source-preparation-v1.json"

spec = importlib.util.spec_from_file_location("rpi5_main_exact_source_prepare", SOURCE)
assert spec and spec.loader
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)

TARGET = "b" * 40
CURRENT = "a" * 40


class FakeRunner:
    def __init__(
        self,
        root: Path,
        *,
        branch: str = "main",
        origin: str = "https://github.com/rozkalnsandris/RPi5_main.git",
        status: str = "",
        target_present: bool = True,
        ancestor: bool = True,
    ) -> None:
        self.root = root
        self.branch = branch
        self.origin = origin
        self.status = status
        self.target_present = target_present
        self.ancestor = ancestor

    def __call__(self, argv, **kwargs):
        cmd = list(argv)[3:]
        rc = 0
        out = ""
        if cmd == ["rev-parse", "--show-toplevel"]:
            out = str(self.root)
        elif cmd == ["branch", "--show-current"]:
            out = self.branch
        elif cmd == ["remote", "get-url", "origin"]:
            out = self.origin
        elif cmd == ["status", "--porcelain=v1", "--untracked-files=all"]:
            out = self.status
        elif cmd == ["rev-parse", "HEAD"]:
            out = CURRENT
        elif cmd == ["cat-file", "-e", f"{TARGET}^{{commit}}"]:
            rc = 0 if self.target_present else 128
        elif cmd == ["merge-base", "--is-ancestor", CURRENT, TARGET]:
            rc = 0 if self.ancestor else 1
        else:
            raise AssertionError(f"unexpected command: {cmd}")
        return subprocess.CompletedProcess(
            argv,
            rc,
            stdout=out + ("\n" if out else ""),
            stderr="",
        )


class ExactSourcePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def run_preflight(self, **kwargs):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(prep, "CHECKOUT_PATH", root):
                return prep.preflight(
                    TARGET,
                    runner=FakeRunner(root, **kwargs),
                )

    def test_clean_main_canonical_fast_forward_target_is_ready(self) -> None:
        report = self.run_preflight()
        self.assertEqual(report["result"], "PASS")
        self.assertTrue(report["apply_ready"])
        self.assertTrue(report["fetch_required"])
        self.assertFalse(report["mutation_performed"])

    def test_target_object_may_be_absent_without_mutating_preflight(self) -> None:
        report = self.run_preflight(target_present=False)
        self.assertTrue(report["fetch_required"])
        self.assertFalse(report["mutation_performed"])

    def test_dirty_nonmain_noncanonical_and_nonff_fail_closed(self) -> None:
        cases = [
            ({"status": " M tracked.txt"}, "checkout_dirty"),
            ({"branch": "feature"}, "branch_not_main"),
            ({"origin": "https://example.invalid/repo.git"}, "origin_not_canonical"),
            ({"ancestor": False}, "target_not_fast_forward"),
        ]
        for kwargs, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(prep.PrepareError, reason):
                    self.run_preflight(**kwargs)

    def test_cli_exposes_no_path_remote_ref_or_command_selection(self) -> None:
        args = prep.parse_args(["--expected-main", TARGET])
        for name in (
            "checkout",
            "path",
            "remote",
            "ref",
            "command",
            "argv",
            "environment",
        ):
            self.assertFalse(hasattr(args, name))
        with self.assertRaises(SystemExit):
            prep.parse_args(["--expected-main", TARGET, "--remote", "evil"])

    def test_contract_allows_only_fixed_fetch_and_ff_only_merge(self) -> None:
        commands = self.contract["future_apply"]["exact_commands"]
        self.assertEqual(
            commands[0][-4:],
            ["fetch", "--no-tags", "origin", "main"],
        )
        self.assertEqual(
            commands[1][-3:],
            ["merge", "--ff-only", "<expected-main>"],
        )
        forbidden = set(self.contract["forbidden"])
        for name in ("reset", "rebase", "clean", "force", "force-with-lease"):
            self.assertIn(name, forbidden)
        self.assertFalse(self.contract["future_apply"]["automatic_retry"])
        self.assertFalse(self.contract["future_apply"]["automatic_cleanup"])
        self.assertFalse(self.contract["future_apply"]["automatic_rollback"])
        self.assertFalse(self.contract["source_merge_authorizes_host_mutation"])


if __name__ == "__main__":
    unittest.main()
