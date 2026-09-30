#!/usr/bin/env python3
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_upgrade_v9_host_capability as cap
from deploy_executor import weather_operator_upgrade_v10_dispatch_caller as caller

BROKER_PATH = ROOT / "ops/bin/rozkalns-weather-operator-v10-successor-privileged-broker"


def load_broker():
    loader = SourceFileLoader("weather_v10_successor_broker_661", str(BROKER_PATH))
    spec = spec_from_loader(loader.name, loader)
    assert spec is not None
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


class WeatherV10PostConsumeFailureCodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = load_broker()

    def assert_bounded(self, reason: str, expected_code: str, raw: str) -> None:
        self.assertEqual(caller._broker_failure_code(reason), expected_code)
        self.assertNotIn(raw, reason)

    def test_checkout_bootstrap_failure_is_bounded_after_consume(self) -> None:
        raw = "private bootstrap detail /secret/path"
        plan = SimpleNamespace()
        with (
            mock.patch.object(self.broker.cap, "_admit_and_consume", return_value=None),
            mock.patch.object(
                self.broker,
                "_bootstrap_checkout",
                side_effect=cap.WeatherV9HostCapabilityError(raw),
            ),
        ):
            with self.assertRaises(cap.WeatherV9HostCapabilityError) as raised:
                self.broker._execute_plan_v10(plan)
        self.assert_bounded(
            str(raised.exception),
            "V10_SOURCE_BLOB_DRIFT",
            raw,
        )

    def test_source_blob_read_failure_is_bounded(self) -> None:
        raw = "private git failure TOKEN=value"
        with mock.patch.object(self.broker, "_bounded_run_git", side_effect=OSError(raw)):
            with self.assertRaises(cap.WeatherV9HostCapabilityError) as raised:
                self.broker._require_source_blob(
                    Path("/home/test/RPi5_main"),
                    "a" * 40,
                    self.broker.ENTRYPOINT,
                    self.broker.UPGRADE_ENTRYPOINT_BLOB,
                )
        self.assert_bounded(
            str(raised.exception),
            "V10_SOURCE_BLOB_DRIFT",
            raw,
        )

    def test_entrypoint_lstat_failure_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan = SimpleNamespace(
                manager_checkout=Path(temp),
                trusted_checkout=Path(temp),
                authorization=SimpleNamespace(source_sha="a" * 40),
            )
            with mock.patch.object(self.broker, "_require_source_blob", return_value=None):
                with self.assertRaises(cap.WeatherV9HostCapabilityError) as raised:
                    self.broker._run_fixed_upgrade(plan)
        self.assertEqual(str(raised.exception), "fixed v10 entrypoint metadata drifted")
        self.assertEqual(
            caller._broker_failure_code(str(raised.exception)),
            "V10_ENTRYPOINT_METADATA_DRIFT",
        )

    def test_postcondition_read_failure_is_bounded(self) -> None:
        raw = "private postcondition failure /secret/path"
        plan = SimpleNamespace()
        with (
            mock.patch.object(self.broker.cap, "_admit_and_consume", return_value=None),
            mock.patch.object(self.broker, "_bootstrap_checkout", return_value=None),
            mock.patch.object(self.broker, "_run_fixed_upgrade", return_value={}),
            mock.patch.object(self.broker.cap, "_safe_file", side_effect=OSError(raw)),
        ):
            with self.assertRaises(cap.WeatherV9HostCapabilityError) as raised:
                self.broker._execute_plan_v10(plan)
        self.assert_bounded(
            str(raised.exception),
            "V10_OPERATOR_POSTCONDITION_FAILED",
            raw,
        )

    def test_unknown_reason_still_fails_closed(self) -> None:
        self.assertEqual(
            caller._broker_failure_code("arbitrary untrusted broker text"),
            caller.BROKER_FAIL_CLOSED_UNKNOWN,
        )


if __name__ == "__main__":
    unittest.main()
