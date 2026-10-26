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

    def test_privacy_gate_surfaces_only_operator_safe_codes(self):
        root = Path("/tmp/goatcounter-offline-synthetic")
        for code in (
            "SESSION_STORE_SHAPE",
            "NO_DAILY_STATS",
            "FORBIDDEN_ROWS_BOTS",
        ):
            with self.subTest(code=code), mock.patch.object(
                runtime.base,
                "inspect_fixture",
                side_effect=runtime.base.ProbeStop(code),
            ) as inspect_fixture:
                with self.assertRaises(runtime.base.RuntimeStop) as raised:
                    runtime._inspect_fixture_or_raise(root)

                self.assertEqual(str(raised.exception), code)
                inspect_fixture.assert_called_once_with(
                    root,
                    page_id=runtime.base.PAGE_ID,
                    expected_views=runtime.base.VIEWS,
                )

        private = "fixture-only-private-row-value"
        with mock.patch.object(
            runtime.base,
            "inspect_fixture",
            side_effect=runtime.base.ProbeStop(private),
        ):
            with self.assertRaises(runtime.base.RuntimeStop) as raised:
                runtime._inspect_fixture_or_raise(root)

        self.assertEqual(
            str(raised.exception),
            "ISOLATED_SQLITE_PRIVACY_GATE",
        )
        self.assertNotIn(private, str(raised.exception))

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
            (
                (
                    "db",
                    "update",
                    "site",
                    "-find=stats.example.test",
                    "-db=synthetic",
                ),
                "SYNTHETIC_SITE_DESERIALIZATION_FAILED",
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

    def test_pre_shutdown_exit_classes_are_stable_and_never_send_sigint(self):
        cases = (
            (0, "SERVER_PRE_SHUTDOWN_CLEAN_EXIT"),
            (-runtime.signal.SIGINT, "SERVER_PRE_SHUTDOWN_SIGINT_EXIT"),
            (1, "SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR"),
            (2, "SERVER_PRE_SHUTDOWN_GO_RUNTIME_FAILURE"),
            (66, "SERVER_PRE_SHUTDOWN_ZHTTP_SERVE_ERROR"),
            (99, "SERVER_PRE_SHUTDOWN_FORCE_KILL_EXIT"),
            (-runtime.signal.SIGTERM, "SERVER_PRE_SHUTDOWN_OTHER_SIGNAL"),
            (7, "SERVER_PRE_SHUTDOWN_OTHER_NONZERO_EXIT"),
        )
        for exit_code, expected in cases:
            with self.subTest(exit_code=exit_code):
                proc = mock.Mock()
                proc.poll.return_value = exit_code

                with self.assertRaises(runtime.base.RuntimeStop) as raised:
                    runtime._stop_server_classified(proc)

                self.assertEqual(str(raised.exception), expected)
                proc.poll.assert_called_once_with()
                proc.send_signal.assert_not_called()
                proc.wait.assert_not_called()
                proc.kill.assert_not_called()

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
        proc.poll.assert_called_once_with()
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
        proc.poll.assert_called_once_with()
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
        proc.poll.assert_called_once_with()
        proc.send_signal.assert_called_once_with(runtime.signal.SIGINT)
        proc.kill.assert_called_once_with()
        self.assertEqual(proc.wait.call_count, 2)

    def test_count_failure_survives_pre_shutdown_exit_one_finalizer(self):
        primary_codes = (
            "BACKEND_NOT_ACCEPTED",
            "BACKEND_RESPONSE_UNCERTAIN",
        )
        for primary_code in primary_codes:
            with self.subTest(primary_code=primary_code):
                with tempfile.TemporaryDirectory(dir="/tmp") as parent:
                    root = Path(parent)
                    proc = mock.Mock()
                    secondary_code = (
                        "SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR"
                    )

                    with mock.patch.object(
                        runtime.base,
                        "_verified_release_archive",
                        return_value=Path("/synthetic/bin"),
                    ), mock.patch.object(
                        runtime.base, "_isolated_env", return_value={}
                    ), mock.patch.object(
                        runtime.base, "_version"
                    ), mock.patch.object(
                        runtime,
                        "_make_site_with_stage_diagnostics",
                        return_value="synthetic-token",
                    ), mock.patch.object(
                        runtime.base, "_free_loopback_port", return_value=12345
                    ), mock.patch.object(
                        runtime.subprocess, "Popen", return_value=proc
                    ), mock.patch.object(
                        runtime, "_tcp_ready_classified"
                    ), mock.patch.object(
                        runtime.base,
                        "_count_once",
                        side_effect=runtime.base.RuntimeStop(primary_code),
                    ) as count_once, mock.patch.object(
                        runtime,
                        "_stop_server_classified",
                        side_effect=runtime.base.RuntimeStop(secondary_code),
                    ) as stop_server:
                        with self.assertRaises(runtime.base.RuntimeStop) as raised:
                            runtime._run_fixture("/tmp/synthetic-release.gz", root)

                self.assertEqual(str(raised.exception), primary_code)
                self.assertEqual(
                    raised.exception.secondary_server_stop_code,
                    secondary_code,
                )
                count_once.assert_called_once()
                stop_server.assert_called_once_with(proc)

    def test_successful_counts_keep_server_stop_failure_primary(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as parent:
            root = Path(parent)
            proc = mock.Mock()
            secondary_code = "SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR"

            with mock.patch.object(
                runtime.base,
                "_verified_release_archive",
                return_value=Path("/synthetic/bin"),
            ), mock.patch.object(
                runtime.base, "_isolated_env", return_value={}
            ), mock.patch.object(
                runtime.base, "_version"
            ), mock.patch.object(
                runtime,
                "_make_site_with_stage_diagnostics",
                return_value="synthetic-token",
            ), mock.patch.object(
                runtime.base, "_free_loopback_port", return_value=12345
            ), mock.patch.object(
                runtime.subprocess, "Popen", return_value=proc
            ), mock.patch.object(
                runtime, "_tcp_ready_classified"
            ), mock.patch.object(
                runtime.base, "_count_once"
            ) as count_once, mock.patch.object(
                runtime,
                "_stop_server_classified",
                side_effect=runtime.base.RuntimeStop(secondary_code),
            ):
                with self.assertRaises(runtime.base.RuntimeStop) as raised:
                    runtime._run_fixture("/tmp/synthetic-release.gz", root)

        self.assertEqual(str(raised.exception), secondary_code)
        self.assertEqual(count_once.call_count, runtime.base.VIEWS)

    def test_secondary_server_stop_evidence_is_sanitized(self):
        known = runtime.base.RuntimeStop(
            "SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR"
        )
        unknown = runtime.base.RuntimeStop("fixture-only-raw-detail")

        self.assertEqual(
            runtime._secondary_server_stop_code(known),
            "SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR",
        )
        self.assertEqual(
            runtime._secondary_server_stop_code(unknown),
            "SERVER_STOP_SECONDARY_ERROR",
        )
        self.assertEqual(
            runtime._secondary_server_stop_code(
                ValueError("fixture-only-raw-detail")
            ),
            "SERVER_STOP_SECONDARY_ERROR",
        )

    def test_aggregate_only_replaces_default_collection_bits(self):
        settings = {
            "collect": 190,
            "ignore_ips": "192.0.2.1",
            "other": "preserved",
        }

        runtime._enforce_aggregate_only(settings)

        self.assertEqual(settings["collect"], 1)
        self.assertEqual(settings["ignore_ips"], "")
        self.assertNotIsInstance(settings["ignore_ips"], list)
        self.assertEqual(settings["other"], "preserved")

    def test_aggregate_only_disables_collecthits(self):
        settings = {"collect": 257, "ignore_ips": ""}

        runtime._enforce_aggregate_only(settings)

        self.assertEqual(settings["collect"], 1)
        self.assertFalse(settings["collect"] & 256)
        self.assertEqual(settings["ignore_ips"], "")

    def test_synthetic_settings_serialize_collectnothing_and_text_ignore_ips(self):
        settings = {
            "collect": 190,
            "ignore_ips": "192.0.2.1",
            "allow_counter": True,
        }

        runtime._enforce_aggregate_only(settings)
        encoded = runtime.json.dumps(settings, separators=(",", ":"))
        decoded = runtime.json.loads(encoded)

        self.assertIsInstance(decoded["collect"], int)
        self.assertEqual(decoded["collect"], 1)
        self.assertIsInstance(decoded["ignore_ips"], str)
        self.assertEqual(decoded["ignore_ips"], "")
        self.assertNotIn('"ignore_ips":[]', encoded)

    def test_aggregate_only_rejects_malformed_bitmasks_without_mutation(self):
        malformed = (None, True, 1.5, "190", -1, 65536)
        for value in malformed:
            with self.subTest(value=value):
                settings = {
                    "collect": value,
                    "ignore_ips": "fixture-only-ip",
                }
                before = dict(settings)

                with self.assertRaises(runtime.base.RuntimeStop) as raised:
                    runtime._enforce_aggregate_only(settings)

                self.assertEqual(
                    str(raised.exception),
                    "SYNTHETIC_SETTINGS_INVALID",
                )
                self.assertEqual(settings, before)
                self.assertNotIn("fixture-only-ip", str(raised.exception))

    def test_server_launch_uses_one_automigrate_and_one_popen(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as parent:
            root = Path(parent)
            proc = mock.Mock()

            with mock.patch.object(
                runtime.base,
                "_verified_release_archive",
                return_value=Path("/synthetic/bin"),
            ), mock.patch.object(
                runtime.base, "_isolated_env", return_value={}
            ), mock.patch.object(
                runtime.base, "_version"
            ), mock.patch.object(
                runtime,
                "_make_site_with_stage_diagnostics",
                return_value="synthetic-token",
            ), mock.patch.object(
                runtime.base, "_free_loopback_port", return_value=12345
            ), mock.patch.object(
                runtime.subprocess, "Popen", return_value=proc
            ) as popen, mock.patch.object(
                runtime, "_tcp_ready_classified"
            ), mock.patch.object(
                runtime.base,
                "_count_once",
                side_effect=runtime.base.RuntimeStop("BACKEND_NOT_ACCEPTED"),
            ), mock.patch.object(
                runtime, "_stop_server_classified"
            ):
                with self.assertRaises(runtime.base.RuntimeStop):
                    runtime._run_fixture("/tmp/synthetic-release.gz", root)

        popen.assert_called_once()
        argv = popen.call_args.args[0]
        self.assertEqual(argv.count("-automigrate"), 1)
        self.assertEqual(argv[1], "serve")
        self.assertIn("-tls=http", argv)
        self.assertIn("-store-every=1", argv)

    def test_site_deserialization_uses_exact_silent_noop_update_argv(self):
        with mock.patch.object(runtime, "_run_stage") as run_stage:
            runtime._verify_site_deserialization(
                Path("/synthetic/bin"),
                Path("/tmp/synthetic"),
                {"PATH": "/usr/bin:/bin"},
                "sqlite+/tmp/synthetic/db.sqlite3",
            )

        run_stage.assert_called_once_with(
            Path("/synthetic/bin"),
            Path("/tmp/synthetic"),
            {"PATH": "/usr/bin:/bin"},
            "db",
            "update",
            "site",
            "-find=" + runtime.base.HOST,
            "-db=sqlite+/tmp/synthetic/db.sqlite3",
        )
        argv = run_stage.call_args.args[3:]
        self.assertFalse(any(arg.startswith("-format") for arg in argv))
        self.assertFalse(any(arg.startswith("-vhost") for arg in argv))
        self.assertFalse(any(arg.startswith("-link") for arg in argv))

    def test_site_deserialization_runs_once_after_settings_commit(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as parent:
            root = Path(parent)
            db = root / "synthetic.sqlite3"
            with sqlite3.connect(db) as con:
                con.execute(
                    "CREATE TABLE sites (site_id integer, settings text)"
                )
                con.execute(
                    "CREATE TABLE api_tokens (token text)"
                )
                con.execute(
                    "INSERT INTO sites VALUES (?, ?)",
                    (
                        1,
                        '{"collect":1,"ignore_ips":"fixture-only-ip"}',
                    ),
                )
                con.execute(
                    "INSERT INTO api_tokens VALUES (?)",
                    ("synthetic-token-1234567890",),
                )

            def verify_deserialization(binary, verify_root, env, db_arg):
                self.assertEqual(binary, Path("/synthetic/bin"))
                self.assertEqual(verify_root, root)
                self.assertEqual(env, {"PATH": "/usr/bin:/bin"})
                self.assertEqual(db_arg, "sqlite+" + str(db))
                with sqlite3.connect(db) as con:
                    stored = con.execute(
                        "SELECT settings FROM sites WHERE site_id=1"
                    ).fetchone()[0]
                settings = runtime.json.loads(stored)
                self.assertEqual(settings["collect"], 1)
                self.assertEqual(settings["ignore_ips"], "")
                self.assertNotIsInstance(settings["ignore_ips"], list)

            with mock.patch.object(
                runtime, "_run_stage"
            ), mock.patch.object(
                runtime, "_create_count_token"
            ), mock.patch.object(
                runtime,
                "_verify_site_deserialization",
                side_effect=verify_deserialization,
            ) as deserialization:
                token = runtime._make_site_with_stage_diagnostics(
                    Path("/synthetic/bin"),
                    root,
                    {"PATH": "/usr/bin:/bin"},
                    db,
                )

            self.assertEqual(token, "synthetic-token-1234567890")
            deserialization.assert_called_once()

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

    def test_startup_exit_classes_are_fixed_and_sanitized(self):
        cases = (
            (
                1,
                (
                    b"goatcounter: zhttp.Serve: listen tcp "
                    b"127.0.0.1:54321: bind: address already in use\n"
                ),
                "SERVER_STARTUP_BIND_ADDRESS_IN_USE",
            ),
            (
                1,
                (
                    b"goatcounter: zhttp.Serve: listen tcp "
                    b"127.0.0.1:54321: bind: permission denied\n"
                ),
                "SERVER_STARTUP_BIND_PERMISSION_DENIED",
            ),
            (
                1,
                b"goatcounter: zdb.Connect: sqlite database at /tmp/private.sqlite does not exist\n",
                "SERVER_STARTUP_DATABASE_ERROR",
            ),
            (
                1,
                b"goatcounter: Sites.List: no such table: sites\n",
                "SERVER_STARTUP_SITE_LIST_ERROR",
            ),
            (
                1,
                b"goatcounter: template: dashboard: parse failure\n",
                "SERVER_STARTUP_TEMPLATE_ERROR",
            ),
            (
                1,
                b"goatcounter: zhttp.Serve: listen tcp: invalid argument\n",
                "SERVER_STARTUP_ZHTTP_SETUP_ERROR",
            ),
            (0, b"", "SERVER_STARTUP_CLEAN_EXIT"),
            (1, b"other startup error", "SERVER_STARTUP_GOATCOUNTER_COMMAND_ERROR"),
            (2, b"", "SERVER_STARTUP_GO_RUNTIME_FAILURE"),
            (66, b"", "SERVER_STARTUP_ZHTTP_SERVE_ERROR"),
            (99, b"", "SERVER_STARTUP_FORCE_KILL_EXIT"),
            (-runtime.signal.SIGTERM, b"", "SERVER_STARTUP_SIGNAL_EXIT"),
            (7, b"", "SERVER_STARTUP_OTHER_NONZERO_EXIT"),
        )
        for exit_code, stderr_prefix, expected in cases:
            with self.subTest(exit_code=exit_code, expected=expected):
                code = runtime._startup_exit_failure_code(
                    exit_code,
                    stderr_prefix + b" token=fixture-only-secret",
                )
                self.assertEqual(code, expected)
                self.assertNotIn("54321", code)
                self.assertNotIn("fixture-only-secret", code)
                self.assertNotIn("address already in use", code.casefold())
                self.assertNotIn("permission denied", code.casefold())
                self.assertNotIn("/tmp/private.sqlite", code)
                self.assertNotIn("no such table", code.casefold())
                self.assertNotIn("parse failure", code.casefold())

    def test_startup_bind_classification_has_priority_over_other_markers(self):
        code = runtime._startup_exit_failure_code(
            1,
            (
                b"goatcounter: zhttp.Serve: listen tcp 127.0.0.1:54321: "
                b"bind: address already in use; zdb.Connect: fixture-only-detail"
            ),
        )
        self.assertEqual(code, "SERVER_STARTUP_BIND_ADDRESS_IN_USE")

    def test_startup_stderr_capture_is_bounded_and_discardable(self):
        payload = b"x" * (runtime._STARTUP_STDERR_LIMIT + 4096)
        capture = runtime._BoundedStderrCapture(io.BytesIO(payload))
        capture.wait()

        self.assertEqual(
            len(capture.snapshot()),
            runtime._STARTUP_STDERR_LIMIT,
        )
        capture.discard()
        self.assertEqual(capture.snapshot(), b"")

    def test_tcp_ready_early_exit_emits_only_sanitized_startup_code(self):
        proc = mock.Mock()
        proc.poll.return_value = 1
        proc.stderr = io.BytesIO(
            b"goatcounter: zhttp.Serve: listen tcp "
            b"127.0.0.1:54321: bind: address already in use\n"
            b"token=fixture-only-secret\n"
        )

        with self.assertRaises(runtime.base.RuntimeStop) as raised:
            runtime._tcp_ready_classified(54321, proc)

        self.assertEqual(
            str(raised.exception),
            "SERVER_STARTUP_BIND_ADDRESS_IN_USE",
        )
        self.assertNotIn("54321", str(raised.exception))
        self.assertNotIn("fixture-only-secret", str(raised.exception))
        proc.poll.assert_called_once_with()

    def test_tcp_ready_requires_diagnostic_pipe(self):
        proc = mock.Mock()
        proc.stderr = None

        with self.assertRaises(runtime.base.RuntimeStop) as raised:
            runtime._tcp_ready_classified(54321, proc)

        self.assertEqual(
            str(raised.exception),
            "SERVER_STARTUP_DIAGNOSTIC_UNAVAILABLE",
        )
        proc.poll.assert_not_called()

    def test_main_outputs_only_stable_failure_code(self):
        cases = (
            "SYNTHETIC_SITE_CREATE_FAILED",
            "SERVER_STARTUP_BIND_ADDRESS_IN_USE",
            "SERVER_STARTUP_BIND_PERMISSION_DENIED",
            "SERVER_STARTUP_DATABASE_ERROR",
            "SERVER_STARTUP_SITE_LIST_ERROR",
            "SERVER_STARTUP_TEMPLATE_ERROR",
            "SERVER_STARTUP_ZHTTP_SETUP_ERROR",
            "SERVER_STARTUP_CLEAN_EXIT",
            "SERVER_STARTUP_GOATCOUNTER_COMMAND_ERROR",
            "SERVER_STARTUP_GO_RUNTIME_FAILURE",
            "SERVER_STARTUP_ZHTTP_SERVE_ERROR",
            "SERVER_STARTUP_FORCE_KILL_EXIT",
            "SERVER_STARTUP_SIGNAL_EXIT",
            "SERVER_STARTUP_OTHER_NONZERO_EXIT",
            "SERVER_STARTUP_DIAGNOSTIC_UNAVAILABLE",
            "SERVER_PRE_SHUTDOWN_CLEAN_EXIT",
            "SERVER_PRE_SHUTDOWN_SIGINT_EXIT",
            "SERVER_PRE_SHUTDOWN_GOATCOUNTER_COMMAND_ERROR",
            "SERVER_PRE_SHUTDOWN_GO_RUNTIME_FAILURE",
            "SERVER_PRE_SHUTDOWN_ZHTTP_SERVE_ERROR",
            "SERVER_PRE_SHUTDOWN_FORCE_KILL_EXIT",
            "SERVER_PRE_SHUTDOWN_OTHER_SIGNAL",
            "SERVER_PRE_SHUTDOWN_OTHER_NONZERO_EXIT",
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
        self.assertIn("stderr=subprocess.PIPE", source)
        self.assertIn("_STARTUP_STDERR_LIMIT = 8192", source)
        self.assertIn("_startup_exit_failure_code", source)
        self.assertNotIn("stderr=subprocess.STDOUT", source)
        self.assertEqual(source.count('"-automigrate"'), 1)
        self.assertIn("_COLLECT_NOTHING = 1", source)
        self.assertIn('settings["collect"] = _COLLECT_NOTHING', source)
        self.assertIn('settings["ignore_ips"] = ""', source)
        self.assertNotIn('settings["ignore_ips"] = []', source)
        self.assertIn('"SYNTHETIC_SITE_DESERIALIZATION_FAILED"', source)
        self.assertNotIn('"-format=json"', source)
        self.assertIn("_verify_site_deserialization(binary, root, env, db_arg)", source)
        self.assertIn("privacy.operator_safe_stop_code(exc)", source)
        self.assertIn("_inspect_fixture_or_raise(root)", source)

        base_source = (
            ROOT / "scripts" / "ausmalwiese_goatcounter_isolated_probe_v1.py"
        ).read_text(encoding="utf-8")
        self.assertIn("if response.status != 202:", base_source)
        self.assertIn('"no_sessions": True', base_source)


if __name__ == "__main__":
    unittest.main()
