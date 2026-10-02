from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
from typing import Any, Callable, Mapping

from .hermes_deals_origin_runtime_adapters import (
    ConcreteDurableHermesOriginReplayAuthority,
)
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
from .weather_private_gcs_contract import (
    CONTRACT_ID,
    READ_ONLY_PRIVATE_GCS,
    GCSFirstAccessScope,
    validate_first_access_scope,
)
from .weather_private_gcs_execution_bridge import (
    BRIDGE_OPERATION_ID,
    GCSStageReceipt,
    TARGET_ALIAS,
)
from .weather_private_gcs_runtime_materialization import (
    RUNTIME_BASE,
    RUNTIME_MARKER_NAME,
    TARGET_PIP_PLATFORM,
    TARGET_PYTHON_ABI,
)
from .weather_private_gcs_trusted_backend import (
    APPLICATION_STAGE_ROOT,
    GOOGLE_AUTH_SLOT_ID,
)
from .weather_private_gcs_host_runtime import (
    ACTIVATION_MARKER,
    EXPECTED_GCS_RUNTIME_CLOSURE_SHA256,
    RPI5_MAIN_REPOSITORY,
    RPI5_MAIN_REPOSITORY_ID,
    WEATHER_REPOSITORY,
    WEATHER_REPOSITORY_ID,
    ExactSourceEvidence,
    OwnerAuthorizationEvidence,
    SanitizedGCSHostEvidence,
    WeatherNextPrivateGCSHostRuntimeError,
    build_runtime_composition,
    validate_activation_marker,
)

ISOLATED_AUTH_PATH = Path(
    "/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json"
)
EXECUTOR_CREDENTIAL_PATH = Path("/etc/rozkalns-deploy-executor/github-app.pem")
APPLICATION_MARKER = Path(APPLICATION_STAGE_ROOT) / "source-stage.json"
BINDING_ROOT = Path("/var/lib/rpi5-deploy/weather-private-gcs-bindings")
AUTH_READY_MARKER = BINDING_ROOT / "google-auth.ready.json"
PRIVATE_VALUES = BINDING_ROOT / "first-access-private.json"
CREDENTIAL_ROOT = BINDING_ROOT / "credentials"
MAX_MARKER_BYTES = 16 * 1024
MAX_CREDENTIAL_BYTES = 64 * 1024
WEATHER_REQUIRED_WORKFLOWS = ("tests.yml", "governance.yml")
GCS_AUTH_READY_SCHEMA = (
    "rozkalns-weather.weathernext-private-gcs-google-auth-ready.v1"
)
GCS_PRIVATE_BINDING_SCHEMA = (
    "rozkalns-weather.weathernext-private-gcs-first-access-binding.v1"
)
GCS_AUTH_PROVIDER_CLASS = "obstore.auth.google.GoogleCredentialProvider"
GCS_READONLY_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"
INIT_DEPENDENCY_PREFIX = "weathernext-init-utc:"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_CREDENTIAL_BASENAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class WeatherNextGCSInstalledBindingsError(
    WeatherNextPrivateGCSHostRuntimeError
):
    pass


def _fail(message: str) -> None:
    raise WeatherNextGCSInstalledBindingsError(message)


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
            _fail(f"required fixed GCS runtime state is absent: {path.name}")
        return None
    except OSError:
        _fail(f"fixed GCS runtime state metadata failed: {path.name}")
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or not 0 < before.st_size <= max_bytes
        or before.st_uid != uid
        or before.st_gid != gid
    ):
        _fail(f"fixed GCS runtime state shape or ownership drifted: {path.name}")
    if mode is not None and stat.S_IMODE(before.st_mode) != mode:
        _fail(f"fixed GCS runtime state mode drifted: {path.name}")
    flags = os.O_RDONLY
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        value = getattr(os, name, None)
        if value is None:
            _fail(f"required descriptor guard unavailable: {name}")
        flags |= value
    try:
        fd = os.open(path, flags)
    except OSError:
        _fail(f"fixed GCS runtime state open failed: {path.name}")
    try:
        opened = os.fstat(fd)
        if (
            (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or opened.st_uid != uid
            or opened.st_gid != gid
            or (mode is not None and stat.S_IMODE(opened.st_mode) != mode)
        ):
            _fail(f"fixed GCS runtime state changed before read: {path.name}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            try:
                chunk = os.read(fd, min(65536, remaining))
            except OSError:
                _fail(f"fixed GCS runtime state read failed: {path.name}")
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > max_bytes or len(raw) != opened.st_size:
            _fail(f"fixed GCS runtime state changed during read: {path.name}")
        try:
            after = path.lstat()
        except OSError:
            _fail(f"fixed GCS runtime state path changed during read: {path.name}")
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
            _fail(f"fixed GCS runtime state path changed during read: {path.name}")
        return raw
    finally:
        os.close(fd)


def _strict_json(
    path: Path,
    *,
    required: bool = True,
    mode: int | None = None,
) -> Mapping[str, Any] | None:
    raw = _read_regular(
        path,
        max_bytes=MAX_MARKER_BYTES,
        required=required,
        mode=mode,
    )
    if raw is None:
        return None
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError):
        _fail(f"fixed GCS runtime JSON is malformed: {path.name}")
    if type(value) is not dict:
        _fail(f"fixed GCS runtime JSON must be an object: {path.name}")
    return value


class FixedPublicGitHubReadClient:
    """Credential-free GET client restricted to the two reviewed source repositories."""

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
                "User-Agent": "rozkalns-weathernext-private-gcs-host/1",
            },
        )
        if response.status != 200:
            raise HTTPStatusError(response.status)
        date_header = next(
            (
                value
                for key, value in response.headers.items()
                if key.lower() == "date"
            ),
            None,
        )
        if type(date_header) is not str:
            _fail("public source response omitted Date header")
        try:
            server_time = parsedate_to_datetime(date_header)
            value = json.loads(response.body.decode("utf-8", "strict"))
        except (
            TypeError,
            ValueError,
            OverflowError,
            UnicodeError,
            json.JSONDecodeError,
        ):
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

    def load_exact_source(
        self, repository: str, repository_id: int
    ) -> ExactSourceEvidence:
        expected = {
            RPI5_MAIN_REPOSITORY: RPI5_MAIN_REPOSITORY_ID,
            WEATHER_REPOSITORY: WEATHER_REPOSITORY_ID,
        }
        if expected.get(repository) != repository_id:
            _fail("exact source request escaped reviewed repositories")
        value = self._client.get_json(
            f"/repos/{repository}/branches/main"
        ).value
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
            if (
                proof.repository_id != repository_id
                or proof.current_main_sha != current_sha
            ):
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


class WeatherNextGCSReplayAuthority:
    def __init__(self):
        self._delegate = ConcreteDurableHermesOriginReplayAuthority()

    def is_available(self, accepted: AcceptedAuthorization) -> bool:
        return self._delegate.is_available(accepted)

    def consume(self, request_id: str) -> Any:
        return self._delegate.consume(request_id)


@dataclass
class _AcceptedBox:
    accepted: AcceptedAuthorization | None = None


def _dependency(payload: Mapping[str, Any], prefix: str) -> str:
    values = [
        item[len(prefix) :]
        for item in payload.get("dependencies", [])
        if type(item) is str and item.startswith(prefix)
    ]
    if len(values) != 1 or not values[0]:
        _fail(f"owner authorization dependency missing: {prefix[:-1]}")
    return values[0]


def _selected_init(value: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        _fail("WeatherNext selected init dependency must use UTC Z form")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00").astimezone(
            timezone.utc
        )
    except (TypeError, ValueError, OverflowError):
        _fail("WeatherNext selected init dependency is malformed")
    if (
        parsed.year < 2026
        or parsed.minute
        or parsed.second
        or parsed.microsecond
    ):
        _fail("WeatherNext selected init dependency must be an exact UTC hour")
    return parsed


class DeployGCSAuthorizationEvidenceProvider:
    """Read one exact GCS owner LIVE-AUTH through the reviewed isolated auth surface."""

    def __init__(
        self,
        *,
        client: Any,
        replay: WeatherNextGCSReplayAuthority,
        box: _AcceptedBox,
    ):
        self._client = client
        self._replay = replay
        self._box = box

    def load_owner_authorization(
        self, authorization_issue_number: int
    ) -> OwnerAuthorizationEvidence:
        if (
            type(authorization_issue_number) is not int
            or authorization_issue_number <= 0
        ):
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
            != [{"category": READ_ONLY_PRIVATE_GCS, "max_operations": 1}]
        ):
            _fail(
                "owner authorization is not the fixed read-only WeatherNext GCS capability"
            )
        contract = _dependency(payload, "contract:")
        rpi_sha = _dependency(payload, "rpi5-main-sha:")
        init_utc = _selected_init(
            _dependency(payload, INIT_DEPENDENCY_PREFIX)
        )
        weather_sha = payload.get("source_sha")
        if (
            contract != CONTRACT_ID
            or type(rpi_sha) is not str
            or _SHA40.fullmatch(rpi_sha) is None
            or type(weather_sha) is not str
            or _SHA40.fullmatch(weather_sha) is None
        ):
            _fail("owner authorization GCS source or contract identity drifted")
        if (
            not self._replay.is_available(accepted)
            or not self._replay.is_available(accepted)
        ):
            _fail("owner authorization GCS replay boundary unavailable")
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
            selected_init_utc=init_utc,
        )


class ReplayGCSAuthorizationConsumer:
    """Revalidate exact source/auth state before durable GCS authorization consumption."""

    def __init__(
        self,
        *,
        client: Any,
        replay: WeatherNextGCSReplayAuthority,
        box: _AcceptedBox,
        sources: PublicExactSourceEvidenceProvider,
    ):
        self._client = client
        self._replay = replay
        self._box = box
        self._sources = sources
        self._consumed = False

    def consume_once(
        self, authorization_issue_number: int, *, first_stage: str
    ) -> None:
        if self._consumed:
            _fail("WeatherNext GCS authorization already consumed")
        accepted = self._box.accepted
        if (
            accepted is None
            or accepted.issue_number != authorization_issue_number
            or first_stage != READ_ONLY_PRIVATE_GCS
        ):
            _fail("WeatherNext GCS consume boundary identity drifted")
        payload = accepted.payload
        weather_sha = payload.get("source_sha")
        rpi_sha = _dependency(payload, "rpi5-main-sha:")
        rpi = self._sources.load_exact_source(
            RPI5_MAIN_REPOSITORY, RPI5_MAIN_REPOSITORY_ID
        )
        weather = self._sources.load_exact_source(
            WEATHER_REPOSITORY, WEATHER_REPOSITORY_ID
        )
        if rpi.source_sha != rpi_sha or weather.source_sha != weather_sha:
            _fail("exact GCS source drifted immediately before authorization consume")
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
            _fail("WeatherNext GCS replay consume receipt drifted")


def _glibc_compatible(name: str, version: str) -> bool:
    if type(name) is not str or name.lower() != "glibc" or type(version) is not str:
        return False
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", version.strip())
    if match is None:
        return False
    return (int(match.group(1)), int(match.group(2))) >= (2, 28)


class PosixSanitizedGCSHostEvidenceProvider:
    """Observe only public-safe GCS marker identity; never read credential values."""

    def __init__(
        self,
        *,
        json_reader: Callable[..., Mapping[str, Any] | None] | None = None,
        libc_provider: Callable[[], tuple[str, str]] | None = None,
    ):
        self._json_reader = json_reader or _strict_json
        self._libc_provider = libc_provider or platform.libc_ver

    def _ready_state(self, path: Path) -> str:
        value = self._json_reader(path, required=False, mode=0o644)
        if value is None:
            return "absent"
        expected = {
            "schema": GCS_AUTH_READY_SCHEMA,
            "slot_id": GOOGLE_AUTH_SLOT_ID,
            "provider_class": GCS_AUTH_PROVIDER_CLASS,
            "ready": True,
        }
        return "ready" if dict(value) == expected else "mismatch"

    def load_sanitized_host_evidence(self) -> SanitizedGCSHostEvidence:
        capability = self._json_reader(
            ACTIVATION_MARKER, required=False, mode=0o644
        )
        capability_installed = capability is not None
        capability_sha: str | None = None
        if capability is not None:
            capability_sha = capability.get("rpi5_main_source_sha")
            if (
                type(capability_sha) is not str
                or _SHA40.fullmatch(capability_sha) is None
            ):
                _fail("GCS host capability activation marker source SHA invalid")
            validate_activation_marker(
                capability, exact_rpi5_main_sha=capability_sha
            )

        application = self._json_reader(
            APPLICATION_MARKER, required=False, mode=0o644
        )
        application_staged = application is not None
        application_sha: str | None = None
        if application is not None:
            application_sha = application.get("source_sha")
            if (
                set(application)
                != {"schema", "source_repository", "source_sha", "staged"}
                or application.get("schema")
                != "rozkalns-weather.weathernext-private-application-stage.v1"
                or application.get("source_repository") != WEATHER_REPOSITORY
                or application.get("staged") is not True
                or type(application_sha) is not str
                or _SHA40.fullmatch(application_sha) is None
            ):
                _fail("Weather application stage marker identity drifted")

        runtime = self._json_reader(
            Path(RUNTIME_BASE) / RUNTIME_MARKER_NAME,
            required=False,
            mode=0o644,
        )
        runtime_present = runtime is not None
        runtime_sha: str | None = None
        runtime_closure: str | None = None
        runtime_abi: str | None = None
        runtime_platform: str | None = None
        if runtime is not None:
            runtime_sha = runtime.get("source_sha")
            runtime_closure = runtime.get("closure_sha256")
            runtime_abi = runtime.get("target_python_abi")
            runtime_platform = runtime.get("target_platform")
            if (
                runtime.get("schema")
                != "rozkalns-weather.weathernext-private-gcs-runtime-installed.v1"
                or type(runtime_sha) is not str
                or _SHA40.fullmatch(runtime_sha) is None
                or runtime_closure
                != EXPECTED_GCS_RUNTIME_CLOSURE_SHA256
                or type(runtime_closure) is not str
                or _SHA64.fullmatch(runtime_closure) is None
                or runtime_abi != TARGET_PYTHON_ABI
                or runtime_platform != TARGET_PIP_PLATFORM
                or runtime.get("credential_binding") is not False
                or runtime.get("google_gcs_access") is not False
                or runtime.get("project_binding") is not False
                or runtime.get("analytics_hub_link") is not False
                or runtime.get("bigquery_access") is not False
                or runtime.get("sqlite_write") is not False
            ):
                _fail("private GCS runtime marker identity drifted")

        libc_name, libc_version = self._libc_provider()
        return SanitizedGCSHostEvidence(
            host_capability_installed=capability_installed,
            host_capability_source_sha=capability_sha,
            application_staged=application_staged,
            application_source_sha=application_sha,
            runtime_present=runtime_present,
            runtime_source_sha=runtime_sha,
            runtime_closure_sha256=runtime_closure,
            runtime_python_abi=runtime_abi,
            runtime_target_platform=runtime_platform,
            host_glibc_compatible=_glibc_compatible(
                libc_name, libc_version
            ),
            auth_binding_state=self._ready_state(AUTH_READY_MARKER),
        )


class ExecutionReadySanitizedGCSHostEvidenceProvider(
    PosixSanitizedGCSHostEvidenceProvider
):
    """Reject missing GCS prerequisites before durable authorization consumption."""

    def load_sanitized_host_evidence(self) -> SanitizedGCSHostEvidence:
        evidence = super().load_sanitized_host_evidence()
        if (
            evidence.host_capability_installed is not True
            or evidence.application_staged is not True
            or evidence.runtime_present is not True
            or evidence.runtime_closure_sha256
            != EXPECTED_GCS_RUNTIME_CLOSURE_SHA256
            or evidence.runtime_python_abi != TARGET_PYTHON_ABI
            or evidence.runtime_target_platform != TARGET_PIP_PLATFORM
            or evidence.host_glibc_compatible is not True
            or evidence.auth_binding_state != "ready"
        ):
            _fail(
                "WeatherNext GCS prerequisite gates must be exact before one-shot consume"
            )
        return evidence


class PosixGCSRuntimeBindings:
    """Fixed runtime-only GCS provider; mutation prerequisites remain separate LIVE gates."""

    @staticmethod
    def _receipt(
        stage: str,
        *,
        status: str = "completed",
        mutation: bool = False,
    ) -> GCSStageReceipt:
        return GCSStageReceipt(
            stage=stage,
            status=status,
            mutation_performed=mutation,
        )

    def stage_exact_weather_application(
        self, weather_source_sha: str
    ) -> GCSStageReceipt:
        _fail("Weather application staging requires its separate exact LIVE gate")

    def materialize_exact_gcs_runtime(
        self, rpi5_main_source_sha: str
    ) -> GCSStageReceipt:
        _fail("WeatherNext GCS runtime materialization requires its separate exact LIVE gate")

    def bind_google_auth_slot(self) -> GCSStageReceipt:
        _fail("WeatherNext GCS auth binding requires its separate protected LIVE gate")

    @staticmethod
    def _credential_path() -> Path:
        value = _strict_json(PRIVATE_VALUES, required=True, mode=0o600)
        if value is None or set(value) != {"schema", "credential_file"}:
            _fail("private GCS first-access binding schema drifted")
        credential_file = value.get("credential_file")
        if (
            value.get("schema") != GCS_PRIVATE_BINDING_SCHEMA
            or type(credential_file) is not str
            or _CREDENTIAL_BASENAME.fullmatch(credential_file) is None
            or credential_file in {".", ".."}
        ):
            _fail("private GCS first-access binding is incomplete")
        credential_path = CREDENTIAL_ROOT / credential_file
        _read_regular(
            credential_path,
            max_bytes=MAX_CREDENTIAL_BYTES,
            required=True,
            mode=0o600,
        )
        return credential_path

    def run_read_only_first_access(
        self,
        weather_source_sha: str,
        scope: GCSFirstAccessScope,
    ) -> GCSStageReceipt:
        validated = validate_first_access_scope(scope)
        observed = (
            ExecutionReadySanitizedGCSHostEvidenceProvider()
            .load_sanitized_host_evidence()
        )
        if observed.application_source_sha != weather_source_sha:
            _fail("read-only GCS first-access Weather source identity drifted")
        credential_path = self._credential_path()
        site_packages = Path(RUNTIME_BASE) / "site-packages"
        weather_src = Path(APPLICATION_STAGE_ROOT) / "src"
        for fixed in (str(site_packages), str(weather_src)):
            if fixed not in sys.path:
                sys.path.insert(0, fixed)
        try:
            import google.auth  # type: ignore
            from obstore.auth.google import GoogleCredentialProvider  # type: ignore
            from rozkalns_weather.weathernext_gcs_transport import (  # type: ignore
                read_private_first_access_gcs,
            )
        except Exception:
            _fail("reviewed WeatherNext GCS runtime import failed closed")
        try:
            credentials, _credential_project = google.auth.load_credentials_from_file(
                str(credential_path),
                scopes=[GCS_READONLY_SCOPE],
            )
            credential_provider = GoogleCredentialProvider(
                credentials=credentials
            )
        except Exception:
            _fail("fixed GCS credential reference failed closed")
        result = read_private_first_access_gcs(
            init_time=scope.selected_init_utc,
            retrieved_at=datetime.now(timezone.utc),
            credential_provider=credential_provider,
        )
        evidence = result.evidence
        expected_init = validated["selected_init_utc"]
        if (
            evidence.get("state") != "gcs_canary_complete"
            or evidence.get("location_id") != "station_05480"
            or evidence.get("selected_init_time_utc") != expected_init
            or evidence.get("lead_count") != 6
            or evidence.get("materialized_scalar_count") != 288
            or evidence.get("schema_valid") is not True
            or evidence.get("provenance_complete") is not True
            or evidence.get("automatic_retry_used") is not False
            or evidence.get("coordinates_exposed") is not False
            or evidence.get("raw_values_exposed") is not False
            or evidence.get("production_write_performed") is not False
        ):
            _fail("WeatherNext GCS first access did not reach sanitized canary readiness")
        return self._receipt(READ_ONLY_PRIVATE_GCS, mutation=False)


def build_installed_weather_private_gcs_runtime() -> Any:
    marker = _strict_json(ACTIVATION_MARKER, required=True, mode=0o644)
    if marker is None:
        _fail("installed GCS host capability marker is absent")
    source_sha = marker.get("rpi5_main_source_sha")
    if type(source_sha) is not str or _SHA40.fullmatch(source_sha) is None:
        _fail("installed GCS host capability marker source SHA invalid")
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
        replay = WeatherNextGCSReplayAuthority()
        box = _AcceptedBox()
        sources = PublicExactSourceEvidenceProvider(
            client=FixedPublicGitHubReadClient(sender=sender)
        )
        authorization = DeployGCSAuthorizationEvidenceProvider(
            client=read_clients.authorization,
            replay=replay,
            box=box,
        )
        consumer = ReplayGCSAuthorizationConsumer(
            client=read_clients.authorization,
            replay=replay,
            box=box,
            sources=sources,
        )
        return build_runtime_composition(
            authorization=authorization,
            sources=sources,
            host=ExecutionReadySanitizedGCSHostEvidenceProvider(),
            authorization_consumer=consumer,
            bindings=PosixGCSRuntimeBindings(),
        )
    except WeatherNextPrivateGCSHostRuntimeError:
        raise
    except Exception:
        raise WeatherNextGCSInstalledBindingsError(
            "installed WeatherNext GCS runtime composition failed closed"
        ) from None
