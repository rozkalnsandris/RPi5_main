from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPLACEMENT_SCRIPT = (
    ROOT / "scripts/replace-deploy-executor-p9-control-d1-read-token.py"
)


class P9D1CredentialReplacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location(
            "p9_d1_credential_replacement", REPLACEMENT_SCRIPT
        )
        assert spec is not None and spec.loader is not None
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.source = REPLACEMENT_SCRIPT.read_text(encoding="utf-8")

    def test_fixed_account_target_and_hidden_ingress(self):
        self.assertEqual(
            self.module.ACCOUNT_ID,
            "70e29dbca0e8363358659102d2b74178",
        )
        self.assertEqual(
            self.module.VERIFY_PATH,
            "/client/v4/accounts/"
            "70e29dbca0e8363358659102d2b74178/tokens/verify",
        )
        self.assertEqual(
            str(self.module.CREDENTIAL_PATH),
            "/root/.config/rozkalns-deploy-executor-p9/control-d1-read-token",
        )
        self.assertIn("getpass.getpass", self.source)
        self.assertIn("interactive TTY", self.source)
        self.assertNotIn("os.environ", self.source)

    def test_expected_token_id_is_exact_public_metadata(self):
        token_id = "a" * 32
        self.assertEqual(
            self.module._validate_expected_token_id(token_id),
            token_id,
        )
        for invalid in (
            "",
            "a" * 31,
            "a" * 33,
            "A" * 32,
            "g" * 32,
            "../" + "a" * 29,
        ):
            with self.assertRaises(self.module.ReplacementError):
                self.module._validate_expected_token_id(invalid)

    def test_candidate_validation_matches_existing_credential_bounds(self):
        self.assertEqual(
            self.module.validate_token("x" * 20),
            ("x" * 20 + "\n").encode(),
        )
        self.assertEqual(len(self.module.validate_token("x" * 4096)), 4097)
        for value in (
            "x" * 19,
            "x" * 4097,
            "abc def" + "x" * 20,
            "abc\t" + "x" * 20,
        ):
            with self.assertRaises(self.module.ReplacementError):
                self.module.validate_token(value)

    def test_verify_binds_candidate_to_exact_active_account_token_id(self):
        expected = "b" * 32
        seen: list[str] = []

        def requester(token: str):
            seen.append(token)
            return (
                200,
                json.dumps(
                    {
                        "success": True,
                        "result": {
                            "id": expected,
                            "status": "active",
                        },
                    }
                ).encode(),
            )

        result = self.module.verify_candidate_token(
            "candidate-secret-value",
            expected,
            requester=requester,
        )
        self.assertEqual(seen, ["candidate-secret-value"])
        self.assertEqual(result.token_id, expected)
        self.assertEqual(result.status, "active")

    def test_verify_fails_closed_on_status_payload_identity_or_state(self):
        expected = "c" * 32

        cases = (
            (
                lambda _token: (403, b"provider detail must stay hidden"),
                "token_verify_status",
            ),
            (
                lambda _token: (200, b"not-json"),
                "token_verify_payload",
            ),
            (
                lambda _token: (
                    200,
                    json.dumps(
                        {
                            "success": True,
                            "result": {"id": "d" * 32, "status": "active"},
                        }
                    ).encode(),
                ),
                "token_verify_identity",
            ),
            (
                lambda _token: (
                    200,
                    json.dumps(
                        {
                            "success": True,
                            "result": {"id": expected, "status": "disabled"},
                        }
                    ).encode(),
                ),
                "token_verify_state",
            ),
        )

        for requester, stage in cases:
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(
                    self.module.ReplacementError,
                    f"^{stage}$",
                ):
                    self.module.verify_candidate_token(
                        "candidate-secret-value",
                        expected,
                        requester=requester,
                    )

    def test_verify_transport_is_fixed_get_only_bounded_and_no_retry(self):
        self.assertIn('API_HOST = "api.cloudflare.com"', self.source)
        self.assertIn('connection.request(\n            "GET",\n            VERIFY_PATH,', self.source)
        self.assertIn("MAX_VERIFY_RESPONSE_BYTES + 1", self.source)
        self.assertIn("Authorization", self.source)
        for forbidden in (
            "urllib",
            "requests.",
            "curl",
            "Retry",
            "retry",
            "redirect",
            "Location",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_old_credential_contents_are_never_read(self):
        self.assertNotIn("CREDENTIAL_PATH.read_bytes", self.source)
        self.assertNotIn("os.read(", self.source)
        self.assertIn("flags = os.O_WRONLY", self.source)
        self.assertNotIn("os.O_RDONLY", self.source)
        self.assertIn("OLD_CREDENTIAL_CONTENT_READ=NO", self.source)

    def test_source_and_inode_are_revalidated_around_consumed_verify(self):
        self.assertGreaterEqual(
            self.source.count("_require_exact_source(args.expected_sha)"),
            3,
        )
        self.assertGreaterEqual(
            self.source.count("_require_credential_unchanged(prestate)"),
            2,
        )
        consumed = self.source.index("AUTHORIZATION_CONSUMED=YES ")
        verify = self.source.index(
            "verified = verify_candidate_token(candidate, expected_token_id)"
        )
        mutate = self.source.index("_replace_target(payload, prestate)")
        self.assertLess(consumed, verify)
        self.assertLess(verify, mutate)

    def test_mutation_is_one_target_in_place_without_backup_or_rollback(self):
        self.assertIn("os.ftruncate(fd, 0)", self.source)
        self.assertIn("os.fsync(fd)", self.source)
        self.assertIn("O_NOFOLLOW", self.source)
        for forbidden in (
            "os.unlink",
            "os.replace",
            "os.rename",
            "shutil",
            "tempfile",
            ".bak",
        ):
            self.assertNotIn(forbidden, self.source)
        for marker in (
            "D1_REQUEST=NO",
            "CLOUDFLARE_PERMISSION_MUTATION=NO",
            "BASELINE_COLLECTION=NO",
            "P9_EXECUTION=NO",
            "STATE_STORE_TOUCHED=NO",
            "ROLLBACK_PATH=NO",
            "RETRY_PATH=NO",
        ):
            self.assertIn(marker, self.source)


if __name__ == "__main__":
    unittest.main()
