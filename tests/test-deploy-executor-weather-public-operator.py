from __future__ import annotations

from dataclasses import replace
import ast
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.protocol import AcceptedAuthorization, AUTHORIZATION_REPOSITORY, AUTHORIZATION_REPOSITORY_ID
from deploy_executor.state import StateStore
from deploy_executor.weather_public_runtime_adapter import SOURCE_REPOSITORY, TARGET_ALIAS
from deploy_executor.weather_public_runtime_bootstrap import BASELINE_EVIDENCE_SCHEMA, parse_weather_bootstrap_baseline
from deploy_executor.weather_public_runtime_composite import (
    ADDITIONAL_MUTATION_BUDGET,
    COMPOSITE_GATE_ORDER,
    FULL_MUTATION_BUDGET,
    HOST_ALIAS,
    RELEASE_MUTATION_BUDGET,
    WeatherCompositeAuthorityEvidence,
)
from deploy_executor.weather_public_runtime_helper_launch import WeatherHelperLaunchReceipt
from deploy_executor.weather_public_runtime_operator import (
    HELPER_MANIFEST_RELATIVE,
    HOST_VOLUME,
    OPERATOR_STATUS,
    RPi5_ORIGIN,
    TRUSTED_CHECKOUT_NAME,
    ConcreteSanitizedWeatherBaselineProvider,
    ConcreteWeatherOperatorHostMutator,
    ConcreteWeatherReplayAuthority,
    CommandResult,
    WeatherCompositeOperator,
    WeatherCompositeOperatorError,
    WeatherOperatorMutationReceipt,
    WeatherReplayConsumptionReceipt,
    WeatherTrustedCheckoutPreflight,
    _safe_relative,
    source_readiness,
)
from deploy_executor.weather_public_runtime_privileged_install import (
    TRUSTED_INSTALL_CHECKOUT_NAME,
    expected_install_artifacts,
)
from deploy_executor.weather_public_runtime_stage_helper import CommandResult as StageCommandResult, _application_release, _volume_ensure

ISSUE = 45417
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174517"
WEATHER_SHA = "a" * 40
RPI5_SHA = "b" * 40
SHA256_A = "1" * 64
SHA256_B = "2" * 64
SHA256_C = "3" * 64
SHA256_D = "4" * 64


def baseline_payload(*, deployed=False, schema=False, schedule=False):
    return {
        "schema": BASELINE_EVIDENCE_SCHEMA,
        "target_alias": TARGET_ALIAS,
        "deployment_state": "deployed" if deployed else "not_deployed",
        "current_source_sha": WEATHER_SHA if deployed else None,
        "persistent_volume_state": "present" if deployed else "absent",
        "schema_state": "ready" if schema else "absent",
        "schema_version": 1 if schema else None,
        "public_ingest_schedule_state": "enabled" if schedule else "absent",
        "bootstrap_stage_state": (
            "recurring_ingest_enabled" if schedule else "schema_ready" if schema else "application_ready" if deployed else "not_started"
        ),
        "privacy_safe": True,
    }


INITIAL_TOKEN = parse_weather_bootstrap_baseline(baseline_payload()).canonical_token


def authority(*, consumed=False):
    return WeatherCompositeAuthorityEvidence(
        authorization_issue_number=ISSUE,
        authorization_issue_id=990001,
        authorization_created_at="2026-09-10T17:00:00Z",
        github_server_time="2026-09-10T17:00:01Z",
        request_id=REQUEST_ID,
        authorization_payload_sha256=SHA256_A,
        authorization_raw_body_sha256=SHA256_B,
        composite_authorization_sha256=SHA256_C,
        queue_issue_number=46,
        queue_contract_sha256=SHA256_D,
        source_sha=WEATHER_SHA,
        weather_current_main_sha=WEATHER_SHA,
        weather_ci_run_id=123,
        rpi5_main_sha=RPI5_SHA,
        rpi5_main_ci_run_id=456,
        host_alias=HOST_ALIAS,
        target_alias=TARGET_ALIAS,
        expected_bootstrap_baseline_token=INITIAL_TOKEN,
        start_date="2026-04-02",
        end_date="2026-09-10",
        recovery_decision="owner-accepted-no-prewrite-backup",
        release_mutation_budget=RELEASE_MUTATION_BUDGET,
        additional_mutation_budget=ADDITIONAL_MUTATION_BUDGET,
        full_mutation_budget=FULL_MUTATION_BUDGET,
        authorization_replay_available=not consumed,
        authorization_replay_consumed=consumed,
    )


class FakeRevalidator:
    def __init__(self, log): self.log = log
    def revalidate_composite(self, issue):
        self.log.append(("jit-pre", issue)); return authority()
    def revalidate_consumed_composite(self, issue):
        self.log.append(("jit-consumed", issue)); return authority(consumed=True)


class FakeReplay:
    def __init__(self, log, *, fail=False): self.log=log; self.fail=fail
    def consume(self, request_id):
        self.log.append(("consume", request_id))
        if self.fail: raise RuntimeError("synthetic consume failure")
        return WeatherReplayConsumptionReceipt(request_id, "CONSUMED", 2, True, True)


class FakeBaseline:
    def __init__(self, log): self.log=log; self.phase="initial"
    def resolve(self, *, source_sha, target_alias):
        self.log.append(("baseline", self.phase))
        assert source_sha == WEATHER_SHA and target_alias == TARGET_ALIAS
        if self.phase == "initial": return baseline_payload()
        if self.phase == "deployed": return baseline_payload(deployed=True)
        if self.phase == "schema": return baseline_payload(deployed=True, schema=True)
        if self.phase == "enabled": return baseline_payload(deployed=True, schema=True, schedule=True)
        raise AssertionError(self.phase)


class FakeHost:
    def __init__(self, log, *, fail_gate=None, excess_gate=None, checkout_state="absent", fail_preflight=False):
        self.log=log; self.fail_gate=fail_gate; self.excess_gate=excess_gate
        self.checkout_state=checkout_state; self.fail_preflight=fail_preflight
    def preflight_trusted_checkout(self, expected_sha):
        assert expected_sha == RPI5_SHA
        self.log.append(("preflight", self.checkout_state))
        if self.fail_preflight: raise RuntimeError("synthetic checkout incompatibility")
        return WeatherTrustedCheckoutPreflight(self.checkout_state)
    def _one(self, gate, category):
        self.log.append(("host", gate))
        if self.fail_gate == gate: raise RuntimeError("synthetic host failure")
        count = 2 if self.excess_gate == gate else 1
        return WeatherOperatorMutationReceipt(gate, ((category, count),), True)
    def trusted_checkout_fetch(self, expected_sha):
        assert expected_sha == RPI5_SHA
        if self.checkout_state == "verified_existing":
            self.log.append(("reuse", "trusted_checkout_fetch"))
            return WeatherOperatorMutationReceipt("trusted_checkout_fetch_verified_existing", (("git.trusted-checkout-fetch", 0),), False)
        return self._one("trusted_checkout_fetch", "git.trusted-checkout-fetch")
    def trusted_checkout_worktree_add(self, expected_sha):
        assert expected_sha == RPI5_SHA
        if self.checkout_state == "verified_existing":
            self.log.append(("reuse", "trusted_checkout_worktree_add"))
            return WeatherOperatorMutationReceipt("trusted_checkout_worktree_add_verified_existing", (("git.trusted-checkout-worktree-add", 0),), False)
        return self._one("trusted_checkout_worktree_add", "git.trusted-checkout-worktree-add")
    def install_helper(self, expected_sha):
        assert expected_sha == RPI5_SHA; return self._one("helper_install", "filesystem.weather-helper-install-transaction")
    def publish_activation(self, plan):
        assert plan.source_sha == WEATHER_SHA; return self._one("activation_publish", "filesystem.weather-helper-activation-publish")


class FakeLauncher:
    def __init__(self, log, baseline, *, fail_stage=None): self.log=log; self.baseline=baseline; self.fail_stage=fail_stage
    def launch_stage(self, executable, host, envelope, stage_id):
        self.log.append(("launch", stage_id))
        if self.fail_stage == stage_id: raise RuntimeError("synthetic helper failure")
        stage = next(item for item in executable.stages if item.stage_id == stage_id)
        if stage_id == "persistent_volume_ensure": self.baseline.phase = "deployed"
        elif stage_id == "explicit_schema_init": self.baseline.phase = "schema"
        elif stage_id == "recurring_public_ingest_schedule": self.baseline.phase = "enabled"
        operations = 0 if stage_id in {"readiness_schema_privacy", "public_smoke_read_only"} else stage.max_operations
        return WeatherHelperLaunchReceipt(
            authorization_issue_number=ISSUE,
            request_id=REQUEST_ID,
            stage_id=stage.stage_id,
            helper_id=stage.helper_id,
            source_sha=WEATHER_SHA,
            preactivation_sha256=executable.preactivation_sha256,
            operations_performed=operations,
            helper_exit_code=0,
            output_validated=True,
            production_mutation_started=not stage.read_only and operations > 0,
        )


def operator(*, fail_host=None, excess_host=None, fail_stage=None, fail_consume=False, checkout_state="absent", fail_preflight=False, host_mutator=None):
    log=[]; baseline=FakeBaseline(log)
    host = host_mutator or FakeHost(
        log,
        fail_gate=fail_host,
        excess_gate=excess_host,
        checkout_state=checkout_state,
        fail_preflight=fail_preflight,
    )
    return WeatherCompositeOperator(
        revalidator=FakeRevalidator(log),
        replay_authority=FakeReplay(log, fail=fail_consume),
        baseline_provider=baseline,
        host_mutator=host,
        launcher=FakeLauncher(log, baseline, fail_stage=fail_stage),
    ), log


class WeatherCompositeOperatorTests(unittest.TestCase):
    def test_source_surface_is_identity_only_and_host_inactive(self):
        readiness = source_readiness()
        self.assertEqual(readiness["status"], OPERATOR_STATUS)
        self.assertEqual(tuple(inspect.signature(WeatherCompositeOperator.execute).parameters), ("self", "authorization_issue_number"))
        self.assertEqual(readiness["caller_authority"], ("authorization_issue_number",))
        self.assertTrue(readiness["fixed_helper_launcher_wired"])
        self.assertTrue(readiness["trusted_checkout_preconsume_compatibility_check"])
        self.assertTrue(readiness["trusted_checkout_verified_reuse_enabled"])
        self.assertFalse(readiness["host_installed"])
        self.assertFalse(readiness["runtime_live_authority"])
        self.assertFalse(readiness["generic_shell_authority"])
        self.assertFalse(readiness["automatic_retry"])

    def test_success_is_consume_first_then_exact_gate_order_and_budget(self):
        target, log = operator()
        receipt = target.execute(ISSUE)
        consume_index = log.index(("consume", REQUEST_ID))
        first_host = next(i for i, row in enumerate(log) if row[0] == "host")
        self.assertLess(consume_index, first_host)
        self.assertEqual(receipt.completed_gates, COMPOSITE_GATE_ORDER)
        self.assertEqual(dict(receipt.mutation_counts), dict(FULL_MUTATION_BUDGET))
        self.assertEqual(dict(receipt.read_only_invocations), {"readiness_schema_privacy": 1, "public_smoke_read_only": 1, "corpus_integrity_check": 3})
        self.assertTrue(receipt.durable_replay_consumed)
        self.assertTrue(receipt.authorization_reuse_forbidden)
        self.assertTrue(receipt.production_mutation_started)
        self.assertEqual(sum(1 for row in log if row[0] == "host"), 4)
        self.assertEqual(sum(1 for row in log if row[0] == "launch"), 9)
        self.assertGreaterEqual(sum(1 for row in log if row[0] == "jit-consumed"), len(COMPOSITE_GATE_ORDER) + 1)

    def _concrete_checkout_fixture(self, root, *, present=True, head=RPI5_SHA, clean=True, detached=True, origin=RPi5_ORIGIN):
        manager = root / "RPi5_main"
        trusted = root / TRUSTED_CHECKOUT_NAME
        manager.mkdir()
        account = mock.Mock(pw_uid=os.getuid(), pw_gid=os.getgid(), pw_dir=str(root))
        if present:
            trusted.mkdir(mode=0o755)
            manifest = json.loads((ROOT / HELPER_MANIFEST_RELATIVE).read_text())
            manifest_path = trusted / HELPER_MANIFEST_RELATIVE
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(manifest))
            for artifact in manifest["artifacts"]:
                source = trusted / artifact["source"]
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("fixture\n")
        calls = []

        def runner(argv, *, env=None, user=None, group=None):
            argv = tuple(argv); calls.append(argv)
            self.assertEqual(argv[0], "/usr/bin/git")
            cwd = argv[argv.index("-C") + 1]
            tail = argv[argv.index("-C") + 2:]
            if cwd == str(manager):
                if tail == ("rev-parse", "--show-toplevel"):
                    return CommandResult(0, str(manager) + "\n", "")
                if tail == ("remote", "get-url", "origin"):
                    return CommandResult(0, RPi5_ORIGIN + "\n", "")
            if cwd == str(trusted):
                if tail == ("rev-parse", "--show-toplevel"):
                    return CommandResult(0, str(trusted) + "\n", "")
                if tail == ("rev-parse", "HEAD"):
                    return CommandResult(0, head + "\n", "")
                if tail == ("status", "--porcelain=v1", "--untracked-files=all"):
                    return CommandResult(0, "" if clean else " M fixture\n", "")
                if tail == ("symbolic-ref", "-q", "HEAD"):
                    return CommandResult(1 if detached else 0, "" if detached else "refs/heads/main\n", "")
                if tail == ("remote", "get-url", "origin"):
                    return CommandResult(0, origin + "\n", "")
                if tail[:2] == ("merge-base", "--is-ancestor"):
                    return CommandResult(0, "", "")
            raise AssertionError(argv)

        return account, manager, trusted, runner, calls

    def test_concrete_existing_checkout_exact_is_verified_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account, manager, trusted, runner, calls = self._concrete_checkout_fixture(root)
            with mock.patch(
                "deploy_executor.weather_public_runtime_operator._owner_paths",
                return_value=(account, manager, trusted),
            ):
                result = ConcreteWeatherOperatorHostMutator(runner=runner).preflight_trusted_checkout(RPI5_SHA)
            self.assertEqual(result.state, "verified_existing")
            self.assertFalse(any("fetch" in argv or "worktree" in argv for argv in calls))

    def test_concrete_existing_checkout_drift_fails_before_consume(self):
        cases = {
            "wrong-sha": {"head": "c" * 40},
            "dirty": {"clean": False},
            "attached": {"detached": False},
            "wrong-origin": {"origin": "https://github.com/example/drift.git"},
        }
        for label, overrides in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                account, manager, trusted, runner, _calls = self._concrete_checkout_fixture(root, **overrides)
                concrete = ConcreteWeatherOperatorHostMutator(runner=runner)
                target, log = operator(host_mutator=concrete)
                with mock.patch(
                    "deploy_executor.weather_public_runtime_operator._owner_paths",
                    return_value=(account, manager, trusted),
                ), self.assertRaises(WeatherCompositeOperatorError) as caught:
                    target.execute(ISSUE)
                self.assertEqual(caught.exception.stage, "trusted_checkout_preflight")
                self.assertFalse(caught.exception.authorization_reuse_forbidden)
                self.assertFalse(caught.exception.host_mutation_started)
                self.assertFalse(caught.exception.production_mutation_started)
                self.assertFalse(any(row[0] == "consume" for row in log))

    def test_concrete_absent_checkout_preflight_is_read_only_and_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account, manager, trusted, runner, calls = self._concrete_checkout_fixture(root, present=False)
            with mock.patch(
                "deploy_executor.weather_public_runtime_operator._owner_paths",
                return_value=(account, manager, trusted),
            ):
                result = ConcreteWeatherOperatorHostMutator(runner=runner).preflight_trusted_checkout(RPI5_SHA)
            self.assertEqual(result.state, "absent")
            self.assertFalse(trusted.exists())
            self.assertFalse(any("fetch" in argv or "worktree" in argv for argv in calls))

    def test_verified_existing_checkout_is_preflighted_before_consume_and_skips_git_mutations(self):
        target, log = operator(checkout_state="verified_existing")
        receipt = target.execute(ISSUE)
        self.assertLess(log.index(("preflight", "verified_existing")), log.index(("consume", REQUEST_ID)))
        self.assertEqual(receipt.trusted_checkout_state, "verified_existing")
        counts = dict(receipt.mutation_counts)
        self.assertEqual(counts["git.trusted-checkout-fetch"], 0)
        self.assertEqual(counts["git.trusted-checkout-worktree-add"], 0)
        self.assertIn(("reuse", "trusted_checkout_fetch"), log)
        self.assertIn(("reuse", "trusted_checkout_worktree_add"), log)
        self.assertTrue(receipt.authorization_reuse_forbidden)

    def test_deterministic_checkout_incompatibility_fails_before_replay_consume(self):
        target, log = operator(fail_preflight=True)
        with self.assertRaises(WeatherCompositeOperatorError) as caught:
            target.execute(ISSUE)
        self.assertEqual(caught.exception.stage, "trusted_checkout_preflight")
        self.assertFalse(caught.exception.authorization_reuse_forbidden)
        self.assertFalse(caught.exception.host_mutation_started)
        self.assertFalse(caught.exception.production_mutation_started)
        self.assertFalse(any(row[0] == "consume" for row in log))
        self.assertFalse(any(row[0] == "host" for row in log))

    def test_consume_failure_is_terminal_before_host_mutation(self):
        target, log = operator(fail_consume=True)
        with self.assertRaises(WeatherCompositeOperatorError) as caught:
            target.execute(ISSUE)
        self.assertEqual(caught.exception.stage, "durable_replay_consume")
        self.assertTrue(caught.exception.authorization_reuse_forbidden)
        self.assertFalse(caught.exception.host_mutation_started)
        self.assertFalse(caught.exception.production_mutation_started)
        self.assertFalse(any(row[0] == "host" for row in log))

    def test_first_host_failure_reports_attempt_and_has_no_retry(self):
        target, log = operator(fail_host="trusted_checkout_fetch")
        with self.assertRaises(WeatherCompositeOperatorError) as caught:
            target.execute(ISSUE)
        self.assertEqual(caught.exception.stage, "trusted_checkout_fetch")
        self.assertTrue(caught.exception.authorization_reuse_forbidden)
        self.assertTrue(caught.exception.host_mutation_started)
        self.assertFalse(caught.exception.production_mutation_started)
        self.assertEqual(log.count(("host", "trusted_checkout_fetch")), 1)
        self.assertNotIn(("host", "trusted_checkout_worktree_add"), log)

    def test_mutating_helper_failure_marks_production_started_before_result(self):
        target, log = operator(fail_stage="application_release")
        with self.assertRaises(WeatherCompositeOperatorError) as caught:
            target.execute(ISSUE)
        self.assertEqual(caught.exception.stage, "application_release")
        self.assertTrue(caught.exception.authorization_reuse_forbidden)
        self.assertTrue(caught.exception.host_mutation_started)
        self.assertTrue(caught.exception.production_mutation_started)
        self.assertEqual(log.count(("launch", "application_release")), 1)
        self.assertNotIn(("launch", "persistent_volume_ensure"), log)

    def test_budget_excess_stops_before_next_gate(self):
        target, log = operator(excess_host="trusted_checkout_fetch")
        with self.assertRaises(WeatherCompositeOperatorError) as caught:
            target.execute(ISSUE)
        self.assertEqual(caught.exception.stage, "trusted_checkout_fetch")
        self.assertTrue(caught.exception.authorization_reuse_forbidden)
        self.assertNotIn(("host", "trusted_checkout_worktree_add"), log)

    def test_replay_authority_durably_consumes_once(self):
        accepted = AcceptedAuthorization(
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            issue_id=99117,
            issue_number=ISSUE,
            request_id=REQUEST_ID,
            created_at=datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc),
            target_alias=TARGET_ALIAS,
            canonical_payload_json="{}",
            canonical_payload_sha256=SHA256_A,
            raw_body_sha256=SHA256_B,
            performed_via_github_app_id=None,
            performed_via_github_app_slug=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"state.sqlite3"
            with StateStore(db, bootstrap=True): pass
            db.chmod(0o600)
            with mock.patch("deploy_executor.weather_public_runtime_operator.STATE_DB_PATH", db), mock.patch("deploy_executor.weather_public_runtime_operator.ROOT_UID", os.getuid()), mock.patch("deploy_executor.weather_public_runtime_operator.ROOT_GID", os.getgid()):
                replay=ConcreteWeatherReplayAuthority()
                self.assertTrue(replay.is_available(accepted))
                self.assertTrue(replay.is_available(accepted))
                receipt=replay.consume(REQUEST_ID)
                self.assertEqual(receipt.state, "CONSUMED")
                self.assertTrue(replay.is_consumed(accepted))
                with self.assertRaises(RuntimeError): replay.consume(REQUEST_ID)

    def test_manifest_path_and_write_hardening_is_present(self):
        with self.assertRaises(RuntimeError): _safe_relative("../escape", "fixture")
        with self.assertRaises(RuntimeError): _safe_relative("/absolute", "fixture")
        self.assertEqual(_safe_relative("ops/lib/x.py", "fixture"), Path("ops/lib/x.py"))
        source=(ROOT/"ops/lib/deploy_executor/weather_public_runtime_operator.py").read_text()
        self.assertIn("_write_all(fd, raw)", source)
        self.assertIn('".." in relative.parts', source)
        for forbidden in ("shell=True", "os.system(", "subprocess.Popen(", "eval(", "exec("):
            self.assertNotIn(forbidden, source)


    def test_sanitized_baseline_binds_release_head_and_running_image(self):
        calls=[]
        image_match={"value": True}
        def runner(argv, *, env=None, user=None, group=None):
            argv=tuple(argv); calls.append(argv)
            if argv[:4] == ("/usr/bin/docker", "ps", "-a", "--filter"):
                return CommandResult(0, "container-1\n", "")
            if argv[:4] == ("/usr/bin/docker", "volume", "ls", "--filter"):
                return CommandResult(0, HOST_VOLUME + "\n", "")
            if argv[0:2] == ("/usr/bin/git", "--no-optional-locks") and "rev-parse" in argv:
                return CommandResult(0, WEATHER_SHA + "\n", "")
            if argv[0:2] == ("/usr/bin/git", "--no-optional-locks") and "status" in argv:
                return CommandResult(0, "", "")
            if argv[:2] == ("/usr/bin/docker", "compose") and "ps" in argv:
                return CommandResult(0, "container-1\n", "")
            if argv[:3] == ("/usr/bin/docker", "inspect", "--format"):
                return CommandResult(0, "sha256:exact\n", "")
            if argv[:2] == ("/usr/bin/docker", "compose") and "images" in argv:
                return CommandResult(0, ("sha256:exact" if image_match["value"] else "sha256:drift") + "\n", "")
            if argv[:2] == ("/usr/bin/docker", "compose") and "exec" in argv:
                payload={"schema_version":1,"database":{"state":"ready"},"privacy":{"coordinates_exposed":False,"credentials_exposed":False,"database_path_exposed":False}}
                return CommandResult(0, json.dumps(payload), "")
            raise AssertionError(argv)
        with tempfile.TemporaryDirectory() as tmp:
            release_root=Path(tmp)/"releases"
            compose=release_root/WEATHER_SHA/"deploy/docker-compose.public.yml"
            compose.parent.mkdir(parents=True)
            compose.write_text("services: {}\n")
            timer=Path(tmp)/"missing.timer"
            with mock.patch("deploy_executor.weather_public_runtime_operator.RELEASE_ROOT", str(release_root)), mock.patch("deploy_executor.weather_public_runtime_operator.SYSTEMD_TIMER_PATH", timer):
                provider=ConcreteSanitizedWeatherBaselineProvider(runner=runner)
                value=provider.resolve(source_sha=WEATHER_SHA, target_alias=TARGET_ALIAS)
                parsed=parse_weather_bootstrap_baseline(value)
                self.assertEqual(parsed.current_source_sha, WEATHER_SHA)
                self.assertEqual(parsed.schema_state, "ready")
                image_match["value"]=False
                with self.assertRaises(RuntimeError):
                    provider.resolve(source_sha=WEATHER_SHA, target_alias=TARGET_ALIAS)

    def test_application_stage_cannot_implicitly_create_named_volume(self):
        calls=[]
        def runner(argv):
            argv=tuple(argv); calls.append(argv)
            if argv[:3] == ("/usr/bin/git", "-C", str(release)) and argv[3:] == ("rev-parse", "HEAD"):
                return StageCommandResult(0, WEATHER_SHA + "\n", "")
            if argv[:3] == ("/usr/bin/git", "-C", str(release)) and argv[3:5] == ("status", "--porcelain=v1"):
                return StageCommandResult(0, "", "")
            if argv[:4] == ("/usr/bin/docker", "volume", "ls", "--filter"):
                return StageCommandResult(0, "", "")
            return StageCommandResult(0, "", "")
        with tempfile.TemporaryDirectory() as tmp:
            release=Path(tmp)/WEATHER_SHA
            (release/"deploy").mkdir(parents=True)
            (release/"deploy/docker-compose.public.yml").write_text("services: {}\n")
            _application_release(release, release, WEATHER_SHA, runner)
            app_calls=tuple(calls)
            self.assertTrue(any("build" in argv for argv in app_calls))
            self.assertFalse(any("up" in argv for argv in app_calls))
            calls.clear()
            _volume_ensure(release, runner)
            create_index=next(i for i, argv in enumerate(calls) if argv[:3] == ("/usr/bin/docker", "volume", "create"))
            up_index=next(i for i, argv in enumerate(calls) if "up" in argv)
            self.assertLess(create_index, up_index)

    def test_machine_contracts_remain_source_only(self):
        contract=json.loads((ROOT/"ops/deploy/weather-public-runtime-operator.json").read_text())
        install=json.loads((ROOT/"ops/deploy/weather-public-runtime-operator-install.json").read_text())
        registry=json.loads((ROOT/"ops/deploy/weather-public-runtime-operator-registry.json").read_text())
        self.assertEqual(contract["status"], "SOURCE_READY_HOST_NOT_INSTALLED")
        self.assertEqual(contract["caller_authority"], ["authorization_issue_number"])
        self.assertEqual(contract["gate_order"], list(COMPOSITE_GATE_ORDER))
        self.assertEqual(TRUSTED_CHECKOUT_NAME, TRUSTED_INSTALL_CHECKOUT_NAME)
        self.assertEqual(
            contract["trusted_checkout_contract"],
            "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json",
        )
        self.assertEqual(
            contract["privileged_install_activation_contract"],
            "ops/deploy/weather-public-runtime-privileged-install-activation.json",
        )
        self.assertFalse(contract["safety"]["source_merge_authorizes_live"])
        self.assertFalse(contract["safety"]["host_installed"])
        self.assertEqual(install["status"], "SOURCE_READY_INSTALL_DISABLED")
        self.assertEqual(install["artifact_count"], 23)
        artifacts = install["artifacts"]
        self.assertEqual(len(artifacts), len({row["destination"] for row in artifacts}))
        self.assertTrue(all((ROOT / row["source"]).is_file() for row in artifacts))
        helper_install = json.loads((ROOT / "ops/deploy/weather-public-runtime-helper-install.json").read_text())
        manifest_identity = tuple(
            (row["source"], row["destination"], int(row["mode"], 8))
            for row in helper_install["artifacts"]
        )
        self.assertEqual(manifest_identity, expected_install_artifacts())
        self.assertIn(
            "ops/lib/deploy_executor/weather_public_runtime_privileged_install.py",
            [row["source"] for row in artifacts],
        )
        self.assertNotIn(
            "ops/lib/deploy_executor/weather_public_runtime_operator.py",
            [row["source"] for row in helper_install["artifacts"]],
        )
        module_sources = {
            Path(row["source"]).stem
            for row in artifacts
            if row["kind"] == "module"
        }
        for module in tuple(module_sources):
            tree = ast.parse((ROOT / f"ops/lib/deploy_executor/{module}.py").read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                    dependency = node.module.split(".", 1)[0]
                    if (ROOT / f"ops/lib/deploy_executor/{dependency}.py").is_file():
                        self.assertIn(dependency, module_sources)
        entrypoint = (ROOT / "ops/bin/rozkalns-weather-public-runtime-operator").read_text()
        self.assertIn("--issue-number", entrypoint)
        self.assertNotIn("--path", entrypoint)
        self.assertNotIn("--command", entrypoint)
        self.assertFalse(install["activation"]["source_merge_authorizes_install"])
        self.assertTrue(install["activation"]["separate_explicit_live_authorization_required"])
        self.assertFalse(registry["execution_enabled"])
        self.assertEqual(len(registry["operations"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
