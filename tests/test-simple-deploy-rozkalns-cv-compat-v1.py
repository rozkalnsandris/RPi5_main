#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TARGET_ALIAS = "rozkalns-cv-rpi5"
CONSUMER_SHA = "139fb7046c77e1e58ec4a0876db3dddb96c85cb5"
SHARED_SHA = "e05ed760791a127c7c9628696806ef39c9fe329c"
COMPOSE_SHA = "d4c7e9ed5c36245d92ce7da199194ec032c74de6ea03f2b522e31a43ffaf3277"
COMPOSE_PATH = ROOT / "ops/deploy/simple-deploy-compose/rozkalns-cv.yml"
CONTRACT_PATH = ROOT / "ops/contracts/simple-deploy-rozkalns-cv-compat-v1.json"
HOST_CONTRACT_PATH = ROOT / "ops/contracts/simple-deploy-host-v1.json"
REGISTRY_PATH = ROOT / "ops/deploy/simple-deploy-targets-v1.json"

FORBIDDEN_OPERATIONS = [
    "database-schema-data-mutation",
    "destructive-recovery",
    "secrets-credentials-permissions",
    "cloudflare-dns-network",
    "private-provider-activation",
    "unrelated-host-control",
]


class RozkalnsCvCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_contract_binds_exact_consumer_and_shared_source(self) -> None:
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.simple-deploy-rozkalns-cv-compat.v1",
        )
        self.assertEqual(
            self.contract["status"],
            "SOURCE_COMPATIBILITY_COMPLETE_TARGET_REGISTERED_LIVE_CUTOVER_REQUIRED",
        )
        consumer = self.contract["consumer"]
        self.assertEqual(consumer["repository"], "rozkalnsandris/rozkalns-cv")
        self.assertEqual(consumer["consumer_contract_revision"], CONSUMER_SHA)
        self.assertEqual(consumer["target_alias"], TARGET_ALIAS)
        self.assertEqual(consumer["image"], "ghcr.io/rozkalnsandris/rozkalns-cv")
        self.assertEqual(consumer["architecture"], "linux/arm64")
        self.assertEqual(consumer["manifest_named_volumes"], [])
        self.assertTrue(consumer["consumer_compose_uses_persistent_bind"])

        shared = self.contract["shared_contract"]
        self.assertEqual(shared["repository"], "rozkalnsandris/ops-workflows")
        self.assertEqual(shared["revision"], SHARED_SHA)
        self.assertEqual(shared["workflow"], ".github/workflows/simple-deploy.yml")
        self.assertEqual(self.contract["forbidden_operations"], FORBIDDEN_OPERATIONS)

    def test_host_adapter_is_fixed_and_fail_closed(self) -> None:
        body = COMPOSE_PATH.read_bytes()
        text = body.decode("utf-8")
        self.assertEqual(hashlib.sha256(body).hexdigest(), COMPOSE_SHA)

        adapter = self.contract["host_adapter"]
        self.assertEqual(adapter["compose_sha256"], COMPOSE_SHA)
        self.assertEqual(
            adapter["compose_source"],
            "ops/deploy/simple-deploy-compose/rozkalns-cv.yml",
        )
        self.assertEqual(adapter["project"], "rozkalns-cv")
        self.assertEqual(adapter["service"], "cv")
        self.assertEqual(adapter["registry_pull_profile"], "public-anonymous-pull")
        self.assertEqual(adapter["persistent_data_home_resolution"], "passwd_database")
        self.assertEqual(adapter["persistent_data_relative_path"], "docker/cv/bot/data")
        self.assertEqual(adapter["compose_interpolation_env_path"], "/etc/rozkalns-simple-deployer/compose/.env")
        self.assertEqual(
            adapter["compose_interpolation_variables"],
            {"persistent_data": "ROZKALNS_CV_DATA_PATH"},
        )
        self.assertEqual(
            adapter["private_runtime_config_path"],
            "/etc/rozkalns-simple-deployer/private/rozkalns-cv.env",
        )
        self.assertEqual(
            adapter["private_runtime_config_parent_path"],
            "/etc/rozkalns-simple-deployer/private",
        )
        self.assertEqual(adapter["private_runtime_config_owner"], "root")
        self.assertEqual(adapter["private_runtime_config_group"], "rozkalns-simple-deployer")
        self.assertEqual(adapter["private_runtime_config_mode"], "0640")
        self.assertEqual(
            adapter["private_runtime_config_materializer"],
            "scripts/materialize-simple-deploy-rozkalns-cv-private-env-v1.py",
        )
        self.assertTrue(adapter["materializes_private_runtime_config_boundary"])
        self.assertTrue(adapter["reuses_existing_persistent_data"])
        self.assertFalse(adapter["persistent_data_create_host_path"])
        self.assertEqual(adapter["liveness_url"], "http://127.0.0.1:8088/api/health")
        self.assertEqual(adapter["readiness_state"], "required")
        self.assertEqual(
            adapter["readiness_url"],
            "http://127.0.0.1:8088/api/health/ready",
        )
        self.assertEqual(adapter["wait_timeout_seconds"], 180)

        self.assertIn("ghcr.io/rozkalnsandris/rozkalns-cv:production", text)
        self.assertIn('"127.0.0.1:8088:8080"', text)
        self.assertIn('user: "10001:10001"', text)
        self.assertIn("read_only: true", text)
        self.assertIn("no-new-privileges:true", text)
        self.assertIn("cap_drop:", text)
        self.assertIn("pids_limit: 192", text)
        self.assertIn("env_file:", text)
        self.assertIn("../private/rozkalns-cv.env", text)
        self.assertNotIn("ROZKALNS_CV_ENV_FILE", text)
        self.assertIn("source: ${ROZKALNS_CV_DATA_PATH:?", text)
        self.assertNotIn("/home/", text)
        self.assertIn("create_host_path: false", text)
        self.assertIn("http://127.0.0.1:8080/api/health/ready", text)
        self.assertEqual(text.count("${"), 1)
        self.assertIn("${ROZKALNS_CV_DATA_PATH:?", text)
        self.assertNotIn("build:", text)
        self.assertNotIn("privileged:", text)
        self.assertNotIn("network_mode:", text)
        self.assertNotIn("/var/run/docker.sock", text)

    def test_registration_is_source_only_and_preserves_live_gates(self) -> None:
        boundaries = self.contract["boundaries"]
        self.assertTrue(boundaries["source_merge_registers_target"])
        self.assertFalse(boundaries["source_merge_installs_or_enables_runtime"])
        self.assertFalse(
            boundaries["target_registration_requires_follow_up_tracked_source_change"]
        )
        self.assertTrue(
            boundaries["target_installation_requires_separate_exact_live_cutover"]
        )
        self.assertFalse(
            boundaries[
                "private_runtime_config_provisioning_requires_separate_exact_authority"
            ]
        )
        self.assertFalse(boundaries["existing_private_runtime_config_reused_in_place"])
        self.assertTrue(
            boundaries["private_runtime_config_materialized_during_one_time_cutover"]
        )
        self.assertTrue(boundaries["private_runtime_config_source_remains_unchanged"])
        self.assertTrue(
            boundaries["private_runtime_config_materialization_requires_exact_live_authority"]
        )
        self.assertFalse(boundaries["ordinary_reconciler_reads_legacy_private_env"])
        self.assertFalse(
            boundaries["persistent_data_adoption_requires_separate_exact_data_authority"]
        )
        self.assertTrue(boundaries["existing_persistent_data_reused_in_place"])
        self.assertFalse(
            boundaries["ordinary_reconciler_initializes_migrates_or_recovers_database"]
        )
        self.assertTrue(
            boundaries[
                "existing_runtime_retirement_requires_separate_exact_live_authority"
            ]
        )
        self.assertFalse(boundaries["source_merge_runs_compose_or_docker"])
        self.assertFalse(boundaries["source_merge_mutates_cloudflare_or_network"])

    def test_registry_and_host_contract_bind_exact_cv_target(self) -> None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(registry["schema"], "rozkalns.rpi5-main.simple-deploy.targets.v1")
        self.assertTrue(registry["execution_enabled"])
        self.assertEqual(len(registry["targets"]), 4)
        targets = {item["target_alias"]: item for item in registry["targets"]}
        self.assertIn(TARGET_ALIAS, targets)
        target = targets[TARGET_ALIAS]
        self.assertEqual(target["consumer_repository"], "rozkalnsandris/rozkalns-cv")
        self.assertEqual(target["image"], "ghcr.io/rozkalnsandris/rozkalns-cv")
        self.assertEqual(target["architecture"], "linux/arm64")
        self.assertEqual(target["shared_workflow_sha"], SHARED_SHA)
        self.assertEqual(target["compose"]["project"], "rozkalns-cv")
        self.assertEqual(target["compose"]["file"], "rozkalns-cv.yml")
        self.assertEqual(target["compose"]["file_sha256"], COMPOSE_SHA)
        self.assertEqual(target["compose"]["service"], "cv")
        self.assertEqual(target["health"]["liveness_url"], "http://127.0.0.1:8088/api/health")
        self.assertEqual(target["health"]["readiness_state"], "required")
        self.assertEqual(
            target["health"]["readiness_url"],
            "http://127.0.0.1:8088/api/health/ready",
        )
        self.assertEqual(target["wait_timeout_seconds"], 180)
        self.assertEqual(target["receipt_name"], "rozkalns-cv-rpi5.json")
        self.assertEqual(target["persistent_volumes"], [])
        self.assertEqual(target["registry_pull_profile"], "public-anonymous-pull")
        self.assertEqual(target["forbidden_operations"], FORBIDDEN_OPERATIONS)

        host = json.loads(HOST_CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(host["registry"]["current_reviewed_targets"], 4)
        reviewed = {
            item["target_alias"]: item
            for item in host["registry"]["reviewed_targets"]
        }
        self.assertIn(TARGET_ALIAS, reviewed)
        cv = reviewed[TARGET_ALIAS]
        self.assertEqual(cv["consumer_contract_revision"], CONSUMER_SHA)
        self.assertEqual(cv["compatibility_prerequisite_pr"], 741)
        self.assertEqual(cv["compose_sha256"], COMPOSE_SHA)
        self.assertFalse(cv["persistent_data_create_host_path"])
        self.assertEqual(cv["persistent_data_home_resolution"], "passwd_database")
        self.assertEqual(cv["persistent_data_relative_path"], "docker/cv/bot/data")
        self.assertEqual(cv["compose_interpolation_env_path"], "/etc/rozkalns-simple-deployer/compose/.env")
        self.assertEqual(
            cv["compose_interpolation_variables"],
            {"persistent_data": "ROZKALNS_CV_DATA_PATH"},
        )
        self.assertEqual(
            cv["private_runtime_config_path"],
            "/etc/rozkalns-simple-deployer/private/rozkalns-cv.env",
        )
        self.assertEqual(
            cv["private_runtime_config_materializer"],
            "scripts/materialize-simple-deploy-rozkalns-cv-private-env-v1.py",
        )
        self.assertTrue(cv["materializes_private_runtime_config_boundary"])
        self.assertTrue(cv["reuses_existing_persistent_data"])

        activation = host["activation"]
        self.assertTrue(
            activation["rozkalns_cv_target_installation_requires_separate_exact_live_cutover"]
        )
        self.assertTrue(
            activation["rozkalns_cv_private_runtime_config_materialized_during_cutover"]
        )
        self.assertTrue(
            activation["rozkalns_cv_existing_persistent_data_reused_in_place"]
        )
        self.assertTrue(
            activation[
                "rozkalns_cv_existing_runtime_retirement_requires_separate_exact_live_authority"
            ]
        )


if __name__ == "__main__":
    unittest.main()
