from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping, Sequence

from .weather_public_runtime_adapter import OPERATION_ID, TARGET_ALIAS
from .weather_public_runtime_execution import (
    ACTIVATION_FILE,
    ACTIVATION_SCHEMA,
    CANDIDATE_ROOT,
    COMPOSE_PROJECT,
    RELEASE_ROOT,
)
from .weather_public_runtime_host_wiring import expected_helper_bindings

RECEIPT_SCHEMA = "rozkalns-weather.public-runtime-helper-receipt.v1"
COMPOSE_RELATIVE = Path("deploy/docker-compose.public.yml")
LOGICAL_VOLUME = "weather_data"
HOST_VOLUME = f"{COMPOSE_PROJECT}_{LOGICAL_VOLUME}"
READINESS_URL = "http://127.0.0.1:9180/ready"
TIMER_NAME = "rozkalns-weather-public-ingest.timer"
SERVICE_NAME = "rozkalns-weather-public-ingest.service"
SYSTEMD_ROOT = Path("/etc/systemd/system")
FIXED_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}
RECOVERY_DECISIONS = frozenset({"verified-backup-available", "owner-accepted-no-prewrite-backup"})
MODELS = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")
RUN_HOURS = ("00", "06", "12", "18")
TRUTH_STATION_ID = "10416"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class WeatherStageHelperError(RuntimeError):
    pass


@dataclass(frozen=True)
class Activation:
    source_sha: str
    preactivation_sha256: str
    start_date: str
    end_date: str
    recovery_decision: str
    allowed_helper_ids: tuple[str, ...]


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str]], CommandResult]


def _fail(message: str) -> None:
    raise WeatherStageHelperError(message)


def parse_activation(value: Mapping[str, Any]) -> Activation:
    expected = {
        "schema",
        "enabled",
        "target_alias",
        "operation_id",
        "source_sha",
        "preactivation_sha256",
        "start_date",
        "end_date",
        "recovery_decision",
        "allowed_helper_ids",
    }
    if type(value) is not dict or set(value) != expected:
        _fail("Weather helper activation fields drifted")
    if value["schema"] != ACTIVATION_SCHEMA or value["enabled"] is not True:
        _fail("Weather helper activation is absent or disabled")
    if value["target_alias"] != TARGET_ALIAS or value["operation_id"] != OPERATION_ID:
        _fail("Weather helper activation operation/target drifted")
    source_sha = value["source_sha"]
    digest = value["preactivation_sha256"]
    if type(source_sha) is not str or not _SHA40_RE.fullmatch(source_sha):
        _fail("Weather helper activation source SHA is invalid")
    if type(digest) is not str or not _SHA256_RE.fullmatch(digest):
        _fail("Weather helper activation preactivation hash is invalid")
    try:
        start = date.fromisoformat(value["start_date"])
        end = date.fromisoformat(value["end_date"])
    except (TypeError, ValueError) as exc:
        raise WeatherStageHelperError("Weather helper activation date bounds are invalid") from exc
    if end < start or (end - start).days + 1 > 180:
        _fail("Weather helper activation date bounds are invalid")
    recovery = value["recovery_decision"]
    if recovery not in RECOVERY_DECISIONS:
        _fail("Weather helper activation recovery decision drifted")
    helper_ids = value["allowed_helper_ids"]
    expected_helpers = tuple(binding.helper_id for binding in expected_helper_bindings())
    if type(helper_ids) is not list or tuple(helper_ids) != expected_helpers:
        _fail("Weather helper activation helper identities drifted")
    return Activation(source_sha, digest, start.isoformat(), end.isoformat(), recovery, expected_helpers)


def read_activation(path: Path = Path(ACTIVATION_FILE)) -> Activation:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise WeatherStageHelperError("Weather helper activation file is unavailable") from exc
    if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_gid != 0 or stat.S_IMODE(meta.st_mode) != 0o600:
        _fail("Weather helper activation file metadata drifted")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise WeatherStageHelperError("Weather helper activation file read failed") from exc
    if not 1 <= len(raw) <= 8192:
        _fail("Weather helper activation file size is invalid")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeatherStageHelperError("Weather helper activation file is not strict JSON") from exc
    return parse_activation(value)


def run_command(argv: Sequence[str]) -> CommandResult:
    if not argv or any(type(part) is not str or not part for part in argv):
        _fail("Weather helper fixed argv is invalid")
    try:
        completed = subprocess.run(
            tuple(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            env=dict(FIXED_ENV),
            shell=False,
            close_fds=True,
            timeout=1800,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise WeatherStageHelperError("Weather helper fixed command failed to run") from exc
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _require_success(result: CommandResult, where: str) -> str:
    if type(result) is not CommandResult or result.returncode != 0:
        _fail(f"Weather helper {where} failed closed")
    if len(result.stdout.encode("utf-8")) > 65536 or len(result.stderr.encode("utf-8")) > 65536:
        _fail(f"Weather helper {where} output exceeded source limit")
    return result.stdout


def _compose_argv(release: Path, *args: str) -> tuple[str, ...]:
    compose = release / COMPOSE_RELATIVE
    if not compose.is_file():
        _fail("Weather release Compose file is absent")
    return ("/usr/bin/docker", "compose", "-p", COMPOSE_PROJECT, "-f", str(compose), *args)


def _validate_request(argv: Sequence[str], activation: Activation) -> tuple[str, str, str, str, str, str, tuple[str, ...]]:
    if len(argv) < 6:
        _fail("Weather helper canonical argv is incomplete")
    helper_id, source_sha, digest, start_date, end_date, recovery = argv[:6]
    if source_sha != activation.source_sha or digest != activation.preactivation_sha256:
        _fail("Weather helper canonical provenance drifted")
    if (start_date, end_date, recovery) != (activation.start_date, activation.end_date, activation.recovery_decision):
        _fail("Weather helper canonical bounds/recovery drifted")
    helper_map = {binding.helper_id: binding for binding in expected_helper_bindings()}
    if helper_id not in helper_map or helper_id not in activation.allowed_helper_ids:
        _fail("Weather helper identity is not activated")
    extra = tuple(argv[6:])
    binding = helper_map[helper_id]
    if binding.stage_id in {"bounded_deterministic_forecast_backfill", "corpus_integrity_check"}:
        if extra != (",".join(MODELS), ",".join(RUN_HOURS)):
            _fail("Weather helper model/run-hour scope drifted")
    elif binding.stage_id == "bounded_dwd_truth_backfill":
        if extra != (TRUTH_STATION_ID,):
            _fail("Weather helper truth-station scope drifted")
    elif extra:
        _fail("Weather helper received unexpected canonical arguments")
    return helper_id, source_sha, digest, start_date, end_date, recovery, extra


def _candidate_and_release(source_sha: str) -> tuple[Path, Path]:
    candidate = Path(CANDIDATE_ROOT) / source_sha
    release = Path(RELEASE_ROOT) / source_sha
    if candidate != release:
        _fail("Weather release materialization path contract drifted")
    if not release.is_dir():
        _fail("Weather exact release is absent")
    return release, release


def _validate_candidate(candidate: Path, source_sha: str, runner: CommandRunner) -> None:
    head = _require_success(runner(("/usr/bin/git", "-C", str(candidate), "rev-parse", "HEAD")), "release HEAD").strip()
    if head != source_sha:
        _fail("Weather exact release HEAD drifted")
    status_out = _require_success(runner(("/usr/bin/git", "-C", str(candidate), "status", "--porcelain=v1", "--untracked-files=all")), "release cleanliness")
    if status_out:
        _fail("Weather exact release is not clean")
    if any(path.is_symlink() for path in candidate.rglob("*")):
        _fail("Weather exact release symlink surface is forbidden")


def _application_release(candidate: Path, release: Path, source_sha: str, runner: CommandRunner) -> int:
    if candidate != release:
        _fail("Weather application release would duplicate filesystem materialization")
    _validate_candidate(release, source_sha, runner)
    _require_success(runner(_compose_argv(release, "build", "weather", "public-ingest", "schema-init", "readiness", "corpus-check")), "Compose build")
    _require_success(runner(_compose_argv(release, "up", "-d", "weather")), "application apply")
    return 1


def _volume_ensure(runner: CommandRunner) -> int:
    out = _require_success(runner(("/usr/bin/docker", "volume", "ls", "--filter", f"name=^{HOST_VOLUME}$", "--format", "{{.Name}}")), "volume discovery").strip()
    if out == HOST_VOLUME:
        return 0
    if out:
        _fail("Weather volume discovery returned ambiguous identity")
    _require_success(runner(("/usr/bin/docker", "volume", "create", HOST_VOLUME)), "volume create")
    return 1


def _schema_init(release: Path, runner: CommandRunner) -> int:
    _require_success(runner(_compose_argv(release, "exec", "-T", "weather", "rozkalns-weather", "init-database")), "schema init")
    return 1


def _readiness() -> int:
    try:
        with urllib.request.urlopen(READINESS_URL, timeout=5) as response:
            if response.status != 200:
                _fail("Weather readiness HTTP status failed")
            payload = response.read(65537)
    except (OSError, urllib.error.URLError) as exc:
        raise WeatherStageHelperError("Weather readiness request failed") from exc
    if len(payload) > 65536:
        _fail("Weather readiness response exceeded source limit")
    return 0


def _public_smoke(release: Path, runner: CommandRunner) -> int:
    _require_success(runner(_compose_argv(release, "exec", "-T", "weather", "rozkalns-weather", "smoke-public")), "public smoke")
    return 0


def _truth_backfill(release: Path, start: str, end: str, runner: CommandRunner) -> int:
    argv = _compose_argv(
        release,
        "exec", "-T", "weather", "python", "-m", "rozkalns_weather.backfill",
        "--database-url", "sqlite:///data/weather.db", "truth",
        "--start", start, "--end", end,
        "--checkpoint", "/app/data/backfill-truth-checkpoint.json",
        "--chunk-days", "14",
    )
    _require_success(runner(argv), "DWD truth backfill")
    return 1


def _forecast_backfill(release: Path, start: str, end: str, runner: CommandRunner) -> int:
    operations = 0
    for model in MODELS:
        argv = _compose_argv(
            release,
            "exec", "-T", "weather", "python", "-m", "rozkalns_weather.backfill",
            "--database-url", "sqlite:///data/weather.db", "forecast",
            "--model", model, "--start", start, "--end", end,
            "--run-hours", ",".join(str(int(hour)) for hour in RUN_HOURS),
            "--checkpoint", f"/app/data/backfill-{model}-checkpoint.json",
        )
        _require_success(runner(argv), f"{model} forecast backfill")
        operations += 1
    return operations


def _integrity(release: Path, start: str, end: str, runner: CommandRunner) -> int:
    operations = 0
    for model in MODELS:
        argv = _compose_argv(
            release,
            "exec", "-T", "weather", "python", "-m", "rozkalns_weather.backfill",
            "--database-url", "sqlite:///data/weather.db", "integrity",
            "--model", model, "--start", start, "--end", end,
            "--run-hours", ",".join(str(int(hour)) for hour in RUN_HOURS),
        )
        _require_success(runner(argv), f"{model} corpus integrity")
        operations += 1
    return operations


def _schedule_units(release: Path) -> tuple[str, str]:
    compose = release / COMPOSE_RELATIVE
    service = (
        "[Unit]\nDescription=Rozkalns Weather public ingest\nAfter=docker.service\nRequires=docker.service\n\n"
        "[Service]\nType=oneshot\n"
        f"ExecStart=/usr/bin/docker compose -p {COMPOSE_PROJECT} -f {compose} exec -T weather rozkalns-weather ingest-public\n"
        "NoNewPrivileges=true\nPrivateTmp=true\n"
    )
    timer = (
        "[Unit]\nDescription=Rozkalns Weather public ingest timer\n\n"
        "[Timer]\nOnCalendar=*:0/30\nPersistent=true\nRandomizedDelaySec=60\nAccuracySec=60\nUnit=" + SERVICE_NAME + "\n\n"
        "[Install]\nWantedBy=timers.target\n"
    )
    return service, timer


def _write_exact(path: Path, content: str) -> None:
    encoded = content.encode("utf-8")
    if path.exists():
        try:
            if path.read_bytes() == encoded:
                return
        except OSError as exc:
            raise WeatherStageHelperError("Weather systemd unit read failed") from exc
    tmp = path.with_name(path.name + ".new")
    try:
        with open(tmp, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except OSError as exc:
        raise WeatherStageHelperError("Weather systemd unit write failed closed") from exc


def _schedule(release: Path, runner: CommandRunner) -> int:
    service, timer = _schedule_units(release)
    _write_exact(SYSTEMD_ROOT / SERVICE_NAME, service)
    _write_exact(SYSTEMD_ROOT / TIMER_NAME, timer)
    _require_success(runner(("/usr/bin/systemctl", "daemon-reload")), "systemd daemon-reload")
    _require_success(runner(("/usr/bin/systemctl", "enable", "--now", TIMER_NAME)), "systemd timer activation")
    return 1


def execute_stage(argv: Sequence[str], *, activation: Activation, runner: CommandRunner = run_command) -> Mapping[str, Any]:
    helper_id, source_sha, digest, start, end, _recovery, _extra = _validate_request(argv, activation)
    binding = next(binding for binding in expected_helper_bindings() if binding.helper_id == helper_id)
    candidate, release = _candidate_and_release(source_sha)
    if binding.stage_id == "application_release":
        operations = _application_release(candidate, release, source_sha, runner)
    elif binding.stage_id == "persistent_volume_ensure":
        operations = _volume_ensure(runner)
    elif binding.stage_id == "explicit_schema_init":
        operations = _schema_init(release, runner)
    elif binding.stage_id == "readiness_schema_privacy":
        operations = _readiness()
    elif binding.stage_id == "public_smoke_read_only":
        operations = _public_smoke(release, runner)
    elif binding.stage_id == "bounded_dwd_truth_backfill":
        operations = _truth_backfill(release, start, end, runner)
    elif binding.stage_id == "bounded_deterministic_forecast_backfill":
        operations = _forecast_backfill(release, start, end, runner)
    elif binding.stage_id == "corpus_integrity_check":
        operations = _integrity(release, start, end, runner)
    elif binding.stage_id == "recurring_public_ingest_schedule":
        operations = _schedule(release, runner)
    else:
        _fail("Weather helper stage implementation is missing")
    if not 0 <= operations <= binding.max_operations:
        _fail("Weather helper stage exceeded its operation budget")
    return {
        "schema": RECEIPT_SCHEMA,
        "stage_id": binding.stage_id,
        "helper_id": binding.helper_id,
        "source_sha": source_sha,
        "preactivation_sha256": digest,
        "operations_performed": operations,
        "production_mutation_started": not binding.read_only and operations > 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    import sys

    args = tuple(sys.argv[1:] if argv is None else argv)
    try:
        activation = read_activation()
        receipt = execute_stage(args, activation=activation)
    except WeatherStageHelperError as exc:
        print(f"WEATHER_STAGE_HELPER=STOP error={type(exc).__name__}", file=sys.stderr)
        return 78
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0
