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
COMPOSE_SHA = "be7f021c9d64192905c908bcbb127dbc7ec1c2514d898f05cbf8de4c44ffa4a2"
COMPOSE_PATH = ROOT / "ops/deploy/simple-deploy-compose/rozkalns-cv.yml"
CONTRACT_PATH = ROOT / "ops/contracts/simple-deploy-rozkalns-cv-compat-v1.json"
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
            "SOURCE_COMPATIBILITY_PREREQUISITE_READY_TARGET_REGISTRATION_PENDING",
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
        self.assertEqual(
            adapter["private_runtime_config_path"],
            "/etc/rozkalns-simple-deployer/private/rozkalns-cv.env",
        )
        self.assertEqual(
            adapter["persistent_data_path"],
            "/var/lib/rozkalns-simple-deployer/rozkalns-cv/data",
        )
        self.assertFalse(adapter["persistent_data_create_host_path"])
        self.assertEqual(
            adapter["liveness_url"],
            "http://127.0.0.1:8088/api/health",
        )
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
        self.assertIn(
            "/etc/rozkalns-simple-deployer/private/rozkalns-cv.env",
            text,
        )
        self.assertIn(
            "source: /var/lib/rozkalns-simple-deployer/rozkalns-cv/data",
            text,
        )
        self.assertIn("create_host_path: false", text)
        self.assertIn("http://127.0.0.1:8080/api/health/ready", text)
        self.assertNotIn("${", text)
        self.assertNotIn("/home/", text)
        self.assertNotIn("build:", text)
        self.assertNotIn("privileged:", text)
        self.assertNotIn("network_mode:", text)
        self.assertNotIn("/var/run/docker.sock", text)

    def test_source_prerequisite_does_not_register_or_activate_target(self) -> None:
        boundaries = self.contract["boundaries"]
        self.assertFalse(boundaries["source_merge_registers_target"])
        self.assertFalse(boundaries["source_merge_installs_or_enables_runtime"])
        self.assertTrue(
            boundaries["target_registration_requires_follow_up_tracked_source_change"]
        )
        self.assertTrue(
            boundaries["target_installation_requires_separate_exact_live_cutover"]
        )
        self.assertTrue(
            boundaries[
                "private_runtime_config_provisioning_requires_separate_exact_authority"
            ]
        )
        self.assertTrue(
            boundaries["persistent_data_adoption_requires_separate_exact_data_authority"]
        )
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

        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        aliases = {item["target_alias"] for item in registry["targets"]}
        self.assertNotIn(TARGET_ALIAS, aliases)


if __name__ == "__main__":
    unittest.main()
