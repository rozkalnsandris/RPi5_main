#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WORKFLOWS = (
    ".github/workflows/cloudflare-p1d03-browser-sso-preflight.yml",
    ".github/workflows/cloudflare-p1d04-browser-sso-session.yml",
    ".github/workflows/cloudflare-phase4-admin-access-scope.yml",
    ".github/workflows/cloudflare-p1d04-prelive-prep.yml",
)


class CodeQLTrustedCheckoutGuardTests(unittest.TestCase):
    def test_privileged_jobs_checkout_trusted_main_before_secret_use(self) -> None:
        for relative in WORKFLOWS:
            with self.subTest(workflow=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("ref: main", source)
                self.assertNotIn("ref: ${{ needs.authorize.outputs.expected_sha }}", source)
                guard = source.index("- name: Verify authorized SHA matches trusted checkout")
                secret = source.index("CLOUDFLARE_", guard)
                self.assertLess(guard, secret)
                self.assertIn('[[ ! "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]', source)
                self.assertIn('test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', source)


if __name__ == "__main__":
    unittest.main()
