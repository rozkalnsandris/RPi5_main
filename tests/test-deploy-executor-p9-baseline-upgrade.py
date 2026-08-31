from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROVISION_SCRIPT = (
    ROOT / "scripts/provision-deploy-executor-p9-control-d1-read-token.py"
)

EXPECTED_281_PACKAGE_FILES = (
    "__init__.py",
    "adapters.py",
    "control_center_postcanary_adapter.py",
    "github_app_auth.py",
    "p9_canary.py",
    "p9_evidence.py",
    "p9_host_runtime.py",
    "p9_isolated_auth_surface.py",
    "p9_provenance.py",
    "p9_runtime.py",
    "p9_source_auth.py",
    "protocol.py",
    "queue_normalizer.py",
    "registry.py",
    "source_evidence.py",
    "state.py",
    "transport.py",
)


class P9BaselineWiringUpgradeTests(unittest.TestCase):
    def _source(self) -> str:
        return (
            ROOT / "scripts/install-deploy-executor-p9-baseline-wiring-upgrade.sh"
        ).read_text(encoding="utf-8")

    def test_upgrade_verifies_actual_281_installed_baseline(self):
        source = self._source()
        marker = "Authorized post-install P9 baseline wiring mutation begins here"
        preflight = source[: source.index(marker)]
        self.assertIn(
            'BASELINE_SOURCE_SHA="416860795831203e1670cb383c527bd212614a1d"',
            source,
        )
        self.assertIn("verify_installed_baseline_file()", preflight)
        for name in EXPECTED_281_PACKAGE_FILES:
            self.assertIn(f"  {name}\n", preflight)
        baseline_array = preflight[
            preflight.index("BASELINE_PACKAGE_FILES=(") : preflight.index(
                ")\nSOURCE_PATHS=("
            )
        ]
        self.assertNotIn("p9_control_postcanary_producer.py", baseline_array)
        self.assertIn(
            'verify_installed_baseline_file "ops/bin/rozkalns-deploy-p9" "$P9_BIN" 755',
            preflight,
        )
        self.assertIn(
            'verify_installed_baseline_file "ops/deploy/executor-operations.json" "$P9_REGISTRY" 644',
            preflight,
        )
        self.assertIn("executor-p9-isolated-auth-surface.json", preflight)
        self.assertIn('require_directory_metadata "$STATE_ROOT" "0:0:700"', preflight)
        self.assertIn("P9 state database ownership/mode mismatch", preflight)
        self.assertIn("/usr/bin/cmp -s", preflight)
        self.assertNotIn("installed Control producer missing or symlink", source)
        self.assertNotIn(
            "installed Control producer does not match reviewed P9 runtime baseline", source
        )

    def test_all_baseline_wiring_targets_must_be_absent_before_mutation(self):
        source = self._source()
        marker = "Authorized post-install P9 baseline wiring mutation begins here"
        preflight = source[: source.index(marker)]
        self.assertIn(
            'for target in "$PRODUCER" "$COLLECTOR" "$BASELINE_BIN"; do',
            preflight,
        )
        self.assertIn(
            "baseline wiring target already exists; refusing ambiguous upgrade", preflight
        )

    def test_upgrade_mutates_only_three_new_reviewed_targets(self):
        source = self._source()
        marker = "Authorized post-install P9 baseline wiring mutation begins here"
        mutation = source[source.index(marker) :]
        self.assertEqual(mutation.count("/usr/bin/install -o root -g root"), 3)
        self.assertIn(
            '"$ROOT/ops/lib/deploy_executor/p9_control_postcanary_producer.py" "$PRODUCER"',
            mutation,
        )
        self.assertIn(
            '"$ROOT/ops/lib/deploy_executor/p9_control_postcanary_collector.py" "$COLLECTOR"',
            mutation,
        )
        self.assertIn(
            '"$ROOT/ops/bin/rozkalns-deploy-p9-control-baseline" "$BASELINE_BIN"',
            mutation,
        )
        self.assertNotIn("P9_CONFIG_ROOT/", mutation)
        self.assertNotIn("STATE_ROOT/", mutation)
        self.assertNotIn("EVIDENCE_ROOT/", mutation)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("StateStore", source)
        self.assertNotIn("control-d1-read-token", source)
        self.assertNotIn("github-app.pem", source)
        self.assertNotIn("mkdir", source)
        self.assertNotIn("install -d", source)
        self.assertIn("P9_RUNTIME_ACTIVE=NO", source)
        self.assertIn("P9_EVIDENCE_PRODUCED=NO", source)
        self.assertIn("P9_CREDENTIAL_MUTATION=NO", source)


class P9D1CredentialProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location(
            "p9_d1_credential_provision", PROVISION_SCRIPT
        )
        assert spec is not None and spec.loader is not None
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.source = PROVISION_SCRIPT.read_text(encoding="utf-8")

    def test_fixed_target_and_hidden_tty_ingress(self):
        self.assertEqual(
            str(self.module.CREDENTIAL_PATH),
            "/root/.config/rozkalns-deploy-executor-p9/control-d1-read-token",
        )
        self.assertIn("getpass.getpass", self.source)
        self.assertIn("interactive TTY", self.source)
        self.assertNotIn("os.environ", self.source)

    def test_token_validation_matches_collector_bounds(self):
        self.assertEqual(
            self.module.validate_token("x" * 20), ("x" * 20 + "\n").encode()
        )
        self.assertEqual(len(self.module.validate_token("x" * 4096)), 4097)
        for value in (
            "x" * 19,
            "x" * 4097,
            "abc def" + "x" * 20,
            "abc\t" + "x" * 20,
        ):
            with self.assertRaises(self.module.ProvisioningError):
                self.module.validate_token(value)

    def test_operator_is_create_only_and_has_no_network_path(self):
        self.assertIn("os.O_EXCL", self.source)
        self.assertIn("O_NOFOLLOW", self.source)
        self.assertIn(
            "credential target already exists; overwrite/rotation is not authorized",
            self.source,
        )
        for forbidden in (
            "unlink(",
            "replace(",
            "rename(",
            "rmtree",
            "urllib",
            "http.client",
            "requests",
            "curl",
            "Authorization:",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_exact_sha_is_revalidated_before_mutation(self):
        self.assertGreaterEqual(
            self.source.count("_require_exact_source(args.expected_sha)"), 2
        )
        marker = "Authorized credential-placement mutation begins here"
        preflight = self.source[: self.source.index(marker)]
        self.assertIn("_require_target_absent()", preflight)
        self.assertIn("_require_root_config_metadata()", preflight)

    def test_success_markers_preserve_prerequisite_scope(self):
        for marker in (
            "CREDENTIAL_INPUT=HIDDEN_TTY",
            "CREDENTIAL_OVERWRITE=NO",
            "D1_REQUEST=NO",
            "BASELINE_COLLECTION=NO",
            "P9_EXECUTION=NO",
            "STATE_STORE_TOUCHED=NO",
        ):
            self.assertIn(marker, self.source)


if __name__ == "__main__":
    unittest.main()
