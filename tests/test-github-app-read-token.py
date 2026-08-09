from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "github-app-read-token.py"

spec = importlib.util.spec_from_file_location("github_app_read_token", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GitHubAppReadTokenTests(unittest.TestCase):
    def valid_payload(self, repository: str) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "token": "ghs_" + "x" * 80,
            "expires_at": (now + timedelta(seconds=3600)).isoformat().replace("+00:00", "Z"),
            "permissions": {
                "actions": "read",
                "contents": "read",
                "metadata": "read",
            },
            "repositories": [{"full_name": repository}],
        }

    def test_approved_repository_set_is_exact(self) -> None:
        self.assertEqual(
            module.ALLOWED_REPOSITORIES,
            {
                "rozkalnsandris/RPi5_main",
                "rozkalnsandris/hermes-tech",
                "rozkalnsandris/rozkalns-cv",
                "rozkalnsandris/hermes-deals",
            },
        )
        self.assertNotIn("rozkalnsandris/ops-workflows", module.ALLOWED_REPOSITORIES)
        self.assertNotIn("rozkalnsandris/hermes-email-skill", module.ALLOWED_REPOSITORIES)

    def test_accepts_one_repo_read_only_payload(self) -> None:
        repo = "rozkalnsandris/rozkalns-cv"
        token = module.validate_token_payload(self.valid_payload(repo), repository=repo)
        self.assertTrue(token.startswith("ghs_"))

    def test_rejects_write_permission(self) -> None:
        repo = "rozkalnsandris/rozkalns-cv"
        payload = self.valid_payload(repo)
        payload["permissions"]["contents"] = "write"
        with self.assertRaises(module.TokenBrokerError):
            module.validate_token_payload(payload, repository=repo)

    def test_rejects_extra_repository_scope(self) -> None:
        repo = "rozkalnsandris/rozkalns-cv"
        payload = self.valid_payload(repo)
        payload["repositories"].append({"full_name": "rozkalnsandris/hermes-tech"})
        with self.assertRaises(module.TokenBrokerError):
            module.validate_token_payload(payload, repository=repo)

    def test_mint_requests_only_named_repo_and_read_permissions(self) -> None:
        repo = "rozkalnsandris/rozkalns-cv"
        captured: dict = {}

        def fake_request(url, *, authorization, method, body):
            captured.update(
                url=url,
                authorization=authorization,
                method=method,
                body=body,
            )
            return self.valid_payload(repo)

        with patch.object(module, "build_app_jwt", return_value="synthetic-jwt"), patch.object(
            module, "request_json", side_effect=fake_request
        ):
            token = module.mint_repository_token(repo)

        self.assertTrue(token.startswith("ghs_"))
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["body"]["repositories"], [repo])
        self.assertEqual(
            captured["body"]["permissions"],
            {"actions": "read", "contents": "read"},
        )
        self.assertNotIn("token", str(captured["body"]).lower())

    def test_unapproved_repository_fails_before_network_or_signing(self) -> None:
        with patch.object(module, "build_app_jwt") as jwt, patch.object(
            module, "request_json"
        ) as request:
            with self.assertRaises(module.TokenBrokerError):
                module.mint_repository_token("rozkalnsandris/ops-workflows")
        jwt.assert_not_called()
        request.assert_not_called()

    def test_private_key_contract_rejects_symlink_and_open_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "key.pem"
            target.write_text("not-a-real-key", encoding="utf-8")
            target.chmod(0o644)
            with self.assertRaises(module.TokenBrokerError):
                module.require_private_key(target)

            target.chmod(0o600)
            link = root / "link.pem"
            link.symlink_to(target)
            with self.assertRaises(module.TokenBrokerError):
                module.require_private_key(link)


if __name__ == "__main__":
    unittest.main()
