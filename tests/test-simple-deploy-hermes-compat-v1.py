#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops/contracts/simple-deploy-hermes-compat-v1.json"
COMPOSE_PATH = ROOT / "ops/deploy/simple-deploy-compose/hermes-deals-api.yml"
TARGETS_PATH = ROOT / "ops/deploy/simple-deploy-targets-v1.json"
EXECUTOR_PATH = ROOT / "ops/lib/deploy_executor/simple_deploy_v1.py"

EXPECTED_CONSUMER_SHA = "13f9fb69b9576d8e97ab3a85334927f3c576ca1c"
EXPECTED_ENV_PATH = "/etc/rozkalns-simple-deployer/private/hermes-deals-api.env"
EXPECTED_HOST_ROOT = "/var/lib/rozkalns-simple-deployer/hermes-deals"
EXPECTED_BINDS = {
    f"{EXPECTED_HOST_ROOT}/data/raw": "/data/raw",
    f"{EXPECTED_HOST_ROOT}/config": "/app/config",
}


def _service_names(compose_text: str) -> list[str]:
    names: list[str] = []
    in_services = False
    for line in compose_text.splitlines():
        if line == "services:":
            in_services = True
            continue
        if not in_services:
            continue
        if line and not line.startswith(" "):
            break
        match = re.fullmatch(r"  ([a-zA-Z0-9_-]+):", line)
        if match:
            names.append(match.group(1))
    return names


class HermesSimpleDeployCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.compose = COMPOSE_PATH.read_text(encoding="utf-8")
        cls.targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
        cls.executor = EXECUTOR_PATH.read_text(encoding="utf-8")

    def test_contract_is_source_only_and_binds_exact_consumer(self) -> None:
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.simple-deploy-hermes-compat.v1",
        )
        self.assertEqual(self.contract["issue"], 690)
        self.assertEqual(
            self.contract["status"],
            "SOURCE_COMPATIBILITY_TARGET_REGISTERED_NOT_INSTALLED",
        )
        self.assertEqual(
            self.contract["consumer"],
            {
                "repository": "rozkalnsandris/hermes-deals",
                "revision": EXPECTED_CONSUMER_SHA,
                "future_target_alias": "hermes-deals",
                "image": "ghcr.io/rozkalnsandris/hermes-deals",
                "architecture": "linux/arm64",
            },
        )
        self.assertEqual(self.contract["source_target_registration_issue"], 692)
        self.assertTrue(self.contract["target_registration_performed"])
        self.assertFalse(self.contract["target_installation_performed"])
        self.assertFalse(self.contract["host_runtime_mutation_performed"])
        self.assertFalse(self.contract["source_merge_authorizes_live"])

    def test_api_compose_is_structurally_isolated_from_dependencies(self) -> None:
        self.assertEqual(_service_names(self.compose), ["api"])
        for forbidden in (
            "depends_on:",
            "build:",
            "profiles:",
            "  db:",
            "  web:",
            "  worker:",
            "--remove-orphans",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.compose)

        dependency = self.contract["dependency_isolation"]
        self.assertEqual(dependency["database_service"], "db")
        self.assertEqual(dependency["existing_web_service"], "web")
        self.assertEqual(dependency["profile_only_worker"], "worker")
        self.assertTrue(dependency["ordinary_compose_model_excludes_all_three"])
        self.assertTrue(dependency["api_uses_existing_external_project_network"])
        self.assertTrue(dependency["generic_reconciler_targets_only_api"])

    def test_private_runtime_config_is_one_fixed_host_owned_path(self) -> None:
        private = self.contract["private_runtime_config"]
        self.assertEqual(private["path"], EXPECTED_ENV_PATH)
        self.assertEqual(private["required_keys"], ["DATABASE_URL", "HTTP_USER_AGENT"])
        self.assertFalse(private["secret_values_in_git"])
        self.assertFalse(private["provisioning_or_copy_performed_by_issue_690"])
        self.assertTrue(private["future_live_provisioning_requires_separate_exact_authority"])
        self.assertIn(f"      - {EXPECTED_ENV_PATH}", self.compose)

        # The static adapter does not interpolate caller/process environment at parse time.
        self.assertNotIn("${", self.compose)
        self.assertNotIn("postgresql+", self.compose)
        self.assertNotIn("POSTGRES_PASSWORD", self.compose)

    def test_relative_consumer_binds_are_normalized_to_reviewed_absolute_sources(self) -> None:
        mounts = self.contract["bind_mounts"]
        self.assertEqual(
            {item["source"]: item["target"] for item in mounts},
            EXPECTED_BINDS,
        )
        self.assertTrue(all(item["create_host_path"] is False for item in mounts))
        self.assertTrue(all(item["source"].startswith(f"{EXPECTED_HOST_ROOT}/") for item in mounts))
        self.assertNotIn("source: ./", self.compose)
        for source, target in EXPECTED_BINDS.items():
            with self.subTest(source=source):
                self.assertIn(f"        source: {source}", self.compose)
                self.assertIn(f"        target: {target}", self.compose)
        self.assertEqual(self.compose.count("create_host_path: false"), 2)

    def test_existing_project_network_is_fixed_and_external(self) -> None:
        self.assertIn("    external: true", self.compose)
        self.assertIn("    name: hermes-deals_internal", self.compose)
        self.assertIn("          - api", self.compose)
        self.assertEqual(
            self.contract["ordinary_api_compose"]["external_network"],
            "hermes-deals_internal",
        )

    def test_consumer_cannot_select_runtime_authority(self) -> None:
        self.assertEqual(
            self.contract["caller_authority"],
            {
                "project_directory": False,
                "env_file": False,
                "host_path": False,
                "environment": False,
                "secret": False,
                "credential": False,
                "argv": False,
                "command": False,
            },
        )
        # #690/#692 must not widen the generic reconciler CLI/runtime authority surface.
        for marker in ("--project-directory", "--env-file", "--no-deps"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.executor)

    def test_hermes_target_registration_is_static_and_not_live(self) -> None:
        aliases = [target["target_alias"] for target in self.targets["targets"]]
        self.assertEqual(aliases, ["rozkalns-weather-public-rpi5", "hermes-deals"])
        self.assertTrue(self.contract["target_registration_performed"])
        self.assertFalse(self.contract["target_installation_performed"])
        self.assertFalse(self.contract["host_runtime_mutation_performed"])


if __name__ == "__main__":
    unittest.main()
