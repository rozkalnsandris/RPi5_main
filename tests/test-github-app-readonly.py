from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "verify-github-app-readonly.py"
SPEC = importlib.util.spec_from_file_location("verify_github_app_readonly", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def decode_segment(value: str) -> dict[str, object]:
    padding = "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(value + padding))


class GitHubAppReadonlyTests(unittest.TestCase):
    def make_key(self, root: Path) -> Path:
        key = root / "app.pem"
        proc = subprocess.run(
            [
                "openssl",
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                str(key),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", errors="replace"))
        key.chmod(0o600)
        return key

    def test_build_app_jwt_uses_rs256_and_bounded_claims(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            key = self.make_key(Path(raw))
            jwt = MODULE.build_app_jwt(12345, key, now=1_800_000_000)
            parts = jwt.split(".")
            self.assertEqual(len(parts), 3)
            header = decode_segment(parts[0])
            payload = decode_segment(parts[1])
            self.assertEqual(header, {"alg": "RS256", "typ": "JWT"})
            self.assertEqual(payload["iss"], "12345")
            self.assertEqual(payload["iat"], 1_799_999_940)
            self.assertEqual(payload["exp"], 1_800_000_540)
            self.assertTrue(parts[2])

    def test_private_key_must_not_be_group_or_world_accessible(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            key = self.make_key(Path(raw))
            key.chmod(0o644)
            with self.assertRaises(MODULE.VerificationError):
                MODULE.build_app_jwt(12345, key, now=1_800_000_000)

    def test_private_key_must_not_be_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            key = self.make_key(root)
            link = root / "link.pem"
            link.symlink_to(key)
            with self.assertRaises(MODULE.VerificationError):
                MODULE.build_app_jwt(12345, link, now=1_800_000_000)

    def token_payload(self, now: datetime) -> dict[str, object]:
        return {
            "token": "ghs_" + "x" * 48,
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "permissions": {
                "actions": "read",
                "contents": "read",
                "metadata": "read",
            },
            "repository_selection": "selected",
        }

    def test_readonly_token_contract_accepts_exact_permissions(self) -> None:
        now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
        token, remaining = MODULE.validate_token_payload(self.token_payload(now), now=now)
        self.assertTrue(token.startswith("ghs_"))
        self.assertEqual(remaining, 3600)

    def test_readonly_token_contract_rejects_write_permission(self) -> None:
        now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
        payload = self.token_payload(now)
        payload["permissions"] = {
            "actions": "read",
            "contents": "read",
            "issues": "write",
        }
        with self.assertRaises(MODULE.VerificationError):
            MODULE.validate_token_payload(payload, now=now)

    def test_readonly_token_contract_rejects_all_repository_selection(self) -> None:
        now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
        payload = self.token_payload(now)
        payload["repository_selection"] = "all"
        with self.assertRaises(MODULE.VerificationError):
            MODULE.validate_token_payload(payload, now=now)

    def test_repository_scope_must_be_exact(self) -> None:
        expected = sorted(MODULE.EXPECTED_REPOS)
        MODULE.validate_repository_scope(
            {"repositories": [{"full_name": name} for name in expected]}
        )
        with self.assertRaises(MODULE.VerificationError):
            MODULE.validate_repository_scope(
                {
                    "repositories": [
                        *({"full_name": name} for name in expected),
                        {"full_name": "rozkalnsandris/rozkalnsandris"},
                    ]
                }
            )

    def test_expected_scope_excludes_email_skill_and_profile_repo(self) -> None:
        self.assertNotIn("rozkalnsandris/hermes-email-skill", MODULE.EXPECTED_REPOS)
        self.assertNotIn("rozkalnsandris/rozkalnsandris", MODULE.EXPECTED_REPOS)
        self.assertEqual(
            set(MODULE.EXPECTED_REPOS),
            {
                "rozkalnsandris/RPi5_main",
                "rozkalnsandris/hermes-tech",
                "rozkalnsandris/rozkalns-cv",
                "rozkalnsandris/hermes-deals",
            },
        )

    def test_script_is_not_group_or_world_writable(self) -> None:
        mode = MODULE_PATH.stat().st_mode
        self.assertFalse(mode & stat.S_IWGRP)
        self.assertFalse(mode & stat.S_IWOTH)


if __name__ == "__main__":
    unittest.main()
