#!/usr/bin/env python3
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import hermes_deals_runner_smoke_broker_bootstrap as bootstrap

CONTRACT_PATH = ROOT / "ops/deploy/hermes-deals-runner-smoke-broker-bootstrap.json"
ENTRYPOINT_PATH = ROOT / "ops/bin/rpi5-hermes-deals-runner-smoke-broker-bootstrap"
SERVICE_PATH = ROOT / "ops/systemd/rozkalns-hermes-deals-runner-smoke-install@.service"
SOCKET_PATH = ROOT / "ops/systemd/rozkalns-hermes-deals-runner-smoke-install.socket"


class RunnerSmokeBrokerBootstrapTests(unittest.TestCase):
    def test_source_readiness_is_fixed_and_live_disabled(self) -> None:
        ready = bootstrap.source_readiness()
        self.assertEqual(ready["implementation_issue"], 570)
        self.assertEqual(ready["caller_authority"], ())
        self.assertFalse(ready["generic_sudo_allowed"])
        self.assertFalse(ready["caller_command_allowed"])
        self.assertFalse(ready["caller_path_allowed"])
        self.assertFalse(ready["caller_argv_allowed"])
        self.assertFalse(ready["caller_environment_allowed"])
        self.assertFalse(ready["caller_unit_allowed"])
        self.assertFalse(ready["dynamic_module_discovery_allowed"])
        self.assertFalse(ready["whole_repository_copy_allowed"])
        self.assertTrue(ready["rdc_no_new_privileges_must_remain"])
        self.assertTrue(ready["bootstrap_apply_implemented"])
        self.assertFalse(ready["runtime_activation_enabled"])
        self.assertFalse(ready["systemd_socket_installed"])
        self.assertFalse(ready["source_merge_authorizes_live"])
        self.assertFalse(ready["automatic_retry"])
        self.assertFalse(ready["automatic_cleanup"])
        self.assertFalse(ready["automatic_rollback"])

    def test_external_entrypoint_accepts_no_arguments_or_generic_authority(self) -> None:
        source = ENTRYPOINT_PATH.read_text(encoding="utf-8")
        self.assertIn("len(sys.argv) != 1", source)
        self.assertIn("apply_bootstrap(repo_root)", source)
        for prohibited in (
            "argparse", "sudo", "shell=True", "--path", "--command", "--unit",
            "--uid", "--gid", "--sha", "--environment",
        ):
            self.assertNotIn(prohibited, source)
        self.assertEqual(tuple(inspect.signature(bootstrap.apply_bootstrap).parameters), ("checkout",))

    def test_runtime_manifest_is_fixed_minimal_transitive_relative_import_closure(self) -> None:
        module_set = set(bootstrap.PACKAGE_MODULES)
        self.assertEqual(len(module_set), len(bootstrap.PACKAGE_MODULES))
        self.assertIn("hermes_deals_runner_smoke_install_broker.py", module_set)
        self.assertIn("hermes_deals_runner_smoke_install_runtime.py", module_set)
        self.assertNotIn("hermes_deals_origin_broker_runtime.py", module_set)

        for module_name in bootstrap.PACKAGE_MODULES:
            path = ROOT / "ops/lib/deploy_executor" / module_name
            self.assertTrue(path.is_file(), module_name)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                    required = f"{node.module}.py"
                    with self.subTest(module=module_name, required=required):
                        self.assertIn(required, module_set)

        artifacts = bootstrap.runtime_artifacts()
        self.assertEqual(len(artifacts), 1 + len(bootstrap.PACKAGE_MODULES))
        self.assertEqual(artifacts[0], (bootstrap.BROKER_ENTRYPOINT, bootstrap.BROKER_ENTRYPOINT, 0o755))
        for source, destination, mode in artifacts[1:]:
            self.assertEqual(source, destination)
            self.assertTrue(str(source).startswith("ops/lib/deploy_executor/"))
            self.assertEqual(mode, 0o644)

    def test_plan_accepts_only_absent_or_exact_terminal_states(self) -> None:
        sha = "a" * 40
        absent = bootstrap.BootstrapObservation(
            source_sha=sha,
            filesystem_state="ABSENT",
            socket_enabled_state="not-found",
            socket_active_state="inactive",
        )
        plan = bootstrap.plan_bootstrap(absent)
        self.assertEqual(plan.decision, "INSTALL_REQUIRED_EXPLICIT_LIVE")
        self.assertEqual(plan.mutations_required, bootstrap.MUTATION_SEQUENCE)
        self.assertEqual(plan.caller_arguments, ())

        exact = bootstrap.BootstrapObservation(
            source_sha=sha,
            filesystem_state="EXACT",
            socket_enabled_state="enabled",
            socket_active_state="active",
        )
        plan = bootstrap.plan_bootstrap(exact)
        self.assertEqual(plan.decision, "ALREADY_EXACT_NO_MUTATION")
        self.assertEqual(plan.mutations_required, ())

        partial = (
            bootstrap.BootstrapObservation(sha, "EXACT", "disabled", "inactive"),
            bootstrap.BootstrapObservation(sha, "ABSENT", "enabled", "active"),
            bootstrap.BootstrapObservation(sha, "DRIFT", "not-found", "inactive"),
        )
        for value in partial:
            with self.subTest(value=value):
                with self.assertRaises(bootstrap.RunnerSmokeBrokerBootstrapError):
                    bootstrap.plan_bootstrap(value)

    def test_fixed_systemctl_mutation_surface_has_only_two_commands(self) -> None:
        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with mock.patch.object(bootstrap.subprocess, "run", return_value=ok) as run:
            bootstrap._run_fixed_systemctl("daemon-reload")
            bootstrap._run_fixed_systemctl("enable", "--now", bootstrap.SOCKET_UNIT)
        calls = [call.args[0] for call in run.call_args_list]
        self.assertEqual(
            calls,
            [
                ["/usr/bin/systemctl", "daemon-reload"],
                ["/usr/bin/systemctl", "enable", "--now", bootstrap.SOCKET_UNIT],
            ],
        )
        with self.assertRaises(bootstrap.RunnerSmokeBrokerBootstrapError):
            bootstrap._run_fixed_systemctl("restart", bootstrap.SOCKET_UNIT)
        with self.assertRaises(bootstrap.RunnerSmokeBrokerBootstrapError):
            bootstrap._run_fixed_systemctl("enable", "--now", "ssh.service")

    def test_failure_receipt_is_fail_closed_without_recovery_actions(self) -> None:
        pre = bootstrap.failure_receipt(mutation_started=False)
        self.assertEqual(pre["result"], "FAIL_CLOSED")
        self.assertEqual(pre["mutation_state"], "NOT_STARTED")
        post = bootstrap.failure_receipt(mutation_started=True)
        self.assertEqual(post["mutation_state"], "UNKNOWN_FAIL_CLOSED")
        for receipt in (pre, post):
            self.assertFalse(receipt["automatic_retry"])
            self.assertFalse(receipt["automatic_cleanup"])
            self.assertFalse(receipt["automatic_rollback"])

    def test_contract_matches_fixed_source_surface(self) -> None:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(value["implementation_issue"], 570)
        self.assertEqual(value["status"], "SOURCE_READY_LIVE_DISABLED")
        self.assertEqual(value["trusted_checkout_name"], bootstrap.TRUSTED_CHECKOUT_NAME)
        self.assertEqual(value["release_root"], str(bootstrap.RELEASE_ROOT))
        self.assertEqual(value["current_link"], str(bootstrap.CURRENT_LINK))
        self.assertEqual(value["socket_destination"], str(bootstrap.SOCKET_DESTINATION))
        self.assertEqual(value["service_destination"], str(bootstrap.SERVICE_DESTINATION))
        self.assertEqual(tuple(value["activation_sequence"]), bootstrap.MUTATION_SEQUENCE)
        self.assertEqual(value["authority"]["caller_arguments"], [])
        self.assertFalse(value["authority"]["generic_sudo"])
        self.assertFalse(value["activation"]["source_merge_authorizes_live"])
        self.assertTrue(value["activation"]["separate_explicit_live_authorization_required"])

    def test_existing_systemd_source_stays_identity_only_and_no_new_privileges(self) -> None:
        service = SERVICE_PATH.read_text(encoding="utf-8")
        socket = SOCKET_PATH.read_text(encoding="utf-8")
        service_directives = "\n".join(line.split("#", 1)[0] for line in service.splitlines())
        self.assertIn(
            "ExecStart=/usr/local/libexec/rozkalns-runner-smoke-install/current/ops/bin/rpi5-hermes-deals-runner-smoke-install-broker",
            service,
        )
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("StandardInput=socket", service)
        self.assertIn("StandardOutput=socket", service)
        self.assertIn("SocketMode=0600", socket)
        self.assertIn("SocketUser=andris", socket)
        self.assertIn("Accept=yes", socket)
        self.assertNotIn("sudo", service_directives)
        self.assertNotIn("/bin/sh", service)
        self.assertNotIn("/bin/bash", service)


if __name__ == "__main__":
    unittest.main()
