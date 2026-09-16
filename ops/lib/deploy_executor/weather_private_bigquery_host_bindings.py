from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping

from .hermes_deals_origin_runtime_adapters import ConcreteDurableHermesOriginReplayAuthority
from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    AcceptedAuthorization,
    accept_issue,
    verify_authorization_unchanged,
)
from .source_evidence import verify_source_evidence
from .transport import API_VERSION, GitHubHttpsSender, HTTPStatusError, JSONResponse
from .weather_private_bigquery_contract import (
    CONTRACT_ID,
    READ_ONLY_PRIVATE_BIGQUERY,
    FirstAccessScope,
    validate_first_access_scope,
)
from .weather_private_bigquery_execution_bridge import BRIDGE_OPERATION_ID, TARGET_ALIAS, StageReceipt
from .weather_private_bigquery_runtime_materialization import (
    ARTIFACT_CACHE_ROOT,
    RUNTIME_BASE,
    RUNTIME_MARKER_NAME,
    RuntimeArtifactReceipt,
    TARGET_PYTHON_ABI,
)
from .weather_private_bigquery_trusted_backend import (
    ANALYTICS_HUB_LINK_SLOT_ID,
    APPLICATION_STAGE_ROOT,
    GOOGLE_AUTH_SLOT_ID,
    GOOGLE_PROJECT_SLOT_ID,
)
from .weather_private_bigquery_host_runtime import (
    ACTIVATION_MARKER,
    RPI5_MAIN_REPOSITORY,
    RPI5_MAIN_REPOSITORY_ID,
    WEATHER_REPOSITORY,
    WEATHER_REPOSITORY_ID,
    ExactSourceEvidence,
    OwnerAuthorizationEvidence,
    SanitizedHostEvidence,
    WeatherNextPrivateHostRuntimeError,
    build_runtime_composition,
    validate_activation_marker,
)

ISOLATED_AUTH_PATH = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_CREDENTIAL_PATH = Path("/etc/rozkalns-deploy-executor/github-app.pem")
APPLICATION_MARKER = Path(APPLICATION_STAGE_ROOT) / "source-stage.json"
BINDING_ROOT = Path("/var/lib/rpi5-deploy/weather-private-bindings")
AUTH_READY_MARKER = BINDING_ROOT / "google-auth.ready.json"
PROJECT_READY_MARKER = BINDING_ROOT / "google-project.ready.json"
LINK_READY_MARKER = BINDING_ROOT / "analytics-hub-link.ready.json"
PRIVATE_VALUES = BINDING_ROOT / "first-access-private.json"
CREDENTIAL_ROOT = BINDING_ROOT / "credentials"
ARTIFACT_RECEIPT = Path(ARTIFACT_CACHE_ROOT) / "artifact-receipt.json"
MAX_MARKER_BYTES = 16 * 1024
MAX_CREDENTIAL_BYTES = 64 * 1024
WEATHER_REQUIRED_WORKFLOWS = ("tests.yml", "governance.yml")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_PROJECT = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_DATASET = re.compile(r"^[A-Za-z0-9_]{1,1024}$")
_CREDENTIAL_BASENAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class WeatherNextInstalledBindingsError(WeatherNextPrivateHostRuntimeError):
    pass


def _fail(message: str) -> None:
    raise WeatherNextInstalledBindingsError(message)


def _read_regular(
    path: Path,
    *,
    max_bytes: int,
    required: bool = True,
    mode: int | None = None,
    uid: int = 0,
    gid: int = 0,
) -> bytes | None:
    try:
        before = path.lstat()
    except FileNotFoundError:
        if required:
            _fail(f"required fixed runtime state is absent: {path.name}")
        return None
    except OSError:
        _fail(f"fixed runtime state metadata failed: {path.name}")
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or not 0 < before.st_size <= max_bytes
        or before.st_uid != uid
        or before.st_gid != gid
    ):
        _fail(f"fixed runtime state shape or ownership drifted: {path.name}")
    if mode is not None and stat.S_IMODE(before.st_mode) != mode:
        _fail(f"fixed runtime state mode drifted: {path.name}")
    flags = os.O_RDONLY
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        value = getattr(os, name, None)
        if value is None:
            _fail(f"required descriptor guard unavailable: {name}")
        flags |= value
    try:
        fd = os.open(path, flags)
    except OSError:
        _fail(f"fixed runtime state open failed: {path.name}")
    try:
        opened = os.fstat(fd)
        if (
            (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or opened.st_uid != uid
            or opened.st_gid != gid
            or (mode is not None and stat.S_IMODE(opened.st_mode) != mode)
        ):
            _fail(f"fixed runtime state changed before read: {path.name}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            try:
                chunk = os.read(fd, min(65536, remaining))
            except OSError:
                _fail(f"fixed runtime state read failed: {path.name}")
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > max_bytes or len(raw) != opened.st_size:
            _fail(f"fixed runtime state changed during read: {path.name}")
        try:
            after = path.lstat()
        except OSError:
            _fail(f"fixed runtime state path changed during read: {path.name}")
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
            _fail(f"fixed runtime state path changed during read: {path.name}")
        return raw
    finally:
        os.close(fd)


def _strict_json(
    path: Path,
    *,
    required: bool = True,
    mode: int | None = None,
) -> Mapping[str, Any] | None:
    raw = _read_regular(path, max_bytes=MAX_MARKER_BYTES, required=required, mode=mode)
    if raw is None:
        return None
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError):
        _fail(f"fixed runtime JSON is malformed: {path.name}")
    if type(value) is not dict:
        _fail(f"fixed runtime JSON must be an object: {path.name}")
    return value


class FixedPublicGitHubReadClient:
    """Credential-free GET client restricted to the two public source repositories."""

    def __init__(self, *, sender: Any | None = None):
        self._sender = sender or GitHubHttpsSender()

    @staticmethod
    def _require_path(path: str) -> None:
        if type(path) is not str or not path.startswith("/repos/"):
            _fail("public source read path is invalid")
        remainder = path[len("/repos/") :]
        pieces = remainder.split("/", 2)
        if len(pieces) < 2:
            _fail("public source read path is malformed")
        repository = f"{pieces[0]}/{pieces[1].split('?', 1)[0]}"
        if repository not in {RPI5_MAIN_REPOSITORY, WEATHER_REPOSITORY}:
            _fail("public source read escaped fixed repositories")

    def get_json(self, path_or_url: str) -> JSONResponse:
        self._require_path(path_or_url)
        response = self._sender.send(
            method="GET",
            url="https://api.github.com" + path_or_url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "rozkalns-weathernext-private-host/1",
            },
        )
        if response.status != 200:
            raise HTTPStatusError(response.status)
        date_header = next(
            (value for key, value in response.headers.items() if key.lower() == "date"),
            None,
        )
        if type(date_header) is not str:
            _fail("public source response omitted Date header")
        try:
            server_time = parsedate_to_datetime(date_header)
            value = json.loads(response.body.decode("utf-8", "strict"))
        except (TypeError, ValueError, OverflowError, UnicodeError, json.JSONDecodeError):
            _fail("public source response failed closed")
        if server_time.tzinfo is None:
            _fail("public source response Date header has no timezone")
        return JSONResponse(
            value=value,
            server_time=server_time.astimezone(timezone.utc),
            etag=None,
            not_modified=False,
            url="https://api.github.com" + path_or_url,
            next_url=None,
        )


class PublicExactSourceEvidenceProvider:
    def __init__(self, *, client: FixedPublicGitHubReadClient):
        if type(client) is not FixedPublicGitHubReadClient:
            raise TypeError("exact source provider requires fixed public GitHub client")
        self._client = client

    @staticmethod
    def _object(value: Any, where: str) -> Mapping[str, Any]:
        if type(value) is not dict:
            _fail(f"{where} is not an object")
        return value

    def _require_weather_exact_main_ci(self, source_sha: str) -> None:
        repository = self._object(
            self._client.get_json(f"/repos/{WEATHER_REPOSITORY}").value,
            "Weather repository",
        )
        if (
            repository.get("id") != WEATHER_REPOSITORY_ID
            or repository.get("full_name") != WEATHER_REPOSITORY
            or repository.get("default_branch") != "main"
        ):
            _fail("Weather repository stable identity drifted")
        for workflow in WEATHER_REQUIRED_WORKFLOWS:
            runs = self._object(
                self._client.get_json(
                    f"/repos/{WEATHER_REPOSITORY}/actions/workflows/{workflow}/runs"
                    f"?branch=main&head_sha={source_sha}&status=completed&per_page=100"
                ).value,
                f"Weather {workflow} runs",
            ).get("workflow_runs")
            if type(runs) is not list:
                _fail(f"Weather {workflow} run list is malformed")
            successful = [
                row
                for row in runs
                if type(row) is dict
                and row.get("head_sha") == source_sha
                and row.get("head_branch") == "main"
                and row.get("status") == "completed"
                and row.get("conclusion") == "success"
                and type(row.get("id")) is int
                and row["id"] > 0
            ]
            if not successful:
                _fail(f"Weather exact-main {workflow} has no successful run")
            run_id = max(row["id"] for row in successful)
            jobs = self._object(
                self._client.get_json(
                    f"/repos/{WEATHER_REPOSITORY}/actions/runs/{run_id}/jobs"
                    "?filter=latest&per_page=100"
                ).value,
                f"Weather {workflow} jobs",
            ).get("jobs")
            if type(jobs) is not list or not any(
                type(job) is dict
                and job.get("status") == "completed"
                and job.get("conclusion") == "success"
                for job in jobs
            ):
                _fail(f"Weather exact-main {workflow} has no successful job")

    def load_exact_source(self, repository: str, repository_id: int) -> ExactSourceEvidence:
        expected = {
            RPI5_MAIN_REPOSITORY: RPI5_MAIN_REPOSITORY_ID,
            WEATHER_REPOSITORY: WEATHER_REPOSITORY_ID,
        }
        if expected.get(repository) != repository_id:
            _fail("exact source request escaped reviewed repositories")
        value = self._client.get_json(f"/repos/{repository}/branches/main").value
        if type(value) is not dict or type(value.get("commit")) is not dict:
            _fail("public source branch response malformed")
        current_sha = value["commit"].get("sha")
        if type(current_sha) is not str or _SHA40.fullmatch(current_sha) is None:
            _fail("public source current main SHA invalid")
        if repository == RPI5_MAIN_REPOSITORY:
            proof = verify_source_evidence(
                self._client,
                source_repository=repository,
                source_sha=current_sha,
            )
            if proof.repository_id != repository_id or proof.current_main_sha != current_sha:
                _fail("RPi5_main public source stable identity drifted")
        else:
            self._require_weather_exact_main_ci(current_sha)
        return ExactSourceEvidence(
            repository=repository,
            repository_id=repository_id,
            source_sha=current_sha,
            current_main_sha=current_sha,
            merged_reachable=True,
            required_ci_success=True,
        )


class WeatherNextReplayAuthority:
    """Capability-specific wrapper over the reviewed durable one-shot replay primitive."""

    def __init__(self):
        self._delegate = ConcreteDurableHermesOriginReplayAuthority()

    def is_available(self, accepted: AcceptedAuthorization) -> bool:
        return self._delegate.is_available(accepted)

    def consume(self, request_id: str) -> Any:
        return self._delegate.consume(request_id)


@dataclass
class _AcceptedBox:
    accepted: AcceptedAuthorization | None = None


class DeployAuthorizationEvidenceProvider:
    """Read one exact owner LIVE-AUTH through the reviewed isolated auth surface."""

    def __init__(self, *, client: Any, replay: WeatherNextReplayAuthority, box: _AcceptedBox):
        self._client = client
        self._replay = replay
        self._box = box

    @staticmethod
    def _dependency(payload: Mapping[str, Any], prefix: str) -> str:
        values = [
            item[len(prefix) :]
            for item in payload.get("dependencies", [])
            if type(item) is str and item.startswith(prefix)
        ]
        if len(values) != 1 or not values[0]:
            _fail(f"owner authorization dependency missing: {prefix[:-1]}")
        return values[0]

    def load_owner_authorization(self, authorization_issue_number: int) -> OwnerAuthorizationEvidence:
        if type(authorization_issue_number) is not int or authorization_issue_number <= 0:
            _fail("owner authorization issue number invalid")
        require_isolated_auth_surface(load_contract(ISOLATED_AUTH_PATH))
        first = self._client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{authorization_issue_number}"
        )
        accepted = accept_issue(
            first.value,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=first.server_time,
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        payload = accepted.payload
        if (
            payload.get("source_repository") != WEATHER_REPOSITORY
            or payload.get("target_alias") != TARGET_ALIAS
            or payload.get("operation_id") != BRIDGE_OPERATION_ID
            or payload.get("rollback_policy") != "NONE"
            or payload.get("mutation_budget")
            != [{"category": READ_ONLY_PRIVATE_BIGQUERY, "max_operations": 1}]
        ):
            _fail("owner authorization is not the fixed read-only WeatherNext capability")
        contract = self._dependency(payload, "contract:")
        rpi_sha = self._dependency(payload, "rpi5-main-sha:")
        weather_sha = payload.get("source_sha")
        if (
            contract != CONTRACT_ID
            or type(rpi_sha) is not str
            or _SHA40.fullmatch(rpi_sha) is None
            or type(weather_sha) is not str
            or _SHA40.fullmatch(weather_sha) is None
        ):
            _fail("owner authorization source or contract identity drifted")
        if not self._replay.is_available(accepted) or not self._replay.is_available(accepted):
            _fail("owner authorization replay boundary unavailable")
        require_isolated_auth_surface(load_contract(ISOLATED_AUTH_PATH))
        final = self._client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{authorization_issue_number}"
        )
        verify_authorization_unchanged(
            accepted,
            final.value,
            server_time=final.server_time,
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        self._box.accepted = accepted
        return OwnerAuthorizationEvidence(
            authorization_issue_number=authorization_issue_number,
            owner_authorized=True,
            operation_id=BRIDGE_OPERATION_ID,
            contract_id=CONTRACT_ID,
            target_alias=TARGET_ALIAS,
            rpi5_main_source_sha=rpi_sha,
            weather_source_sha=weather_sha,
        )


class ReplayAuthorizationConsumer:
    """Freshly revalidate authorization and exact sources immediately before consume."""

    def __init__(
        self,
        *,
        client: Any,
        replay: WeatherNextReplayAuthority,
        box: _AcceptedBox,
        sources: PublicExactSourceEvidenceProvider,
    ):
        self._client = client
        self._replay = replay
        self._box = box
        self._sources = sources
        self._consumed = False

    @staticmethod
    def _dependency(payload: Mapping[str, Any], prefix: str) -> str:
        values = [
            item[len(prefix) :]
            for item in payload.get("dependencies", [])
            if type(item) is str and item.startswith(prefix)
        ]
        if len(values) != 1:
            _fail("authorization source dependency drifted before consume")
        return values[0]

    def consume_once(self, authorization_issue_number: int, *, first_stage: str) -> None:
        if self._consumed:
            _fail("WeatherNext private authorization already consumed")
        accepted = self._box.accepted
        if (
            accepted is None
            or accepted.issue_number != authorization_issue_number
            or first_stage != READ_ONLY_PRIVATE_BIGQUERY
        ):
            _fail("WeatherNext private consume boundary identity drifted")
        payload = accepted.payload
        weather_sha = payload.get("source_sha")
        rpi_sha = self._dependency(payload, "rpi5-main-sha:")
        rpi = self._sources.load_exact_source(RPI5_MAIN_REPOSITORY, RPI5_MAIN_REPOSITORY_ID)
        weather = self._sources.load_exact_source(WEATHER_REPOSITORY, WEATHER_REPOSITORY_ID)
        if rpi.source_sha != rpi_sha or weather.source_sha != weather_sha:
            _fail("exact source drifted immediately before authorization consume")
        require_isolated_auth_surface(load_contract(ISOLATED_AUTH_PATH))
        final = self._client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{authorization_issue_number}"
        )
        verify_authorization_unchanged(
            accepted,
            final.value,
            server_time=final.server_time,
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        self._consumed = True
        receipt = self._replay.consume(accepted.request_id)
        if (
            getattr(receipt, "state", None) != "CONSUMED"
            or getattr(receipt, "durable_replay_consumed", None) is not True
            or getattr(receipt, "replay_mutation_started", None) is not True
            or getattr(receipt, "production_mutation_started", None) is not False
        ):
            _fail("WeatherNext private replay consume receipt drifted")


class PosixSanitizedHostEvidenceProvider:
    """Observe public-safe marker identity without reading project/dataset/credential values."""

    @staticmethod
    def _ready_state(path: Path, *, schema: str, slot_id: str) -> str:
        value = _strict_json(path, required=False, mode=0o644)
        if value is None:
            return "absent"
        return "ready" if value == {"schema": schema, "slot_id": slot_id, "ready": True} else "mismatch"

    def load_sanitized_host_evidence(self) -> SanitizedHostEvidence:
        capability = _strict_json(ACTIVATION_MARKER, required=False, mode=0o644)
        capability_installed = capability is not None
        capability_sha: str | None = None
        if capability is not None:
            capability_sha = capability.get("rpi5_main_source_sha")
            if type(capability_sha) is not str or _SHA40.fullmatch(capability_sha) is None:
                _fail("host capability activation marker source SHA invalid")
            validate_activation_marker(capability, exact_rpi5_main_sha=capability_sha)

        application = _strict_json(APPLICATION_MARKER, required=False, mode=0o644)
        application_staged = application is not None
        application_sha: str | None = None
        if application is not None:
            application_sha = application.get("source_sha")
            if (
                set(application) != {"schema", "source_repository", "source_sha", "staged"}
                or application.get("schema") != "rozkalns-weather.weathernext-private-application-stage.v1"
                or application.get("source_repository") != WEATHER_REPOSITORY
                or application.get("staged") is not True
                or type(application_sha) is not str
                or _SHA40.fullmatch(application_sha) is None
            ):
                _fail("Weather application stage marker identity drifted")

        runtime = _strict_json(Path(RUNTIME_BASE) / RUNTIME_MARKER_NAME, required=False, mode=0o644)
        runtime_present = runtime is not None
        runtime_sha: str | None = None
        runtime_abi: str | None = None
        if runtime is not None:
            runtime_sha = runtime.get("source_sha")
            runtime_abi = runtime.get("target_python_abi")
            if (
                runtime.get("schema") != "rozkalns-weather.weathernext-private-runtime-installed.v1"
                or type(runtime_sha) is not str
                or _SHA40.fullmatch(runtime_sha) is None
                or runtime_abi != TARGET_PYTHON_ABI
                or runtime.get("bigquery_access") is not False
                or runtime.get("sqlite_write") is not False
            ):
                _fail("private runtime marker identity drifted")

        return SanitizedHostEvidence(
            host_capability_installed=capability_installed,
            host_capability_source_sha=capability_sha,
            application_staged=application_staged,
            application_source_sha=application_sha,
            runtime_present=runtime_present,
            runtime_source_sha=runtime_sha,
            runtime_python_abi=runtime_abi,
            auth_binding_state=self._ready_state(
                AUTH_READY_MARKER,
                schema="rozkalns-weather.weathernext-private-google-auth-ready.v1",
                slot_id=GOOGLE_AUTH_SLOT_ID,
            ),
            project_binding_state=self._ready_state(
                PROJECT_READY_MARKER,
                schema="rozkalns-weather.weathernext-private-google-project-ready.v1",
                slot_id=GOOGLE_PROJECT_SLOT_ID,
            ),
            linked_dataset_state=self._ready_state(
                LINK_READY_MARKER,
                schema="rozkalns-weather.weathernext-private-analytics-hub-ready.v1",
                slot_id=ANALYTICS_HUB_LINK_SLOT_ID,
            ),
        )


class ExecutionReadySanitizedHostEvidenceProvider(PosixSanitizedHostEvidenceProvider):
    """Reject missing prerequisite gates before durable authorization consumption."""

    def load_sanitized_host_evidence(self) -> SanitizedHostEvidence:
        evidence = super().load_sanitized_host_evidence()
        if (
            evidence.host_capability_installed is not True
            or evidence.application_staged is not True
            or evidence.runtime_present is not True
            or evidence.runtime_python_abi != TARGET_PYTHON_ABI
            or evidence.auth_binding_state != "ready"
            or evidence.project_binding_state != "ready"
            or evidence.linked_dataset_state != "ready"
        ):
            _fail("WeatherNext private prerequisite gates must be exact before one-shot consume")
        return evidence


class PosixPrivateRuntimeBindings:
    """Fixed runtime-only provider; first access is the only executable stage here."""

    @staticmethod
    def _receipt(stage: str, *, status: str = "completed", mutation: bool = False) -> StageReceipt:
        return StageReceipt(stage=stage, status=status, mutation_performed=mutation)

    def stage_exact_weather_application(self, weather_source_sha: str) -> StageReceipt:
        _fail("Weather application staging requires its separate exact LIVE gate")

    def load_runtime_artifact_receipt(self, rpi5_main_source_sha: str) -> RuntimeArtifactReceipt:
        value = _strict_json(ARTIFACT_RECEIPT, required=True, mode=0o644)
        receipt = RuntimeArtifactReceipt.from_mapping(value)
        if receipt.source_sha != rpi5_main_source_sha:
            _fail("runtime artifact receipt source SHA drifted")
        return receipt

    def bind_google_auth_slot(self) -> StageReceipt:
        _fail("Google auth binding requires its separate protected LIVE gate")

    def bind_google_project_slot(self) -> StageReceipt:
        _fail("Google project binding requires its separate protected LIVE gate")

    def ensure_analytics_hub_link_slot(self) -> StageReceipt:
        _fail("Analytics Hub link requires its separate protected LIVE gate")

    @staticmethod
    def _private_values() -> tuple[str, str, Path]:
        value = _strict_json(PRIVATE_VALUES, required=True, mode=0o600)
        if set(value) != {"schema", "project", "dataset", "credential_file"}:
            _fail("private first-access binding schema drifted")
        project = value.get("project")
        dataset = value.get("dataset")
        credential_file = value.get("credential_file")
        if (
            value.get("schema") != "rozkalns-weather.weathernext-private-first-access-binding.v1"
            or type(project) is not str
            or _PROJECT.fullmatch(project) is None
            or type(dataset) is not str
            or _DATASET.fullmatch(dataset) is None
            or type(credential_file) is not str
            or _CREDENTIAL_BASENAME.fullmatch(credential_file) is None
            or credential_file in {".", ".."}
        ):
            _fail("private first-access binding is incomplete")
        credential_path = CREDENTIAL_ROOT / credential_file
        _read_regular(
            credential_path,
            max_bytes=MAX_CREDENTIAL_BYTES,
            required=True,
            mode=0o600,
        )
        return project, dataset, credential_path

    def run_read_only_first_access(self, weather_source_sha: str, scope: FirstAccessScope) -> StageReceipt:
        validate_first_access_scope(scope)
        observed = ExecutionReadySanitizedHostEvidenceProvider().load_sanitized_host_evidence()
        if observed.application_source_sha != weather_source_sha:
            _fail("read-only first-access Weather source identity drifted")
        project, dataset, credential_path = self._private_values()
        site_packages = Path(RUNTIME_BASE) / "site-packages"
        weather_src = Path(APPLICATION_STAGE_ROOT) / "src"
        for fixed in (str(site_packages), str(weather_src)):
            if fixed not in sys.path:
                sys.path.insert(0, fixed)
        try:
            import google.auth  # type: ignore
            from google.cloud import bigquery  # type: ignore
            from rozkalns_weather.locations import DWD_10416
            from rozkalns_weather.providers.weathernext import WeatherNextBigQueryAdapter
            from rozkalns_weather.weathernext_access import (
                build_canary_plan,
                dry_run_canary_queries,
                read_first_access_canary,
                schema_summary,
            )
        except Exception:
            _fail("reviewed WeatherNext private runtime import failed closed")
        now = datetime.now(timezone.utc)
        plan = build_canary_plan(
            now=now,
            hours_limit=scope.forecast_hours,
            maximum_bytes_billed=scope.max_bytes_billed_per_query,
        )
        init_time = datetime.fromisoformat(str(plan["selected_init_time_utc"]).replace("Z", "+00:00"))
        try:
            credentials, credential_project = google.auth.load_credentials_from_file(str(credential_path))
        except Exception:
            _fail("fixed Google auth credential reference failed closed")
        if credential_project is not None and credential_project != project:
            _fail("fixed Google credential project binding mismatch")
        client = bigquery.Client(project=project, credentials=credentials)
        schema = schema_summary(
            WeatherNextBigQueryAdapter(project=project, dataset=dataset, client=client).schema_probe(
                maximum_bytes_billed=scope.max_bytes_billed_per_query
            )
        )
        if schema.get("state") != "linked_dataset_ready":
            _fail("WeatherNext linked-dataset/schema fingerprint preflight failed")
        dry = dry_run_canary_queries(
            client=client,
            project=project,
            dataset=dataset,
            lat=DWD_10416.lat,
            lon=DWD_10416.lon,
            init_time=init_time,
            hours_limit=scope.forecast_hours,
            maximum_bytes_billed=scope.max_bytes_billed_per_query,
        )
        narrowed_cap = max(item.estimated_bytes for item in dry)
        if not 1 <= narrowed_cap <= scope.max_bytes_billed_per_query:
            _fail("fresh dry-run cannot derive a defensible real-query cap")
        evidence, _runs = read_first_access_canary(
            client=client,
            project=project,
            dataset=dataset,
            now=now,
            init_time=init_time,
            maximum_bytes_billed=narrowed_cap,
        )
        if evidence.get("state") != "canary_ready_for_snapshot":
            _fail("WeatherNext first access did not reach sanitized canary readiness")
        return self._receipt(READ_ONLY_PRIVATE_BIGQUERY, mutation=False)


def build_installed_weather_private_runtime() -> Any:
    marker = _strict_json(ACTIVATION_MARKER, required=True, mode=0o644)
    source_sha = marker.get("rpi5_main_source_sha")
    if type(source_sha) is not str or _SHA40.fullmatch(source_sha) is None:
        _fail("installed host capability marker source SHA invalid")
    validate_activation_marker(marker, exact_rpi5_main_sha=source_sha)
    try:
        auth_surface = load_contract(ISOLATED_AUTH_PATH)
        require_isolated_auth_surface(auth_surface)
        sender = GitHubHttpsSender()
        read_clients = build_p9_read_clients(
            auth_surface=auth_surface,
            private_key=EXECUTOR_CREDENTIAL_PATH,
            sender=sender,
        )
        replay = WeatherNextReplayAuthority()
        box = _AcceptedBox()
        sources = PublicExactSourceEvidenceProvider(
            client=FixedPublicGitHubReadClient(sender=sender)
        )
        authorization = DeployAuthorizationEvidenceProvider(
            client=read_clients.authorization,
            replay=replay,
            box=box,
        )
        consumer = ReplayAuthorizationConsumer(
            client=read_clients.authorization,
            replay=replay,
            box=box,
            sources=sources,
        )
        return build_runtime_composition(
            authorization=authorization,
            sources=sources,
            host=ExecutionReadySanitizedHostEvidenceProvider(),
            authorization_consumer=consumer,
            bindings=PosixPrivateRuntimeBindings(),
        )
    except WeatherNextPrivateHostRuntimeError:
        raise
    except Exception:
        raise WeatherNextInstalledBindingsError(
            "installed WeatherNext private runtime composition failed closed"
        ) from None
