from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_origin_adapter import HermesDealsOriginAuditAdapter
from deploy_executor.hermes_deals_origin_dispatch_request import (
    SCHEMA,
    HermesDealsOriginDispatchRequestError,
    parse_hermes_deals_origin_dispatch_request,
    source_readiness,
)


class HermesDealsOriginDispatchRequestTests(unittest.TestCase):
    def test_exact_identity_only_request_is_accepted(self):
        request = parse_hermes_deals_origin_dispatch_request(
            {
                "schema": SCHEMA,
                "authorization_issue_number": 17,
            }
        )
        self.assertEqual(request.authorization_issue_number, 17)

    def test_extra_execution_authority_fields_are_rejected(self):
        prohibited = (
            "command",
            "shell",
            "path",
            "argv",
            "environment",
            "dispatcher_path",
            "probe_path",
            "sudo",
            "source_sha",
            "as_of",
            "artifact_dir",
            "repository_entrypoint",
            "capability",
        )
        for field in prohibited:
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    HermesDealsOriginDispatchRequestError,
                    "identity-only dispatch request shape mismatch",
                ):
                    parse_hermes_deals_origin_dispatch_request(
                        {
                            "schema": SCHEMA,
                            "authorization_issue_number": 17,
                            field: "untrusted",
                        }
                    )

    def test_invalid_identity_fails_closed(self):
        cases = (None, True, False, 0, -1, 2_147_483_648, "17", 17.0)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(HermesDealsOriginDispatchRequestError):
                    parse_hermes_deals_origin_dispatch_request(
                        {
                            "schema": SCHEMA,
                            "authorization_issue_number": value,
                        }
                    )

    def test_missing_or_wrong_schema_fails_closed(self):
        with self.assertRaises(HermesDealsOriginDispatchRequestError):
            parse_hermes_deals_origin_dispatch_request(
                {"authorization_issue_number": 17}
            )
        with self.assertRaisesRegex(
            HermesDealsOriginDispatchRequestError,
            "schema mismatch",
        ):
            parse_hermes_deals_origin_dispatch_request(
                {
                    "schema": "wrong",
                    "authorization_issue_number": 17,
                }
            )

    def test_source_readiness_claims_source_boundary_only(self):
        readiness = source_readiness()
        self.assertEqual(readiness["identity_fields"], ("authorization_issue_number",))
        self.assertTrue(readiness["privileged_dispatch_implemented"])
        self.assertFalse(readiness["privileged_dispatch_enabled"])
        self.assertFalse(readiness["host_wiring_enabled"])
        self.assertFalse(readiness["runner_retirement_eligible"])
        self.assertFalse(readiness["production_mutation_started"])
        requirements = readiness["independent_revalidation"]
        self.assertTrue(any("LIVE-AUTH" in row for row in requirements))
        self.assertTrue(any("READY queue" in row for row in requirements))
        self.assertTrue(any("exact-SHA CI" in row for row in requirements))
        self.assertTrue(any("installed helper identities" in row for row in requirements))
        self.assertTrue(any("never request prose" in row for row in requirements))

    def test_existing_adapter_remains_deliberately_non_executable(self):
        source = (
            ROOT
            / "ops"
            / "lib"
            / "deploy_executor"
            / "hermes_deals_origin_adapter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("privileged_dispatch_ready\": False", source)
        self.assertIn("execution-disabled", source)
        self.assertIn("raise AdapterError", source)
        self.assertTrue(callable(HermesDealsOriginAuditAdapter().apply))


if __name__ == "__main__":
    unittest.main()
