#!/usr/bin/env python3
"""Offline, fail-closed proof for the fixed ausmalwiese.de GSC TXT operator."""
from __future__ import annotations

import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "cloudflare_rdc_operator.py"
CONTRACT = ROOT / "ops" / "contracts" / "cloudflare-rdc-operator-v1.json"
spec = importlib.util.spec_from_file_location("cloudflare_rdc_operator_gsc", MODULE)
assert spec and spec.loader
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)

ZONE_ID = "b" * 32
ACCOUNT_ID = "a" * 32
CREATED_ID = "d" * 32
OLD_ID = "c" * 32


class FakeDNS:
    def __init__(self):
        self.rows = [{"id": OLD_ID, "name": "ausmalwiese.de", "type": "CNAME",
                      "content": "existing-tunnel.cfargotunnel.com", "ttl": 1}]
        self.writes = []
        self.mutate_existing = False
        self.broken_post_get = False
        self.missing_id = False

    def _request(self, method, path, body=None):
        if method == "GET" and path == f"/zones/{ZONE_ID}":
            return {"result": {"id": ZONE_ID, "name": "ausmalwiese.de",
                    "status": "active", "account": {"id": ACCOUNT_ID},
                    "plan": {"legacy_id": "free"}}}
        if method == "GET" and path == f"/zones/{ZONE_ID}/dns_records?page=1&per_page=100":
            if self.broken_post_get and self.writes:
                raise op.OperatorError("cloudflare_get_failed")
            return {"result": list(self.rows), "result_info": {"total_pages": 1}}
        if method == "POST" and path == f"/zones/{ZONE_ID}/dns_records":
            self.writes.append(body)
            self.rows.append({**body, "id": CREATED_ID})
            if self.mutate_existing:
                self.rows[0] = {**self.rows[0], "content": "changed.invalid"}
            return {"result": {} if self.missing_id else {"id": CREATED_ID}}
        raise AssertionError((method, path))


class GscTxtTests(unittest.TestCase):
    def test_preflight_preserves_apex_cname_and_existing_unrelated_txt(self):
        client = FakeDNS()
        client.rows.append({"id": "e" * 32, "name": "ausmalwiese.de",
                            "type": "TXT", "content": "v=spf1 -all"})
        result = op.run_ausmalwiese_gsc_txt(client, ZONE_ID, False, "")
        self.assertFalse(result["applied"])
        self.assertRegex(result["baseline"], r"^[0-9a-f]{64}$")
        self.assertEqual(client.writes, [])

    def test_one_exact_post_and_read_only_verify(self):
        client = FakeDNS()
        before = op.run_ausmalwiese_gsc_txt(client, ZONE_ID, False, "")
        after = op.run_ausmalwiese_gsc_txt(
            client, ZONE_ID, True, before["baseline"])
        self.assertTrue(after["applied"])
        self.assertEqual(after["baseline"], before["baseline"])
        self.assertEqual(client.writes, [{
            "type": "TXT", "name": "ausmalwiese.de",
            "content": op.GSC_TXT_CONTENT, "ttl": 1,
        }])
        self.assertEqual(client.rows[0]["content"], "existing-tunnel.cfargotunnel.com")

    def test_duplicate_exact_or_other_google_verification_blocks_without_write(self):
        for content in (op.GSC_TXT_CONTENT,
                        '"'+op.GSC_TXT_CONTENT+'"',
                        "google-site-verification=other"):
            with self.subTest(content=content):
                client = FakeDNS()
                client.rows.append({"id": "e" * 32, "type": "TXT",
                                    "name": "ausmalwiese.de", "content": content})
                with self.assertRaisesRegex(op.OperatorError, "dns_record_conflict"):
                    op.run_ausmalwiese_gsc_txt(client, ZONE_ID, False, "")
                self.assertEqual(client.writes, [])

    def test_stale_baseline_blocks_before_post(self):
        client = FakeDNS()
        with self.assertRaisesRegex(op.OperatorError, "baseline_mismatch"):
            op.run_ausmalwiese_gsc_txt(client, ZONE_ID, True, "0" * 64)
        self.assertEqual(client.writes, [])

    def test_post_write_changed_unrelated_record_stops_once(self):
        client = FakeDNS()
        client.mutate_existing = True
        hash_ = op.run_ausmalwiese_gsc_txt(client, ZONE_ID, False, "")["baseline"]
        with self.assertRaises(op.PostWriteError):
            op.run_ausmalwiese_gsc_txt(client, ZONE_ID, True, hash_)
        self.assertEqual(len(client.writes), 1)

    def test_post_write_get_failure_stops_once(self):
        client = FakeDNS()
        client.broken_post_get = True
        hash_ = op.run_ausmalwiese_gsc_txt(client, ZONE_ID, False, "")["baseline"]
        with self.assertRaises(op.PostWriteError):
            op.run_ausmalwiese_gsc_txt(client, ZONE_ID, True, hash_)
        self.assertEqual(len(client.writes), 1)

    def test_post_write_missing_id_stops_once(self):
        client = FakeDNS()
        client.missing_id = True
        hash_ = op.run_ausmalwiese_gsc_txt(client, ZONE_ID, False, "")["baseline"]
        with self.assertRaises(op.PostWriteError):
            op.run_ausmalwiese_gsc_txt(client, ZONE_ID, True, hash_)
        self.assertEqual(len(client.writes), 1)

    def test_wrong_zone_and_incomplete_inventory_block(self):
        client = FakeDNS()
        with self.assertRaises(op.OperatorError):
            op.run_ausmalwiese_gsc_txt(client, "f" * 32, False, "")
        class Partial(FakeDNS):
            def _request(self, method, path, body=None):
                res = super()._request(method, path, body)
                if "/dns_records?" in path:
                    res["result_info"]["total_pages"] = 2
                return res
        with self.assertRaisesRegex(op.OperatorError, "dns_records_incomplete"):
            op.run_ausmalwiese_gsc_txt(Partial(), ZONE_ID, False, "")

    def test_cli_fixed_scope_no_custom_hostname_content_or_token(self):
        args = op.parse_args(["dns-ausmalwiese-gsc-txt", "--expected-main", "a" * 40])
        self.assertFalse(args.apply)
        self.assertEqual(args.expected_baseline, "")
        for flag in ("--hostname", "--content", "--zone-id", "--api-token"):
            with self.subTest(flag=flag), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                op.parse_args(["dns-ausmalwiese-gsc-txt", "--expected-main", "a" * 40, flag, "x"])

    def test_cli_apply_confirmation_blocks_before_credentials(self):
        with mock.patch.object(op.os, "geteuid", return_value=0), \
             mock.patch.object(op, "load_release_metadata", return_value={}), \
             mock.patch.object(op, "load_dns_credentials", side_effect=AssertionError("no credential read")), \
             mock.patch.object(op, "load_tunnel_credentials", side_effect=AssertionError("no tunnel")), \
             redirect_stdout(io.StringIO()) as output:
            code = op.main(["dns-ausmalwiese-gsc-txt", "--expected-main", "a" * 40,
                            "--apply", "--expected-baseline", "1" * 64])
        self.assertEqual(code, 3)
        self.assertIn("apply_confirmation_missing", output.getvalue())

    def test_cli_pass_never_reads_tunnel_and_outputs_only_sanitized_report(self):
        client = FakeDNS()
        with mock.patch.object(op.os, "geteuid", return_value=0), \
             mock.patch.object(op, "load_release_metadata", return_value={}), \
             mock.patch.object(op, "load_dns_credentials", return_value=(ZONE_ID, "t" * 32)), \
             mock.patch.object(op, "load_tunnel_credentials", side_effect=AssertionError("no tunnel")), \
             mock.patch.object(op, "CloudflareClient", return_value=client), \
             redirect_stdout(io.StringIO()) as output:
            code = op.main(["dns-ausmalwiese-gsc-txt", "--expected-main", "a" * 40])
        self.assertEqual(code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["operation"], "dns-ausmalwiese-gsc-txt")
        self.assertFalse(data["mutation_performed"])
        self.assertNotIn(op.GSC_TXT_CONTENT, output.getvalue())
        self.assertEqual(client.writes, [])

    def test_contract_has_fixed_one_write_scope(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        entries = [x for x in contract["operations"]
                   if x.get("action") == "dns-ausmalwiese-gsc-txt"]
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["zone"], "ausmalwiese.de")
        self.assertEqual(entry["hostname"], "ausmalwiese.de")
        self.assertEqual(entry["value"], op.GSC_TXT_CONTENT)
        self.assertEqual(entry["max_write_requests"], 1)


if __name__ == "__main__":
    unittest.main()
