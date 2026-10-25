"""Disconnected tests for the canonical GoatCounter isolated proof v2.

No GoatCounter binary, network, RPi5 runtime, production database, credential,
service, Cloudflare route or protected runtime state is touched.
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ausmalwiese_goatcounter_isolated_probe_v2 as runtime  # noqa: E402


class IsolatedProofV2Tests(unittest.TestCase):
    def test_reuses_exact_pinned_v27_runtime_and_existing_privacy_path(self):
        self.assertEqual(
            runtime.base.RELEASE_ASSETS,
            {
                "arm64": {
                    "name": "goatcounter-v2.7.0-linux-arm64.gz",
                    "size": 12770791,
                    "sha256": (
                        "ff5b2670b858bbe48802dfdc74130b6d"
                        "cde2de9f5c1229b838eb9132769307dd"
                    ),
                }
            },
        )
        self.assertEqual(runtime.base.PAGE_ID, "0427183")
        self.assertEqual(runtime.base.VIEWS, 2)

    def test_each_setup_nonzero_maps_to_stage_specific_silent_code(self):
        cases = (
            (("db", "newdb", "-db=synthetic"), "SYNTHETIC_DB_CREATE_FAILED"),
            (
                ("db", "create", "site", "-vhost=stats.example.test"),
                "SYNTHETIC_SITE_CREATE_FAILED",
            ),
            (
                ("db", "create", "apitoken", "-perm=count"),
                "SYNTHETIC_API_TOKEN_CREATE_FAILED",
            ),
        )
        for argv, expected in cases:
            with self.subTest(expected=expected):
                stdout = io.StringIO()
                stderr = io.StringIO()
                completed = mock.Mock(returncode=7)
                with mock.patch.object(
                    runtime.subprocess, "run", return_value=completed
                ) as run:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        with self.assertRaises(runtime.base.RuntimeStop) as raised:
                            runtime._run_stage(
                                Path("/synthetic/bin"),
                                Path("/tmp/synthetic"),
                                {"PATH": "/usr/bin:/bin"},
                                *argv,
                            )
                self.assertEqual(str(raised.exception), expected)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(stderr.getvalue(), "")
                self.assertIs(run.call_args.kwargs["stdout"], runtime.subprocess.DEVNULL)
                self.assertIs(run.call_args.kwargs["stderr"], runtime.subprocess.DEVNULL)
                self.assertEqual(run.call_count, 1)

    def test_setup_exec_error_uses_same_sanitized_stage_code(self):
        with mock.patch.object(
            runtime.subprocess,
            "run",
            side_effect=OSError("synthetic upstream detail that must stay hidden"),
        ):
            with self.assertRaises(runtime.base.RuntimeStop) as raised:
                runtime._run_stage(
                    Path("/synthetic/bin"),
                    Path("/tmp/synthetic"),
                    {"PATH": "/usr/bin:/bin"},
                    "db",
                    "create",
                    "site",
                )
        self.assertEqual(str(raised.exception), "SYNTHETIC_SITE_CREATE_FAILED")
        self.assertNotIn("upstream", str(raised.exception))

    def test_unknown_setup_stage_fails_closed(self):
        self.assertEqual(
            runtime._stage_failure_code(("unexpected", "command")),
            "SYNTHETIC_SETUP_STAGE_INVALID",
        )

    def test_base_runner_is_restored_even_when_site_setup_fails(self):
        original = runtime.base._run
        with mock.patch.object(
            runtime.base,
            "_make_site",
            side_effect=runtime.base.RuntimeStop("SYNTHETIC_DB_CREATE_FAILED"),
        ):
            with self.assertRaises(runtime.base.RuntimeStop):
                runtime._make_site_with_stage_diagnostics(
                    Path("/synthetic/bin"),
                    Path("/tmp/synthetic"),
                    {},
                    Path("/tmp/synthetic/db.sqlite3"),
                )
        self.assertIs(runtime.base._run, original)

    def test_runtime_failure_preserves_private_fixture_and_skips_cleanup(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as parent:
            root = Path(parent) / "goatcounter-offline-retained"
            root.mkdir()
            os.chmod(root, 0o700)

            with mock.patch.object(runtime.base, "_host_guard"),                     mock.patch.object(runtime, "_new_fixture_root", return_value=root),                     mock.patch.object(
                        runtime,
                        "_run_fixture",
                        side_effect=runtime.base.RuntimeStop(
                            "SYNTHETIC_API_TOKEN_CREATE_FAILED"
                        ),
                    ),                     mock.patch.object(runtime, "_cleanup_success_fixture") as cleanup:
                with self.assertRaises(runtime.base.RuntimeStop):
                    runtime.run_isolated("/tmp/synthetic-release.gz")

            cleanup.assert_not_called()
            self.assertTrue(root.is_dir())
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)

    def test_complete_pass_runs_success_cleanup_exactly_once(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as parent:
            root = Path(parent) / "goatcounter-offline-success"
            root.mkdir()
            os.chmod(root, 0o700)

            with mock.patch.object(runtime.base, "_host_guard"),                     mock.patch.object(runtime, "_new_fixture_root", return_value=root),                     mock.patch.object(runtime, "_run_fixture") as run_fixture:
                result = runtime.run_isolated("/tmp/synthetic-release.gz")

            run_fixture.assert_called_once_with("/tmp/synthetic-release.gz", root)
            self.assertEqual(result, runtime.PASS)
            self.assertFalse(root.exists())

    def test_main_outputs_only_stable_failure_code(self):
        stdout = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            ["probe-v2", "--release-archive", "/tmp/synthetic-release.gz"],
        ), mock.patch.object(
            runtime,
            "run_isolated",
            side_effect=runtime.base.RuntimeStop("SYNTHETIC_SITE_CREATE_FAILED"),
        ), contextlib.redirect_stdout(stdout):
            rc = runtime.main()

        self.assertEqual(rc, 2)
        self.assertEqual(
            stdout.getvalue(),
            "GOATCOUNTER_ISOLATED=STOP CODE=SYNTHETIC_SITE_CREATE_FAILED\n",
        )
        self.assertNotIn("/tmp/", stdout.getvalue())

    def test_v2_source_has_no_retry_downloader_or_implicit_temp_cleanup(self):
        source = (
            ROOT / "scripts" / "ausmalwiese_goatcounter_isolated_probe_v2.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("TemporaryDirectory", source)
        self.assertNotIn("urlretrieve(", source)
        self.assertNotIn('subprocess.run(["curl"', source)
        self.assertNotIn('subprocess.run(["wget"', source)
        self.assertNotIn("/srv/coloring-pages-content", source)
        self.assertNotIn("/var/lib/ausmalwiese-goatcounter", source)
        self.assertNotIn("retry", source.casefold().split("No retry", 1)[-1])
        self.assertIn('tempfile.mkdtemp(prefix=base.PREFIX, dir="/tmp")', source)
        self.assertIn("shutil.rmtree(root)", source)


if __name__ == "__main__":
    unittest.main()
