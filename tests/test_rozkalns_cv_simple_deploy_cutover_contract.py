#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops/deploy/rozkalns-cv-simple-deploy-cutover-v1.json"
ACTIVATION_REGISTRY_PATH = ROOT / "ops/deploy/baselines/simple-deploy-targets-weather-cv-v1.json"
TARGET_REGISTRY_PATH = ROOT / "ops/deploy/simple-deploy-targets-v1.json"
EXECUTOR_REGISTRY_PATH = ROOT / "ops/deploy/executor-operations.json"
COMPOSE_PATH = ROOT / "ops/deploy/simple-deploy-compose/rozkalns-cv.yml"

TARGET_ALIAS = "rozkalns-cv-rpi5"
CANDIDATE_SOURCE_SHA = "645717e63596a6ece415d9f4ef69367b9e6ecafc"
CANDIDATE_DIGEST = "sha256:bc6cb2ab3c0e944db49b6c403212802d5289eabaf77db4dd30082856a9fdaadc"
LEGACY_SOURCE_SHA = "4986a6d80460bd6d7681c70e09e61a15e31007f4"
COMPOSE_SHA = "be7f021c9d64192905c908bcbb127dbc7ec1c2514d898f05cbf8de4c44ffa4a2"

MODULE_PATH = ROOT / "ops/lib/deploy_executor/simple_deploy_v1.py"
spec = importlib.util.spec_from_file_location("simple_deploy_v1_cv_cutover", MODULE_PATH)
assert spec and spec.loader
sd = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sd
spec.loader.exec_module(sd)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def by(items, key, value):
    return next(item for item in items if item[key] == value)


class RozkalnsCvSimpleDeployCutoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load(CONTRACT_PATH)

    def test_contract_is_strict_source_only_one_time_and_fail_closed(self) -> None:
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.rozkalns-cv-simple-deploy-cutover.v1",
        )
        self.assertEqual(self.contract["issue"], 802)
        self.assertEqual(
            self.contract["operation_id"],
            "rpi5-main.rozkalns-cv-simple-deploy-cutover.v1",
        )
        self.assertFalse(self.contract["execution_enabled"])
        self.assertEqual(self.contract["target_alias"], TARGET_ALIAS)
        self.assertEqual(self.contract["authorization_class"], "STRICT")
        self.assertTrue(self.contract["one_time"])
        self.assertEqual(
            self.contract["source_only_state"],
            {
                "live_authorized": False,
                "runtime_mutation_permitted_by_this_file": False,
                "protected_prerequisite_materialization_authorized": False,
                "merge_authorized": False,
            },
        )
        self.assertTrue(self.contract["failure_semantics"]["fail_closed"])
        for key in (
            "automatic_retry",
            "automatic_cleanup",
            "automatic_rollback",
            "alternate_mutation_path",
        ):
            self.assertFalse(self.contract["failure_semantics"][key], key)
        self.assertTrue(
            self.contract["failure_semantics"][
                "generic_timer_remains_stopped_on_post_mutation_failure"
            ]
        )

    def test_candidate_release_is_exact_sha_digest_and_publication(self) -> None:
        candidate = self.contract["candidate_release"]
        self.assertEqual(candidate["consumer_repository"], "rozkalnsandris/rozkalns-cv")
        self.assertEqual(candidate["source_sha"], CANDIDATE_SOURCE_SHA)
        self.assertEqual(candidate["simple_deploy_run_id"], 36241004385)
        self.assertEqual(candidate["image"], "ghcr.io/rozkalnsandris/rozkalns-cv")
        self.assertEqual(candidate["image_digest"], CANDIDATE_DIGEST)
        self.assertEqual(
            candidate["shared_workflow_sha"],
            "e05ed760791a127c7c9628696806ef39c9fe329c",
        )
        self.assertTrue(candidate["production_pointer_must_match_candidate_before_mutation"])
        self.assertFalse(candidate["mutable_production_tag_is_authority"])

    def test_activation_registry_contains_only_weather_and_cv(self) -> None:
        activation = load(ACTIVATION_REGISTRY_PATH)
        canonical = load(TARGET_REGISTRY_PATH)
        parsed = sd.load_registry(ACTIVATION_REGISTRY_PATH)
        self.assertTrue(parsed.execution_enabled)
        aliases = [item["target_alias"] for item in activation["targets"]]
        self.assertEqual(aliases, ["rozkalns-weather-public-rpi5", TARGET_ALIAS])
        self.assertNotIn("hermes-deals", aliases)
        self.assertNotIn("hermes-tech-public-rpi5", aliases)

        canonical_by_alias = {
            item["target_alias"]: item for item in canonical["targets"]
        }
        for item in activation["targets"]:
            self.assertEqual(item, canonical_by_alias[item["target_alias"]])

    def test_compose_and_host_materialization_are_exact_and_bounded(self) -> None:
        body = COMPOSE_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), COMPOSE_SHA)
        source = self.contract["source_contract"]
        self.assertEqual(
            source["activation_registry_path"],
            "ops/deploy/baselines/simple-deploy-targets-weather-cv-v1.json",
        )
        self.assertEqual(
            source["activation_registry_exact_aliases"],
            ["rozkalns-weather-public-rpi5", TARGET_ALIAS],
        )
        self.assertEqual(source["compose_source_sha256"], COMPOSE_SHA)

        materialization = self.contract["host_materialization"]
        self.assertEqual(
            materialization["activation_registry"]["destination_path"],
            "/etc/rozkalns-simple-deployer/targets.json",
        )
        self.assertEqual(materialization["activation_registry"]["required_mode"], "0444")
        self.assertEqual(
            materialization["identity"]["destination_path"],
            "/etc/rozkalns-simple-deployer/identity.json",
        )
        self.assertEqual(
            materialization["identity"]["source_sha"],
            "EXACT_AUTHORIZED_RPI5_MAIN_SHA",
        )
        self.assertEqual(
            materialization["compose"]["destination_path"],
            "/etc/rozkalns-simple-deployer/compose/rozkalns-cv.yml",
        )
        self.assertEqual(materialization["compose"]["required_mode"], "0444")

    def test_protected_config_and_data_are_preconditions_not_cutover_authority(self) -> None:
        protected = self.contract["protected_prerequisites"]
        config = protected["private_runtime_config"]
        self.assertEqual(
            config["path"],
            "/etc/rozkalns-simple-deployer/private/rozkalns-cv.env",
        )
        self.assertTrue(config["required_before_cutover"])
        self.assertFalse(config["content_read_by_cutover_preflight"])
        self.assertFalse(config["provisioned_by_cutover"])
        self.assertTrue(config["separate_exact_authority_required_if_absent"])

        data = protected["persistent_data"]
        self.assertEqual(
            data["path"],
            "/var/lib/rozkalns-simple-deployer/rozkalns-cv/data",
        )
        self.assertTrue(data["required_before_cutover"])
        self.assertFalse(data["create_host_path"])
        self.assertFalse(data["contents_read_by_cutover_preflight"])
        self.assertFalse(data["adopted_or_materialized_by_cutover"])
        self.assertTrue(data["separate_exact_data_authority_required_if_absent"])

        forbidden = self.contract["forbidden_operations"]
        self.assertIn("private-runtime-config-provisioning-or-content-read", forbidden)
        self.assertIn("persistent-data-adoption-copy-migration-or-content-read", forbidden)
        self.assertIn("database-schema-or-data-mutation", forbidden)

    def test_legacy_baseline_and_port_transition_are_exact(self) -> None:
        legacy = self.contract["legacy_runtime"]
        self.assertEqual(legacy["required_production_sha"], LEGACY_SOURCE_SHA)
        self.assertEqual(
            legacy["production_state_path"],
            "/var/lib/rozkalns-cv-deploy/current-sha",
        )
        containers = {item["name"]: item for item in legacy["containers"]}
        self.assertEqual(set(containers), {"cv", "cvbot"})
        self.assertEqual(containers["cv"]["required_port_bind"], "127.0.0.1:8088")
        self.assertEqual(
            containers["cvbot"]["required_runtime_image"],
            f"rozkalns-cv-cvbot:{LEGACY_SOURCE_SHA}",
        )
        self.assertEqual(legacy["pull_timer"]["required_enabled_state"], "disabled")
        self.assertEqual(legacy["pull_timer"]["required_active_state"], "inactive")
        self.assertEqual(legacy["pull_service"]["required_active_state"], "inactive")
        self.assertEqual(legacy["legacy_network_mutation"], "forbidden")
        self.assertEqual(legacy["legacy_data_or_config_mutation"], "forbidden")

        self.assertEqual(
            self.contract["port_ownership_transition"],
            {
                "bind": "127.0.0.1:8088",
                "required_before_owner": "container:cv",
                "required_between_state": "unbound",
                "required_after_owner": "compose:rozkalns-cv/cv",
                "parallel_bind_forbidden": True,
            },
        )

    def test_order_quiesces_timer_materializes_prepulls_then_retires_legacy(self) -> None:
        steps = self.contract["ordered_steps"]
        config = steps.index(
            "revalidate-private-runtime-config-metadata-only-prerequisite-present"
        )
        data = steps.index(
            "revalidate-persistent-data-metadata-only-prerequisite-present"
        )
        timer_stop = steps.index("stop-generic-simple-deployer.timer")
        registry = steps.index("materialize-weather-plus-cv-activation-registry")
        prepull = steps.index("prepull-exact-candidate-image-digest")
        legacy_cv = steps.index("stop-and-remove-legacy-cv-container")
        unbound = steps.index("verify-127.0.0.1:8088-unbound")
        apply = steps.index(
            "apply-rozkalns-cv-rpi5-through-reviewed-generic-simple-deploy"
        )
        health = steps.index("verify-health-200")
        timer_start = steps.index("start-generic-simple-deployer.timer")

        self.assertLess(config, timer_stop)
        self.assertLess(data, timer_stop)
        self.assertLess(timer_stop, registry)
        self.assertLess(registry, prepull)
        self.assertLess(prepull, legacy_cv)
        self.assertLess(legacy_cv, unbound)
        self.assertLess(unbound, apply)
        self.assertLess(apply, health)
        self.assertLess(health, timer_start)

    def test_generic_apply_and_receipt_must_match_exact_candidate(self) -> None:
        apply = self.contract["generic_simple_deploy_apply"]
        self.assertEqual(apply["target_alias"], TARGET_ALIAS)
        self.assertEqual(apply["expected_consumer_source_sha"], CANDIDATE_SOURCE_SHA)
        self.assertEqual(apply["expected_image_digest"], CANDIDATE_DIGEST)
        self.assertTrue(apply["exact_source_sha_required"])
        self.assertTrue(apply["exact_image_digest_required"])

        verification = self.contract["verification"]
        self.assertEqual(verification["required_http_status"], 200)
        self.assertEqual(
            verification["receipt_path"],
            "/var/lib/rozkalns-simple-deployer/receipts/rozkalns-cv-rpi5.json",
        )
        self.assertTrue(verification["receipt_source_sha_must_equal_candidate"])
        self.assertTrue(verification["receipt_digest_must_equal_candidate"])

    def test_executor_registry_keeps_cutover_strict_and_globally_disabled(self) -> None:
        registry = load(EXECUTOR_REGISTRY_PATH)
        operation = by(
            registry["operations"],
            "operation_id",
            "rpi5-main.rozkalns-cv-simple-deploy-cutover.v1",
        )
        self.assertFalse(registry["execution_enabled"])
        self.assertEqual(operation["source_repository"], "rozkalnsandris/RPi5_main")
        self.assertEqual(operation["target_alias"], TARGET_ALIAS)
        self.assertEqual(operation["authorization_class"], "STRICT")
        self.assertFalse(operation["ordinary_live_all_eligible"])
        self.assertEqual(operation["rollback_policy"], "NONE")
        self.assertEqual(
            operation["queue_match"]["repository_entrypoint"],
            "ops/deploy/rozkalns-cv-simple-deploy-cutover-v1.json",
        )


if __name__ == "__main__":
    unittest.main()
