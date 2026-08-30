from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class P9BaselineWiringUpgradeTests(unittest.TestCase):
    def test_upgrade_is_exact_baseline_only_and_nonactivating(self):
        source = (
            ROOT / "scripts/install-deploy-executor-p9-baseline-wiring-upgrade.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('BASELINE_SOURCE_SHA="416860795831203e1670cb383c527bd212614a1d"', source)
        self.assertIn("cat-file -e", source)
        self.assertIn("/usr/bin/cmp -s", source)
        self.assertIn("installed Control producer does not match reviewed P9 runtime baseline", source)
        self.assertIn("baseline wiring target already exists; refusing ambiguous upgrade", source)
        self.assertIn("p9_control_postcanary_collector.py", source)
        self.assertIn("rozkalns-deploy-p9-control-baseline", source)
        self.assertIn("p9_control_postcanary_producer.py", source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("StateStore", source)
        self.assertNotIn("control-d1-read-token", source)
        self.assertNotIn("github-app.pem", source)
        self.assertNotIn("mkdir", source)
        self.assertNotIn("install -d", source)
        self.assertIn("P9_RUNTIME_ACTIVE=NO", source)
        self.assertIn("P9_EVIDENCE_PRODUCED=NO", source)
        self.assertIn("P9_CREDENTIAL_MUTATION=NO", source)
        self.assertLess(
            source.index("/usr/bin/cmp -s"),
            source.index("Authorized post-install P9 baseline wiring mutation begins here"),
        )

    def test_upgrade_mutates_only_three_reviewed_targets(self):
        source = (
            ROOT / "scripts/install-deploy-executor-p9-baseline-wiring-upgrade.sh"
        ).read_text(encoding="utf-8")
        marker = "Authorized post-install P9 baseline wiring mutation begins here"
        mutation = source[source.index(marker):]
        self.assertEqual(mutation.count("/usr/bin/install -o root -g root"), 3)
        self.assertNotIn("P9_CONFIG_ROOT/", mutation)
        self.assertNotIn("STATE_ROOT/", mutation)
        self.assertNotIn("EVIDENCE_ROOT/", mutation)


if __name__ == "__main__":
    unittest.main()
