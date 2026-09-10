from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path
import sys
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.p9_isolated_auth_surface import load_contract
from deploy_executor.p9_runtime import P9ExecutorInstallationTokenProvider
from deploy_executor.protocol import END_MARKER, LIVE_AUTH_SCHEMA, OWNER_USER_ID, START_MARKER
from deploy_executor.queue_normalizer import QUEUE_REPOSITORY, normalize_ready_queue
from deploy_executor.registry import load_registry
from deploy_executor.transport import GitHubRestClient, HTTPResponse, InstallationToken
from deploy_executor.weather_public_runtime_bootstrap import (
    BASELINE_EVIDENCE_SCHEMA,
    FORECAST_MODELS,
    PUBLIC_INGEST_CADENCE,
    RUN_HOURS,
    TRUTH_CHUNK_DAYS,
    TRUTH_PROVIDER,
    TRUTH_STATION_ID,
    parse_weather_bootstrap_baseline,
)
from deploy_executor.weather_public_runtime_composite import (
    ADDITIONAL_MUTATION_BUDGET,
    COMPOSITE_END_MARKER,
    COMPOSITE_GATE_ORDER,
    COMPOSITE_SCHEMA,
    COMPOSITE_START_MARKER,
    FULL_MUTATION_BUDGET,
    HELPER_INSTALL_ARTIFACT_COUNT,
    HOST_ALIAS,
    READ_ONLY_STAGE_BUDGET,
    RELEASE_MUTATION_BUDGET,
    RPI5_MAIN_SOURCE_REPOSITORY,
    RPI5_MAIN_SOURCE_REPOSITORY_ID,
    RPI5_MIN_REVIEWED_ANCESTOR,
    ConcreteCanonicalWeatherCompositeRevalidator,
    FixedPublicGitHubReadClient,
    WeatherCompositeAuthorityError,
    compose_weather_composite_source_plan,
    parse_weather_composite_supplement,
    source_readiness,
)
from deploy_executor.weather_public_runtime_adapter import (
    OPERATION_ID,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    TARGET_ALIAS,
)

REGISTRY_PATH = ROOT / "ops/deploy/executor-operations.json"
QUEUE_PATH = ROOT / "tests/fixtures/deploy_executor/queue_issue_weather_public_runtime_ready.json"
SURFACE_PATH = ROOT / "ops/deploy/executor-p9-isolated-auth-surface.json"
MACHINE_PATH = ROOT / "ops/deploy/weather-public-runtime-composite-live.json"
EXECUTION_PATH = ROOT / "ops/deploy/weather-public-runtime-execution.json"
HELPER_INSTALL_PATH = ROOT / "ops/deploy/weather-public-runtime-helper-install.json"
CHECKOUT_PATH = ROOT / "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json"
HOST_WIRING_PATH = ROOT / "ops/deploy/weather-public-runtime-host-wiring.json"
SOURCE_PATH = ROOT / "ops/lib/deploy_executor/weather_public_runtime_composite.py"
DOC_PATH = ROOT / "docs/WEATHER_PUBLIC_RUNTIME_EXECUTOR_SOURCE.md"

AUTH_ISSUE_NUMBER = 9449
AUTH_ISSUE_ID = 99449
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174449"
WEATHER_SOURCE_SHA = "a" * 40
WEATHER_MAIN_SHA = "b" * 40
RPI5_MAIN_SHA = "c" * 40
SERVER_DATETIME = datetime(2026, 9, 10, 4, 1, 0, tzinfo=timezone.utc)
SERVER_DATE = "Thu, 10 Sep 2026 04:01:00 GMT"
CREATED_AT = "2026-09-10T04:00:00Z"


def normalized_queue() -> dict[str, object]:
    raw = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    return normalize_ready_queue(
        raw,
        repository_full_name=QUEUE_REPOSITORY,
        registry=load_registry(REGISTRY_PATH),
    ).as_protocol_queue()


def baseline_payload() -> dict[str, object]:
    return {
        "schema": BASELINE_EVIDENCE_SCHEMA,
        "target_alias": TARGET_ALIAS,
        "deployment_state": "not_deployed",
        "current_source_sha": None,
        "persistent_volume_state": "absent",
        "schema_state": "absent",
        "schema_version": None,
        "public_ingest_schedule_state": "absent",
        "bootstrap_stage_state": "not_started",
        "privacy_safe": True,
    }


def baseline_token() -> str:
    return parse_weather_bootstrap_baseline(baseline_payload()).canonical_token


def release_payload() -> dict[str, object]:
    queue = normalized_queue()
    return {
        "schema": LIVE_AUTH_SCHEMA,
        "request_id": REQUEST_ID,
        "queue_repository": queue["repository"],
        "queue_issue": queue["issue_number"],
        "source_repository": queue["source_repository"],
        "source_sha": queue["source_sha"],
        "target_alias": queue["target_alias"],
        "operation_id": queue["operation_id"],
        "expected_baseline": copy.deepcopy(queue["expected_baseline"]),
        "mutation_budget": copy.deepcopy(queue["mutation_budget"]),
        "rollback_policy": queue["rollback_policy"],
        "exclusions": copy.deepcopy(queue["exclusions"]),
        "dependencies": copy.deepcopy(queue["dependencies"]),
    }


def composite_payload(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": COMPOSITE_SCHEMA,
        "host_alias": HOST_ALIAS,
        "rpi5_main_sha": RPI5_MAIN_SHA,
        "expected_bootstrap_baseline_token": baseline_token(),
        "start_date": "2026-04-02",
        "end_date": "2026-09-07",
        "recovery_decision": "owner-accepted-no-prewrite-backup",
        "helper_install_artifact_count": HELPER_INSTALL_ARTIFACT_COUNT,
        "additional_mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in ADDITIONAL_MUTATION_BUDGET
        ],
    }
    value.update(updates)
    return value


def auth_issue(
    *,
    release: dict[str, object] | None = None,
    supplement: dict[str, object] | None = None,
    app_authored: bool = False,
    created_at: str = CREATED_AT,
) -> dict[str, object]:
    release_value = release or release_payload()
    supplement_value = supplement or composite_payload()
    body = (
        "Weather Composite source fixture.\n\n"
        f"{START_MARKER}\n```json\n"
        f"{json.dumps(release_value, sort_keys=True, separators=(',', ':'))}\n"
        f"```\n{END_MARKER}\n\n"
        f"{COMPOSITE_START_MARKER}\n```json\n"
        f"{json.dumps(supplement_value, sort_keys=True, separators=(',', ':'))}\n"
        f"```\n{COMPOSITE_END_MARKER}"
    )
    return {
        "id": AUTH_ISSUE_ID,
        "number": AUTH_ISSUE_NUMBER,
        "repository_url": "https://api.github.com/repos/rozkalnsandris/deploy-authorizations",
        "state": "open",
        "created_at": created_at,
        "title": f"[LIVE-AUTH][PENDING] {TARGET_ALIAS}",
        "body": body,
        "user": {"id": OWNER_USER_ID, "type": "User", "login": "rozkalnsandris"},
        "performed_via_github_app": {"id": 1144995} if app_authored else None,
    }


class FixtureSender:
    def __init__(
        self,
        *,
        authorization_issue: dict[str, object] | None = None,
        final_authorization_issue: dict[str, object] | None = None,
        queue_state: str = "open",
        final_queue_state: str | None = None,
        weather_ci_success: bool = True,
        rpi5_ci_success: bool = True,
        weather_ancestry_ok: bool = True,
        rpi5_exact_main: bool = True,
        rpi5_ancestor_ok: bool = True,
    ):
        self.authorization_issue = authorization_issue or auth_issue()
        self.final_authorization_issue = final_authorization_issue
        self.queue_state = queue_state
        self.final_queue_state = final_queue_state
        self.weather_ci_success = weather_ci_success
        self.rpi5_ci_success = rpi5_ci_success
        self.weather_ancestry_ok = weather_ancestry_ok
        self.rpi5_exact_main = rpi5_exact_main
        self.rpi5_ancestor_ok = rpi5_ancestor_ok
        self.auth_reads = 0
        self.queue_reads = 0
        self.calls: list[str] = []
        self.public_authorization_headers: list[bool] = []

    @staticmethod
    def _json(value: object) -> bytes:
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    def send(self, *, method: str, url: str, headers: object) -> HTTPResponse:
        if method != "GET":
            raise AssertionError("Weather Composite fixture permits GET only")
        parsed = urlsplit(url)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        self.calls.append(path)

        if parsed.path.startswith(f"/repos/{SOURCE_REPOSITORY}") or parsed.path.startswith(
            f"/repos/{RPI5_MAIN_SOURCE_REPOSITORY}"
        ):
            self.public_authorization_headers.append(
                any(str(key).lower() == "authorization" for key in dict(headers))
            )

        if path == "/repos/rozkalnsandris/deploy-authorizations":
            value: object = {
                "id": 1350486101,
                "full_name": "rozkalnsandris/deploy-authorizations",
            }
        elif path == f"/repos/rozkalnsandris/deploy-authorizations/issues/{AUTH_ISSUE_NUMBER}":
            self.auth_reads += 1
            value = (
                self.final_authorization_issue
                if self.final_authorization_issue is not None and self.auth_reads > 1
                else self.authorization_issue
            )
        elif path == f"/repos/{QUEUE_REPOSITORY}":
            value = {"id": 1328835922, "full_name": QUEUE_REPOSITORY}
        elif path == f"/repos/{QUEUE_REPOSITORY}/issues/{normalized_queue()['issue_number']}":
            self.queue_reads += 1
            value = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
            value["state"] = (
                self.final_queue_state
                if self.final_queue_state is not None and self.queue_reads > 1
                else self.queue_state
            )
            value["repository_url"] = f"https://api.github.com/repos/{QUEUE_REPOSITORY}"
        elif path == f"/repos/{SOURCE_REPOSITORY}":
            value = {
                "id": SOURCE_REPOSITORY_ID,
                "full_name": SOURCE_REPOSITORY,
                "default_branch": "main",
                "private": False,
            }
        elif path == f"/repos/{SOURCE_REPOSITORY}/branches/main":
            value = {"commit": {"sha": WEATHER_MAIN_SHA}}
        elif path == f"/repos/{SOURCE_REPOSITORY}/compare/{WEATHER_SOURCE_SHA}...{WEATHER_MAIN_SHA}":
            value = {
                "merge_base_commit": {"sha": WEATHER_SOURCE_SHA if self.weather_ancestry_ok else "d" * 40},
                "behind_by": 0,
                "status": "ahead",
            }
        elif path.startswith(f"/repos/{SOURCE_REPOSITORY}/actions/workflows/tests.yml/runs?"):
            value = {
                "workflow_runs": [
                    {
                        "id": 9101,
                        "head_sha": WEATHER_SOURCE_SHA,
                        "head_branch": "main",
                        "status": "completed",
                        "conclusion": "success" if self.weather_ci_success else "failure",
                    }
                ]
            }
        elif path == f"/repos/{SOURCE_REPOSITORY}/actions/runs/9101/jobs?filter=latest&per_page=100":
            value = {"jobs": [{"status": "completed", "conclusion": "success"}]}
        elif path == f"/repos/{RPI5_MAIN_SOURCE_REPOSITORY}":
            value = {
                "id": RPI5_MAIN_SOURCE_REPOSITORY_ID,
                "full_name": RPI5_MAIN_SOURCE_REPOSITORY,
                "default_branch": "main",
                "private": False,
            }
        elif path == f"/repos/{RPI5_MAIN_SOURCE_REPOSITORY}/branches/main":
            value = {"commit": {"sha": RPI5_MAIN_SHA if self.rpi5_exact_main else "d" * 40}}
        elif path.startswith(
            f"/repos/{RPI5_MAIN_SOURCE_REPOSITORY}/actions/workflows/validate.yml/runs?"
        ):
            value = {
                "workflow_runs": [
                    {
                        "id": 9201,
                        "head_sha": RPI5_MAIN_SHA,
                        "head_branch": "main",
                        "status": "completed",
                        "conclusion": "success" if self.rpi5_ci_success else "failure",
                    }
                ]
            }
        elif path == f"/repos/{RPI5_MAIN_SOURCE_REPOSITORY}/actions/runs/9201/jobs?filter=latest&per_page=100":
            value = {"jobs": [{"status": "completed", "conclusion": "success"}]}
        elif path == (
            f"/repos/{RPI5_MAIN_SOURCE_REPOSITORY}/compare/"
            f"{RPI5_MIN_REVIEWED_ANCESTOR}...{RPI5_MAIN_SHA}"
        ):
            value = {
                "merge_base_commit": {
                    "sha": RPI5_MIN_REVIEWED_ANCESTOR if self.rpi5_ancestor_ok else "e" * 40
                },
                "behind_by": 0,
                "status": "ahead",
            }
        else:
            raise AssertionError(path)

        return HTTPResponse(
            status=200,
            headers={"date": SERVER_DATE},
            body=self._json(value),
        )


def executor_provider(repository: str, repository_id: int):
    provider = object.__new__(P9ExecutorInstallationTokenProvider)
    provider.repository = repository
    provider.repository_id = repository_id
    provider._cached_token = InstallationToken(
        "fixture-executor-token",
        expires_at=SERVER_DATETIME + timedelta(hours=1),
    )
    return provider


def client(provider: object, sender: FixtureSender) -> GitHubRestClient:
    return GitHubRestClient(
        token_provider=provider,
        sender=sender,
        clock=lambda: SERVER_DATETIME,
    )


class ReplayAvailability:
    def __init__(self, available: bool = True, *, consumed: bool = False):
        self.available = available
        self.consumed = consumed
        self.calls: list[str] = []

    def is_available(self, accepted: object) -> bool:
        self.calls.append(accepted.request_id)
        return self.available

    def is_consumed(self, accepted: object) -> bool:
        self.calls.append(accepted.request_id)
        return self.consumed


class BaselineProvider:
    def __init__(self, payload: dict[str, object] | None = None):
        self.payload = payload or baseline_payload()
        self.calls = 0

    def resolve(self, *, source_sha: str, target_alias: str) -> dict[str, object]:
        self.calls += 1
        if source_sha != WEATHER_SOURCE_SHA or target_alias != TARGET_ALIAS:
            raise AssertionError("unexpected baseline identity")
        return copy.deepcopy(self.payload)


def revalidator(
    sender: FixtureSender | None = None,
    replay: ReplayAvailability | None = None,
) -> tuple[ConcreteCanonicalWeatherCompositeRevalidator, FixtureSender, ReplayAvailability]:
    sender = sender or FixtureSender()
    replay = replay or ReplayAvailability()
    result = ConcreteCanonicalWeatherCompositeRevalidator(
        authorization_client=client(
            executor_provider("rozkalnsandris/deploy-authorizations", 1350486101),
            sender,
        ),
        queue_client=client(
            executor_provider(QUEUE_REPOSITORY, 1328835922),
            sender,
        ),
        source_client=FixedPublicGitHubReadClient(sender=sender),
        auth_surface=load_contract(SURFACE_PATH),
        registry=load_registry(REGISTRY_PATH),
        replay_availability=replay,
    )
    return result, sender, replay


class WeatherCompositeCanonicalTests(unittest.TestCase):
    def test_revalidator_binds_auth_queue_sources_ci_and_distinct_budgets(self):
        value, sender, replay = revalidator()
        evidence = value.revalidate_composite(AUTH_ISSUE_NUMBER)
        self.assertEqual(evidence.source_sha, WEATHER_SOURCE_SHA)
        self.assertEqual(evidence.weather_current_main_sha, WEATHER_MAIN_SHA)
        self.assertEqual(evidence.rpi5_main_sha, RPI5_MAIN_SHA)
        self.assertEqual(evidence.host_alias, HOST_ALIAS)
        self.assertEqual(evidence.target_alias, TARGET_ALIAS)
        self.assertEqual(evidence.release_mutation_budget, RELEASE_MUTATION_BUDGET)
        self.assertEqual(evidence.additional_mutation_budget, ADDITIONAL_MUTATION_BUDGET)
        self.assertEqual(evidence.full_mutation_budget, FULL_MUTATION_BUDGET)
        self.assertTrue(replay.calls)
        self.assertTrue(sender.public_authorization_headers)
        self.assertFalse(any(sender.public_authorization_headers))
        self.assertTrue(all(call.startswith("/repos/") for call in sender.calls))

    def test_post_consume_revalidator_requires_durable_consumed_identity(self):
        replay = ReplayAvailability(False, consumed=True)
        target, _sender, _replay = revalidator(replay=replay)
        evidence = target.revalidate_consumed_composite(AUTH_ISSUE_NUMBER)
        self.assertTrue(evidence.authorization_replay_consumed)
        self.assertFalse(evidence.authorization_replay_available)
        replay.consumed = False
        with self.assertRaisesRegex(WeatherCompositeAuthorityError, "not durably consumed|replay state drifted"):
            target.revalidate_consumed_composite(AUTH_ISSUE_NUMBER)

    def test_composer_keeps_runtime_inactive_and_public_scope_fixed(self):
        value, _, _ = revalidator()
        plan = compose_weather_composite_source_plan(
            AUTH_ISSUE_NUMBER,
            canonical_revalidator=value,
            baseline_provider=BaselineProvider(),
        )
        self.assertEqual(plan.gate_order, COMPOSITE_GATE_ORDER)
        self.assertEqual(plan.read_only_stage_budget, READ_ONLY_STAGE_BUDGET)
        self.assertEqual(plan.start_date, "2026-04-02")
        self.assertEqual(plan.end_date, "2026-09-07")
        self.assertFalse(plan.runtime_live_authority)
        self.assertFalse(plan.trusted_checkout_enabled)
        self.assertFalse(plan.helper_installation_enabled)
        self.assertFalse(plan.activation_publication_enabled)
        self.assertFalse(plan.privileged_dispatch_enabled)
        self.assertFalse(plan.production_mutation_enabled)
        self.assertFalse(plan.production_mutation_started)
        self.assertFalse(plan.automatic_retry_cleanup_rollback)

    def test_generic_release_live_auth_cannot_launder_sqlite_or_checkout_authority(self):
        payload = release_payload()
        payload["mutation_budget"] = list(payload["mutation_budget"]) + [
            {"category": "sqlite.schema-init", "max_operations": 1}
        ]
        sender = FixtureSender(authorization_issue=auth_issue(release=payload))
        value, _, _ = revalidator(sender)
        with self.assertRaises(Exception):
            value.revalidate_composite(AUTH_ISSUE_NUMBER)

        wrong = composite_payload(
            additional_mutation_budget=[
                {"category": "docker.compose-build", "max_operations": 1}
            ]
        )
        with self.assertRaises(WeatherCompositeAuthorityError):
            parse_weather_composite_supplement(auth_issue(supplement=wrong)["body"])

    def test_stale_app_authored_replay_and_body_or_queue_drift_fail_closed(self):
        stale = auth_issue(created_at="2026-09-10T03:40:00Z")
        app = auth_issue(app_authored=True)
        drifted = auth_issue()
        drifted["body"] += "\n"
        cases = (
            (FixtureSender(authorization_issue=stale), ReplayAvailability()),
            (FixtureSender(authorization_issue=app), ReplayAvailability()),
            (FixtureSender(), ReplayAvailability(False)),
            (
                FixtureSender(
                    authorization_issue=auth_issue(),
                    final_authorization_issue=drifted,
                ),
                ReplayAvailability(),
            ),
            (
                FixtureSender(final_queue_state="closed"),
                ReplayAvailability(),
            ),
        )
        for sender, replay in cases:
            with self.subTest(sender=sender.__dict__, replay=replay.available):
                value, _, _ = revalidator(sender, replay)
                with self.assertRaises(Exception):
                    value.revalidate_composite(AUTH_ISSUE_NUMBER)

    def test_source_ci_ancestry_and_exact_rpi5_main_drift_fail_closed(self):
        cases = (
            FixtureSender(weather_ci_success=False),
            FixtureSender(weather_ancestry_ok=False),
            FixtureSender(rpi5_ci_success=False),
            FixtureSender(rpi5_exact_main=False),
            FixtureSender(rpi5_ancestor_ok=False),
        )
        for sender in cases:
            with self.subTest(sender=sender.__dict__):
                value, _, _ = revalidator(sender)
                with self.assertRaises(Exception):
                    value.revalidate_composite(AUTH_ISSUE_NUMBER)

    def test_sanitized_baseline_token_mismatch_fails_closed(self):
        value, _, _ = revalidator()
        payload = baseline_payload()
        payload["persistent_volume_state"] = "present"
        with self.assertRaises(WeatherCompositeAuthorityError):
            compose_weather_composite_source_plan(
                AUTH_ISSUE_NUMBER,
                canonical_revalidator=value,
                baseline_provider=BaselineProvider(payload),
            )


class WeatherCompositeMachineContractTests(unittest.TestCase):
    def test_machine_contract_freezes_exact_authority_partition_and_bootstrap_scope(self):
        machine = json.loads(MACHINE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(machine["contract"], "rozkalns-weather.public-runtime-composite-live.v1")
        self.assertEqual(machine["status"], "SOURCE_READY_OPERATOR_HOST_INACTIVE")
        self.assertEqual(machine["host_alias"], "rpi5")
        self.assertEqual(machine["target_alias"], TARGET_ALIAS)
        self.assertFalse(machine["release_authorization"]["generic_release_live_auth_sufficient"])
        self.assertTrue(machine["release_authorization"]["same_human_issue_required"])
        observed_release = tuple(
            (row["category"], row["max_operations"])
            for row in machine["release_mutation_budget"]
        )
        observed_additional = tuple(
            (row["category"], row["max_operations"])
            for row in machine["supplemental_authorization"]["additional_mutation_budget"]
        )
        observed_read_only = tuple(
            (row["stage_id"], row["max_operations"])
            for row in machine["read_only_stage_budget"]
        )
        self.assertEqual(observed_release, RELEASE_MUTATION_BUDGET)
        self.assertEqual(observed_additional, ADDITIONAL_MUTATION_BUDGET)
        self.assertEqual(observed_read_only, READ_ONLY_STAGE_BUDGET)
        self.assertEqual(tuple(machine["gate_order"]), COMPOSITE_GATE_ORDER)
        scope = machine["bootstrap_scope"]
        self.assertEqual(scope["truth_provider"], TRUTH_PROVIDER)
        self.assertEqual(scope["truth_station_id"], TRUTH_STATION_ID)
        self.assertEqual(tuple(scope["forecast_models"]), FORECAST_MODELS)
        self.assertEqual(tuple(scope["run_hours"]), RUN_HOURS)
        self.assertEqual(scope["truth_chunk_days"], TRUTH_CHUNK_DAYS)
        self.assertEqual(scope["max_backfill_days"], 180)
        self.assertEqual(scope["public_ingest_cadence"], PUBLIC_INGEST_CADENCE)
        self.assertFalse(scope["weather_next_required"])
        self.assertFalse(scope["home_coordinates_required"])

    def test_existing_checkout_helper_activation_and_host_wiring_are_exactly_bound(self):
        machine = json.loads(MACHINE_PATH.read_text(encoding="utf-8"))
        checkout = json.loads(CHECKOUT_PATH.read_text(encoding="utf-8"))
        install = json.loads(HELPER_INSTALL_PATH.read_text(encoding="utf-8"))
        execution = json.loads(EXECUTION_PATH.read_text(encoding="utf-8"))
        wiring = json.loads(HOST_WIRING_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            machine["trusted_checkout"]["contract"],
            "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json",
        )
        self.assertEqual(
            [row["argv"] for row in checkout["allowed_git_mutations"]],
            [
                ["git", "fetch", "origin", "main"],
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted",
                    "EXPLICIT_COMPOSITE_STRICT_LIVE_EXACT_RPI5_MAIN_SHA",
                ],
            ],
        )
        self.assertFalse(checkout["legacy_checkout"]["mutation_allowed"])
        self.assertFalse(checkout["legacy_checkout"]["cleanup_allowed"])
        self.assertEqual(
            machine["trusted_checkout"]["legacy_target"],
            "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-trusted",
        )
        self.assertFalse(machine["trusted_checkout"]["legacy_target_mutation_allowed"])
        self.assertEqual(
            machine["privileged_install_activation_contract"],
            "ops/deploy/weather-public-runtime-privileged-install-activation.json",
        )
        self.assertEqual(install["artifact_count"], 13)
        self.assertEqual(install["required_owner_uid"], 0)
        self.assertEqual(install["required_owner_gid"], 0)
        self.assertEqual(install["directory_mode"], "0755")
        self.assertEqual(install["entrypoint_mode"], "0755")
        self.assertEqual(install["module_mode"], "0644")
        self.assertNotIn(
            "ops/lib/deploy_executor/weather_public_runtime_composite.py",
            [row["source"] for row in install["artifacts"]],
        )
        self.assertEqual(
            execution["composite_live_authority_contract"],
            "ops/deploy/weather-public-runtime-composite-live.json",
        )
        self.assertFalse(execution["generic_release_live_auth_sufficient"])
        self.assertEqual(
            execution["privileged_install_activation_contract"],
            "ops/deploy/weather-public-runtime-privileged-install-activation.json",
        )
        self.assertEqual(execution["activation_file_required_mode"], "0600")
        self.assertTrue(execution["activation_file_required_root_owner"])
        self.assertTrue(execution["whole_preactivation_sha256_required"])
        self.assertEqual(len(wiring["helpers"]), 9)
        self.assertEqual(
            tuple(row["stage_id"] for row in wiring["helpers"]),
            COMPOSITE_GATE_ORDER[4:],
        )
        self.assertTrue(execution["helper_process_launch_wired"])
        for field in (
            "privileged_dispatch_enabled",
            "host_wiring_enabled",
            "helper_installation_enabled",
            "helper_invocation_enabled",
            "production_mutation_enabled",
            "production_mutation_started",
        ):
            self.assertFalse(execution[field])

    def test_source_readiness_and_docs_preserve_inactive_non_generic_boundary(self):
        readiness = source_readiness()
        for field in (
            "runtime_live_authority",
            "trusted_checkout_enabled",
            "helper_installation_enabled",
            "activation_publication_enabled",
            "privileged_dispatch_enabled",
            "production_mutation_enabled",
            "production_mutation_started",
            "automatic_retry_cleanup_rollback",
            "weather_next_required",
            "home_coordinates_required",
            "generic_shell_path_argv_environment_authority",
        ):
            self.assertFalse(readiness[field])
        doc = DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("Composite STRICT LIVE authority bridge — Issue #449", doc)
        self.assertIn("generic `rozkalns.live-auth.v1`", doc)
        self.assertIn("individually insufficient", doc)

    def test_revalidator_exposes_identity_only_interface_and_no_execution_primitives(self):
        parameters = tuple(
            inspect.signature(
                ConcreteCanonicalWeatherCompositeRevalidator.revalidate_composite
            ).parameters
        )
        self.assertEqual(parameters, ("self", "authorization_issue_number"))
        source = SOURCE_PATH.read_text(encoding="utf-8")
        for token in (
            "import subprocess",
            "from subprocess",
            "Popen(",
            "os.system(",
            "shell=True",
            "sudo ",
            "systemctl ",
            "sqlite3.connect",
            "docker compose",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
