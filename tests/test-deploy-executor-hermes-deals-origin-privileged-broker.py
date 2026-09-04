from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_origin_adapter import (
    ADAPTER_ID,
    INVOCATION_BUDGET,
    OPERATION_ID,
    PULL_HELPER_ARGUMENTS,
    PULL_HELPER_CAPABILITY,
    PULL_HELPER_SOURCE_BLOB,
    REQUIRED_DEPENDENCIES,
    REQUIRED_EXCLUSIONS,
    ROLLBACK_POLICY,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)
from deploy_executor.hermes_deals_origin_dispatch_request import SCHEMA as REQUEST_SCHEMA
from deploy_executor.hermes_deals_origin_privileged_broker import (
    BROKER_INSTALL_PATH,
    BROKER_REQUEST_MAX_BYTES,
    BROKER_SERVICE_UNIT,
    BROKER_SOCKET_PATH,
    BROKER_SOCKET_UNIT,
    HermesDealsOriginPrivilegedBrokerError,
    parse_broker_transport_request,
    prepare_hermes_deals_origin_broker_envelope,
    source_readiness,
)
from deploy_executor.hermes_deals_origin_privileged_consumer import (
    AUTHORIZATION_CLASS,
    HOST_EVIDENCE_SCHEMA,
    CanonicalHermesOriginEvidence,
)
from deploy_executor.hermes_deals_origin_privileged_dispatcher import INSTALLED_HELPER_PATH

SOURCE_SHA = "1" * 40
CURRENT_MAIN_SHA = "2" * 40
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"
AUTHORIZATION_CREATED_AT = "2026-09-04T07:26:48Z"


def canonical_evidence() -> CanonicalHermesOriginEvidence:
    return CanonicalHermesOriginEvidence(
        authorization_issue_number=17,
        authorization_created_at=AUTHORIZATION_CREATED_AT,
        request_id=REQUEST_ID,
        queue_issue=41,
        source_repository=SOURCE_REPOSITORY,
        source_sha=SOURCE_SHA,
        current_main_sha=CURRENT_MAIN_SHA,
        source_ci_run_id=9001,
        operation_id=OPERATION_ID,
        adapter_id=ADAPTER_ID,
        target_alias=TARGET_ALIAS,
        authorization_class=AUTHORIZATION_CLASS,
        ordinary_live_all_eligible=False,
        rollback_policy=ROLLBACK_POLICY,
        mutation_budget=INVOCATION_BUDGET,
        exclusions=tuple(sorted(REQUIRED_EXCLUSIONS)),
        dependencies=tuple(sorted(REQUIRED_DEPENDENCIES)),
        isolated_authorization_surface_valid=True,
        authorization_owner_verified=True,
        authorization_ttl_valid=True,
        authorization_body_unchanged=True,
        authorization_replay_available=True,
        queue_ready=True,
        queue_binding_valid=True,
        registry_execution_enabled=False,
        source_reachable_from_main=True,
        source_ci_success=True,
        baseline_matched=True,
        prepared_execution_enabled=False,
        adapter_preflight_read_only=True,
        adapter_preflight_privileged_dispatch_ready=False,
    )


def host_evidence() -> dict[str, object]:
    return {
        "schema": HOST_EVIDENCE_SCHEMA,
        "evidence_id": "host-origin-audit-readonly-1",
        "operation_id": OPERATION_ID,
        "registered_source_sha": SOURCE_SHA,
        "registration_name": "origin-path-audit",
        "registration_owner_root": True,
        "registration_mode_0600": True,
        "dispatcher_identity_match": True,
        "probe_identity_match": True,
        "workflow_identity_match": True,
        "pull_helper_identity_match": True,
        "pull_helper_interface_match": True,
        "evidence_read_only": True,
        "evidence_fresh": True,
        "protected_values_included": False,
    }


class FakeCanonicalRevalidator:
    def __init__(self):
        self.calls: list[int] = []

    def revalidate(self, authorization_issue_number: int) -> CanonicalHermesOriginEvidence:
        self.calls.append(authorization_issue_number)
        return canonical_evidence()


class FakeHostEvidenceResolver:
    def __init__(self):
        self.calls: list[str] = []

    def resolve(self, *, source_sha: str) -> dict[str, object]:
        self.calls.append(source_sha)
        return host_evidence()


def request_bytes(**extra: object) -> bytes:
    value: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "authorization_issue_number": 17,
    }
    value.update(extra)
    return (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")


class HermesDealsOriginPrivilegedBrokerTests(unittest.TestCase):
    def test_broker_composes_existing_double_revalidation_without_launch(self):
        canonical = FakeCanonicalRevalidator()
        host = FakeHostEvidenceResolver()
        envelope = prepare_hermes_deals_origin_broker_envelope(
            request_bytes(),
            canonical_revalidator=canonical,
            host_evidence_resolver=host,
        )

        self.assertEqual(canonical.calls, [17, 17])
        self.assertEqual(host.calls, [SOURCE_SHA])
        self.assertEqual(envelope.authorization_issue_number, 17)
        self.assertEqual(envelope.operation_id, OPERATION_ID)
        self.assertEqual(envelope.source_repository, SOURCE_REPOSITORY)
        self.assertEqual(envelope.capability, PULL_HELPER_CAPABILITY)
        self.assertEqual(envelope.helper_source_blob, PULL_HELPER_SOURCE_BLOB)
        self.assertEqual(envelope.installed_helper_path, INSTALLED_HELPER_PATH)
        self.assertEqual(envelope.helper_argument_names, PULL_HELPER_ARGUMENTS)
        self.assertEqual(envelope.helper_arguments, (SOURCE_SHA, "2026-09-04"))
        self.assertFalse(envelope.process_launch_implemented)
        self.assertFalse(envelope.privileged_dispatch_enabled)
        self.assertFalse(envelope.host_wiring_enabled)
        self.assertFalse(envelope.genuine_hermes_audit_authorized)
        self.assertFalse(envelope.runner_retirement_eligible)
        self.assertFalse(envelope.production_mutation_started)

    def test_transport_is_one_bounded_identity_only_frame(self):
        parsed = parse_broker_transport_request(request_bytes())
        self.assertEqual(parsed.authorization_issue_number, 17)
        for raw in (
            b"",
            request_bytes()[:-1],
            request_bytes() + b"\n",
            request_bytes().replace(b"\n", b"\r\n"),
            b"{\"schema\":\"x\",\"authorization_issue_number\":17}\n",
            b"{\"schema\":\"rozkalns.hermes-deals.origin-dispatch-request.v1\",\"authorization_issue_number\":17,\"authorization_issue_number\":18}\n",
            b"x" * (BROKER_REQUEST_MAX_BYTES + 1),
        ):
            with self.subTest(raw=raw[:80]):
                with self.assertRaises(HermesDealsOriginPrivilegedBrokerError):
                    parse_broker_transport_request(raw)

    def test_caller_cannot_add_execution_authority(self):
        for field in (
            "source_sha",
            "as_of",
            "helper_path",
            "path",
            "argv",
            "environment",
            "uid",
            "gid",
            "unit",
            "capability",
            "command",
            "shell",
            "output_path",
        ):
            canonical = FakeCanonicalRevalidator()
            host = FakeHostEvidenceResolver()
            with self.subTest(field=field):
                with self.assertRaises(HermesDealsOriginPrivilegedBrokerError):
                    prepare_hermes_deals_origin_broker_envelope(
                        request_bytes(**{field: "untrusted"}),
                        canonical_revalidator=canonical,
                        host_evidence_resolver=host,
                    )
                self.assertEqual(canonical.calls, [])
                self.assertEqual(host.calls, [])

    def test_broker_source_and_entrypoint_have_no_process_launch_surface(self):
        broker_source = (
            ROOT / "ops/lib/deploy_executor/hermes_deals_origin_privileged_broker.py"
        ).read_text(encoding="utf-8")
        entrypoint = (ROOT / "ops/bin/rozkalns-hermes-deals-origin-broker").read_text(
            encoding="utf-8"
        )
        combined = broker_source + "\n" + entrypoint
        for token in (
            "import subprocess",
            "from subprocess",
            "os.system(",
            "Popen(",
            "shell=True",
            "bash -c",
            "sh -c",
            "eval(",
            "sudo ",
            "systemctl ",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, combined)
        self.assertIn("prepare_hermes_deals_origin_privileged_dispatch(", broker_source)
        self.assertIn("SOURCE_AUTHORITY_UNPROVEN", entrypoint)

    def test_installation_manifest_tracks_365_prerequisite_and_stays_non_live(self):
        manifest = json.loads(
            (ROOT / "ops/deploy/hermes-deals-origin-broker-installation.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["issue"], 365)
        self.assertEqual(
            manifest["source_baseline"],
            "9c60248547043ee5ae7b1d0e2897fd9b8aac381a",
        )
        self.assertIsNone(manifest["eligible_source_sha"])
        self.assertEqual(
            manifest["eligible_source_sha_status"],
            "POST_MERGE_EXACT_MAIN_BIND_REQUIRED",
        )
        self.assertFalse(manifest["live_install_eligible"])
        source_auth = manifest["source_read_authority"]
        self.assertEqual(
            source_auth["status"],
            "SOURCE_COMPOSITION_IMPLEMENTED_RUNTIME_UNPROVEN",
        )
        self.assertEqual(source_auth["required_repository"], SOURCE_REPOSITORY)
        self.assertEqual(source_auth["required_repository_id"], 1317143994)
        self.assertEqual(
            source_auth["required_permissions"],
            {"actions": "read", "contents": "read"},
        )
        self.assertFalse(source_auth["permission_or_credential_mutation_authorized"])
        self.assertFalse(source_auth["runtime_credential_proven"])
        self.assertFalse(source_auth["runtime_installation_scope_proven"])
        self.assertEqual(manifest["transport"]["socket_path"], BROKER_SOCKET_PATH)
        self.assertEqual(manifest["transport"]["request_max_bytes"], BROKER_REQUEST_MAX_BYTES)
        self.assertEqual(
            manifest["reviewed_helper_dependency"]["source_blob"],
            PULL_HELPER_SOURCE_BLOB,
        )
        self.assertEqual(
            manifest["reviewed_helper_dependency"]["installed_helper_path"],
            INSTALLED_HELPER_PATH,
        )
        self.assertEqual(
            manifest["reviewed_helper_dependency"]["argument_names"],
            list(PULL_HELPER_ARGUMENTS),
        )
        self.assertEqual(manifest["service_security"]["writable_privileged_paths"], [])
        flags = manifest["source_gate_flags"]
        self.assertTrue(flags["source_auth_composition_implemented"])
        self.assertFalse(flags["source_read_authority_proven"])
        self.assertFalse(flags["concrete_canonical_revalidator_implemented"])
        self.assertTrue(flags["helper_process_launch_implemented"])
        self.assertFalse(flags["helper_process_launch_wired"])
        self.assertFalse(flags["privileged_dispatch_enabled"])
        self.assertFalse(flags["host_wiring_enabled"])
        self.assertFalse(flags["genuine_hermes_audit_authorized"])
        self.assertFalse(flags["runner_retirement_eligible"])
        self.assertFalse(flags["production_mutation_started"])

    def test_socket_and_service_are_capability_specific_and_hardened(self):
        socket_unit = (
            ROOT / "ops/systemd/rozkalns-hermes-deals-origin-broker.socket"
        ).read_text(encoding="utf-8")
        service_unit = (
            ROOT / "ops/systemd/rozkalns-hermes-deals-origin-broker@.service"
        ).read_text(encoding="utf-8")
        self.assertIn(f"ListenStream={BROKER_SOCKET_PATH}", socket_unit)
        self.assertIn("Accept=yes", socket_unit)
        self.assertIn("SocketUser=root", socket_unit)
        self.assertIn("SocketGroup=rozkalns-deploy-executor", socket_unit)
        self.assertIn("SocketMode=0660", socket_unit)
        self.assertIn("MaxConnections=1", socket_unit)
        self.assertIn(f"ExecStart={BROKER_INSTALL_PATH}", service_unit)
        self.assertIn("User=root", service_unit)
        self.assertIn("Group=root", service_unit)
        self.assertIn("StandardInput=socket", service_unit)
        self.assertIn("NoNewPrivileges=yes", service_unit)
        self.assertIn("ProtectSystem=strict", service_unit)
        self.assertIn("ProtectHome=yes", service_unit)
        self.assertIn("RestrictSUIDSGID=yes", service_unit)
        self.assertIn("MemoryDenyWriteExecute=yes", service_unit)
        self.assertIn("RestrictNamespaces=yes", service_unit)
        self.assertIn("CapabilityBoundingSet=CAP_SETUID CAP_SETGID", service_unit)
        self.assertIn("AmbientCapabilities=", service_unit)
        self.assertIn("RuntimeMaxSec=60", service_unit)
        self.assertNotIn("ReadWritePaths=", service_unit)
        self.assertNotIn("sudo", service_unit.lower())
        self.assertNotIn("systemd-run", service_unit)
        self.assertNotIn("/bin/sh", service_unit)
        self.assertNotIn("/bin/bash", service_unit)

    def test_existing_poller_and_generic_dispatcher_remain_unchanged_in_posture(self):
        poller = (ROOT / "ops/systemd/rozkalns-deploy-executor.service").read_text(
            encoding="utf-8"
        )
        generic_dispatch = (ROOT / "ops/bin/rozkalns-deploy-dispatch").read_text(
            encoding="utf-8"
        )
        self.assertIn("User=rozkalns-deploy-executor", poller)
        self.assertIn("Group=rozkalns-deploy-executor", poller)
        self.assertIn("NoNewPrivileges=true", poller)
        self.assertIn("CapabilityBoundingSet=", poller)
        self.assertNotIn("sudo", poller.lower())
        self.assertIn("DEPLOY_EXECUTOR_DISPATCH=DISABLED", generic_dispatch)
        self.assertNotIn("subprocess", generic_dispatch)

    def test_broker_source_readiness_still_requires_concrete_integration_gate(self):
        readiness = source_readiness()
        self.assertTrue(readiness["broker_boundary_implemented"])
        self.assertEqual(readiness["socket_path"], BROKER_SOCKET_PATH)
        self.assertEqual(readiness["socket_unit"], BROKER_SOCKET_UNIT)
        self.assertEqual(readiness["service_unit"], BROKER_SERVICE_UNIT)
        self.assertEqual(readiness["broker_install_path"], BROKER_INSTALL_PATH)
        self.assertEqual(readiness["caller_authority"], ("authorization_issue_number",))
        self.assertFalse(readiness["source_read_authority_proven"])
        self.assertFalse(readiness["process_launch_surface"])
        self.assertFalse(readiness["privileged_dispatch_enabled"])
        self.assertFalse(readiness["host_wiring_enabled"])
        self.assertFalse(readiness["genuine_hermes_audit_authorized"])
        self.assertFalse(readiness["runner_retirement_eligible"])
        self.assertFalse(readiness["production_mutation_started"])
        self.assertFalse(readiness["live_install_eligible"])


if __name__ == "__main__":
    unittest.main()
