from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEGACY_HISTORICAL_SHA = "c99f6b9df47603703f7d1e67ddc7d88c77ed726a"
V5_HISTORICAL_SHA = "14501ddbe2853d8072464291b338c29a029dd3cf"
V6_HISTORICAL_SHA = "9136c37156e84da3918e58d5d467c8b1e5cc403a"
V7_HISTORICAL_SHA = "db7946fc64067c11d16a5b10902edf1157544db5"
V9_HISTORICAL_SHA = "84e129909831bd8111c4f4c1f6618b7fff2a803b"
V9_MODULE_PATH = "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v9.py"
V9_CONTRACT_PATH = "ops/deploy/weather-public-runtime-operator-upgrade-v9.json"
V9_CHECKOUT_CONTRACT_PATH = "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v9-trusted-checkout-bootstrap.json"
V9_BROKER_PATH = "ops/bin/rozkalns-weather-operator-v9-privileged-broker"
V9_ENTRYPOINT_PATH = "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v9"
TARGET_SOURCE_PATH = "ops/lib/deploy_executor/weather_public_runtime_operator.py"
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
V6_FROZEN_PATHS = (
    "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v6",
    "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v6-trusted-checkout-bootstrap.json",
    "ops/deploy/weather-public-runtime-operator-upgrade-v6.json",
    "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v6.py",
    "tests/test-deploy-executor-weather-public-operator-upgrade-v6.py",
)
V7_FROZEN_PATHS = (
    "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v7",
    "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v7-trusted-checkout-bootstrap.json",
    "ops/deploy/weather-public-runtime-operator-upgrade-v7.json",
    "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v7.py",
    "tests/test-deploy-executor-weather-public-operator-upgrade-v7.py",
)
V9_FROZEN_PATHS = (
    V9_ENTRYPOINT_PATH,
    V9_CHECKOUT_CONTRACT_PATH,
    V9_CONTRACT_PATH,
    V9_MODULE_PATH,
    V9_BROKER_PATH,
)
LEGACY_HISTORICAL_TESTS = (
    "tests/test-deploy-executor-weather-public-operator-upgrade-v3.py",
    "tests/test-deploy-executor-weather-public-operator-upgrade-v4.py",
)
V7_HISTORICAL_TESTS = (
    "tests/test-deploy-executor-weather-public-operator-upgrade-v7.py",
)
CURRENT_TESTS = (
    "tests/test-deploy-executor-weather-public-operator-upgrade-v8.py",
    "tests/test-weather-operator-v9-capability-refresh.py",
)


def git_bytes(*args: str) -> bytes:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(ROOT), *args],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def python_string_constant(relative: str, name: str) -> str:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if type(node.value.value) is not str:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return node.value.value
    raise AssertionError(f"missing string constant {name} in {relative}")


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def run_historical_tests(sha: str, tests: tuple[str, ...]) -> None:
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
                sha,
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            for relative in tests:
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

    def test_v6_sources_remain_exact_historical_evidence(self) -> None:
        for path in V6_FROZEN_PATHS:
            with self.subTest(path=path):
                current = git_bytes("show", f"HEAD:{path}")
                historical = git_bytes("show", f"{V6_HISTORICAL_SHA}:{path}")
                self.assertEqual(current, historical)

    def test_v7_sources_remain_exact_historical_evidence(self) -> None:
        for path in V7_FROZEN_PATHS:
            with self.subTest(path=path):
                current = git_bytes("show", f"HEAD:{path}")
                historical = git_bytes("show", f"{V7_HISTORICAL_SHA}:{path}")
                self.assertEqual(current, historical)

    def test_v9_sources_remain_exact_historical_evidence(self) -> None:
        for path in V9_FROZEN_PATHS:
            with self.subTest(path=path):
                current = git_bytes("show", f"HEAD:{path}")
                historical = git_bytes("show", f"{V9_HISTORICAL_SHA}:{path}")
                self.assertEqual(current, historical)

    def test_v3_v4_positive_suites_run_at_reviewed_historical_snapshot(self) -> None:
        run_historical_tests(LEGACY_HISTORICAL_SHA, LEGACY_HISTORICAL_TESTS)

    def test_v7_positive_suite_runs_at_reviewed_historical_snapshot(self) -> None:
        run_historical_tests(V7_HISTORICAL_SHA, V7_HISTORICAL_TESTS)

    def test_current_v8_positive_suite_runs(self) -> None:
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

    def test_v9_target_bindings_match_exact_historical_target_source_bytes(self) -> None:
        source = git_bytes("show", f"{V9_HISTORICAL_SHA}:{TARGET_SOURCE_PATH}")
        source_sha256 = hashlib.sha256(source).hexdigest()
        source_blob_sha1 = git_blob_sha1(source)
        contract = json.loads((ROOT / V9_CONTRACT_PATH).read_text(encoding="utf-8"))

        self.assertEqual(
            python_string_constant(V9_MODULE_PATH, "TARGET_NEW_SHA256"),
            source_sha256,
        )
        self.assertEqual(contract["new_sha256"], source_sha256)
        self.assertEqual(
            python_string_constant(V9_MODULE_PATH, "TARGET_NEW_BLOB"),
            source_blob_sha1,
        )
        self.assertEqual(contract["new_blob"], source_blob_sha1)

    def test_v9_broker_bindings_match_exact_upgrade_source_bytes(self) -> None:
        entrypoint_blob = git_blob_sha1((ROOT / V9_ENTRYPOINT_PATH).read_bytes())
        module_blob = git_blob_sha1((ROOT / V9_MODULE_PATH).read_bytes())
        self.assertEqual(
            python_string_constant(V9_BROKER_PATH, "UPGRADE_ENTRYPOINT_BLOB"),
            entrypoint_blob,
        )
        self.assertEqual(
            python_string_constant(V9_BROKER_PATH, "UPGRADE_MODULE_BLOB"),
            module_blob,
        )


if __name__ == "__main__":
    unittest.main()
