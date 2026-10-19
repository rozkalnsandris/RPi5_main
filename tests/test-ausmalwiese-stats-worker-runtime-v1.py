#!/usr/bin/env python3
"""Offline regressions for #1118 Stats Worker installed deploy boundary."""
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

    def read_snapshot(self):
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
            "e6c1a4a4fa9f8a9c82dc73babd6b4a2a1bdd4d63",
        )
        self.assertEqual(
            core.SOURCE_BLOB,
            "c2ac9da6e0701103e0041b30db7dfbea4298f96c",
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

    def test_beta_version_module_proof_hashes_exact_main_module(self):
        transport = runtime.CloudflareTransport(
            "a" * 32,
            "T" * 32,
            {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32},
        )
        payload = {
            "id": OLD,
            "main_module": "stats-worker.js",
            "modules": [{
                "name": "stats-worker.js",
                "content_type": "application/javascript+module",
                "content_base64": base64.b64encode(SOURCE).decode("ascii"),
            }],
        }
        with mock.patch.object(transport, "_get", return_value=payload):
            self.assertEqual(transport._code_sha(OLD), SOURCE_SHA)

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

    def test_source_contract_keeps_live_authority_closed(self):
        contract = json.loads(
            (ROOT / "ops/contracts/ausmalwiese-stats-worker-runtime-v1.json").read_text()
        )
        self.assertEqual(contract["issue"], 1118)
        self.assertEqual(contract["parent_issue"], 996)
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
