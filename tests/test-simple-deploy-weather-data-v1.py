#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

sd = _load("simple_deploy_v1", ROOT / "ops/lib/deploy_executor/simple_deploy_v1.py")
schema_bridge = _load("simple_deploy_weather_schema_init_v1", ROOT / "ops/lib/deploy_executor/simple_deploy_weather_schema_init_v1.py")
bridge = _load("simple_deploy_weather_data_v1", ROOT / "ops/lib/deploy_executor/simple_deploy_weather_data_v1.py")


class FakeRunner:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def run(self, argv, *, timeout_seconds, stdin_text=None):
        self.calls.append((tuple(argv), stdin_text))
        if not self.responses:
            raise AssertionError(f"unexpected command: {argv}")
        return self.responses.pop(0)


def _preflight(source_sha: str = "d" * 40):
    return SimpleNamespace(
        compose_file=Path("/fixed/compose.yml"),
        digest="sha256:" + "1" * 64,
        metadata=SimpleNamespace(source_sha=source_sha),
        capability_source_sha="c" * 40,
        target=SimpleNamespace(image=bridge.IMAGE),
        container_id="a" * 64,
        local_image_id="sha256:" + "2" * 64,
    )


class Tests(unittest.TestCase):
    def _subject(self, runner=None):
        return bridge.WeatherDataBridge(
            registry_path=Path("/fixed/registry"),
            identity_path=Path("/fixed/identity"),
            capability_identity_path=Path("/fixed/capability"),
            compose_root=Path("/fixed"),
            runner=runner or FakeRunner(),
        )

    def _lock_patch(self, subject):
        return mock.patch.object(
            subject,
            "_target_lock",
            return_value=mock.MagicMock(__enter__=mock.Mock(return_value=None), __exit__=mock.Mock(return_value=False)),
        )

    def test_fixed_bootstrap_scope_and_checkpoint_paths(self):
        fingerprint = "a" * 64
        commands = bridge.fixed_bootstrap_commands(fingerprint)
        self.assertEqual(len(commands), 4)
        self.assertEqual(commands[0][:6], ("python", "-m", "rozkalns_weather.backfill", "--database-url", bridge.DATABASE_URL, "truth"))
        self.assertEqual([command[command.index("--model") + 1] for command in commands[1:]], list(bridge.MODELS))
        for command in commands:
            self.assertEqual(command[command.index("--start") + 1], bridge.BOOTSTRAP_START_DATE)
            self.assertEqual(command[command.index("--end") + 1], bridge.BOOTSTRAP_END_DATE)
            checkpoint = command[command.index("--checkpoint") + 1]
            self.assertTrue(checkpoint.startswith(f"/app/data/production-bootstrap-v1/{fingerprint}/"))
        for command in commands[1:]:
            self.assertEqual(command[command.index("--run-hours") + 1], "0,6,12,18")

    def test_capability_identity_is_exact_and_rejects_extra_authority_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "identity.json"
            path.write_text(json.dumps({
                "schema": bridge.CAPABILITY_IDENTITY_SCHEMA,
                "repository": bridge.HOST_REPOSITORY,
                "source_sha": "b" * 40,
            }))
            self.assertEqual(bridge.load_capability_identity(path).source_sha, "b" * 40)
            path.write_text(json.dumps({
                "schema": bridge.CAPABILITY_IDENTITY_SCHEMA,
                "repository": bridge.HOST_REPOSITORY,
                "source_sha": "b" * 40,
                "command": "anything",
            }))
            with self.assertRaises(bridge.WeatherDataError):
                bridge.load_capability_identity(path)

    def test_checkpoint_probe_blocks_any_prior_state(self):
        preflight = SimpleNamespace(compose_file=Path("/fixed/compose.yml"))
        runner = FakeRunner([
            bridge.CommandResult(0, json.dumps({
                "truth.json": True,
                "icon_d2.json": False,
                "ecmwf_ifs.json": False,
                "ecmwf_aifs.json": False,
            }), "")
        ])
        subject = self._subject(runner)
        with self.assertRaises(bridge.WeatherDataError) as cm:
            subject._require_fresh_checkpoint_root(preflight, "a" * 64)
        self.assertEqual(cm.exception.code, "PRIOR_BOOTSTRAP_STATE_PRESENT")
        self.assertTrue(cm.exception.mutation_started)

    def test_bootstrap_path_keeps_historical_source_pin(self):
        subject = self._subject()
        preflight = _preflight(bridge.EXPECTED_BOOTSTRAP_SOURCE_SHA)
        plan = {"bootstrap_fingerprint": "a" * 64}
        with self._lock_patch(subject), \
             mock.patch.object(subject, "preflight", return_value=preflight) as preflight_call, \
             mock.patch.object(subject, "_production_plan", return_value=plan), \
             mock.patch.object(subject, "_require_fresh_checkpoint_root"), \
             mock.patch.object(bridge, "fixed_bootstrap_commands", return_value=()), \
             mock.patch.object(subject, "_strict_integrity"), \
             mock.patch.object(subject, "_recheck_pointer"):
            subject.bootstrap(bridge.RECOVERY_ACCEPT_NO_BACKUP)
        preflight_call.assert_called_once_with(require_bootstrap_source=True, require_recurring_disabled=True)

    def test_nonblocking_warn_allows_enable_for_later_reviewed_consumer(self):
        runner = FakeRunner([
            bridge.CommandResult(0, json.dumps({
                "state": "WARN",
                "block_reasons": [],
                "warn_reasons": ["ECMWF_IFS_MODEL_VERSION_MISSING"],
            }), ""),
            bridge.CommandResult(0, json.dumps({"ok": True}), ""),
        ])
        subject = self._subject(runner)
        preflight = _preflight("d" * 40)
        with self._lock_patch(subject), \
             mock.patch.object(subject, "preflight", return_value=preflight) as preflight_call, \
             mock.patch.object(subject, "_recheck_pointer"):
            receipt = subject.enable_preflight()
        self.assertEqual(receipt["result"], "RECURRING_ENABLE_READY")
        self.assertEqual(receipt["consumer_source_sha"], "d" * 40)
        self.assertFalse(receipt["timer_enabled_or_started"])
        preflight_call.assert_called_once_with(require_bootstrap_source=False, require_recurring_disabled=True)
        report_call = runner.calls[0][0]
        self.assertIn(bridge.RECURRING_INTEGRITY_START_DATE, report_call)
        self.assertIn(bridge.RECURRING_INTEGRITY_END_DATE, report_call)

    def test_blocked_or_malformed_warn_still_blocks_enable(self):
        for report in (
            {"state": "BLOCKED", "block_reasons": ["X"], "warn_reasons": []},
            {"state": "WARN", "block_reasons": ["X"], "warn_reasons": ["Y"]},
            {"state": "WARN", "block_reasons": [], "warn_reasons": []},
        ):
            with self.subTest(report=report):
                runner = FakeRunner([bridge.CommandResult(0, json.dumps(report), "")])
                subject = self._subject(runner)
                with self._lock_patch(subject), mock.patch.object(subject, "preflight", return_value=_preflight()):
                    with self.assertRaises(bridge.WeatherDataError) as cm:
                        subject.enable_preflight()
                self.assertEqual(cm.exception.code, "CORPUS_REPORT_NOT_PASS")

    def test_corpus_check_failure_still_blocks_enable(self):
        runner = FakeRunner([
            bridge.CommandResult(0, json.dumps({"state": "PASS"}), ""),
            bridge.CommandResult(0, json.dumps({"ok": False}), ""),
        ])
        subject = self._subject(runner)
        with self._lock_patch(subject), mock.patch.object(subject, "preflight", return_value=_preflight()):
            with self.assertRaises(bridge.WeatherDataError) as cm:
                subject.enable_preflight()
        self.assertEqual(cm.exception.code, "CORPUS_CHECK_NOT_PASS")

    def test_timer_must_be_disabled_and_inactive_before_enable(self):
        runner = FakeRunner([
            bridge.CommandResult(0, "enabled\n", ""),
            bridge.CommandResult(3, "inactive\n", ""),
            bridge.CommandResult(3, "inactive\n", ""),
        ])
        subject = self._subject(runner)
        with self.assertRaises(bridge.WeatherDataError) as cm:
            subject._systemd_state(require_disabled=True, mutation_started=False)
        self.assertEqual(cm.exception.code, "TIMER_NOT_DISABLED")
        self.assertFalse(cm.exception.mutation_started)

    def test_integrity_pass_allows_enable_preflight_but_never_enables_systemd(self):
        runner = FakeRunner([
            bridge.CommandResult(0, json.dumps({"state": "PASS"}), ""),
            bridge.CommandResult(0, json.dumps({"ok": True}), ""),
        ])
        subject = self._subject(runner)
        with self._lock_patch(subject), mock.patch.object(subject, "preflight", return_value=_preflight()), mock.patch.object(subject, "_recheck_pointer"):
            receipt = subject.enable_preflight()
        self.assertEqual(receipt["result"], "RECURRING_ENABLE_READY")
        self.assertFalse(receipt["timer_enabled_or_started"])
        flat = "\n".join(" ".join(call[0]) for call in runner.calls)
        self.assertNotIn("systemctl enable", flat)
        self.assertNotIn("systemctl start", flat)

    def test_units_match_weather_schedule_and_are_not_self_enabling(self):
        service = (ROOT / "ops/systemd/rozkalns-weather-public-ingest.service").read_text()
        timer = (ROOT / "ops/systemd/rozkalns-weather-public-ingest.timer").read_text()
        self.assertIn("ExecStart=/usr/local/libexec/rozkalns-simple-deployer/rozkalns-simple-deploy-weather-data --ingest-once", service)
        self.assertNotIn("ExecStartPre=", service)
        self.assertIn("OnCalendar=*:0/30", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("RandomizedDelaySec=60", timer)
        self.assertIn("AccuracySec=60", timer)
        self.assertNotIn("systemctl", service + timer)

    def test_contract_and_cli_expose_only_fixed_actions(self):
        contract = json.loads((ROOT / "ops/deploy/simple-deploy-weather-data-v1.json").read_text())
        self.assertEqual(contract["issue"], 682)
        self.assertEqual(contract["reconciliation_issue"], 684)
        self.assertEqual(contract["reviewed_bootstrap_consumer_source_sha"], bridge.EXPECTED_BOOTSTRAP_SOURCE_SHA)
        self.assertEqual(contract["integrity"]["recurring_window_start"], bridge.RECURRING_INTEGRITY_START_DATE)
        self.assertEqual(contract["integrity"]["recurring_window_end"], bridge.RECURRING_INTEGRITY_END_DATE)
        self.assertEqual(contract["actions"], [
            "--preflight",
            "--bootstrap-verified-backup",
            "--bootstrap-accept-no-backup",
            "--integrity",
            "--enable-preflight",
            "--ingest-once",
        ])
        self.assertTrue(contract["recurring"]["installed_disabled_by_default"])
        self.assertTrue(contract["bootstrap"]["first_attempt_requires_all_fixed_checkpoint_files_absent"])
        self.assertTrue(contract["target"]["shared_simple_deploy_target_lock_required"])
        self.assertFalse(contract["bootstrap"]["automatic_resume"])
        source = (ROOT / "ops/lib/deploy_executor/simple_deploy_weather_data_v1.py").read_text()
        self.assertIn('args not in valid', source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("docker volume create", source)
        self.assertNotIn('"enable"', source)
        self.assertNotIn('"start"', source)


if __name__ == "__main__":
    unittest.main()
