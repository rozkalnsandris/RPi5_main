from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Mapping, Protocol, Sequence

import simple_deploy_v1 as sd
import simple_deploy_weather_schema_init_v1 as schema_bridge

TARGET_ALIAS = "rozkalns-weather-public-rpi5"
CONSUMER_REPOSITORY = "rozkalnsandris/rozkalns_weather"
IMAGE = "ghcr.io/rozkalnsandris/rozkalns_weather"
EXPECTED_BOOTSTRAP_SOURCE_SHA = "789a79820807829cc9b057d9ffafc56e0e41afe9"
COMPOSE_PROJECT = "rozkalns-weather-public"
COMPOSE_FILE = "rozkalns-weather-public.yml"
COMPOSE_SERVICE = "weather"
LOGICAL_VOLUME = "weather_data"
HOST_VOLUME = f"{COMPOSE_PROJECT}_{LOGICAL_VOLUME}"
DATABASE_URL = "sqlite:///data/weather.db"
BOOTSTRAP_START_DATE = "2026-04-02"
BOOTSTRAP_END_DATE = "2026-09-10"
RECURRING_INTEGRITY_START_DATE = "2026-08-13"
RECURRING_INTEGRITY_END_DATE = "2026-08-26"
MODELS = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")
RUN_HOURS = "0,6,12,18"
TRUTH_CHUNK_DAYS = "14"
RATE_LIMIT_SECONDS = "1.0"
RECOVERY_VERIFIED_BACKUP = "verified_backup_available"
RECOVERY_ACCEPT_NO_BACKUP = "owner_accepts_proceeding_without_prewrite_backup"
RECOVERY_DECISIONS = (RECOVERY_VERIFIED_BACKUP, RECOVERY_ACCEPT_NO_BACKUP)
INGEST_SERVICE_UNIT = "rozkalns-weather-public-ingest.service"
INGEST_TIMER_UNIT = "rozkalns-weather-public-ingest.timer"
CAPABILITY_IDENTITY_SCHEMA = "rozkalns.rpi5-main.simple-deploy.weather-data.identity.v1"
HOST_REPOSITORY = "rozkalnsandris/RPi5_main"
PRODUCTION_CAPABILITY_IDENTITY_PATH = Path("/etc/rozkalns-simple-deployer/weather-data-v1.identity.json")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{12,64}$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

PRODUCTION_REGISTRY_PATH = schema_bridge.PRODUCTION_REGISTRY_PATH
PRODUCTION_IDENTITY_PATH = schema_bridge.PRODUCTION_IDENTITY_PATH
PRODUCTION_COMPOSE_ROOT = schema_bridge.PRODUCTION_COMPOSE_ROOT
PRODUCTION_STATE_ROOT = schema_bridge.PRODUCTION_STATE_ROOT

CHECKPOINT_NAMES = (
    "truth.json",
    "icon_d2.json",
    "ecmwf_ifs.json",
    "ecmwf_aifs.json",
)
CHECKPOINT_PROBE = (
    "import json,pathlib,sys;"
    "root=pathlib.Path(sys.argv[1]);"
    "names=('truth.json','icon_d2.json','ecmwf_ifs.json','ecmwf_aifs.json');"
    "print(json.dumps({name:(root/name).exists() for name in names},sort_keys=True))"
)


class WeatherDataError(RuntimeError):
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


class SubprocessRunner:
    def __init__(self, *, state_root: Path):
        self.state_root = state_root
        self.docker_config = state_root / "docker-anonymous"
        self.buildx_config = self.docker_config / "buildx"

    def run(self, argv: Sequence[str], *, timeout_seconds: int, stdin_text: str | None = None) -> CommandResult:
        if not argv or any(type(part) is not str or not part for part in argv):
            raise WeatherDataError("COMMAND_CONTRACT", "fixed argv contract invalid")
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": str(self.state_root),
            "DOCKER_CONFIG": str(self.docker_config),
            "BUILDX_CONFIG": str(self.buildx_config),
        }
        try:
            completed = subprocess.run(
                list(argv),
                input=stdin_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=timeout_seconds,
                env=env,
                shell=False,
                check=False,
                cwd=str(PRODUCTION_COMPOSE_ROOT),
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
            raise WeatherDataError("COMMAND_TRANSPORT", f"command transport failed: {argv[0]}") from exc
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class CapabilityIdentity:
    source_sha: str


@dataclass(frozen=True)
class Preflight:
    target: sd.TargetSpec
    compose_file: Path
    digest: str
    metadata: sd.ImageMetadata
    capability_source_sha: str
    container_id: str
    local_image_id: str


def load_capability_identity(path: Path) -> CapabilityIdentity:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WeatherDataError("CAPABILITY_IDENTITY_INVALID", "Weather data capability identity cannot be loaded") from exc
    if type(payload) is not dict or set(payload) != {"schema", "repository", "source_sha"}:
        raise WeatherDataError("CAPABILITY_IDENTITY_INVALID", "Weather data capability identity schema drifted")
    if payload["schema"] != CAPABILITY_IDENTITY_SCHEMA or payload["repository"] != HOST_REPOSITORY:
        raise WeatherDataError("CAPABILITY_IDENTITY_INVALID", "Weather data capability identity repository/schema drifted")
    source_sha = payload["source_sha"]
    if type(source_sha) is not str or SHA_RE.fullmatch(source_sha) is None:
        raise WeatherDataError("CAPABILITY_IDENTITY_INVALID", "Weather data capability source SHA is invalid")
    return CapabilityIdentity(source_sha)


def _required(result: CommandResult, code: str, *, mutation_started: bool, allowed_returncodes: tuple[int, ...] = (0,)) -> str:
    if result.returncode not in allowed_returncodes:
        raise WeatherDataError(code, f"fixed command failed: {code}", mutation_started=mutation_started)
    if len(result.stdout.encode("utf-8")) > 262144 or len(result.stderr.encode("utf-8")) > 65536:
        raise WeatherDataError(code, "fixed command output exceeded limit", mutation_started=mutation_started)
    return result.stdout


def _json_object(result: CommandResult, code: str, *, mutation_started: bool) -> dict[str, object]:
    text = _required(result, code, mutation_started=mutation_started)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WeatherDataError(code, f"{code} did not return JSON", mutation_started=mutation_started) from exc
    if type(value) is not dict:
        raise WeatherDataError(code, f"{code} did not return a JSON object", mutation_started=mutation_started)
    return value


def fixed_bootstrap_commands(fingerprint: str) -> tuple[tuple[str, ...], ...]:
    if FINGERPRINT_RE.fullmatch(fingerprint) is None:
        raise WeatherDataError("BOOTSTRAP_FINGERPRINT_INVALID", "bootstrap fingerprint is not lowercase SHA-256")
    checkpoint_root = f"/app/data/production-bootstrap-v1/{fingerprint}"
    commands: list[tuple[str, ...]] = [
        (
            "python", "-m", "rozkalns_weather.backfill",
            "--database-url", DATABASE_URL,
            "truth",
            "--start", BOOTSTRAP_START_DATE,
            "--end", BOOTSTRAP_END_DATE,
            "--checkpoint", f"{checkpoint_root}/truth.json",
            "--chunk-days", TRUTH_CHUNK_DAYS,
            "--rate-limit-seconds", RATE_LIMIT_SECONDS,
        )
    ]
    for model in MODELS:
        commands.append(
            (
                "python", "-m", "rozkalns_weather.backfill",
                "--database-url", DATABASE_URL,
                "forecast",
                "--model", model,
                "--start", BOOTSTRAP_START_DATE,
                "--end", BOOTSTRAP_END_DATE,
                "--run-hours", RUN_HOURS,
                "--checkpoint", f"{checkpoint_root}/{model}.json",
                "--rate-limit-seconds", RATE_LIMIT_SECONDS,
            )
        )
    return tuple(commands)


class WeatherDataBridge:
    def __init__(
        self,
        *,
        registry_path: Path,
        identity_path: Path,
        capability_identity_path: Path,
        compose_root: Path,
        runner: Runner,
        state_root: Path = PRODUCTION_STATE_ROOT,
        require_root_owned: bool = False,
    ):
        self.registry_path = registry_path
        self.identity_path = identity_path
        self.capability_identity_path = capability_identity_path
        self.compose_root = compose_root
        self.runner = runner
        self.state_root = state_root
        self.require_root_owned = require_root_owned

    @contextmanager
    def _target_lock(self):
        lock_path = self.state_root / "locks" / f"{TARGET_ALIAS}.lock"
        try:
            info = lock_path.lstat()
        except FileNotFoundError as exc:
            raise WeatherDataError("TARGET_LOCK_INVALID", "existing SIMPLE-DEPLOY target lock file is missing") from exc
        if lock_path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise WeatherDataError("TARGET_LOCK_INVALID", "SIMPLE-DEPLOY target lock path is not a regular file")
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise WeatherDataError("TARGET_LOCK_INVALID", "SIMPLE-DEPLOY target lock metadata drifted")
        try:
            with sd.StateStore(self.state_root).lock(TARGET_ALIAS):
                yield
        except sd.LockBusy as exc:
            raise WeatherDataError("TARGET_BUSY", "SIMPLE-DEPLOY reconciliation already owns the Weather target") from exc

    def _deployer(self, registry: sd.TargetRegistry, identity: sd.DeployerIdentity) -> sd.SimpleDeployer:
        return sd.SimpleDeployer(
            registry=registry,
            identity=identity,
            state=None,
            runner=self.runner,
            http=schema_bridge.LoopbackHttp(),
            compose_root=self.compose_root,
            require_root_owned_compose=self.require_root_owned,
        )

    def _compose_prefix(self, compose_file: Path) -> tuple[str, ...]:
        return (
            "docker", "compose",
            "--project-name", COMPOSE_PROJECT,
            "--file", str(compose_file),
        )

    def _systemd_state(self, *, require_disabled: bool, mutation_started: bool) -> None:
        timer_enabled = _required(
            self.runner.run(("systemctl", "is-enabled", INGEST_TIMER_UNIT), timeout_seconds=15),
            "TIMER_ENABLE_STATE_FAILED",
            mutation_started=mutation_started,
            allowed_returncodes=(0, 1, 3, 4),
        ).strip()
        timer_active = _required(
            self.runner.run(("systemctl", "is-active", INGEST_TIMER_UNIT), timeout_seconds=15),
            "TIMER_ACTIVE_STATE_FAILED",
            mutation_started=mutation_started,
            allowed_returncodes=(0, 1, 3, 4),
        ).strip()
        service_active = _required(
            self.runner.run(("systemctl", "is-active", INGEST_SERVICE_UNIT), timeout_seconds=15),
            "SERVICE_ACTIVE_STATE_FAILED",
            mutation_started=mutation_started,
            allowed_returncodes=(0, 1, 3, 4),
        ).strip()
        if require_disabled:
            if timer_enabled != "disabled":
                raise WeatherDataError("TIMER_NOT_DISABLED", "recurring ingest timer must be installed and disabled", mutation_started=mutation_started)
            if timer_active != "inactive" or service_active != "inactive":
                raise WeatherDataError("RECURRING_INGEST_ACTIVE", "recurring ingest must be inactive before bootstrap/enable", mutation_started=mutation_started)

    def preflight(self, *, require_bootstrap_source: bool, require_recurring_disabled: bool) -> Preflight:
        registry = sd.load_registry(self.registry_path)
        identity = sd.load_identity(self.identity_path)
        capability_identity = load_capability_identity(self.capability_identity_path)
        if not registry.execution_enabled:
            raise WeatherDataError("REGISTRY_DISABLED", "SIMPLE-DEPLOY registry is disabled")
        target = registry.get(TARGET_ALIAS)
        if (
            target.consumer_repository != CONSUMER_REPOSITORY
            or target.image != IMAGE
            or target.compose.project != COMPOSE_PROJECT
            or target.compose.file != COMPOSE_FILE
            or target.compose.service != COMPOSE_SERVICE
            or target.persistent_volumes != (LOGICAL_VOLUME,)
            or target.registry_pull_profile != "public-anonymous-pull"
            or target.health.readiness_state != "required"
            or target.health.readiness_url is None
        ):
            raise WeatherDataError("TARGET_CONTRACT_DRIFT", "Weather data target contract drifted")
        deployer = self._deployer(registry, identity)
        try:
            compose_file = deployer._verify_compose_file(target)
            digest = deployer._resolve_pointer(target)
            metadata = deployer._inspect_image(target, digest)
        except sd.SimpleDeployError as exc:
            raise WeatherDataError("IMAGE_CONTRACT_FAILED", "immutable image contract validation failed") from exc
        if DIGEST_RE.fullmatch(digest) is None:
            raise WeatherDataError("IMAGE_CONTRACT_FAILED", "production pointer digest is invalid")
        if require_bootstrap_source and metadata.source_sha != EXPECTED_BOOTSTRAP_SOURCE_SHA:
            raise WeatherDataError("CONSUMER_SOURCE_DRIFT", "bootstrap must use the reviewed Weather source revision")
        volume = _required(
            self.runner.run(("docker", "volume", "inspect", "--format", "{{.Name}}", HOST_VOLUME), timeout_seconds=30),
            "VOLUME_IDENTITY_FAILED",
            mutation_started=False,
        ).strip()
        if volume != HOST_VOLUME:
            raise WeatherDataError("VOLUME_IDENTITY_FAILED", "existing Weather volume identity does not match")
        try:
            readiness = schema_bridge.LoopbackHttp().get(target.health.readiness_url, timeout_seconds=10)
        except schema_bridge.SchemaInitError as exc:
            raise WeatherDataError("READINESS_PROBE_FAILED", "Weather readiness probe failed") from exc
        if readiness != 200:
            raise WeatherDataError("READINESS_NOT_READY", "Weather readiness must be 200 before data operations")
        prefix = self._compose_prefix(compose_file)
        container_id = _required(
            self.runner.run((*prefix, "ps", "--quiet", COMPOSE_SERVICE), timeout_seconds=30),
            "WEATHER_CONTAINER_DISCOVERY_FAILED",
            mutation_started=False,
        ).strip()
        if CONTAINER_ID_RE.fullmatch(container_id) is None:
            raise WeatherDataError("WEATHER_CONTAINER_DISCOVERY_FAILED", "exactly one valid running Weather container is required")
        inspect_format = (
            '{{.Image}}\t{{index .Config.Labels "org.opencontainers.image.revision"}}'
            '\t{{index .Config.Labels "io.rozkalns.simple-deploy.target"}}'
            '\t{{index .Config.Labels "com.docker.compose.project"}}'
            '\t{{index .Config.Labels "com.docker.compose.service"}}'
        )
        runtime = _required(
            self.runner.run(("docker", "inspect", "--format", inspect_format, container_id), timeout_seconds=30),
            "WEATHER_CONTAINER_IDENTITY_FAILED",
            mutation_started=False,
        ).strip().split("\t")
        if len(runtime) != 5:
            raise WeatherDataError("WEATHER_CONTAINER_IDENTITY_FAILED", "Weather runtime identity fields are incomplete")
        runtime_image_id, runtime_source_sha, runtime_target, runtime_project, runtime_service = runtime
        if (
            IMAGE_ID_RE.fullmatch(runtime_image_id) is None
            or runtime_source_sha != metadata.source_sha
            or runtime_target != TARGET_ALIAS
            or runtime_project != COMPOSE_PROJECT
            or runtime_service != COMPOSE_SERVICE
        ):
            raise WeatherDataError("WEATHER_CONTAINER_IDENTITY_FAILED", "running Weather container does not match reviewed target metadata")
        local_image_id = _required(
            self.runner.run(("docker", "image", "inspect", "--format", "{{.Id}}", f"{IMAGE}@{digest}"), timeout_seconds=30),
            "LOCAL_IMAGE_ID_FAILED",
            mutation_started=False,
        ).strip()
        if IMAGE_ID_RE.fullmatch(local_image_id) is None or runtime_image_id != local_image_id:
            raise WeatherDataError("RUNNING_IMAGE_POINTER_DRIFT", "running Weather image does not match the current production pointer")
        if require_recurring_disabled:
            self._systemd_state(require_disabled=True, mutation_started=False)
        return Preflight(target, compose_file, digest, metadata, capability_identity.source_sha, container_id, local_image_id)

    def _exec(self, preflight: Preflight, command: Sequence[str], *, timeout_seconds: int, code: str) -> CommandResult:
        if not command or any(type(part) is not str or not part for part in command):
            raise WeatherDataError("COMMAND_CONTRACT", "fixed Weather command invalid", mutation_started=True)
        prefix = self._compose_prefix(preflight.compose_file)
        result = self.runner.run((*prefix, "exec", "-T", COMPOSE_SERVICE, *tuple(command)), timeout_seconds=timeout_seconds)
        return CommandResult(result.returncode, result.stdout, result.stderr)

    def _production_plan(self, preflight: Preflight, recovery_decision: str) -> dict[str, object]:
        if recovery_decision not in RECOVERY_DECISIONS:
            raise WeatherDataError("RECOVERY_DECISION_REQUIRED", "unsupported production bootstrap recovery decision")
        command = (
            "rozkalns-weather", "production-bootstrap-plan",
            "--source-sha", EXPECTED_BOOTSTRAP_SOURCE_SHA,
            "--start", BOOTSTRAP_START_DATE,
            "--end", BOOTSTRAP_END_DATE,
            "--recovery-decision", recovery_decision,
        )
        plan = _json_object(
            self._exec(preflight, command, timeout_seconds=30, code="BOOTSTRAP_PLAN_FAILED"),
            "BOOTSTRAP_PLAN_FAILED",
            mutation_started=True,
        )
        identity = plan.get("identity")
        if (
            plan.get("state") != "source_plan_ready"
            or type(identity) is not dict
            or identity.get("source_sha") != EXPECTED_BOOTSTRAP_SOURCE_SHA
            or identity.get("start_date") != BOOTSTRAP_START_DATE
            or identity.get("end_date") != BOOTSTRAP_END_DATE
            or tuple(identity.get("models", [])) != MODELS
            or tuple(identity.get("run_hours_utc", [])) != (0, 6, 12, 18)
            or identity.get("truth_station_id") != "10416"
            or identity.get("truth_chunk_days") != 14
            or identity.get("recovery_decision") != recovery_decision
        ):
            raise WeatherDataError("BOOTSTRAP_PLAN_DRIFT", "Weather production bootstrap plan drifted", mutation_started=True)
        fingerprint = plan.get("bootstrap_fingerprint")
        if type(fingerprint) is not str or FINGERPRINT_RE.fullmatch(fingerprint) is None:
            raise WeatherDataError("BOOTSTRAP_PLAN_DRIFT", "Weather production bootstrap fingerprint is invalid", mutation_started=True)
        return plan

    def _require_fresh_checkpoint_root(self, preflight: Preflight, fingerprint: str) -> None:
        checkpoint_root = f"/app/data/production-bootstrap-v1/{fingerprint}"
        result = _json_object(
            self._exec(
                preflight,
                ("python", "-c", CHECKPOINT_PROBE, checkpoint_root),
                timeout_seconds=30,
                code="CHECKPOINT_STATE_FAILED",
            ),
            "CHECKPOINT_STATE_FAILED",
            mutation_started=True,
        )
        if set(result) != set(CHECKPOINT_NAMES) or any(type(value) is not bool for value in result.values()):
            raise WeatherDataError("CHECKPOINT_STATE_FAILED", "checkpoint state probe returned an invalid shape", mutation_started=True)
        if any(result.values()):
            raise WeatherDataError(
                "PRIOR_BOOTSTRAP_STATE_PRESENT",
                "partial or completed bootstrap checkpoint state requires a separate explicit resume/recovery decision",
                mutation_started=True,
            )

    @staticmethod
    def _report_is_acceptable(report: Mapping[str, object], *, allow_nonblocking_warn: bool) -> bool:
        state = report.get("state")
        if state == "PASS":
            return True
        if not allow_nonblocking_warn or state != "WARN":
            return False
        block_reasons = report.get("block_reasons")
        warn_reasons = report.get("warn_reasons")
        return (
            type(block_reasons) is list
            and block_reasons == []
            and type(warn_reasons) is list
            and bool(warn_reasons)
            and all(type(reason) is str and bool(reason) for reason in warn_reasons)
        )

    def _strict_integrity(
        self,
        preflight: Preflight,
        *,
        start_date: str,
        end_date: str,
        allow_nonblocking_warn: bool,
    ) -> tuple[dict[str, object], dict[str, object]]:
        report = _json_object(
            self._exec(
                preflight,
                ("rozkalns-weather", "corpus-report", "--start", start_date, "--end", end_date),
                timeout_seconds=120,
                code="CORPUS_REPORT_FAILED",
            ),
            "CORPUS_REPORT_FAILED",
            mutation_started=True,
        )
        if not self._report_is_acceptable(report, allow_nonblocking_warn=allow_nonblocking_warn):
            raise WeatherDataError("CORPUS_REPORT_NOT_PASS", "production public corpus report is blocking or invalid", mutation_started=True)
        corpus_check = _json_object(
            self._exec(
                preflight,
                ("rozkalns-weather", "corpus-check"),
                timeout_seconds=120,
                code="CORPUS_CHECK_FAILED",
            ),
            "CORPUS_CHECK_FAILED",
            mutation_started=True,
        )
        if corpus_check.get("ok") is not True:
            raise WeatherDataError("CORPUS_CHECK_NOT_PASS", "corpus-check is not PASS", mutation_started=True)
        return report, corpus_check

    def _recheck_pointer(self, preflight: Preflight, *, mutation_started: bool) -> None:
        registry = sd.load_registry(self.registry_path)
        identity = sd.load_identity(self.identity_path)
        try:
            current = self._deployer(registry, identity)._resolve_pointer(preflight.target)
        except sd.SimpleDeployError as exc:
            raise WeatherDataError("POINTER_RECHECK_FAILED", "production pointer recheck failed", mutation_started=mutation_started) from exc
        if current != preflight.digest:
            raise WeatherDataError("POINTER_CHANGED", "production pointer changed during Weather data operation", mutation_started=mutation_started)

    def bootstrap(self, recovery_decision: str) -> dict[str, object]:
        with self._target_lock():
            preflight = self.preflight(require_bootstrap_source=True, require_recurring_disabled=True)
            plan = self._production_plan(preflight, recovery_decision)
            fingerprint = str(plan["bootstrap_fingerprint"])
            self._require_fresh_checkpoint_root(preflight, fingerprint)
            for command in fixed_bootstrap_commands(fingerprint):
                _required(
                    self._exec(preflight, command, timeout_seconds=7200, code="BACKFILL_FAILED"),
                    "BACKFILL_FAILED",
                    mutation_started=True,
                )
            self._strict_integrity(
                preflight,
                start_date=BOOTSTRAP_START_DATE,
                end_date=BOOTSTRAP_END_DATE,
                allow_nonblocking_warn=False,
            )
            self._recheck_pointer(preflight, mutation_started=True)
            return self._receipt(
                "BOOTSTRAP_PASS",
                preflight,
                runtime_process_started=True,
                production_data_mutation=True,
                recovery_decision=recovery_decision,
                fingerprint=fingerprint,
            )

    def integrity(self) -> dict[str, object]:
        with self._target_lock():
            preflight = self.preflight(require_bootstrap_source=False, require_recurring_disabled=False)
            self._strict_integrity(
                preflight,
                start_date=RECURRING_INTEGRITY_START_DATE,
                end_date=RECURRING_INTEGRITY_END_DATE,
                allow_nonblocking_warn=True,
            )
            self._recheck_pointer(preflight, mutation_started=True)
            return self._receipt("INTEGRITY_PASS", preflight, runtime_process_started=True, production_data_mutation=False)

    def enable_preflight(self) -> dict[str, object]:
        with self._target_lock():
            preflight = self.preflight(require_bootstrap_source=False, require_recurring_disabled=True)
            self._strict_integrity(
                preflight,
                start_date=RECURRING_INTEGRITY_START_DATE,
                end_date=RECURRING_INTEGRITY_END_DATE,
                allow_nonblocking_warn=True,
            )
            self._recheck_pointer(preflight, mutation_started=True)
            return self._receipt("RECURRING_ENABLE_READY", preflight, runtime_process_started=True, production_data_mutation=False)

    def ingest_once(self) -> dict[str, object]:
        with self._target_lock():
            preflight = self.preflight(require_bootstrap_source=False, require_recurring_disabled=False)
            self._strict_integrity(
                preflight,
                start_date=RECURRING_INTEGRITY_START_DATE,
                end_date=RECURRING_INTEGRITY_END_DATE,
                allow_nonblocking_warn=True,
            )
            result = _json_object(
                self._exec(
                    preflight,
                    ("rozkalns-weather", "ingest-public"),
                    timeout_seconds=2400,
                    code="PUBLIC_INGEST_FAILED",
                ),
                "PUBLIC_INGEST_FAILED",
                mutation_started=True,
            )
            if result.get("state") == "already_running":
                raise WeatherDataError("INGEST_OVERLAP", "public ingest overlap lock rejected this run", mutation_started=True)
            self._recheck_pointer(preflight, mutation_started=True)
            return self._receipt("INGEST_PASS", preflight, runtime_process_started=True, production_data_mutation=True)

    @staticmethod
    def _receipt(
        result: str,
        preflight: Preflight,
        *,
        runtime_process_started: bool,
        production_data_mutation: bool,
        recovery_decision: str | None = None,
        fingerprint: str | None = None,
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": "rozkalns.rpi5-main.simple-deploy.weather-data.receipt.v1",
            "result": result,
            "target_alias": TARGET_ALIAS,
            "consumer_repository": CONSUMER_REPOSITORY,
            "consumer_source_sha": preflight.metadata.source_sha,
            "capability_source_sha": preflight.capability_source_sha,
            "image_ref": f"{preflight.target.image}@{preflight.digest}",
            "persistent_volume": HOST_VOLUME,
            "runtime_process_started": runtime_process_started,
            "mutation_started": runtime_process_started,
            "production_data_mutation": production_data_mutation,
            "timer_enabled_or_started": False,
            "service_enabled_or_started": False,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
            "automatic_restore": False,
            "automatic_delete": False,
        }
        if recovery_decision is not None:
            value["recovery_decision"] = recovery_decision
        if fingerprint is not None:
            value["bootstrap_fingerprint"] = fingerprint
        return value


def production_bridge() -> WeatherDataBridge:
    sd._require_production_file(PRODUCTION_REGISTRY_PATH)
    sd._require_production_file(PRODUCTION_IDENTITY_PATH)
    sd._require_production_file(PRODUCTION_CAPABILITY_IDENTITY_PATH)
    uid, gid = schema_bridge._require_execution_identity()
    schema_bridge._require_anonymous_state(uid, gid)
    return WeatherDataBridge(
        registry_path=PRODUCTION_REGISTRY_PATH,
        identity_path=PRODUCTION_IDENTITY_PATH,
        capability_identity_path=PRODUCTION_CAPABILITY_IDENTITY_PATH,
        compose_root=PRODUCTION_COMPOSE_ROOT,
        runner=SubprocessRunner(state_root=PRODUCTION_STATE_ROOT),
        state_root=PRODUCTION_STATE_ROOT,
        require_root_owned=True,
    )


def _preflight_receipt(preflight: Preflight) -> dict[str, object]:
    return WeatherDataBridge._receipt(
        "PRECHECK_READY",
        preflight,
        runtime_process_started=False,
        production_data_mutation=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    valid = {
        ("--preflight",),
        ("--bootstrap-verified-backup",),
        ("--bootstrap-accept-no-backup",),
        ("--integrity",),
        ("--enable-preflight",),
        ("--ingest-once",),
    }
    if args not in valid:
        print(json.dumps({
            "result": "PRE_MUTATION_FAILURE",
            "error_code": "ARGUMENTS_FORBIDDEN",
            "mutation_started": False,
        }, sort_keys=True))
        return 2
    try:
        bridge = production_bridge()
        if args == ("--preflight",):
            output = _preflight_receipt(
                bridge.preflight(require_bootstrap_source=True, require_recurring_disabled=True)
            )
        elif args == ("--bootstrap-verified-backup",):
            output = bridge.bootstrap(RECOVERY_VERIFIED_BACKUP)
        elif args == ("--bootstrap-accept-no-backup",):
            output = bridge.bootstrap(RECOVERY_ACCEPT_NO_BACKUP)
        elif args == ("--integrity",):
            output = bridge.integrity()
        elif args == ("--enable-preflight",):
            output = bridge.enable_preflight()
        else:
            output = bridge.ingest_once()
    except WeatherDataError as exc:
        print(json.dumps({
            "result": "FAIL_CLOSED" if exc.mutation_started else "PRE_MUTATION_FAILURE",
            "error_code": exc.code,
            "mutation_started": exc.mutation_started,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
        }, sort_keys=True))
        return 1
    except sd.SimpleDeployError as exc:
        print(json.dumps({
            "result": "PRE_MUTATION_FAILURE",
            "error_code": exc.code,
            "mutation_started": False,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
        }, sort_keys=True))
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
