#!/usr/bin/env python3
"""Offline tests for sanitized Stats Versions failure diagnostics (#1069)."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PARSER = ROOT / "scripts/ausmalwiese_stats_wrangler_inventory_v1.py"
RUNTIME = ROOT / "scripts/ausmalwiese_stats_wrangler_inventory_executor_v1.py"

parser_spec = importlib.util.spec_from_file_location(
    "stats_versions_diag_parser_1069", PARSER
)
plan = importlib.util.module_from_spec(parser_spec)
assert parser_spec and parser_spec.loader
parser_spec.loader.exec_module(plan)

runtime_spec = importlib.util.spec_from_file_location(
    "stats_versions_diag_runtime_1069", RUNTIME
)
runtime = importlib.util.module_from_spec(runtime_spec)
assert runtime_spec and runtime_spec.loader
runtime_spec.loader.exec_module(runtime)

SHA = "a" * 40
ACCOUNT = "0123456789abcdef0123456789abcdef"
TOKEN = "T" * 32
SECOND = "22345678-1234-4234-a234-123456789abc"

EXPECTED_MAPPING = {
    "API_ENVELOPE": "envelope",
    "API_ENVELOPE_FIELDS": "envelope",
    "API_FAILURE": "api_failure",
    "PAGINATION_MODE": "pagination",
    "PAGINATION_UNEXPECTED": "pagination",
    "VERSIONS_RESULT": "result_shape",
    "VERSIONS_COUNT": "item_count",
    "VERSION_ENTRY": "item_shape",
    "VERSION_ID": "version_id",
    "VERSION_DUPLICATE": "duplicate_id",
    "VERSION_NUMBER": "number",
    "VERSION_METADATA": "metadata",
    "VERSION_SOURCE": "source",
    "VERSION_ORDER": "order",
}


def versions():
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": {
            "items": [
                {
                    "id": plan.BASELINE_VERSION,
                    "number": 10,
                    "metadata": {"source": "api"},
                },
                {
                    "id": SECOND,
                    "number": 9,
                    "metadata": {"source": "api"},
                },
            ]
        },
    }


class VersionsDiagnosticTests(unittest.TestCase):
    def test_mapping_is_exact_bounded_allowlist(self):
        self.assertEqual(plan.VERSIONS_FAILURE_CLASS_BY_REASON, EXPECTED_MAPPING)
        self.assertEqual(
            plan.VERSIONS_DIAGNOSTIC_CLASSES,
            frozenset(set(EXPECTED_MAPPING.values()) | {"unclassified"}),
        )
        self.assertEqual(
            runtime.VERSIONS_DIAGNOSTIC_CLASSES,
            plan.VERSIONS_DIAGNOSTIC_CLASSES,
        )
        self.assertEqual(runtime.MAX_REQUESTS, 3)

    def test_every_static_parser_reason_maps_without_payload_data(self):
        for reason, expected in EXPECTED_MAPPING.items():
            with self.subTest(reason=reason), mock.patch.object(
                plan,
                "parse_versions",
                side_effect=plan.Blocked(reason),
            ):
                self.assertEqual(
                    plan.classify_versions_failure({"sensitive": "value"}),
                    expected,
                )

    def test_unknown_and_unexpected_failures_are_unclassified(self):
        with mock.patch.object(
            plan,
            "parse_versions",
            side_effect=plan.Blocked("SECRET_PROVIDER_FIELD"),
        ):
            self.assertEqual(
                plan.classify_versions_failure({"token": TOKEN}),
                "unclassified",
            )
        with mock.patch.object(
            plan,
            "parse_versions",
            side_effect=RuntimeError("TOKEN=" + TOKEN),
        ):
            self.assertEqual(
                plan.classify_versions_failure({"account": ACCOUNT}),
                "unclassified",
            )

    def test_valid_versions_contract_remains_unchanged(self):
        payload = versions()
        self.assertEqual(plan.classify_versions_failure(payload), "valid")
        version_id, source = plan.parse_versions(payload)
        self.assertEqual(version_id, plan.BASELINE_VERSION)
        self.assertEqual(source, "api")

    def test_runtime_surfaces_static_class_and_stops_before_second_get(self):
        bad = versions()
        bad["result"] = bad["result"]["items"]
        calls = []

        def fake_get(account, token, spec, decoder):
            calls.append(spec["stage"])
            return bad

        account_digest = hashlib.sha256(ACCOUNT.encode("ascii")).hexdigest()
        with mock.patch.object(runtime, "trusted_entry"), mock.patch.object(
            runtime,
            "verified_install",
            return_value=(PARSER.read_bytes(), account_digest),
        ), mock.patch.object(
            runtime,
            "checked_credential",
            return_value=(ACCOUNT, TOKEN),
        ), mock.patch.object(runtime, "single_get", side_effect=fake_get):
            with self.assertRaisesRegex(
                runtime.Stop,
                "^versions_normalization_failed_result_shape$",
            ):
                runtime.run_once(SHA, stage="before")
        self.assertEqual(calls, ["versions"])

    def test_runtime_rejects_nonallowlisted_classifier_output(self):
        loaded = runtime.load_normalizer(PARSER.read_bytes())
        loaded["parse_versions"] = mock.Mock(
            side_effect=RuntimeError("TOKEN=" + TOKEN)
        )
        loaded["classify_versions_failure"] = mock.Mock(
            return_value="TOKEN=" + TOKEN
        )
        calls = []

        def fake_get(account, token, spec, decoder):
            calls.append(spec["stage"])
            return versions()

        account_digest = hashlib.sha256(ACCOUNT.encode("ascii")).hexdigest()
        with mock.patch.object(runtime, "trusted_entry"), mock.patch.object(
            runtime,
            "verified_install",
            return_value=(PARSER.read_bytes(), account_digest),
        ), mock.patch.object(
            runtime,
            "checked_credential",
            return_value=(ACCOUNT, TOKEN),
        ), mock.patch.object(
            runtime,
            "load_normalizer",
            return_value=loaded,
        ), mock.patch.object(runtime, "single_get", side_effect=fake_get):
            with self.assertRaises(runtime.Stop) as caught:
                runtime.run_once(SHA, stage="before")
        self.assertEqual(
            str(caught.exception),
            "versions_normalization_failed_unclassified",
        )
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertNotIn(ACCOUNT, str(caught.exception))
        self.assertEqual(calls, ["versions"])

    def test_runtime_classifier_exception_is_unclassified(self):
        loaded = runtime.load_normalizer(PARSER.read_bytes())
        loaded["parse_versions"] = mock.Mock(side_effect=ValueError("sensitive"))
        loaded["classify_versions_failure"] = mock.Mock(
            side_effect=RuntimeError("TOKEN=" + TOKEN)
        )
        calls = []

        def fake_get(account, token, spec, decoder):
            calls.append(spec["stage"])
            return versions()

        account_digest = hashlib.sha256(ACCOUNT.encode("ascii")).hexdigest()
        with mock.patch.object(runtime, "trusted_entry"), mock.patch.object(
            runtime,
            "verified_install",
            return_value=(PARSER.read_bytes(), account_digest),
        ), mock.patch.object(
            runtime,
            "checked_credential",
            return_value=(ACCOUNT, TOKEN),
        ), mock.patch.object(
            runtime,
            "load_normalizer",
            return_value=loaded,
        ), mock.patch.object(runtime, "single_get", side_effect=fake_get):
            with self.assertRaisesRegex(
                runtime.Stop,
                "^versions_normalization_failed_unclassified$",
            ):
                runtime.run_once(SHA, stage="before")
        self.assertEqual(calls, ["versions"])


if __name__ == "__main__":
    unittest.main()
