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

TARGET_ALIAS = "coloring-pages-public-rpi5"
CONSUMER_SHA = "dd9204581d46be618f1c7b0a6bafde90bcb691df"
SHARED_SHA = "94187cc447fc80757db10ac25d49717d00dc8430"
COMPOSE_SHA = "77c71da44896b393002b7a13449d6fbaca76b38c6d982580d23156b674fe2941"
COMPOSE_PATH = ROOT / "ops/deploy/simple-deploy-compose/coloring-pages-public.yml"


class ColoringPagesTargetTests(unittest.TestCase):
    def test_registry_binds_narrow_public_static_target(self):
        registry = sd.load_registry(ROOT / "ops/deploy/simple-deploy-targets-v1.json")
        target = registry.get(TARGET_ALIAS)

        self.assertEqual(len(registry.targets), 5)
        self.assertEqual(target.consumer_repository, "rozkalnsandris/coloring-pages")
        self.assertEqual(target.image, "ghcr.io/rozkalnsandris/coloring-pages")
        self.assertEqual(target.architecture, "linux/arm64")
        self.assertEqual(target.shared_workflow_sha, SHARED_SHA)
        self.assertEqual(target.compose.project, "coloring-pages-public")
        self.assertEqual(target.compose.file, "coloring-pages-public.yml")
        self.assertEqual(target.compose.service, "coloring-pages")
        self.assertEqual(target.health.liveness_url, "http://127.0.0.1:9191/health")
        self.assertEqual(target.health.readiness_state, "required")
        self.assertEqual(target.health.readiness_url, "http://127.0.0.1:9191/ready")
        self.assertEqual(target.wait_timeout_seconds, 180)
        self.assertEqual(target.persistent_volumes, ())
        self.assertEqual(target.registry_pull_profile, "public-anonymous-pull")
        self.assertEqual(target.forbidden_operations, sd.FORBIDDEN_OPERATIONS)

    def test_compose_is_hash_pinned_loopback_only_and_stateless(self):
        body = COMPOSE_PATH.read_bytes()
        text = body.decode("utf-8")
        self.assertEqual(hashlib.sha256(body).hexdigest(), COMPOSE_SHA)
        self.assertIn('127.0.0.1:9191:8080', text)
        self.assertIn('ghcr.io/rozkalnsandris/coloring-pages:production', text)
        self.assertIn('http://127.0.0.1:8080/ready', text)
        self.assertIn('read_only: true', text)
        self.assertIn('no-new-privileges:true', text)
        self.assertIn('cap_drop:', text)
        self.assertNotIn('volumes:', text)
        self.assertNotIn('environment:', text)
        self.assertNotIn('build:', text)
        self.assertNotIn('/home/', text)

    def test_host_contract_records_exact_consumer_revision_and_live_gate(self):
        contract = json.loads(
            (ROOT / "ops/contracts/simple-deploy-host-v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(contract["registry"]["current_reviewed_targets"], 5)
        targets = {
            item["target_alias"]: item
            for item in contract["registry"]["reviewed_targets"]
        }
        self.assertIn(TARGET_ALIAS, targets)
        coloring = targets[TARGET_ALIAS]
        self.assertEqual(coloring["consumer_contract_revision"], CONSUMER_SHA)
        self.assertEqual(coloring["source_registration_issue"], 838)
        self.assertEqual(coloring["compose_sha256"], COMPOSE_SHA)
        self.assertEqual(coloring["liveness_url"], "http://127.0.0.1:9191/health")
        self.assertEqual(coloring["readiness_url"], "http://127.0.0.1:9191/ready")
        self.assertTrue(
            contract["activation"][
                "coloring_pages_target_installation_requires_separate_exact_live_cutover"
            ]
        )
        self.assertFalse(contract["activation"]["source_merge_installs_or_enables_runtime"])


if __name__ == "__main__":
    unittest.main()
