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


class Tests(unittest.TestCase):
    def test_fixed_bootstrap_scope_and_checkpoint_paths(self):
        fingerprint = "a" * 64
        commands = bridge.fixed_bootstrap_commands(fingerprint)
        self.assertEqual(len(commands), 4)
        self.assertEqual(commands[0][:6], ("python", "-m", "rozkalns_weather.backfill", "--database-url", bridge.DATABASE_URL, "truth"))
        self.assertEqual([command[command.index("--model") + 1] for command in commands[1:]], list(bridge.MODELS))
        for command in commands:
            self.assertEqual(command[command.index("--start") + 1], bridge.START_DATE)
            self.assertEqual(command[command.index("--end") + 1], bridge.END_DATE)
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
        subject = bridge.WeatherDataBridge(
            registry_path=Path("/fixed/registry"),
            identity_path=Path("/fixed/identity"),
            capability_identity_path=Path("/fixed/capability"),
            compose_root=Path("/fixed"),
            runner=runner,
        )
        with self.assertRaises(bridge.WeatherDataError) as cm:
            subject._require_fresh_checkpoint_root(preflight, "a" * 64)
        self.assertEqual(cm.exception.code, "PRIOR_BOOTSTRAP_STATE_PRESENT")
        self.assertTrue(cm.exception.mutation_started)

    def test_integrity_requires_exact_pass_before_enable_ready(self):
        preflight = SimpleNamespace(
            compose_file=Path("/fixed/compose.yml"),
            digest="sha256:" + "1" * 64,
            metadata=SimpleNamespace(source_sha=bridge.EXPECTED_BOOTSTRAP_SOURCE_SHA),
            capability_source_sha="c" * 40,
            target=SimpleNamespace(image=bridge.IMAGE),
        )
        runner = FakeRunner([
            bridge.CommandResult(0, json.dumps({"state": "WARN"}), ""),
        ])
        subject = bridge.WeatherDataBridge(
            registry_path=Path("/fixed/registry"),
            identity_path=Path("/fixed/identity"),
            capability_identity_path=Path("/fixed/capability"),
            compose_root=Path("/fixed"),
            runner=runner,
        )
        with mock.patch.object(subject, "_target_lock", return_value=mock.MagicMock(__enter__=mock.Mock(return_value=None), __exit__=mock.Mock(return_value=False))), mock.patch.object(subject, "preflight", return_value=preflight):
            with self.assertRaises(bridge.WeatherDataError) as cm:
                subject.enable_preflight()
        self.assertEqual(cm.exception.code, "CORPUS_REPORT_NOT_PASS")
        self.assertTrue(cm.exception.mutation_started)

    def test_integrity_pass_allows_enable_preflight_but_never_enables_systemd(self):
        preflight = SimpleNamespace(
            compose_file=Path("/fixed/compose.yml"),
            digest="sha256:" + "1" * 64,
            metadata=SimpleNamespace(source_sha=bridge.EXPECTED_BOOTSTRAP_SOURCE_SHA),
            capability_source_sha="c" * 40,
            target=SimpleNamespace(image=bridge.IMAGE),
        )
        runner = FakeRunner([
            bridge.CommandResult(0, json.dumps({"state": "PASS"}), ""),
            bridge.CommandResult(0, json.dumps({"ok": True}), ""),
        ])
        subject = bridge.WeatherDataBridge(
            registry_path=Path("/fixed/registry"),
            identity_path=Path("/fixed/identity"),
            capability_identity_path=Path("/fixed/capability"),
            compose_root=Path("/fixed"),
            runner=runner,
        )
        with mock.patch.object(subject, "_target_lock", return_value=mock.MagicMock(__enter__=mock.Mock(return_value=None), __exit__=mock.Mock(return_value=False))), mock.patch.object(subject, "preflight", return_value=preflight), mock.patch.object(subject, "_recheck_pointer"):
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
        self.assertEqual(contract["reviewed_bootstrap_consumer_source_sha"], bridge.EXPECTED_BOOTSTRAP_SOURCE_SHA)
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
