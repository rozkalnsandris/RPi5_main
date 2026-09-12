import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/lib/deploy_executor/hermes_deals_runner_smoke_install.py"
SPEC = importlib.util.spec_from_file_location("runner_smoke_install", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
import sys
sys.modules[SPEC.name] = mod
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)

sys.path.insert(0, str(ROOT / "ops" / "lib"))
from deploy_executor.registry import load_registry


def live_envelope(**overrides):
    value = {
        "schema": mod.LIVE_ENVELOPE_SCHEMA,
        "authorization_issue_number": 9001,
        "owner_numeric_id": mod.OWNER_NUMERIC_ID,
        "operation_id": mod.OPERATION_ID,
        "live_gate_id": mod.LIVE_GATE_ID,
        "target_alias": mod.INSTALL_TARGET_ALIAS,
        "source_repository": mod.SOURCE_REPOSITORY,
        "source_repository_id": mod.SOURCE_REPOSITORY_ID,
        "source_sha": mod.SOURCE_SHA,
        "rpi5_main_sha": "1" * 40,
        "rpi5_main_merged_reachable": True,
        "rpi5_main_ci_success": True,
        "hermes_source_merged_reachable": True,
        "hermes_source_ci_success": True,
        "helper_sha256": mod.HELPER_SHA256,
        "registration_sha256": mod.REGISTRATION_SHA256,
        "request_body_sha256": "2" * 64,
        "identical_body_refetch": True,
        "ttl_valid": True,
        "replay_available": True,
        "live_authorized": True,
        "rollback_policy": "NONE",
    }
    value.update(overrides)
    return value


class Consumer:
    def __init__(self):
        self.calls = []
    def consume(self, *, authorization_issue_number, body_sha256):
        self.calls.append((authorization_issue_number, body_sha256))


class Backend:
    def __init__(self, observed):
        self.observed = observed
        self.calls = []
    def observe(self):
        self.calls.append("observe")
        return self.observed
    def ensure_identity(self):
        self.calls.append("ensure_identity")
        self.observed = mod.InstallObservation(
            "EXACT", self.observed.helper_destination_state, self.observed.registration_destination_state
        )
    def install_helper(self):
        self.calls.append("install_helper")
        self.observed = mod.InstallObservation(
            self.observed.execution_identity_state, "EXACT", self.observed.registration_destination_state
        )
    def install_registration(self):
        self.calls.append("install_registration")
        self.observed = mod.InstallObservation(
            self.observed.execution_identity_state, self.observed.helper_destination_state, "EXACT"
        )
    def verify_exact_state(self):
        self.calls.append("verify_exact_state")
        if self.observed != mod.InstallObservation("EXACT", "EXACT", "EXACT"):
            raise mod.RunnerSmokeInstallError("not exact")
        return self.observed


class FailingBackend(Backend):
    def install_helper(self):
        self.calls.append("install_helper")
        raise mod.RunnerSmokeInstallError("simulated post-consume failure")


class RunnerSmokeInstallTests(unittest.TestCase):
    def test_source_readiness_is_strict_and_inactive(self):
        ready = mod.source_readiness()
        self.assertTrue(ready["apply_implemented"])
        self.assertFalse(ready["external_apply_entrypoint_enabled"])
        self.assertFalse(ready["global_executor_execution_enabled"])
        self.assertFalse(ready["runtime_live_authority"])
        self.assertEqual(ready["caller_authority"], ("authorization_issue_number",))
        for field in (
            "caller_command_allowed", "caller_path_allowed", "caller_argv_allowed",
            "caller_environment_allowed", "generic_shell_allowed", "generic_sudo_allowed",
            "helper_invocation_allowed", "automatic_retry_after_mutation_start",
            "automatic_cleanup_after_mutation_start", "automatic_rollback_after_mutation_start",
            "alternate_mutation_path_after_mutation_start",
        ):
            self.assertFalse(ready[field])

    def test_plan_allows_only_absent_or_exact(self):
        evidence = {
            "rpi5_main_sha": "1" * 40,
            "rpi5_main_merged_reachable": True,
            "rpi5_main_ci_success": True,
            "hermes_source_sha": mod.SOURCE_SHA,
            "hermes_source_merged_reachable": True,
            "hermes_source_ci_success": True,
            "execution_identity_state": "ABSENT",
            "helper_destination_state": "EXACT",
            "registration_destination_state": "ABSENT",
        }
        plan = mod.build_plan(evidence)
        self.assertEqual(
            plan.mutations_required,
            ("create_exact_system_group", "create_exact_system_user", "install_exact_registration"),
        )
        self.assertFalse(plan.host_write_allowed)
        self.assertFalse(plan.live_authority_consumed)
        with self.assertRaises(mod.RunnerSmokeInstallError):
            mod.build_plan({**evidence, "helper_destination_state": "CONFLICT"})

    def test_apply_consumes_once_before_first_fixed_mutation(self):
        consumer = Consumer()
        backend = Backend(mod.InstallObservation("ABSENT", "ABSENT", "ABSENT"))
        receipt = mod.apply_install(live_envelope(), authorization_consumer=consumer, backend=backend)
        self.assertEqual(len(consumer.calls), 1)
        self.assertEqual(
            backend.calls,
            ["observe", "ensure_identity", "install_helper", "install_registration", "verify_exact_state"],
        )
        self.assertEqual(receipt.result, "INSTALLED_EXACT")
        self.assertTrue(receipt.authorization_consumed)
        self.assertTrue(receipt.mutations_started)
        self.assertFalse(receipt.helper_invoked)

    def test_exact_state_is_idempotent_without_consuming_authority(self):
        consumer = Consumer()
        backend = Backend(mod.InstallObservation("EXACT", "EXACT", "EXACT"))
        receipt = mod.apply_install(live_envelope(), authorization_consumer=consumer, backend=backend)
        self.assertEqual(consumer.calls, [])
        self.assertEqual(backend.calls, ["observe", "verify_exact_state"])
        self.assertEqual(receipt.result, "ALREADY_EXACT_NO_MUTATION")
        self.assertFalse(receipt.authorization_consumed)

    def test_post_consume_failure_has_no_retry_cleanup_or_rollback(self):
        consumer = Consumer()
        backend = FailingBackend(mod.InstallObservation("EXACT", "ABSENT", "EXACT"))
        with self.assertRaises(mod.RunnerSmokeInstallError):
            mod.apply_install(live_envelope(), authorization_consumer=consumer, backend=backend)
        self.assertEqual(len(consumer.calls), 1)
        self.assertEqual(backend.calls, ["observe", "install_helper"])

    def test_live_envelope_fails_closed_on_scope_drift(self):
        for changed in (
            {"operation_id": "wrong"},
            {"target_alias": "wrong"},
            {"source_sha": "3" * 40},
            {"owner_numeric_id": 1},
            {"live_authorized": False},
            {"rollback_policy": "BUILTIN_TRANSACTIONAL_V1"},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(mod.RunnerSmokeInstallError):
                    mod.validate_live_envelope(live_envelope(**changed))

    def test_identity_rejects_root_or_docker_primary_gid_aliases(self):
        account = type("Account", (), {
            "pw_uid": 1234, "pw_gid": 2000, "pw_dir": mod.EXECUTION_HOME, "pw_shell": mod.EXECUTION_SHELL
        })()
        dedicated = type("Group", (), {"gr_gid": 2000})()
        docker = type("Group", (), {"gr_gid": 2000})()
        with mock.patch.object(mod.pwd, "getpwnam", return_value=account), \
             mock.patch.object(mod.grp, "getgrnam", side_effect=lambda name: dedicated if name == mod.EXECUTION_GROUP else docker), \
             mock.patch.object(mod.grp, "getgrall", return_value=[]):
            self.assertEqual(mod.PosixFixedInstallBackend._identity_state(), "CONFLICT")

        root_gid_account = type("Account", (), {
            "pw_uid": 1234, "pw_gid": 0, "pw_dir": mod.EXECUTION_HOME, "pw_shell": mod.EXECUTION_SHELL
        })()
        root_gid_group = type("Group", (), {"gr_gid": 0})()
        with mock.patch.object(mod.pwd, "getpwnam", return_value=root_gid_account), \
             mock.patch.object(mod.grp, "getgrnam", return_value=root_gid_group):
            self.assertEqual(mod.PosixFixedInstallBackend._identity_state(), "CONFLICT")

    def test_helper_source_enforces_exact_nonroot_primary_group_and_docker_gid(self):
        helper = (ROOT / "ops/bin/hermes-deals-runner-smoke-audit").read_text()
        self.assertIn('EXPECTED_PRIMARY_GROUP = "hermes-deals-audit-canary"', helper)
        self.assertIn('primary_group.gr_gid == 0', helper)
        self.assertIn('entry.pw_gid == docker.gr_gid', helper)

    def test_fixed_artifact_hashes_match_source(self):
        helper = ROOT / "ops/bin/hermes-deals-runner-smoke-audit"
        registration = ROOT / "ops/deploy/hermes-deals-runner-smoke-audit-registration.json"
        import hashlib
        self.assertEqual(hashlib.sha256(helper.read_bytes()).hexdigest(), mod.HELPER_SHA256)
        self.assertEqual(hashlib.sha256(registration.read_bytes()).hexdigest(), mod.REGISTRATION_SHA256)
        reg = json.loads(registration.read_text())
        self.assertEqual(reg["helper_sha256"], mod.HELPER_SHA256)
        self.assertEqual(reg["execution_identity"]["account"], mod.EXECUTION_ACCOUNT)
        self.assertFalse(reg["execution_identity"]["root"])
        self.assertFalse(reg["execution_identity"]["docker_group"])
        self.assertEqual(reg["execution_identity"]["supplementary_groups"], [])

    def test_static_operation_is_strict_and_globally_disabled(self):
        registry = load_registry(ROOT / "ops/deploy/executor-operations.json")
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 7)
        op = {item.operation_id: item for item in registry.operations}[mod.OPERATION_ID]
        self.assertEqual(op.authorization_class, "STRICT")
        self.assertFalse(op.ordinary_live_all_eligible)
        self.assertEqual(op.target_alias, mod.CANARY_TARGET_ALIAS)
        self.assertEqual(op.queue_match.repository_entrypoint, ".github/workflows/rpi5-audit-command.yml")
        self.assertEqual(op.baseline.resolver_id, "hermes-deals.runner-smoke-registration.v2")
        self.assertEqual(op.rollback_policy, "NONE")

    def test_helper_output_is_not_canonical_canary_receipt(self):
        contract = json.loads((ROOT / "ops/contracts/hermes-deals-runner-smoke-install-v2.json").read_text())
        output = contract["helper_output"]
        self.assertEqual(output["schema"], "rozkalns.hermes-deals.runner-smoke-helper-output.v2")
        self.assertFalse(output["authorization_metadata_in_helper_output"])
        self.assertTrue(output["canonical_receipt_composed_by_future_live_wrapper"])
        self.assertFalse(output["synthetic_pass_allowed"])

    def test_successor_contract_preserves_predecessor_historical_truth(self):
        contract = json.loads((ROOT / "ops/contracts/hermes-deals-runner-smoke-install-v2.json").read_text())
        self.assertEqual(contract["implementation_issue"], 476)
        self.assertFalse(contract["predecessor"]["historical_apply_entrypoint_present"])
        self.assertEqual(contract["apply"]["rollback_policy"], "NONE")
        self.assertFalse(contract["apply"]["external_entrypoint_enabled"])
        self.assertFalse(contract["handoff"]["source_merge_authorizes_live"])
        self.assertFalse(contract["handoff"]["ready_queue_created"])
        self.assertFalse(contract["handoff"]["live_auth_created"])


if __name__ == "__main__":
    unittest.main()
