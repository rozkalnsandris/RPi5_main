#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops/deploy/rozkalns-cv-simple-deploy-cutover-v1.json"
ACTIVATION_REGISTRY_PATH = ROOT / "ops/deploy/baselines/simple-deploy-targets-weather-cv-v1.json"
TARGET_REGISTRY_PATH = ROOT / "ops/deploy/simple-deploy-targets-v1.json"
HOST_CONTRACT_PATH = ROOT / "ops/contracts/simple-deploy-host-v1.json"
COMPAT_PATH = ROOT / "ops/contracts/simple-deploy-rozkalns-cv-compat-v1.json"
EXECUTOR_REGISTRY_PATH = ROOT / "ops/deploy/executor-operations.json"
COMPOSE_PATH = ROOT / "ops/deploy/simple-deploy-compose/rozkalns-cv.yml"

TARGET_ALIAS = "rozkalns-cv-rpi5"
CANDIDATE_SOURCE_SHA = "d75863d0ce4cfdac0015150137523abbaccf5914"
CANDIDATE_DIGEST = "sha256:ba9e24c82eccd833cfe42d6a4aa61ef76c584bcfd4c27efbced13c3a408d2a1a"
LEGACY_SOURCE_SHA = "4986a6d80460bd6d7681c70e09e61a15e31007f4"
COMPOSE_SHA = "a1ded554dc931c8451eb7e606c9cd9c6bac1c4b4126e56e533ad9ea38ee2c3d8"
PRIVATE_ENV = "/home/andris/docker/cv/bot/.env"
DATA_PATH = "/home/andris/docker/cv/bot/data"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def by(items, key, value):
    return next(item for item in items if item[key] == value)


class RozkalnsCvSimpleDeployCutoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load(CONTRACT_PATH)

    def test_contract_is_one_strict_source_only_adoption(self) -> None:
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.rozkalns-cv-simple-deploy-cutover.v1",
        )
        self.assertEqual(self.contract["issue"], 821)
        self.assertEqual(
            self.contract["operation_id"],
            "rpi5-main.rozkalns-cv-simple-deploy-cutover.v1",
        )
        self.assertFalse(self.contract["execution_enabled"])
        self.assertEqual(self.contract["authorization_class"], "STRICT")
        self.assertTrue(self.contract["one_time"])
        self.assertEqual(
            self.contract["operator_model"],
            "consumer-merge -> SIMPLE-DEPLOY -> production",
        )
        state = self.contract["source_only_state"]
        self.assertFalse(state["live_authorized"])
        self.assertFalse(state["runtime_mutation_permitted_by_this_file"])
        self.assertFalse(state["protected_runtime_content_access_authorized"])
        self.assertFalse(state["merge_authorized"])

    def test_candidate_is_current_exact_release(self) -> None:
        candidate = self.contract["candidate_release"]
        self.assertEqual(candidate["consumer_repository"], "rozkalnsandris/rozkalns-cv")
        self.assertEqual(candidate["source_sha"], CANDIDATE_SOURCE_SHA)
        self.assertEqual(candidate["image_digest"], CANDIDATE_DIGEST)
        self.assertTrue(candidate["production_pointer_must_match_candidate_before_mutation"])
        self.assertFalse(candidate["mutable_production_tag_is_authority"])

        apply = self.contract["generic_simple_deploy_apply"]
        self.assertEqual(apply["target_alias"], TARGET_ALIAS)
        self.assertEqual(apply["expected_consumer_source_sha"], CANDIDATE_SOURCE_SHA)
        self.assertEqual(apply["expected_image_digest"], CANDIDATE_DIGEST)

    def test_compose_reuses_existing_env_and_data_in_place(self) -> None:
        body = COMPOSE_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), COMPOSE_SHA)
        text = body.decode("utf-8")
        self.assertIn(f"- {PRIVATE_ENV}", text)
        self.assertIn(f"source: {DATA_PATH}", text)
        self.assertIn("target: /app/data", text)
        self.assertIn("create_host_path: false", text)
        self.assertIn("LLM_BASE_URL: https://api.openai.com", text)
        self.assertIn("LLM_MODEL: gpt-5.6-luna", text)
        self.assertNotIn("/etc/rozkalns-simple-deployer/private/rozkalns-cv.env", text)
        self.assertNotIn("/var/lib/rozkalns-simple-deployer/rozkalns-cv/data", text)

        existing = self.contract["existing_runtime_inputs"]
        env = existing["private_env"]
        data = existing["persistent_data"]
        self.assertEqual(env["path"], PRIVATE_ENV)
        self.assertTrue(env["reused_in_place"])
        self.assertFalse(env["content_read_by_cutover_preflight"])
        self.assertFalse(env["provisioned_or_copied_by_cutover"])
        self.assertEqual(data["path"], DATA_PATH)
        self.assertTrue(data["reused_in_place"])
        self.assertFalse(data["create_host_path"])
        self.assertFalse(data["copied_migrated_or_reowned_by_cutover"])
        self.assertTrue(data["storage_implementation_identical"])
        self.assertFalse(data["database_schema_migration_required"])
        self.assertEqual((data["application_uid"], data["application_gid"]), (10001, 10001))

    def test_all_registered_cv_compose_identities_match(self) -> None:
        for path in (TARGET_REGISTRY_PATH, ACTIVATION_REGISTRY_PATH):
            registry = load(path)
            target = by(registry["targets"], "target_alias", TARGET_ALIAS)
            self.assertEqual(target["compose"]["file_sha256"], COMPOSE_SHA)

        host = load(HOST_CONTRACT_PATH)
        host_target = by(host["registry"]["reviewed_targets"], "target_alias", TARGET_ALIAS)
        self.assertEqual(host_target["compose_sha256"], COMPOSE_SHA)
        self.assertEqual(host_target["private_runtime_config_path"], PRIVATE_ENV)
        self.assertEqual(host_target["persistent_data_path"], DATA_PATH)
        self.assertTrue(host_target["reuses_existing_runtime_inputs"])

        compat = load(COMPAT_PATH)
        adapter = compat["host_adapter"]
        self.assertEqual(adapter["compose_sha256"], COMPOSE_SHA)
        self.assertEqual(adapter["private_runtime_config_path"], PRIVATE_ENV)
        self.assertEqual(adapter["persistent_data_path"], DATA_PATH)
        self.assertTrue(adapter["reuses_existing_runtime_inputs"])
        self.assertTrue(compat["boundaries"]["existing_private_runtime_config_reused_in_place"])
        self.assertTrue(compat["boundaries"]["existing_persistent_data_reused_in_place"])
        self.assertFalse(
            compat["boundaries"]["private_runtime_config_provisioning_requires_separate_exact_authority"]
        )
        self.assertFalse(
            compat["boundaries"]["persistent_data_adoption_requires_separate_exact_data_authority"]
        )

    def test_data_adoption_copy_machinery_is_removed(self) -> None:
        self.assertFalse(
            (ROOT / "ops/contracts/simple-deploy-rozkalns-cv-data-adoption-v1.json").exists()
        )
        self.assertFalse(
            (ROOT / "scripts/adopt-simple-deploy-rozkalns-cv-data-v1.py").exists()
        )
        self.assertFalse(
            (ROOT / "tests/test_rozkalns_cv_simple_deploy_data_adoption.py").exists()
        )

    def test_legacy_transition_is_small_and_fail_closed(self) -> None:
        legacy = self.contract["legacy_runtime"]
        self.assertEqual(legacy["required_production_sha"], LEGACY_SOURCE_SHA)
        containers = {item["name"]: item for item in legacy["containers"]}
        self.assertEqual(set(containers), {"cv", "cvbot"})
        self.assertEqual(containers["cv"]["required_port_bind"], "127.0.0.1:8088")
        self.assertEqual(
            containers["cvbot"]["required_runtime_image"],
            f"rozkalns-cv-cvbot:{LEGACY_SOURCE_SHA}",
        )

        steps = self.contract["ordered_steps"]
        joined = "\n".join(steps)
        self.assertNotIn("data-adoption", joined)
        self.assertNotIn("persistent-data-through", joined)
        self.assertLess(
            steps.index("stop-and-remove-exact-legacy-cvbot-and-cv-containers"),
            steps.index("verify-127.0.0.1:8088-unbound"),
        )
        self.assertLess(
            steps.index("verify-127.0.0.1:8088-unbound"),
            steps.index("apply-rozkalns-cv-rpi5-through-generic-simple-deploy"),
        )

        failure = self.contract["failure_semantics"]
        self.assertTrue(failure["fail_closed"])
        for key in (
            "automatic_retry",
            "automatic_cleanup",
            "automatic_rollback",
            "alternate_mutation_path",
        ):
            self.assertFalse(failure[key], key)

    def test_verification_binds_receipt_health_and_ui_v2(self) -> None:
        verification = self.contract["verification"]
        self.assertEqual(verification["required_http_status"], 200)
        self.assertTrue(verification["receipt_source_sha_must_equal_candidate"])
        self.assertTrue(verification["receipt_digest_must_equal_candidate"])
        self.assertEqual(verification["public_url"], "https://rozkalns.net/en/")
        self.assertEqual(verification["public_ui_v2_marker"], "Linux Operations Lab")
        self.assertEqual(
            verification["public_app_asset"],
            "assets/app.e29b029635cc.mjs",
        )

    def test_executor_registry_matches_simplified_contract(self) -> None:
        registry = load(EXECUTOR_REGISTRY_PATH)
        operation = by(
            registry["operations"],
            "operation_id",
            "rpi5-main.rozkalns-cv-simple-deploy-cutover.v1",
        )
        self.assertFalse(registry["execution_enabled"])
        self.assertEqual(operation["authorization_class"], "STRICT")
        self.assertFalse(operation["ordinary_live_all_eligible"])
        deps = operation["dependencies"]
        self.assertIn("issue:RPi5_main#821", deps)
        self.assertIn(f"consumer-source-sha:{CANDIDATE_SOURCE_SHA}", deps)
        self.assertIn(f"candidate-image-digest:{CANDIDATE_DIGEST}", deps)
        self.assertIn(f"existing-private-env:{PRIVATE_ENV}", deps)
        self.assertIn(f"existing-persistent-data:{DATA_PATH}", deps)
        text = json.dumps(operation)
        self.assertNotIn("data-adoption", text)
        self.assertNotIn("/etc/rozkalns-simple-deployer/private/rozkalns-cv.env", text)
        self.assertNotIn("/var/lib/rozkalns-simple-deployer/rozkalns-cv/data", text)


if __name__ == "__main__":
    unittest.main()
