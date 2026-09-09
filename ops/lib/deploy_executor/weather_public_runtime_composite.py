from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Protocol, Sequence

from .adapters import prepare_operation
from .p9_canary import require_isolated_auth_surface
from .p9_runtime import P9ExecutorInstallationTokenProvider
from email.utils import parsedate_to_datetime

from .transport import API_VERSION, GitHubHttpsSender, HTTPStatusError, JSONResponse
from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    QUEUE_REPOSITORY,
    QUEUE_REPOSITORY_ID,
    AcceptedAuthorization,
    accept_issue,
    validate_queue_binding,
    verify_authorization_unchanged,
)
from .queue_normalizer import normalize_ready_queue
from .transport import GitHubRestClient
from .weather_public_runtime_adapter import (
    ADAPTER_ID,
    BASELINE_RESOLVER_ID,
    MUTATION_BUDGET as RELEASE_MUTATION_BUDGET,
    OPERATION_ID,
    REQUIRED_EXCLUSIONS,
    ROLLBACK_POLICY,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    TARGET_ALIAS,
    WeatherPublicRuntimeAdapter,
)
from .weather_public_runtime_bootstrap import (
    BASELINE_EVIDENCE_SCHEMA,
    BOOTSTRAP_CAPABILITY_ID,
    FORECAST_MODELS,
    MAX_BACKFILL_DAYS,
    PUBLIC_INGEST_CADENCE,
    RECOVERY_DECISIONS,
    REQUEST_SCHEMA,
    RUN_HOURS,
    RUNTIME_CLASS,
    TRUTH_CHUNK_DAYS,
    TRUTH_PROVIDER,
    TRUTH_STATION_ID,
    CanonicalWeatherBootstrapEvidence,
    SanitizedWeatherBootstrapBaselineResolver,
    parse_weather_bootstrap_baseline,
    prepare_weather_bootstrap_dispatch,
)

COMPOSITE_SCHEMA = "rozkalns.weather-composite-live-auth.v1"
COMPOSITE_CONTRACT = "rozkalns-weather.public-runtime-composite-live.v1"
COMPOSITE_RESULT = "WEATHER_COMPOSITE_LIVE_SOURCE_READY"
COMPOSITE_START_MARKER = "<!-- rozkalns-weather-composite-live-auth:v1 -->"
COMPOSITE_END_MARKER = "<!-- /rozkalns-weather-composite-live-auth:v1 -->"
HOST_ALIAS = "rpi5"
RPI5_MAIN_SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
RPI5_MAIN_SOURCE_REPOSITORY_ID = 1323383044
WEATHER_SOURCE_WORKFLOW = "tests.yml"
RPI5_MAIN_SOURCE_WORKFLOW = "validate.yml"
HELPER_INSTALL_ARTIFACT_COUNT = 13
RPI5_MIN_REVIEWED_ANCESTOR = "95b6b95b132614cbc330d6d764d0557079a67534"
MAX_GITHUB_TIMESTAMP_SPREAD_SECONDS = 30

ADDITIONAL_MUTATION_BUDGET = (
    ("git.trusted-checkout-fetch", 1),
    ("git.trusted-checkout-worktree-add", 1),
    ("filesystem.weather-helper-install-transaction", 1),
    ("filesystem.weather-helper-activation-publish", 1),
    ("sqlite.schema-init", 1),
    ("sqlite.corpus-truth-backfill", 1),
    ("sqlite.corpus-forecast-backfill", len(FORECAST_MODELS)),
)
READ_ONLY_STAGE_BUDGET = (
    ("readiness_schema_privacy", 1),
    ("public_smoke_read_only", 1),
    ("corpus_integrity_check", len(FORECAST_MODELS)),
)
FULL_MUTATION_BUDGET = RELEASE_MUTATION_BUDGET + ADDITIONAL_MUTATION_BUDGET
COMPOSITE_GATE_ORDER = (
    "trusted_checkout_fetch",
    "trusted_checkout_worktree_add",
    "helper_install",
    "activation_publish",
    "application_release",
    "persistent_volume_ensure",
    "explicit_schema_init",
    "readiness_schema_privacy",
    "public_smoke_read_only",
    "bounded_dwd_truth_backfill",
    "bounded_deterministic_forecast_backfill",
    "corpus_integrity_check",
    "recurring_public_ingest_schedule",
)
_RELEASE_APPLICATION_CATEGORIES = (
    "filesystem.release-materialization",
    "docker.compose-build",
    "docker.compose-application-apply",
)
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMPOSITE_PAYLOAD_RE = re.compile(
    re.escape(COMPOSITE_START_MARKER)
    + r"\n```json\n(?P<payload>.*?)\n```\n"
    + re.escape(COMPOSITE_END_MARKER),
    re.DOTALL,
)
_COMPOSITE_FIELDS = frozenset(
    {
        "schema",
        "host_alias",
        "rpi5_main_sha",
        "expected_bootstrap_baseline_token",
        "start_date",
        "end_date",
        "recovery_decision",
        "helper_install_artifact_count",
        "additional_mutation_budget",
    }
)


class WeatherCompositeAuthorityError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeatherCompositeSupplement:
    host_alias: str
    rpi5_main_sha: str
    expected_bootstrap_baseline_token: str
    start_date: str
    end_date: str
    recovery_decision: str
    helper_install_artifact_count: int
    additional_mutation_budget: tuple[tuple[str, int], ...]
    canonical_sha256: str


@dataclass(frozen=True)
class WeatherCompositeAuthorityEvidence:
    authorization_issue_number: int
    authorization_issue_id: int
    authorization_created_at: str
    github_server_time: str
    request_id: str
    authorization_payload_sha256: str
    authorization_raw_body_sha256: str
    composite_authorization_sha256: str
    queue_issue_number: int
    source_sha: str
    weather_current_main_sha: str
    weather_ci_run_id: int
    rpi5_main_sha: str
    rpi5_main_ci_run_id: int
    host_alias: str
    target_alias: str
    expected_bootstrap_baseline_token: str
    start_date: str
    end_date: str
    recovery_decision: str
    release_mutation_budget: tuple[tuple[str, int], ...]
    additional_mutation_budget: tuple[tuple[str, int], ...]
    full_mutation_budget: tuple[tuple[str, int], ...]
    authorization_owner_verified: bool = True
    authorization_ttl_valid: bool = True
    authorization_body_unchanged: bool = True
    authorization_replay_available: bool = True
    queue_ready: bool = True
    queue_binding_valid: bool = True
    registry_execution_enabled: bool = False
    source_reachable_from_main: bool = True
    source_ci_success: bool = True
    rpi5_main_exact: bool = True
    rpi5_main_ci_success: bool = True
    public_only_private_inputs_absent: bool = True
    production_mutation_started: bool = False


@dataclass(frozen=True)
class WeatherCompositeSourcePlan:
    authorization_issue_number: int
    source_sha: str
    rpi5_main_sha: str
    target_alias: str
    host_alias: str
    composite_authorization_sha256: str
    expected_bootstrap_baseline_token: str
    start_date: str
    end_date: str
    recovery_decision: str
    release_mutation_budget: tuple[tuple[str, int], ...]
    additional_mutation_budget: tuple[tuple[str, int], ...]
    full_mutation_budget: tuple[tuple[str, int], ...]
    read_only_stage_budget: tuple[tuple[str, int], ...]
    gate_order: tuple[str, ...] = COMPOSITE_GATE_ORDER
    runtime_live_authority: bool = False
    trusted_checkout_enabled: bool = False
    helper_installation_enabled: bool = False
    activation_publication_enabled: bool = False
    privileged_dispatch_enabled: bool = False
    production_mutation_enabled: bool = False
    production_mutation_started: bool = False
    automatic_retry_cleanup_rollback: bool = False


@dataclass(frozen=True)
class FixedPublicSourceEvidence:
    repository: str
    repository_id: int
    source_sha: str
    current_main_sha: str
    workflow: str
    run_id: int


class AuthorizationReplayAvailability(Protocol):
    def is_available(self, accepted: AcceptedAuthorization) -> bool: ...


class SanitizedWeatherBaselineProvider(Protocol):
    def resolve(self, *, source_sha: str, target_alias: str) -> Mapping[str, Any]: ...


@dataclass
class _GitHubTimeWindow:
    first: datetime | None = None
    last: datetime | None = None

    def observe(self, value: Any) -> None:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise WeatherCompositeAuthorityError("GitHub response time is unavailable")
        observed = value.astimezone(timezone.utc)
        if observed.microsecond != 0:
            raise WeatherCompositeAuthorityError(
                "GitHub response time is not canonical to whole seconds"
            )
        if self.last is not None and observed < self.last:
            raise WeatherCompositeAuthorityError(
                "GitHub response time regressed during Weather revalidation"
            )
        if self.first is None:
            self.first = observed
        if (observed - self.first).total_seconds() > MAX_GITHUB_TIMESTAMP_SPREAD_SECONDS:
            raise WeatherCompositeAuthorityError(
                "GitHub response times are inconsistent during Weather revalidation"
            )
        self.last = observed

    def canonical_last(self) -> str:
        if self.last is None:
            raise WeatherCompositeAuthorityError("Weather revalidation observed no GitHub time")
        return self.last.strftime("%Y-%m-%dT%H:%M:%SZ")


class FixedPublicGitHubReadClient:
    """Credential-free reader restricted to the two public Weather source repositories."""

    _ALLOWED_REPOSITORIES = frozenset(
        {SOURCE_REPOSITORY, RPI5_MAIN_SOURCE_REPOSITORY}
    )

    def __init__(self, *, sender: GitHubHttpsSender | None = None):
        self._sender = sender or GitHubHttpsSender()

    @staticmethod
    def _repository_for_path(path: str) -> str:
        if type(path) is not str or not path.startswith("/repos/"):
            raise WeatherCompositeAuthorityError(
                "public Weather source read path is outside fixed GitHub repositories"
            )
        remainder = path[len("/repos/") :]
        parts = remainder.split("/", 2)
        if len(parts) < 2:
            raise WeatherCompositeAuthorityError(
                "public Weather source read path is malformed"
            )
        repository = f"{parts[0]}/{parts[1].split('?', 1)[0]}"
        if repository not in FixedPublicGitHubReadClient._ALLOWED_REPOSITORIES:
            raise WeatherCompositeAuthorityError(
                "public Weather source read repository is not allowlisted"
            )
        return repository

    def get_json(self, path_or_url: str) -> JSONResponse:
        self._repository_for_path(path_or_url)
        if not path_or_url.startswith("/"):
            raise WeatherCompositeAuthorityError(
                "public Weather source reader accepts relative API paths only"
            )
        url = "https://api.github.com" + path_or_url
        response = self._sender.send(
            method="GET",
            url=url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "rozkalns-weather-public-source-read/1",
            },
        )
        if response.status != 200:
            raise HTTPStatusError(response.status)
        date_header = next(
            (value for key, value in response.headers.items() if key.lower() == "date"),
            None,
        )
        if type(date_header) is not str:
            raise WeatherCompositeAuthorityError(
                "public GitHub source response omitted Date header"
            )
        try:
            server_time = parsedate_to_datetime(date_header)
        except (TypeError, ValueError, OverflowError) as exc:
            raise WeatherCompositeAuthorityError(
                "public GitHub source Date header is invalid"
            ) from exc
        if server_time.tzinfo is None:
            raise WeatherCompositeAuthorityError(
                "public GitHub source Date header has no timezone"
            )
        try:
            value = json.loads(response.body.decode("utf-8", "strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise WeatherCompositeAuthorityError(
                "public GitHub source response is malformed JSON"
            ) from exc
        return JSONResponse(
            value=value,
            server_time=server_time.astimezone(timezone.utc),
            etag=None,
            not_modified=False,
            url=url,
            next_url=None,
        )


class _TimedSourceClient:
    def __init__(self, client: FixedPublicGitHubReadClient, window: _GitHubTimeWindow):
        self._client = client
        self._window = window

    def get_json(self, path_or_url: str) -> Any:
        response = self._client.get_json(path_or_url)
        self._window.observe(getattr(response, "server_time", None))
        return response

def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise WeatherCompositeAuthorityError("duplicate composite authorization JSON key")
        value[key] = item
    return value


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise WeatherCompositeAuthorityError(
            "composite authorization cannot be canonicalized"
        ) from exc


def _parse_budget(value: Any) -> tuple[tuple[str, int], ...]:
    if type(value) is not list:
        raise WeatherCompositeAuthorityError("composite additional mutation budget is invalid")
    observed: list[tuple[str, int]] = []
    for item in value:
        if type(item) is not dict or set(item) != {"category", "max_operations"}:
            raise WeatherCompositeAuthorityError(
                "composite additional mutation budget entry is invalid"
            )
        category = item["category"]
        maximum = item["max_operations"]
        if type(category) is not str or type(maximum) is not int:
            raise WeatherCompositeAuthorityError(
                "composite additional mutation budget types are invalid"
            )
        observed.append((category, maximum))
    result = tuple(observed)
    if result != ADDITIONAL_MUTATION_BUDGET:
        raise WeatherCompositeAuthorityError(
            "composite additional mutation budget drifted"
        )
    return result


def parse_weather_composite_supplement(body: Any) -> WeatherCompositeSupplement:
    if type(body) is not str:
        raise WeatherCompositeAuthorityError("composite authorization body is invalid")
    if body.count(COMPOSITE_START_MARKER) != 1 or body.count(COMPOSITE_END_MARKER) != 1:
        raise WeatherCompositeAuthorityError(
            "exactly one Weather composite authorization block is required"
        )
    match = _COMPOSITE_PAYLOAD_RE.search(body)
    if match is None:
        raise WeatherCompositeAuthorityError(
            "Weather composite authorization block is malformed"
        )
    try:
        payload = json.loads(
            match.group("payload"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                WeatherCompositeAuthorityError(
                    f"invalid composite JSON number {value!r}"
                )
            ),
        )
    except WeatherCompositeAuthorityError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WeatherCompositeAuthorityError(
            "Weather composite authorization JSON is malformed"
        ) from exc
    if type(payload) is not dict or frozenset(payload) != _COMPOSITE_FIELDS:
        raise WeatherCompositeAuthorityError(
            "Weather composite authorization fields drifted"
        )
    if payload["schema"] != COMPOSITE_SCHEMA:
        raise WeatherCompositeAuthorityError("Weather composite schema drifted")
    if payload["host_alias"] != HOST_ALIAS:
        raise WeatherCompositeAuthorityError("Weather composite host alias drifted")
    rpi5_main_sha = payload["rpi5_main_sha"]
    if type(rpi5_main_sha) is not str or _SHA40_RE.fullmatch(rpi5_main_sha) is None:
        raise WeatherCompositeAuthorityError("Weather composite RPi5_main SHA is invalid")
    token = payload["expected_bootstrap_baseline_token"]
    if (
        type(token) is not str
        or not 1 <= len(token) <= 512
        or "\n" in token
        or "\r" in token
    ):
        raise WeatherCompositeAuthorityError(
            "Weather composite expected baseline token is invalid"
        )
    start_text = payload["start_date"]
    end_text = payload["end_date"]
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except (TypeError, ValueError) as exc:
        raise WeatherCompositeAuthorityError(
            "Weather composite date bounds are invalid"
        ) from exc
    if start.isoformat() != start_text or end.isoformat() != end_text:
        raise WeatherCompositeAuthorityError(
            "Weather composite date bounds are not canonical"
        )
    if end < start or (end - start).days + 1 > MAX_BACKFILL_DAYS:
        raise WeatherCompositeAuthorityError(
            "Weather composite date bounds exceed reviewed maximum"
        )
    recovery = payload["recovery_decision"]
    if recovery not in RECOVERY_DECISIONS:
        raise WeatherCompositeAuthorityError(
            "Weather composite recovery decision is invalid"
        )
    if payload["helper_install_artifact_count"] != HELPER_INSTALL_ARTIFACT_COUNT:
        raise WeatherCompositeAuthorityError(
            "Weather composite helper install artifact count drifted"
        )
    additional_budget = _parse_budget(payload["additional_mutation_budget"])
    canonical_sha = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return WeatherCompositeSupplement(
        host_alias=HOST_ALIAS,
        rpi5_main_sha=rpi5_main_sha,
        expected_bootstrap_baseline_token=token,
        start_date=start_text,
        end_date=end_text,
        recovery_decision=recovery,
        helper_install_artifact_count=HELPER_INSTALL_ARTIFACT_COUNT,
        additional_mutation_budget=additional_budget,
        canonical_sha256=canonical_sha,
    )


def _require_repository(
    response: Any,
    *,
    repository: str,
    repository_id: int,
    window: _GitHubTimeWindow,
) -> None:
    window.observe(getattr(response, "server_time", None))
    value = getattr(response, "value", None)
    if type(value) is not dict:
        raise WeatherCompositeAuthorityError("GitHub repository response is malformed")
    if value.get("id") != repository_id or value.get("full_name") != repository:
        raise WeatherCompositeAuthorityError("GitHub repository identity drifted")


def _require_issue_response(
    response: Any,
    *,
    issue_number: int,
    repository: str,
    window: _GitHubTimeWindow,
) -> Mapping[str, Any]:
    window.observe(getattr(response, "server_time", None))
    value = getattr(response, "value", None)
    if type(value) is not dict or value.get("number") != issue_number:
        raise WeatherCompositeAuthorityError("GitHub issue identity drifted")
    expected_url = f"https://api.github.com/repos/{repository}"
    if value.get("repository_url") not in {None, expected_url}:
        raise WeatherCompositeAuthorityError("GitHub issue repository identity drifted")
    return value


def _require_read_clients(
    authorization_client: GitHubRestClient,
    queue_client: GitHubRestClient,
    source_client: FixedPublicGitHubReadClient,
) -> None:
    if type(authorization_client) is not GitHubRestClient:
        raise WeatherCompositeAuthorityError(
            "Weather authorization client is not the reviewed GitHub client"
        )
    if type(queue_client) is not GitHubRestClient:
        raise WeatherCompositeAuthorityError(
            "Weather queue client is not the reviewed GitHub client"
        )
    if type(source_client) is not FixedPublicGitHubReadClient:
        raise WeatherCompositeAuthorityError(
            "Weather source client is not the fixed credential-free public reader"
        )
    auth_provider = authorization_client.token_provider
    queue_provider = queue_client.token_provider
    if type(auth_provider) is not P9ExecutorInstallationTokenProvider:
        raise WeatherCompositeAuthorityError("Weather authorization client identity drifted")
    if type(queue_provider) is not P9ExecutorInstallationTokenProvider:
        raise WeatherCompositeAuthorityError("Weather queue client identity drifted")
    if (
        auth_provider.repository != AUTHORIZATION_REPOSITORY
        or auth_provider.repository_id != AUTHORIZATION_REPOSITORY_ID
        or queue_provider.repository != QUEUE_REPOSITORY
        or queue_provider.repository_id != QUEUE_REPOSITORY_ID
    ):
        raise WeatherCompositeAuthorityError(
            "Weather control-plane read client repository binding drifted"
        )

def _release_budget_payload() -> list[dict[str, object]]:
    return [
        {"category": category, "max_operations": maximum}
        for category, maximum in RELEASE_MUTATION_BUDGET
    ]


def _require_release_authority(
    accepted: AcceptedAuthorization,
    supplement: WeatherCompositeSupplement,
) -> None:
    payload = accepted.payload
    expected = {
        "queue_repository": QUEUE_REPOSITORY,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "expected_baseline": {"kind": "resolver", "value": BASELINE_RESOLVER_ID},
        "mutation_budget": _release_budget_payload(),
        "rollback_policy": ROLLBACK_POLICY,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise WeatherCompositeAuthorityError(
                f"generic Weather release LIVE-AUTH {field} drifted"
            )
    exclusions = payload.get("exclusions")
    if type(exclusions) is not list or not REQUIRED_EXCLUSIONS.issubset(set(exclusions)):
        raise WeatherCompositeAuthorityError(
            "generic Weather release LIVE-AUTH exclusions drifted"
        )
    generic_categories = {category for category, _ in RELEASE_MUTATION_BUDGET}
    additional_categories = {
        category for category, _ in supplement.additional_mutation_budget
    }
    if generic_categories & additional_categories:
        raise WeatherCompositeAuthorityError(
            "release and supplemental Weather mutation authorities overlap"
        )
    if any(category.startswith("sqlite.") for category in generic_categories):
        raise WeatherCompositeAuthorityError(
            "generic Weather release LIVE-AUTH cannot authorize SQLite"
        )
    if (
        "SQLite schema initialization or historical corpus backfill"
        not in set(exclusions)
    ):
        raise WeatherCompositeAuthorityError(
            "generic Weather release LIVE-AUTH no longer excludes SQLite/backfill"
        )


def _require_weather_operation(normalized: Any) -> tuple[Any, Mapping[str, Any]]:
    if getattr(normalized, "execution_enabled", None) is not False:
        raise WeatherCompositeAuthorityError(
            "Weather operation registry must remain execution-disabled"
        )
    operation = getattr(normalized, "operation", None)
    expected = {
        "operation_id": OPERATION_ID,
        "adapter_id": ADAPTER_ID,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "authorization_class": "STRICT",
        "ordinary_live_all_eligible": False,
        "rollback_policy": ROLLBACK_POLICY,
    }
    for name, value in expected.items():
        if getattr(operation, name, None) != value:
            raise WeatherCompositeAuthorityError(
                f"canonical Weather operation {name} drifted"
            )
    observed_budget = tuple(
        (item.category, item.max_operations)
        for item in getattr(operation, "mutation_budget", ())
    )
    if observed_budget != RELEASE_MUTATION_BUDGET:
        raise WeatherCompositeAuthorityError("Weather registry release budget drifted")
    observed_exclusions = set(getattr(operation, "exclusions", ()))
    if not REQUIRED_EXCLUSIONS.issubset(observed_exclusions):
        raise WeatherCompositeAuthorityError("Weather registry exclusions drifted")
    baseline = getattr(operation, "baseline", None)
    if (
        getattr(baseline, "kind", None) != "resolver"
        or getattr(baseline, "resolver_id", None) != BASELINE_RESOLVER_ID
    ):
        raise WeatherCompositeAuthorityError("Weather registry baseline drifted")
    protocol_queue = normalized.as_protocol_queue()
    if protocol_queue.get("expected_baseline") != {
        "kind": "resolver",
        "value": BASELINE_RESOLVER_ID,
    }:
        raise WeatherCompositeAuthorityError("Weather queue baseline binding drifted")
    prepared = prepare_operation(normalized)
    result = WeatherPublicRuntimeAdapter().preflight(prepared)
    if (
        result.get("execution_enabled") is not False
        or result.get("privileged_dispatch_ready") is not False
        or result.get("read_only_contract") is not True
    ):
        raise WeatherCompositeAuthorityError("Weather adapter preflight drifted")
    return operation, protocol_queue



def _require_object(value: Any, where: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise WeatherCompositeAuthorityError(f"{where} is malformed")
    return value


def _require_exact_sha(value: Any, where: str) -> str:
    if type(value) is not str or _SHA40_RE.fullmatch(value) is None:
        raise WeatherCompositeAuthorityError(f"{where} is not an exact Git SHA")
    return value


def _verify_fixed_public_source(
    client: _TimedSourceClient,
    *,
    repository: str,
    repository_id: int,
    source_sha: str,
    workflow: str,
    require_exact_main: bool,
) -> FixedPublicSourceEvidence:
    _require_exact_sha(source_sha, "authorized source SHA")
    repository_value = _require_object(
        client.get_json(f"/repos/{repository}").value,
        "public source repository",
    )
    if (
        repository_value.get("id") != repository_id
        or repository_value.get("full_name") != repository
        or repository_value.get("default_branch") != "main"
        or repository_value.get("private") is not False
    ):
        raise WeatherCompositeAuthorityError(
            "public source repository identity/visibility drifted"
        )
    branch = _require_object(
        client.get_json(f"/repos/{repository}/branches/main").value,
        "public source main branch",
    )
    commit = _require_object(branch.get("commit"), "public source main commit")
    main_sha = _require_exact_sha(commit.get("sha"), "public source main SHA")
    if require_exact_main:
        if source_sha != main_sha:
            raise WeatherCompositeAuthorityError(
                "authorized public source SHA is not exact current main"
            )
    elif source_sha != main_sha:
        compare = _require_object(
            client.get_json(
                f"/repos/{repository}/compare/{source_sha}...{main_sha}"
            ).value,
            "public source ancestry compare",
        )
        merge_base = _require_object(
            compare.get("merge_base_commit"),
            "public source ancestry merge base",
        )
        if (
            merge_base.get("sha") != source_sha
            or compare.get("behind_by") != 0
            or compare.get("status") not in {"ahead", "identical"}
        ):
            raise WeatherCompositeAuthorityError(
                "authorized public source SHA is not reachable from current main"
            )

    runs = _require_object(
        client.get_json(
            f"/repos/{repository}/actions/workflows/{workflow}/runs"
            f"?branch=main&head_sha={source_sha}&status=completed&per_page=100"
        ).value,
        "public source workflow runs",
    ).get("workflow_runs")
    if type(runs) is not list:
        raise WeatherCompositeAuthorityError(
            "public source workflow run list is malformed"
        )
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
        raise WeatherCompositeAuthorityError(
            "public source exact-main CI is not successful"
        )
    run_id = max(row["id"] for row in successful)
    jobs = _require_object(
        client.get_json(
            f"/repos/{repository}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"
        ).value,
        "public source workflow jobs",
    ).get("jobs")
    if type(jobs) is not list or not any(
        type(job) is dict
        and job.get("status") == "completed"
        and job.get("conclusion") == "success"
        for job in jobs
    ):
        raise WeatherCompositeAuthorityError(
            "public source exact-main CI has no successful job"
        )
    return FixedPublicSourceEvidence(
        repository=repository,
        repository_id=repository_id,
        source_sha=source_sha,
        current_main_sha=main_sha,
        workflow=workflow,
        run_id=run_id,
    )


def _require_rpi5_minimum_ancestor(
    client: _TimedSourceClient,
    source: FixedPublicSourceEvidence,
) -> None:
    response = client.get_json(
        f"/repos/{RPI5_MAIN_SOURCE_REPOSITORY}/compare/"
        f"{RPI5_MIN_REVIEWED_ANCESTOR}...{source.current_main_sha}"
    )
    value = getattr(response, "value", None)
    if type(value) is not dict:
        raise WeatherCompositeAuthorityError("RPi5_main ancestry evidence is malformed")
    merge_base = value.get("merge_base_commit")
    if (
        type(merge_base) is not dict
        or merge_base.get("sha") != RPI5_MIN_REVIEWED_ANCESTOR
        or value.get("behind_by") != 0
        or value.get("status") not in {"ahead", "identical"}
    ):
        raise WeatherCompositeAuthorityError(
            "RPi5_main no longer descends from reviewed Weather minimum ancestor"
        )


class ConcreteCanonicalWeatherCompositeRevalidator:
    """Rebuild one Weather Composite authority from fixed read-only identities.

    The caller supplies only a LIVE-AUTH issue number. Repository, source, target,
    helper, Git, filesystem, Docker, systemd and SQLite identities are fixed by
    reviewed source. This class performs read-only GitHub revalidation only.
    """

    def __init__(
        self,
        *,
        authorization_client: GitHubRestClient,
        queue_client: GitHubRestClient,
        source_client: FixedPublicGitHubReadClient,
        auth_surface: Any,
        registry: Any,
        replay_availability: AuthorizationReplayAvailability,
    ):
        _require_read_clients(
            authorization_client,
            queue_client,
            source_client,
        )
        require_isolated_auth_surface(auth_surface)
        if getattr(registry, "execution_enabled", None) is not False:
            raise WeatherCompositeAuthorityError(
                "Weather canonical registry must remain execution-disabled"
            )
        if not callable(getattr(replay_availability, "is_available", None)):
            raise WeatherCompositeAuthorityError(
                "Weather authorization replay availability is missing"
            )
        self._authorization_client = authorization_client
        self._queue_client = queue_client
        self._source_client = source_client
        self._auth_surface = auth_surface
        self._registry = registry
        self._replay_availability = replay_availability

    def revalidate_composite(
        self, authorization_issue_number: int
    ) -> WeatherCompositeAuthorityEvidence:
        if type(authorization_issue_number) is not int or not (
            1 <= authorization_issue_number <= 2_147_483_647
        ):
            raise WeatherCompositeAuthorityError(
                "Weather authorization issue number is invalid"
            )
        try:
            return self._revalidate_composite(authorization_issue_number)
        except WeatherCompositeAuthorityError:
            raise
        except Exception:
            raise WeatherCompositeAuthorityError(
                "canonical Weather Composite revalidation failed closed"
            ) from None

    def revalidate(
        self, authorization_issue_number: int
    ) -> CanonicalWeatherBootstrapEvidence:
        evidence = self.revalidate_composite(authorization_issue_number)
        return CanonicalWeatherBootstrapEvidence(
            authorization_issue_number=evidence.authorization_issue_number,
            source_repository=SOURCE_REPOSITORY,
            source_sha=evidence.source_sha,
            current_main_sha=evidence.weather_current_main_sha,
            target_alias=TARGET_ALIAS,
            operation_id=OPERATION_ID,
            capability_id=BOOTSTRAP_CAPABILITY_ID,
            runtime_class=RUNTIME_CLASS,
            source_reachable_from_main=evidence.source_reachable_from_main,
            source_ci_success=evidence.source_ci_success,
            handoff_identity_match=True,
            static_registry_contract_match=True,
            registry_execution_enabled=evidence.registry_execution_enabled,
            release_adapter_execution_enabled=False,
            public_only_private_inputs_absent=evidence.public_only_private_inputs_absent,
            start_date=evidence.start_date,
            end_date=evidence.end_date,
            truth_provider=TRUTH_PROVIDER,
            truth_station_id=TRUTH_STATION_ID,
            forecast_models=FORECAST_MODELS,
            run_hours=RUN_HOURS,
            truth_chunk_days=TRUTH_CHUNK_DAYS,
            recovery_decision=evidence.recovery_decision,
            backup_restore_authorized=False,
            public_ingest_cadence=PUBLIC_INGEST_CADENCE,
        )

    def _revalidate_composite(
        self, issue_number: int
    ) -> WeatherCompositeAuthorityEvidence:
        _require_read_clients(
            self._authorization_client,
            self._queue_client,
            self._source_client,
        )
        require_isolated_auth_surface(self._auth_surface)
        window = _GitHubTimeWindow()

        auth_repository_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}"
        )
        _require_repository(
            auth_repository_response,
            repository=AUTHORIZATION_REPOSITORY,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            window=window,
        )
        issue_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        issue = _require_issue_response(
            issue_response,
            issue_number=issue_number,
            repository=AUTHORIZATION_REPOSITORY,
            window=window,
        )
        accepted = accept_issue(
            issue,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=issue_response.server_time,
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        supplement = parse_weather_composite_supplement(issue.get("body"))
        _require_release_authority(accepted, supplement)

        queue_repository_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}"
        )
        _require_repository(
            queue_repository_response,
            repository=QUEUE_REPOSITORY,
            repository_id=QUEUE_REPOSITORY_ID,
            window=window,
        )
        queue_issue_number = accepted.payload.get("queue_issue")
        if type(queue_issue_number) is not int or queue_issue_number < 1:
            raise WeatherCompositeAuthorityError("Weather queue issue is invalid")
        queue_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue_number}"
        )
        queue_issue = _require_issue_response(
            queue_response,
            issue_number=queue_issue_number,
            repository=QUEUE_REPOSITORY,
            window=window,
        )
        normalized = normalize_ready_queue(
            queue_issue,
            repository_full_name=QUEUE_REPOSITORY,
            registry=self._registry,
        )
        _operation, protocol_queue = _require_weather_operation(normalized)
        validate_queue_binding(accepted, protocol_queue)

        weather_client = _TimedSourceClient(self._source_client, window)
        weather_source = _verify_fixed_public_source(
            weather_client,
            repository=SOURCE_REPOSITORY,
            repository_id=SOURCE_REPOSITORY_ID,
            source_sha=accepted.payload["source_sha"],
            workflow=WEATHER_SOURCE_WORKFLOW,
            require_exact_main=False,
        )
        if weather_source.repository_id != SOURCE_REPOSITORY_ID:
            raise WeatherCompositeAuthorityError(
                "Weather source repository numeric identity drifted"
            )

        rpi5_client = _TimedSourceClient(self._source_client, window)
        rpi5_source = _verify_fixed_public_source(
            rpi5_client,
            repository=RPI5_MAIN_SOURCE_REPOSITORY,
            repository_id=RPI5_MAIN_SOURCE_REPOSITORY_ID,
            source_sha=supplement.rpi5_main_sha,
            workflow=RPI5_MAIN_SOURCE_WORKFLOW,
            require_exact_main=True,
        )
        if (
            rpi5_source.repository_id != RPI5_MAIN_SOURCE_REPOSITORY_ID
            or rpi5_source.source_sha != rpi5_source.current_main_sha
        ):
            raise WeatherCompositeAuthorityError(
                "RPi5_main authorized SHA is not exact current main"
            )
        _require_rpi5_minimum_ancestor(rpi5_client, rpi5_source)

        replay_available = self._replay_availability.is_available(accepted)
        if type(replay_available) is not bool or replay_available is not True:
            raise WeatherCompositeAuthorityError(
                "Weather authorization is unavailable for one-shot consumption"
            )

        require_isolated_auth_surface(self._auth_surface)
        final_issue_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        final_issue = _require_issue_response(
            final_issue_response,
            issue_number=issue_number,
            repository=AUTHORIZATION_REPOSITORY,
            window=window,
        )
        verify_authorization_unchanged(
            accepted,
            final_issue,
            server_time=final_issue_response.server_time,
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        final_supplement = parse_weather_composite_supplement(final_issue.get("body"))
        if final_supplement.canonical_sha256 != supplement.canonical_sha256:
            raise WeatherCompositeAuthorityError(
                "Weather composite authorization supplement drifted"
            )

        final_queue_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue_number}"
        )
        final_queue_issue = _require_issue_response(
            final_queue_response,
            issue_number=queue_issue_number,
            repository=QUEUE_REPOSITORY,
            window=window,
        )
        final_normalized = normalize_ready_queue(
            final_queue_issue,
            repository_full_name=QUEUE_REPOSITORY,
            registry=self._registry,
        )
        _final_operation, final_protocol_queue = _require_weather_operation(
            final_normalized
        )
        validate_queue_binding(accepted, final_protocol_queue)
        if final_protocol_queue != protocol_queue:
            raise WeatherCompositeAuthorityError(
                "Weather READY queue drifted during canonical revalidation"
            )

        return WeatherCompositeAuthorityEvidence(
            authorization_issue_number=accepted.issue_number,
            authorization_issue_id=accepted.issue_id,
            authorization_created_at=accepted.created_at.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            github_server_time=window.canonical_last(),
            request_id=accepted.request_id,
            authorization_payload_sha256=accepted.canonical_payload_sha256,
            authorization_raw_body_sha256=accepted.raw_body_sha256,
            composite_authorization_sha256=supplement.canonical_sha256,
            queue_issue_number=queue_issue_number,
            source_sha=weather_source.source_sha,
            weather_current_main_sha=weather_source.current_main_sha,
            weather_ci_run_id=weather_source.run_id,
            rpi5_main_sha=rpi5_source.source_sha,
            rpi5_main_ci_run_id=rpi5_source.run_id,
            host_alias=supplement.host_alias,
            target_alias=TARGET_ALIAS,
            expected_bootstrap_baseline_token=supplement.expected_bootstrap_baseline_token,
            start_date=supplement.start_date,
            end_date=supplement.end_date,
            recovery_decision=supplement.recovery_decision,
            release_mutation_budget=RELEASE_MUTATION_BUDGET,
            additional_mutation_budget=ADDITIONAL_MUTATION_BUDGET,
            full_mutation_budget=FULL_MUTATION_BUDGET,
        )


class ConcreteWeatherCompositeBaselineResolver:
    """Bind a sanitized host baseline to the owner-authorized expected token."""

    def __init__(
        self,
        *,
        provider: SanitizedWeatherBaselineProvider,
        expected_token: str,
    ):
        if not callable(getattr(provider, "resolve", None)):
            raise WeatherCompositeAuthorityError(
                "Weather sanitized baseline provider is missing"
            )
        if (
            type(expected_token) is not str
            or not 1 <= len(expected_token) <= 512
            or "\n" in expected_token
            or "\r" in expected_token
        ):
            raise WeatherCompositeAuthorityError(
                "Weather expected bootstrap baseline token is invalid"
            )
        self._provider = provider
        self._expected_token = expected_token

    def resolve(self, *, source_sha: str, target_alias: str) -> Mapping[str, Any]:
        if type(source_sha) is not str or _SHA40_RE.fullmatch(source_sha) is None:
            raise WeatherCompositeAuthorityError(
                "Weather baseline source SHA is invalid"
            )
        if target_alias != TARGET_ALIAS:
            raise WeatherCompositeAuthorityError(
                "Weather baseline target alias drifted"
            )
        payload = self._provider.resolve(
            source_sha=source_sha,
            target_alias=target_alias,
        )
        if type(payload) is not dict or payload.get("schema") != BASELINE_EVIDENCE_SCHEMA:
            raise WeatherCompositeAuthorityError(
                "Weather sanitized baseline payload is invalid"
            )
        baseline = parse_weather_bootstrap_baseline(payload)
        if baseline.canonical_token != self._expected_token:
            raise WeatherCompositeAuthorityError(
                "Weather sanitized bootstrap baseline drifted from owner authorization"
            )
        return dict(payload)


def compose_weather_composite_source_plan(
    authorization_issue_number: int,
    *,
    canonical_revalidator: ConcreteCanonicalWeatherCompositeRevalidator,
    baseline_provider: SanitizedWeatherBaselineProvider,
) -> WeatherCompositeSourcePlan:
    """Build one source-only Composite plan without enabling or invoking mutation."""

    if type(canonical_revalidator) is not ConcreteCanonicalWeatherCompositeRevalidator:
        raise WeatherCompositeAuthorityError(
            "Weather Composite source plan requires concrete canonical revalidator"
        )
    authority = canonical_revalidator.revalidate_composite(
        authorization_issue_number
    )
    baseline_resolver: SanitizedWeatherBootstrapBaselineResolver = (
        ConcreteWeatherCompositeBaselineResolver(
            provider=baseline_provider,
            expected_token=authority.expected_bootstrap_baseline_token,
        )
    )
    dispatch = prepare_weather_bootstrap_dispatch(
        {
            "schema": REQUEST_SCHEMA,
            "authorization_issue_number": authorization_issue_number,
        },
        canonical_revalidator=canonical_revalidator,
        baseline_resolver=baseline_resolver,
    )
    if (
        dispatch.source_sha != authority.source_sha
        or dispatch.target_alias != authority.target_alias
        or dispatch.baseline_token != authority.expected_bootstrap_baseline_token
        or dispatch.start_date != authority.start_date
        or dispatch.end_date != authority.end_date
        or dispatch.recovery_decision != authority.recovery_decision
    ):
        raise WeatherCompositeAuthorityError(
            "Weather Composite dispatch binding drifted"
        )
    if any(
        (
            dispatch.privileged_dispatch_enabled,
            dispatch.host_wiring_enabled,
            dispatch.production_mutation_started,
            dispatch.automatic_retry_cleanup_rollback,
            dispatch.sqlite_rollback_delete_restore,
            dispatch.weather_next_required,
            dispatch.home_coordinates_required,
        )
    ):
        raise WeatherCompositeAuthorityError(
            "Weather Composite dispatch unexpectedly expanded authority"
        )
    if tuple(stage.stage_id for stage in dispatch.stages) != COMPOSITE_GATE_ORDER[4:]:
        raise WeatherCompositeAuthorityError(
            "Weather Composite ordered stage surface drifted"
        )
    return WeatherCompositeSourcePlan(
        authorization_issue_number=authorization_issue_number,
        source_sha=authority.source_sha,
        rpi5_main_sha=authority.rpi5_main_sha,
        target_alias=authority.target_alias,
        host_alias=authority.host_alias,
        composite_authorization_sha256=authority.composite_authorization_sha256,
        expected_bootstrap_baseline_token=authority.expected_bootstrap_baseline_token,
        start_date=authority.start_date,
        end_date=authority.end_date,
        recovery_decision=authority.recovery_decision,
        release_mutation_budget=authority.release_mutation_budget,
        additional_mutation_budget=authority.additional_mutation_budget,
        full_mutation_budget=authority.full_mutation_budget,
        read_only_stage_budget=READ_ONLY_STAGE_BUDGET,
    )


def source_readiness() -> Mapping[str, object]:
    return {
        "contract": COMPOSITE_CONTRACT,
        "schema": COMPOSITE_SCHEMA,
        "result": COMPOSITE_RESULT,
        "authorization_repository": AUTHORIZATION_REPOSITORY,
        "queue_repository": QUEUE_REPOSITORY,
        "source_repository": SOURCE_REPOSITORY,
        "rpi5_main_repository": RPI5_MAIN_SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "host_alias": HOST_ALIAS,
        "source_read_mode": "credential-free-public-github-api",
        "source_repository_visibility_required": "public",
        "release_mutation_budget": RELEASE_MUTATION_BUDGET,
        "additional_mutation_budget": ADDITIONAL_MUTATION_BUDGET,
        "full_mutation_budget": FULL_MUTATION_BUDGET,
        "read_only_stage_budget": READ_ONLY_STAGE_BUDGET,
        "gate_order": COMPOSITE_GATE_ORDER,
        "application_release_budget_categories": _RELEASE_APPLICATION_CATEGORIES,
        "helper_install_artifact_count": HELPER_INSTALL_ARTIFACT_COUNT,
        "rpi5_minimum_reviewed_ancestor": RPI5_MIN_REVIEWED_ANCESTOR,
        "caller_authority": ("authorization_issue_number",),
        "concrete_canonical_revalidator_implemented": True,
        "composite_supplement_required": True,
        "generic_release_live_auth_sufficient": False,
        "runtime_live_authority": False,
        "trusted_checkout_enabled": False,
        "helper_installation_enabled": False,
        "activation_publication_enabled": False,
        "privileged_dispatch_enabled": False,
        "production_mutation_enabled": False,
        "production_mutation_started": False,
        "automatic_retry_cleanup_rollback": False,
        "weather_next_required": False,
        "home_coordinates_required": False,
        "generic_shell_path_argv_environment_authority": False,
    }
