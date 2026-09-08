from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

import deploy_executor.hermes_deals_netto_nonroot_preflight_v2_execution_identity as execution
from deploy_executor.hermes_deals_netto_nonroot_preflight_v2_execution_identity import (
    ACCESS_CONTRACT_ID,
    BROKER_COMPOSITION_PATTERN,
    CANARY_AUTHORIZED,
    CONTRACT_ID,
    CORPUS_PARENT,
    CORPUS_ROOT,
    EXECUTION_ENABLED,
    EXECUTION_GROUP,
    EXECUTION_HOME,
    EXECUTION_SHELL,
    EXECUTION_USER,
    FIXED_ARGV,
    FIXED_CWD,
    FIXED_ENV,
    FIXED_INPUT_ACCESS,
    FIXED_INPUT_RELATIVE_PATHS,
    HELPER_SHA256,
    HOST_WIRING_ENABLED,
    INPUT_OWNER_ACCOUNT,
    INPUT_OWNER_HOME_TOKEN,
    INSTALLED_HELPER_PATH,
    N9_GENERATED,
    N9_MANIFEST,
    N9_ROOT,
    PARALLEL_PRIVILEGED_BROKER_ALLOWED,
    PRODUCTION_MUTATION_STARTED,
    REGISTRATION_BYTES,
    REGISTRATION_PATH,
    REGISTRATION_SHA256,
    SOURCE_SHA,
    ExecutionIdentitySnapshot,
    FixedAccessSnapshot,
    FixedProcessResult,
    HermesDealsNettoExecutionIdentityError,
    HermesDealsNettoV2OneShotLauncher,
    SecureFileSnapshot,
    fixed_launch_plan,
    source_readiness,
    validate_execution_identity,
    validate_fixed_input_access,
    validate_helper_result,
    validate_installed_provenance,
)

CONTRACT_PATH = (
    ROOT / "ops" / "deploy"
    / "hermes-deals-netto-nonroot-preflight-v2-execution-identity.json"
)
SOURCE_PATH = (
    ROOT / "ops" / "lib" / "deploy_executor"
    / "hermes_deals_netto_nonroot_preflight_v2_execution_identity.py"
)


def _identity(**overrides) -> ExecutionIdentitySnapshot:
    values = {
        "username": EXECUTION_USER,
        "uid": 991,
        "primary_group": EXECUTION_GROUP,
        "gid": 991,
        "home": EXECUTION_HOME,
        "shell": EXECUTION_SHELL,
        "supplementary_groups": (),
    }
    values.update(overrides)
    return ExecutionIdentitySnapshot(**values)


def _access() -> tuple[FixedAccessSnapshot, ...]:
    return tuple(
        FixedAccessSnapshot(
            row.path,
            row.kind,
            row.readable,
            row.executable,
            row.writable,
        )
        for row in FIXED_INPUT_ACCESS
    )


def _helper_snapshot(**overrides) -> SecureFileSnapshot:
    values = {
        "path": INSTALLED_HELPER_PATH,
        "regular": True,
        "symlink": False,
        "link_count": 1,
        "uid": 0,
        "gid": 0,
        "mode": 0o555,
        "size": 12_000,
        "sha256": HELPER_SHA256,
        "descriptor_matches_path": True,
        "content": None,
    }
    values.update(overrides)
    return SecureFileSnapshot(**values)


def _registration_snapshot(**overrides) -> SecureFileSnapshot:
    values = {
        "path": REGISTRATION_PATH,
        "regular": True,
        "symlink": False,
        "link_count": 1,
        "uid": 0,
        "gid": 0,
        "mode": 0o444,
        "size": len(REGISTRATION_BYTES),
        "sha256": REGISTRATION_SHA256,
        "descriptor_matches_path": True,
        "content": REGISTRATION_BYTES,
    }
    values.update(overrides)
    return SecureFileSnapshot(**values)


def _valid_result(uid: int = 991) -> FixedProcessResult:
    payload = {
        "schema": "rozkalns.hermes-deals.netto-nonroot-preflight-v2-evidence.v1",
        "schema_version": 2,
        "strategy": "netto_missing_normal_price_nonroot_access_preflight_v2",
        "capability": "netto-missing-normal-price-nonroot-preflight-v2",
        "registered_source_sha": SOURCE_SHA,
        "runner_user": EXECUTION_USER,
        "runner_uid": uid,
        "n9_manifest_readable": True,
        "n9_manifest_sha256_match": True,
        "corpus_root_readable": True,
        "corpus_root_executable": True,
        "blocked_at": "campaign_identity_probe_required",
        "non_root_ready": False,
        "safe_permission_metadata": {
            "home_andris_mode": "750",
            "home_andris_uid": 1000,
            "home_andris_gid": 1000,
            "n9_parent_mode": "750",
            "corpus_root_mode": "750",
        },
        "sudo_used": False,
        "file_contents_exported": False,
        "parser_executed": False,
        "database_write_performed": False,
        "review_write_performed": False,
        "deployment_performed": False,
    }
    return FixedProcessResult(
        0,
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        b"",
    )


class NettoExecutionIdentityContractTests(unittest.TestCase):
    def test_machine_contract_matches_source_and_stays_disabled(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        readiness = source_readiness()

        self.assertEqual(contract["schema"], "rozkalns.hermes-deals.netto-v2-execution-identity.v1")
        self.assertEqual(contract["status"], "SOURCE_ONLY_EXECUTION_DISABLED")
        self.assertEqual(contract["tracking_issue"], 425)
        self.assertEqual(contract["source"]["registered_source_sha"], SOURCE_SHA)
        self.assertEqual(contract["source"]["helper_sha256"], HELPER_SHA256)
        self.assertEqual(contract["source"]["registration_sha256"], REGISTRATION_SHA256)
        self.assertEqual(contract["execution_identity"]["account"], EXECUTION_USER)
        self.assertEqual(contract["execution_identity"]["primary_group"], EXECUTION_GROUP)
        self.assertEqual(contract["execution_identity"]["home"], EXECUTION_HOME)
        self.assertEqual(contract["execution_identity"]["shell"], EXECUTION_SHELL)
        self.assertEqual(contract["execution_identity"]["supplementary_groups"], [])
        self.assertTrue(contract["execution_identity"]["forbidden_numeric_identity_aliases"])
        self.assertEqual(contract["architecture"]["reuse_pattern"], BROKER_COMPOSITION_PATTERN)
        self.assertFalse(contract["architecture"]["parallel_privileged_broker_allowed"])
        self.assertFalse(contract["input_access"]["generic_home_read_allowed"])
        self.assertFalse(contract["process"]["direct_low_level_execution_when_disabled"])
        self.assertEqual(contract["process"]["argv"], list(FIXED_ARGV))
        self.assertEqual(contract["process"]["cwd"], FIXED_CWD)
        self.assertEqual(contract["process"]["environment"], dict(FIXED_ENV))
        self.assertEqual(
            contract["input_access"]["path_binding"],
            {
                "base_token": INPUT_OWNER_HOME_TOKEN,
                "owner_account": INPUT_OWNER_ACCOUNT,
                "absolute_path_authority": (
                    "frozen_helper_provenance_plus_future_trusted_host_resolver"
                ),
                "relative_paths_are_source_fixed": True,
                "caller_override_allowed": False,
            },
        )
        self.assertEqual(
            contract["input_access"]["requirements"],
            [
                {
                    "relative_path": relative_path,
                    "kind": item.kind,
                    "readable": item.readable,
                    "executable": item.executable,
                    "writable": item.writable,
                }
                for relative_path, item in zip(
                    FIXED_INPUT_RELATIVE_PATHS, FIXED_INPUT_ACCESS, strict=True
                )
            ],
        )
        self.assertEqual(readiness["input_owner_account"], INPUT_OWNER_ACCOUNT)
        self.assertEqual(readiness["input_owner_home_token"], INPUT_OWNER_HOME_TOKEN)
        self.assertEqual(readiness["fixed_input_relative_paths"], FIXED_INPUT_RELATIVE_PATHS)

        for field in (
            "execution_enabled",
            "host_wiring_enabled",
            "access_evidence_resolver_wired",
            "canary_authorized",
            "production_mutation_started",
        ):
            self.assertFalse(contract["activation"][field])
            self.assertFalse(readiness[field])

        self.assertFalse(EXECUTION_ENABLED)
        self.assertFalse(HOST_WIRING_ENABLED)
        self.assertFalse(CANARY_AUTHORIZED)
        self.assertFalse(PRODUCTION_MUTATION_STARTED)
        self.assertFalse(PARALLEL_PRIVILEGED_BROKER_ALLOWED)

    def test_identity_is_dedicated_nonlogin_nonroot_and_no_docker(self):
        validate_execution_identity(_identity())

        bad_cases = (
            _identity(username="andris"),
            _identity(username="github-runner"),
            _identity(username="root", uid=0, gid=0),
            _identity(uid=0),
            _identity(primary_group="docker"),
            _identity(home="/tmp"),
            _identity(shell="/bin/bash"),
            _identity(supplementary_groups=("docker",)),
            _identity(supplementary_groups=("adm",)),
        )
        for snapshot in bad_cases:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(HermesDealsNettoExecutionIdentityError):
                    validate_execution_identity(snapshot)

    def test_resolver_rejects_forbidden_numeric_uid_or_gid_aliases(self):
        primary = SimpleNamespace(gr_name=EXECUTION_GROUP, gr_gid=991, gr_mem=[])
        docker = SimpleNamespace(gr_name="docker", gr_gid=998, gr_mem=[])
        root = SimpleNamespace(pw_uid=0)
        owner = SimpleNamespace(pw_uid=1000)

        uid_alias_account = SimpleNamespace(
            pw_name=EXECUTION_USER,
            pw_uid=1000,
            pw_gid=991,
            pw_dir=EXECUTION_HOME,
            pw_shell=EXECUTION_SHELL,
        )

        def uid_alias_pwd(name):
            if name == EXECUTION_USER:
                return uid_alias_account
            if name == "andris":
                return owner
            if name == "root":
                return root
            raise KeyError(name)

        with (
            patch.object(execution.pwd, "getpwnam", side_effect=uid_alias_pwd),
            patch.object(execution.grp, "getgrgid", return_value=primary),
            patch.object(execution.grp, "getgrall", return_value=[primary, docker]),
            patch.object(
                execution.grp,
                "getgrnam",
                side_effect=lambda name: docker if name == "docker" else (_ for _ in ()).throw(KeyError(name)),
            ),
        ):
            with self.assertRaisesRegex(HermesDealsNettoExecutionIdentityError, "forbidden numeric UID"):
                execution.resolve_execution_identity()

        gid_alias_account = SimpleNamespace(
            pw_name=EXECUTION_USER,
            pw_uid=991,
            pw_gid=998,
            pw_dir=EXECUTION_HOME,
            pw_shell=EXECUTION_SHELL,
        )
        gid_alias_primary = SimpleNamespace(gr_name=EXECUTION_GROUP, gr_gid=998, gr_mem=[])

        def gid_alias_pwd(name):
            if name == EXECUTION_USER:
                return gid_alias_account
            if name == "andris":
                return owner
            if name == "root":
                return root
            raise KeyError(name)

        with (
            patch.object(execution.pwd, "getpwnam", side_effect=gid_alias_pwd),
            patch.object(execution.grp, "getgrgid", return_value=gid_alias_primary),
            patch.object(execution.grp, "getgrall", return_value=[gid_alias_primary, docker]),
            patch.object(
                execution.grp,
                "getgrnam",
                side_effect=lambda name: docker if name == "docker" else (_ for _ in ()).throw(KeyError(name)),
            ),
        ):
            with self.assertRaisesRegex(HermesDealsNettoExecutionIdentityError, "forbidden numeric GID"):
                execution.resolve_execution_identity()

    def test_fixed_input_access_is_minimal_and_rejects_broad_home_access(self):
        paths = [item.path for item in FIXED_INPUT_ACCESS]
        self.assertEqual(
            paths,
            [
                INPUT_OWNER_HOME_TOKEN,
                f"{INPUT_OWNER_HOME_TOKEN}/hermes-deals-audits",
                N9_ROOT,
                N9_GENERATED,
                N9_MANIFEST,
                CORPUS_PARENT,
                CORPUS_ROOT,
            ],
        )
        self.assertFalse(FIXED_INPUT_ACCESS[0].readable)
        self.assertTrue(FIXED_INPUT_ACCESS[0].executable)
        self.assertFalse(FIXED_INPUT_ACCESS[0].writable)
        self.assertTrue(FIXED_INPUT_ACCESS[-1].readable)
        self.assertTrue(FIXED_INPUT_ACCESS[-1].executable)
        self.assertFalse(any(item.writable for item in FIXED_INPUT_ACCESS))
        validate_fixed_input_access(_access())

        broad = list(_access())
        broad[0] = FixedAccessSnapshot(INPUT_OWNER_HOME_TOKEN, "directory", True, True, False)
        with self.assertRaisesRegex(HermesDealsNettoExecutionIdentityError, "input-access"):
            validate_fixed_input_access(tuple(broad))

        writable = list(_access())
        writable[-1] = FixedAccessSnapshot(CORPUS_ROOT, "directory", True, True, True)
        with self.assertRaisesRegex(HermesDealsNettoExecutionIdentityError, "input-access"):
            validate_fixed_input_access(tuple(writable))

    def test_helper_and_registration_provenance_remain_authoritative(self):
        validate_installed_provenance(_helper_snapshot(), _registration_snapshot())
        for helper in (
            _helper_snapshot(uid=1000),
            _helper_snapshot(mode=0o755),
            _helper_snapshot(link_count=2),
            _helper_snapshot(sha256="0" * 64),
            _helper_snapshot(descriptor_matches_path=False),
        ):
            with self.subTest(helper=helper):
                with self.assertRaises(HermesDealsNettoExecutionIdentityError):
                    validate_installed_provenance(helper, _registration_snapshot())

        for registration in (
            _registration_snapshot(mode=0o640),
            _registration_snapshot(sha256="0" * 64),
            _registration_snapshot(content=REGISTRATION_BYTES + b" "),
        ):
            with self.subTest(registration=registration):
                with self.assertRaises(HermesDealsNettoExecutionIdentityError):
                    validate_installed_provenance(_helper_snapshot(), registration)

    def test_launch_plan_has_no_caller_selected_process_surface(self):
        plan = fixed_launch_plan(_identity())
        self.assertEqual(plan.argv, FIXED_ARGV)
        self.assertEqual(plan.cwd, FIXED_CWD)
        self.assertEqual(dict(plan.environment), dict(FIXED_ENV))
        self.assertEqual(plan.uid, 991)
        self.assertEqual(plan.gid, 991)
        self.assertEqual(plan.extra_groups, ())
        self.assertFalse(plan.shell)
        self.assertTrue(plan.close_fds)

    def test_low_level_process_seam_remains_disabled_without_all_gates(self):
        plan = fixed_launch_plan(_identity())
        with patch.object(execution, "resolve_execution_identity") as resolver:
            with self.assertRaisesRegex(HermesDealsNettoExecutionIdentityError, "source-disabled"):
                execution._run_fixed_process(plan)
            resolver.assert_not_called()

    def test_helper_output_is_bounded_sanitized_and_identity_bound(self):
        plan = fixed_launch_plan(_identity())
        payload = validate_helper_result(plan, _valid_result())
        self.assertEqual(payload["runner_user"], EXECUTION_USER)
        self.assertEqual(payload["blocked_at"], "campaign_identity_probe_required")
        for field in (
            "sudo_used",
            "file_contents_exported",
            "parser_executed",
            "database_write_performed",
            "review_write_performed",
            "deployment_performed",
        ):
            self.assertFalse(payload[field])

        bad_identity = json.loads(_valid_result().stdout)
        bad_identity["runner_user"] = "andris"
        with self.assertRaises(HermesDealsNettoExecutionIdentityError):
            validate_helper_result(
                plan,
                FixedProcessResult(
                    0,
                    (json.dumps(bad_identity, sort_keys=True) + "\n").encode(),
                    b"",
                ),
            )

        mutation = json.loads(_valid_result().stdout)
        mutation["database_write_performed"] = True
        with self.assertRaises(HermesDealsNettoExecutionIdentityError):
            validate_helper_result(
                plan,
                FixedProcessResult(
                    0,
                    (json.dumps(mutation, sort_keys=True) + "\n").encode(),
                    b"",
                ),
            )

        incomplete_access = json.loads(_valid_result().stdout)
        incomplete_access["n9_manifest_readable"] = False
        incomplete_access["blocked_at"] = "n9_manifest_unreadable"
        with self.assertRaises(HermesDealsNettoExecutionIdentityError):
            validate_helper_result(
                plan,
                FixedProcessResult(
                    0,
                    (json.dumps(incomplete_access, sort_keys=True) + "\n").encode(),
                    b"",
                ),
            )

    def test_one_shot_consumes_before_runner_and_has_no_retry(self):
        calls = []

        def runner(plan):
            calls.append(plan)
            return _valid_result(plan.uid)

        launcher = HermesDealsNettoV2OneShotLauncher()
        with (
            patch.object(execution, "_run_fixed_process", side_effect=runner),
            patch.object(execution, "EXECUTION_ENABLED", True),
            patch.object(execution, "HOST_WIRING_ENABLED", True),
            patch.object(execution, "ACCESS_EVIDENCE_RESOLVER_WIRED", True),
            patch.object(execution, "CANARY_AUTHORIZED", True),
            patch.object(execution.os, "geteuid", return_value=0),
        ):
            receipt = launcher.launch_prevalidated(
                identity=_identity(),
                helper=_helper_snapshot(),
                registration=_registration_snapshot(),
                access=_access(),
            )
            self.assertTrue(receipt.output_validated)
            self.assertEqual(receipt.contract_id, CONTRACT_ID)
            self.assertEqual(receipt.access_contract_id, ACCESS_CONTRACT_ID)
            self.assertEqual(len(calls), 1)
            with self.assertRaisesRegex(
                HermesDealsNettoExecutionIdentityError, "budget already consumed"
            ):
                launcher.launch_prevalidated(
                    identity=_identity(),
                    helper=_helper_snapshot(),
                    registration=_registration_snapshot(),
                    access=_access(),
                )
            self.assertEqual(len(calls), 1)

    def test_source_has_no_parallel_broker_or_generic_privilege_bridge(self):
        source = SOURCE_PATH.read_text(encoding="utf-8").lower()
        for forbidden in (
            "import socket",
            "os.system",
            "shell=true",
            "bash -c",
            "sh -c",
            "eval(",
            "docker.sock",
            "systemctl",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("parallel_privileged_broker_allowed = false", source)
        self.assertIn("extra_groups=()", source)
        self.assertIn("user=plan.uid", source)
        self.assertIn("group=plan.gid", source)
        self.assertIn("resolved_identity = resolve_execution_identity()", source)
        self.assertNotIn("runner:", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
