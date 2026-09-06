from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/install-hermes-deals-origin-broker-evidence-write-recovery.py"
spec = importlib.util.spec_from_file_location("hermes_evidence_write_recovery", SCRIPT)
assert spec is not None and spec.loader is not None
recovery = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = recovery
spec.loader.exec_module(recovery)


def completed(returncode: int = 0, stdout: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(("test",), returncode, stdout=stdout, stderr=b"")


class HermesOriginBrokerEvidenceWriteRecoveryTests(unittest.TestCase):
    def test_mutation_surface_is_exact_two_replacements(self) -> None:
        self.assertEqual(len(recovery.REPLACE_TARGETS), 2)
        self.assertEqual(len(recovery.CREATE_TARGETS), 0)
        self.assertEqual(len(recovery.PREREQUISITES), 25)
        self.assertEqual(
            {t.source_path for t in recovery.REPLACE_TARGETS},
            {
                "ops/lib/deploy_executor/hermes_deals_origin_runtime_adapters.py",
                "ops/systemd/rozkalns-hermes-deals-origin-broker@.service",
            },
        )
        self.assertEqual(
            recovery.SYSTEMCTL_MUTATIONS,
            (("stop", recovery.SOCKET_UNIT), ("daemon-reload",), ("start", recovery.SOCKET_UNIT)),
        )

    def test_service_write_authority_is_exact_replay_plus_machine_evidence_root(self) -> None:
        unit = (ROOT / "ops/systemd/rozkalns-hermes-deals-origin-broker@.service").read_text()
        self.assertIn("ProtectSystem=strict\n", unit)
        write_lines = [line for line in unit.splitlines() if line.startswith("ReadWritePaths=")]
        self.assertEqual(
            write_lines,
            ["ReadWritePaths=/var/lib/rozkalns-deploy-executor-p9 /var/lib/hermes-deals-audits/origin-path-audit/evidence/rpi5"],
        )
        self.assertNotIn("ReadWritePaths=/var/lib\n", unit)
        self.assertNotIn("ReadWritePaths=/var/lib/hermes-deals-audits\n", unit)

    def test_runtime_adapter_binds_new_service_blob(self) -> None:
        service = ROOT / "ops/systemd/rozkalns-hermes-deals-origin-broker@.service"
        expected = subprocess.check_output(("git", "hash-object", str(service.relative_to(ROOT))), cwd=ROOT, text=True).strip()
        source = (ROOT / "ops/lib/deploy_executor/hermes_deals_origin_runtime_adapters.py").read_text()
        self.assertIn(f"BROKER_SERVICE_UNIT_GIT_BLOB = '{expected}'", source)
        self.assertEqual(expected, "2f4874323a92610d4d91df719a97688bc880fc48")

    def test_fixed_evidence_path_is_machine_specific(self) -> None:
        self.assertEqual(str(recovery.EVIDENCE_ROOT), "/var/lib/hermes-deals-audits/origin-path-audit/evidence")
        self.assertEqual(str(recovery.EVIDENCE_MACHINE_ROOT), "/var/lib/hermes-deals-audits/origin-path-audit/evidence/rpi5")
        self.assertEqual(recovery.EVIDENCE_MACHINE_ROOT.parent, recovery.EVIDENCE_ROOT)

    def test_systemctl_mutation_rejects_non_allowlisted_action(self) -> None:
        state = recovery._new_state()
        with self.assertRaises(recovery.UpgradeError):
            recovery._systemctl_mutation(state, "restart", recovery.SOCKET_UNIT)
        self.assertFalse(state["mutation_started"])

    def test_apply_order_is_double_preflight_stop_replace_reload_start(self) -> None:
        state = recovery._new_state()
        events: list[str] = []
        reviewed = {item.source_path: b"reviewed" for item in recovery.REPLACE_TARGETS}
        active_checks = iter((completed(3, b"inactive\n"), completed(0, b"active\n")))

        def fake_preflight(_sha: str):
            events.append("preflight")
            return reviewed

        def fake_mutation(inner_state, *args):
            inner_state["mutation_started"] = True
            events.append("systemctl:" + " ".join(args))

        def fake_query(*args):
            if args == ("is-active", recovery.SOCKET_UNIT):
                return next(active_checks)
            if args[0] == "list-units":
                return completed(0, b"")
            if args == ("is-enabled", recovery.SOCKET_UNIT):
                return completed(0, b"enabled\n")
            raise AssertionError(args)

        def fake_replace(target, _data, inner_state):
            events.append("replace:" + target.source_path)
            inner_state["files_replaced"] = int(inner_state["files_replaced"]) + 1

        with mock.patch.object(recovery, "_preflight", side_effect=fake_preflight), \
             mock.patch.object(recovery, "_systemctl_mutation", side_effect=fake_mutation), \
             mock.patch.object(recovery, "_systemctl_query", side_effect=fake_query), \
             mock.patch.object(recovery, "_replace_target", side_effect=fake_replace), \
             mock.patch.object(recovery, "_read_exact_file", return_value=None):
            value = json.loads(recovery.apply("a" * 40, state))

        self.assertEqual(events[:3], ["preflight", "preflight", f"systemctl:stop {recovery.SOCKET_UNIT}"])
        self.assertEqual(sum(event.startswith("replace:") for event in events), 2)
        self.assertLess(events.index(f"systemctl:stop {recovery.SOCKET_UNIT}"), events.index("systemctl:daemon-reload"))
        self.assertLess(events.index("systemctl:daemon-reload"), events.index(f"systemctl:start {recovery.SOCKET_UNIT}"))
        self.assertEqual(value["result"], "HERMES_ORIGIN_BROKER_EVIDENCE_WRITE_RECOVERY_PASS")
        self.assertEqual(value["files_replaced"], 2)
        self.assertEqual(value["files_created"], 0)
        self.assertEqual(value["evidence_write_path"], str(recovery.EVIDENCE_MACHINE_ROOT))
        self.assertFalse(value["replay_consume_invoked"])
        self.assertFalse(value["helper_executed"])

    def test_post_stop_failure_has_no_retry_rollback_or_restart(self) -> None:
        state = recovery._new_state()
        reviewed = {item.source_path: b"reviewed" for item in recovery.REPLACE_TARGETS}
        mutations: list[tuple[str, ...]] = []

        def fake_mutation(inner_state, *args):
            inner_state["mutation_started"] = True
            mutations.append(tuple(args))

        def fake_query(*args):
            if args == ("is-active", recovery.SOCKET_UNIT):
                return completed(3, b"inactive\n")
            if args[0] == "list-units":
                return completed(0, b"")
            raise AssertionError(args)

        with mock.patch.object(recovery, "_preflight", return_value=reviewed), \
             mock.patch.object(recovery, "_systemctl_mutation", side_effect=fake_mutation), \
             mock.patch.object(recovery, "_systemctl_query", side_effect=fake_query), \
             mock.patch.object(recovery, "_replace_target", side_effect=recovery.UpgradeError("simulated failure")):
            with self.assertRaises(recovery.UpgradeError):
                recovery.apply("a" * 40, state)

        self.assertEqual(mutations, [("stop", recovery.SOCKET_UNIT)])
        self.assertTrue(state["socket_stopped"])
        self.assertFalse(state["daemon_reload_attempted"])
        self.assertFalse(state["socket_start_attempted"])

    def test_machine_contract_binds_operator_and_nonreusable_canary(self) -> None:
        contract = json.loads((ROOT / "ops/deploy/hermes-deals-origin-broker-evidence-write-recovery.json").read_text())
        operator_blob = subprocess.check_output(("git", "hash-object", str(SCRIPT.relative_to(ROOT))), cwd=ROOT, text=True).strip()
        self.assertEqual(contract["operator"]["source_blob"], operator_blob)
        self.assertEqual(
            [(r["source"], r["target"], r["old_blob"], r["new_blob"], r["mode"]) for r in contract["replace_targets"]],
            [(t.source_path, str(t.target_path), t.old_blob, t.new_blob, f"{t.mode:04o}") for t in recovery.REPLACE_TARGETS],
        )
        self.assertEqual(contract["runtime_design"]["service_write_paths_exact"], [str(recovery.REPLAY_STATE_DIR), str(recovery.EVIDENCE_MACHINE_ROOT)])
        self.assertTrue(contract["failed_canary"]["durable_replay_consumed"])
        self.assertTrue(contract["failed_canary"]["authorization_reuse_forbidden"])
        self.assertFalse(contract["failed_canary"]["retry_authorized"])
        self.assertEqual(contract["failed_canary"]["queue_issue"], 30)
        self.assertEqual(contract["failed_canary"]["authorization_issue"], 9)
        for key, value in contract["source_gate_state"].items():
            if isinstance(value, bool):
                self.assertFalse(value, key)

        manifest = json.loads((ROOT / "ops/deploy/hermes-deals-origin-broker-installation.json").read_text())
        source = manifest["broker_evidence_write_recovery_source"]
        self.assertEqual(source["contract"], "ops/deploy/hermes-deals-origin-broker-evidence-write-recovery.json")
        self.assertEqual(source["replace_target_count"], 2)
        self.assertEqual(source["shared_prerequisite_count"], 25)
        self.assertFalse(source["failed_canary_retry_authorized"])
        self.assertFalse(source["recovery_applied"])
        self.assertFalse(source["live_recovery_eligible"])

        marker = "PHASE4_CURRENT_WORK_ITEM=HERMES_ORIGIN_BROKER_EVIDENCE_WRITE_PATH_RECOVERY"
        for name in (
            "docs/HERMES_DEALS_ORIGIN_DISPATCH_READINESS.md",
            "docs/AUTOMATION_MASTER_PLAN.md",
            "docs/HERMES_DEALS_ORIGIN_PULL_CANARY_SOURCE.md",
        ):
            text = (ROOT / name).read_text()
            self.assertIn(marker, text, name)
            self.assertIn("Queue #30 and LIVE-AUTH #9 must never be reused.", text, name)

    def test_receipt_never_claims_audit_or_production_mutation(self) -> None:
        value = json.loads(recovery._receipt("TEST", "a" * 40, recovery._new_state()))
        for key in ("credential_content_read", "github_api_request", "replay_consume_invoked", "helper_executed", "genuine_audit_authorized", "production_mutation_started", "automatic_retry", "automatic_rollback", "automatic_cleanup"):
            self.assertFalse(value[key], key)


if __name__ == "__main__":
    unittest.main()
