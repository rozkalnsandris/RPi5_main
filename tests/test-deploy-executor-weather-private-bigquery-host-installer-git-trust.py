#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import weather_private_bigquery_host_installer as installer  # noqa: E402


class WeatherNextPrivateHostInstallerGitTrustTests(unittest.TestCase):
    def test_git_trust_is_exact_command_scoped_for_fixed_checkouts(self):
        completed = subprocess.CompletedProcess(
            args=(),
            returncode=0,
            stdout="ok\n",
            stderr="",
        )
        for checkout in (installer.MANAGER_CHECKOUT, installer.TRUSTED_CHECKOUT):
            with self.subTest(checkout=str(checkout)):
                with mock.patch.object(
                    installer.subprocess,
                    "run",
                    return_value=completed,
                ) as run_process:
                    result = installer._run_git(checkout, "rev-parse", "HEAD")

                self.assertEqual(result.stdout, "ok\n")
                argv = run_process.call_args.args[0]
                self.assertEqual(
                    argv[:6],
                    (
                        "/usr/bin/git",
                        "-c",
                        f"safe.directory={checkout}",
                        "--no-optional-locks",
                        "-C",
                        str(checkout),
                    ),
                )
                self.assertNotIn("safe.directory=*", argv)
                self.assertNotIn("--global", argv)
                self.assertNotIn("--system", argv)
                self.assertFalse(run_process.call_args.kwargs["shell"])

    def test_arbitrary_checkout_is_rejected_before_git_process(self):
        with mock.patch.object(installer.subprocess, "run") as run_process:
            with self.assertRaises(installer.WeatherNextPrivateHostInstallerError):
                installer._run_git(Path("/tmp/unreviewed-checkout"), "rev-parse", "HEAD")
        run_process.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
