from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.adapters import AdapterCatalog, AdapterError, prepare_operation
from deploy_executor.hermes_deals_netto_nonroot_preflight_v2_adapter import (
    ADAPTER_ID,
    BASELINE_RESOLVER_ID,
    HELPER_ARGUMENTS,
    HELPER_CAPABILITY,
    HELPER_EVIDENCE_SCHEMA,
    HELPER_REGISTRATION_SCHEMA,
    HELPER_SOURCE_BLOB,
    HELPER_SOURCE_PATH,
    MUTATION_BUDGET,
    N9_MANIFEST_SHA256,
    OPERATION_ID,
    REQUIRED_EXCLUSIONS,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    SOURCE_SHA,
    TARGET_ALIAS,
    HermesDealsNettoNonrootPreflightV2Adapter,
)
from deploy_executor.hermes_deals_netto_nonroot_preflight_v2_helper_launch import (
    CANARY_AUTHORIZED,
    EXTRA_GROUPS,
    FIXED_ARGV,
    FIXED_CWD,
    FIXED_ENV,
    HELPER_SHA256,
    HOST_WIRING_ENABLED,
    INSTALLED_HELPER_PATH,
    INTERPRETER,
    LAUNCH_ENABLED,
    PRODUCTION_MUTATION_STARTED,
    RUN_GID,
    RUN_UID,
    HermesDealsNettoNonrootPreflightV2LaunchError,
    InstalledHelperSnapshot,
    _validate_helper_snapshot,
    fixed_launch_spec,
    launch_fixed_helper,
    source_readiness as launcher_source_readiness,
)
from deploy_executor.queue_normalizer import (
    QUEUE_REPOSITORY,
    QueueNormalizationError,
    normalize_ready_queue,
)
from deploy_executor.registry import load_registry

PRODUCTION_REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"
QUEUE_FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "deploy_executor"
    / "queue_issue_hermes_netto_nonroot_preflight_v2_ready.json"
)
ADAPTER_SOURCE = (
    ROOT
    / "ops"
    / "lib"
    / "deploy_executor"
    / "hermes_deals_netto_nonroot_preflight_v2_adapter.py"
)
LAUNCHER_SOURCE = (
    ROOT
    / "ops"
    / "lib"
    / "deploy_executor"
    / "hermes_deals_netto_nonroot_preflight_v2_helper_launch.py"
)


def _queue() -> dict:
    return json.loads(QUEUE_FIXTURE.read_text(encoding="utf-8"))


def _prepared():
    registry = load_registry(PRODUCTION_REGISTRY)
    normalized = normalize_ready_queue(
        _queue(), repository_full_name=QUEUE_REPOSITORY, registry=registry
    )
    return prepare_operation(normalized)


class HermesNettoNonrootPreflightV2RegistryTests(unittest.TestCase):
    def test_operation_is_exact_strict_and_globally_disabled(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        self.assertFalse(registry.execution_enabled)
        operation = next(op for op in registry.operations if op.operation_id == OPERATION_ID)
        self.assertEqual(operation.source_repository, SOURCE_REPOSITORY)
        self.assertEqual(operation.target_alias, TARGET_ALIAS)
        self.assertEqual(operation.adapter_id, ADAPTER_ID)
        self.assertEqual(operation.authorization_class, "STRICT")
        self.assertFalse(operation.ordinary_live_all_eligible)
        self.assertEqual(operation.baseline.kind, "resolver")
        self.assertEqual(operation.baseline.resolver_id, BASELINE_RESOLVER_ID)
        self.assertEqual(operation.rollback_policy, "NONE")
        self.assertEqual(
            tuple((row.category, row.max_operations) for row in operation.mutation_budget),
            MUTATION_BUDGET,
        )

    def test_queue_normalizes_to_exact_merged_helper_source(self):
        prepared = _prepared()
        self.assertFalse(prepared.execution_enabled)
        self.assertEqual(prepared.operation_id, OPERATION_ID)
        self.assertEqual(prepared.source_sha, SOURCE_SHA)
        self.assertEqual(prepared.expected_baseline_kind, "resolver")
        self.assertEqual(prepared.expected_baseline_value, BASELINE_RESOLVER_ID)
        self.assertIn(f"source-repository-id:{SOURCE_REPOSITORY_ID}", prepared.dependencies)
        self.assertIn(f"pull-helper-source-path:{HELPER_SOURCE_PATH}", prepared.dependencies)
        self.assertIn(f"pull-helper-source-blob:{HELPER_SOURCE_BLOB}", prepared.dependencies)
        self.assertIn(f"pull-helper-capability:{HELPER_CAPABILITY}", prepared.dependencies)
        self.assertIn(
            f"pull-helper-registration-schema:{HELPER_REGISTRATION_SCHEMA}",
            prepared.dependencies,
        )
        self.assertIn(
            f"pull-helper-evidence-schema:{HELPER_EVIDENCE_SCHEMA}",
            prepared.dependencies,
        )
        self.assertIn(f"n9-manifest-sha256:{N9_MANIFEST_SHA256}", prepared.dependencies)

    def test_unreviewed_entrypoint_cannot_select_operation(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        issue = _queue()
        issue["body"] = issue["body"].replace(
            "`tools/runner/netto_missing_normal_price_nonroot_preflight_v2.py`",
            "`/tmp/attacker-selected.py`",
        )
        with self.assertRaisesRegex(QueueNormalizationError, "UNKNOWN_OPERATION"):
            normalize_ready_queue(
                issue, repository_full_name=QUEUE_REPOSITORY, registry=registry
            )


class HermesNettoNonrootPreflightV2AdapterTests(unittest.TestCase):
    def test_preflight_binds_exact_reviewed_helper_contract(self):
        adapter = HermesDealsNettoNonrootPreflightV2Adapter()
        self.assertIs(AdapterCatalog((adapter,)).require(ADAPTER_ID), adapter)
        preflight = adapter.preflight(_prepared())
        self.assertEqual(
            preflight["result"],
            "HERMES_NETTO_NONROOT_PREFLIGHT_V2_SOURCE_CONTRACT_PASS",
        )
        self.assertEqual(preflight["source_sha"], SOURCE_SHA)
        self.assertEqual(preflight["helper_source_blob"], HELPER_SOURCE_BLOB)
        self.assertEqual(preflight["helper_arguments"], HELPER_ARGUMENTS)
        self.assertTrue(preflight["read_only"])
        self.assertTrue(preflight["non_root_required"])
        self.assertFalse(preflight["docker_authority_allowed"])
        self.assertFalse(preflight["parser_execution_allowed"])
        self.assertFalse(preflight["database_write_allowed"])
        self.assertFalse(preflight["review_write_allowed"])
        self.assertFalse(preflight["deployment_allowed"])
        self.assertFalse(preflight["execution_enabled"])
        self.assertFalse(preflight["privileged_dispatch_ready"])
        self.assertTrue(preflight["requires_separate_live_authorization"])
        for forbidden in ("command", "argv", "environment", "sudo", "docker_socket"):
            self.assertNotIn(forbidden, preflight)

    def test_apply_is_always_source_disabled(self):
        with self.assertRaisesRegex(AdapterError, "execution-disabled"):
            HermesDealsNettoNonrootPreflightV2Adapter().apply(_prepared())

    def test_adapter_rejects_source_baseline_budget_and_exclusion_drift(self):
        prepared = _prepared()
        cases = (
            ("source_repository", "attacker/repo", "source repository"),
            ("source_sha", "a" * 40, "source SHA"),
            ("target_alias", "attacker-target", "target alias"),
            ("expected_baseline_kind", "queue_exact", "baseline kind"),
            ("expected_baseline_value", "attacker-resolver", "baseline resolver"),
            (
                "mutation_budget",
                (("hermes-deals.read-only-netto-nonroot-preflight-v2-invocation", 2),),
                "budget",
            ),
        )
        for field, value, pattern in cases:
            bad = copy.copy(prepared)
            object.__setattr__(bad, field, value)
            with self.subTest(field=field):
                with self.assertRaisesRegex(AdapterError, pattern):
                    HermesDealsNettoNonrootPreflightV2Adapter().preflight(bad)

        bad = copy.copy(prepared)
        excluded = next(iter(REQUIRED_EXCLUSIONS))
        object.__setattr__(
            bad,
            "exclusions",
            tuple(item for item in prepared.exclusions if item != excluded),
        )
        with self.assertRaisesRegex(AdapterError, "exclusions"):
            HermesDealsNettoNonrootPreflightV2Adapter().preflight(bad)

    def test_adapter_rejects_missing_helper_dependency(self):
        prepared = _prepared()
        dependency = f"pull-helper-source-blob:{HELPER_SOURCE_BLOB}"
        bad = copy.copy(prepared)
        object.__setattr__(
            bad,
            "dependencies",
            tuple(item for item in prepared.dependencies if item != dependency),
        )
        with self.assertRaisesRegex(AdapterError, "dependency mismatch"):
            HermesDealsNettoNonrootPreflightV2Adapter().preflight(bad)

    def test_postconditions_keep_all_mutation_flags_false(self):
        post = HermesDealsNettoNonrootPreflightV2Adapter().postconditions(_prepared())
        self.assertEqual(post["registered_source_sha"], SOURCE_SHA)
        for field in (
            "sudo_used",
            "file_contents_exported",
            "parser_executed",
            "database_write_performed",
            "review_write_performed",
            "deployment_performed",
            "runner_registration_changed",
            "automatic_retry_cleanup_rollback",
            "execution_enabled",
        ):
            self.assertFalse(post[field])

    def test_adapter_source_has_no_execution_bridge(self):
        source = ADAPTER_SOURCE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "import subprocess",
            "os.system",
            "shell=true",
            "bash -c",
            "sh -c",
            "eval(",
            "requests",
            "urllib",
            "socket.",
        ):
            self.assertNotIn(forbidden, source)


class HermesNettoNonrootPreflightV2FixedLauncherTests(unittest.TestCase):
    def _valid_snapshot(self) -> InstalledHelperSnapshot:
        return InstalledHelperSnapshot(
            regular=True,
            symlink=False,
            link_count=1,
            uid=0,
            gid=0,
            mode=0o555,
            sha256=HELPER_SHA256,
            descriptor_matches_path=True,
        )

    def test_launcher_readiness_is_fixed_and_source_disabled(self):
        readiness = launcher_source_readiness()
        spec = fixed_launch_spec()
        self.assertTrue(readiness["launch_implemented"])
        self.assertFalse(LAUNCH_ENABLED)
        self.assertFalse(HOST_WIRING_ENABLED)
        self.assertFalse(CANARY_AUTHORIZED)
        self.assertFalse(PRODUCTION_MUTATION_STARTED)
        self.assertFalse(readiness["launch_enabled"])
        self.assertFalse(readiness["host_wiring_enabled"])
        self.assertFalse(readiness["canary_authorized"])
        self.assertFalse(readiness["production_mutation_started"])
        self.assertEqual(INTERPRETER, "/usr/bin/python3")
        self.assertEqual(spec.argv, FIXED_ARGV)
        self.assertEqual(
            spec.argv,
            (INTERPRETER, INSTALLED_HELPER_PATH, SOURCE_SHA),
        )
        self.assertEqual(spec.cwd, FIXED_CWD)
        self.assertEqual(dict(spec.environment), dict(FIXED_ENV))
        self.assertEqual(spec.user, RUN_UID)
        self.assertEqual(spec.group, RUN_GID)
        self.assertEqual((RUN_UID, RUN_GID), (1000, 1000))
        self.assertEqual(spec.extra_groups, EXTRA_GROUPS)
        self.assertEqual(spec.extra_groups, ())
        self.assertFalse(spec.shell)
        self.assertFalse(readiness["caller_process_authority"])

    def test_helper_provenance_contract_rejects_any_metadata_or_hash_drift(self):
        valid = self._valid_snapshot()
        _validate_helper_snapshot(valid)
        cases = (
            replace(valid, regular=False),
            replace(valid, symlink=True),
            replace(valid, link_count=2),
            replace(valid, uid=1000),
            replace(valid, gid=1000),
            replace(valid, mode=0o755),
            replace(valid, sha256="0" * 64),
            replace(valid, descriptor_matches_path=False),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(HermesDealsNettoNonrootPreflightV2LaunchError):
                    _validate_helper_snapshot(candidate)

    def test_launch_cannot_reach_subprocess_while_source_disabled(self):
        with (
            mock.patch(
                "deploy_executor.hermes_deals_netto_nonroot_preflight_v2_helper_launch.validate_installed_helper"
            ) as validate,
            mock.patch(
                "deploy_executor.hermes_deals_netto_nonroot_preflight_v2_helper_launch.subprocess.run"
            ) as run,
        ):
            with self.assertRaisesRegex(
                HermesDealsNettoNonrootPreflightV2LaunchError,
                "source-disabled",
            ):
                launch_fixed_helper()
        validate.assert_not_called()
        run.assert_not_called()

    def test_launcher_source_uses_fixed_posix_identity_drop_without_generic_bridge(self):
        source = LAUNCHER_SOURCE.read_text(encoding="utf-8").lower()
        for required in (
            "user=run_uid",
            "group=run_gid",
            "extra_groups=extra_groups",
            "shell=false",
            "close_fds=true",
            "os.lstat(installed_helper_path)",
            "os.o_nofollow",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "sudo",
            "systemctl",
            "docker.sock",
            "docker ",
            "requests",
            "urllib",
            "socket.",
            "os.system",
            "shell=true",
            "bash -c",
            "sh -c",
            "eval(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
