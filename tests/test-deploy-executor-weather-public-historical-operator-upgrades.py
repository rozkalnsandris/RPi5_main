from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEGACY_HISTORICAL_SHA = "c99f6b9df47603703f7d1e67ddc7d88c77ed726a"
V5_HISTORICAL_SHA = "14501ddbe2853d8072464291b338c29a029dd3cf"
LEGACY_FROZEN_PATHS = (
    "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v3",
    "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v3-trusted-checkout-bootstrap.json",
    "ops/deploy/weather-public-runtime-operator-upgrade-v3.json",
    "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v3.py",
    "tests/test-deploy-executor-weather-public-operator-upgrade-v3.py",
    "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v4",
    "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v4-trusted-checkout-bootstrap.json",
    "ops/deploy/weather-public-runtime-operator-upgrade-v4.json",
    "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v4.py",
    "tests/test-deploy-executor-weather-public-operator-upgrade-v4.py",
)
V5_FROZEN_PATHS = (
    "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v5",
    "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v5-trusted-checkout-bootstrap.json",
    "ops/deploy/weather-public-runtime-operator-upgrade-v5.json",
    "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v5.py",
)
LEGACY_HISTORICAL_TESTS = (
    "tests/test-deploy-executor-weather-public-operator-upgrade-v3.py",
    "tests/test-deploy-executor-weather-public-operator-upgrade-v4.py",
)
CURRENT_TESTS = (
    "tests/test-deploy-executor-weather-public-operator-upgrade-v6.py",
)


def git_bytes(*args: str) -> bytes:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(ROOT), *args],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


class HistoricalWeatherOperatorUpgradeTests(unittest.TestCase):
    def test_v3_v4_sources_remain_exact_historical_evidence(self) -> None:
        for path in LEGACY_FROZEN_PATHS:
            with self.subTest(path=path):
                current = git_bytes("show", f"HEAD:{path}")
                historical = git_bytes("show", f"{LEGACY_HISTORICAL_SHA}:{path}")
                self.assertEqual(current, historical)

    def test_v5_sources_remain_exact_historical_evidence(self) -> None:
        for path in V5_FROZEN_PATHS:
            with self.subTest(path=path):
                current = git_bytes("show", f"HEAD:{path}")
                historical = git_bytes("show", f"{V5_HISTORICAL_SHA}:{path}")
                self.assertEqual(current, historical)

    def test_v3_v4_positive_suites_run_at_reviewed_historical_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "reviewed"
            subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(ROOT),
                    "worktree",
                    "add",
                    "--detach",
                    str(checkout),
                    LEGACY_HISTORICAL_SHA,
                ],
                check=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                env = dict(os.environ)
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                for relative in LEGACY_HISTORICAL_TESTS:
                    with self.subTest(test=relative):
                        subprocess.run(
                            [sys.executable, str(checkout / relative)],
                            cwd=checkout,
                            env=env,
                            check=True,
                        )
            finally:
                subprocess.run(
                    [
                        "/usr/bin/git",
                        "-C",
                        str(ROOT),
                        "worktree",
                        "remove",
                        "--force",
                        str(checkout),
                    ],
                    check=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

    def test_current_v6_positive_suite_runs(self) -> None:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for relative in CURRENT_TESTS:
            with self.subTest(test=relative):
                subprocess.run(
                    [sys.executable, str(ROOT / relative)],
                    cwd=ROOT,
                    env=env,
                    check=True,
                )


if __name__ == "__main__":
    unittest.main()
