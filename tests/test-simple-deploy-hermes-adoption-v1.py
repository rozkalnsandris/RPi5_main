#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/adopt-simple-deploy-hermes-v1.py"
spec = importlib.util.spec_from_file_location("adopt_simple_deploy_hermes_v1", MODULE_PATH)
assert spec and spec.loader
adopt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adopt
spec.loader.exec_module(adopt)

BASELINE = ROOT / "ops/deploy/baselines/simple-deploy-targets-weather-only-v1.json"
DESIRED = ROOT / "ops/deploy/baselines/simple-deploy-targets-weather-hermes-v1.json"
WEATHER = ROOT / "ops/deploy/simple-deploy-compose/rozkalns-weather-public.yml"
HERMES = ROOT / "ops/deploy/simple-deploy-compose/hermes-deals-api.yml"
CONTRACT = ROOT / "ops/contracts/simple-deploy-hermes-adoption-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.install_root = self.base / "etc/rozkalns-simple-deployer"
        self.compose_root = self.install_root / "compose"
        self.libexec_root = self.base / "usr/local/libexec/rozkalns-simple-deployer"
        self.compose_root.mkdir(parents=True, mode=0o755)
        self.libexec_root.mkdir(parents=True, mode=0o755)
        os.chmod(self.install_root, 0o755)
        os.chmod(self.compose_root, 0o755)

        self.registry = self.install_root / "targets.json"
        self.identity = self.install_root / "identity.json"
        self.weather = self.compose_root / "rozkalns-weather-public.yml"
        self.hermes = self.compose_root / "hermes-deals-api.yml"
        self.executor = self.libexec_root / "simple_deploy_v1.py"
        self.public_registry = self.install_root / "public_targets.json"
        self.registry_stage = self.install_root / ".targets.json.hermes-adoption-v1.staged"
        self.hermes_stage = self.compose_root / ".hermes-deals-api.yml.adoption-v1.staged"

        self.registry.write_bytes(BASELINE.read_bytes())
        self.identity.write_bytes(adopt._identity_bytes())
        self.weather.write_bytes(WEATHER.read_bytes())
        self.executor.write_text("# frozen executor fixture\n", encoding="utf-8")
        for path in (self.registry, self.identity, self.weather, self.executor):
            os.chmod(path, 0o444)

        self.paths = adopt.InstallPaths(
            root=self.install_root,
            registry=self.registry,
            identity=self.identity,
            compose_root=self.compose_root,
            weather_compose=self.weather,
            hermes_compose=self.hermes,
            executor=self.executor,
            erroneous_public_registry=self.public_registry,
            registry_stage=self.registry_stage,
            hermes_stage=self.hermes_stage,
        )
        self.uid = os.getuid()
        self.gid = os.getgid()

    def preflight(self) -> adopt.Prepared:
        return adopt._preflight(self.paths, uid=self.uid, gid=self.gid)

    def close(self) -> None:
        self.temp.cleanup()


class HermesAdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()

    def tearDown(self) -> None:
        self.fx.close()

    def test_exact_weather_baseline_adopts_only_two_reviewed_targets(self) -> None:
        weather_before = self.fx.weather.read_bytes()
        executor_before = self.fx.executor.read_bytes()
        identity_before = self.fx.identity.read_bytes()

        prepared = self.fx.preflight()
        progress = adopt._apply(self.fx.paths, prepared, uid=self.fx.uid, gid=self.fx.gid)

        self.assertTrue(progress.mutation_started)
        self.assertEqual(progress.staged_files_created, 2)
        self.assertEqual(progress.installed_targets_changed, 2)
        self.assertEqual(self.fx.registry.read_bytes(), DESIRED.read_bytes())
        self.assertEqual(self.fx.hermes.read_bytes(), HERMES.read_bytes())
        self.assertEqual(self.fx.weather.read_bytes(), weather_before)
        self.assertEqual(self.fx.executor.read_bytes(), executor_before)
        self.assertEqual(self.fx.identity.read_bytes(), identity_before)
        self.assertFalse(self.fx.registry_stage.exists())
        self.assertFalse(self.fx.hermes_stage.exists())

        aliases = [
            target["target_alias"]
            for target in json.loads(self.fx.registry.read_text(encoding="utf-8"))["targets"]
        ]
        self.assertEqual(aliases, [adopt.WEATHER_ALIAS, adopt.HERMES_ALIAS])

    def test_registry_mismatch_fails_before_mutation(self) -> None:
        os.chmod(self.fx.registry, 0o644)
        self.fx.registry.write_text('{"unexpected":true}\n', encoding="utf-8")
        os.chmod(self.fx.registry, 0o444)
        with self.assertRaisesRegex(adopt.AdoptionError, "exact reviewed Weather-only baseline"):
            self.fx.preflight()
        self.assertFalse(self.fx.hermes.exists())
        self.assertFalse(self.fx.registry_stage.exists())
        self.assertFalse(self.fx.hermes_stage.exists())

    def test_weather_compose_mismatch_fails_before_mutation(self) -> None:
        os.chmod(self.fx.weather, 0o644)
        self.fx.weather.write_text("drift\n", encoding="utf-8")
        os.chmod(self.fx.weather, 0o444)
        with self.assertRaisesRegex(adopt.AdoptionError, "Weather compose adapter drifted"):
            self.fx.preflight()
        self.assertFalse(self.fx.hermes.exists())

    def test_identity_provenance_mismatch_fails_before_mutation(self) -> None:
        os.chmod(self.fx.identity, 0o644)
        payload = json.loads(adopt._identity_bytes())
        payload["source_sha"] = "0" * 40
        self.fx.identity.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.chmod(self.fx.identity, 0o444)
        with self.assertRaisesRegex(adopt.AdoptionError, "baseline provenance"):
            self.fx.preflight()
        self.assertFalse(self.fx.hermes.exists())

    def test_wrong_type_or_existing_target_fails_before_mutation(self) -> None:
        os.chmod(self.fx.registry, 0o644)
        self.fx.registry.unlink()
        self.fx.registry.symlink_to(BASELINE)
        with self.assertRaisesRegex(adopt.AdoptionError, "not a real regular file"):
            self.fx.preflight()

        self.fx.registry.unlink()
        self.fx.registry.write_bytes(BASELINE.read_bytes())
        os.chmod(self.fx.registry, 0o444)
        self.fx.hermes.write_bytes(HERMES.read_bytes())
        os.chmod(self.fx.hermes, 0o444)
        with self.assertRaisesRegex(adopt.AdoptionError, "must be absent"):
            self.fx.preflight()

    def test_parallel_public_targets_name_is_rejected(self) -> None:
        self.fx.public_registry.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(adopt.AdoptionError, "must be absent"):
            self.fx.preflight()
        self.assertEqual(self.fx.registry.read_bytes(), BASELINE.read_bytes())

    def test_source_contract_binds_hashes_and_preserves_weather_entry(self) -> None:
        self.assertEqual(sha256(BASELINE), adopt.BASELINE_REGISTRY_SHA256)
        self.assertEqual(sha256(DESIRED), adopt.DESIRED_REGISTRY_SHA256)
        self.assertEqual(sha256(WEATHER), adopt.WEATHER_COMPOSE_SHA256)
        self.assertEqual(sha256(HERMES), adopt.HERMES_COMPOSE_SHA256)

        old = json.loads(BASELINE.read_text(encoding="utf-8"))
        new = json.loads(DESIRED.read_text(encoding="utf-8"))
        self.assertEqual(old["targets"][0], new["targets"][0])
        self.assertEqual(
            [target["target_alias"] for target in new["targets"]],
            [adopt.WEATHER_ALIAS, adopt.HERMES_ALIAS],
        )

    def test_cli_exposes_no_arbitrary_runtime_authority(self) -> None:
        parser = adopt._build_parser()
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertEqual(options, {"-h", "--help", "--expected-source-sha", "--apply"})
        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "--path",
            "--env",
            "--command",
            "--target",
            "--repository",
            "shell=True",
            "docker ",
            "systemctl",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_first_install_remains_separate_and_fail_closed(self) -> None:
        first_installer = (ROOT / "scripts/install-simple-deploy-v1.py").read_text(encoding="utf-8")
        self.assertIn(
            "first-install target already exists and needs separate reconciliation",
            first_installer,
        )
        self.assertNotIn("adopt-simple-deploy-hermes-v1", first_installer)

    def test_machine_contract_names_exact_two_file_target_delta(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["issue"], 698)
        self.assertEqual(contract["baseline"]["identity_source_sha"], adopt.BASELINE_SOURCE_SHA)
        self.assertEqual(contract["baseline"]["registry_sha256"], adopt.BASELINE_REGISTRY_SHA256)
        self.assertEqual(contract["desired"]["registry_sha256"], adopt.DESIRED_REGISTRY_SHA256)
        self.assertEqual(contract["desired"]["hermes_compose_sha256"], adopt.HERMES_COMPOSE_SHA256)
        self.assertEqual(
            contract["installed_target_delta"],
            [
                {
                    "operation": "create",
                    "path": "/etc/rozkalns-simple-deployer/compose/hermes-deals-api.yml",
                },
                {
                    "operation": "replace",
                    "path": "/etc/rozkalns-simple-deployer/targets.json",
                },
            ],
        )
        self.assertFalse(contract["authority"]["docker"])
        self.assertFalse(contract["authority"]["systemd"])
        self.assertFalse(contract["authority"]["database_or_data"])
        self.assertFalse(contract["authority"]["secrets_or_credentials"])
        self.assertFalse(contract["authority"]["arbitrary_path_or_command"])


if __name__ == "__main__":
    unittest.main()
