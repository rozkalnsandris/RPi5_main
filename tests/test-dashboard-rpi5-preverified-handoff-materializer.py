from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dashboard-rpi5-preverified-handoff-materializer.py"
CONTRACT = ROOT / "ops" / "deploy" / "dashboard-preverified-handoff-materializer-v1.json"
loader = importlib.machinery.SourceFileLoader("dashboard_handoff_repair_tested", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = module
loader.exec_module(module)


class RepairContractTests(unittest.TestCase):
    def test_root_owned_namespace_is_fixed_and_outside_executor_state(self) -> None:
        self.assertEqual(str(module.HANDOFF_BASE), "/var/lib/rozkalns-dashboard-candidate-input")
        self.assertTrue(str(module.HANDOFF_ROOT).startswith("/var/lib/rozkalns-dashboard-candidate-input/"))
        self.assertFalse(str(module.HANDOFF_ROOT).startswith("/var/lib/rozkalns-deploy-executor/"))
        self.assertEqual(module.core.HANDOFF_OWNER, "root")
        self.assertEqual(module.core.HANDOFF_GROUP, "root")
        self.assertEqual(module.HANDOFF_MUTATION_BUDGET[0], ("handoff-namespace-root-create", 1))

    def test_frozen_candidate_binding_is_unchanged(self) -> None:
        self.assertEqual(module.core.REVIEWED_SOURCE_SHA, "066b9a24008dd57439f9e66eae198416c4dfc590")
        self.assertEqual(module.core.REVIEWED_SOURCE_TREE_SHA, "62756ba22fc8d47e44988c086c08dcf37779cfb3")
        self.assertEqual(module.core.REVIEWED_PARENT_SHA, "5f7739348f56398d0ba301c9320e1de0062838fc")
        self.assertEqual(module.core.REVIEWED_PRODUCER_BLOB_SHA, "bea0f30602d119ae53b81e70ce2d4c283d369ce8")
        self.assertEqual(module.EXPECTED_CANDIDATE_SHA256, "d12a49de01891e3a4cc188fa16c173c5eb44c786f013d3a6ebfefe95dcaa47b9")
        self.assertEqual(module.core.EXPECTED_FILE_COUNT, 72)
        self.assertEqual(module.core.EXPECTED_TOTAL_BYTES, 6773246)

    def test_contract_matches_repaired_entrypoint_and_stays_disabled(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertFalse(contract["execution_enabled"])
        self.assertEqual(contract["root_owned_handoff"]["base"], str(module.HANDOFF_BASE))
        self.assertEqual(contract["root_owned_handoff"]["root"], str(module.HANDOFF_ROOT))
        self.assertEqual(contract["root_owned_handoff"]["owner_uid"], 0)
        self.assertEqual(contract["root_owned_handoff"]["group_gid"], 0)
        self.assertTrue(contract["root_owned_handoff"]["post_publish_absolute_reopen"])
        self.assertFalse(contract["root_owned_handoff"]["under_executor_state_directory"])
        self.assertFalse(contract["source_state"]["live_authority"])
        self.assertTrue(contract["source_state"]["supersedes_live_path_from_issue_345"])

    def test_failure_policy_and_gate_sequence_remain_fail_closed(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        policy = contract["failure_policy"]
        self.assertFalse(policy["automatic_retry"])
        self.assertFalse(policy["automatic_cleanup"])
        self.assertFalse(policy["automatic_rollback"])
        self.assertEqual(policy["deletion_budget"], 0)
        self.assertTrue(policy["preserve_partial_after_post_mutation_failure"])
        self.assertEqual(contract["post_merge_gate_sequence"][:4], [
            "unprivileged-preverification-pass",
            "unprivileged-fixed-ingress-preparation",
            "separate-handoff-materialization-live-root-gate",
            "read-only-handoff-proof",
        ])

    def test_entrypoint_has_no_dynamic_path_or_command_authority(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "--source", "--path", "--manifest", "--candidate", "--digest", "--command",
            "subprocess", "os.system(", "shell=True", "Popen(", "execv(", "curl ", "wget ",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('Path("/var/lib/rozkalns-dashboard-candidate-input")', source)

    def test_core_keeps_descriptor_safe_copy_without_execution_surface(self) -> None:
        source = module.CORE_PATH.read_text(encoding="utf-8")
        for required in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "renameat2", "_hash_fd"):
            self.assertIn(required, source)
        for forbidden in ("subprocess", "os.system(", "shell=True", "Popen(", "execv(", "/usr/bin/node"):
            self.assertNotIn(forbidden, source)

    def test_manifest_paths_reject_traversal_and_reserved_components(self) -> None:
        for path in ("../escape", "/absolute", "a/../b", "a//b", "a\\b", "node_modules/x", "candidate-manifest.json"):
            with self.subTest(path=path):
                with self.assertRaises(module.core.HandoffMaterializerError):
                    module.core._safe_parts(path)

    def test_root_ownership_is_required_before_materialization(self) -> None:
        with self.assertRaisesRegex(module.core.HandoffMaterializerError, "root-owned"):
            module._materialize_handoff(
                None, ingress_uid=1000, ingress_gid=1000,
                handoff_uid=1, handoff_gid=0, build_uid=0, build_gid=0,
            )

    def test_absolute_post_publish_reverification_is_installed(self) -> None:
        self.assertIs(module.core._materialize_handoff, module._materialize_handoff)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("_verify_published_absolute(manifest)", source)
        self.assertIn('core._open_abs_dir(core.HANDOFF_ROOT, "published handoff root")', source)

    def test_base_creation_is_fixed_root_owned_only(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        old_uid, old_gid = module.ROOT_UID, module.ROOT_GID
        module.ROOT_UID, module.ROOT_GID = uid, gid
        try:
            with tempfile.TemporaryDirectory() as tmp:
                parent = Path(tmp)
                os.chmod(parent, 0o755)
                base = parent / "fixed"
                old_base = module.core.HANDOFF_BASE
                old_open = module.core._open_abs_dir
                module.core.HANDOFF_BASE = base
                def fake_open_abs_dir(path: Path, label: str) -> int:
                    self.assertEqual(path, parent)
                    return os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                module.core._open_abs_dir = fake_open_abs_dir
                try:
                    fd = module._open_or_create_handoff_base(uid=uid, gid=gid)
                    try:
                        self.assertTrue(base.is_dir())
                        self.assertEqual(base.stat().st_uid, uid)
                        self.assertEqual(base.stat().st_gid, gid)
                    finally:
                        os.close(fd)
                finally:
                    module.core.HANDOFF_BASE = old_base
                    module.core._open_abs_dir = old_open
        finally:
            module.ROOT_UID, module.ROOT_GID = old_uid, old_gid


if __name__ == "__main__":
    unittest.main(verbosity=2)
