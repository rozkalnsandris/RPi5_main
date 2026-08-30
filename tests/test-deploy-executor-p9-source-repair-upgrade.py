from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPAIR_OPERATOR = (
    ROOT / "scripts" / "install-deploy-executor-p9-source-repair-upgrade.py"
)
DIAGNOSTICS_OPERATOR = (
    ROOT / "scripts" / "install-deploy-executor-p9-installation-diagnostics-upgrade.py"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class P9SourceRepairUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load("p9_source_repair_upgrade", SOURCE_REPAIR_OPERATOR)
        cls.source = SOURCE_REPAIR_OPERATOR.read_text(encoding="utf-8")

    def test_exact_two_target_contract_and_reviewed_old_blobs(self):
        self.assertEqual(len(self.module.TARGETS), 2)
        self.assertEqual(
            [
                (spec.source_path, str(spec.target_path), spec.old_blob_sha, spec.mode)
                for spec in self.module.TARGETS
            ],
            [
                (
                    "ops/lib/deploy_executor/p9_source_auth.py",
                    "/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py",
                    "b4dc3e3b4662c5f8606817fe453ce5bfb907db3e",
                    0o644,
                ),
                (
                    "ops/bin/rozkalns-deploy-p9-control-baseline",
                    "/usr/local/sbin/rozkalns-deploy-p9-control-baseline",
                    "210815b33e47fb843f71473f485b87e0b751b59d",
                    0o755,
                ),
            ],
        )

    def test_preflight_proves_exact_source_and_both_old_targets_before_apply(self):
        source = self.source
        marker = "Final duplicate gate before the first live mutation"
        preflight = source[: source.index(marker)]
        self.assertIn("_require_exact_source(expected_sha)", preflight)
        self.assertIn("_require_target_prestate(spec)", preflight)
        self.assertIn("_require_parent_chain_safe(spec.target_path)", preflight)
        self.assertIn(
            '_run_git("show", f"{expected_sha}:{source_path}", capture=True)',
            preflight,
        )
        self.assertIn("if not args.apply:", preflight)
        self.assertIn("P9_SOURCE_REPAIR_MUTATION=NO", preflight)
        self.assertGreaterEqual(source.count("_preflight(args.expected_sha)"), 2)

    def test_mutation_is_in_place_only_and_has_no_retry_rollback_or_temp_path(self):
        source = self.source
        marker = "Authorized two-target P9 source repair mutation begins at the first ftruncate"
        mutation = source[source.index(marker):]
        for operation in (
            "os.ftruncate(fd, 0)",
            "_write_fd_all(fd, reviewed_bytes)",
            "os.fchmod(fd, spec.mode)",
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
        self.assertIn("ROLLBACK_PATH=NO", source)

    def test_operator_has_no_network_credential_p9_or_host_control_path(self):
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
            "executor-operations.json",
            "rozkalns-deploy-p9 ",
            "cloudflare",
        ):
            self.assertNotIn(forbidden, source)
        for marker in (
            "NETWORK_REQUEST=NO",
            "CREDENTIAL_READ=NO",
            "P9_EXECUTION=NO",
            "STATE_STORE_TOUCHED=NO",
            "SYSTEMD_MUTATION=NO",
            "CONFIG_REGISTRY_MUTATION=NO",
        ):
            self.assertIn(marker, source)

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
            fn.index("os.stat(spec.target_path, follow_symlinks=False)"),
            truncate_at,
        )
        self.assertIn("os.O_NOFOLLOW", fn)
        self.assertGreater(
            fn.index("if _read_fd_all(fd) != reviewed_bytes"),
            truncate_at,
        )


class P9InstallationDiagnosticsUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load(
            "p9_installation_diagnostics_upgrade",
            DIAGNOSTICS_OPERATOR,
        )
        cls.source = DIAGNOSTICS_OPERATOR.read_text(encoding="utf-8")

    def test_exact_one_target_contract_uses_gate_a_blob_as_prestate(self):
        target = self.module.TARGET
        self.assertEqual(
            (
                target.source_path,
                str(target.target_path),
                target.old_blob_sha,
                target.mode,
            ),
            (
                "ops/lib/deploy_executor/p9_source_auth.py",
                "/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py",
                "2b1fc728453aca32631be9ffe8af127523b14e3b",
                0o644,
            ),
        )
        self.assertNotIn("rozkalns-deploy-p9-control-baseline", self.source)

    def test_diagnostics_preflight_proves_exact_source_and_gate_a_prestate(self):
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
        self.assertIn("P9_INSTALLATION_DIAGNOSTICS_MUTATION=NO", preflight)
        self.assertGreaterEqual(source.count("_preflight(args.expected_sha)"), 2)

    def test_diagnostics_mutation_is_in_place_one_target_only(self):
        source = self.source
        marker = "Authorized one-target diagnostics mutation begins at the first ftruncate"
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
        self.assertIn("BASELINE_CLI_TOUCHED=NO", source)
        self.assertIn("ROLLBACK_PATH=NO", source)

    def test_diagnostics_operator_has_no_network_credential_or_execution_path(self):
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
            "executor-operations.json",
            "cloudflare",
        ):
            self.assertNotIn(forbidden, source)
        for marker in (
            "BASELINE_CLI_TOUCHED=NO",
            "NETWORK_REQUEST=NO",
            "CREDENTIAL_READ=NO",
            "P9_EXECUTION=NO",
            "STATE_STORE_TOUCHED=NO",
            "SYSTEMD_MUTATION=NO",
            "CONFIG_REGISTRY_MUTATION=NO",
        ):
            self.assertIn(marker, source)

    def test_diagnostics_open_fd_is_revalidated_before_first_truncate(self):
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
