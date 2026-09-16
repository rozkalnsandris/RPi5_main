#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import hermes_deals_runner_smoke_broker_bootstrap as bootstrap


class RunnerSmokeSystemctlStateTests(unittest.TestCase):
    def test_absent_fixed_socket_unit_normalizes_to_not_found(self) -> None:
        result = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr=(
                "Failed to get unit file state for "
                f"{bootstrap.SOCKET_UNIT}: No such file or directory\n"
            ),
        )
        with mock.patch.object(bootstrap.subprocess, "run", return_value=result) as run:
            self.assertEqual(
                bootstrap._systemctl_state("is-enabled", bootstrap.SOCKET_UNIT),
                "not-found",
            )
        run.assert_called_once()
        self.assertEqual(
            run.call_args.args[0],
            ["/usr/bin/systemctl", "is-enabled", bootstrap.SOCKET_UNIT],
        )
        self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C.UTF-8")

    def test_unexpected_is_enabled_error_stays_fail_closed(self) -> None:
        result = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="Failed to connect to bus: No medium found\n",
        )
        with mock.patch.object(bootstrap.subprocess, "run", return_value=result):
            with self.assertRaises(bootstrap.RunnerSmokeBrokerBootstrapError):
                bootstrap._systemctl_state("is-enabled", bootstrap.SOCKET_UNIT)


if __name__ == "__main__":
    unittest.main()
