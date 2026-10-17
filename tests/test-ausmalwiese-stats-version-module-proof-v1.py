#!/usr/bin/env python3
"""All-synthetic adversarial version/module bytes proof tests, no network."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "stats_version_proof_1045", ROOT / "scripts/ausmalwiese_stats_version_module_proof_v1.py")
proof = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(proof)
ACCOUNT = "a" * 32
VERSION = "12345678-1234-4234-a234-123456789abc"
SRC = b"export default {fetch() {return new Response('ok')}};\n"
BLOB = hashlib.sha1(b"blob " + str(len(SRC)).encode() + b"\0" + SRC).hexdigest()


def response(data=SRC):
    return {"success": True, "errors": [], "messages": [],
            "result": {"id": VERSION, "main_module": "stats-worker.js",
                       "modules": [{"name": "stats-worker.js",
                                    "content_type": "application/javascript+module",
                                    "content_base64": base64.b64encode(data).decode("ascii")}]}}


def inventory():
    return {"account_sha256": proof.ACCOUNT_SHA256, "worker": proof.WORKER,
            "environment": "production", "active_version": VERSION,
            "latest_uploaded_version": VERSION, "source_repo": proof.SOURCE_REPO,
            "source_commit": proof.SOURCE_COMMIT, "source_blob": proof.SOURCE_BLOB}


def wire(data):
    return json.dumps(data, separators=(",", ":")).encode()


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.object(proof, "ACCOUNT_SHA256", hashlib.sha256(ACCOUNT.encode()).hexdigest()),
                        mock.patch.object(proof, "SOURCE_BLOB", BLOB)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_fixed_scope_and_full_version(self):
        get = proof.fixed_get(ACCOUNT, VERSION)
        self.assertEqual(get["method"], "GET")
        self.assertEqual(get["scheme"], "https")
        self.assertEqual(get["host"], "api.cloudflare.com")
        self.assertEqual(get["port"], 443)
        self.assertTrue(get["path"].endswith("/" + VERSION + "?include=modules"))
        self.assertEqual((get["redirects"], get["retries"]), (0, 0))
        self.assertFalse(get["dispatch_enabled"])
        for wrong in ("latest", VERSION[:8], VERSION.upper(), VERSION + "/", "x" * 36):
            with self.assertRaises(proof.Blocked):
                proof.fixed_get(ACCOUNT, wrong)
        for wrong in ("b" * 32, ACCOUNT.upper(), ACCOUNT + "/"):
            with self.assertRaises(proof.Blocked):
                proof.fixed_get(wrong, VERSION)

    def test_offline_fixture_matches_but_cannot_authorize(self):
        matched = proof.verify_offline(ACCOUNT, VERSION, wire(response()), SRC, inventory())
        self.assertEqual(matched["module_sha256"], hashlib.sha256(SRC).hexdigest())
        self.assertEqual(matched["state"], "OFFLINE_BYTES_MATCH_NOT_AUTHENTICATED_NO_LIVE")
        self.assertEqual(proof.read_module(wire(response()), VERSION), SRC)

    def test_source_git_blob_and_byte_drift(self):
        with self.assertRaisesRegex(proof.Blocked, "SOURCE_BLOB_MISMATCH"):
            proof.verify_offline(ACCOUNT, VERSION, wire(response()), SRC + b" ", inventory())
        with self.assertRaisesRegex(proof.Blocked, "VERSION_CODE_DRIFT"):
            proof.verify_offline(ACCOUNT, VERSION, wire(response(SRC + b" ")), SRC, inventory())
        with self.assertRaises(proof.Blocked):
            proof.verify_source(b"")
        with self.assertRaises(proof.Blocked):
            proof.verify_source("not bytes")

    def test_response_version_and_main_mapping(self):
        for key, val in (("id", "latest"), ("id", "22345678-1234-4234-a234-123456789abc"),
                         ("main_module", "other.js"), ("modules", []),
                         ("modules", response()["result"]["modules"] * 2)):
            data = response()
            data["result"][key] = val
            with self.subTest(key=key, val=str(val)[:15]):
                with self.assertRaises(proof.Blocked):
                    proof.read_module(wire(data), VERSION)

    def test_module_mime_name_shape_and_extras(self):
        for key, value in (("name", "other.js"), ("content_type", "text/javascript"),
                           ("content_type", "application/javascript+module; charset=utf-8"),
                           ("extra", "forbidden"), ("content_base64", None)):
            data = response()
            data["result"]["modules"][0][key] = value
            with self.subTest(key=key):
                with self.assertRaises(proof.Blocked):
                    proof.read_module(wire(data), VERSION)
        x = response()
        del x["result"]["modules"][0]["name"]
        with self.assertRaises(proof.Blocked):
            proof.read_module(wire(x), VERSION)
        x = response()
        x["result"]["unknown"] = "bad"
        with self.assertRaises(proof.Blocked):
            proof.read_module(wire(x), VERSION)

    def test_strict_canonical_base64(self):
        for invalid in ("!", "a", "Zg", "Zg==\n", "Zg===", "Zh==", "", "AAAA====", "AA=A"):
            x = response()
            x["result"]["modules"][0]["content_base64"] = invalid
            with self.subTest(invalid=invalid):
                with self.assertRaises(proof.Blocked):
                    proof.read_module(wire(x), VERSION)

    def test_bad_json_duplicate_oversized_nonfinite(self):
        for raw in (b"", b"\xff", b'{"success":true,"success":true}',
                    b'{"success":NaN}', b"x" * (proof.MAX_REPLY + 1),
                    b'{"success":true,"errors":[],"result":{"id":"x","id":"y"}}'):
            with self.assertRaises(proof.Blocked):
                proof.read_module(raw, VERSION)

    def test_extra_modules_missing_and_size(self):
        x = response()
        x["result"]["modules"].append({"name": "addon.js", "content_type": proof.MIME,
                                           "content_base64": "YQ=="})
        with self.assertRaises(proof.Blocked):
            proof.read_module(wire(x), VERSION)
        x = response()
        x["result"]["modules"][0]["content_base64"] = base64.b64encode(b"a" * (proof.MAX_MODULE + 1)).decode()
        with self.assertRaises(proof.Blocked):
            proof.read_module(wire(x), VERSION)

    def test_response_status_errors_and_ambiguity(self):
        for change in ({"success": False}, {"errors": [{"code": 42}]},
                       {"cookie": "test"}, {"result": []}, {"messages": "bad"}):
            x = response()
            x.update(change)
            with self.assertRaises(proof.Blocked):
                proof.read_module(wire(x), VERSION)

    def test_untrusted_inventory_never_is_a_live_receipt(self):
        for key, bad in (("worker", "coloring-pages-report-v1"),
                         ("environment", "preview"),
                         ("active_version", "22345678-1234-4234-a234-123456789abc"),
                         ("latest_uploaded_version", "22345678-1234-4234-a234-123456789abc"),
                         ("source_blob", "0" * 40), ("account_sha256", "0" * 64)):
            x = inventory()
            x[key] = bad
            with self.subTest(key=key):
                with self.assertRaises(proof.Blocked):
                    proof.verify_offline(ACCOUNT, VERSION, wire(response()), SRC, x)
        x = inventory()
        x["attested"] = True
        with self.assertRaises(proof.Blocked):
            proof.verify_offline(ACCOUNT, VERSION, wire(response()), SRC, x)

    def test_source_only_entrypoint_and_contract(self):
        # Check against real, unpatched source constants.
        for patch in reversed(self.patches):
            patch.stop()
        try:
            self.assertEqual(proof.main(["--check-contract"]), 0)
            self.assertEqual(proof.main([]), 2)
            self.assertEqual(proof.main(["--deploy"]), 2)
            c = json.loads(proof.CONTRACT.read_text("utf-8"))
            proof.check_contract(c)
            self.assertFalse(c["live_authorized"])
            self.assertFalse(c["worker_writes_enabled"])
        finally:
            for patch in self.patches:
                patch.start()
        code = (ROOT / "scripts/ausmalwiese_stats_version_module_proof_v1.py").read_text("utf-8")
        self.assertNotIn("HTTPSConnection", code)
        self.assertNotIn("requests.get", code)
        self.assertNotIn("subprocess", code)
        self.assertNotIn("os.environ", code)
        self.assertNotIn("Authorization: Bearer", code)


if __name__ == "__main__":
    unittest.main()
