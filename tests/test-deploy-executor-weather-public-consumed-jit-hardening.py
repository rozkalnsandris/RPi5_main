from __future__ import annotations

from contextlib import redirect_stdout
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
    "weather_public_runtime_operator_entrypoint_494",
    ROOT / "ops/bin/rozkalns-weather-public-runtime-operator",
)
ENTRYPOINT._install_runtime_jit_hardening()
FIXTURE = _load_module(
    "weather_public_runtime_composite_fixture_494",
    ROOT / "tests/test-deploy-executor-weather-public-composite.py",
)

from deploy_executor.state import StateStore
from deploy_executor.transport import HTTPResponse, NetworkFailure
from deploy_executor.weather_public_runtime_operator import (
    ConcreteWeatherReplayAuthority,
    WeatherCompositeOperatorError,
)
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
                        headers={"date": FIXTURE.SERVER_DATE},
                        body=b"{}",
                    )
                raise AssertionError(self.mode)
        return super().send(method=method, url=url, headers=headers)


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

    def test_consumed_jit_reuses_only_immutable_public_evidence(self):
        target, sender, _replay, initial = self._accepted_then_consumed()
        initial_public_calls = len(sender.public_authorization_headers)
        initial_action_calls = sum("/actions/" in path for path in sender.calls)
        iterations = len(FIXTURE.COMPOSITE_GATE_ORDER) + 1

        for _ in range(iterations):
            current = target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
            self.assertEqual(current.weather_ci_run_id, initial.weather_ci_run_id)
            self.assertEqual(current.rpi5_main_ci_run_id, initial.rpi5_main_ci_run_id)

        final_public_calls = len(sender.public_authorization_headers)
        final_action_calls = sum("/actions/" in path for path in sender.calls)
        self.assertEqual(final_action_calls, initial_action_calls)
        self.assertEqual(final_public_calls, initial_public_calls + (2 * iterations))
        self.assertLess(final_public_calls, 60)
        self.assertTrue(sender.public_authorization_headers)
        self.assertFalse(any(sender.public_authorization_headers))

    def test_consumed_jit_still_detects_current_main_drift(self):
        target, sender, _replay, _initial = self._accepted_then_consumed()
        sender.rpi5_exact_main = False
        with self.assertRaisesRegex(
            FIXTURE.WeatherCompositeAuthorityError,
            "exact current main|canonical Weather Composite revalidation failed closed",
        ):
            target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
        self.assertEqual(
            ENTRYPOINT._LAST_CONSUMED_JIT_FAILURE_CODE,
            "authority_or_source_drift",
        )

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

    def test_one_postconsume_network_failure_recovers_inside_fixed_budget(self):
        sender = PostConsumePublicFailureSender(mode="network", failures=1)
        target, _sender, _replay, initial = self._accepted_then_consumed(sender=sender)
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None) as sleeper:
            current = target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
        self.assertEqual(current.request_id, initial.request_id)
        self.assertEqual(sender.failure_attempts, 1)
        sleeper.assert_called_once_with(1.0)
        self.assertIsNone(ENTRYPOINT._LAST_CONSUMED_JIT_FAILURE_CODE)

    def test_repeated_postconsume_network_failure_stops_with_public_code(self):
        sender = PostConsumePublicFailureSender(mode="network", failures=3)
        target, _sender, _replay, _initial = self._accepted_then_consumed(sender=sender)
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None) as sleeper:
            with self.assertRaises(FIXTURE.WeatherCompositeAuthorityError):
                target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
        self.assertEqual(sender.failure_attempts, 3)
        self.assertEqual(sleeper.call_args_list, [mock.call(1.0), mock.call(2.0)])
        self.assertEqual(
            ENTRYPOINT._LAST_CONSUMED_JIT_FAILURE_CODE,
            "public_source_network",
        )

    def test_repeated_postconsume_503_stops_with_public_code(self):
        sender = PostConsumePublicFailureSender(mode="503", failures=3)
        target, _sender, _replay, _initial = self._accepted_then_consumed(sender=sender)
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None):
            with self.assertRaises(FIXTURE.WeatherCompositeAuthorityError):
                target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
        self.assertEqual(sender.failure_attempts, 3)
        self.assertEqual(
            ENTRYPOINT._LAST_CONSUMED_JIT_FAILURE_CODE,
            "public_source_transient_http",
        )

    def test_postconsume_403_is_never_retried(self):
        sender = PostConsumePublicFailureSender(mode="403", failures=3)
        target, _sender, _replay, _initial = self._accepted_then_consumed(sender=sender)
        with mock.patch.object(ENTRYPOINT.time, "sleep", return_value=None) as sleeper:
            with self.assertRaises(FIXTURE.WeatherCompositeAuthorityError):
                target.revalidate_consumed_composite(FIXTURE.AUTH_ISSUE_NUMBER)
        self.assertEqual(sender.failure_attempts, 1)
        sleeper.assert_not_called()
        self.assertEqual(
            ENTRYPOINT._LAST_CONSUMED_JIT_FAILURE_CODE,
            "public_source_http_nonretryable",
        )

    def test_failure_classifier_is_bounded_and_public_safe(self):
        cases = {
            RuntimeError("GitHub response time regressed during Weather revalidation"): "github_time",
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
                rc = ENTRYPOINT.main(["--issue-number", "23"])
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
