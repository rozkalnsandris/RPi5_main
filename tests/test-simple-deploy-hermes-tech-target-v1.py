#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/lib/deploy_executor/simple_deploy_v1.py"
spec = importlib.util.spec_from_file_location("simple_deploy_v1", MODULE_PATH)
assert spec and spec.loader
sd = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sd
spec.loader.exec_module(sd)

TARGET_ALIAS = "hermes-tech-public-rpi5"
CONSUMER_SHA = "3d8e2400e26e7bf4e992539e1239120f9bc1af44"
SHARED_SHA = "e05ed760791a127c7c9628696806ef39c9fe329c"
COMPOSE_SHA = "fd1ca0d00c79bfb5e5cd1be589ae13b378c5c223be0b61d3f14f31da687fe6b9"
COMPOSE_PATH = ROOT / "ops/deploy/simple-deploy-compose/hermes-tech-public.yml"


class HermesTechTargetTests(unittest.TestCase):
    def test_registry_binds_narrow_public_static_target(self):
        registry = sd.load_registry(ROOT / "ops/deploy/simple-deploy-targets-v1.json")
        target = registry.get(TARGET_ALIAS)

        self.assertEqual(len(registry.targets), 3)
        self.assertEqual(target.consumer_repository, "rozkalnsandris/hermes-tech")
        self.assertEqual(target.image, "ghcr.io/rozkalnsandris/hermes-tech")
        self.assertEqual(target.architecture, "linux/arm64")
        self.assertEqual(target.shared_workflow_sha, SHARED_SHA)
        self.assertEqual(target.compose.project, "hermes-tech-public")
        self.assertEqual(target.compose.file, "hermes-tech-public.yml")
        self.assertEqual(target.compose.service, "hermes-tech")
        self.assertEqual(target.health.liveness_url, "http://127.0.0.1:8089/health")
        self.assertEqual(target.health.readiness_state, "required")
        self.assertEqual(target.health.readiness_url, "http://127.0.0.1:8089/ready")
        self.assertEqual(target.wait_timeout_seconds, 180)
        self.assertEqual(target.persistent_volumes, ())
        self.assertEqual(target.registry_pull_profile, "public-anonymous-pull")
        self.assertEqual(target.forbidden_operations, sd.FORBIDDEN_OPERATIONS)

    def test_compose_is_hash_pinned_loopback_only_and_stateless(self):
        body = COMPOSE_PATH.read_bytes()
        text = body.decode("utf-8")
        self.assertEqual(hashlib.sha256(body).hexdigest(), COMPOSE_SHA)
        self.assertIn('127.0.0.1:8089:8080', text)
        self.assertIn('ghcr.io/rozkalnsandris/hermes-tech:production', text)
        self.assertIn('http://127.0.0.1:8080/ready', text)
        self.assertIn('read_only: true', text)
        self.assertIn('no-new-privileges:true', text)
        self.assertNotIn('volumes:', text)
        self.assertNotIn('environment:', text)
        self.assertNotIn('build:', text)
        self.assertNotIn('/home/andris/hermes-tech', text)

    def test_host_contract_records_exact_consumer_revision_and_live_gate(self):
        contract = json.loads((ROOT / "ops/contracts/simple-deploy-host-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["registry"]["current_reviewed_targets"], 3)
        targets = {
            item["target_alias"]: item
            for item in contract["registry"]["reviewed_targets"]
        }
        self.assertIn(TARGET_ALIAS, targets)
        hermes_tech = targets[TARGET_ALIAS]
        self.assertEqual(hermes_tech["consumer_contract_revision"], CONSUMER_SHA)
        self.assertEqual(hermes_tech["compose_sha256"], COMPOSE_SHA)
        self.assertEqual(hermes_tech["liveness_url"], "http://127.0.0.1:8089/health")
        self.assertEqual(hermes_tech["readiness_url"], "http://127.0.0.1:8089/ready")
        self.assertTrue(contract["activation"]["hermes_tech_target_installation_requires_separate_exact_live_cutover"])
        self.assertTrue(contract["activation"]["hermes_tech_existing_v14_runtime_retirement_requires_separate_exact_live_authority"])


if __name__ == "__main__":
    unittest.main()
