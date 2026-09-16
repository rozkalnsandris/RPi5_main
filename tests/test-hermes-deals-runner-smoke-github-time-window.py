from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_runner_smoke_install_runtime import (  # noqa: E402
    RunnerSmokeInstallRuntimeError,
    _GitHubTimeWindow,
)

# Keep the capability-specific broker regression suite in the existing
# runner-smoke validation lane without widening the top-level Makefile surface.
BROKER_TEST = ROOT / "tests" / "test-hermes-deals-runner-smoke-install-broker.py"
BROKER_SPEC = importlib.util.spec_from_file_location("runner_smoke_install_broker_tests", BROKER_TEST)
assert BROKER_SPEC is not None and BROKER_SPEC.loader is not None
BROKER_MODULE = importlib.util.module_from_spec(BROKER_SPEC)
sys.modules[BROKER_SPEC.name] = BROKER_MODULE
BROKER_SPEC.loader.exec_module(BROKER_MODULE)
RunnerSmokeInstallBrokerTests = BROKER_MODULE.RunnerSmokeInstallBrokerTests


class RunnerSmokeGitHubTimeWindowTests(unittest.TestCase):
    def test_accepts_bounded_out_of_order_dates_and_returns_maximum(self):
        window = _GitHubTimeWindow()
        base = datetime(2026, 9, 16, 8, 42, 0, tzinfo=timezone.utc)

        window.observe(base + timedelta(seconds=10))
        window.observe(base + timedelta(seconds=8))
        window.observe(base + timedelta(seconds=20))

        self.assertEqual(window.first, base + timedelta(seconds=8))
        self.assertEqual(window.last, base + timedelta(seconds=20))
        self.assertEqual(window.canonical_last(), "2026-09-16T08:42:20Z")

    def test_rejects_more_than_thirty_seconds_even_when_time_regresses(self):
        window = _GitHubTimeWindow()
        base = datetime(2026, 9, 16, 8, 42, 0, tzinfo=timezone.utc)

        window.observe(base + timedelta(seconds=31))
        with self.assertRaisesRegex(
            RunnerSmokeInstallRuntimeError,
            "GitHub response time spread is too large",
        ):
            window.observe(base)

    def test_keeps_canonical_second_precision_requirement(self):
        window = _GitHubTimeWindow()
        value = datetime(2026, 9, 16, 8, 42, 0, 1, tzinfo=timezone.utc)

        with self.assertRaisesRegex(
            RunnerSmokeInstallRuntimeError,
            "GitHub response time is not canonical",
        ):
            window.observe(value)


if __name__ == "__main__":
    unittest.main()
