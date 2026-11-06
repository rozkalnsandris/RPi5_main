#!/usr/bin/env python3
"""Disconnected synthetic adversarial handoff tests. No real host or provider."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ausmalwiese_goatcounter_simple_preflight_handoff_v1 as m

SOURCE = "a" * 40
CANARY = "PRIVATE_TOKEN_OR_DB_ROW_CANARY"


def inputs():
    return {path: ("safe source " + name + "\n").encode()
            for name, path in m.MODULE_SOURCE.items()}


def positive():
    return ("PASS_EDGE_SOURCE_ONLY", {
        "remote_tunnel": "verified_exact_config",
        "routes": {
            "ausmalwiese.de": "absent_safe_before_app_catchall",
            "www.ausmalwiese.de": "absent_safe_before_app_catchall",
        },
        "worker_routes": "verified_no_count_interception",
        "worker_custom_domains": "verified_no_count_interception",
    })


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.sources = inputs()
        self.manifest = m.plan_source_release(
            source_sha=SOURCE, source_bytes=self.sources)
        self.assertIsNotNone(self.manifest)

    def verdict(self, **overrides):
        values = dict(manifest=self.manifest, source_sha=SOURCE,
                      collect_status="COLLECT_CANDIDATE_130",
                      cloudflare_result=positive())
        values.update(overrides)
        value = m.inspect_offline(**values)
        self.assertEqual(set(value), {
            "schema_version", "status", "source_only", "live_verified"})
        self.assertEqual(value["source_only"], True)
        self.assertEqual(value["live_verified"], False)
        self.assertNotIn(CANARY, json.dumps(value))
        return value["status"]

    def test_manifest_is_exact_stable_offline_digest_inventory(self):
        self.assertEqual(self.manifest["deployable"], False)
        self.assertEqual(set(self.manifest["sha256"]), set(m.MODULE_SOURCE))
        self.assertEqual(self.manifest["source_sha"], SOURCE)
        self.assertEqual(self.manifest, m.plan_source_release(
            source_sha=SOURCE, source_bytes=dict(reversed(
                list(self.sources.items())))))
        for name, path in m.MODULE_SOURCE.items():
            self.assertEqual(self.manifest["sha256"][name],
                             hashlib.sha256(self.sources[path]).hexdigest())

    def test_offline_positive_never_authorizes_live(self):
        self.assertEqual(self.verdict(), "PASS_OFFLINE_SHAPE_ONLY")

    def test_disabled_and_unknown_collect_stop(self):
        self.assertEqual(self.verdict(
            collect_status="COLLECT_DISABLED_1"), "STOP_COLLECT_DISABLED")
        for value in (None, 130, "130", "STOP_DB_READ", CANARY,
                      ["COLLECT_CANDIDATE_130"]):
            with self.subTest(value=type(value).__name__):
                self.assertEqual(self.verdict(collect_status=value),
                                 "STOP_COLLECT_UNVERIFIED")

    def test_incomplete_or_ambiguous_cloudflare_stop(self):
        for value in (None, CANARY, (CANARY, None),
                      ("PASS_EDGE_SOURCE_ONLY", None),
                      ("PASS_EDGE_SOURCE_ONLY", {}),
                      ["PASS_EDGE_SOURCE_ONLY", positive()[1]],
                      ("STOP_ROUTE", {"canary": CANARY})):
            with self.subTest(shape=type(value).__name__):
                self.assertEqual(self.verdict(cloudflare_result=value),
                                 "STOP_EDGE_UNVERIFIED")

    def test_route_and_worker_interception_stop(self):
        for field, value in [
            ("worker_routes", "ambiguous"),
            ("worker_custom_domains", "ambiguous"),
            ("remote_tunnel", "different"),
            ("routes", {"ausmalwiese.de": "other"}),
        ]:
            with self.subTest(field=field):
                edge = positive()[1]
                edge[field] = value
                self.assertEqual(
                    self.verdict(cloudflare_result=("PASS_EDGE_SOURCE_ONLY", edge)),
                    "STOP_EDGE_UNVERIFIED")

    def test_malformed_manifest_and_sha_never_echo(self):
        for value in (None, {}, {**self.manifest, "secret": CANARY},
                      {**self.manifest, "source_sha": "z" * 40},
                      {**self.manifest, "deployable": True},
                      {**self.manifest, "sha256": {"secret": CANARY}}):
            with self.subTest(shape=type(value).__name__):
                self.assertEqual(self.verdict(manifest=value),
                                 "STOP_UNVERIFIED")
        self.assertEqual(self.verdict(source_sha="invalid"),
                         "STOP_UNVERIFIED")

    def test_manifest_rejects_extra_missing_unexpected_bytes(self):
        for value in ({}, {**self.sources, "extra": CANARY.encode()},
                      {k: v for k, v in self.sources.items()
                       if k != next(iter(self.sources))},
                      {**self.sources,
                       next(iter(self.sources)): CANARY}):
            with self.subTest(length=len(value)):
                self.assertIsNone(m.plan_source_release(
                    source_sha=SOURCE, source_bytes=value))

    def test_manifest_rejects_invalid_sha_and_oversized_module(self):
        for sha in ("", "F" * 40, "a" * 39, None):
            self.assertIsNone(m.plan_source_release(
                source_sha=sha, source_bytes=self.sources))
        for payload in (b"", b"x" * 196609):
            self.assertIsNone(m.plan_source_release(
                source_sha=SOURCE,
                source_bytes={**self.sources,
                              next(iter(self.sources)): payload}))

    def test_no_host_database_or_cloudflare_access(self):
        with patch.object(Path, "open", side_effect=AssertionError("file I/O")), \
             patch.object(Path, "read_bytes",
                          side_effect=AssertionError("file I/O")):
            self.assertIsNotNone(m.plan_source_release(
                source_sha=SOURCE, source_bytes=self.sources))
            self.assertEqual(self.verdict(), "PASS_OFFLINE_SHAPE_ONLY")

    def test_output_never_reflects_sensitive_upstream_data(self):
        private = {
            "auth": CANARY, "account_id": CANARY,
            "db": CANARY, "headers": {"CF-Connecting-IP": CANARY},
        }
        self.assertEqual(self.verdict(
            cloudflare_result=("PASS_EDGE_SOURCE_ONLY", private)),
            "STOP_EDGE_UNVERIFIED")
        self.assertEqual(self.verdict(collect_status=CANARY),
                         "STOP_COLLECT_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
