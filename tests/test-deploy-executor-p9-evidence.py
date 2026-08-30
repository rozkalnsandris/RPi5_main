from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.p9_evidence import (
    CONTROL_BASELINE_RESOLVER,
    HERMES_BASELINE_RESOLVER,
    P9EvidenceError,
    parse_governance_evidence,
    resolve_control_postcanary_baseline,
    resolve_hermes_origin_baseline,
    resolve_p9_baseline,
)

NOW = datetime(2026, 8, 28, 19, 15, tzinfo=timezone.utc)
SHA = "a" * 40
CONTROL_SHA = "f9b900a884bffda993197fc7fa9223c886e11a90"


def governance(**overrides):
    value = {
        "schema": "rozkalns.deploy-executor-p9-governance-evidence.v1",
        "repository": "rozkalnsandris/ops-workflows",
        "repository_id": 1328835922,
        "observed_at": "2026-08-28T19:14:30Z",
        "writer_set_sha256": "b" * 64,
        "trusted": True,
    }
    value.update(overrides)
    return value


def operation():
    return SimpleNamespace(
        operation_id="hermes-deals.origin-path-audit.v1",
        source_repository="rozkalnsandris/hermes-deals",
        target_alias="hermes-deals-origin-path-audit",
        baseline=SimpleNamespace(kind="resolver", resolver_id=HERMES_BASELINE_RESOLVER),
    )


def baseline(**overrides):
    value = {
        "schema": "rozkalns.deploy-executor-p9-hermes-origin-baseline.v1",
        "resolver_id": HERMES_BASELINE_RESOLVER,
        "target_alias": "hermes-deals-origin-path-audit",
        "source_repository": "rozkalnsandris/hermes-deals",
        "registered_commit_sha": SHA,
        "observed_at": "2026-08-28T19:14:30Z",
        "registration_identity_ok": True,
        "registered_source_match": True,
        "probe_identity_ok": True,
        "dispatcher_identity_ok": True,
        "workflow_identity_ok": True,
        "mutation_surface_read_only": True,
    }
    value.update(overrides)
    return value


def control_operation():
    return SimpleNamespace(
        operation_id="rozkalns-control-center.merge-postcanary-reconcile.v1",
        source_repository="rozkalnsandris/rozkalns-control-center",
        target_alias="control-center-merge-postcanary-reconcile",
        baseline=SimpleNamespace(kind="resolver", resolver_id=CONTROL_BASELINE_RESOLVER),
    )


def control_baseline(**overrides):
    value = {
        "schema": "rozkalns.deploy-executor-p9-control-postcanary-baseline.v1",
        "resolver_id": CONTROL_BASELINE_RESOLVER,
        "target_alias": "control-center-merge-postcanary-reconcile",
        "source_repository": "rozkalnsandris/rozkalns-control-center",
        "source_sha": CONTROL_SHA,
        "observed_at": "2026-08-28T19:14:30Z",
        "canary_run_terminal_failure_exact": True,
        "target_issue_exact": True,
        "target_pr_merge_evidence_exact": True,
        "target_merge_parent_exact": True,
        "target_main_descends_from_merge": True,
        "audit_row_exact": True,
        "target_audit_row_count_one": True,
        "d1_select_only_zero_write": True,
        "mutation_surface_read_only": True,
    }
    value.update(overrides)
    return value


class P9EvidenceTests(unittest.TestCase):
    def test_governance_evidence_accepts_exact_fresh_trusted_contract(self):
        result = parse_governance_evidence(governance(), server_time=NOW)
        self.assertEqual(result.repository, "rozkalnsandris/ops-workflows")
        self.assertEqual(result.repository_id, 1328835922)
        self.assertTrue(result.trusted)
        self.assertEqual(result.writer_set_sha256, "b" * 64)

    def test_governance_evidence_rejects_schema_identity_trust_and_digest_drift(self):
        cases = (
            (governance(schema="wrong"), "schema"),
            (governance(repository_id=1), "identity"),
            (governance(trusted=False), "trusted"),
            (governance(writer_set_sha256="B" * 64), "digest"),
        )
        for value, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(P9EvidenceError, error):
                parse_governance_evidence(value, server_time=NOW)

    def test_governance_evidence_rejects_missing_fields_and_stale_or_future_time(self):
        value = governance()
        value.pop("trusted")
        with self.assertRaisesRegex(P9EvidenceError, "keys mismatch"):
            parse_governance_evidence(value, server_time=NOW)
        with self.assertRaisesRegex(P9EvidenceError, "stale"):
            parse_governance_evidence(
                governance(observed_at="2026-08-28T19:00:00Z"), server_time=NOW
            )
        with self.assertRaisesRegex(P9EvidenceError, "future"):
            parse_governance_evidence(
                governance(observed_at="2026-08-28T19:15:01Z"), server_time=NOW
            )

    def test_governance_evidence_rejects_noncanonical_rfc3339_utc_shapes(self):
        for observed_at in (
            "2026-08-28Z",
            "2026-08-28 19:14:30Z",
            "2026-08-28T19:14Z",
            "2026-08-28T19:14:30+00:00",
        ):
            with self.subTest(observed_at=observed_at), self.assertRaisesRegex(
                P9EvidenceError, "canonical RFC3339 UTC"
            ):
                parse_governance_evidence(
                    governance(observed_at=observed_at), server_time=NOW
                )

    def test_hermes_baseline_accepts_only_exact_authorized_source_and_safety_attestation(self):
        result = resolve_hermes_origin_baseline(
            operation(),
            {"kind": "resolver", "value": HERMES_BASELINE_RESOLVER},
            evidence=baseline(),
            source_sha=SHA,
            server_time=NOW,
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.resolver_id, HERMES_BASELINE_RESOLVER)
        self.assertEqual(result.target_alias, "hermes-deals-origin-path-audit")
        self.assertRegex(result.evidence_id, r"^sha256:[0-9a-f]{64}$")

    def test_hermes_baseline_rejects_wrong_operation_or_live_auth_resolver(self):
        wrong = operation()
        wrong.operation_id = "other"
        with self.assertRaisesRegex(P9EvidenceError, "wrong operation"):
            resolve_hermes_origin_baseline(
                wrong,
                {"kind": "resolver", "value": HERMES_BASELINE_RESOLVER},
                evidence=baseline(),
                source_sha=SHA,
                server_time=NOW,
            )
        with self.assertRaisesRegex(P9EvidenceError, "expected_baseline"):
            resolve_hermes_origin_baseline(
                operation(),
                {"kind": "resolver", "value": "other"},
                evidence=baseline(),
                source_sha=SHA,
                server_time=NOW,
            )

    def test_hermes_baseline_rejects_source_drift_missing_or_false_safety_assertions(self):
        with self.assertRaisesRegex(P9EvidenceError, "authorized source SHA"):
            resolve_hermes_origin_baseline(
                operation(),
                {"kind": "resolver", "value": HERMES_BASELINE_RESOLVER},
                evidence=baseline(registered_commit_sha="c" * 40),
                source_sha=SHA,
                server_time=NOW,
            )
        for flag in (
            "registration_identity_ok",
            "registered_source_match",
            "probe_identity_ok",
            "dispatcher_identity_ok",
            "workflow_identity_ok",
            "mutation_surface_read_only",
        ):
            with self.subTest(flag=flag), self.assertRaisesRegex(P9EvidenceError, flag):
                resolve_hermes_origin_baseline(
                    operation(),
                    {"kind": "resolver", "value": HERMES_BASELINE_RESOLVER},
                    evidence=baseline(**{flag: False}),
                    source_sha=SHA,
                    server_time=NOW,
                )
        missing = baseline()
        missing.pop("probe_identity_ok")
        with self.assertRaisesRegex(P9EvidenceError, "keys mismatch"):
            resolve_hermes_origin_baseline(
                operation(),
                {"kind": "resolver", "value": HERMES_BASELINE_RESOLVER},
                evidence=missing,
                source_sha=SHA,
                server_time=NOW,
            )

    def test_hermes_baseline_rejects_stale_future_and_noncanonical_evidence_time(self):
        cases = (
            ("2026-08-28T19:00:00Z", "stale"),
            ("2026-08-28T19:15:01Z", "future"),
            ("2026-08-28T19:14:30+00:00", "canonical RFC3339 UTC"),
            ("2026-08-28 19:14:30Z", "canonical RFC3339 UTC"),
            ("2026-08-28T19:14Z", "canonical RFC3339 UTC"),
        )
        for observed_at, error in cases:
            with self.subTest(observed_at=observed_at), self.assertRaisesRegex(
                P9EvidenceError, error
            ):
                resolve_hermes_origin_baseline(
                    operation(),
                    {"kind": "resolver", "value": HERMES_BASELINE_RESOLVER},
                    evidence=baseline(observed_at=observed_at),
                    source_sha=SHA,
                    server_time=NOW,
                )

    def test_control_baseline_accepts_exact_fresh_operation_specific_evidence(self):
        result = resolve_control_postcanary_baseline(
            control_operation(),
            {"kind": "resolver", "value": CONTROL_BASELINE_RESOLVER},
            evidence=control_baseline(),
            source_sha=CONTROL_SHA,
            server_time=NOW,
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.resolver_id, CONTROL_BASELINE_RESOLVER)
        self.assertEqual(result.target_alias, "control-center-merge-postcanary-reconcile")
        self.assertRegex(result.evidence_id, r"^sha256:[0-9a-f]{64}$")

    def test_control_baseline_rejects_live_auth_source_and_safety_drift(self):
        with self.assertRaisesRegex(P9EvidenceError, "expected_baseline"):
            resolve_control_postcanary_baseline(
                control_operation(),
                {"kind": "resolver", "value": "other"},
                evidence=control_baseline(),
                source_sha=CONTROL_SHA,
                server_time=NOW,
            )
        with self.assertRaisesRegex(P9EvidenceError, "authorized source SHA"):
            resolve_control_postcanary_baseline(
                control_operation(),
                {"kind": "resolver", "value": CONTROL_BASELINE_RESOLVER},
                evidence=control_baseline(source_sha="c" * 40),
                source_sha=CONTROL_SHA,
                server_time=NOW,
            )
        for flag in (
            "canary_run_terminal_failure_exact",
            "target_issue_exact",
            "target_pr_merge_evidence_exact",
            "target_merge_parent_exact",
            "target_main_descends_from_merge",
            "audit_row_exact",
            "target_audit_row_count_one",
            "d1_select_only_zero_write",
            "mutation_surface_read_only",
        ):
            with self.subTest(flag=flag), self.assertRaisesRegex(P9EvidenceError, flag):
                resolve_control_postcanary_baseline(
                    control_operation(),
                    {"kind": "resolver", "value": CONTROL_BASELINE_RESOLVER},
                    evidence=control_baseline(**{flag: False}),
                    source_sha=CONTROL_SHA,
                    server_time=NOW,
                )

    def test_control_baseline_rejects_missing_stale_and_noncanonical_evidence(self):
        missing = control_baseline()
        missing.pop("audit_row_exact")
        with self.assertRaisesRegex(P9EvidenceError, "keys mismatch"):
            resolve_control_postcanary_baseline(
                control_operation(),
                {"kind": "resolver", "value": CONTROL_BASELINE_RESOLVER},
                evidence=missing,
                source_sha=CONTROL_SHA,
                server_time=NOW,
            )
        for observed_at, error in (
            ("2026-08-28T19:00:00Z", "stale"),
            ("2026-08-28T19:15:01Z", "future"),
            ("2026-08-28T19:14:30+00:00", "canonical RFC3339 UTC"),
        ):
            with self.subTest(observed_at=observed_at), self.assertRaisesRegex(
                P9EvidenceError, error
            ):
                resolve_control_postcanary_baseline(
                    control_operation(),
                    {"kind": "resolver", "value": CONTROL_BASELINE_RESOLVER},
                    evidence=control_baseline(observed_at=observed_at),
                    source_sha=CONTROL_SHA,
                    server_time=NOW,
                )

    def test_canonical_resolver_dispatches_control_and_fails_closed_unknown(self):
        result = resolve_p9_baseline(
            control_operation(),
            {"kind": "resolver", "value": CONTROL_BASELINE_RESOLVER},
            evidence=control_baseline(),
            source_sha=CONTROL_SHA,
            server_time=NOW,
        )
        self.assertEqual(result.resolver_id, CONTROL_BASELINE_RESOLVER)

        unknown = control_operation()
        unknown.baseline = SimpleNamespace(kind="resolver", resolver_id="unknown")
        with self.assertRaisesRegex(P9EvidenceError, "not allowlisted"):
            resolve_p9_baseline(
                unknown,
                {"kind": "resolver", "value": "unknown"},
                evidence=control_baseline(),
                source_sha=CONTROL_SHA,
                server_time=NOW,
            )


if __name__ == "__main__":
    unittest.main()
