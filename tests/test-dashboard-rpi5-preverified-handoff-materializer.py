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

    def test_entrypoint_has_no_dynamic_path_or_command_authority(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "--source", "--path", "--manifest", "--candidate", "--digest", "--command",
            "subprocess", "os.system(", "shell=True", "Popen(", "execv(", "curl ", "wget ",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('Path("/var/lib/rozkalns-dashboard-candidate-input")', source)

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
                    finally:
                        os.close(fd)
                finally:
                    module.core.HANDOFF_BASE = old_base
                    module.core._open_abs_dir = old_open
        finally:
            module.ROOT_UID, module.ROOT_GID = old_uid, old_gid


if __name__ == "__main__":
    unittest.main(verbosity=2)
