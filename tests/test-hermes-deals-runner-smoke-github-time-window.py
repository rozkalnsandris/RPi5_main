from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_runner_smoke_install_runtime import (  # noqa: E402
    RunnerSmokeInstallRuntimeError,
    _GitHubTimeWindow,
)


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
