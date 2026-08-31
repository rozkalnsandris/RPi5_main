from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))
BASELINE_BIN = ROOT / "ops" / "bin" / "rozkalns-deploy-p9-control-baseline"


def load_baseline_module():
    loader = importlib.machinery.SourceFileLoader(
        "p9_control_baseline_freshness_handoff", str(BASELINE_BIN)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


class P9ControlBaselineFreshnessHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_baseline_module()
        cls.observed_at = datetime(2026, 8, 31, 19, 40, 0, tzinfo=timezone.utc)

    def test_security_ttl_is_unchanged_and_handoff_margin_is_narrower(self):
        self.assertEqual(self.module.MAX_EVIDENCE_AGE_SECONDS, 300)
        self.assertEqual(
            self.module._MIN_OPERATOR_HANDOFF_FRESHNESS_SECONDS,
            180,
        )
        self.assertLess(
            self.module._MIN_OPERATOR_HANDOFF_FRESHNESS_SECONDS,
            self.module.MAX_EVIDENCE_AGE_SECONDS,
        )

    def test_handoff_metadata_uses_github_server_time(self):
        metadata = self.module._freshness_handoff(
            self.observed_at,
            server_time=self.observed_at + timedelta(seconds=60),
        )
        self.assertEqual(metadata["observed_at"], "2026-08-31T19:40:00Z")
        self.assertEqual(metadata["expires_at"], "2026-08-31T19:45:00Z")
        self.assertEqual(metadata["remaining_freshness_seconds"], 240)
        self.assertEqual(metadata["minimum_handoff_freshness_seconds"], 180)

    def test_handoff_rejects_future_stale_and_low_remaining_budget(self):
        cases = (
            (
                self.observed_at - timedelta(seconds=1),
                "stale or from the future",
            ),
            (
                self.observed_at + timedelta(seconds=121),
                "below the operator handoff minimum",
            ),
            (
                self.observed_at + timedelta(seconds=301),
                "stale or from the future",
            ),
        )
        for server_time, message in cases:
            with self.subTest(server_time=server_time):
                with self.assertRaisesRegex(
                    self.module.ControlPostCanaryCollectorError,
                    message,
                ):
                    self.module._freshness_handoff(
                        self.observed_at,
                        server_time=server_time,
                    )

    def test_main_stops_before_publisher_when_handoff_budget_is_too_low(self):
        source_client = mock.Mock()
        source_client.get_json.return_value = SimpleNamespace(
            server_time=self.observed_at + timedelta(seconds=121)
        )
        observation = SimpleNamespace(observed_at=self.observed_at)
        publisher = mock.Mock(side_effect=AssertionError("publisher must not run"))

        with mock.patch.object(self.module.os, "geteuid", return_value=0), mock.patch.object(
            self.module,
            "parse_args",
            return_value=SimpleNamespace(source_sha="f" * 40),
        ), mock.patch.object(
            self.module,
            "build_source_client",
            return_value=source_client,
        ), mock.patch.object(
            self.module,
            "collect_once",
            return_value=observation,
        ), mock.patch.object(
            self.module,
            "publish_control_postcanary_baseline_evidence",
            publisher,
        ):
            with self.assertRaisesRegex(
                self.module.ControlPostCanaryCollectorError,
                "below the operator handoff minimum",
            ):
                self.module.main()

        publisher.assert_not_called()
        source_client.get_json.assert_called_once_with(
            f"/repos/{self.module.SOURCE_REPOSITORY}"
        )

    def test_main_pass_output_exposes_exact_freshness_window(self):
        source_client = mock.Mock()
        source_client.get_json.return_value = SimpleNamespace(
            server_time=self.observed_at + timedelta(seconds=60)
        )
        observation = SimpleNamespace(observed_at=self.observed_at)

        with mock.patch.object(self.module.os, "geteuid", return_value=0), mock.patch.object(
            self.module,
            "parse_args",
            return_value=SimpleNamespace(source_sha="f" * 40),
        ), mock.patch.object(
            self.module,
            "build_source_client",
            return_value=source_client,
        ), mock.patch.object(
            self.module,
            "collect_once",
            return_value=observation,
        ), mock.patch.object(
            self.module,
            "publish_control_postcanary_baseline_evidence",
            return_value="a" * 64,
        ) as publisher:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(self.module.main(), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["P9_CONTROL_BASELINE"], "PASS")
        self.assertEqual(payload["observed_at"], "2026-08-31T19:40:00Z")
        self.assertEqual(payload["expires_at"], "2026-08-31T19:45:00Z")
        self.assertEqual(payload["remaining_freshness_seconds"], 240)
        self.assertEqual(payload["minimum_handoff_freshness_seconds"], 180)
        self.assertFalse(payload["p9_executed"])
        self.assertFalse(payload["state_store_touched"])
        self.assertFalse(payload["production_mutation_started"])
        publisher.assert_called_once_with(observation)


if __name__ == "__main__":
    unittest.main()
