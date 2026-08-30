#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "provision-deploy-executor-p9-control-d1-read-token.py"

spec = importlib.util.spec_from_file_location("p9_d1_credential_provision", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProvisioningContractTests(unittest.TestCase):
    def test_fixed_credential_path(self) -> None:
        self.assertEqual(
            str(module.CREDENTIAL_PATH),
            "/root/.config/rozkalns-deploy-executor-p9/control-d1-read-token",
        )
        self.assertEqual(str(module.ROOT_CONFIG), "/root/.config")

    def test_token_validation_matches_collector_bounds(self) -> None:
        self.assertEqual(module.validate_token("x" * 20), ("x" * 20 + "\n").encode())
        self.assertEqual(len(module.validate_token("x" * 4096)), 4097)
        for value in ("x" * 19, "x" * 4097, "abc def" + "x" * 20, "abc\t" + "x" * 20):
            with self.assertRaises(module.ProvisioningError):
                module.validate_token(value)

    def test_source_has_no_secret_argv_env_or_network_path(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("getpass.getpass", source)
        self.assertIn("interactive TTY", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("http.client", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("curl", source)
        self.assertNotIn("Authorization:", source)

    def test_source_is_create_only_and_fail_closed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("os.O_EXCL", source)
        self.assertIn("O_NOFOLLOW", source)
        self.assertIn("credential target already exists; overwrite/rotation is not authorized", source)
        self.assertNotIn("unlink(", source)
        self.assertNotIn("replace(", source)
        self.assertNotIn("rename(", source)
        self.assertNotIn("rmtree", source)

    def test_source_has_exact_sha_and_final_race_gate(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("_require_exact_source(args.expected_sha)"), 2)
        self.assertIn("git", source)
        self.assertIn("diff", source)
        self.assertIn("SCRIPT_RELATIVE", source)

    def test_success_markers_preserve_scope(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for marker in (
            "CREDENTIAL_INPUT=HIDDEN_TTY",
            "CREDENTIAL_OVERWRITE=NO",
            "D1_REQUEST=NO",
            "BASELINE_COLLECTION=NO",
            "P9_EXECUTION=NO",
            "STATE_STORE_TOUCHED=NO",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
