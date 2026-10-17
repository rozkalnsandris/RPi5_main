#!/usr/bin/env python3
"""Offline tests for Stats Wrangler protected inventory runtime (#1056)."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "scripts/ausmalwiese_stats_wrangler_inventory_executor_v1.py"
INSTALLER = ROOT / "scripts/install-ausmalwiese-stats-wrangler-inventory-v1.py"
NORMALIZER = ROOT / "scripts/ausmalwiese_stats_wrangler_inventory_v1.py"
CONTRACT = ROOT / "ops/contracts/ausmalwiese-stats-wrangler-inventory-runtime-v1.json"

spec = importlib.util.spec_from_file_location("stats_inventory_runtime_1056", EXECUTOR)
runtime = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(runtime)

ispec = importlib.util.spec_from_file_location("stats_inventory_installer_1056", INSTALLER)
installer = importlib.util.module_from_spec(ispec)
assert ispec and ispec.loader
ispec.loader.exec_module(installer)

ACCOUNT = "a" * 32
ACCOUNT_SHA256 = hashlib.sha256(ACCOUNT.encode()).hexdigest()
TOKEN = "fixed-dummy-token-not-real-0123456789"
SHA = "b" * 40
BASELINE = "e47f145f-1851-4917-be5c-387f96549539"
SECOND = "22345678-1234-4234-a234-123456789abc"
DEPLOYMENT = "32345678-1234-4234-a234-123456789abc"


def versions():
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": {
            "items": [
                {
                    "id": BASELINE,
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


def deployments():
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": {
            "deployments": [
                {
                    "id": DEPLOYMENT,
                    "strategy": "percentage",
                    "versions": [
                        {
                            "version_id": BASELINE,
                            "percentage": 100,
                        }
                    ],
                }
            ]
        },
    }


def detail():
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": {
            "id": BASELINE,
            "number": 10,
            "metadata": {"source": "api"},
            "resources": {
                "bindings": [
                    {
                        "name": "DB",
                        "type": "d1",
                        "database_id": (
                            "f8ac8f1d-a230-4bc4-af13-557c1b91b273"
                        ),
                    },
                    {
                        "name": "RATE_LIMITER",
                        "type": "ratelimit",
                        "namespace_id": "1152026106",
                        "simple": {"limit": 100, "period": 60},
                    },
                    {
                        "name": "CF_ANALYTICS_API_TOKEN",
                        "type": "secret_text",
                    },
                    {
                        "name": "VISITOR_HMAC_KEY",
                        "type": "secret_text",
                    },
                    {
                        "name": "CF_ANALYTICS_HOST",
                        "type": "plain_text",
                        "text": "analytics.example.invalid",
                    },
                    {
                        "name": "CF_ZONE_TAG",
                        "type": "plain_text",
                        "text": "zone-source-value",
                    },
                    {
                        "name": "PUBLIC_ORIGIN",
                        "type": "plain_text",
                        "text": "https://ausmalwiese.de",
                    },
                ],
                "script": {
                    "etag": "not-a-source-proof",
                    "handlers": ["fetch"],
                    "last_deployed_from": "api",
                    "named_handlers": [],
                },
                "script_runtime": {
                    "compatibility_date": "2026-10-06T00:00:00Z",
                    "compatibility_flags": [],
                    "exports": {"default": {"type": "worker"}},
                    "limits": {"cpu_ms": 50},
                    "usage_model": "standard",
                },
            },
        },
    }


class FakeReply:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json",
        encoding: str = "identity",
        content_length: str | None = None,
    ):
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": content_type,
            "Content-Encoding": encoding,
        }
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, limit):
        return self.body[:limit]


class FakeConnection:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []
        self.closed = False

    def request(self, method, path, headers):
        self.calls.append((method, path, headers))

    def getresponse(self):
        return self.reply

    def close(self):
        self.closed = True


class RuntimeTests(unittest.TestCase):
    def test_contract_source_only(self):
        c = json.loads(CONTRACT.read_text("utf-8"))
        self.assertEqual(
            c["status"],
            "SOURCE_ONLY_PROTECTED_RUNTIME_NOT_INSTALLED",
        )
        for key in (
            "merge",
            "live",
            "host_install",
            "cloudflare_request",
            "credential_access",
            "credential_write",
            "permission_change",
            "retry",
            "rollback",
            "cleanup",
        ):
            self.assertFalse(c["actions"][key])
        self.assertEqual(c["baseline_version"], BASELINE)
        self.assertEqual(runtime.BASELINE_VERSION, BASELINE)
        self.assertEqual(c["api"]["max_requests"], 3)
        self.assertEqual(c["api"]["max_retries"], 0)
        self.assertEqual(c["api"]["max_redirects"], 0)

    def test_checkout_execution_rejected(self):
        with mock.patch.object(runtime.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(
                runtime.Stop,
                "installed_root_entry_required",
            ):
                runtime.trusted_entry()

    def test_credential_shape_and_account_fingerprint(self):
        raw = json.dumps(
            {
                "worker": runtime.WORKER,
                "account_id": ACCOUNT,
                "api_token": TOKEN,
            }
        ).encode()
        digest = hashlib.sha256(ACCOUNT.encode()).hexdigest()
        with mock.patch.object(runtime, "guarded_bytes", return_value=raw):
            self.assertEqual(
                runtime.checked_credential(digest),
                (ACCOUNT, TOKEN),
            )
            with self.assertRaisesRegex(
                runtime.Stop,
                "credential_invalid",
            ):
                runtime.checked_credential("0" * 64)

    def test_single_get_exact_https_and_no_redirect_retry(self):
        payload = versions()
        reply = FakeReply(json.dumps(payload).encode())
        conn = FakeConnection(reply)
        spec = {
            "stage": "versions",
            "method": "GET",
            "host": runtime.HOST,
            "path": (
                "/client/v4/accounts/{account_id}/workers/scripts/"
                + runtime.WORKER
                + "/versions?page=1&per_page=2"
            ),
            "max_response_bytes": runtime.MAX_RESPONSE_BYTES,
            "timeout_s": runtime.TIMEOUT_S,
            "retries": 0,
            "redirects": 0,
        }
        normalized = runtime.load_normalizer(NORMALIZER.read_bytes())
        with mock.patch.object(
            runtime,
            "ACCOUNT_SHA256",
            ACCOUNT_SHA256,
        ), mock.patch.object(
            runtime.http.client,
            "HTTPSConnection",
            return_value=conn,
        ) as http:
            out = runtime.single_get(
                ACCOUNT,
                TOKEN,
                spec,
                normalized["decode_reply"],
            )
        self.assertEqual(out, payload)
        http.assert_called_once()
        self.assertEqual(http.call_args.args[0], "api.cloudflare.com")
        self.assertEqual(http.call_args.kwargs["timeout"], 10)
        self.assertEqual(len(conn.calls), 1)
        method, path, headers = conn.calls[0]
        self.assertEqual(method, "GET")
        self.assertIn("/versions?page=1&per_page=2", path)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))
        self.assertTrue(conn.closed)

    def test_single_get_rejects_redirect_error_oversize(self):
        normalized = runtime.load_normalizer(NORMALIZER.read_bytes())
        spec = {
            "stage": "versions",
            "method": "GET",
            "host": runtime.HOST,
            "path": (
                "/client/v4/accounts/{account_id}/workers/scripts/"
                + runtime.WORKER
                + "/versions?page=1&per_page=2"
            ),
            "max_response_bytes": runtime.MAX_RESPONSE_BYTES,
            "timeout_s": runtime.TIMEOUT_S,
            "retries": 0,
            "redirects": 0,
        }
        cases = [
            FakeReply(b"{}", status=301),
            FakeReply(b"{}", status=500),
            FakeReply(
                b"{}",
                content_length=str(runtime.MAX_RESPONSE_BYTES + 1),
            ),
            FakeReply(
                b"x" * (runtime.MAX_RESPONSE_BYTES + 1),
            ),
        ]
        for reply in cases:
            with self.subTest(status=reply.status):
                conn = FakeConnection(reply)
                with mock.patch.object(
                    runtime,
                    "ACCOUNT_SHA256",
                    ACCOUNT_SHA256,
                ), mock.patch.object(
                    runtime.http.client,
                    "HTTPSConnection",
                    return_value=conn,
                ):
                    with self.assertRaises(runtime.Stop):
                        runtime.single_get(
                            ACCOUNT,
                            TOKEN,
                            spec,
                            normalized["decode_reply"],
                        )
                self.assertEqual(len(conn.calls), 1)

    def test_run_once_exact_three_stage_order_and_sanitized_output(self):
        calls = []
        payloads = [versions(), deployments(), detail()]

        def fake_get(account, token, spec, decoder):
            calls.append(spec["stage"])
            return payloads[len(calls) - 1]

        account_digest = hashlib.sha256(ACCOUNT.encode()).hexdigest()
        with mock.patch.object(runtime, "trusted_entry"), \
             mock.patch.object(
                 runtime,
                 "verified_install",
                 return_value=(NORMALIZER.read_bytes(), account_digest),
             ), \
             mock.patch.object(
                 runtime,
                 "checked_credential",
                 return_value=(ACCOUNT, TOKEN),
             ), \
             mock.patch.object(runtime, "single_get", side_effect=fake_get):
            out = runtime.run_once(SHA, stage="before")

        self.assertEqual(
            calls,
            ["versions", "deployments", "version_detail"],
        )
        self.assertEqual(
            set(out),
            {"inventory", "inventory_sha256"},
        )
        encoded = json.dumps(out, sort_keys=True)
        self.assertNotIn("analytics.example.invalid", encoded)
        self.assertNotIn("zone-source-value", encoded)
        self.assertNotIn("https://ausmalwiese.de", encoded)
        self.assertNotIn(TOKEN, encoded)
        self.assertNotIn(ACCOUNT, encoded)

    def test_versions_parse_failure_is_static_stop_before_second_get(self):
        calls = []
        bad = versions()
        bad["result"] = bad["result"]["items"]

        def fake_get(account, token, spec, decoder):
            calls.append(spec["stage"])
            return bad

        account_digest = hashlib.sha256(ACCOUNT.encode()).hexdigest()
        with mock.patch.object(runtime, "trusted_entry"), \
             mock.patch.object(
                 runtime,
                 "verified_install",
                 return_value=(NORMALIZER.read_bytes(), account_digest),
             ), \
             mock.patch.object(
                 runtime,
                 "checked_credential",
                 return_value=(ACCOUNT, TOKEN),
             ), \
             mock.patch.object(runtime, "single_get", side_effect=fake_get):
            with self.assertRaisesRegex(
                runtime.Stop,
                "versions_normalization_failed",
            ):
                runtime.run_once(SHA, stage="before")
        self.assertEqual(calls, ["versions"])

    def test_run_once_requires_stage_version_contract_before_access(self):
        with mock.patch.object(runtime, "trusted_entry") as entry, \
             mock.patch.object(runtime, "checked_credential") as credential, \
             mock.patch.object(runtime, "single_get") as get:
            with self.assertRaisesRegex(
                runtime.Stop,
                "new_version_not_allowed",
            ):
                runtime.run_once(
                    SHA,
                    stage="before",
                    new_version_id=SECOND,
                )
        entry.assert_not_called()
        credential.assert_not_called()
        get.assert_not_called()

    def test_before_rejects_consistent_wrangler_source_snapshot(self):
        v = versions()
        v["result"]["items"][0]["metadata"]["source"] = "wrangler"
        d = detail()
        d["result"]["metadata"]["source"] = "wrangler"
        d["result"]["resources"]["script"]["last_deployed_from"] = "wrangler"
        calls = []
        payloads = [v, deployments(), d]

        def fake_get(account, token, spec, decoder):
            calls.append(spec["stage"])
            return payloads[len(calls) - 1]

        account_digest = hashlib.sha256(ACCOUNT.encode()).hexdigest()
        with mock.patch.object(runtime, "trusted_entry"), \
             mock.patch.object(
                 runtime,
                 "verified_install",
                 return_value=(NORMALIZER.read_bytes(), account_digest),
             ), \
             mock.patch.object(
                 runtime,
                 "checked_credential",
                 return_value=(ACCOUNT, TOKEN),
             ), \
             mock.patch.object(runtime, "single_get", side_effect=fake_get):
            with self.assertRaisesRegex(
                runtime.Stop,
                "normalized_stage_invalid",
            ):
                runtime.run_once(SHA, stage="before")
        self.assertEqual(
            calls,
            ["versions", "deployments", "version_detail"],
        )

    def test_static_errors_do_not_echo_secret(self):
        with mock.patch.object(
            runtime,
            "ACCOUNT_SHA256",
            ACCOUNT_SHA256,
        ), mock.patch.object(
            runtime.http.client,
            "HTTPSConnection",
            side_effect=RuntimeError("TOKEN=" + TOKEN),
        ):
            spec = {
                "stage": "versions",
                "method": "GET",
                "host": runtime.HOST,
                "path": (
                    "/client/v4/accounts/{account_id}/workers/scripts/"
                    + runtime.WORKER
                    + "/versions?page=1&per_page=2"
                ),
                "max_response_bytes": runtime.MAX_RESPONSE_BYTES,
                "timeout_s": runtime.TIMEOUT_S,
                "retries": 0,
                "redirects": 0,
            }
            with self.assertRaises(runtime.Stop) as err:
                runtime.single_get(
                    ACCOUNT,
                    TOKEN,
                    spec,
                    lambda *args: {},
                )
        self.assertNotIn(TOKEN, str(err.exception))


class InstallerTests(unittest.TestCase):
    def test_release_metadata_has_hashes_no_credential(self):
        raw = installer.release_bytes(
            SHA,
            b"executor",
            b"normalizer",
            installer.ACCOUNT_SHA256,
        )
        obj = json.loads(raw)
        self.assertEqual(obj["source_sha"], SHA)
        self.assertEqual(
            obj["executor_sha256"],
            hashlib.sha256(b"executor").hexdigest(),
        )
        self.assertEqual(
            obj["normalizer_sha256"],
            hashlib.sha256(b"normalizer").hexdigest(),
        )
        self.assertNotIn(b"api_token", raw)
        self.assertNotIn(b"account_id", raw)

    def test_root_installer_checkout_forbidden(self):
        with mock.patch.object(installer.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(
                installer.Stop,
                "installer_must_be_unprivileged",
            ):
                installer.checked_checkout(SHA)

    def test_checkout_stale_dirty_wrong_branch_fail_closed(self):
        def fake_git_factory(*, head=SHA, branch="main", dirty=b""):
            def fake_git(args, **kwargs):
                key = tuple(args)
                if key == ("rev-parse", "--show-toplevel"):
                    return (str(installer.ROOT) + "\n").encode()
                if key == (
                    "symbolic-ref",
                    "--quiet",
                    "--short",
                    "HEAD",
                ):
                    return (branch + "\n").encode()
                if key == ("rev-parse", "HEAD"):
                    return (head + "\n").encode()
                if key == (
                    "status",
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=all",
                ):
                    return dirty
                if key == ("remote", "get-url", "origin"):
                    return b"https://github.com/rozkalnsandris/RPi5_main.git\n"
                raise AssertionError(args)
            return fake_git

        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            for kwargs in (
                {"head": "c" * 40},
                {"branch": "other"},
                {"dirty": b"?? file\0"},
            ):
                with self.subTest(kwargs=kwargs):
                    with mock.patch.object(
                        installer,
                        "git",
                        side_effect=fake_git_factory(**kwargs),
                    ):
                        with self.assertRaises(installer.Stop):
                            installer.checked_checkout(SHA)

    def test_existing_or_symlink_target_is_rejected(self):
        class Result:
            def __init__(self, returncode):
                self.returncode = returncode
                self.stdout = b""
                self.stderr = b""

        with mock.patch.object(
            installer,
            "invoke",
            return_value=Result(0),
        ):
            with self.assertRaisesRegex(
                installer.Stop,
                "target_already_exists",
            ):
                installer.absent(installer.EXECUTOR)

    def test_unsafe_parent_is_rejected(self):
        values = iter([
            "",
            "0:0:777:directory",
        ])

        def fake_read(cmd, **kwargs):
            return next(values)

        with mock.patch.object(installer, "sudo_read", side_effect=fake_read):
            with self.assertRaisesRegex(
                installer.Stop,
                "unsafe_parent",
            ):
                installer.roots_preflight()

    def test_apply_is_four_fixed_mutations_and_failure_is_terminal(self):
        meta = installer.release_bytes(
            SHA,
            b"executor",
            b"normalizer",
            installer.ACCOUNT_SHA256,
        )
        with mock.patch.object(
            installer,
            "preflight",
            return_value=(b"executor", b"normalizer", meta),
        ), mock.patch.object(installer, "write_once") as write, \
             mock.patch.object(installer, "post_verify"):
            installer.apply(SHA)
        self.assertEqual(write.call_count, 4)
        args = [c.args[0] for c in write.call_args_list]
        self.assertEqual(args[0][-1], installer.RELEASE_DIR)
        self.assertEqual(
            [a[-1] for a in args[1:]],
            [installer.EXECUTOR, installer.NORMALIZER, installer.RELEASE],
        )

        with mock.patch.object(
            installer,
            "preflight",
            return_value=(b"executor", b"normalizer", meta),
        ), mock.patch.object(
            installer,
            "write_once",
            side_effect=installer.Stop("post_dispatch_unknown_state"),
        ), mock.patch.object(installer, "post_verify"):
            with self.assertRaisesRegex(
                installer.Stop,
                "post_dispatch_unknown_state",
            ):
                installer.apply(SHA)

    def test_upgrade_requires_exact_old_release_and_checkout_gate(self):
        with mock.patch.object(installer, "checked_checkout") as checkout, \
             mock.patch.object(
                 installer,
                 "tracked_snapshot",
                 side_effect=[b"new-executor", b"new-normalizer", b"binding"],
             ), \
             mock.patch.object(
                 installer,
                 "approved_account_fingerprint",
                 return_value=installer.ACCOUNT_SHA256,
             ), \
             mock.patch.object(installer, "upgrade_roots_preflight") as roots:
            executor, normalizer, metadata = installer.upgrade_preflight(
                SHA,
                installer.OLD_RELEASE_SHA,
            )
        checkout.assert_called_once_with(SHA, runner=subprocess.run)
        roots.assert_called_once_with(
            installer.OLD_RELEASE_SHA,
            installer.ACCOUNT_SHA256,
            runner=subprocess.run,
        )
        self.assertEqual(executor, b"new-executor")
        self.assertEqual(normalizer, b"new-normalizer")
        self.assertEqual(json.loads(metadata)["source_sha"], SHA)

        with mock.patch.object(installer, "checked_checkout") as checkout:
            with self.assertRaisesRegex(
                installer.Stop,
                "invalid_upgrade_source",
            ):
                installer.upgrade_preflight(SHA, "c" * 40)
        checkout.assert_not_called()

    def test_upgrade_preflight_binds_old_git_release_and_target_modes(self):
        old_executor = b"old-executor"
        old_normalizer = b"old-normalizer"
        expected_release = installer.release_bytes(
            installer.OLD_RELEASE_SHA,
            old_executor,
            old_normalizer,
            installer.ACCOUNT_SHA256,
        )
        with mock.patch.object(installer, "parents_preflight"), \
             mock.patch.object(installer, "exact_target") as target, \
             mock.patch.object(
                 installer,
                 "historical_snapshot",
                 side_effect=[old_executor, old_normalizer],
             ) as history, \
             mock.patch.object(installer, "exact_digest") as digest:
            installer.upgrade_roots_preflight(
                installer.OLD_RELEASE_SHA,
                installer.ACCOUNT_SHA256,
            )

        self.assertEqual(target.call_count, 4)
        target.assert_any_call(
            installer.RELEASE_DIR,
            mode="700",
            kind="directory",
            runner=subprocess.run,
        )
        target.assert_any_call(
            installer.EXECUTOR,
            mode="500",
            kind="regular file",
            runner=subprocess.run,
        )
        target.assert_any_call(
            installer.NORMALIZER,
            mode="400",
            kind="regular file",
            runner=subprocess.run,
        )
        target.assert_any_call(
            installer.RELEASE,
            mode="400",
            kind="regular file",
            runner=subprocess.run,
        )
        self.assertEqual(history.call_count, 2)
        digest.assert_any_call(
            installer.EXECUTOR,
            old_executor,
            runner=subprocess.run,
        )
        digest.assert_any_call(
            installer.NORMALIZER,
            old_normalizer,
            runner=subprocess.run,
        )
        digest.assert_any_call(
            installer.RELEASE,
            expected_release,
            runner=subprocess.run,
        )

    def test_upgrade_target_rejects_symlink_and_metadata_drift(self):
        class Result:
            def __init__(self, returncode):
                self.returncode = returncode
                self.stdout = b""
                self.stderr = b""

        with mock.patch.object(
            installer,
            "invoke",
            return_value=Result(0),
        ):
            with self.assertRaisesRegex(
                installer.Stop,
                "upgrade_target_symlink",
            ):
                installer.exact_target(
                    installer.EXECUTOR,
                    mode="500",
                    kind="regular file",
                )

        with mock.patch.object(
            installer,
            "invoke",
            return_value=Result(1),
        ), mock.patch.object(
            installer,
            "sudo_read",
            return_value="0:0:777:regular file",
        ):
            with self.assertRaisesRegex(
                installer.Stop,
                "upgrade_target_metadata_mismatch",
            ):
                installer.exact_target(
                    installer.EXECUTOR,
                    mode="500",
                    kind="regular file",
                )

    def test_upgrade_is_three_fixed_replacements_and_failure_is_terminal(self):
        meta = installer.release_bytes(
            SHA,
            b"new-executor",
            b"new-normalizer",
            installer.ACCOUNT_SHA256,
        )
        with mock.patch.object(
            installer,
            "upgrade_preflight",
            return_value=(b"new-executor", b"new-normalizer", meta),
        ), mock.patch.object(installer, "write_once") as write, \
             mock.patch.object(installer, "post_verify") as verify:
            installer.upgrade(SHA, installer.OLD_RELEASE_SHA)

        self.assertEqual(write.call_count, 3)
        self.assertEqual(
            [c.args[0][-1] for c in write.call_args_list],
            [installer.EXECUTOR, installer.NORMALIZER, installer.RELEASE],
        )
        verify.assert_called_once()

        writes = [None, installer.Stop("post_dispatch_unknown_state")]
        with mock.patch.object(
            installer,
            "upgrade_preflight",
            return_value=(b"new-executor", b"new-normalizer", meta),
        ), mock.patch.object(
            installer,
            "write_once",
            side_effect=writes,
        ) as write, mock.patch.object(installer, "post_verify"):
            with self.assertRaisesRegex(
                installer.Stop,
                "post_dispatch_unknown_state",
            ):
                installer.upgrade(SHA, installer.OLD_RELEASE_SHA)
        self.assertEqual(write.call_count, 2)

    def test_post_verify_checks_exact_target_and_digest(self):
        payload = b"new-executor"
        checksum = hashlib.sha256(payload).hexdigest()
        with mock.patch.object(installer, "exact_target") as target, \
             mock.patch.object(
                 installer,
                 "sudo_read",
                 return_value=f"{checksum}  {installer.EXECUTOR}",
             ):
            installer.post_verify(
                ((installer.EXECUTOR, "500", payload),)
            )
        target.assert_called_once_with(
            installer.EXECUTOR,
            mode="500",
            kind="regular file",
            runner=subprocess.run,
        )

    def test_source_scope_has_no_cleanup_or_credential_write(self):
        source = INSTALLER.read_text("utf-8")
        for forbidden in (
            "/usr/bin/rm",
            "unlink(",
            "CLOUDFLARE_API_TOKEN",
            "sudoers",
            "shell=True",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn(
            str(runtime.CREDENTIAL),
            installer.TARGETS,
        )


if __name__ == "__main__":
    unittest.main()
