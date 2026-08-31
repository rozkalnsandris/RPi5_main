from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts" / "install-deploy-executor-p9-gate-d-registry-provenance-upgrade.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class P9RegistryProvenanceUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load("p9_registry_provenance_upgrade", OPERATOR)
        cls.source = OPERATOR.read_text(encoding="utf-8")

    def test_exact_one_target_contract_and_reviewed_old_blob(self):
        target = self.module.TARGET
        self.assertEqual(
            (
                target.source_path,
                str(target.target_path),
                target.old_blob_sha,
                target.mode,
            ),
            (
                "ops/deploy/executor-operations.json",
                "/etc/rozkalns-deploy-executor-p9/executor-operations.json",
                "5e9e4c7e96b6f24453077d896812a402bb303a92",
                0o644,
            ),
        )

    def test_preflight_proves_exact_source_and_old_target_before_apply(self):
        source = self.source
        marker = "Final duplicate gate before the first live mutation"
        preflight = source[: source.index(marker)]
        self.assertIn("_require_exact_source(expected_sha)", preflight)
        self.assertIn("_require_target_prestate()", preflight)
        self.assertIn("_require_parent_chain_safe(TARGET.target_path)", preflight)
        self.assertIn(
            '_run_git("show", f"{expected_sha}:{TARGET.source_path}", capture=True)',
            preflight,
        )
        self.assertIn("if not args.apply:", preflight)
        self.assertIn("P9_GATE_D_REGISTRY_PROVENANCE_MUTATION=NO", preflight)
        self.assertGreaterEqual(source.count("_preflight(args.expected_sha)"), 2)

    def test_mutation_is_in_place_one_target_only_with_no_retry_or_rollback(self):
        source = self.source
        marker = "A separately owner-authorized one-target live mutation begins here"
        mutation = source[source.index(marker):]
        for operation in (
            "os.ftruncate(fd, 0)",
            "_write_fd_all(fd, reviewed_bytes)",
            "os.fchmod(fd, TARGET.mode)",
            "os.fchown(fd, 0, 0)",
            "os.fsync(fd)",
        ):
            self.assertIn(operation, mutation)
        for forbidden in (
            "os.replace",
            "os.rename",
            "os.unlink",
            "shutil",
            "tempfile",
            "mkstemp",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("for attempt", source)
        self.assertNotIn("while attempt", source)
        self.assertIn("TARGETS_REPLACED=1", source)
        self.assertIn("ROLLBACK_PATH=NO", source)
        self.assertIn("RETRY_PATH=NO", source)

    def test_operator_has_only_registry_live_mutation_surface(self):
        source = self.source
        for forbidden in (
            "urllib",
            "http.client",
            "requests",
            "curl",
            "wget",
            "gh ",
            "Authorization:",
            "control-d1-read-token",
            "github-app.pem",
            "systemctl",
            "StateStore",
            "cloudflare",
            "rozkalns-deploy-p9 ",
        ):
            self.assertNotIn(forbidden, source)
        for marker in (
            "NETWORK_REQUEST=NO",
            "CREDENTIAL_READ=NO",
            "D1_REQUEST=NO",
            "BASELINE_COLLECTION=NO",
            "P9_EXECUTION=NO",
            "STATE_STORE_TOUCHED=NO",
            "SYSTEMD_MUTATION=NO",
            "CONFIG_REGISTRY_MUTATION=YES",
            "ADAPTER_TOUCHED=NO",
            "BASELINE_CLI_TOUCHED=NO",
            "COLLECTOR_TOUCHED=NO",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("CONFIG_REGISTRY_MUTATION=NO", source)

    def test_open_fd_is_revalidated_before_first_truncate(self):
        source = self.source
        fn = source[
            source.index("def _replace_exact_target") :
            source.index("def _parse_args")
        ]
        truncate_at = fn.index("os.ftruncate(fd, 0)")
        self.assertLess(fn.index("os.fstat(fd)"), truncate_at)
        self.assertLess(fn.index("_git_blob_sha(current)"), truncate_at)
        self.assertLess(
            fn.index("os.stat(TARGET.target_path, follow_symlinks=False)"),
            truncate_at,
        )
        self.assertIn("os.O_NOFOLLOW", fn)
        self.assertGreater(
            fn.index("if _read_fd_all(fd) != reviewed_bytes"),
            truncate_at,
        )


if __name__ == "__main__":
    unittest.main()
