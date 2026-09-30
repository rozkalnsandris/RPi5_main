#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import inspect
import os
from pathlib import Path
from types import SimpleNamespace
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_installer_boundary_bootstrap_reconcile as reconcile
from deploy_executor import weather_private_installer_boundary_bootstrap_reconcile_runtime as runtime

DISPATCH = ROOT / "ops/lib/deploy_executor/weather_private_privileged_dispatch.py"
WORKFLOW = ROOT / ".github/workflows/weathernext-private-installer-boundary-bootstrap-reconcile-source.yml"


class FakePublicClient:
    def __init__(self, *, source_sha: str, raw: bytes, mode: str = "100755", tree_blob: str | None = None, contents_blob: str | None = None):
        self.source_sha = source_sha
        self.raw = raw
        self.tree_sha = "b" * 40
        self.blob = runtime._git_blob_sha1(raw)
        self.mode = mode
        self.tree_blob = tree_blob or self.blob
        self.contents_blob = contents_blob or self.blob

    def get_json(self, path: str):
        if path == f"/repos/{reconcile.SOURCE_REPOSITORY}/git/commits/{self.source_sha}":
            value = {"sha": self.source_sha, "tree": {"sha": self.tree_sha}}
        elif path == f"/repos/{reconcile.SOURCE_REPOSITORY}/git/trees/{self.tree_sha}?recursive=1":
            value = {
                "truncated": False,
                "tree": [
                    {
                        "path": reconcile.SOURCE_PATH,
                        "type": "blob",
                        "mode": self.mode,
                        "sha": self.tree_blob,
                    }
                ],
            }
        elif path == f"/repos/{reconcile.SOURCE_REPOSITORY}/contents/{reconcile.SOURCE_PATH}?ref={self.source_sha}":
            value = {
                "type": "file",
                "path": reconcile.SOURCE_PATH,
                "sha": self.contents_blob,
                "encoding": "base64",
                "content": base64.b64encode(self.raw).decode("ascii"),
            }
        else:
            raise AssertionError(f"unexpected public GitHub path: {path}")
        return SimpleNamespace(value=value)


class FakeReplay:
    def __init__(self):
        self.events: list[str] = []

    def consume(self, request_id: str):
        self.events.append(f"consume:{request_id}")

    def mark_succeeded(self, request_id: str):
        self.events.append(f"succeeded:{request_id}")


def plan_for(raw: bytes, *, installed_sha256: str):
    return reconcile.build_reconcile_plan(
        reconcile.BootstrapEvidence(
            exact_source_sha="a" * 40,
            current_main_sha="a" * 40,
            exact_main_ci_success=True,
            source_git_mode=reconcile.SOURCE_GIT_MODE,
            source_git_blob=runtime._git_blob_sha1(raw),
            source_sha256=hashlib.sha256(raw).hexdigest(),
            installed_is_regular=True,
            installed_uid=reconcile.ROOT_UID,
            installed_gid=reconcile.ROOT_GID,
            installed_mode=reconcile.DESTINATION_MODE,
            installed_nlink=1,
            installed_sha256=installed_sha256,
        )
    )


def canonical(plan, installed_sha256: str):
    return runtime.CanonicalEvidence(
        authorization_issue_number=1,
        authorization_issue_id=2,
        request_id="request-1",
        request_body_sha256="d" * 64,
        queue_issue_number=3,
        source_sha=plan.source_sha,
        installed_sha256=installed_sha256,
        plan=reconcile.public_plan(plan),
    )


class WeatherNextBootstrapReconcileRuntimeTests(unittest.TestCase):
    def test_reviewed_source_derives_executable_blob_and_digest_from_exact_main(self) -> None:
        raw = b"#!/usr/bin/env python3\nprint('reviewed')\n"
        client = FakePublicClient(source_sha="a" * 40, raw=raw)
        blob, digest, observed = runtime._reviewed_source(client, "a" * 40)
        self.assertEqual(blob, runtime._git_blob_sha1(raw))
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        self.assertEqual(observed, raw)

    def test_reviewed_source_rejects_wrong_git_mode_or_blob(self) -> None:
        raw = b"#!/usr/bin/env python3\nprint('reviewed')\n"
        cases = (
            FakePublicClient(source_sha="a" * 40, raw=raw, mode="100644"),
            FakePublicClient(source_sha="a" * 40, raw=raw, tree_blob="c" * 40),
            FakePublicClient(source_sha="a" * 40, raw=raw, contents_blob="c" * 40),
        )
        for client in cases:
            with self.subTest(mode=client.mode, tree_blob=client.tree_blob, contents_blob=client.contents_blob):
                with self.assertRaises(runtime.BootstrapReconcileRuntimeError):
                    runtime._reviewed_source(client, "a" * 40)

    def test_preimage_guard_accepts_each_reviewed_predecessor_when_unchanged(self) -> None:
        self.assertGreaterEqual(len(reconcile.RECOGNIZED_PREDECESSOR_SHA256S), 2)
        for digest in reconcile.RECOGNIZED_PREDECESSOR_SHA256S:
            with self.subTest(digest=digest):
                runtime._require_recognized_preimage(digest, digest)

    def test_preimage_guard_rejects_unknown_and_cross_predecessor_drift(self) -> None:
        first, second = reconcile.RECOGNIZED_PREDECESSOR_SHA256S[:2]
        cases = (
            ("e" * 64, "e" * 64),
            (first, second),
            (second, first),
        )
        for prepared, observed in cases:
            with self.subTest(prepared=prepared, observed=observed):
                with self.assertRaisesRegex(
                    runtime.BootstrapReconcileRuntimeError,
                    "preimage drifted before replacement",
                ):
                    runtime._require_recognized_preimage(prepared, observed)

    def test_exact_current_returns_noop_without_replay_consume(self) -> None:
        raw = b"current reviewed bootstrap\n"
        digest = hashlib.sha256(raw).hexdigest()
        plan = plan_for(raw, installed_sha256=digest)
        prepared = runtime.PreparedReconcile(plan.source_sha, raw, digest, plan)
        replay = FakeReplay()
        receipt = runtime.execute_prevalidated(
            canonical(plan, digest),
            prepared=prepared,
            accepted=SimpleNamespace(request_id="request-1"),
            replay=replay,
        )
        self.assertEqual(receipt["status"], "ALREADY_EXACT")
        self.assertFalse(receipt["authorization_consumed"])
        self.assertFalse(receipt["production_mutation_started"])
        self.assertEqual(receipt["mutation_categories"], [])
        self.assertEqual(replay.events, [])

    def test_predecessor_consumes_once_before_replacement_and_marks_success_after(self) -> None:
        raw = b"current reviewed bootstrap\n"
        plan = plan_for(raw, installed_sha256=reconcile.RECOGNIZED_PREDECESSOR_SHA256)
        prepared = runtime.PreparedReconcile(
            plan.source_sha,
            raw,
            reconcile.RECOGNIZED_PREDECESSOR_SHA256,
            plan,
        )
        replay = FakeReplay()
        expected = {
            "status": "BOOTSTRAP_EXACT",
            "authorization_consumed": True,
            "production_mutation_started": True,
        }
        with mock.patch.object(runtime, "_atomic_replace", return_value=expected):
            receipt = runtime.execute_prevalidated(
                canonical(plan, reconcile.RECOGNIZED_PREDECESSOR_SHA256),
                prepared=prepared,
                accepted=SimpleNamespace(request_id="request-1"),
                replay=replay,
            )
        self.assertEqual(receipt, expected)
        self.assertEqual(replay.events, ["consume:request-1", "succeeded:request-1"])

    def test_post_consume_failure_has_no_retry_cleanup_or_success_mark(self) -> None:
        raw = b"current reviewed bootstrap\n"
        plan = plan_for(raw, installed_sha256=reconcile.RECOGNIZED_PREDECESSOR_SHA256)
        prepared = runtime.PreparedReconcile(
            plan.source_sha,
            raw,
            reconcile.RECOGNIZED_PREDECESSOR_SHA256,
            plan,
        )
        replay = FakeReplay()
        with mock.patch.object(
            runtime,
            "_atomic_replace",
            side_effect=runtime.BootstrapReconcileRuntimeError("write failed closed"),
        ):
            with self.assertRaisesRegex(runtime.BootstrapReconcileRuntimeError, "write failed closed"):
                runtime.execute_prevalidated(
                    canonical(plan, reconcile.RECOGNIZED_PREDECESSOR_SHA256),
                    prepared=prepared,
                    accepted=SimpleNamespace(request_id="request-1"),
                    replay=replay,
                )
        self.assertEqual(replay.events, ["consume:request-1"])

    def test_fixed_destination_reader_rejects_mode_owner_symlink_and_hardlink_drift(self) -> None:
        uid = os.getuid()
        gid = os.getgid()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good = root / "good"
            good.write_bytes(b"bootstrap\n")
            good.chmod(0o755)
            with mock.patch.object(runtime, "ROOT_UID", uid), mock.patch.object(runtime, "ROOT_GID", gid):
                _, raw = runtime._read_fixed_regular(good)
                self.assertEqual(raw, b"bootstrap\n")

                good.chmod(0o775)
                with self.assertRaises(runtime.BootstrapReconcileRuntimeError):
                    runtime._read_fixed_regular(good)
                good.chmod(0o755)

                link = root / "link"
                link.symlink_to(good)
                with self.assertRaises(runtime.BootstrapReconcileRuntimeError):
                    runtime._read_fixed_regular(link)

                hard = root / "hard"
                os.link(good, hard)
                with self.assertRaises(runtime.BootstrapReconcileRuntimeError):
                    runtime._read_fixed_regular(good)

            with mock.patch.object(runtime, "ROOT_UID", uid + 1), mock.patch.object(runtime, "ROOT_GID", gid):
                with self.assertRaises(runtime.BootstrapReconcileRuntimeError):
                    runtime._read_fixed_regular(good)

    def test_registry_and_readiness_expose_only_fixed_one_operation_scope(self) -> None:
        readiness = runtime.source_readiness()
        self.assertEqual(readiness["implementation_issue"], 743)
        self.assertEqual(readiness["operation_id"], reconcile.OPERATION_ID)
        self.assertEqual(readiness["target_alias"], reconcile.TARGET_ALIAS)
        self.assertEqual(readiness["source_repository"], reconcile.SOURCE_REPOSITORY)
        self.assertEqual(readiness["source_path"], reconcile.SOURCE_PATH)
        self.assertEqual(readiness["source_git_mode"], "100755")
        self.assertEqual(readiness["target_identity"], "derived-from-exact-current-main")
        self.assertEqual(readiness["caller_authority"], ("authorization_issue_number",))
        self.assertEqual(readiness["mutation_budget"], reconcile.MUTATION_BUDGET)
        self.assertEqual(readiness["rollback_policy"], "NONE")
        self.assertFalse(readiness["automatic_retry"])
        self.assertFalse(readiness["automatic_cleanup"])
        self.assertFalse(readiness["automatic_rollback"])
        self.assertFalse(readiness["source_merge_authorizes_live"])
        self.assertFalse(readiness["runtime_live_authority"])
        self.assertFalse(readiness["production_mutation_started"])

        registry = runtime._fixed_registry()
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, reconcile.OPERATION_ID)
        self.assertEqual(operation.target_alias, reconcile.TARGET_ALIAS)
        self.assertEqual(
            tuple((item.category, item.max_operations) for item in operation.mutation_budget),
            reconcile.MUTATION_BUDGET,
        )
        self.assertEqual(operation.rollback_policy, "NONE")

    def test_dispatch_and_runtime_add_no_generic_authority(self) -> None:
        dispatch = DISPATCH.read_text(encoding="utf-8")
        source = Path(runtime.__file__).read_text(encoding="utf-8")
        self.assertIn("BOOTSTRAP_RECONCILE_OPERATION_ID", dispatch)
        self.assertIn("run_privileged_bootstrap_reconcile", dispatch)
        self.assertEqual(
            tuple(inspect.signature(runtime.run_privileged_bootstrap_reconcile).parameters),
            ("authorization_issue_number",),
        )
        forbidden = (
            "subprocess",
            "os.system",
            "Popen(",
            "shell=True",
            "os.environ",
            "git reset",
            "git clean",
            "git rebase",
            "run_privileged_installer_boundary_refresh",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_dedicated_workflow_runs_focused_and_existing_bootstrap_tests(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("test-weather-private-installer-boundary-bootstrap-reconcile.py", workflow)
        self.assertIn("test-weather-private-installer-boundary-bootstrap-reconcile-runtime.py", workflow)
        self.assertIn("test-weather-private-installer-boundary-bootstrap.py", workflow)
        self.assertIn("test-weather-private-installer-boundary-manager-runtime-mode.py", workflow)


if __name__ == "__main__":
    unittest.main()
