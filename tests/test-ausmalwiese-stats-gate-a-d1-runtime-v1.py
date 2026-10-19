#!/usr/bin/env python3
"""Offline tests for Ausmalwiese Stats Gate A D1 runtime (#996)."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_stats_gate_a_d1_runtime_v1.py"
spec = importlib.util.spec_from_file_location("stats_gate_a_runtime_996", SOURCE)
op = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(op)


def remote():
    return {
        "schema": op.REMOTE_SCHEMA,
        "worker": op.WORKER,
        "environment": "production",
        "wrangler_version": op.WRANGLER_VERSION,
        "reviewed_source": {
            "repository": op.SOURCE_REPO,
            "commit": op.SOURCE_COMMIT,
            "worker_blob": op.WORKER_BLOB,
            "config_blob": op.CONFIG_BLOB,
            "migration_blob": op.MIGRATION_BLOB,
        },
        "latest_uploaded_version": "6477f23a-f3da-40c1-bb57-ad672561d243",
        "active_versions": [{
            "version_id": "e014e7c7-4c08-40c6-a9dd-6593b3afcf3c",
            "percentage": 100,
        }],
        "active_provenance": {
            "source": "dash",
            "last_deployed_from": "dash",
            "annotation_class": "secret_change",
        },
        "active_bindings": [
            {"name": "CF_ANALYTICS_API_TOKEN", "type": "secret_text"},
            {"name": "DB", "type": "d1"},
            {"name": "PUBLIC_ORIGIN", "type": "plain_text"},
            {"name": "RATE_LIMITER", "type": "ratelimit"},
        ],
        "d1": {
            "binding": op.DATABASE_BINDING,
            "database_name": op.DATABASE_NAME,
            "database_id": op.DATABASE_ID,
        },
    }


def before():
    return {
        "schema": op.SCHEMA,
        "database_name": op.DATABASE_NAME,
        "database_id": op.DATABASE_ID,
        "objects": {name: None for name in op.TARGETS},
    }


def after():
    return {
        "schema": op.SCHEMA,
        "database_name": op.DATABASE_NAME,
        "database_id": op.DATABASE_ID,
        "objects": copy.deepcopy(op.EXPECTED_POST),
    }


class GateARuntimeTests(unittest.TestCase):
    def test_contract_is_source_only_and_exact(self):
        data = json.loads(op.CONTRACT.read_text("utf-8"))
        op.check_contract(data)
        self.assertEqual(
            data["remote_evidence_sha256"], op.REMOTE_EVIDENCE_SHA256
        )
        self.assertEqual(data["pre_schema_sha256"], op.PRE_SCHEMA_SHA256)
        self.assertEqual(data["migration_blob"], op.MIGRATION_BLOB)
        self.assertFalse(data["actions"]["run_wrangler"])
        self.assertFalse(data["actions"]["d1_write"])
        self.assertFalse(data["actions"]["live"])
        for item in ("retry", "rollback", "cleanup", "worker-deploy"):
            self.assertIn(item, data["forbidden"])

    def test_frozen_observed_digests_match_fixtures(self):
        self.assertEqual(
            op.canonical_sha256(remote()), op.REMOTE_EVIDENCE_SHA256
        )
        self.assertEqual(
            op.canonical_sha256(before()), op.PRE_SCHEMA_SHA256
        )


    def test_runtime_checkout_repin_preserves_reviewed_evidence_digest(self):
        self.assertEqual(
            op.SOURCE_COMMIT,
            "7f07c226105e26c0ca9cf91eb150a3e8f585c5ea",
        )
        self.assertEqual(
            op.RUNTIME_SOURCE_COMMIT,
            "9a8111f19f9d82395f331ed49409af22f4765db7",
        )
        self.assertEqual(
            op.canonical_sha256(remote()), op.REMOTE_EVIDENCE_SHA256
        )

    def test_git_blob_uses_nul_separator(self):
        raw = b"x"
        expected = hashlib.sha1(b"blob 1\x00x").hexdigest()
        self.assertEqual(op.git_blob(raw), expected)

    def test_git_ls_tree_parser_accepts_real_tab(self):
        line = "100644 blob " + "a" * 40 + "\tcloudflare/stats-worker.js"
        match = op.TREE_LINE.fullmatch(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "100644")
        self.assertEqual(match.group(2), "a" * 40)
        self.assertEqual(match.group(3), "cloudflare/stats-worker.js")
        self.assertIsNone(
            op.TREE_LINE.fullmatch(
                "100644 blob " + "a" * 40 + r"\tcloudflare/stats-worker.js"
            )
        )

    def test_owner_binding_is_exact(self):
        op.validate_owner_binding(
            op.REMOTE_EVIDENCE_SHA256,
            op.PRE_SCHEMA_SHA256,
            op.MIGRATION_BLOB,
        )
        with self.assertRaisesRegex(op.Blocked, "OWNER_GATE_UNBOUND"):
            op.validate_owner_binding(
                "0" * 64, op.PRE_SCHEMA_SHA256, op.MIGRATION_BLOB
            )

    def test_schema_validators_are_fail_closed(self):
        self.assertEqual(op.validate_before_schema(before()), before())
        self.assertEqual(op.validate_after_schema(after()), after())
        bad = before()
        bad["objects"]["like_cookie_sessions"] = copy.deepcopy(
            op.EXPECTED_POST["like_cookie_sessions"]
        )
        with self.assertRaisesRegex(op.Blocked, "PRE_SCHEMA_NOT_ABSENT"):
            op.validate_before_schema(bad)

    def test_schema_reader_requires_provider_success(self):
        with mock.patch.object(
            op,
            "run_wrangler_json",
            return_value=[{"success": False, "results": []}],
        ):
            with self.assertRaisesRegex(op.Blocked, "SCHEMA_READ_1_API"):
                op.collect_schema()

    def test_mutation_command_is_one_exact_file_only_action(self):
        self.assertEqual(
            op.mutation_command(),
            [
                str(op.WRANGLER),
                "d1", "execute", "DB",
                "--remote", "--file", op.MIGRATION_PATH,
                "--yes", "--config", op.CONFIG_PATH,
            ],
        )
        joined = " ".join(op.mutation_command())
        self.assertNotIn("--command", op.mutation_command())
        self.assertNotIn("versions upload", joined)
        self.assertNotIn("versions deploy", joined)
        self.assertNotIn("stats-remove-daily-visitor-hmac", joined)

    def _wrangler_symlink_fixture(self, root: Path):
        outer = root / ".local/bin/wrangler"
        bin_dir = root / ".local/share/wrangler-cli/.bin"
        node_bin = root / ".local/share/wrangler-cli/node_modules/.bin/wrangler"
        real = (
            root
            / ".local/share/wrangler-cli/node_modules/wrangler/bin/wrangler.js"
        )
        outer.parent.mkdir(parents=True)
        node_bin.parent.mkdir(parents=True)
        real.parent.mkdir(parents=True)
        real.write_text("#!/usr/bin/env node\n", encoding="utf-8")
        real.chmod(0o700)
        bin_dir.symlink_to("node_modules/.bin")
        node_bin.symlink_to("../wrangler/bin/wrangler.js")
        outer.symlink_to("../share/wrangler-cli/.bin/wrangler")
        return outer, bin_dir, node_bin, real

    def test_wrangler_binary_accepts_only_exact_installed_symlink_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer, bin_dir, node_bin, real = self._wrangler_symlink_fixture(
                Path(tmp)
            )
            patches = (
                mock.patch.object(op, "WRANGLER", outer),
                mock.patch.object(op, "WRANGLER_BIN_DIR", bin_dir),
                mock.patch.object(op, "WRANGLER_NODE_BIN", node_bin),
                mock.patch.object(op, "WRANGLER_REAL", real),
                mock.patch.object(op, "RUNTIME_OPERATOR_UID", os.getuid()),
                mock.patch.object(op, "RUNTIME_OPERATOR_GID", os.getgid()),
            )
            with patches[0], patches[1], patches[2], patches[3], \
                 patches[4], patches[5]:
                op.wrangler_binary_trusted()

    def test_wrangler_binary_rejects_link_target_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer, bin_dir, node_bin, real = self._wrangler_symlink_fixture(
                Path(tmp)
            )
            outer.unlink()
            outer.symlink_to("../share/other/.bin/wrangler")
            with mock.patch.object(op, "WRANGLER", outer), \
                 mock.patch.object(op, "WRANGLER_BIN_DIR", bin_dir), \
                 mock.patch.object(op, "WRANGLER_NODE_BIN", node_bin), \
                 mock.patch.object(op, "WRANGLER_REAL", real), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_UID", os.getuid()), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_GID", os.getgid()):
                with self.assertRaisesRegex(
                    op.Blocked, "WRANGLER_BINARY_UNTRUSTED"
                ):
                    op.wrangler_binary_trusted()

    def test_wrangler_binary_rejects_group_writable_real_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer, bin_dir, node_bin, real = self._wrangler_symlink_fixture(
                Path(tmp)
            )
            real.chmod(0o720)
            with mock.patch.object(op, "WRANGLER", outer), \
                 mock.patch.object(op, "WRANGLER_BIN_DIR", bin_dir), \
                 mock.patch.object(op, "WRANGLER_NODE_BIN", node_bin), \
                 mock.patch.object(op, "WRANGLER_REAL", real), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_UID", os.getuid()), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_GID", os.getgid()):
                with self.assertRaisesRegex(
                    op.Blocked, "WRANGLER_BINARY_UNTRUSTED"
                ):
                    op.wrangler_binary_trusted()

    def test_subprocess_is_fixed_user_and_nolog(self):
        calls = []
        def runner(args, **kwargs):
            calls.append((list(args), kwargs))
            return SimpleNamespace(returncode=0, stdout=b"{}", stderr=b"")
        op.runtime_subprocess([str(op.WRANGLER), "noop"], runner=runner)
        argv, kwargs = calls[0]
        self.assertEqual(kwargs["user"], 1000)
        self.assertEqual(kwargs["group"], 1000)
        self.assertEqual(kwargs["extra_groups"], ())
        self.assertEqual(kwargs["env"]["WRANGLER_WRITE_LOGS"], "false")
        self.assertEqual(kwargs["env"]["WRANGLER_SEND_METRICS"], "false")
        self.assertEqual(
            kwargs["env"]["WRANGLER_LOG_PATH"], str(op.WRANGLER_LOG_PATH)
        )
        self.assertEqual(op.WRANGLER_VERSION, "4.135.0")
        self.assertEqual(op.WRANGLER_LOG_PATH.suffix, ".log")
        self.assertTrue(op.WRANGLER_LOG_PATH.name.startswith("gate-a-"))
        self.assertNotIn("WRANGLER_LOG", kwargs["env"])
        self.assertNotIn("--version", argv)

    def test_runtime_entry_requires_root(self):
        with mock.patch.object(op.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(op.Blocked, "RUNTIME_ROOT_REQUIRED"):
                op.trusted_runtime_entry()

    def test_preflight_digest_drift_blocks_before_schema_read(self):
        with mock.patch.object(op, "trusted_runtime_entry"), \
             mock.patch.object(op, "wrangler_package_version"), \
             mock.patch.object(op, "exact_application_bytes", return_value={}), \
             mock.patch.object(op, "log_snapshot", return_value=()), \
             mock.patch.object(op, "collect_remote_evidence", return_value={"bad": 1}), \
             mock.patch.object(op, "collect_schema") as schema:
            with self.assertRaisesRegex(op.Blocked, "REMOTE_EVIDENCE_DRIFT"):
                op.preflight()
        schema.assert_not_called()

    def test_preflight_log_write_blocks_before_mutation(self):
        with mock.patch.object(op, "trusted_runtime_entry"), \
             mock.patch.object(op, "wrangler_package_version"), \
             mock.patch.object(op, "exact_application_bytes", return_value={}), \
             mock.patch.object(op, "log_snapshot", side_effect=[(), (("x", 1, 1),)]), \
             mock.patch.object(op, "collect_remote_evidence", return_value=remote()), \
             mock.patch.object(op, "collect_schema", return_value=before()):
            with self.assertRaisesRegex(op.Blocked, "PREFLIGHT_LOG_WRITE"):
                op.preflight()

    def test_runtime_preflight_cli_is_read_only(self):
        expected = {
            "remote_evidence_sha256": op.REMOTE_EVIDENCE_SHA256,
            "pre_schema_sha256": op.PRE_SCHEMA_SHA256,
            "migration_blob": op.MIGRATION_BLOB,
        }
        with mock.patch.object(op, "preflight", return_value=expected) as preflight, \
             mock.patch.object(op, "execute_once") as execute, \
             mock.patch("builtins.print") as emit:
            self.assertEqual(op.main(["--runtime-preflight"]), 0)
        preflight.assert_called_once_with()
        execute.assert_not_called()
        payload = emit.call_args.args[0]
        data = json.loads(payload)
        self.assertEqual(data["status"], "PREFLIGHT_PASS")
        self.assertFalse(data["mutation_started"])
        self.assertEqual(data["remote_evidence_sha256"], op.REMOTE_EVIDENCE_SHA256)
        self.assertEqual(data["pre_schema_sha256"], op.PRE_SCHEMA_SHA256)
        self.assertEqual(data["migration_blob"], op.MIGRATION_BLOB)

    def test_runtime_preflight_rejects_mutation_arguments(self):
        with mock.patch.object(op, "preflight") as preflight, \
             mock.patch.object(op, "execute_once") as execute, \
             mock.patch("builtins.print"):
            self.assertEqual(
                op.main(["--runtime-preflight", "--confirm", "unexpected"]),
                2,
            )
        preflight.assert_not_called()
        execute.assert_not_called()

    def test_execute_dispatches_exactly_one_mutation(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(list(args))
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")
        with mock.patch.object(op, "preflight", return_value={}), \
             mock.patch.object(op, "exact_application_bytes", return_value={}), \
             mock.patch.object(op, "log_snapshot", return_value=()), \
             mock.patch.object(op, "collect_schema", return_value=after()):
            result = op.execute_once(runner=runner)
        self.assertTrue(result["mutation_started"])
        self.assertEqual(calls, [op.mutation_command()])

    def test_mutation_failure_is_terminal_no_retry(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(list(args))
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"redacted")
        with mock.patch.object(op, "preflight", return_value={}), \
             mock.patch.object(op, "exact_application_bytes", return_value={}), \
             mock.patch.object(op, "log_snapshot", return_value=()):
            with self.assertRaisesRegex(
                op.MutationUnknown, "MIGRATION_OUTCOME_UNKNOWN"
            ):
                op.execute_once(runner=runner)
        self.assertEqual(calls, [op.mutation_command()])

    def test_post_verify_failure_is_terminal_no_retry(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(list(args))
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")
        with mock.patch.object(op, "preflight", return_value={}), \
             mock.patch.object(op, "exact_application_bytes", return_value={}), \
             mock.patch.object(op, "log_snapshot", return_value=()), \
             mock.patch.object(
                 op, "collect_schema", side_effect=op.Blocked("read")
             ):
            with self.assertRaisesRegex(
                op.MutationUnknown, "POST_SCHEMA_UNVERIFIED"
            ):
                op.execute_once(runner=runner)
        self.assertEqual(calls, [op.mutation_command()])

    def test_log_write_after_mutation_is_terminal(self):
        with mock.patch.object(op, "preflight", return_value={}), \
             mock.patch.object(op, "exact_application_bytes", return_value={}), \
             mock.patch.object(
                 op, "log_snapshot",
                 side_effect=[(), (("unexpected.log", 1, 2),)]
             ), \
             mock.patch.object(
                 op,
                 "runtime_subprocess",
                 return_value=SimpleNamespace(
                     returncode=0, stdout=b"", stderr=b""
                 ),
             ):
            with self.assertRaisesRegex(
                op.MutationUnknown, "MIGRATION_LOG_WRITE_UNKNOWN"
            ):
                op.execute_once()

    def test_shared_wrangler_logs_are_not_attributed_to_this_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scoped = root / "gate-a-private.log"
            other = root / "other-process.log"
            other.write_text("not our log")
            with mock.patch.object(op, "WRANGLER_LOG_DIR", root), \
                 mock.patch.object(op, "WRANGLER_LOG_PATH", scoped), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_UID", os.getuid()), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_GID", os.getgid()):
                baseline = op.log_snapshot()
                other.write_text("independent change")
                self.assertEqual(op.log_snapshot(), baseline)
                self.assertEqual(baseline, ())

    def test_scoped_log_any_entry_blocks_without_content_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scoped = root / "gate-a-private.log"
            with mock.patch.object(op, "WRANGLER_LOG_DIR", root), \
                 mock.patch.object(op, "WRANGLER_LOG_PATH", scoped), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_UID", os.getuid()), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_GID", os.getgid()):
                self.assertEqual(op.log_snapshot(), ())
                scoped.touch()
                with self.assertRaisesRegex(op.Blocked, "SCOPED_LOG_WRITE"):
                    op.log_snapshot()
                scoped.unlink()
                scoped.symlink_to(root / "missing-target")
                with self.assertRaisesRegex(op.Blocked, "SCOPED_LOG_WRITE"):
                    op.log_snapshot()

    def test_scoped_log_missing_or_untrusted_dir_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "absent"
            with mock.patch.object(op, "WRANGLER_LOG_DIR", missing), \
                 mock.patch.object(op, "WRANGLER_LOG_PATH", missing / "gate-a-x.log"):
                with self.assertRaisesRegex(op.Blocked, "LOG_METADATA_UNAVAILABLE"):
                    op.log_snapshot()
            symlink = root / "link"
            symlink.symlink_to(root, target_is_directory=True)
            with mock.patch.object(op, "WRANGLER_LOG_DIR", symlink), \
                 mock.patch.object(op, "WRANGLER_LOG_PATH", symlink / "gate-a-x.log"):
                with self.assertRaisesRegex(op.Blocked, "LOG_DIR_UNTRUSTED"):
                    op.log_snapshot()

    def test_preflight_ignores_unrelated_log_activity_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scoped = root / "gate-a-private.log"
            with mock.patch.object(op, "WRANGLER_LOG_DIR", root), \
                 mock.patch.object(op, "WRANGLER_LOG_PATH", scoped), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_UID", os.getuid()), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_GID", os.getgid()), \
                 mock.patch.object(op, "trusted_runtime_entry"), \
                 mock.patch.object(op, "wrangler_package_version"), \
                 mock.patch.object(op, "exact_application_bytes", return_value={}), \
                 mock.patch.object(op, "collect_remote_evidence", return_value=remote()), \
                 mock.patch.object(op, "collect_schema", return_value=before()):
                state = op.preflight()
                self.assertEqual(state["migration_blob"], op.MIGRATION_BLOB)

    def test_scoped_log_after_dispatch_is_terminal_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scoped = root / "gate-a-private.log"
            count = []
            def writes_log(args, **_):
                count.append(list(args))
                scoped.touch()
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            with mock.patch.object(op, "WRANGLER_LOG_DIR", root), \
                 mock.patch.object(op, "WRANGLER_LOG_PATH", scoped), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_UID", os.getuid()), \
                 mock.patch.object(op, "RUNTIME_OPERATOR_GID", os.getgid()), \
                 mock.patch.object(op, "preflight", return_value={}), \
                 mock.patch.object(op, "exact_application_bytes", return_value={}):
                with self.assertRaisesRegex(
                    op.MutationUnknown, "MIGRATION_LOG_WRITE_UNKNOWN"
                ):
                    op.execute_once(runner=writes_log)
                self.assertEqual(count, [op.mutation_command()])

    def test_source_has_no_secret_package_or_cleanup_surface(self):
        text = SOURCE.read_text("utf-8")
        for forbidden in (
            "/etc/rpi5-secrets",
            "CLOUDFLARE_API_TOKEN",
            "npx --yes",
            "npm install",
            "stats-remove-daily-visitor-hmac.sql",
            "versions upload",
            "versions deploy",
            "shell=True",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
