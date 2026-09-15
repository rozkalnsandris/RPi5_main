#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.weather_private_bigquery_host_installer import (  # noqa: E402
    ADAPTER_ID,
    BASELINE_RESOLVER_ID,
    CanonicalInstallEvidence,
    REQUIRED_EXCLUSIONS,
    SOURCE_REPOSITORY,
    WeatherNextPrivateHostInstallerError,
    apply_install,
    source_readiness,
)
from deploy_executor.weather_private_bigquery_host_installer_runtime import (  # noqa: E402
    _fixed_registry,
    source_readiness as runtime_source_readiness,
)
from deploy_executor.weather_private_bigquery_host_runtime import (  # noqa: E402
    INSTALL_MUTATION_BUDGET,
    INSTALL_OPERATION_ID,
    INSTALL_TARGET_ALIAS,
    HostInstallObservation,
)

SHA = "a" * 40
REQUEST = "11111111-1111-4111-8111-111111111111"


class FakeReplay:
    def __init__(self, events: list[str]):
        self.events = events
        self.consumed = False
        self.succeeded = False

    def consume(self, request_id: str) -> None:
        if self.consumed:
            raise AssertionError("replay consume called twice")
        if request_id != REQUEST:
            raise AssertionError("unexpected request id")
        self.events.append("consume")
        self.consumed = True

    def mark_succeeded(self, request_id: str) -> None:
        if not self.consumed or request_id != REQUEST:
            raise AssertionError("success without canonical consume")
        self.events.append("succeeded")
        self.succeeded = True


class FakeBackend:
    def __init__(
        self,
        events: list[str],
        observation: HostInstallObservation,
        *,
        fail_at: str | None = None,
    ):
        self.events = events
        self.checkout = observation.trusted_checkout_state
        self.operator = observation.operator_state
        self.marker = observation.activation_marker_state
        self.fail_at = fail_at

    def observe(self, exact_source_sha: str) -> HostInstallObservation:
        if exact_source_sha != SHA:
            raise AssertionError("unexpected source SHA")
        self.events.append("observe")
        return HostInstallObservation(self.checkout, self.operator, self.marker)

    def _step(self, name: str) -> None:
        self.events.append(name)
        if self.fail_at == name:
            raise RuntimeError("synthetic post-consume failure")

    def fetch_origin_main(self, exact_source_sha: str) -> None:
        self._step("fetch")

    def create_trusted_checkout(self, exact_source_sha: str) -> None:
        self._step("worktree")
        self.checkout = "EXACT"

    def install_operator(self, exact_source_sha: str) -> None:
        self._step("operator")
        self.operator = "EXACT"

    def write_activation_marker(self, exact_source_sha: str) -> None:
        self._step("marker")
        self.marker = "EXACT"

    def verify_exact(self, exact_source_sha: str) -> HostInstallObservation:
        self.events.append("verify")
        result = HostInstallObservation(self.checkout, self.operator, self.marker)
        if result != HostInstallObservation("EXACT", "EXACT", "EXACT"):
            raise RuntimeError("synthetic final identity mismatch")
        return result


def evidence(**overrides: object) -> CanonicalInstallEvidence:
    values: dict[str, object] = {
        "authorization_issue_number": 99,
        "authorization_issue_id": 999,
        "authorization_created_at": "2026-09-15T10:00:00Z",
        "github_server_time": "2026-09-15T10:00:01Z",
        "request_id": REQUEST,
        "request_body_sha256": "b" * 64,
        "operation_id": INSTALL_OPERATION_ID,
        "target_alias": INSTALL_TARGET_ALIAS,
        "rpi5_main_sha": SHA,
        "queue_issue_number": 77,
    }
    values.update(overrides)
    return CanonicalInstallEvidence(**values)


class InstallerPlanTests(unittest.TestCase):
    def test_absent_state_executes_exact_four_mutations_after_consume(self) -> None:
        events: list[str] = []
        replay = FakeReplay(events)
        backend = FakeBackend(events, HostInstallObservation("ABSENT", "ABSENT", "ABSENT"))
        receipt = apply_install(evidence(), replay=replay, backend=backend)
        self.assertEqual(
            events,
            ["observe", "consume", "fetch", "worktree", "operator", "marker", "verify", "succeeded"],
        )
        self.assertEqual(receipt.mutations_executed, tuple(category for category, _ in INSTALL_MUTATION_BUDGET))
        self.assertTrue(receipt.authorization_consumed)
        self.assertTrue(receipt.production_mutation_started)
        self.assertTrue(replay.succeeded)

    def test_exact_state_is_idempotent_and_does_not_consume(self) -> None:
        events: list[str] = []
        replay = FakeReplay(events)
        backend = FakeBackend(events, HostInstallObservation("EXACT", "EXACT", "EXACT"))
        receipt = apply_install(evidence(), replay=replay, backend=backend)
        self.assertEqual(events, ["observe", "verify"])
        self.assertEqual(receipt.mutations_executed, ())
        self.assertFalse(receipt.authorization_consumed)
        self.assertFalse(receipt.production_mutation_started)
        self.assertFalse(replay.consumed)

    def test_conflict_fails_before_consume(self) -> None:
        events: list[str] = []
        replay = FakeReplay(events)
        backend = FakeBackend(events, HostInstallObservation("CONFLICT", "ABSENT", "ABSENT"))
        with self.assertRaises(Exception):
            apply_install(evidence(), replay=replay, backend=backend)
        self.assertEqual(events, ["observe"])
        self.assertFalse(replay.consumed)

    def test_failure_after_consume_stops_without_retry_or_cleanup(self) -> None:
        events: list[str] = []
        replay = FakeReplay(events)
        backend = FakeBackend(
            events,
            HostInstallObservation("ABSENT", "ABSENT", "ABSENT"),
            fail_at="worktree",
        )
        with self.assertRaisesRegex(RuntimeError, "synthetic post-consume failure"):
            apply_install(evidence(), replay=replay, backend=backend)
        self.assertEqual(events, ["observe", "consume", "fetch", "worktree"])
        self.assertTrue(replay.consumed)
        self.assertFalse(replay.succeeded)

    def test_stale_or_widened_canonical_evidence_fails_before_observation(self) -> None:
        for changed in (
            {"source_ci_success": False},
            {"queue_ready": False},
            {"app_authored": True},
            {"operation_id": "other.operation"},
            {"target_alias": "other-target"},
            {"rollback_policy": "BUILTIN_TRANSACTIONAL_V1"},
        ):
            with self.subTest(changed=changed):
                events: list[str] = []
                with self.assertRaises(WeatherNextPrivateHostInstallerError):
                    apply_install(
                        evidence(**changed),
                        replay=FakeReplay(events),
                        backend=FakeBackend(
                            events,
                            HostInstallObservation("ABSENT", "ABSENT", "ABSENT"),
                        ),
                    )
                self.assertEqual(events, [])


class SourceContractTests(unittest.TestCase):
    def test_core_and_runtime_remain_source_disabled(self) -> None:
        core = source_readiness()
        runtime = runtime_source_readiness()
        self.assertEqual(core["implementation_issue"], 554)
        self.assertEqual(core["mutation_budget"], INSTALL_MUTATION_BUDGET)
        self.assertEqual(core["rollback_policy"], "NONE")
        self.assertFalse(core["global_executor_execution_enabled"])
        self.assertFalse(core["privileged_dispatch_enabled"])
        self.assertFalse(core["source_merge_authorizes_live"])
        self.assertFalse(runtime["fixed_registry_execution_enabled"])
        self.assertFalse(runtime["global_executor_execution_enabled"])
        self.assertFalse(runtime["runtime_activation_enabled"])
        self.assertFalse(runtime["privileged_boundary_installed"])
        self.assertFalse(runtime["source_merge_authorizes_live"])

    def test_fixed_registry_is_strict_and_exact(self) -> None:
        registry = _fixed_registry()
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, INSTALL_OPERATION_ID)
        self.assertEqual(operation.source_repository, SOURCE_REPOSITORY)
        self.assertEqual(operation.target_alias, INSTALL_TARGET_ALIAS)
        self.assertEqual(operation.adapter_id, ADAPTER_ID)
        self.assertEqual(operation.authorization_class, "STRICT")
        self.assertFalse(operation.ordinary_live_all_eligible)
        self.assertEqual(operation.baseline.resolver_id, BASELINE_RESOLVER_ID)
        self.assertEqual(
            tuple((item.category, item.max_operations) for item in operation.mutation_budget),
            INSTALL_MUTATION_BUDGET,
        )
        self.assertEqual(operation.rollback_policy, "NONE")
        self.assertTrue(set(REQUIRED_EXCLUSIONS).issubset(set(operation.exclusions)))

    def test_machine_contract_preserves_bootstrap_and_capability_boundaries(self) -> None:
        path = ROOT / "ops/deploy/weather-private-bigquery-host-privileged-installer.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(value["implementation_issue"], 554)
        self.assertFalse(value["global_executor_execution_enabled"])
        self.assertFalse(value["privileged_dispatch_enabled"])
        self.assertFalse(value["source_merge_authorizes_live"])
        self.assertEqual(value["privileged_boundary"]["status"], "SOURCE_READY_HOST_BOOTSTRAP_REQUIRED")
        self.assertEqual(value["privileged_boundary"]["rollback_policy"], "NONE")
        self.assertFalse(value["privileged_boundary"]["agent_sudo_allowed"])
        self.assertEqual(
            tuple(
                (item["category"], item["max_operations"])
                for item in value["capability_install"]["mutation_budget"]
            ),
            INSTALL_MUTATION_BUDGET,
        )
        self.assertTrue(value["capability_install"]["authorization_consumed_before_first_mutation"])
        self.assertFalse(value["capability_install"]["automatic_retry"])
        self.assertFalse(value["capability_install"]["automatic_cleanup"])
        self.assertFalse(value["capability_install"]["automatic_rollback"])

    def test_privileged_entrypoint_is_executable_and_issue_identity_only(self) -> None:
        relative = "ops/bin/rpi5-weathernext-private-host-privileged-install"
        tree = subprocess.run(
            ["git", "ls-tree", "HEAD", relative],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertTrue(tree.startswith("100755 blob "), tree)
        source = (ROOT / relative).read_text(encoding="utf-8")
        self.assertEqual(source.count("parser.add_argument("), 1)
        self.assertIn('parser.add_argument("--issue-number"', source)
        self.assertNotIn("--command", source)
        self.assertNotIn("--path", source)
        self.assertNotIn("--argv", source)
        self.assertNotIn("--environment", source)
        self.assertNotIn("--repository", source)
        self.assertNotIn("--source-sha", source)
        self.assertNotIn("--target", source)

    def test_source_introduces_no_generic_shell_package_or_service_authority(self) -> None:
        paths = (
            ROOT / "ops/lib/deploy_executor/weather_private_bigquery_host_installer.py",
            ROOT / "ops/lib/deploy_executor/weather_private_bigquery_host_installer_runtime.py",
            ROOT / "ops/bin/rpi5-weathernext-private-host-privileged-install",
        )
        text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotIn("shell=True", text)
        self.assertNotIn("/bin/sh", text)
        self.assertNotIn("/bin/bash", text)
        self.assertNotIn("/usr/bin/docker", text)
        self.assertNotIn("/usr/bin/systemctl", text)
        self.assertNotIn("pip install", text)
        self.assertNotIn("apt install", text)
        self.assertNotIn("GOOGLE_APPLICATION_CREDENTIALS", text)
        self.assertNotIn("HOME_LAT", text)
        self.assertNotIn("HOME_LON", text)
        self.assertNotIn("SELECT *", text.upper())


if __name__ == "__main__":
    unittest.main()
