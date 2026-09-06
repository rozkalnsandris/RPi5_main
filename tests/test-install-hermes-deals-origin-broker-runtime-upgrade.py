from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import os
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/install-hermes-deals-origin-broker-runtime-upgrade.py"
spec = importlib.util.spec_from_file_location("hermes_runtime_upgrade", SCRIPT)
assert spec is not None and spec.loader is not None
upgrade = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = upgrade
spec.loader.exec_module(upgrade)


def completed(returncode: int = 0, stdout: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(("test",), returncode, stdout=stdout, stderr=b"")


class HermesOriginBrokerRuntimeUpgradeTests(unittest.TestCase):
    def test_mutation_surface_is_exact_and_capability_specific(self) -> None:
        self.assertEqual(len(upgrade.REPLACE_TARGETS), 5)
        self.assertEqual(len(upgrade.CREATE_TARGETS), 6)
        self.assertEqual(len(upgrade.PREREQUISITES), 16)
        self.assertEqual(
            upgrade.SYSTEMCTL_MUTATIONS,
            (("stop", upgrade.SOCKET_UNIT), ("daemon-reload",), ("start", upgrade.SOCKET_UNIT)),
        )
        targets = {item.source_path for item in (*upgrade.REPLACE_TARGETS, *upgrade.CREATE_TARGETS)}
        self.assertNotIn("ops/deploy/executor-operations.json", targets)
        self.assertNotIn("ops/lib/deploy_executor/registry.py", targets)
        self.assertNotIn("ops/lib/deploy_executor/adapters.py", targets)
        self.assertNotIn("ops/lib/deploy_executor/queue_normalizer.py", targets)

    def test_service_write_authority_is_only_replay_state_directory(self) -> None:
        unit = (ROOT / "ops/systemd/rozkalns-hermes-deals-origin-broker@.service").read_text()
        write_lines = [line for line in unit.splitlines() if line.startswith("ReadWritePaths=")]
        self.assertEqual(write_lines, ["ReadWritePaths=/var/lib/rozkalns-deploy-executor-p9 /var/lib/hermes-deals-audits/origin-path-audit/evidence/rpi5"])
        self.assertNotIn("ReadWritePaths=/var/lib/rozkalns-deploy-executor\n", unit)

    def test_git_source_guard_is_exact_command_scoped_and_clean(self) -> None:
        source = SCRIPT.read_text()
        self.assertIn("f'safe.directory={ROOT}'", source)
        self.assertIn("_git_stdout('rev-parse', 'HEAD')", source)
        self.assertIn("_git('status','--porcelain')", source)
        self.assertIn("_git_stdout('show', f'{expected_sha}:{SCRIPT_RELATIVE}')", source)
        self.assertNotIn("safe.directory=*", source)
        self.assertNotIn("--global", source)
        self.assertNotIn("--system", source)

    def test_systemctl_mutation_rejects_non_allowlisted_action(self) -> None:
        state = upgrade._new_state()
        with self.assertRaises(upgrade.UpgradeError):
            upgrade._systemctl_mutation(state, "restart", upgrade.SOCKET_UNIT)
        self.assertFalse(state["mutation_started"])

    def test_apply_order_is_stop_files_reload_start(self) -> None:
        state = upgrade._new_state()
        events: list[str] = []
        reviewed = {item.source_path: b"reviewed" for item in (*upgrade.REPLACE_TARGETS, *upgrade.CREATE_TARGETS)}
        active_checks = iter((completed(3, b"inactive\n"), completed(0, b"active\n")))

        def fake_preflight(_sha: str):
            events.append("preflight")
            return reviewed

        def fake_mutation(inner_state, *args):
            inner_state["mutation_started"] = True
            events.append("systemctl:" + " ".join(args))

        def fake_query(*args):
            if args == ("is-active", upgrade.SOCKET_UNIT):
                events.append("query:is-active")
                return next(active_checks)
            if args[0] == "list-units":
                events.append("query:list-units")
                return completed(0, b"")
            if args == ("is-enabled", upgrade.SOCKET_UNIT):
                events.append("query:is-enabled")
                return completed(0, b"enabled\n")
            raise AssertionError(args)

        def fake_replace(target, _data, inner_state):
            events.append("replace:" + target.source_path)
            inner_state["files_replaced"] = int(inner_state["files_replaced"]) + 1

        def fake_create(target, _data, inner_state):
            events.append("create:" + target.source_path)
            inner_state["files_created"] = int(inner_state["files_created"]) + 1

        with mock.patch.object(upgrade, "_preflight", side_effect=fake_preflight), \
             mock.patch.object(upgrade, "_systemctl_mutation", side_effect=fake_mutation), \
             mock.patch.object(upgrade, "_systemctl_query", side_effect=fake_query), \
             mock.patch.object(upgrade, "_replace_target", side_effect=fake_replace), \
             mock.patch.object(upgrade, "_create_target", side_effect=fake_create), \
             mock.patch.object(upgrade, "_read_exact_file", return_value=None):
            value = json.loads(upgrade.apply("a" * 40, state))

        self.assertEqual(events[:3], ["preflight", "preflight", f"systemctl:stop {upgrade.SOCKET_UNIT}"])
        stop_index = events.index(f"systemctl:stop {upgrade.SOCKET_UNIT}")
        first_file = min(i for i, event in enumerate(events) if event.startswith(("replace:", "create:")))
        reload_index = events.index("systemctl:daemon-reload")
        start_index = events.index(f"systemctl:start {upgrade.SOCKET_UNIT}")
        self.assertLess(stop_index, first_file)
        self.assertLess(first_file, reload_index)
        self.assertLess(reload_index, start_index)
        self.assertEqual(value["result"], "HERMES_ORIGIN_BROKER_RUNTIME_UPGRADE_PASS")
        self.assertEqual(value["files_replaced"], 5)
        self.assertEqual(value["files_created"], 6)
        self.assertTrue(value["socket_started"])
        self.assertFalse(value["global_registry_mutation"])
        self.assertFalse(value["replay_consume_invoked"])
        self.assertFalse(value["helper_executed"])

    def test_post_stop_failure_has_no_retry_rollback_or_socket_restart(self) -> None:
        state = upgrade._new_state()
        reviewed = {item.source_path: b"reviewed" for item in (*upgrade.REPLACE_TARGETS, *upgrade.CREATE_TARGETS)}
        mutations: list[tuple[str, ...]] = []

        def fake_mutation(inner_state, *args):
            inner_state["mutation_started"] = True
            mutations.append(tuple(args))

        def fake_query(*args):
            if args == ("is-active", upgrade.SOCKET_UNIT):
                return completed(3, b"inactive\n")
            if args[0] == "list-units":
                return completed(0, b"")
            raise AssertionError(args)

        with mock.patch.object(upgrade, "_preflight", return_value=reviewed), \
             mock.patch.object(upgrade, "_systemctl_mutation", side_effect=fake_mutation), \
             mock.patch.object(upgrade, "_systemctl_query", side_effect=fake_query), \
             mock.patch.object(upgrade, "_replace_target", side_effect=upgrade.UpgradeError("simulated post-stop failure")):
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.apply("a" * 40, state)

        self.assertEqual(mutations, [("stop", upgrade.SOCKET_UNIT)])
        self.assertTrue(state["mutation_started"])
        self.assertTrue(state["socket_stopped"])
        self.assertFalse(state["daemon_reload_attempted"])
        self.assertFalse(state["socket_start_attempted"])
        self.assertFalse(state["socket_started"])

    def test_fixed_registry_is_compatible_with_frozen_installed_resolver_modules(self) -> None:
        frozen = {
            "adapters.py": "9d62967607fc9677a3c8cc2720462ee7135ed2a6",
            "queue_normalizer.py": "1878d4765fab112a1066aec75cbcd9c422040dd2",
            "registry.py": "7de127a58534879385bc58299827d9081775dbe9",
        }
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            package = temp_root / "deploy_executor"
            shutil.copytree(ROOT / "ops/lib/deploy_executor", package)
            for name, blob in frozen.items():
                data = subprocess.check_output(("git", "cat-file", "blob", blob), cwd=ROOT)
                (package / name).write_bytes(data)
            fixture = ROOT / "tests/fixtures/deploy_executor/queue_issue_hermes_deals_origin_ready_markup.json"
            code = (
                "import json\n"
                "from pathlib import Path\n"
                "from deploy_executor.hermes_deals_origin_broker_runtime import _fixed_registry\n"
                "from deploy_executor.queue_normalizer import normalize_ready_queue\n"
                "registry=_fixed_registry()\n"
                "assert registry.execution_enabled is False\n"
                "assert len(registry.operations)==1\n"
                "assert registry.operations[0].baseline.kind=='resolver'\n"
                f"issue=json.loads(Path({str(fixture)!r}).read_text())\n"
                "normalized=normalize_ready_queue(issue,repository_full_name='rozkalnsandris/ops-workflows',registry=registry)\n"
                "assert normalized.operation.operation_id=='hermes-deals.origin-path-audit.v1'\n"
                "assert normalized.as_protocol_queue()['expected_baseline']=={'kind':'resolver','value':'hermes-deals.origin-path-registration.v1'}\n"
            )
            env = dict(os.environ)
            env["PYTHONPATH"] = str(temp_root)
            result = subprocess.run(
                (sys.executable, "-c", code), cwd=ROOT, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_machine_contract_binds_operator_targets_and_stays_nonlive(self) -> None:
        contract_path = ROOT / "ops/deploy/hermes-deals-origin-broker-runtime-upgrade.json"
        contract = json.loads(contract_path.read_text())
        operator_blob = subprocess.check_output(
            ("git", "hash-object", str(SCRIPT.relative_to(ROOT))), cwd=ROOT, text=True
        ).strip()
        self.assertEqual(contract["operator"]["source_blob"], operator_blob)
        self.assertEqual(
            [(row["source"], row["target"], row["old_blob"], row["new_blob"], row["mode"]) for row in contract["replace_targets"]],
            [(t.source_path, str(t.target_path), t.old_blob, t.new_blob, f"{t.mode:04o}") for t in upgrade.REPLACE_TARGETS],
        )
        self.assertEqual(
            [(row["source"], row["target"], row["new_blob"], row["mode"]) for row in contract["create_targets"]],
            [(t.source_path, str(t.target_path), t.new_blob, f"{t.mode:04o}") for t in upgrade.CREATE_TARGETS],
        )
        self.assertEqual(
            [(row["target"], row["expected_blob"], row["mode"]) for row in contract["shared_prerequisites"]],
            [(str(t.target_path), t.expected_blob, f"{t.mode:04o}") for t in upgrade.PREREQUISITES],
        )
        design = contract["runtime_design"]
        self.assertTrue(design["fixed_runtime_registry_implemented"])
        self.assertFalse(design["global_p9_registry_used"])
        self.assertFalse(design["global_p9_registry_mutation"])
        self.assertEqual(
            design["service_write_permission"],
            "ReadWritePaths=/var/lib/rozkalns-deploy-executor-p9",
        )
        state = contract["source_gate_state"]
        for key in (
            "runtime_upgrade_preflight_proven",
            "runtime_upgrade_applied",
            "current_service_replay_write_authority_proven",
            "privileged_dispatch_enabled",
            "replay_consume_invoked",
            "helper_executed",
            "genuine_hermes_audit_authorized",
            "runner_retirement_eligible",
            "production_mutation_started",
            "live_upgrade_eligible",
        ):
            self.assertFalse(state[key], key)

    def test_receipt_never_claims_audit_or_production_mutation(self) -> None:
        value = json.loads(upgrade._receipt("TEST", "a" * 40, upgrade._new_state()))
        self.assertFalse(value["credential_content_read"])
        self.assertFalse(value["github_api_request"])
        self.assertFalse(value["replay_consume_invoked"])
        self.assertFalse(value["helper_executed"])
        self.assertFalse(value["genuine_audit_authorized"])
        self.assertFalse(value["production_mutation_started"])
        self.assertFalse(value["automatic_retry"])
        self.assertFalse(value["automatic_rollback"])
        self.assertFalse(value["automatic_cleanup"])


if __name__ == "__main__":
    unittest.main()
