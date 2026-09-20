from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Protocol, Sequence

import simple_deploy_v1 as sd

TARGET_ALIAS = "rozkalns-weather-public-rpi5"
CONSUMER_REPOSITORY = "rozkalnsandris/rozkalns_weather"
IMAGE = "ghcr.io/rozkalnsandris/rozkalns_weather"
COMPOSE_PROJECT = "rozkalns-weather-public"
COMPOSE_FILE = "rozkalns-weather-public.yml"
COMPOSE_SERVICE = "weather"
LOGICAL_VOLUME = "weather_data"
HOST_VOLUME = f"{COMPOSE_PROJECT}_{LOGICAL_VOLUME}"
SCHEMA_SERVICE = "schema-init"
SCHEMA_CONTAINER = "rozkalns-weather-schema-init-v1"
EXPECTED_PRE_SCHEMA_READINESS = 503
PRODUCTION_REGISTRY_PATH = Path("/etc/rozkalns-simple-deployer/targets.json")
PRODUCTION_IDENTITY_PATH = Path("/etc/rozkalns-simple-deployer/identity.json")
PRODUCTION_COMPOSE_ROOT = Path("/etc/rozkalns-simple-deployer/compose")


class SchemaInitError(RuntimeError):
    def __init__(self, code: str, message: str, *, mutation_started: bool = False):
        super().__init__(message)
        self.code = code
        self.mutation_started = mutation_started


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def run(self, argv: Sequence[str], *, timeout_seconds: int, stdin_text: str | None = None) -> CommandResult: ...


class Http(Protocol):
    def get(self, url: str, *, timeout_seconds: int) -> int: ...


class SubprocessRunner:
    def run(self, argv: Sequence[str], *, timeout_seconds: int, stdin_text: str | None = None) -> CommandResult:
        if not argv or any(type(part) is not str or not part for part in argv):
            raise SchemaInitError("COMMAND_CONTRACT", "fixed argv contract invalid")
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": "/nonexistent",
            "DOCKER_CONFIG": "/etc/rozkalns-simple-deployer/docker-anonymous",
        }
        try:
            completed = subprocess.run(
                list(argv), input=stdin_text, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="strict", timeout=timeout_seconds,
                env=env, shell=False, check=False, cwd=str(PRODUCTION_COMPOSE_ROOT),
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
            raise SchemaInitError("COMMAND_TRANSPORT", f"command transport failed: {argv[0]}") from exc
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class LoopbackHttp:
    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, url: str, *, timeout_seconds: int) -> int:
        sd._validate_loopback_url(url, "readiness url")
        request = urllib.request.Request(url, method="GET", headers={"User-Agent": "rozkalns-simple-deploy-schema-init/1"})
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                response.read(1)
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)
        except Exception as exc:
            raise SchemaInitError("READINESS_PROBE_FAILED", "readiness probe transport failed") from exc


def _required(result: CommandResult, code: str, *, mutation_started: bool) -> str:
    if result.returncode != 0:
        raise SchemaInitError(code, f"fixed command failed: {code}", mutation_started=mutation_started)
    if len(result.stdout.encode("utf-8")) > 65536 or len(result.stderr.encode("utf-8")) > 65536:
        raise SchemaInitError(code, "fixed command output exceeded limit", mutation_started=mutation_started)
    return result.stdout


def _override(image_ref: str) -> str:
    return json.dumps({
        "services": {SCHEMA_SERVICE: {"image": image_ref}},
        "volumes": {LOGICAL_VOLUME: {"external": True, "name": HOST_VOLUME}},
    }, sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class Preflight:
    target: sd.TargetSpec
    compose_file: Path
    digest: str
    metadata: sd.ImageMetadata
    readiness_before: int


class WeatherSchemaInit:
    def __init__(self, *, registry_path: Path, identity_path: Path, compose_root: Path, runner: Runner, http: Http, require_root_owned: bool = False):
        self.registry_path = registry_path
        self.identity_path = identity_path
        self.compose_root = compose_root
        self.runner = runner
        self.http = http
        self.require_root_owned = require_root_owned

    def _deployer(self, registry: sd.TargetRegistry, identity: sd.DeployerIdentity) -> sd.SimpleDeployer:
        return sd.SimpleDeployer(
            registry=registry, identity=identity, state=None, runner=self.runner, http=self.http,
            compose_root=self.compose_root, require_root_owned_compose=self.require_root_owned,
        )

    def preflight(self) -> Preflight:
        registry = sd.load_registry(self.registry_path)
        identity = sd.load_identity(self.identity_path)
        if not registry.execution_enabled:
            raise SchemaInitError("REGISTRY_DISABLED", "SIMPLE-DEPLOY registry is disabled")
        target = registry.get(TARGET_ALIAS)
        if (
            target.consumer_repository != CONSUMER_REPOSITORY or target.image != IMAGE
            or target.compose.project != COMPOSE_PROJECT or target.compose.file != COMPOSE_FILE
            or target.compose.service != COMPOSE_SERVICE or target.persistent_volumes != (LOGICAL_VOLUME,)
            or target.registry_pull_profile != "public-anonymous-pull"
            or target.health.readiness_state != "required" or target.health.readiness_url is None
        ):
            raise SchemaInitError("TARGET_CONTRACT_DRIFT", "Weather schema-init target contract drifted")
        deployer = self._deployer(registry, identity)
        try:
            compose_file = deployer._verify_compose_file(target)
            digest = deployer._resolve_pointer(target)
            metadata = deployer._inspect_image(target, digest)
        except sd.SimpleDeployError as exc:
            raise SchemaInitError("IMAGE_CONTRACT_FAILED", "immutable image contract validation failed") from exc
        volume = _required(
            self.runner.run(("docker", "volume", "inspect", "--format", "{{.Name}}", HOST_VOLUME), timeout_seconds=30),
            "VOLUME_IDENTITY_FAILED", mutation_started=False,
        ).strip()
        if volume != HOST_VOLUME:
            raise SchemaInitError("VOLUME_IDENTITY_FAILED", "existing Weather volume identity does not match")
        existing = _required(
            self.runner.run(("docker", "ps", "-a", "--filter", f"name=^/{SCHEMA_CONTAINER}$", "--format", "{{.Names}}"), timeout_seconds=30),
            "SCHEMA_CONTAINER_DISCOVERY_FAILED", mutation_started=False,
        ).strip()
        if existing:
            raise SchemaInitError("PRIOR_ATTEMPT_PRESENT", "fixed schema-init evidence container already exists")
        try:
            readiness = self.http.get(target.health.readiness_url, timeout_seconds=10)
        except SchemaInitError:
            raise
        if readiness not in (200, EXPECTED_PRE_SCHEMA_READINESS):
            raise SchemaInitError("PRE_SCHEMA_READINESS_DRIFT", "pre-schema readiness status is neither 200 nor expected 503")
        return Preflight(target, compose_file, digest, metadata, readiness)

    def apply(self) -> dict[str, object]:
        preflight = self.preflight()
        if preflight.readiness_before == 200:
            return self._receipt("NO_OP_ALREADY_READY", preflight, mutation_started=False, readiness_after=200, pointer_changed=False)
        image_ref = f"{preflight.target.image}@{preflight.digest}"
        mutation_started = True
        _required(
            self.runner.run(("docker", "pull", image_ref), timeout_seconds=900),
            "IMMUTABLE_IMAGE_PULL_FAILED", mutation_started=True,
        )
        prefix = (
            "docker", "compose", "--project-name", COMPOSE_PROJECT,
            "--file", str(preflight.compose_file), "--file", "-", "--profile", "bootstrap",
        )
        _required(
            self.runner.run(
                (*prefix, "run", "--no-deps", "--pull", "never", "--name", SCHEMA_CONTAINER, SCHEMA_SERVICE),
                timeout_seconds=300, stdin_text=_override(image_ref),
            ),
            "SCHEMA_INIT_FAILED", mutation_started=True,
        )
        try:
            readiness_after = self.http.get(preflight.target.health.readiness_url, timeout_seconds=10)
        except SchemaInitError as exc:
            raise SchemaInitError(exc.code, str(exc), mutation_started=True) from exc
        if readiness_after != 200:
            raise SchemaInitError("POST_SCHEMA_READINESS_FAILED", "readiness did not become 200 after schema init", mutation_started=True)
        try:
            registry = sd.load_registry(self.registry_path)
            identity = sd.load_identity(self.identity_path)
            pointer_after = self._deployer(registry, identity)._resolve_pointer(preflight.target)
        except sd.SimpleDeployError as exc:
            raise SchemaInitError("POINTER_RECHECK_FAILED", "production pointer recheck failed", mutation_started=True) from exc
        pointer_changed = pointer_after != preflight.digest
        if pointer_changed:
            raise SchemaInitError("POINTER_CHANGED", "production pointer changed during schema-init attempt", mutation_started=True)
        return self._receipt("PASS", preflight, mutation_started=mutation_started, readiness_after=readiness_after, pointer_changed=False)

    @staticmethod
    def _receipt(result: str, preflight: Preflight, *, mutation_started: bool, readiness_after: int, pointer_changed: bool) -> dict[str, object]:
        return {
            "schema": "rozkalns.rpi5-main.simple-deploy.weather-schema-init.v1",
            "result": result,
            "target_alias": TARGET_ALIAS,
            "consumer_repository": CONSUMER_REPOSITORY,
            "consumer_source_sha": preflight.metadata.source_sha,
            "shared_workflow_sha": preflight.metadata.shared_workflow_sha,
            "image_ref": f"{preflight.target.image}@{preflight.digest}",
            "persistent_volume": HOST_VOLUME,
            "schema_service": SCHEMA_SERVICE,
            "schema_container": SCHEMA_CONTAINER,
            "readiness_before": preflight.readiness_before,
            "readiness_after": readiness_after,
            "pointer_changed_during_attempt": pointer_changed,
            "mutation_started": mutation_started,
            "database_schema_mutation": mutation_started,
            "corpus_backfill": False,
            "volume_create_delete_recreate": False,
            "ordinary_reconciliation": False,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
        }


def production_bridge() -> WeatherSchemaInit:
    sd._require_production_file(PRODUCTION_REGISTRY_PATH)
    sd._require_production_file(PRODUCTION_IDENTITY_PATH)
    return WeatherSchemaInit(
        registry_path=PRODUCTION_REGISTRY_PATH,
        identity_path=PRODUCTION_IDENTITY_PATH,
        compose_root=PRODUCTION_COMPOSE_ROOT,
        runner=SubprocessRunner(), http=LoopbackHttp(), require_root_owned=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args:
        print(json.dumps({"result": "PRE_MUTATION_FAILURE", "error_code": "ARGUMENTS_FORBIDDEN", "mutation_started": False}, sort_keys=True))
        return 2
    try:
        receipt = production_bridge().apply()
    except SchemaInitError as exc:
        print(json.dumps({
            "schema": "rozkalns.rpi5-main.simple-deploy.weather-schema-init.v1",
            "result": "STOP_ERROR" if exc.mutation_started else "PRE_MUTATION_FAILURE",
            "error_code": exc.code,
            "mutation_started": exc.mutation_started,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
        }, sort_keys=True))
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0
