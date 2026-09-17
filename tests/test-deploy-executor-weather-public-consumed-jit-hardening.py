from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))


def _load_module(name: str, path: Path):
    loader = SourceFileLoader(name, str(path))
    spec = spec_from_loader(name, loader)
    if spec is None:
        raise RuntimeError(f"cannot build module spec for {path}")
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


ENTRYPOINT = _load_module(
    "weather_public_runtime_operator_entrypoint_525",
    ROOT / "ops/bin/rozkalns-weather-public-runtime-operator",
)
ENTRYPOINT._install_runtime_jit_hardening()
FIXTURE = _load_module(
    "weather_public_runtime_composite_fixture_525",
    ROOT / "tests/test-deploy-executor-weather-public-composite.py",
)

from deploy_executor.state import StateStore
from deploy_executor.transport import HTTPResponse, HTTPStatusError, NetworkFailure, RateLimitError
from deploy_executor.weather_public_runtime_operator import (
    ConcreteWeatherReplayAuthority,
    WeatherCompositeOperatorError,
)
from deploy_executor import weather_public_runtime_composite as COMPOSITE_MODULE
from deploy_executor import weather_public_runtime_operator as OPERATOR_MODULE


class PostConsumePublicFailureSender(FIXTURE.FixtureSender):
    def __init__(self, *, mode: str, failures: int):
        super().__init__()
        self.mode = mode
        self.failures_remaining = failures
        self.failure_attempts = 0
        self.weather_branch_calls = 0

    def send(self, *, method: str, url: str, headers: object) -> HTTPResponse:
        parsed = urlsplit(url)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        weather_branch = f"/repos/{FIXTURE.SOURCE_REPOSITORY}/branches/main"
        if path == weather_branch:
            self.weather_branch_calls += 1
            if self.weather_branch_calls >= 2 and self.failures_remaining > 0:
                self.failures_remaining -= 1
                self.failure_attempts += 1
                if self.mode == "network":
                    raise NetworkFailure("fixture")
                if self.mode == "503":
                    return HTTPResponse(
                        status=503,
                        headers={"date": FIXTURE.SERVER_DATE},
                        body=b"{}",
                    )
                if self.mode == "403":
                    return HTTPResponse(
                        status=403,
                        headers={
                            "date": FIXTURE.SERVER_DATE,
                            "x-ratelimit-remaining": "0",
                        },
                        body=b"{}",
                    )
                if self.mode == "403_forbidden":
                    return HTTPResponse(
                        status=403,
                        headers={"date": FIXTURE.SERVER_DATE},
                        body=b"{}",
                    )
                if self.mode == "429":
                    return HTTPResponse(
                        status=429,
                        headers={"date": FIXTURE.SERVER_DATE},
                        body=b"{}",
                    )
                if self.mode in {"missing_date", "invalid_date"}:
                    response = super().send(method=method, url=url, headers=headers)
                    response_headers = dict(response.headers)
                    if self.mode == "missing_date":
                        response_headers.pop("date", None)
                    else:
                        response_headers["date"] = "not-a-github-http-date"
                    return HTTPResponse(
                        status=response.status,
                        headers=response_headers,
                        body=response.body,
                    )
                raise AssertionError(self.mode)
        return super().send(method=method, url=url, headers=headers)


class SequencedDateSender(FIXTURE.FixtureSender):
    def __init__(self):
        super().__init__()
        self.date_headers: list[str] = []
        self.repeat_last: str | None = None

    def set_dates(self, *values: str) -> None:
        self.date_headers = list(values)
        self.repeat_last = values[-1] if values else None

    def send(self, *, method: str, url: str, headers: object) -> HTTPResponse:
        response = super().send(method=method, url=url, headers=headers)
        if self.date_headers:
            observed = self.date_headers.pop(0)
            self.repeat_last = observed
        elif self.repeat_last is not None:
            observed = self.repeat_last
        else:
            return response
        response_headers = dict(response.headers)
        response_headers["date"] = observed
        return HTTPResponse(
            status=response.status,
            headers=response_headers,
            body=response.body,
        )


class WeatherConsumedJITHardeningTests(unittest.TestCase):
    def setUp(self):
        FIXTURE.SERVER_DATE = "Thu, 10 Sep 2026 04:01:00 GMT"
        ENTRYPOINT._LAST_CONSUMED_JIT_FAILURE_CODE = None

    def _accepted_then_consumed(self, *, sender=None):
        replay = FIXTURE.ReplayAvailability()
        target, sender, replay = FIXTURE.revalidator(sender=sender, replay=replay)
        initial = target.revalidate_composite(FIXTURE.AUTH_ISSUE_NUMBER)
        replay.available = False
        replay.consumed = True
        return target, sender, replay, initial

    def test_preconsume_ttl_remains_strict(self):
        target, _sender, _replay = FIXTURE.revalidator()
        FIXTURE.SERVER_DATE = "Thu, 10 Sep 2026 04:10:01 GMT"
        with self.assertRaisesRegex(
            FIXTURE.WeatherCompositeAuthorityError,
            "AUTH_EXPIRED|canonical Weather Composite revalidation failed closed",
        ):
            target.revalidate_composite(FIXTURE.AUTH_ISSUE_NUMBER)

    def test_preconsume_time_window_still_rejects_regression(self):
        window = COMPOSITE_MODULE._GitHubTimeWindow()
        window.observe(datetime(2026, 9, 10, 4, 1, 0, tzinfo=timezone.utc))
        with self.assertRaisesRegex(
            FIXTURE.WeatherCompositeAuthorityError,
            "regressed during Weather revalidation",
        ):
            window.observe(datetime(2026, 9, 10, 4, 0, 59, tzinfo=timezone.utc))

    def test_preconsume_time_window_still_rejects_spread_over_30_seconds(self):
        window = COMPOSITE_MODULE._GitHubTimeWindow()
        window.observe(datetime(2026, 9, 10, 4, 1, 0, tzinfo=timezone.utc))
        with self.assertRaisesRegex(
            FIXTURE.WeatherCompositeAuthorityError,
            "inconsistent during Weather revalidation",
        ):
            window.observe(datetime(2026, 9, 10, 4, 1, 31, tzinfo=timezone.utc))

    def test_consumed_authority_survives_admission_ttl(self):
        target, _sender, _replay, initial = self._accepted_then_consumed()
        FIXTURE.SERVER_DATE = "Thu, 10 Sep 2026 04:11:01 GMT"
        current = target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
        self.assertEqual(current.request_id, initial.request_id)
        self.assertEqual(
            current.authorization_payload_sha256,
            initial.authorization_payload_sha256,
        )
        self.assertEqual(current.queue_contract_sha256, initial.queue_contract_sha256)
        self.assertTrue(current.authorization_replay_consumed)
        self.assertFalse(current.authorization_replay_available)

    def test_consumed_time_window_tolerates_regression_and_long_span(self):
        sender = SequencedDateSender()
        target, _sender, _replay, initial = self._accepted_then_consumed(sender=sender)
        sender.set_dates(
            "Thu, 10 Sep 2026 04:02:00 GMT",
            "Thu, 10 Sep 2026 04:01:59 GMT",
            "Thu, 10 Sep 2026 04:02:45 GMT",
            "Thu, 10 Sep 2026 04:02:10 GMT",
        )
        current = target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
        self.assertEqual(current.request_id, initial.request_id)
        self.assertEqual(current.github_server_time, "2026-09-10T04:02:45Z")
        self.assertIsNone(ENTRYPOINT._LAST_CONSUMED_JIT_FAILURE_CODE)

    def test_consumed_jit_does_not_reopen_public_source_time_surface(self):
        sender = PostConsumePublicFailureSender(mode="missing_date", failures=1)
        target, _sender, _replay, initial = self._accepted_then_consumed(sender=sender)
        initial_public_calls = len(sender.public_authorization_headers)

        current = target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)

        self.assertEqual(current.request_id, initial.request_id)
        self.assertEqual(sender.failure_attempts, 0)
        self.assertEqual(len(sender.public_authorization_headers), initial_public_calls)
        self.assertIsNone(ENTRYPOINT._LAST_CONSUMED_JIT_FAILURE_CODE)

    def test_consumed_jit_freezes_public_evidence_and_refreshes_mutable_control_plane(self):
        target, sender, replay, initial = self._accepted_then_consumed()
        initial_public_calls = len(sender.public_authorization_headers)
        initial_action_calls = sum("/actions/" in path for path in sender.calls)
        initial_auth_reads = sender.auth_reads
        initial_queue_reads = sender.queue_reads
        initial_replay_calls = len(replay.calls)
        iterations = len(FIXTURE.COMPOSITE_GATE_ORDER) + 1

        for _ in range(iterations):
            current = target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
            self.assertEqual(current.weather_ci_run_id, initial.weather_ci_run_id)
            self.assertEqual(current.rpi5_main_ci_run_id, initial.rpi5_main_ci_run_id)

        final_public_calls = len(sender.public_authorization_headers)
        final_action_calls = sum("/actions/" in path for path in sender.calls)
        self.assertEqual(final_action_calls, initial_action_calls)
        self.assertEqual(final_public_calls, initial_public_calls)
        self.assertEqual(sender.auth_reads, initial_auth_reads + (2 * iterations))
        self.assertEqual(sender.queue_reads, initial_queue_reads + (2 * iterations))
        self.assertEqual(len(replay.calls), initial_replay_calls + (2 * iterations))
        self.assertTrue(sender.public_authorization_headers)
        self.assertFalse(any(sender.public_authorization_headers))

    def test_consumed_jit_does_not_requery_current_main_after_consume(self):
        target, sender, _replay, initial = self._accepted_then_consumed()
        initial_public_calls = len(sender.public_authorization_headers)
        sender.rpi5_exact_main = False

        current = target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)

        self.assertEqual(current.rpi5_main_sha, initial.rpi5_main_sha)
        self.assertEqual(current.rpi5_main_ci_run_id, initial.rpi5_main_ci_run_id)
        self.assertEqual(len(sender.public_authorization_headers), initial_public_calls)
        self.assertIsNone(ENTRYPOINT._LAST_CONSUMED_JIT_FAILURE_CODE)

    def test_consumed_jit_still_detects_ready_queue_drift(self):
        target, sender, _replay, _initial = self._accepted_then_consumed()
        sender.final_queue_state = "closed"
        with self.assertRaises(FIXTURE.WeatherCompositeAuthorityError):
            target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)

    def test_consumed_jit_still_detects_replay_drift(self):
        target, _sender, replay, _initial = self._accepted_then_consumed()
        replay.consumed = False
        with self.assertRaisesRegex(
            FIXTURE.WeatherCompositeAuthorityError,
            "durably consumed|canonical Weather Composite revalidation failed closed",
        ):
            target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)

    def test_real_sqlite_replay_crosses_first_consumed_jit_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite3"
            with StateStore(db, bootstrap=True):
                pass
            db.chmod(0o600)
            with (
                mock.patch.object(OPERATOR_MODULE, "STATE_DB_PATH", db),
                mock.patch.object(OPERATOR_MODULE, "ROOT_UID", os.getuid()),
                mock.patch.object(OPERATOR_MODULE, "ROOT_GID", os.getgid()),
            ):
                replay = ConcreteWeatherReplayAuthority()
                target, _sender, _replay = FIXTURE.revalidator(replay=replay)
                initial = target.revalidate_composite(FIXTURE.AUTH_ISSUE_NUMBER)
                receipt = replay.consume(initial.request_id)
                self.assertTrue(receipt.durable_replay_consumed)
                current = target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
                self.assertEqual(current.request_id, initial.request_id)
                self.assertTrue(current.authorization_replay_consumed)
                self.assertFalse(current.authorization_replay_available)

    @staticmethod
    def _fresh_public_client(sender):
        sender.weather_branch_calls = 1
        return COMPOSITE_MODULE.FixedPublicGitHubReadClient(sender=sender)

    def test_public_source_network_failure_recovers_inside_fixed_budget(self):
        sender = PostConsumePublicFailureSender(mode="network", failures=1)
        client = self._fresh_public_client(sender)
        weather_branch = f"/repos/{FIXTURE.SOURCE_REPOSITORY}/branches/main"
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None) as sleeper:
            response = client._fresh_get_with_retry(weather_branch)
        self.assertEqual(response.value["commit"]["sha"], FIXTURE.WEATHER_MAIN_SHA)
        self.assertEqual(sender.failure_attempts, 1)
        sleeper.assert_called_once_with(1.0)

    def test_repeated_public_source_network_failure_stops_inside_fixed_budget(self):
        sender = PostConsumePublicFailureSender(mode="network", failures=3)
        client = self._fresh_public_client(sender)
        weather_branch = f"/repos/{FIXTURE.SOURCE_REPOSITORY}/branches/main"
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None) as sleeper:
            with self.assertRaises(NetworkFailure):
                client._fresh_get_with_retry(weather_branch)
        self.assertEqual(sender.failure_attempts, 3)
        self.assertEqual(sleeper.call_args_list, [mock.call(1.0), mock.call(2.0)])

    def test_repeated_public_source_503_stops_inside_fixed_budget(self):
        sender = PostConsumePublicFailureSender(mode="503", failures=3)
        client = self._fresh_public_client(sender)
        weather_branch = f"/repos/{FIXTURE.SOURCE_REPOSITORY}/branches/main"
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None) as sleeper:
            with self.assertRaises(HTTPStatusError) as caught:
                client._fresh_get_with_retry(weather_branch)
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(sender.failure_attempts, 3)
        self.assertEqual(sleeper.call_args_list, [mock.call(1.0), mock.call(2.0)])

    def test_public_source_403_rate_limit_is_never_retried(self):
        sender = PostConsumePublicFailureSender(mode="403", failures=3)
        client = self._fresh_public_client(sender)
        weather_branch = f"/repos/{FIXTURE.SOURCE_REPOSITORY}/branches/main"
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None) as sleeper:
            with self.assertRaises(RateLimitError) as caught:
                client._fresh_get_with_retry(weather_branch)
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(sender.failure_attempts, 1)
        sleeper.assert_not_called()
        self.assertEqual(
            ENTRYPOINT._classify_consumed_jit_failure(caught.exception),
            "public_source_rate_limited",
        )

    def test_public_source_429_rate_limit_is_never_retried(self):
        sender = PostConsumePublicFailureSender(mode="429", failures=3)
        client = self._fresh_public_client(sender)
        weather_branch = f"/repos/{FIXTURE.SOURCE_REPOSITORY}/branches/main"
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None) as sleeper:
            with self.assertRaises(RateLimitError) as caught:
                client._fresh_get_with_retry(weather_branch)
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(sender.failure_attempts, 1)
        sleeper.assert_not_called()
        self.assertEqual(
            ENTRYPOINT._classify_consumed_jit_failure(caught.exception),
            "public_source_rate_limited",
        )

    def test_public_source_generic_403_is_nonretryable_not_rate_limit(self):
        sender = PostConsumePublicFailureSender(mode="403_forbidden", failures=3)
        client = self._fresh_public_client(sender)
        weather_branch = f"/repos/{FIXTURE.SOURCE_REPOSITORY}/branches/main"
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None) as sleeper:
            with self.assertRaises(HTTPStatusError) as caught:
                client._fresh_get_with_retry(weather_branch)
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(sender.failure_attempts, 1)
        sleeper.assert_not_called()
        self.assertEqual(
            ENTRYPOINT._classify_consumed_jit_failure(caught.exception),
            "public_source_http_nonretryable",
        )

    def test_failure_classifier_is_bounded_and_public_safe(self):
        cases = {
            RateLimitError(403, 0): "public_source_rate_limited",
            RateLimitError(429, 0): "public_source_rate_limited",
            HTTPStatusError(403): "public_source_http_nonretryable",
            HTTPStatusError(503): "public_source_transient_http",
            HTTPStatusError(404): "public_source_http_nonretryable",
            RuntimeError("GitHub response time is unavailable"): "github_time_unavailable_or_invalid",
            RuntimeError("public GitHub source response omitted Date header"): "github_time_unavailable_or_invalid",
            RuntimeError("GitHub response time is not canonical to whole seconds"): "github_time_noncanonical",
            RuntimeError("GitHub response time regressed during Weather revalidation"): "github_time_regressed",
            RuntimeError("GitHub response times are inconsistent during Weather revalidation"): "github_time_spread_exceeded",
            RuntimeError("Weather authorization is not durably consumed by this request"): "replay_state",
            RuntimeError("Weather initial bootstrap baseline drifted before first deployment apply"): "baseline_drift",
            RuntimeError("Weather source repository numeric identity drifted"): "authority_or_source_drift",
            RuntimeError("unexpected internal fixture detail"): "canonical_revalidation",
        }
        for exc, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(ENTRYPOINT._classify_consumed_jit_failure(exc), expected)

    def test_fail_receipt_carries_only_bounded_reason_code(self):
        class FailingOperator:
            def execute(self, issue_number):
                self.assert_issue = issue_number
                ENTRYPOINT._set_consumed_jit_failure("public_source_network")
                raise WeatherCompositeOperatorError(
                    "trusted_checkout_fetch",
                    authorization_reuse_forbidden=True,
                    host_mutation_started=False,
                    production_mutation_started=False,
                )

        with (
            mock.patch.object(
                ENTRYPOINT,
                "PACKAGE_INIT",
                ROOT / "ops/lib/deploy_executor/__init__.py",
            ),
            mock.patch.object(
                OPERATOR_MODULE,
                "build_runtime_operator",
                return_value=FailingOperator(),
            ),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                rc = ENTRYPOINT.main(["--issue-number", "24"])
        self.assertEqual(rc, 78)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["safe_stage"], "trusted_checkout_fetch")
        self.assertTrue(payload["authorization_reuse_forbidden"])
        self.assertEqual(payload["failure_reason_code"], "public_source_network")
        self.assertNotIn("url", payload)
        self.assertNotIn("path", payload)
        self.assertNotIn("token", payload)


if __name__ == "__main__":
    unittest.main()