from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import uuid
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/lib/deploy_executor/weather_public_runtime_privileged_install.py"
ENTRYPOINT = ROOT / "ops/bin/rozkalns-weather-public-runtime-privileged-install"
CONTRACT = ROOT / "ops/deploy/weather-public-runtime-privileged-install-activation.json"
CHECKOUT_CONTRACT = ROOT / "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json"
MANIFEST = ROOT / "ops/deploy/weather-public-runtime-helper-install.json"
DOC = ROOT / "docs/WEATHER_PUBLIC_RUNTIME_PRIVILEGED_INSTALL_ACTIVATION.md"
TRUSTED_DERIVATION = "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted"
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor.protocol import AcceptedAuthorization, AUTHORIZATION_REPOSITORY, AUTHORIZATION_REPOSITORY_ID
from deploy_executor.state import StateStore
from deploy_executor.weather_public_runtime_host_wiring import expected_helper_bindings
import deploy_executor.weather_public_runtime_privileged_install as bridge


class WeatherPrivilegedInstallSourceTests(unittest.TestCase):
    def test_source_readiness_is_capability_specific_and_inactive(self) -> None:
        ready = bridge.source_readiness()
        self.assertEqual(ready["caller_authority"], ("authorization_issue_number",))
        self.assertEqual(ready["trusted_install_checkout"], TRUSTED_DERIVATION)
        self.assertEqual(ready["helper_install_artifact_count"], 13)
        self.assertTrue(ready["capability_specific_root_entrypoint_source_present"])
        for key in (
            "runtime_live_authority", "privileged_install_invocation_enabled",
            "helper_installation_enabled", "activation_publication_enabled",
            "stage_invocation_enabled", "production_mutation_enabled",
            "production_mutation_started", "generic_shell_authority",
            "caller_supplied_path_allowed", "caller_supplied_argv_allowed",
            "caller_supplied_environment_allowed", "automatic_retry",
            "automatic_cleanup", "automatic_rollback",
        ):
            self.assertFalse(ready[key], key)

    def test_entrypoint_exposes_only_issue_number(self) -> None:
        source = ENTRYPOINT.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(ENTRYPOINT))
        options = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
                options.extend(arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
        self.assertEqual(options, ["--issue-number"])
        self.assertIn('_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-install-trusted"', source)
        self.assertIn("Path(__file__).resolve().parents[2]", source)
        for forbidden in ("shell=True", "os.system", "subprocess.Popen", "--path", "--command", "--argv", "--env", "--source", "--destination"):
            self.assertNotIn(forbidden, source)

    def test_module_has_no_generic_privileged_execution_surface(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden in ("shell=True", "os.system", "eval(", "exec(", "shutil.copytree", "PYTHONPATH"):
            self.assertNotIn(forbidden, source)
        self.assertIn('args[0] not in {"/usr/bin/git", "/usr/bin/docker", "/usr/bin/systemctl"}', source)
        self.assertIn("replay.consume(envelope.request_id)", source)
        self.assertLess(source.index("replay.consume(envelope.request_id)"), source.index("_install_helper_transaction(envelope.request_id, artifacts)"))

    def test_public_source_contains_no_concrete_user_home(self) -> None:
        for path in (MODULE_PATH, ENTRYPOINT, CONTRACT, DOC):
            self.assertNotIn("/home/", path.read_text(encoding="utf-8"), path)

    def test_manifest_identity_is_a_closed_allowlist(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        expected = tuple((item["source"], item["destination"], int(item["mode"], 8)) for item in manifest["artifacts"])
        self.assertEqual(expected, bridge._EXPECTED_ARTIFACTS)
        self.assertEqual(len(expected), 13)
        self.assertEqual(len({destination for _, destination, _ in expected}), 13)
        self.assertEqual(manifest["trusted_checkout_bootstrap_contract"], "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json")
        self.assertEqual(manifest["trusted_checkout_target"], TRUSTED_DERIVATION)
        self.assertEqual(expected, bridge.expected_install_artifacts())

    def test_activation_payload_is_exact_and_parseable(self) -> None:
        fake = SimpleNamespace(source_sha="a" * 40, preactivation_sha256="b" * 64, start_date="2026-03-15", end_date="2026-09-10", recovery_decision="owner-accepted-no-prewrite-backup")
        payload = bridge._activation_payload(fake)
        self.assertEqual(set(payload), {"schema", "enabled", "target_alias", "operation_id", "source_sha", "preactivation_sha256", "start_date", "end_date", "recovery_decision", "allowed_helper_ids"})
        self.assertEqual(payload["allowed_helper_ids"], [binding.helper_id for binding in expected_helper_bindings()])
        parsed = bridge.parse_activation(payload)
        self.assertEqual(parsed.source_sha, "a" * 40)
        self.assertEqual(parsed.start_date, "2026-03-15")
        self.assertEqual(parsed.end_date, "2026-09-10")

    def test_durable_replay_consumes_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.sqlite3"
            bootstrap = StateStore(state_path, bootstrap=True)
            bootstrap.close()
            request_id = str(uuid.uuid4())
            accepted = AcceptedAuthorization(
                repository_id=AUTHORIZATION_REPOSITORY_ID,
                repository_full_name=AUTHORIZATION_REPOSITORY,
                issue_id=9001,
                issue_number=91,
                request_id=request_id,
                created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
                target_alias="rozkalns-weather-public-rpi5",
                canonical_payload_json="{}",
                canonical_payload_sha256="a" * 64,
                raw_body_sha256="b" * 64,
                performed_via_github_app_id=None,
                performed_via_github_app_slug=None,
            )
            with mock.patch.object(bridge, "STATE_DB", state_path):
                replay = bridge._WeatherDurableReplayAuthority()
                self.assertTrue(replay.is_available(accepted))
                replay.assert_unconsumed(issue_id=accepted.issue_id, request_id=request_id)
                replay.consume(request_id)
                self.assertFalse(replay._available(issue_id=accepted.issue_id, request_id=request_id))
                replay.mark_succeeded(request_id)
                store = StateStore(state_path)
                try:
                    self.assertEqual(store.get(request_id).state, "SUCCEEDED")
                finally:
                    store.close()

    def test_machine_contracts_freeze_successor_checkout(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        checkout = json.loads(CHECKOUT_CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["status"], "SOURCE_ONLY_PRIVILEGED_BRIDGE_INACTIVE")
        self.assertEqual(contract["caller_arguments"], ["authorization_issue_number"])
        self.assertEqual(contract["trusted_checkout"], TRUSTED_DERIVATION)
        self.assertEqual(contract["runtime_entrypoint"], f"{TRUSTED_DERIVATION}/ops/bin/rozkalns-weather-public-runtime-privileged-install")
        self.assertEqual(contract["helper_install_artifact_count"], 13)
        self.assertFalse(contract["source_merge_enables_live"])
        self.assertFalse(contract["stage_invocation"])
        self.assertEqual(checkout["trusted_checkout"]["derivation"], TRUSTED_DERIVATION)
        self.assertTrue(checkout["legacy_checkout"]["may_remain_present"])
        for key in ("automatic_retry", "automatic_cleanup", "automatic_rollback", "legacy_checkout_mutation"):
            self.assertFalse(checkout["failure"][key])


if __name__ == "__main__":
    unittest.main(verbosity=2)
