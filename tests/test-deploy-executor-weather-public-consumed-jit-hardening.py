from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import sys
import unittest

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


class WeatherConsumedJITHardeningTests(unittest.TestCase):
    def setUp(self):
        FIXTURE.SERVER_DATE = "Thu, 10 Sep 2026 04:01:00 GMT"

    def _accepted_then_consumed(self):
        replay = FIXTURE.ReplayAvailability()
        target, sender, replay = FIXTURE.revalidator(replay=replay)
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


if __name__ == "__main__":
    unittest.main()
