#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/lib/deploy_executor/simple_deploy_v1.py"
spec = importlib.util.spec_from_file_location("simple_deploy_v1", MODULE_PATH)
assert spec and spec.loader
sd = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sd
spec.loader.exec_module(sd)

SHARED_SHA = "e05ed760791a127c7c9628696806ef39c9fe329c"
SOURCE_SHA = "a" * 40
DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64
CONTAINER_ID = "3" * 64


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def target_payload(compose_hash: str) -> dict:
    return {
        "target_alias": "weather-canary",
        "consumer_repository": "rozkalnsandris/example-service",
        "image": "ghcr.io/rozkalnsandris/example-service",
        "architecture": "linux/arm64",
        "shared_workflow_sha": SHARED_SHA,
        "compose": {
            "project": "weather-canary",
            "file": "weather-canary.yml",
            "file_sha256": compose_hash,
            "service": "weather",
        },
        "health": {
            "liveness_url": "http://127.0.0.1:8080/health",
            "readiness_state": "required",
            "readiness_url": "http://127.0.0.1:8080/ready",
        },
        "wait_timeout_seconds": 60,
        "receipt_name": "weather-canary.json",
        "persistent_volumes": ["weather_data"],
        "registry_pull_profile": "public-anonymous-pull",
        "forbidden_operations": list(sd.FORBIDDEN_OPERATIONS),
    }


def registry_payload(compose_hash: str, *, enabled: bool = True) -> dict:
    return {
        "schema": sd.REGISTRY_SCHEMA,
        "schema_version": 1,
        "execution_enabled": enabled,
        "targets": [target_payload(compose_hash)],
    }


class FakeRunner:
    def __init__(self, *, pointer_after: str = DIGEST_A, failures: set[str] | None = None):
        self.pointer_calls = 0
        self.pointer_after = pointer_after
        self.failures = failures or set()
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, timeout_seconds):
        call = tuple(argv)
        self.calls.append(call)
        joined = " ".join(argv)
        for marker in self.failures:
            if marker in joined:
                return sd.CommandResult(1, "", "synthetic failure")

        if argv[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            ref = argv[4]
            if ref.endswith(":production"):
                self.pointer_calls += 1
                digest = DIGEST_A if self.pointer_calls == 1 else self.pointer_after
                return sd.CommandResult(0, json.dumps({"digest": digest}) + "\n", "")
            if ref == f"ghcr.io/rozkalnsandris/example-service@{DIGEST_A}":
                return sd.CommandResult(
                    0,
                    json.dumps(
                        {
                            "os": "linux",
                            "architecture": "arm64",
                            "config": {
                                "Labels": {
                                    "org.opencontainers.image.revision": SOURCE_SHA,
                                    "io.rozkalns.simple-deploy.target": "weather-canary",
                                    "io.rozkalns.simple-deploy.shared-revision": SHARED_SHA,
                                }
                            },
                        }
                    )
                    + "\n",
                    "",
                )
        if argv[:2] == ["docker", "compose"] and "ps" in argv:
            return sd.CommandResult(0, CONTAINER_ID + "\n", "")
        if argv[:2] == ["docker", "inspect"]:
            return sd.CommandResult(
                0,
                f"ghcr.io/rozkalnsandris/example-service@{DIGEST_A}\n",
                "",
            )
        if argv[:2] == ["docker", "compose"]:
            return sd.CommandResult(0, "", "")
        raise AssertionError(f"unexpected command: {argv}")


class RaisingRunner(FakeRunner):
    def run(self, argv, *, timeout_seconds):
        if argv[:2] == ["docker", "compose"] and "pull" in argv:
            raise sd.SimpleDeployError("COMMAND_FAILED", "synthetic transport")
        return super().run(argv, timeout_seconds=timeout_seconds)


class FakeHttp:
    def __init__(self, statuses=None):
        self.statuses = statuses or {}
        self.calls: list[str] = []

    def get(self, url, *, timeout_seconds):
        self.calls.append(url)
        return self.statuses.get(url, 200)


class Fixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.compose_root = self.root / "compose"
        self.compose_root.mkdir(mode=0o700)
        self.compose = self.compose_root / "weather-canary.yml"
        self.compose.write_text("services:\n  weather:\n    image: placeholder.invalid/example\n", encoding="utf-8")
        self.compose.chmod(0o600)
        self.registry_path = self.root / "targets.json"
        self.state_root = self.root / "state"
        self.identity = sd.DeployerIdentity("b" * 40)

    def close(self):
        self.temp.cleanup()

    def write_registry(self, payload=None):
        body = registry_payload(sha256(self.compose)) if payload is None else payload
        self.registry_path.write_text(json.dumps(body), encoding="utf-8")
        return sd.load_registry(self.registry_path)

    def deployer(self, runner=None, http=None, payload=None):
        return sd.SimpleDeployer(
            registry=self.write_registry(payload),
            identity=self.identity,
            state=sd.StateStore(self.state_root),
            runner=runner or FakeRunner(),
            http=http or FakeHttp(),
            compose_root=self.compose_root,
        )


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    def test_repository_registry_binds_exact_reviewed_targets(self):
        registry = sd.load_registry(ROOT / "ops/deploy/simple-deploy-targets-v1.json")
        self.assertTrue(registry.execution_enabled)
        self.assertEqual(len(registry.targets), 3)

        weather = registry.get("rozkalns-weather-public-rpi5")
        self.assertEqual(weather.consumer_repository, "rozkalnsandris/rozkalns_weather")
        self.assertEqual(weather.image, "ghcr.io/rozkalnsandris/rozkalns_weather")
        self.assertEqual(weather.shared_workflow_sha, SHARED_SHA)
        self.assertEqual(weather.compose.project, "rozkalns-weather-public")
        self.assertEqual(weather.compose.file, "rozkalns-weather-public.yml")
        self.assertEqual(weather.compose.service, "weather")
        self.assertEqual(weather.health.liveness_url, "http://127.0.0.1:9180/health")
        self.assertEqual(weather.health.readiness_state, "required")
        self.assertEqual(weather.health.readiness_url, "http://127.0.0.1:9180/ready")
        self.assertEqual(weather.wait_timeout_seconds, 180)
        self.assertEqual(weather.persistent_volumes, ("weather_data",))
        self.assertEqual(weather.registry_pull_profile, "public-anonymous-pull")
        self.assertEqual(weather.forbidden_operations, sd.FORBIDDEN_OPERATIONS)

        weather_compose = ROOT / "ops/deploy/simple-deploy-compose" / weather.compose.file
        self.assertTrue(weather_compose.is_file())
        self.assertEqual(sha256(weather_compose), weather.compose.file_sha256)
        self.assertEqual(
            weather.compose.file_sha256,
            "80e2b47e4ed039c38285094e0b273fbc884f0a34ff34d8b201d8e93323af1f32",
        )

        hermes = registry.get("hermes-deals")
        self.assertEqual(hermes.consumer_repository, "rozkalnsandris/hermes-deals")
        self.assertEqual(hermes.image, "ghcr.io/rozkalnsandris/hermes-deals")
        self.assertEqual(hermes.shared_workflow_sha, SHARED_SHA)
        self.assertEqual(hermes.compose.project, "hermes-deals")
        self.assertEqual(hermes.compose.file, "hermes-deals-api.yml")
        self.assertEqual(hermes.compose.service, "api")
        self.assertEqual(hermes.health.liveness_url, "http://127.0.0.1:9128/api/health")
        self.assertEqual(hermes.health.readiness_state, "not-applicable")
        self.assertIsNone(hermes.health.readiness_url)
        self.assertEqual(hermes.wait_timeout_seconds, 180)
        self.assertEqual(hermes.persistent_volumes, ("hermes_deals_pgdata",))
        self.assertEqual(hermes.registry_pull_profile, "public-anonymous-pull")
        self.assertEqual(hermes.forbidden_operations, sd.FORBIDDEN_OPERATIONS)

        hermes_compose = ROOT / "ops/deploy/simple-deploy-compose" / hermes.compose.file
        self.assertTrue(hermes_compose.is_file())
        self.assertEqual(sha256(hermes_compose), hermes.compose.file_sha256)
        self.assertEqual(
            hermes.compose.file_sha256,
            "644dc72da5dc13ee532dd29693db31358451669bb44de4df4b62c41736903f1c",
        )

    def test_valid_static_target_parses(self):
        registry = self.fx.write_registry()
        target = registry.get("weather-canary")
        self.assertEqual(target.image, "ghcr.io/rozkalnsandris/example-service")
        self.assertEqual(target.shared_workflow_sha, SHARED_SHA)
        self.assertEqual(target.forbidden_operations, sd.FORBIDDEN_OPERATIONS)

    def test_unknown_authority_fields_are_rejected(self):
        for field, value in (
            ("command", ["sh", "-c", "id"]),
            ("path", "/tmp/arbitrary"),
            ("secret", "not-a-real-secret"),
            ("environment", {"X": "Y"}),
        ):
            with self.subTest(field=field):
                payload = registry_payload(sha256(self.fx.compose))
                payload["targets"][0][field] = value
                self.fx.registry_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(sd.SimpleDeployError, "REGISTRY_SCHEMA"):
                    sd.load_registry(self.fx.registry_path)

    def test_compose_file_cannot_be_path_authority(self):
        for value in ("../compose.yml", "/etc/compose.yml", "nested/compose.yml", "compose"):
            with self.subTest(value=value):
                payload = registry_payload(sha256(self.fx.compose))
                payload["targets"][0]["compose"]["file"] = value
                self.fx.registry_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(sd.SimpleDeployError):
                    sd.load_registry(self.fx.registry_path)

    def test_health_endpoint_must_be_fixed_loopback(self):
        for value in (
            "https://127.0.0.1:8080/health",
            "http://localhost:8080/health",
            "http://127.0.0.1/health",
            "http://user:pw@127.0.0.1:8080/health",
            "http://127.0.0.1:8080/health?token=x",
        ):
            with self.subTest(value=value):
                payload = registry_payload(sha256(self.fx.compose))
                payload["targets"][0]["health"]["liveness_url"] = value
                self.fx.registry_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(sd.SimpleDeployError):
                    sd.load_registry(self.fx.registry_path)

    def test_image_architecture_and_exclusions_are_fixed(self):
        cases = (
            ("image", "ghcr.io/other/example-service"),
            ("architecture", "linux/amd64"),
            ("forbidden_operations", list(sd.FORBIDDEN_OPERATIONS[:-1])),
        )
        for field, value in cases:
            with self.subTest(field=field):
                payload = registry_payload(sha256(self.fx.compose))
                payload["targets"][0][field] = value
                self.fx.registry_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(sd.SimpleDeployError):
                    sd.load_registry(self.fx.registry_path)


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    def test_new_digest_deploys_exact_digest_and_records_success(self):
        runner = FakeRunner()
        http = FakeHttp()
        deployer = self.fx.deployer(runner=runner, http=http)
        result = deployer.reconcile("weather-canary")
        self.assertEqual(result.result, "SUCCESS")
        self.assertEqual(result.desired_digest, DIGEST_A)
        self.assertTrue(result.mutation_started)
        self.assertFalse(result.pointer_changed_during_attempt)

        calls = [" ".join(call) for call in runner.calls]
        self.assertTrue(any(" compose " in f" {call} " and " pull weather" in call for call in calls))
        self.assertTrue(any(" up -d --wait --wait-timeout 60 weather" in call for call in calls))
        self.assertFalse(any(" down" in call or "volume rm" in call or "sudo" in call for call in calls))

        override = self.fx.state_root / "overrides/weather-canary.yaml"
        self.assertIn(
            f"ghcr.io/rozkalnsandris/example-service@{DIGEST_A}",
            override.read_text(encoding="utf-8"),
        )
        receipt = json.loads((self.fx.state_root / "receipts/weather-canary.json").read_text())
        self.assertEqual(receipt["deployed_digest"], DIGEST_A)
        self.assertEqual(receipt["consumer_source_sha"], SOURCE_SHA)
        self.assertEqual(receipt["shared_workflow_sha"], SHARED_SHA)
        self.assertEqual(receipt["health"]["readiness"], "PASS")
        self.assertEqual(http.calls, [
            "http://127.0.0.1:8080/health",
            "http://127.0.0.1:8080/ready",
        ])

    def test_same_successful_digest_is_no_op(self):
        first = FakeRunner()
        deployer = self.fx.deployer(runner=first)
        self.assertEqual(deployer.reconcile("weather-canary").result, "SUCCESS")

        second = FakeRunner()
        deployer2 = self.fx.deployer(runner=second)
        result = deployer2.reconcile("weather-canary")
        self.assertEqual(result.result, "NO_OP_CURRENT")
        self.assertFalse(result.mutation_started)
        self.assertFalse(any(call[:2] == ("docker", "compose") for call in second.calls))

    def test_pointer_change_during_attempt_waits_for_next_reconciliation(self):
        runner = FakeRunner(pointer_after=DIGEST_B)
        result = self.fx.deployer(runner=runner).reconcile("weather-canary")
        self.assertEqual(result.result, "SUCCESS")
        self.assertEqual(result.desired_digest, DIGEST_A)
        self.assertTrue(result.pointer_changed_during_attempt)
        receipt = json.loads((self.fx.state_root / "receipts/weather-canary.json").read_text())
        self.assertEqual(receipt["pointer_digest_before"], DIGEST_A)
        self.assertEqual(receipt["pointer_digest_after"], DIGEST_B)
        self.assertTrue(receipt["pointer_changed_during_attempt"])
        self.assertEqual(receipt["deployed_digest"], DIGEST_A)

    def test_readiness_not_applicable_is_explicit(self):
        payload = registry_payload(sha256(self.fx.compose))
        payload["targets"][0]["health"]["readiness_state"] = "not-applicable"
        payload["targets"][0]["health"]["readiness_url"] = None
        http = FakeHttp()
        result = self.fx.deployer(http=http, payload=payload).reconcile("weather-canary")
        self.assertEqual(result.result, "SUCCESS")
        self.assertEqual(http.calls, ["http://127.0.0.1:8080/health"])
        receipt = json.loads((self.fx.state_root / "receipts/weather-canary.json").read_text())
        self.assertEqual(receipt["health"]["readiness"], "NOT_APPLICABLE")

    def test_private_pull_profile_is_separate_and_pre_mutation(self):
        payload = registry_payload(sha256(self.fx.compose))
        payload["targets"][0]["registry_pull_profile"] = "private-read-only"
        runner = FakeRunner()
        with self.assertRaisesRegex(sd.SimpleDeployError, "PRIVATE_AUTH_NOT_ACTIVATED") as caught:
            self.fx.deployer(runner=runner, payload=payload).reconcile("weather-canary")
        self.assertFalse(caught.exception.mutation_started)
        self.assertEqual(runner.calls, [])
        status = json.loads((self.fx.state_root / "status/weather-canary.json").read_text())
        self.assertEqual(status["result"], "PRE_MUTATION_FAILURE")
        self.assertFalse(status["blocked"])

    def test_compose_hash_drift_fails_before_mutation(self):
        deployer = self.fx.deployer()
        self.fx.compose.write_text("drift\n", encoding="utf-8")
        with self.assertRaisesRegex(sd.SimpleDeployError, "COMPOSE_CONTRACT_INVALID") as caught:
            deployer.reconcile("weather-canary")
        self.assertFalse(caught.exception.mutation_started)
        status = json.loads((self.fx.state_root / "status/weather-canary.json").read_text())
        self.assertEqual(status["result"], "PRE_MUTATION_FAILURE")
        self.assertFalse(status["blocked"])

    def test_pull_failure_blocks_future_automatic_attempts(self):
        runner = FakeRunner(failures={" pull weather"})
        deployer = self.fx.deployer(runner=runner)
        with self.assertRaisesRegex(sd.SimpleDeployError, "COMPOSE_PULL_FAILED") as caught:
            deployer.reconcile("weather-canary")
        self.assertTrue(caught.exception.mutation_started)
        status = json.loads((self.fx.state_root / "status/weather-canary.json").read_text())
        self.assertEqual(status["result"], "STOP_ERROR")
        self.assertTrue(status["blocked"])
        count = len(runner.calls)
        result = deployer.reconcile("weather-canary")
        self.assertEqual(result.result, "BLOCKED_STOP_ERROR")
        self.assertEqual(len(runner.calls), count)

    def test_runner_transport_failure_is_post_mutation(self):
        runner = RaisingRunner()
        with self.assertRaisesRegex(sd.SimpleDeployError, "COMPOSE_PULL_FAILED") as caught:
            self.fx.deployer(runner=runner).reconcile("weather-canary")
        self.assertTrue(caught.exception.mutation_started)
        status = json.loads((self.fx.state_root / "status/weather-canary.json").read_text())
        self.assertEqual(status["result"], "STOP_ERROR")
        self.assertTrue(status["mutation_started"])

    def test_liveness_failure_blocks_target(self):
        http = FakeHttp({"http://127.0.0.1:8080/health": 503})
        with self.assertRaisesRegex(sd.SimpleDeployError, "LIVENESS_FAILED") as caught:
            self.fx.deployer(http=http).reconcile("weather-canary")
        self.assertTrue(caught.exception.mutation_started)
        status = json.loads((self.fx.state_root / "status/weather-canary.json").read_text())
        self.assertEqual(status["result"], "STOP_ERROR")

    def test_readiness_failure_blocks_target(self):
        http = FakeHttp({"http://127.0.0.1:8080/ready": 503})
        with self.assertRaisesRegex(sd.SimpleDeployError, "READINESS_FAILED") as caught:
            self.fx.deployer(http=http).reconcile("weather-canary")
        self.assertTrue(caught.exception.mutation_started)
        status = json.loads((self.fx.state_root / "status/weather-canary.json").read_text())
        self.assertEqual(status["result"], "STOP_ERROR")
        self.assertTrue(status["blocked"])

    def test_compose_up_timeout_like_transport_failure_blocks_target(self):
        class TimeoutRunner(FakeRunner):
            def run(self, argv, *, timeout_seconds):
                if argv[:2] == ["docker", "compose"] and "up" in argv:
                    raise sd.SimpleDeployError("COMMAND_FAILED", "synthetic timeout")
                return super().run(argv, timeout_seconds=timeout_seconds)

        with self.assertRaisesRegex(sd.SimpleDeployError, "COMPOSE_UP_FAILED") as caught:
            self.fx.deployer(runner=TimeoutRunner()).reconcile("weather-canary")
        self.assertTrue(caught.exception.mutation_started)
        status = json.loads((self.fx.state_root / "status/weather-canary.json").read_text())
        self.assertEqual(status["result"], "STOP_ERROR")
        self.assertTrue(status["blocked"])

    def test_running_container_must_use_frozen_digest(self):
        class WrongImageRunner(FakeRunner):
            def run(self, argv, *, timeout_seconds):
                if argv[:2] == ["docker", "inspect"]:
                    self.calls.append(tuple(argv))
                    return sd.CommandResult(0, "ghcr.io/rozkalnsandris/example-service:production\n", "")
                return super().run(argv, timeout_seconds=timeout_seconds)

        with self.assertRaisesRegex(sd.SimpleDeployError, "CONTAINER_IDENTITY_FAILED") as caught:
            self.fx.deployer(runner=WrongImageRunner()).reconcile("weather-canary")
        self.assertTrue(caught.exception.mutation_started)

    def test_disabled_registry_never_resolves_target_or_runs_commands(self):
        payload = registry_payload(sha256(self.fx.compose), enabled=False)
        runner = FakeRunner()
        result = self.fx.deployer(runner=runner, payload=payload).reconcile("arbitrary-not-allowlisted")
        self.assertEqual(result.result, "DISABLED")
        self.assertEqual(runner.calls, [])


class ContractTests(unittest.TestCase):
    def test_machine_contract_tracks_reviewed_targets_and_pins_shared_revision(self):
        contract = json.loads((ROOT / "ops/contracts/simple-deploy-host-v1.json").read_text())
        self.assertEqual(contract["issue"], 666)
        self.assertEqual(
            contract["status"],
            "WEATHER_ACTIVE_HERMES_DEALS_AND_TECH_SOURCE_TARGETS_REGISTERED_LIVE_CUTOVERS_REQUIRED",
        )
        self.assertEqual(contract["shared_contract"]["revision"], SHARED_SHA)
        self.assertTrue(contract["registry"]["execution_enabled_in_source"])
        self.assertEqual(contract["registry"]["initial_targets"], 1)
        self.assertEqual(contract["registry"]["current_reviewed_targets"], 3)
        self.assertTrue(contract["registry"]["target_adoption_requires_tracked_source_change"])
        reviewed = contract["registry"]["reviewed_targets"]
        self.assertEqual(len(reviewed), 3)
        self.assertEqual(reviewed[0]["target_alias"], "rozkalns-weather-public-rpi5")
        self.assertEqual(
            reviewed[0]["consumer_contract_revision"],
            "606981d10eee59d13b802f6a682abf1daa2aa8a5",
        )
        self.assertEqual(reviewed[0]["wait_timeout_seconds"], 180)
        self.assertEqual(reviewed[1]["target_alias"], "hermes-deals")
        self.assertEqual(
            reviewed[1]["consumer_contract_revision"],
            "13f9fb69b9576d8e97ab3a85334927f3c576ca1c",
        )
        self.assertEqual(reviewed[1]["compatibility_prerequisite_issue"], 690)
        self.assertEqual(reviewed[1]["source_registration_issue"], 692)
        self.assertEqual(
            reviewed[1]["compose_sha256"],
            "644dc72da5dc13ee532dd29693db31358451669bb44de4df4b62c41736903f1c",
        )
        self.assertEqual(reviewed[1]["liveness_url"], "http://127.0.0.1:9128/api/health")
        self.assertEqual(reviewed[1]["readiness_state"], "not-applicable")
        self.assertEqual(reviewed[1]["wait_timeout_seconds"], 180)
        self.assertEqual(reviewed[1]["registry_pull_profile"], "public-anonymous-pull")
        self.assertEqual(reviewed[2]["target_alias"], "hermes-tech-public-rpi5")
        self.assertTrue(contract["activation"]["separate_exact_live_cutover_required"])
        self.assertFalse(contract["activation"]["source_merge_installs_or_enables_runtime"])
        self.assertTrue(
            contract["activation"]["hermes_target_installation_requires_separate_exact_live_cutover"]
        )
        self.assertTrue(
            contract["activation"]["hermes_private_runtime_config_provisioning_requires_separate_exact_authority"]
        )
        bridge = contract["schema_init_bridge"]
        self.assertEqual(bridge["execution_user"], "rozkalns-simple-deployer")
        self.assertEqual(bridge["docker_state_root"], "/var/lib/rozkalns-simple-deployer")
        self.assertEqual(bridge["exact_preflight_argv"], ["--preflight"])
        self.assertTrue(bridge["post_install_repair_required_after_phase_a_base_b57ed42"])
        self.assertFalse(bridge["post_install_repair_runs_docker_or_data"])

    def test_normative_doc_keeps_activation_separate(self):
        doc = (ROOT / "docs/SIMPLE_DEPLOY_HOST_V1.md").read_text(encoding="utf-8")
        self.assertIn("Phase A install-only completed", doc)
        self.assertIn("Phase B is stopped pre-mutation", doc)
        self.assertIn("Phase-B post-install execution/state correction", doc)
        self.assertIn("separate exact LIVE authorization", doc)
        self.assertIn("execution_enabled: true", doc)
        self.assertIn("rozkalns-weather-public-rpi5", doc)
        self.assertIn("hermes-deals", doc)
        self.assertIn("Target adoption remains a tracked source review", doc)
        self.assertIn("Source readiness is not LIVE authority", doc)


class SourceBoundaryTests(unittest.TestCase):
    def test_cli_surface_has_no_runtime_image_path_service_or_command_inputs(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('group.add_argument("--all"', source)
        self.assertIn('group.add_argument("--target"', source)
        for forbidden in ('add_argument("--image"', 'add_argument("--path"', 'add_argument("--service"', 'add_argument("--command"', 'shell=True', 'sudo '):
            self.assertNotIn(forbidden, source)

    def test_ordinary_mutation_surface_excludes_destructive_compose_actions(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"down"', source)
        self.assertNotIn('"volume", "rm"', source)
        self.assertNotIn('"systemctl"', source)
        self.assertNotIn('"docker", "login"', source)

    def test_systemd_source_is_not_privileged_root_service(self):
        unit = (ROOT / "ops/systemd/rozkalns-simple-deployer.service").read_text(encoding="utf-8")
        self.assertIn("User=rozkalns-simple-deployer", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertNotIn("User=root", unit)
        self.assertNotIn("LoadCredential=", unit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
