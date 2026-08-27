from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.adapters import AdapterCatalog, AdapterError, OperationAdapter, prepare_operation
from deploy_executor.queue_normalizer import (
    QUEUE_REPOSITORY,
    QUEUE_FIELDS,
    QueueNormalizationError,
    normalize_ready_queue,
    parse_ready_queue,
)
from deploy_executor.registry import RegistryError, load_registry

FIXTURES = ROOT / "tests" / "fixtures" / "deploy_executor"
PRODUCTION_REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"


def load_issue() -> dict:
    return json.loads((FIXTURES / "queue_issue_ready_markup.json").read_text())


def load_registry_json() -> dict:
    return json.loads((FIXTURES / "operations_inert.json").read_text())


def write_registry(value: dict) -> Path:
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
    json.dump(value, handle)
    handle.close()
    return Path(handle.name)


class P4RegistryAndNormalizationTests(unittest.TestCase):
    def test_production_registry_is_empty_and_execution_disabled(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(registry.operations, ())

    def test_inert_fixture_registry_loads(self):
        registry = load_registry(FIXTURES / "operations_inert.json")
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        self.assertEqual(registry.operations[0].operation_id, "fixture.application-deploy.v1")

    def test_registry_rejects_execution_enablement(self):
        raw = load_registry_json()
        raw["execution_enabled"] = True
        with self.assertRaisesRegex(RegistryError, "P4_EXECUTION_FORBIDDEN"):
            load_registry(write_registry(raw))

    def test_registry_rejects_unknown_authority_field(self):
        raw = load_registry_json()
        raw["operations"][0]["command"] = "bash -c anything"
        with self.assertRaisesRegex(RegistryError, "REGISTRY_SCHEMA"):
            load_registry(write_registry(raw))

    def test_registry_rejects_duplicate_operation_id(self):
        raw = load_registry_json()
        raw["operations"].append(copy.deepcopy(raw["operations"][0]))
        with self.assertRaisesRegex(RegistryError, "duplicate operation_id"):
            load_registry(write_registry(raw))

    def test_registry_rejects_unsupported_rollback(self):
        raw = load_registry_json()
        raw["operations"][0]["rollback_policy"] = "AUTO_MAGIC"
        with self.assertRaisesRegex(RegistryError, "REGISTRY_POLICY"):
            load_registry(write_registry(raw))

    def test_registry_rejects_strict_operation_marked_ordinary(self):
        raw = load_registry_json()
        raw["operations"][0]["authorization_class"] = "STRICT"
        with self.assertRaisesRegex(RegistryError, "REGISTRY_POLICY"):
            load_registry(write_registry(raw))

    def test_ready_markup_parses_exact_machine_selectors(self):
        parsed = parse_ready_queue(load_issue(), repository_full_name=QUEUE_REPOSITORY)
        self.assertEqual(parsed.source_repository, "rozkalnsandris/example")
        self.assertEqual(parsed.source_sha, "0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(parsed.raw_target_alias, "example-production / web")
        self.assertEqual(parsed.repository_entrypoint, "ops/bin/example-deploy")
        self.assertEqual(parsed.deploy_class, "AUTO_DEPLOY_SAFE")
        self.assertEqual(len(dict(parsed.fields)), len(QUEUE_FIELDS))

    def test_non_ready_queue_fails_closed(self):
        issue = load_issue()
        issue["title"] = issue["title"].replace("[READY]", "[WAITING]")
        with self.assertRaisesRegex(QueueNormalizationError, "QUEUE_NOT_READY"):
            parse_ready_queue(issue, repository_full_name=QUEUE_REPOSITORY)

    def test_ready_without_exact_sha_fails_closed(self):
        issue = load_issue()
        issue["body"] = issue["body"].replace(
            "`0123456789abcdef0123456789abcdef01234567`", "`WAITING_MERGE`"
        )
        with self.assertRaisesRegex(QueueNormalizationError, "QUEUE_SHA"):
            parse_ready_queue(issue, repository_full_name=QUEUE_REPOSITORY)

    def test_missing_or_extra_queue_field_fails_closed(self):
        issue = load_issue()
        issue["body"] = issue["body"].replace(
            "- **dependencies_if_any:** none\n", "- **unknown_new_field:** value\n"
        )
        with self.assertRaisesRegex(QueueNormalizationError, "QUEUE_SCHEMA"):
            parse_ready_queue(issue, repository_full_name=QUEUE_REPOSITORY)

    def test_exact_registry_match_normalizes_to_p1_shape(self):
        registry = load_registry(FIXTURES / "operations_inert.json")
        normalized = normalize_ready_queue(
            load_issue(), repository_full_name=QUEUE_REPOSITORY, registry=registry
        )
        queue = normalized.as_protocol_queue()
        self.assertEqual(
            set(queue),
            {
                "repository", "issue_number", "state", "source_repository", "source_sha",
                "target_alias", "operation_id", "expected_baseline", "mutation_budget",
                "rollback_policy", "exclusions", "dependencies",
            },
        )
        self.assertEqual(queue["target_alias"], "example-production")
        self.assertEqual(queue["operation_id"], "fixture.application-deploy.v1")
        self.assertEqual(queue["expected_baseline"], {"kind": "resolver", "value": "fixture.baseline.v1"})
        self.assertEqual(queue["mutation_budget"], [{"category": "application-deploy", "max_operations": 1}])
        self.assertRegex(queue["dependencies"][-1], r"^queue-contract-sha256:[0-9a-f]{64}$")

    def test_unknown_operation_fails_closed(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        with self.assertRaisesRegex(QueueNormalizationError, "UNKNOWN_OPERATION"):
            normalize_ready_queue(load_issue(), repository_full_name=QUEUE_REPOSITORY, registry=registry)

    def test_queue_contract_edit_changes_binding_digest(self):
        registry = load_registry(FIXTURES / "operations_inert.json")
        first = normalize_ready_queue(load_issue(), repository_full_name=QUEUE_REPOSITORY, registry=registry)
        changed_issue = load_issue()
        changed_issue["body"] = changed_issue["body"].replace(
            "exact deployed SHA must equal approved source SHA",
            "exact deployed SHA must equal approved source SHA; additional public note",
        )
        second = normalize_ready_queue(changed_issue, repository_full_name=QUEUE_REPOSITORY, registry=registry)
        self.assertNotEqual(first.parsed.contract_sha256, second.parsed.contract_sha256)
        self.assertNotEqual(
            first.as_protocol_queue()["dependencies"][-1],
            second.as_protocol_queue()["dependencies"][-1],
        )

    def test_ambiguous_static_selectors_fail_closed(self):
        raw = load_registry_json()
        duplicate = copy.deepcopy(raw["operations"][0])
        duplicate["operation_id"] = "fixture.application-deploy-alt.v1"
        raw["operations"].append(duplicate)
        registry = load_registry(write_registry(raw))
        with self.assertRaisesRegex(QueueNormalizationError, "AMBIGUOUS_OPERATION"):
            normalize_ready_queue(load_issue(), repository_full_name=QUEUE_REPOSITORY, registry=registry)

    def test_free_form_contract_is_bound_not_interpreted_as_authority(self):
        registry = load_registry(FIXTURES / "operations_inert.json")
        issue = load_issue()
        issue["body"] = issue["body"].replace(
            "`application-deploy` maximum one operation",
            "`application-deploy` prose says maximum ninety-nine but registry remains authoritative",
        )
        normalized = normalize_ready_queue(issue, repository_full_name=QUEUE_REPOSITORY, registry=registry)
        self.assertEqual(
            normalized.as_protocol_queue()["mutation_budget"],
            [{"category": "application-deploy", "max_operations": 1}],
        )

    def test_p4_sources_have_no_generic_shell_execution_surface(self):
        for relative in (
            "ops/lib/deploy_executor/registry.py",
            "ops/lib/deploy_executor/queue_normalizer.py",
            "ops/lib/deploy_executor/adapters.py",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for forbidden in ("subprocess", "os.system", "shell=True", "bash -c", "sh -c", "eval("):
                self.assertNotIn(forbidden, text, f"{relative} contains forbidden execution surface {forbidden}")


@dataclass
class FakeAdapter:
    adapter_id: str = "fixture.inert.v1"

    def preflight(self, prepared):
        return {"result": "INERT_PREFLIGHT_PASS", "operation_id": prepared.operation_id}

    def apply(self, prepared):
        return {"result": "INERT_APPLY_NO_MUTATION", "mutation": False}

    def postconditions(self, prepared):
        return {"result": "INERT_POSTCONDITION_PASS"}


class P4AdapterInterfaceTests(unittest.TestCase):
    def test_fake_adapter_satisfies_interface_and_catalog_exact_match(self):
        fake = FakeAdapter()
        self.assertIsInstance(fake, OperationAdapter)
        catalog = AdapterCatalog((fake,))
        self.assertIs(catalog.require("fixture.inert.v1"), fake)
        with self.assertRaisesRegex(AdapterError, "unknown adapter_id"):
            catalog.require("unknown.adapter.v1")

    def test_prepare_operation_never_enables_execution_in_p4(self):
        registry = load_registry(FIXTURES / "operations_inert.json")
        normalized = normalize_ready_queue(
            load_issue(), repository_full_name=QUEUE_REPOSITORY, registry=registry
        )
        prepared = prepare_operation(normalized, execution_enabled=registry.execution_enabled)
        self.assertFalse(prepared.execution_enabled)
        self.assertEqual(prepared.adapter_id, "fixture.inert.v1")
        self.assertIn("exact-source-ci.v1", prepared.preflight_checks)
        self.assertIn("exact-deployed-sha.v1", prepared.postcondition_checks)


if __name__ == "__main__":
    unittest.main(verbosity=2)
