from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUDOERS = ROOT / "ops" / "sudoers" / "rozkalns-cv-github-app-read-token"
BROKER = ROOT / "scripts" / "github-app-read-token.py"

EXPECTED_RULE = (
    "andris ALL=(root) NOPASSWD: "
    "/usr/local/sbin/rozkalns-github-app-read-token "
    "--repository rozkalnsandris/rozkalns-cv"
)


class CvGitHubAppAuthBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SUDOERS.read_text(encoding="utf-8")
        cls.rules = [
            line.strip()
            for line in cls.text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        cls.broker_text = BROKER.read_text(encoding="utf-8")

    def test_rule_is_exact_and_cv_only(self) -> None:
        self.assertEqual(self.rules, [EXPECTED_RULE])
        self.assertNotIn("hermes-deals", self.rules[0])
        self.assertNotIn("hermes-tech", self.rules[0])
        self.assertNotIn("RPi5_main", self.rules[0])
        self.assertNotIn("ops-workflows", self.rules[0])
        self.assertNotIn("hermes-email-skill", self.rules[0])

    def test_rule_grants_no_shell_or_deploy_helper(self) -> None:
        rule = self.rules[0]
        self.assertNotIn("/bin/sh", rule)
        self.assertNotIn("/bin/bash", rule)
        self.assertNotIn("rozkalns-cv-deploy-main", rule)
        self.assertNotIn("ALL,", rule)
        self.assertFalse(rule.rstrip().endswith(" ALL"))

    def test_rule_targets_reviewed_broker_contract(self) -> None:
        self.assertIn("APP_ID = 4537106", self.broker_text)
        self.assertIn("INSTALLATION_ID = 152422751", self.broker_text)
        self.assertIn('"actions": "read"', self.broker_text)
        self.assertIn('"contents": "read"', self.broker_text)
        self.assertIn(
            "repository is not approved for automation token access",
            self.broker_text,
        )

    def test_sudoers_syntax_when_visudo_is_available(self) -> None:
        visudo = shutil.which("visudo")
        if visudo is None:
            self.skipTest("visudo unavailable in this CI image")
        completed = subprocess.run(
            [visudo, "-cf", str(SUDOERS)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)


if __name__ == "__main__":
    unittest.main()
