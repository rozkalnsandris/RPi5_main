"""Disconnected tests for the canonical GoatCounter isolated proof v2.

No GoatCounter binary, network, RPi5 runtime, production database, credential,
service, Cloudflare route or protected runtime state is touched.
"""
import contextlib
import io
import os
import sqlite3
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
        fixture_only_value = "fixture-only-value-123"
        cases = (
            (("db", "newdb", "-db=synthetic"), "SYNTHETIC_DB_CREATE_FAILED"),
            (
                (
                    "db",
                    "create",
                    "site",
                    "-vhost=stats.example.test",
                    "-synthetic-value=" + fixture_only_value,
                ),
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
                self.assertNotIn(fixture_only_value, str(raised.exception))
                self.assertNotIn(fixture_only_value, stdout.getvalue())
                self.assertNotIn(fixture_only_value, stderr.getvalue())
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

    def test_server_exit_classes_are_stable_and_zero_only_passes(self):
        cases = (
            (0, None),
            (-runtime.signal.SIGINT, "SERVER_TERMINATED_BY_SIGINT"),
            (1, "SERVER_GOATCOUNTER_COMMAND_ERROR"),
            (2, "SERVER_GO_RUNTIME_FAILURE"),
            (66, "SERVER_ZHTTP_SERVE_ERROR"),
            (99, "SERVER_FORCE_KILL_EXIT"),
            (-runtime.signal.SIGTERM, "SERVER_TERMINATED_BY_OTHER_SIGNAL"),
            (7, "SERVER_OTHER_NONZERO_EXIT"),
        )
        for exit_code, expected in cases:
            with self.subTest(exit_code=exit_code):
                self.assertEqual(
                    runtime._server_exit_failure_code(exit_code),
                    expected,
                )

    def test_shutdown_sends_one_sigint_and_never_emits_raw_exit_code(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.wait.return_value = -runtime.signal.SIGINT

        with self.assertRaises(runtime.base.RuntimeStop) as raised:
            runtime._stop_server_classified(proc)

        self.assertEqual(str(raised.exception), "SERVER_TERMINATED_BY_SIGINT")
        proc.send_signal.assert_called_once_with(runtime.signal.SIGINT)
        proc.wait.assert_called_once_with(timeout=12)
        proc.kill.assert_not_called()
        self.assertNotIn(str(-runtime.signal.SIGINT), str(raised.exception))

    def test_shutdown_timeout_preserves_existing_bounded_codes(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = (
            runtime.subprocess.TimeoutExpired(cmd="goatcounter", timeout=12),
            0,
        )

        with self.assertRaises(runtime.base.RuntimeStop) as raised:
            runtime._stop_server_classified(proc)

        self.assertEqual(str(raised.exception), "SERVER_SHUTDOWN_TIMEOUT")
        proc.send_signal.assert_called_once_with(runtime.signal.SIGINT)
        proc.kill.assert_called_once_with()
        self.assertEqual(proc.wait.call_count, 2)

    def test_shutdown_stuck_preserves_existing_stable_code(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = (
            runtime.subprocess.TimeoutExpired(cmd="goatcounter", timeout=12),
            runtime.subprocess.TimeoutExpired(cmd="goatcounter", timeout=5),
        )

        with self.assertRaises(runtime.base.RuntimeStop) as raised:
            runtime._stop_server_classified(proc)

        self.assertEqual(str(raised.exception), "SERVER_PROCESS_STUCK")
        proc.send_signal.assert_called_once_with(runtime.signal.SIGINT)
        proc.kill.assert_called_once_with()
        self.assertEqual(proc.wait.call_count, 2)

    def test_api_token_uses_numeric_synthetic_user_selector(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as parent:
            db = Path(parent) / "synthetic.sqlite3"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE users (user_id integer, email text)")
                con.execute(
                    "INSERT INTO users VALUES(?, ?)",
                    (17, runtime.base.EMAIL),
                )

            with mock.patch.object(runtime, "_run_stage") as run_stage:
                runtime._create_count_token(
                    Path("/synthetic/bin"),
                    Path(parent),
                    {"PATH": "/usr/bin:/bin"},
                    db,
                    "sqlite+" + str(db),
                )

            run_stage.assert_called_once()
            argv = run_stage.call_args.args[3:]
            self.assertIn("-user=17", argv)
            self.assertNotIn("-user=" + runtime.base.EMAIL, argv)
            self.assertEqual(argv[:3], ("db", "create", "apitoken"))
            self.assertIn("-name=synthetic-count-only", argv)
            self.assertIn("-perm=count", argv)

    def test_api_token_selector_fails_closed_without_one_synthetic_user(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as parent:
            db = Path(parent) / "synthetic.sqlite3"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE users (user_id integer, email text)")
                con.execute(
                    "INSERT INTO users VALUES(?, ?)",
                    (17, "other@example.com"),
                )

            with mock.patch.object(runtime, "_run_stage") as run_stage:
                with self.assertRaises(runtime.base.RuntimeStop) as raised:
                    runtime._create_count_token(
                        Path("/synthetic/bin"),
                        Path(parent),
                        {"PATH": "/usr/bin:/bin"},
                        db,
                        "sqlite+" + str(db),
                    )

            self.assertEqual(str(raised.exception), "SYNTHETIC_DATABASE_SETUP")
            run_stage.assert_not_called()

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
        cases = (
            "SYNTHETIC_SITE_CREATE_FAILED",
            "SERVER_TERMINATED_BY_SIGINT",
            "SERVER_GOATCOUNTER_COMMAND_ERROR",
            "SERVER_GO_RUNTIME_FAILURE",
            "SERVER_ZHTTP_SERVE_ERROR",
            "SERVER_FORCE_KILL_EXIT",
            "SERVER_TERMINATED_BY_OTHER_SIGNAL",
            "SERVER_OTHER_NONZERO_EXIT",
        )
        for code in cases:
            with self.subTest(code=code):
                stdout = io.StringIO()
                with mock.patch.object(
                    sys,
                    "argv",
                    ["probe-v2", "--release-archive", "/tmp/synthetic-release.gz"],
                ), mock.patch.object(
                    runtime,
                    "run_isolated",
                    side_effect=runtime.base.RuntimeStop(code),
                ), contextlib.redirect_stdout(stdout):
                    rc = runtime.main()

                self.assertEqual(rc, 2)
                self.assertEqual(
                    stdout.getvalue(),
                    "GOATCOUNTER_ISOLATED=STOP CODE=" + code + "\n",
                )
                self.assertNotIn("/tmp/", stdout.getvalue())
                self.assertNotIn("returncode", stdout.getvalue().casefold())

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
        self.assertNotIn("for attempt in", source)
        self.assertNotIn("while attempt", source)
        self.assertIn('tempfile.mkdtemp(prefix=base.PREFIX, dir="/tmp")', source)
        self.assertIn("shutil.rmtree(root)", source)


if __name__ == "__main__":
    unittest.main()
