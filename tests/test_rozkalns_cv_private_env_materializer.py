#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/materialize-simple-deploy-rozkalns-cv-private-env-v1.py"

spec = importlib.util.spec_from_file_location("cv_private_env_materializer", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class CvPrivateEnvMaterializerTests(unittest.TestCase):
    def _candidate(self, root: Path, name: str):
        home = root / name
        bot = home / "docker" / "cv" / "bot"
        data = bot / "data"
        data.mkdir(parents=True)
        env = bot / ".env"
        env.write_text("FIXTURE_SECRET=not-a-real-secret\n", encoding="utf-8")
        env.chmod(0o600)
        return SimpleNamespace(pw_dir=str(home)), env, data

    def test_fixed_public_contract_contains_no_account_home(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(
            module.DESTINATION_ENV,
            Path("/etc/rozkalns-simple-deployer/private/rozkalns-cv.env"),
        )
        self.assertEqual(module.SOURCE_ENV_RELATIVE, Path("docker/cv/bot/.env"))
        self.assertEqual(module.SOURCE_DATA_RELATIVE, Path("docker/cv/bot/data"))
        self.assertEqual(module.RUNTIME_GROUP, "rozkalns-simple-deployer")
        self.assertEqual(module.PARENT_MODE, 0o750)
        self.assertEqual(module.DESTINATION_MODE, 0o640)
        self.assertNotIn("/home/", source)
        self.assertNotIn("andris", source.lower())

    def test_discovery_requires_one_private_env_and_data_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry, env, data = self._candidate(root, "fixture-user")
            resolved = module.discover_runtime_inputs([entry])
            self.assertEqual(resolved.private_env, env)
            self.assertEqual(resolved.persistent_data, data)
            self.assertEqual(stat.S_IMODE(os.lstat(env).st_mode), 0o600)

    def test_discovery_fails_closed_on_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, _, _ = self._candidate(root, "one")
            second, _, _ = self._candidate(root, "two")
            with self.assertRaisesRegex(module.BoundaryError, "SOURCE_RUNTIME_INPUTS_NOT_UNIQUE"):
                module.discover_runtime_inputs([first, second])

    def test_discovery_rejects_broad_source_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry, env, _ = self._candidate(root, "fixture-user")
            env.chmod(0o640)
            with self.assertRaisesRegex(module.BoundaryError, "SOURCE_ENV_PERMISSIONS_TOO_BROAD"):
                module.discover_runtime_inputs([entry])

    def test_result_never_contains_secret_or_source_path_fields(self) -> None:
        rendered = module._result("PREFLIGHT_READY", mutation_started=False)
        self.assertIn('"secret_content_emitted":false', rendered)
        self.assertNotIn("FIXTURE_SECRET", rendered)
        self.assertNotIn("private_env", rendered)
        self.assertNotIn("persistent_data", rendered)

    def test_failure_semantics_have_no_automatic_recovery(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"automatic_cleanup": False', source)
        self.assertIn('"automatic_retry": False', source)
        self.assertIn('"automatic_rollback": False', source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("unlink(missing_ok=True)", source)


if __name__ == "__main__":
    unittest.main()
