from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_runner_smoke_install import (
    HELPER_SHA256, INSTALL_TARGET_ALIAS, LIVE_GATE_ID, OPERATION_ID,
    OWNER_NUMERIC_ID, REGISTRATION_SHA256, SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID, SOURCE_SHA, InstallObservation,
)
from deploy_executor.hermes_deals_runner_smoke_install_consumer import (
    CanonicalRunnerSmokeInstallEvidence,
    RunnerSmokeInstallConsumerError,
)
from deploy_executor.hermes_deals_runner_smoke_install_execution_bridge import (
    execute_install_for_authorization,
    source_readiness,
)


def evidence() -> CanonicalRunnerSmokeInstallEvidence:
    return CanonicalRunnerSmokeInstallEvidence(
        authorization_issue_number=17,
        authorization_created_at="2026-09-14T08:00:00Z",
        github_server_time="2026-09-14T08:00:10Z",
        owner_numeric_id=OWNER_NUMERIC_ID,
        owner_type="User",
        app_authored=False,
        operation_id=OPERATION_ID,
        live_gate_id=LIVE_GATE_ID,
        target_alias=INSTALL_TARGET_ALIAS,
        source_repository=SOURCE_REPOSITORY,
        source_repository_id=SOURCE_REPOSITORY_ID,
        source_sha=SOURCE_SHA,
        rpi5_main_sha="1" * 40,
        rpi5_main_merged_reachable=True,
        rpi5_main_ci_success=True,
        hermes_source_merged_reachable=True,
        hermes_source_ci_success=True,
        helper_sha256=HELPER_SHA256,
        registration_sha256=REGISTRATION_SHA256,
        request_body_sha256="2" * 64,
        identical_body_refetch=True,
        ttl_valid=True,
        replay_available=True,
        live_authorized=True,
        rollback_policy="NONE",
    )


class Revalidator:
    def __init__(self, first=None, second=None, events=None):
        self.first = first or evidence()
        self.second = self.first if second is None else second
        self.calls = 0
        self.events = events if events is not None else []
    def revalidate(self, authorization_issue_number):
        self.calls += 1
        self.events.append(f"revalidate{self.calls}")
        return self.first if self.calls == 1 else self.second


class Consumer:
    def __init__(self, events): self.events = events
    def consume(self, *, authorization_issue_number, body_sha256):
        self.events.append("consume")


class Backend:
    def __init__(self, events, observed=None):
        self.events = events
        self.observed = observed or InstallObservation("EXACT", "EXACT", "EXACT")
    def observe(self): self.events.append("observe"); return self.observed
    def ensure_identity(self): self.events.append("ensure_identity")
    def install_helper(self): self.events.append("install_helper")
    def install_registration(self): self.events.append("install_registration")
    def verify_exact_state(self): self.events.append("verify_exact_state"); return InstallObservation("EXACT", "EXACT", "EXACT")


class BridgeTests(unittest.TestCase):
    def test_only_issue_number_is_authority_and_dependencies_are_keyword_only(self):
        sig = inspect.signature(execute_install_for_authorization)
        self.assertEqual(tuple(sig.parameters), ("authorization_issue_number", "canonical_revalidator", "authorization_consumer", "backend"))
        for name in ("canonical_revalidator", "authorization_consumer", "backend"):
            self.assertEqual(sig.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
        for prohibited in ("envelope", "command", "path", "argv", "environment", "source_sha", "target", "operation"):
            self.assertNotIn(prohibited, sig.parameters)

    def test_double_revalidation_is_immediately_before_fixed_apply(self):
        events = []
        rv = Revalidator(events=events)
        receipt = execute_install_for_authorization(17, canonical_revalidator=rv, authorization_consumer=Consumer(events), backend=Backend(events))
        self.assertEqual(receipt.result, "ALREADY_EXACT_NO_MUTATION")
        self.assertEqual(events, ["revalidate1", "revalidate2", "observe", "verify_exact_state"])

    def test_drift_fails_before_backend_or_consume(self):
        events = []
        first = evidence()
        rv = Revalidator(first, replace(first, request_body_sha256="3" * 64), events)
        with self.assertRaises(RunnerSmokeInstallConsumerError):
            execute_install_for_authorization(17, canonical_revalidator=rv, authorization_consumer=Consumer(events), backend=Backend(events))
        self.assertEqual(events, ["revalidate1", "revalidate2"])

    def test_mutating_plan_consumes_once_before_fixed_mutation(self):
        events = []
        backend = Backend(events, InstallObservation("ABSENT", "EXACT", "EXACT"))
        def ensure_identity():
            events.append("ensure_identity")
            backend.observed = InstallObservation("EXACT", "EXACT", "EXACT")
        backend.ensure_identity = ensure_identity
        receipt = execute_install_for_authorization(17, canonical_revalidator=Revalidator(events=events), authorization_consumer=Consumer(events), backend=backend)
        self.assertTrue(receipt.authorization_consumed)
        self.assertEqual(events, ["revalidate1", "revalidate2", "observe", "consume", "ensure_identity", "verify_exact_state"])

    def test_source_exposes_no_generic_execution_or_runtime_entrypoint(self):
        source = (ROOT / "ops/lib/deploy_executor/hermes_deals_runner_smoke_install_execution_bridge.py").read_text()
        for prohibited in ("subprocess", "os.system", "Popen", "shell=True", "sudo", "systemctl"):
            self.assertNotIn(prohibited, source)
        ready = source_readiness()
        self.assertTrue(ready["execution_bridge_implemented"])
        self.assertTrue(ready["canonical_revalidation_immediately_before_apply"])
        self.assertFalse(ready["prebuilt_live_envelope_allowed"])
        self.assertFalse(ready["external_entrypoint_enabled"])
        self.assertFalse(ready["runtime_activation_enabled"])
        self.assertFalse(ready["global_executor_execution_enabled"])
        self.assertFalse(ready["source_merge_authorizes_live"])


if __name__ == "__main__":
    unittest.main()
