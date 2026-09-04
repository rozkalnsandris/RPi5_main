from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path
import sys
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_origin_adapter import (  # noqa: E402
    OPERATION_ID,
    PULL_HELPER_ARGUMENTS,
    PULL_HELPER_SOURCE_BLOB,
    SOURCE_REPOSITORY,
)
from deploy_executor.hermes_deals_origin_broker_composition import (  # noqa: E402
    HermesDealsOriginBrokerComposition,
    source_readiness as composition_readiness,
)
from deploy_executor.hermes_deals_origin_canonical_revalidator import (  # noqa: E402
    ConcreteCanonicalHermesOriginRevalidator,
    ConcreteCanonicalHermesOriginRevalidatorError,
    source_readiness as canonical_readiness,
)
from deploy_executor.hermes_deals_origin_dispatch_request import (  # noqa: E402
    SCHEMA as REQUEST_SCHEMA,
)
from deploy_executor.hermes_deals_origin_helper_launch import (  # noqa: E402
    FIXED_HELPER_ENV,
    HELPER_TIMEOUT_SECONDS,
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    HelperProcessResult,
    HermesDealsOriginHelperLaunchError,
)
from deploy_executor.hermes_deals_origin_host_evidence import (  # noqa: E402
    BROKER_INSTALL_PATH,
    BROKER_MODE,
    HOST_OBSERVATION_SCHEMA,
    PROBE_PATH,
    PULL_HELPER_MODE,
    REGISTRATION_MODE,
    REGISTRATION_NAME,
    REGISTRATION_PATH,
    ROOT_GROUP,
    ROOT_OWNER,
    ConcreteSanitizedHermesOriginHostEvidenceResolver,
    SanitizedHermesOriginHostEvidenceError,
    evidence_field_rationale,
    source_readiness as host_readiness,
)
from deploy_executor.hermes_deals_origin_privileged_broker import (  # noqa: E402
    BROKER_SERVICE_UNIT,
    BROKER_SOCKET_PATH,
    BROKER_SOCKET_UNIT,
)
from deploy_executor.hermes_deals_origin_privileged_dispatcher import (  # noqa: E402
    INSTALLED_HELPER_PATH,
)
from deploy_executor.hermes_deals_origin_source_auth import (  # noqa: E402
    SOURCE_CREDENTIAL_GROUP,
    SOURCE_CREDENTIAL_MODE,
    SOURCE_CREDENTIAL_OWNER,
    SOURCE_CREDENTIAL_PATH,
)
from deploy_executor.p9_isolated_auth_surface import load_contract  # noqa: E402
from deploy_executor.p9_runtime import P9ExecutorInstallationTokenProvider  # noqa: E402
from deploy_executor.p9_source_auth import (  # noqa: E402
    HERMES_DEALS_SOURCE_REPOSITORY,
    HERMES_DEALS_SOURCE_REPOSITORY_ID,
    P9SourceInstallationTokenProvider,
)
from deploy_executor.queue_normalizer import normalize_ready_queue  # noqa: E402
from deploy_executor.registry import load_registry  # noqa: E402
from deploy_executor.transport import (  # noqa: E402
    GitHubRestClient,
    HTTPResponse,
    InstallationToken,
)

SOURCE_SHA = "fbe3cfa143788607446d0095ae1f887354d10eb3"
AUTHORIZATION_CREATED_AT = "2026-09-04T07:26:48Z"
GITHUB_SERVER_TIME = "2026-09-04T07:27:00Z"
SERVER_DATETIME = datetime(2026, 9, 4, 7, 27, tzinfo=timezone.utc)
SERVER_DATE = "Fri, 04 Sep 2026 07:27:00 GMT"
AUTHORIZATION_ISSUE = 17
QUEUE_ISSUE = 384
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"
SURFACE_PATH = ROOT / "ops/deploy/executor-p9-isolated-auth-surface.json"
REGISTRY_PATH = ROOT / "tests/fixtures/deploy_executor/operations_hermes_deals_origin_canary.json"
QUEUE_PATH = ROOT / "tests/fixtures/deploy_executor/queue_issue_hermes_deals_origin_ready_markup.json"


def _request_bytes(**extra: object) -> bytes:
    value: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "authorization_issue_number": AUTHORIZATION_ISSUE,
    }
    value.update(extra)
    return (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")


def _authorization_issue(*, request_id: str = REQUEST_ID) -> dict[str, object]:
    registry = load_registry(REGISTRY_PATH)
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    normalized = normalize_ready_queue(
        queue,
        repository_full_name="rozkalnsandris/ops-workflows",
        registry=registry,
    ).as_protocol_queue()
    payload = {
        "schema": "rozkalns.live-auth.v1",
        "request_id": request_id,
        "queue_repository": normalized["repository"],
        "queue_issue": normalized["issue_number"],
        "source_repository": normalized["source_repository"],
        "source_sha": normalized["source_sha"],
        "target_alias": normalized["target_alias"],
        "operation_id": normalized["operation_id"],
        "expected_baseline": normalized["expected_baseline"],
        "mutation_budget": normalized["mutation_budget"],
        "rollback_policy": normalized["rollback_policy"],
        "exclusions": normalized["exclusions"],
        "dependencies": normalized["dependencies"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "id": 5017,
        "number": AUTHORIZATION_ISSUE,
        "repository_url": "https://api.github.com/repos/rozkalnsandris/deploy-authorizations",
        "state": "open",
        "title": "[LIVE-AUTH][PENDING] hermes-deals-origin-path-audit",
        "created_at": AUTHORIZATION_CREATED_AT,
        "body": (
            "Source-only integration fixture.\n\n"
            "<!-- rozkalns-live-auth:v1 -->\n"
            f"```json\n{canonical}\n```\n"
            "<!-- /rozkalns-live-auth:v1 -->"
        ),
        "user": {"id": 277435981, "type": "User", "login": "rozkalnsandris"},
        "performed_via_github_app": None,
    }


class GitHubFixtureSender:
    def __init__(
        self,
        *,
        source_repository_id: int = HERMES_DEALS_SOURCE_REPOSITORY_ID,
        source_ci_success: bool = True,
        replay_authorization_drift: bool = False,
        regress_queue_time: bool = False,
    ):
        self.source_repository_id = source_repository_id
        self.source_ci_success = source_ci_success
        self.replay_authorization_drift = replay_authorization_drift
        self.regress_queue_time = regress_queue_time
        self.authorization_issue_reads = 0
        self.calls: list[str] = []

    def send(self, *, method: str, url: str, headers: object) -> HTTPResponse:
        if method != "GET":
            raise AssertionError("source integration may issue only GET requests")
        path = urlsplit(url).path
        if urlsplit(url).query:
            path = f"{path}?{urlsplit(url).query}"
        self.calls.append(path)
        date = SERVER_DATE
        if self.regress_queue_time and path == "/repos/rozkalnsandris/ops-workflows":
            date = "Fri, 04 Sep 2026 07:26:59 GMT"

        if path == "/repos/rozkalnsandris/deploy-authorizations":
            value: object = {
                "id": 1350486101,
                "full_name": "rozkalnsandris/deploy-authorizations",
            }
        elif path == f"/repos/rozkalnsandris/deploy-authorizations/issues/{AUTHORIZATION_ISSUE}":
            self.authorization_issue_reads += 1
            request_id = REQUEST_ID
            if self.replay_authorization_drift and self.authorization_issue_reads > 2:
                request_id = "223e4567-e89b-42d3-a456-426614174000"
            value = _authorization_issue(request_id=request_id)
        elif path == "/repos/rozkalnsandris/ops-workflows":
            value = {
                "id": 1328835922,
                "full_name": "rozkalnsandris/ops-workflows",
            }
        elif path == f"/repos/rozkalnsandris/ops-workflows/issues/{QUEUE_ISSUE}":
            value = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
            value["repository_url"] = (
                "https://api.github.com/repos/rozkalnsandris/ops-workflows"
            )
        elif path == f"/repos/{SOURCE_REPOSITORY}":
            value = {
                "id": self.source_repository_id,
                "full_name": SOURCE_REPOSITORY,
                "default_branch": "main",
            }
        elif path == f"/repos/{SOURCE_REPOSITORY}/branches/main":
            value = {"commit": {"sha": SOURCE_SHA}}
        elif path.startswith(
            f"/repos/{SOURCE_REPOSITORY}/actions/workflows/ci.yml/runs?"
        ):
            value = {
                "workflow_runs": [
                    {
                        "id": 9001,
                        "head_sha": SOURCE_SHA,
                        "head_branch": "main",
                        "status": "completed",
                        "conclusion": "success" if self.source_ci_success else "failure",
                    }
                ]
            }
        elif path == f"/repos/{SOURCE_REPOSITORY}/actions/runs/9001/jobs?filter=latest&per_page=100":
            value = {"jobs": [{"status": "completed", "conclusion": "success"}]}
        else:
            raise AssertionError(path)
        return HTTPResponse(
            status=200,
            headers={"date": date},
            body=json.dumps(value, separators=(",", ":")).encode("utf-8"),
        )


def _executor_provider(repository: str, repository_id: int):
    provider = object.__new__(P9ExecutorInstallationTokenProvider)
    provider.repository = repository
    provider.repository_id = repository_id
    provider._cached_token = InstallationToken(
        "fixture-executor-token-value",
        expires_at=SERVER_DATETIME + timedelta(hours=1),
    )
    return provider


def _source_provider():
    provider = object.__new__(P9SourceInstallationTokenProvider)
    provider.repository = HERMES_DEALS_SOURCE_REPOSITORY
    provider.repository_id = HERMES_DEALS_SOURCE_REPOSITORY_ID
    provider._cached_token = InstallationToken(
        "fixture-source-token-value",
        expires_at=SERVER_DATETIME + timedelta(hours=1),
    )
    return provider


def _client(provider: object, sender: GitHubFixtureSender) -> GitHubRestClient:
    return GitHubRestClient(
        token_provider=provider,
        sender=sender,
        clock=lambda: SERVER_DATETIME,
    )


class ReplayAvailability:
    def __init__(self, available: bool = True):
        self.available = available
        self.calls: list[str] = []

    def is_available(self, accepted: object) -> bool:
        self.calls.append(accepted.request_id)
        return self.available


def _revalidator(
    sender: GitHubFixtureSender | None = None,
    replay: ReplayAvailability | None = None,
) -> tuple[ConcreteCanonicalHermesOriginRevalidator, GitHubFixtureSender, ReplayAvailability]:
    sender = sender or GitHubFixtureSender()
    replay = replay or ReplayAvailability()
    result = ConcreteCanonicalHermesOriginRevalidator(
        authorization_client=_client(
            _executor_provider(
                "rozkalnsandris/deploy-authorizations", 1350486101
            ),
            sender,
        ),
        queue_client=_client(
            _executor_provider("rozkalnsandris/ops-workflows", 1328835922),
            sender,
        ),
        source_client=_client(_source_provider(), sender),
        auth_surface=load_contract(SURFACE_PATH),
        registry=load_registry(REGISTRY_PATH),
        replay_availability=replay,
    )
    return result, sender, replay


def _host_observation(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": HOST_OBSERVATION_SCHEMA,
        "evidence_id": "hermes-origin-host-1",
        "observed_at": GITHUB_SERVER_TIME,
        "operation_id": OPERATION_ID,
        "registered_source_sha": SOURCE_SHA,
        "registration_path": REGISTRATION_PATH,
        "registration_name": REGISTRATION_NAME,
        "registration_owner": ROOT_OWNER,
        "registration_group": ROOT_GROUP,
        "registration_mode": REGISTRATION_MODE,
        "broker_install_path": BROKER_INSTALL_PATH,
        "broker_owner": ROOT_OWNER,
        "broker_group": ROOT_GROUP,
        "broker_mode": BROKER_MODE,
        "socket_path": BROKER_SOCKET_PATH,
        "socket_unit": BROKER_SOCKET_UNIT,
        "service_unit": BROKER_SERVICE_UNIT,
        "source_credential_path": SOURCE_CREDENTIAL_PATH,
        "source_credential_owner": SOURCE_CREDENTIAL_OWNER,
        "source_credential_group": SOURCE_CREDENTIAL_GROUP,
        "source_credential_mode": SOURCE_CREDENTIAL_MODE,
        "pull_helper_path": INSTALLED_HELPER_PATH,
        "pull_helper_owner": ROOT_OWNER,
        "pull_helper_group": ROOT_GROUP,
        "pull_helper_mode": PULL_HELPER_MODE,
        "pull_helper_source_blob": PULL_HELPER_SOURCE_BLOB,
        "pull_helper_argument_names": list(PULL_HELPER_ARGUMENTS),
        "probe_path": PROBE_PATH,
        "probe_source_blob": "2362e8eb578a7279c38fe4ed2a7d1edd05df891a",
        "dispatcher_source_blob": "f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc",
        "workflow_source_blob": "99a18c5f669e7880a8a8288c3f964285df87ae22",
        "evidence_read_only": True,
        "credential_content_read": False,
        "protected_values_included": False,
        "filesystem_mutation": False,
        "systemd_interaction": False,
        "authority_expanded": False,
        "production_mutation_started": False,
    }
    result.update(updates)
    return result


class ObservationProvider:
    def __init__(self, value: dict[str, object] | bytes | None = None):
        self.value = value if value is not None else _host_observation()
        self.calls = 0

    def read(self) -> bytes:
        self.calls += 1
        if type(self.value) is bytes:
            return self.value
        return json.dumps(self.value, separators=(",", ":")).encode("utf-8")


class FakeRunner:
    def __init__(self):
        self.calls: list[tuple[object, ...]] = []

    def __call__(
        self,
        argv: tuple[str, str, str],
        *,
        env: object,
        timeout_seconds: int,
        stdout_limit: int,
        stderr_limit: int,
    ) -> HelperProcessResult:
        self.calls.append((argv, env, timeout_seconds, stdout_limit, stderr_limit))
        return HelperProcessResult(
            returncode=0,
            stdout=(
                f"CAPABILITY=origin-path-audit SOURCE_SHA={SOURCE_SHA} "
                "AS_OF=2026-09-04 PROBE_EXIT_CODE=0\n"
                "PRODUCTION_DATABASE_WRITE=false\n"
                "PRODUCTION_DEPLOYMENT=false\n"
                "RESTART_OR_CONFIGURATION_MUTATION=false\n"
            ).encode("ascii"),
            stderr=b"",
        )


class CanonicalHermesOriginRevalidatorTests(unittest.TestCase):
    def test_reconstructs_fixed_authority_queue_source_ci_and_adapter_evidence(self):
        revalidator, sender, replay = _revalidator()
        result = revalidator.revalidate(AUTHORIZATION_ISSUE)

        self.assertEqual(result.authorization_issue_number, AUTHORIZATION_ISSUE)
        self.assertEqual(result.authorization_created_at, AUTHORIZATION_CREATED_AT)
        self.assertEqual(result.github_server_time, GITHUB_SERVER_TIME)
        self.assertEqual(result.source_repository, SOURCE_REPOSITORY)
        self.assertEqual(result.source_sha, SOURCE_SHA)
        self.assertEqual(result.current_main_sha, SOURCE_SHA)
        self.assertEqual(result.source_ci_run_id, 9001)
        self.assertTrue(result.authorization_body_unchanged)
        self.assertTrue(result.authorization_replay_available)
        self.assertTrue(result.queue_binding_valid)
        self.assertTrue(result.source_reachable_from_main)
        self.assertTrue(result.source_ci_success)
        self.assertTrue(result.baseline_contract_valid)
        self.assertFalse(result.registry_execution_enabled)
        self.assertFalse(result.prepared_execution_enabled)
        self.assertFalse(result.adapter_preflight_privileged_dispatch_ready)
        self.assertEqual(replay.calls, [REQUEST_ID])
        self.assertTrue(all(call.startswith("/repos/") for call in sender.calls))

    def test_rejects_repository_ci_replay_and_timestamp_drift(self):
        cases = (
            (GitHubFixtureSender(source_repository_id=1), ReplayAvailability()),
            (GitHubFixtureSender(source_ci_success=False), ReplayAvailability()),
            (GitHubFixtureSender(regress_queue_time=True), ReplayAvailability()),
            (GitHubFixtureSender(), ReplayAvailability(False)),
        )
        for sender, replay in cases:
            with self.subTest(sender=sender.__dict__, replay=replay.available):
                revalidator, _, _ = _revalidator(sender, replay)
                with self.assertRaises(ConcreteCanonicalHermesOriginRevalidatorError):
                    revalidator.revalidate(AUTHORIZATION_ISSUE)

    def test_rejects_generic_or_wrong_repository_source_client(self):
        sender = GitHubFixtureSender()
        wrong_provider = _source_provider()
        wrong_provider.repository = "rozkalnsandris/other"
        with self.assertRaises(ConcreteCanonicalHermesOriginRevalidatorError):
            ConcreteCanonicalHermesOriginRevalidator(
                authorization_client=_client(
                    _executor_provider(
                        "rozkalnsandris/deploy-authorizations", 1350486101
                    ),
                    sender,
                ),
                queue_client=_client(
                    _executor_provider("rozkalnsandris/ops-workflows", 1328835922),
                    sender,
                ),
                source_client=_client(wrong_provider, sender),
                auth_surface=load_contract(SURFACE_PATH),
                registry=load_registry(REGISTRY_PATH),
                replay_availability=ReplayAvailability(),
            )

    def test_second_canonical_pass_detects_authorization_drift(self):
        sender = GitHubFixtureSender(replay_authorization_drift=True)
        revalidator, _, _ = _revalidator(sender)
        host = ConcreteSanitizedHermesOriginHostEvidenceResolver(
            observation_provider=ObservationProvider()
        )
        runner = FakeRunner()
        composition = HermesDealsOriginBrokerComposition(
            canonical_revalidator=revalidator,
            host_evidence_resolver=host,
            runner=runner,
        )
        with self.assertRaises(Exception):
            composition.prepare_and_launch(_request_bytes())
        self.assertEqual(runner.calls, [])

    def test_concrete_revalidator_exposes_no_generic_or_execution_surface(self):
        parameters = tuple(
            inspect.signature(
                ConcreteCanonicalHermesOriginRevalidator.revalidate
            ).parameters
        )
        self.assertEqual(parameters, ("self", "authorization_issue_number"))
        source = (
            ROOT
            / "ops/lib/deploy_executor/hermes_deals_origin_canonical_revalidator.py"
        ).read_text(encoding="utf-8")
        for token in (
            "import subprocess",
            "from subprocess",
            "Popen(",
            "os.system(",
            "shell=True",
            "sudo ",
            "systemctl ",
            "adapter.apply(",
            "private_key=",
            "read_text(",
            "read_bytes(",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


class SanitizedHermesOriginHostEvidenceResolverTests(unittest.TestCase):
    def resolve(self, value: dict[str, object] | bytes | None = None):
        provider = ObservationProvider(value)
        resolver = ConcreteSanitizedHermesOriginHostEvidenceResolver(
            observation_provider=provider
        )
        return resolver.resolve(
            source_sha=SOURCE_SHA,
            github_server_time=GITHUB_SERVER_TIME,
        )

    def test_emits_only_minimal_consumer_evidence(self):
        result = self.resolve()
        self.assertEqual(result["registered_source_sha"], SOURCE_SHA)
        self.assertEqual(result["evidence_id"], "hermes-origin-host-1")
        self.assertTrue(result["pull_helper_identity_match"])
        self.assertTrue(result["pull_helper_interface_match"])
        self.assertFalse(result["protected_values_included"])
        self.assertNotIn("source_credential_path", result)
        self.assertNotIn("pull_helper_path", result)

    def test_rejects_extra_path_secret_identity_version_and_authority_expansion(self):
        cases = (
            {**_host_observation(), "extra": "field"},
            _host_observation(registration_path="/tmp/injected"),
            _host_observation(evidence_id="github_pat_secretvalue"),
            _host_observation(service_unit="other.service"),
            _host_observation(pull_helper_path="/tmp/helper"),
            _host_observation(schema="unsupported.v2"),
            _host_observation(authority_expanded=True),
            _host_observation(credential_content_read=True),
            _host_observation(protected_values_included=True),
            _host_observation(observed_at="2026-09-04T07:20:00Z"),
            _host_observation(observed_at="malformed"),
            _host_observation(pull_helper_argument_names=["path", "argv"]),
        )
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(SanitizedHermesOriginHostEvidenceError):
                    self.resolve(value)

    def test_rejects_duplicate_keys_malformed_utf8_and_oversize(self):
        valid = json.dumps(_host_observation(), separators=(",", ":"))
        duplicate = valid.replace(
            '{"schema":',
            '{"schema":"duplicate","schema":',
            1,
        ).encode("utf-8")
        for raw in (duplicate, b"\xff", b"x" * 8193, b'{"schema":NaN}'):
            with self.subTest(raw=raw[:80]):
                with self.assertRaises(SanitizedHermesOriginHostEvidenceError):
                    self.resolve(raw)

    def test_evidence_fields_are_documented_and_resolver_has_no_host_primitive(self):
        self.assertEqual(len(evidence_field_rationale()), 8)
        source = (
            ROOT
            / "ops/lib/deploy_executor/hermes_deals_origin_host_evidence.py"
        ).read_text(encoding="utf-8")
        for token in (
            "import subprocess",
            "from subprocess",
            "Popen(",
            "os.system(",
            "systemctl ",
            "sudo ",
            "open(",
            "read_text(",
            "read_bytes(",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


class HermesOriginBrokerCompositionTests(unittest.TestCase):
    def composition(
        self,
        *,
        provider: ObservationProvider | None = None,
        sender: GitHubFixtureSender | None = None,
    ):
        revalidator, sender, replay = _revalidator(sender)
        provider = provider or ObservationProvider()
        resolver = ConcreteSanitizedHermesOriginHostEvidenceResolver(
            observation_provider=provider
        )
        runner = FakeRunner()
        composition = HermesDealsOriginBrokerComposition(
            canonical_revalidator=revalidator,
            host_evidence_resolver=resolver,
            runner=runner,
        )
        return composition, runner, provider, sender, replay

    def test_identity_only_request_crosses_both_revalidations_before_fake_runner(self):
        composition, runner, provider, sender, replay = self.composition()
        receipt = composition.prepare_and_launch(_request_bytes())

        self.assertEqual(receipt.registered_source_sha, SOURCE_SHA)
        self.assertEqual(receipt.canonical_as_of, "2026-09-04")
        self.assertEqual(receipt.helper_arguments, (SOURCE_SHA, "2026-09-04"))
        self.assertFalse(receipt.production_mutation_started)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(replay.calls, [REQUEST_ID, REQUEST_ID])
        self.assertEqual(len(runner.calls), 1)
        argv, env, timeout, stdout_limit, stderr_limit = runner.calls[0]
        self.assertEqual(argv, (INSTALLED_HELPER_PATH, SOURCE_SHA, "2026-09-04"))
        self.assertEqual(env, FIXED_HELPER_ENV)
        self.assertEqual(timeout, HELPER_TIMEOUT_SECONDS)
        self.assertEqual(stdout_limit, MAX_STDOUT_BYTES)
        self.assertEqual(stderr_limit, MAX_STDERR_BYTES)
        self.assertGreaterEqual(sender.authorization_issue_reads, 4)

    def test_no_bypass_when_host_evidence_or_request_is_invalid(self):
        bad_provider = ObservationProvider(
            _host_observation(pull_helper_source_blob="0" * 40)
        )
        composition, runner, _, _, _ = self.composition(provider=bad_provider)
        with self.assertRaises(SanitizedHermesOriginHostEvidenceError):
            composition.prepare_and_launch(_request_bytes())
        self.assertEqual(runner.calls, [])

        for field in (
            "source_sha",
            "as_of",
            "url",
            "path",
            "command",
            "argv",
            "environment",
            "unit",
            "uid",
            "gid",
            "capability",
        ):
            composition, runner, _, _, _ = self.composition()
            with self.subTest(field=field), self.assertRaises(Exception):
                composition.prepare_and_launch(_request_bytes(**{field: "untrusted"}))
            self.assertEqual(runner.calls, [])

    def test_second_invocation_is_rejected_and_real_helper_is_never_selected(self):
        composition, runner, _, _, _ = self.composition()
        composition.prepare_and_launch(_request_bytes())
        with self.assertRaises(HermesDealsOriginHelperLaunchError):
            composition.prepare_and_launch(_request_bytes())
        self.assertEqual(len(runner.calls), 1)

        source = (
            ROOT
            / "ops/lib/deploy_executor/hermes_deals_origin_broker_composition.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("_run_fixed_helper_process", source)
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("sudo ", source)
        self.assertNotIn("systemctl ", source)

    def test_all_source_readiness_flags_remain_non_live(self):
        canonical = canonical_readiness()
        host = host_readiness()
        composition = composition_readiness()
        self.assertTrue(canonical["concrete_canonical_revalidator_implemented"])
        self.assertFalse(canonical["source_read_authority_proven"])
        self.assertFalse(canonical["credential_read_or_write_implemented"])
        self.assertTrue(host["sanitized_host_evidence_resolver_implemented"])
        self.assertFalse(host["host_wiring_enabled"])
        self.assertFalse(host["production_mutation_started"])
        self.assertTrue(composition["broker_composition_implemented"])
        for flag in (
            "broker_entrypoint_wired",
            "privileged_dispatch_enabled",
            "host_wiring_enabled",
            "live_install_eligible",
            "genuine_hermes_audit_authorized",
            "runner_retirement_eligible",
            "production_mutation_started",
        ):
            self.assertFalse(composition[flag], flag)

    def test_manifest_and_docs_record_source_truth_without_runtime_claims(self):
        manifest = json.loads(
            (
                ROOT
                / "ops/deploy/hermes-deals-origin-broker-installation.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["source_baseline"],
            "13c0c46e9966b0682b53553a92bed510cf491c86",
        )
        self.assertTrue(manifest["completed_source_prerequisite"]["merged"])
        self.assertEqual(manifest["completed_source_prerequisite"]["pull_request"], 366)
        self.assertEqual(manifest["eligible_source_sha"], "2550e77f6cb811ca6f10b49ef0b2fef554d64869")
        self.assertEqual(
            manifest["eligible_source_sha_status"],
            "MERGED_SOURCE_RUNTIME_PREFLIGHT_REQUIRED",
        )
        self.assertEqual(manifest["source_integration"]["status"], "MERGED_SOURCE_RUNTIME_UNPROVEN")
        self.assertFalse(manifest["post_merge_source_evidence"]["runtime_state_proven"])
        self.assertFalse(manifest["live_install_eligible"])
        self.assertFalse(
            manifest["source_integration"][
                "durable_replay_adapter_runtime_proven"
            ]
        )
        self.assertFalse(
            manifest["source_integration"][
                "host_observation_adapter_runtime_proven"
            ]
        )
        for flag in (
            "broker_entrypoint_wired",
            "helper_process_launch_wired",
            "privileged_dispatch_enabled",
            "host_wiring_enabled",
            "genuine_hermes_audit_authorized",
            "runner_retirement_eligible",
            "production_mutation_started",
        ):
            self.assertFalse(manifest["source_gate_flags"][flag], flag)

        master = (ROOT / "docs/AUTOMATION_MASTER_PLAN.md").read_text(
            encoding="utf-8"
        )
        historical = master.index(
            "## Current supersession — Hermes source auth + bounded helper launch gate"
        )
        current = master.index(
            "## Current supersession — Hermes canonical source-integration gate"
        )
        self.assertLess(historical, current)
        current_text = master[current:]
        self.assertIn("CONCRETE_CANONICAL_REVALIDATOR_IMPLEMENTED=true", current_text)
        self.assertIn("SANITIZED_HOST_EVIDENCE_RESOLVER_IMPLEMENTED=true", current_text)
        self.assertIn("BROKER_ENTRYPOINT_WIRED=false", current_text)
        self.assertIn("LIVE_INSTALL_ELIGIBLE=false", current_text)
        self.assertIn("PRODUCTION_MUTATION_STARTED=false", current_text)

        for path in (
            "docs/HERMES_DEALS_ORIGIN_DISPATCH_READINESS.md",
            "docs/HERMES_DEALS_ORIGIN_PULL_CANARY_SOURCE.md",
        ):
            text = (ROOT / path).read_text(encoding="utf-8")
            supersession = text.index("Source-integration supersession after merged #365/#366")
            current_text = text[supersession:]
            self.assertIn("CONCRETE_CANONICAL_REVALIDATOR_IMPLEMENTED=true", current_text)
            self.assertIn("SOURCE_READ_AUTHORITY_PROVEN=false", current_text)
            self.assertIn("LIVE_INSTALL_ELIGIBLE=false", current_text)
            self.assertIn("PRODUCTION_MUTATION_STARTED=false", current_text)


if __name__ == "__main__":
    unittest.main()
