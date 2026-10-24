#!/usr/bin/env python3
"""Offline regressions for #1118/#1122/#1124/#1126/#1130/#1138 Stats Worker deploy boundary."""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ausmalwiese_stats_worker_exact_deploy as core
import ausmalwiese_stats_worker_runtime_v1 as runtime
import ausmalwiese_stats_worker_provisioner_v1 as provisioner
import importlib.util

_INSTALL = ROOT / "scripts/install-ausmalwiese-stats-worker-runtime-v1.py"
_spec = importlib.util.spec_from_file_location("stats_worker_installer_1118", _INSTALL)
assert _spec is not None and _spec.loader is not None
installer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(installer)


OLD = "11111111-1111-1111-1111-111111111111"
NEW = "22222222-2222-2222-2222-222222222222"
DEPLOY_OLD = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DEPLOY_NEW = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SOURCE = b"export default {fetch(){return new Response('ok')}};"
SOURCE_SHA = hashlib.sha256(SOURCE).hexdigest()
OLD_SHA = "c" * 64


def bindings():
    return {
        "DB": {"kind": "d1", "fingerprint": "1" * 64},
        "RATE_LIMITER": {"kind": "ratelimit", "fingerprint": "2" * 64},
        "PUBLIC_ORIGIN": {"kind": "plain_text", "fingerprint": "3" * 64},
        "CF_ANALYTICS_HOST": {"kind": "plain_text", "fingerprint": "4" * 64},
        "CF_ZONE_TAG": {"kind": "plain_text", "fingerprint": "5" * 64},
        "VISITOR_HMAC_KEY": {"kind": "secret_text", "fingerprint": None},
        "CF_ANALYTICS_API_TOKEN": {"kind": "secret_text", "fingerprint": None},
    }


def config():
    return {
        "compatibility_date": "2026-10-06",
        "compatibility_flags": [],
        "settings_sha256": "6" * 64,
    }


def snapshot(
    *,
    active=OLD,
    latest=OLD,
    deployment=DEPLOY_OLD,
    active_code=OLD_SHA,
    latest_code=OLD_SHA,
):
    return {
        "schema": "ausmalwiese.stats-worker-protected-inventory.v1",
        "account_sha256": core.ACCOUNT_SHA256,
        "worker": core.WORKER,
        "environment": "production",
        "active_version": active,
        "latest_uploaded_version": latest,
        "deployment_id": deployment,
        "traffic_percent": 100,
        "routes": copy.deepcopy(core.ROUTES),
        "active_bindings": bindings(),
        "latest_bindings": bindings(),
        "active_configuration": config(),
        "latest_configuration": config(),
        "active_code_sha256": active_code,
        "latest_code_sha256": latest_code,
    }


def preflight_digest(value):
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


class FakeTrusted:
    def __init__(self, states, *, upload_error=False, deploy_error=False):
        self.states = [copy.deepcopy(x) for x in states]
        self.upload_error = upload_error
        self.deploy_error = deploy_error
        self.reads = 0
        self.uploads = 0
        self.deploys = 0
        self.read_kwargs = []

    def read_snapshot(self, **kwargs):
        self.read_kwargs.append(dict(kwargs))
        value = self.states[self.reads]
        self.reads += 1
        return copy.deepcopy(value)

    def upload_version_once(self, **kwargs):
        self.uploads += 1
        if self.upload_error:
            raise RuntimeError("synthetic")
        self.upload_kwargs = kwargs
        return {"version_id": NEW}

    def deploy_version_once(self, **kwargs):
        self.deploys += 1
        if self.deploy_error:
            raise RuntimeError("synthetic")
        self.deploy_kwargs = kwargs
        return {"deployment_id": DEPLOY_NEW}


class StatsWorkerRuntimeTests(unittest.TestCase):
    def approval(self, before):
        return {
            "source_blob": core.SOURCE_BLOB,
            "config_blob": core.CONFIG_BLOB,
            "worker": core.WORKER,
            "preflight_sha256": preflight_digest(before),
            "allow_upload_once": True,
            "allow_deploy_once": True,
        }

    def test_core_repin_is_exact_current_source(self):
        self.assertEqual(
            core.SOURCE_COMMIT,
            "97741638b4cb52a3241533f30485c0e7529fdd82",
        )
        self.assertEqual(
            core.SOURCE_BLOB,
            "ccb68d7bbf12474f32e0f94d574ead1b02cd9c7e",
        )
        self.assertEqual(
            core.CONFIG_BLOB,
            "3733263a391274f2b6b0f2023c8656565bde8e1a",
        )
        self.assertEqual(core.ROUTES["ausmalwiese.de/q"], "ausmalwiese.de")
        contract = json.loads(
            (ROOT / "ops/contracts/ausmalwiese-stats-worker-exact-deploy-v1.json").read_text()
        )
        core.check_contract(contract)

    def test_core_double_read_upload_deploy_and_code_proof(self):
        before = snapshot()
        after_upload = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        after_deploy = snapshot(
            active=NEW,
            latest=NEW,
            deployment=DEPLOY_NEW,
            active_code=SOURCE_SHA,
            latest_code=SOURCE_SHA,
        )
        trusted = FakeTrusted([before, before, after_upload, after_deploy])
        with mock.patch.object(core, "verify_source"):
            result = core.future_run_once(
                trusted, self.approval(before), SOURCE
            )
        self.assertEqual(result["new_version"], NEW)
        self.assertEqual(trusted.reads, 4)
        self.assertEqual(trusted.uploads, 1)
        self.assertEqual(trusted.deploys, 1)
        self.assertEqual(trusted.upload_kwargs["bindings_inherit"], "strict")
        self.assertEqual(
            trusted.deploy_kwargs["payload"]["versions"],
            [{"version_id": NEW, "percentage": 100}],
        )

    def test_preflight_binding_drift_blocks_before_upload(self):
        before = snapshot()
        approval = self.approval(before)
        approval["preflight_sha256"] = "f" * 64
        trusted = FakeTrusted([before, before])
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(core.Blocked, "PREFLIGHT_BINDING_DRIFT"):
                core.future_run_once(trusted, approval, SOURCE)
        self.assertEqual(trusted.uploads, 0)
        self.assertEqual(trusted.deploys, 0)

    def test_route_or_configuration_drift_after_upload_blocks_deploy(self):
        before = snapshot()
        after_upload = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        after_upload["routes"]["ausmalwiese.de/q"] = "rozkalns.net"
        trusted = FakeTrusted([before, before, after_upload])
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(core.Blocked, "POST_UPLOAD_UNVERIFIED_STOP"):
                core.future_run_once(
                    trusted, self.approval(before), SOURCE
                )
        self.assertEqual(trusted.uploads, 1)
        self.assertEqual(trusted.deploys, 0)

        config_drift = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        config_drift["latest_configuration"]["settings_sha256"] = "7" * 64
        trusted = FakeTrusted([before, before, config_drift])
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(
                core.Blocked, "POST_UPLOAD_UNVERIFIED_STOP"
            ):
                core.future_run_once(
                    trusted, self.approval(before), SOURCE
                )
        self.assertEqual(trusted.uploads, 1)
        self.assertEqual(trusted.deploys, 0)

    def test_post_dispatch_failures_do_not_retry(self):
        before = snapshot()
        upload = FakeTrusted([before, before], upload_error=True)
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(core.Blocked, "UPLOAD_OUTCOME_UNKNOWN_STOP"):
                core.future_run_once(upload, self.approval(before), SOURCE)
        self.assertEqual(upload.uploads, 1)
        self.assertEqual(upload.deploys, 0)

        after_upload = snapshot(
            latest=NEW, active_code=OLD_SHA, latest_code=SOURCE_SHA
        )
        deploy = FakeTrusted(
            [before, before, after_upload], deploy_error=True
        )
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(core.Blocked, "DEPLOY_OUTCOME_UNKNOWN_STOP"):
                core.future_run_once(deploy, self.approval(before), SOURCE)
        self.assertEqual(deploy.uploads, 1)
        self.assertEqual(deploy.deploys, 1)

    def test_binding_metadata_unknown_fields_fail_closed(self):
        transport = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
        )
        resources = {
            "bindings": [
                {
                    "name": "DB",
                    "type": "d1",
                    "database_id": runtime.D1_DATABASE_ID,
                },
                {
                    "name": "RATE_LIMITER",
                    "type": "ratelimit",
                    "namespace_id": runtime.RATE_NAMESPACE_ID,
                    "simple": {
                        "limit": runtime.RATE_LIMIT,
                        "period": runtime.RATE_PERIOD,
                    },
                },
                {"name": "PUBLIC_ORIGIN", "type": "plain_text", "text": "x"},
                {"name": "CF_ANALYTICS_HOST", "type": "plain_text", "text": "y"},
                {"name": "CF_ZONE_TAG", "type": "plain_text", "text": "z"},
                {"name": "VISITOR_HMAC_KEY", "type": "secret_text"},
                {"name": "CF_ANALYTICS_API_TOKEN", "type": "secret_text"},
            ],
            "script": {"handlers": [], "named_handlers": []},
            "script_runtime": {
                "compatibility_date": runtime.COMPATIBILITY_DATE,
                "compatibility_flags": [],
            },
        }
        result = {"id": OLD, "resources": resources}
        with mock.patch.object(transport, "_get", return_value=result):
            descriptor, cfg, handlers = transport._version_metadata(OLD)
        self.assertEqual(descriptor["DB"]["kind"], "d1")
        self.assertEqual(descriptor["RATE_LIMITER"]["kind"], "ratelimit")
        self.assertEqual(cfg["compatibility_flags"], [])
        self.assertEqual(handlers, ())

        candidate_result = copy.deepcopy(result)
        candidate_result["id"] = NEW
        candidate_result["resources"]["script"]["handlers"] = [
            "scheduled", "fetch"
        ]
        with mock.patch.object(transport, "_get", return_value=candidate_result):
            _, candidate_cfg, candidate_handlers = transport._version_metadata(NEW)
        self.assertEqual(candidate_handlers, runtime.CANDIDATE_HANDLERS)
        self.assertEqual(
            candidate_cfg["settings_sha256"],
            cfg["settings_sha256"],
        )

        bad_db = copy.deepcopy(result)
        bad_db["resources"]["bindings"][0]["unexpected"] = True
        with mock.patch.object(transport, "_get", return_value=bad_db):
            with self.assertRaisesRegex(runtime.Stop, "d1_fields"):
                transport._version_metadata(OLD)

        bad_rate = copy.deepcopy(result)
        bad_rate["resources"]["bindings"][1]["simple"]["unexpected"] = True
        with mock.patch.object(transport, "_get", return_value=bad_rate):
            with self.assertRaisesRegex(runtime.Stop, "rate_identity"):
                transport._version_metadata(OLD)

    def test_candidate_handlers_are_exact_when_code_matches_reviewed_source(self):
        transport = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
            candidate_code_sha256=SOURCE_SHA,
        )

        metadata = {
            OLD: (bindings(), config(), ("fetch",)),
            NEW: (bindings(), config(), runtime.CANDIDATE_HANDLERS),
        }

        def metadata_for(version_id):
            return copy.deepcopy(metadata[version_id])

        def code_for(version_id):
            return OLD_SHA if version_id == OLD else SOURCE_SHA

        with (
            mock.patch.object(transport, "_versions", return_value=NEW),
            mock.patch.object(
                transport, "_deployment", return_value=(DEPLOY_OLD, OLD)
            ),
            mock.patch.object(
                transport, "_routes", return_value=copy.deepcopy(core.ROUTES)
            ),
            mock.patch.object(
                transport, "_version_metadata", side_effect=metadata_for
            ),
            mock.patch.object(transport, "_code_sha", side_effect=code_for),
        ):
            state = transport.read_snapshot(allow_latest_difference=True)
        self.assertEqual(state["latest_code_sha256"], SOURCE_SHA)

        metadata[NEW] = (bindings(), config(), ("fetch",))
        with (
            mock.patch.object(transport, "_versions", return_value=NEW),
            mock.patch.object(
                transport, "_deployment", return_value=(DEPLOY_OLD, OLD)
            ),
            mock.patch.object(
                transport, "_routes", return_value=copy.deepcopy(core.ROUTES)
            ),
            mock.patch.object(
                transport, "_version_metadata", side_effect=metadata_for
            ),
            mock.patch.object(transport, "_code_sha", side_effect=code_for),
        ):
            with self.assertRaisesRegex(
                runtime.Stop, "candidate_handlers_drift"
            ):
                transport.read_snapshot(allow_latest_difference=True)

    def test_beta_version_module_proof_uses_provider_declared_main_module(self):
        transport = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
        )
        payload = {
            "id": OLD,
            "main_module": "index.js",
            "modules": [
                {
                    "name": "unrelated.js",
                    "content_type": "application/javascript+module",
                    "content_base64": base64.b64encode(b"other").decode("ascii"),
                },
                {
                    "name": "index.js",
                    "content_type": "application/javascript+module",
                    "content_base64": base64.b64encode(SOURCE).decode("ascii"),
                },
            ],
        }
        with mock.patch.object(transport, "_get", return_value=payload):
            self.assertEqual(transport._code_sha(OLD), SOURCE_SHA)

    def test_beta_version_module_proof_rejects_ambiguous_or_invalid_main_module(self):
        transport = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
        )
        valid = {
            "id": OLD,
            "main_module": "index.js",
            "modules": [{
                "name": "index.js",
                "content_type": "application/javascript+module",
                "content_base64": base64.b64encode(SOURCE).decode("ascii"),
            }],
        }

        for value in (None, "", 7):
            bad = copy.deepcopy(valid)
            bad["main_module"] = value
            with mock.patch.object(transport, "_get", return_value=bad):
                with self.assertRaisesRegex(
                    runtime.Stop, "version_modules_invalid"
                ):
                    transport._code_sha(OLD)

        missing = copy.deepcopy(valid)
        missing["modules"][0]["name"] = "other.js"
        with mock.patch.object(transport, "_get", return_value=missing):
            with self.assertRaisesRegex(runtime.Stop, "main_module_ambiguous"):
                transport._code_sha(OLD)

        duplicate = copy.deepcopy(valid)
        duplicate["modules"].append(copy.deepcopy(duplicate["modules"][0]))
        with mock.patch.object(transport, "_get", return_value=duplicate):
            with self.assertRaisesRegex(runtime.Stop, "main_module_ambiguous"):
                transport._code_sha(OLD)

        bad_type = copy.deepcopy(valid)
        bad_type["modules"][0]["content_type"] = "text/plain"
        with mock.patch.object(transport, "_get", return_value=bad_type):
            with self.assertRaisesRegex(runtime.Stop, "main_module_invalid"):
                transport._code_sha(OLD)

        bad_base64 = copy.deepcopy(valid)
        bad_base64["modules"][0]["content_base64"] = "!!!"
        with mock.patch.object(transport, "_get", return_value=bad_base64):
            with self.assertRaisesRegex(
                runtime.Stop, "main_module_base64_invalid"
            ):
                transport._code_sha(OLD)

        oversized = copy.deepcopy(valid)
        oversized["modules"][0]["content_base64"] = base64.b64encode(
            b"x" * 196609
        ).decode("ascii")
        with mock.patch.object(transport, "_get", return_value=oversized):
            with self.assertRaisesRegex(runtime.Stop, "main_module_size"):
                transport._code_sha(OLD)

    def test_list_versions_uses_only_consumed_latest_fields(self):
        transport = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
        )
        payload = {
            "success": True,
            "errors": [{"code": 1000, "message": "provider decoration"}],
            "messages": [{"code": 1000, "message": "provider decoration"}],
            "unexpected_top_level": {"ignored": True},
            "result": {
                "items": [
                    {
                        "id": NEW,
                        "metadata": {"unexpected": {"deep": True}},
                        "number": -999,
                        "unexpected_item": ["ignored"],
                    },
                    {"id": "malformed-history-entry"},
                ],
                "ignored_result_field": True,
            },
            "result_info": {
                "page": 1,
                "per_page": "provider-owned",
                "count": "provider-owned",
                "total_count": -1,
                "total_pages": 999,
                "ignored": True,
            },
        }
        self.assertEqual(
            transport._latest_version_from_payload(payload), NEW
        )
        with mock.patch.object(transport, "_request", return_value=payload):
            self.assertEqual(transport._versions(), NEW)

    def test_list_versions_requires_first_uuid_and_page_one_only(self):
        transport = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
        )
        legacy = {"result": [{"id": NEW}]}
        with self.assertRaisesRegex(runtime.Stop, "versions_result_shape"):
            transport._latest_version_from_payload(legacy)

        empty = {"result": {"items": []}}
        with self.assertRaisesRegex(
            runtime.Stop, "versions_collection_shape"
        ):
            transport._latest_version_from_payload(empty)

        invalid_first = {
            "result": {"items": [{"id": "not-a-version"}, {"id": NEW}]},
        }
        with self.assertRaisesRegex(runtime.Stop, "version_id_invalid"):
            transport._latest_version_from_payload(invalid_first)

        missing_first = {
            "result": {"items": [{"number": 999}, {"id": NEW}]},
        }
        with self.assertRaisesRegex(runtime.Stop, "version_id_invalid"):
            transport._latest_version_from_payload(missing_first)

        bad_page = {
            "result": {"items": [{"id": NEW}]},
            "result_info": {
                "page": 2,
                "per_page": 100,
                "count": 1,
                "total_count": 1000,
            },
        }
        with self.assertRaisesRegex(runtime.Stop, "versions_pagination"):
            transport._latest_version_from_payload(bad_page)

        bool_page = copy.deepcopy(bad_page)
        bool_page["result_info"]["page"] = True
        with self.assertRaisesRegex(runtime.Stop, "versions_pagination"):
            transport._latest_version_from_payload(bool_page)

    def test_list_deployments_uses_only_first_active_deployment(self):
        transport = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
        )
        payload = {
            "success": True,
            "errors": [{"code": 1000, "message": "provider decoration"}],
            "messages": [{"code": 1000, "message": "provider decoration"}],
            "unexpected_top_level": True,
            "result": {
                "deployments": [
                    {
                        "id": DEPLOY_NEW,
                        "versions": [{
                            "version_id": NEW,
                            "percentage": 100,
                            "ignored": "provider-owned",
                        }],
                        "created_on": 123,
                        "source": {"ignored": True},
                        "strategy": "future-provider-value",
                        "annotations": ["ignored"],
                        "unexpected_deployment": True,
                    },
                    "malformed-history-entry",
                ],
                "ignored_result_field": True,
            },
            "result_info": {
                "page": 1,
                "per_page": "provider-owned",
                "total_pages": 999,
                "ignored": True,
            },
        }
        self.assertEqual(
            transport._latest_deployment_from_payload(payload),
            (DEPLOY_NEW, NEW),
        )
        with mock.patch.object(transport, "_request", return_value=payload):
            self.assertEqual(
                transport._deployment(), (DEPLOY_NEW, NEW)
            )

    def test_list_deployments_rejects_invalid_consumed_invariants(self):
        transport = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
        )
        base = {
            "result": {
                "deployments": [{
                    "id": DEPLOY_NEW,
                    "versions": [
                        {"percentage": 100, "version_id": NEW}
                    ],
                }]
            }
        }

        legacy = copy.deepcopy(base)
        legacy["result"] = legacy["result"]["deployments"]
        with self.assertRaisesRegex(
            runtime.Stop, "deployments_result_shape"
        ):
            transport._latest_deployment_from_payload(legacy)

        invalid_id = copy.deepcopy(base)
        invalid_id["result"]["deployments"][0]["id"] = "invalid"
        with self.assertRaisesRegex(
            runtime.Stop, "deployment_id_invalid"
        ):
            transport._latest_deployment_from_payload(invalid_id)

        split = copy.deepcopy(base)
        split["result"]["deployments"][0]["versions"] = [
            {"percentage": 50, "version_id": NEW},
            {"percentage": 50, "version_id": OLD},
        ]
        with self.assertRaisesRegex(runtime.Stop, "traffic_split"):
            transport._latest_deployment_from_payload(split)

        invalid_version = copy.deepcopy(base)
        invalid_version["result"]["deployments"][0]["versions"][0][
            "version_id"
        ] = "invalid"
        with self.assertRaisesRegex(runtime.Stop, "traffic_split"):
            transport._latest_deployment_from_payload(invalid_version)

        bool_percent = copy.deepcopy(base)
        bool_percent["result"]["deployments"][0]["versions"][0][
            "percentage"
        ] = True
        with self.assertRaisesRegex(runtime.Stop, "traffic_split"):
            transport._latest_deployment_from_payload(bool_percent)

        bad_page = copy.deepcopy(base)
        bad_page["result_info"] = {"page": 2}
        with self.assertRaisesRegex(
            runtime.Stop, "deployments_pagination"
        ):
            transport._latest_deployment_from_payload(bad_page)

    def test_preflight_is_double_read_and_sanitized(self):
        before = snapshot(active_code=SOURCE_SHA, latest_code=SOURCE_SHA)
        trusted = FakeTrusted([before, before])
        fake_core = mock.Mock()
        fake_core.validate_snapshot.side_effect = lambda x: x
        fake_core.verify_source.return_value = None
        result = runtime.preflight(fake_core, trusted, SOURCE)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(trusted.reads, 2)
        self.assertFalse(result["mutation_required"])
        self.assertEqual(result["snapshot_sha256"], preflight_digest(before))
        for forbidden in ("api_token", "account_id", "zones", "provider_body"):
            self.assertNotIn(forbidden, result)

    def test_recovery_preflight_proves_uploaded_candidate_without_ids(self):
        before = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        trusted = FakeTrusted([before, before])
        with mock.patch.object(core, "verify_source"):
            result = runtime.recovery_preflight(core, trusted, SOURCE)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["recovery_required"])
        self.assertEqual(result["provider_writes"], 0)
        self.assertEqual(result["snapshot_sha256"], preflight_digest(before))
        self.assertEqual(result["candidate_code_sha256"], SOURCE_SHA)
        self.assertEqual(trusted.uploads, 0)
        self.assertEqual(trusted.deploys, 0)
        self.assertEqual(
            trusted.read_kwargs,
            [
                {"allow_latest_difference": True},
                {"allow_latest_difference": True},
            ],
        )
        for forbidden in (
            "active_version",
            "latest_uploaded_version",
            "deployment_id",
        ):
            self.assertNotIn(forbidden, result)

    def test_recovery_preflight_rejects_wrong_or_preservation_drift(self):
        wrong = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code="d" * 64,
        )
        trusted = FakeTrusted([wrong, wrong])
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(
                runtime.Stop, "recovery_candidate_state_invalid"
            ):
                runtime.recovery_preflight(core, trusted, SOURCE)

        drift = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        drift["latest_bindings"]["PUBLIC_ORIGIN"]["fingerprint"] = "7" * 64
        trusted = FakeTrusted([drift, drift])
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(runtime.Stop, "recovery_binding_drift"):
                runtime.recovery_preflight(core, trusted, SOURCE)

        config_drift = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        config_drift["latest_configuration"]["settings_sha256"] = "7" * 64
        trusted = FakeTrusted([config_drift, config_drift])
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(
                runtime.Stop, "recovery_configuration_drift"
            ):
                runtime.recovery_preflight(core, trusted, SOURCE)

    def test_deploy_existing_reuses_candidate_without_upload(self):
        before = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        after = snapshot(
            active=NEW,
            latest=NEW,
            deployment=DEPLOY_NEW,
            active_code=SOURCE_SHA,
            latest_code=SOURCE_SHA,
        )
        trusted = FakeTrusted([before, before, after])
        with mock.patch.object(core, "verify_source"):
            result = runtime.deploy_existing(
                core,
                trusted,
                SOURCE,
                preflight_digest(before),
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["provider_writes"], 1)
        self.assertEqual(result["candidate_code_sha256"], SOURCE_SHA)
        self.assertEqual(trusted.uploads, 0)
        self.assertEqual(trusted.deploys, 1)
        self.assertEqual(
            trusted.deploy_kwargs["payload"]["versions"],
            [{"version_id": NEW, "percentage": 100}],
        )

    def test_deploy_existing_binding_drift_blocks_before_write(self):
        before = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        before["latest_bindings"]["PUBLIC_ORIGIN"]["fingerprint"] = "7" * 64
        trusted = FakeTrusted([before, before])
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(runtime.Stop, "recovery_binding_drift"):
                runtime.deploy_existing(
                    core,
                    trusted,
                    SOURCE,
                    preflight_digest(before),
                )
        self.assertEqual(trusted.uploads, 0)
        self.assertEqual(trusted.deploys, 0)

    def test_deploy_existing_snapshot_mismatch_blocks_before_write(self):
        before = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        trusted = FakeTrusted([before, before])
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(
                runtime.Stop, "recovery_snapshot_binding_drift"
            ):
                runtime.deploy_existing(
                    core,
                    trusted,
                    SOURCE,
                    "f" * 64,
                )
        self.assertEqual(trusted.uploads, 0)
        self.assertEqual(trusted.deploys, 0)

    def test_deploy_existing_dispatch_failure_never_retries(self):
        before = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        trusted = FakeTrusted([before, before], deploy_error=True)
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(
                runtime.Stop, "recovery_deploy_outcome_unknown_stop"
            ):
                runtime.deploy_existing(
                    core,
                    trusted,
                    SOURCE,
                    preflight_digest(before),
                )
        self.assertEqual(trusted.uploads, 0)
        self.assertEqual(trusted.deploys, 1)

    def test_deploy_existing_post_verify_failure_is_terminal(self):
        before = snapshot(
            latest=NEW,
            active_code=OLD_SHA,
            latest_code=SOURCE_SHA,
        )
        after = snapshot(
            active=NEW,
            latest=NEW,
            deployment=DEPLOY_NEW,
            active_code=SOURCE_SHA,
            latest_code=SOURCE_SHA,
        )
        after["routes"]["ausmalwiese.de/q"] = "rozkalns.net"
        trusted = FakeTrusted([before, before, after])
        with mock.patch.object(core, "verify_source"):
            with self.assertRaisesRegex(
                runtime.Stop, "recovery_post_deploy_outcome_unknown_stop"
            ):
                runtime.deploy_existing(
                    core,
                    trusted,
                    SOURCE,
                    preflight_digest(before),
                )
        self.assertEqual(trusted.uploads, 0)
        self.assertEqual(trusted.deploys, 1)

    def test_transport_deploy_existing_budget_is_explicit_and_one_shot(self):
        body = json.dumps({
            "success": True,
            "errors": [],
            "result": {"id": DEPLOY_NEW},
        }).encode("ascii")

        class Response:
            status = 200

            def getheader(self, name, default=None):
                if name == "Content-Encoding":
                    return "identity"
                return None

            def read(self, maximum):
                return body

        class Connection:
            def request(self, method, path, body=None, headers=None):
                return None

            def getresponse(self):
                return Response()

            def close(self):
                return None

        recovery = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
            connection_factory=lambda: Connection(),
            allow_deploy_existing=True,
        )
        result = recovery.deploy_version_once(
            payload=core.deployment_payload(NEW)
        )
        self.assertEqual(result, {"deployment_id": DEPLOY_NEW})
        self.assertEqual(recovery.uploads, 0)
        self.assertEqual(recovery.deploys, 1)
        with self.assertRaisesRegex(runtime.Stop, "deploy_budget_exhausted"):
            recovery.deploy_version_once(
                payload=core.deployment_payload(NEW)
            )
        with self.assertRaisesRegex(runtime.Stop, "upload_budget_exhausted"):
            recovery._request(
                "POST",
                "/not-dispatched",
                body=b"",
                phase="upload",
            )

        normal = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
            connection_factory=lambda: Connection(),
        )
        with self.assertRaisesRegex(runtime.Stop, "deploy_budget_exhausted"):
            normal.deploy_version_once(payload=core.deployment_payload(NEW))

    def test_provisioner_schema_and_hidden_tty_only_source(self):
        account = "a" * 32
        new_zone = "b" * 32
        old_zone = "c" * 32
        token = "T" * 32
        with mock.patch.object(
            provisioner,
            "ACCOUNT_SHA256",
            hashlib.sha256(account.encode("ascii")).hexdigest(),
        ):
            raw = provisioner.credential_bytes(
                account, new_zone, old_zone, token
            )
        self.assertEqual(
            json.loads(raw),
            {
                "worker": runtime.WORKER,
                "account_id": account,
                "api_token": token,
                "zones": {
                    "ausmalwiese.de": new_zone,
                    "rozkalns.net": old_zone,
                },
            },
        )
        source = (
            ROOT / "scripts/ausmalwiese_stats_worker_provisioner_v1.py"
        ).read_text()
        self.assertIn('os.open("/dev/tty"', source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("sys.stdin", source)

    def test_installer_release_binds_rpi5_app_worker_and_config(self):
        launcher = b"launcher"
        provision = b"provision"
        core_bytes = b"core"
        worker = b"worker"
        config_bytes = b"config"
        with (
            mock.patch.object(installer, "WORKER_BLOB", installer.git_blob(worker)),
            mock.patch.object(installer, "CONFIG_BLOB", installer.git_blob(config_bytes)),
        ):
            raw = installer.release_bytes(
                "d" * 40,
                launcher,
                provision,
                core_bytes,
                worker,
                config_bytes,
            )
        value = json.loads(raw)
        self.assertEqual(value["source_sha"], "d" * 40)
        self.assertEqual(value["app_sha"], installer.APP_SHA)
        self.assertEqual(value["app_repository"], installer.APP_REPO)
        self.assertEqual(
            value["worker_sha256"], hashlib.sha256(worker).hexdigest()
        )
        self.assertEqual(
            value["config_sha256"], hashlib.sha256(config_bytes).hexdigest()
        )

    def test_installer_upgrade_is_exact_predecessor_and_two_targets(self):
        self.assertEqual(
            installer.APP_SHA,
            "97741638b4cb52a3241533f30485c0e7529fdd82",
        )
        self.assertEqual(
            installer.APP_CHECKOUT_SHA,
            "97741638b4cb52a3241533f30485c0e7529fdd82",
        )
        self.assertEqual(installer.OLD_APP_SHA, "e6c1a4a4fa9f8a9c82dc73babd6b4a2a1bdd4d63")
        self.assertEqual(installer.OLD_WORKER_BLOB, "c2ac9da6e0701103e0041b30db7dfbea4298f96c")
        self.assertEqual(runtime.APP_SHA, installer.APP_SHA)
        self.assertEqual(provisioner.APP_SHA, installer.APP_SHA)
        self.assertEqual(core.SOURCE_COMMIT, installer.APP_SHA)
        self.assertEqual(
            installer.OLD_MAIN,
            "78e3e3aee5ef32386acc8031a955b7ddee803304",
        )
        self.assertEqual(
            installer.OLD_LAUNCHER_BLOB,
            "d64b2f330da67d9f95927d06bd1984f4aac4a343",
        )
        self.assertEqual(
            installer.OLD_RELEASE_SHA256,
            "e65d7b909482fe67629e1da0b42bc5a1b78f255397c01a789941240035b9b066",
        )
        self.assertEqual(
            installer.UPGRADE_TARGETS,
            (installer.EXE, installer.RELEASE),
        )
        source = _INSTALL.read_text("utf-8")
        self.assertIn('parser.add_argument("--upgrade-from", default="")', source)
        self.assertIn("upgrade_scope_drift", source)
        self.assertIn("sudo_exact_upgrade_not_allowed", source)
        self.assertIn("!= APP_CHECKOUT_SHA", source)

    def test_source_contract_keeps_live_authority_closed(self):
        contract = json.loads(
            (ROOT / "ops/contracts/ausmalwiese-stats-worker-runtime-v1.json").read_text()
        )
        self.assertEqual(contract["issue"], 1118)
        self.assertEqual(contract["parent_issue"], 996)
        self.assertEqual(
            contract["application_commit"],
            "97741638b4cb52a3241533f30485c0e7529fdd82",
        )
        self.assertEqual(
            contract["application_checkout_commit"],
            "97741638b4cb52a3241533f30485c0e7529fdd82",
        )
        self.assertEqual(
            contract["install"]["exact_application_main_required"],
            "97741638b4cb52a3241533f30485c0e7529fdd82",
        )
        self.assertEqual(
            contract["runtime_modes"]["apply"]["upload_writes_max"], 1
        )
        self.assertEqual(
            contract["runtime_modes"]["apply"]["deploy_writes_max"], 1
        )
        self.assertEqual(contract["runtime_modes"]["apply"]["retries"], 0)
        self.assertFalse(contract["runtime_modes"]["apply"]["rollback"])
        self.assertFalse(contract["runtime_modes"]["apply"]["cleanup"])
        self.assertFalse(contract["source_authorized_capabilities"]["live"])
        self.assertEqual(contract["upgrade_issue"], 1138)
        self.assertEqual(
            contract["runtime_modes"]["recovery_preflight"]["provider_writes"],
            0,
        )
        self.assertEqual(
            contract["read_protocol"]["source_derived_handler_contract"][
                "candidate_handlers_sorted"
            ],
            ["fetch", "scheduled"],
        )
        self.assertTrue(
            contract["runtime_modes"]["recovery_preflight"][
                "candidate_handlers_exact_required"
            ]
        )
        self.assertTrue(
            contract["runtime_modes"]["recovery_preflight"][
                "nonhandler_configuration_preserved"
            ]
        )
        self.assertEqual(
            contract["install"]["upgrade"]["predecessor_main"],
            "78e3e3aee5ef32386acc8031a955b7ddee803304",
        )
        self.assertEqual(
            contract["install"]["upgrade"]["predecessor_launcher_blob"],
            "d64b2f330da67d9f95927d06bd1984f4aac4a343",
        )
        self.assertEqual(
            contract["install"]["upgrade"]["predecessor_release_sha256"],
            "e65d7b909482fe67629e1da0b42bc5a1b78f255397c01a789941240035b9b066",
        )
        self.assertEqual(
            contract["runtime_modes"]["deploy_existing"]["upload_writes_max"],
            0,
        )
        self.assertEqual(
            contract["runtime_modes"]["deploy_existing"]["deploy_writes_max"],
            1,
        )
        self.assertFalse(
            contract["runtime_modes"]["deploy_existing"][
                "provider_version_ids_output"
            ]
        )
        self.assertEqual(
            contract["read_protocol"]["versions_result_contract"]["latest_rule"],
            "first-item-consumed-fields-only",
        )
        self.assertEqual(
            contract["read_protocol"]["deployments_result_contract"]["latest_rule"],
            "first-deployment-consumed-fields-only",
        )
        self.assertFalse(
            contract["source_authorized_capabilities"]["cloudflare_upload"]
        )
        runtime_source = (
            ROOT / "scripts/ausmalwiese_stats_worker_runtime_v1.py"
        ).read_text()
        self.assertNotIn("os.environ", runtime_source)
        self.assertNotIn("sys.stdin", runtime_source)
        self.assertIn("?include=modules", runtime_source)


if __name__ == "__main__":
    unittest.main()
