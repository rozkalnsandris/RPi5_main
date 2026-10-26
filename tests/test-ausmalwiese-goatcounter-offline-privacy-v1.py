"""Synthetic, disconnected tests of the GoatCounter SQLite structural gate.

These unit tests do not start GoatCounter, send visitor requests, touch
Cloudflare, inspect RPi5, or demonstrate GDPR/TDDDG compliance.
"""
import contextlib
import io
import importlib.util
import itertools
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ausmalwiese_goatcounter_offline_privacy_probe_v1 as probe  # noqa: E402

V2_TEST_PATH = ROOT / "tests" / "test-ausmalwiese-goatcounter-isolated-proof-v2.py"
V2_SPEC = importlib.util.spec_from_file_location("goatcounter_isolated_proof_v2_tests", V2_TEST_PATH)
if V2_SPEC is None or V2_SPEC.loader is None:
    raise RuntimeError("unable to load GoatCounter isolated proof v2 tests")
V2_TESTS = importlib.util.module_from_spec(V2_SPEC)
V2_SPEC.loader.exec_module(V2_TESTS)
IsolatedProofV2Tests = V2_TESTS.IsolatedProofV2Tests


class SyntheticGoatCounterFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=probe.PREFIX)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / probe.MARKER).write_bytes(probe.MARKER_BYTES)
        self.db = self.root / probe.DB_NAME
        self.id = "0427183"
        self.views = 2
        self._create_synthetic_schema()

    def _create_synthetic_schema(self):
        schemas = {
            "sites": "site_id integer, settings text",
            "users": "user_id integer, site_id integer, email text",
            "api_tokens": (
                "api_token_id integer, site_id integer, user_id integer, "
                "name text, token text, permissions text, sites text"
            ),
            "paths": "site_id integer, path_id integer, path text",
            "refs": "ref_id integer, ref text, ref_scheme text",
            "hit_counts": "site_id integer, path_id integer, hour text, total integer",
            "ref_counts": "site_id integer, path_id integer, ref_id integer, hour text, total integer",
            "hit_stats": "site_id integer, path_id integer, day text, stats text",
            "bots": "site_id integer, path text, bot integer, user_agent text, created_at text",
            "hits": "site_id integer, path_id integer, session blob, created_at text",
            "store": "key text, value blob",
            "version": "name text",
            "locations": "location_id integer, country text, country_name text, region text, region_name text",
            "languages": "iso_639_3 text, name text",
            "iso_3166_1": "name text, alpha2 text",
        }
        with sqlite3.connect(self.db) as con:
            for table in sorted(probe.TABLES):
                definition = schemas.get(table, "test_sentinel integer")
                con.execute("CREATE TABLE " + table + " (" + definition + ")")
            con.execute(
                "INSERT INTO version VALUES('2025-12-12-1-ref-scheme')"
            )
            con.execute(
                "INSERT INTO locations VALUES(1, '', '(unknown)', '', '')"
            )
            con.execute(
                "INSERT INTO languages VALUES('', '(unknown)')"
            )
            con.execute(
                "INSERT INTO sites VALUES(?, ?)",
                (1, json.dumps({"collect": 1, "ignore_ips": ""})),
            )
            con.execute(
                "INSERT INTO store VALUES('session', ?)",
                (
                    json.dumps(
                        {
                            "sessions": {},
                            "hashes": {},
                            "paths": {},
                            "seen": {},
                        },
                        separators=(",", ":"),
                    ),
                ),
            )
            con.execute(
                "INSERT INTO users VALUES(5, 1, 'goatcounter-probe@example.com')"
            )
            con.execute(
                "INSERT INTO api_tokens VALUES(7, 1, 5, "
                "'synthetic-count-only', ?, '2', '[1]')",
                ("synthetic-disposable-token",),
            )
            con.execute(
                "INSERT INTO paths VALUES(1, 9, ?)",
                ("/coloring-page/" + self.id,),
            )
            con.execute("INSERT INTO refs VALUES(1, '', 'o')")
            con.execute(
                "INSERT INTO hit_counts VALUES(1, 9, '2026-10-25 11:00:00', 2)"
            )
            con.execute(
                "INSERT INTO ref_counts VALUES(1, 9, 1, '2026-10-25 11:00:00', 2)"
            )
            hours = [0] * 24
            hours[11] = 2
            con.execute(
                "INSERT INTO hit_stats VALUES(1, 9, ?, ?)",
                ("2026-10-25", json.dumps(hours)),
            )

    def mutate(self, sql, args=()):
        with sqlite3.connect(self.db) as con:
            con.execute(sql, args)

    def run_probe(self):
        return probe.inspect_fixture(
            self.root, page_id=self.id, expected_views=self.views
        )

    def assert_stops(self, code):
        with self.assertRaisesRegex(probe.ProbeStop, "^" + code + "$"):
            self.run_probe()

    def test_structural_baseline_and_leading_zero_string(self):
        self.assertEqual(
            self.run_probe(),
            "PASS_STRUCTURAL_SYNTHETIC_ONLY_NOT_RUNTIME_OR_PRIVACY_PROOF",
        )

    def test_synthetic_user_is_required(self):
        self.mutate("DELETE FROM users")
        self.assert_stops("SYNTHETIC_USER_SCOPE")

    def test_unexpected_second_user_rejected(self):
        self.mutate(
            "INSERT INTO users VALUES(6, 1, 'extra@example.com')"
        )
        self.assert_stops("SYNTHETIC_USER_SCOPE")

    def test_unexpected_user_identity_rejected(self):
        self.mutate(
            "UPDATE users SET email='visitor@example.com'"
        )
        self.assert_stops("SYNTHETIC_USER_SCOPE")

    def test_missing_api_token_rejected(self):
        self.mutate("DELETE FROM api_tokens")
        self.assert_stops("API_TOKEN_COUNT")

    def test_extra_api_token_rejected(self):
        self.mutate(
            "INSERT INTO api_tokens VALUES("
            "8, 1, 5, 'synthetic-count-only', "
            "'synthetic-second-token', '2', '[1]')"
        )
        self.assert_stops("API_TOKEN_COUNT")

    def test_elevated_api_token_permissions_rejected(self):
        for permissions in ("4", "6", "64", "3", "0", "true", '"2"'):
            with self.subTest(permissions=permissions):
                self.mutate(
                    "UPDATE api_tokens SET permissions=?",
                    (permissions,),
                )
                self.assert_stops("API_TOKEN_NOT_COUNT_ONLY")

    def test_unparsable_api_token_permissions_rejected(self):
        self.mutate("UPDATE api_tokens SET permissions='not-json'")
        self.assert_stops("API_TOKEN_JSON")

    def test_wildcard_or_cross_site_api_token_scopes_rejected(self):
        for sites in ("[-1]", "[1, 2]", "[2]", "[]", '["1"]'):
            with self.subTest(sites=sites):
                self.mutate("UPDATE api_tokens SET sites=?", (sites,))
                self.assert_stops("API_TOKEN_NOT_COUNT_ONLY")

    def test_api_token_site_and_owner_must_match(self):
        for column, value in (("site_id", 2), ("user_id", 6)):
            with self.subTest(column=column):
                self.mutate(
                    "UPDATE api_tokens SET " + column + "=?",
                    (value,),
                )
                self.assert_stops("API_TOKEN_NOT_COUNT_ONLY")
                self.mutate(
                    "UPDATE api_tokens SET " + column + "=?",
                    (1 if column == "site_id" else 5,),
                )

    def test_api_token_metadata_and_length_gate(self):
        self.mutate(
            "UPDATE api_tokens SET name='synthetic-admin-token'"
        )
        self.assert_stops("API_TOKEN_NOT_COUNT_ONLY")
        self.mutate(
            "UPDATE api_tokens SET name='synthetic-count-only', "
            "token='short'"
        )
        self.assert_stops("API_TOKEN_NOT_COUNT_ONLY")

    def test_unknown_country_lookup_table_is_present_but_empty(self):
        self.mutate("INSERT INTO iso_3166_1 VALUES('Injected', 'ZZ')")
        self.assert_stops("FORBIDDEN_ROWS_ISO_3166_1")

    def test_additional_location_rows_are_rejected(self):
        self.mutate(
            "INSERT INTO locations VALUES(2, 'DE', 'Germany', 'NW', 'NRW')"
        )
        self.assert_stops("LOCATION_LOOKUP_NOT_STATIC")

    def test_changed_location_sentinel_is_rejected(self):
        self.mutate(
            "UPDATE locations SET country_name='203.0.113.7'"
        )
        self.assert_stops("LOCATION_LOOKUP_NOT_STATIC")

    def test_added_language_row_does_not_fit_exact_pinned_counts(self):
        self.mutate(
            "INSERT INTO languages VALUES('eng', 'English')"
        )
        self.assert_stops("LANGUAGE_LOOKUP_COUNT")

    def test_changed_language_sentinel_is_rejected(self):
        self.mutate(
            "UPDATE languages SET name='Visitor synthetic' WHERE iso_639_3=''"
        )
        self.assert_stops("LANGUAGE_LOOKUP_SENTINEL")

    def test_full_pinned_language_reference_count_is_accepted(self):
        # Reference-table shape only: these are all synthetic labels, NOT
        # the actual bundled upstream language names.
        rows = []
        for chars in itertools.product("abcdefghijklmnopqrstuvwxyz", repeat=3):
            if len(rows) == 7086:
                break
            rows.append(("".join(chars), "Synthetic reference name"))
        with sqlite3.connect(self.db) as con:
            con.executemany(
                "INSERT INTO languages (iso_639_3, name) VALUES(?, ?)",
                rows,
            )
        self.assertEqual(
            self.run_probe(),
            "PASS_STRUCTURAL_SYNTHETIC_ONLY_NOT_RUNTIME_OR_PRIVACY_PROOF",
        )

    def test_invalid_language_label_rejected_with_full_reference_count(self):
        rows = []
        for chars in itertools.product("abcdefghijklmnopqrstuvwxyz", repeat=3):
            if len(rows) == 7086:
                break
            rows.append(("".join(chars), "Synthetic reference name"))
        with sqlite3.connect(self.db) as con:
            con.executemany(
                "INSERT INTO languages (iso_639_3, name) VALUES(?, ?)",
                rows,
            )
        self.mutate(
            "UPDATE languages SET name='visitor\nheader' WHERE iso_639_3='aaa'"
        )
        self.assert_stops("LANGUAGE_LOOKUP_SHAPE")

    def test_zero_collect_rejected(self):
        self.mutate("UPDATE sites SET settings='{\"collect\": 0}'")
        self.assert_stops("SITE_COLLECTION_NOT_MINIMAL")

    def test_any_non_aggregate_collection_bits_rejected(self):
        for collect in (2, 4, 16, 128, 190, 257):
            with self.subTest(collect=collect):
                self.mutate(
                    "UPDATE sites SET settings=?",
                    (json.dumps({"collect": collect, "ignore_ips": ""}),),
                )
                self.assert_stops("SITE_COLLECTION_NOT_MINIMAL")

    def test_boolean_collect_rejected(self):
        self.mutate("UPDATE sites SET settings='{\"collect\": true}'")
        self.assert_stops("SITE_COLLECTION_NOT_MINIMAL")

    def test_nonempty_text_ip_ignore_rejected(self):
        self.mutate(
            "UPDATE sites SET settings=?",
            (json.dumps({"collect": 1, "ignore_ips": "203.0.113.1"}),),
        )
        self.assert_stops("SITE_COLLECTION_NOT_MINIMAL")

    def test_array_ip_ignore_representation_rejected(self):
        self.mutate(
            "UPDATE sites SET settings=?",
            (json.dumps({"collect": 1, "ignore_ips": []}),),
        )
        self.assert_stops("SITE_COLLECTION_NOT_MINIMAL")

    def test_individual_hit_record_rejected(self):
        self.mutate(
            "INSERT INTO hits VALUES(1, 9, ?, '2026-10-25 11:08:00')",
            (b"opaque-session",),
        )
        self.assert_stops("FORBIDDEN_ROWS_HITS")

    def test_bot_raw_user_agent_record_rejected(self):
        self.mutate(
            "INSERT INTO bots VALUES(1, ?, 20, ?, '2026-10-25 11:05:00')",
            ("/coloring-page/0427183", "SyntheticBot/1.0"),
        )
        self.assert_stops("FORBIDDEN_ROWS_BOTS")

    def test_empty_shutdown_session_housekeeping_is_permitted(self):
        self.assertEqual(
            self.run_probe(),
            "PASS_STRUCTURAL_SYNTHETIC_ONLY_NOT_RUNTIME_OR_PRIVACY_PROOF",
        )

    def test_missing_shutdown_session_housekeeping_rejected(self):
        self.mutate("DELETE FROM store")
        self.assert_stops("SESSION_STORE_SHAPE")

    def test_extra_store_row_rejected(self):
        self.mutate("INSERT INTO store VALUES('other', '{}')")
        self.assert_stops("SESSION_STORE_SHAPE")

    def test_wrong_store_key_rejected(self):
        self.mutate("UPDATE store SET key='other'")
        self.assert_stops("SESSION_STORE_SHAPE")

    def test_malformed_session_store_json_rejected(self):
        self.mutate("UPDATE store SET value='not-json'")
        self.assert_stops("SESSION_STORE_JSON")

    def test_session_store_requires_exact_empty_map_shape(self):
        payloads = (
            {},
            {"sessions": {}, "hashes": {}, "paths": {}},
            {
                "sessions": {},
                "hashes": {},
                "paths": {},
                "seen": {},
                "extra": {},
            },
            {"sessions": [], "hashes": {}, "paths": {}, "seen": {}},
            {
                "sessions": {"visitor": "synthetic"},
                "hashes": {},
                "paths": {},
                "seen": {},
            },
            {
                "sessions": {},
                "hashes": {"visitor": "synthetic"},
                "paths": {},
                "seen": {},
            },
            {
                "sessions": {},
                "hashes": {},
                "paths": {"visitor": {}},
                "seen": {},
            },
            {
                "sessions": {},
                "hashes": {},
                "paths": {},
                "seen": {"visitor": 1},
            },
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                self.mutate(
                    "UPDATE store SET value=?",
                    (json.dumps(payload, separators=(",", ":")),),
                )
                self.assert_stops("SESSION_STORE_NOT_EMPTY")
                self.mutate(
                    "UPDATE store SET value=?",
                    (
                        json.dumps(
                            {
                                "sessions": {},
                                "hashes": {},
                                "paths": {},
                                "seen": {},
                            },
                            separators=(",", ":"),
                        ),
                    ),
                )

    def test_personal_dimensions_rejected(self):
        for table in ("browser_stats", "location_stats", "campaign_stats"):
            with self.subTest(table=table):
                self.mutate("INSERT INTO " + table + " VALUES(1)")
                self.assert_stops("FORBIDDEN_ROWS_" + table.upper())
                self.mutate("DELETE FROM " + table)

    def test_nonblank_referrer_rejected(self):
        self.mutate(
            "INSERT INTO refs VALUES(2, 'https://example.invalid/', 'u')"
        )
        self.assert_stops("REFERRER_STORED")

    def test_no_referrer_aggregation_is_permitted(self):
        self.assertEqual(
            self.run_probe(),
            "PASS_STRUCTURAL_SYNTHETIC_ONLY_NOT_RUNTIME_OR_PRIVACY_PROOF",
        )

    def test_wrong_referrer_id_rejected(self):
        self.mutate("UPDATE ref_counts SET ref_id=2")
        self.assert_stops("REF_AGGREGATE_ROW_INVALID")

    def test_non_matching_referrer_aggregation_rejected(self):
        self.mutate("UPDATE ref_counts SET total=4")
        self.assert_stops("REF_AGGREGATE_MISMATCH")

    def test_missing_referrer_aggregate_rejected(self):
        self.mutate("DELETE FROM ref_counts")
        self.assert_stops("REF_AGGREGATE_MISMATCH")

    def test_duplicate_referrer_hour_rejected(self):
        self.mutate(
            "INSERT INTO ref_counts VALUES(1, 9, 1, '2026-10-25 11:00:00', 2)"
        )
        self.assert_stops("REF_AGGREGATE_DUPLICATE_HOUR")

    def test_daily_array_must_have_exactly_24_hours(self):
        self.mutate("UPDATE hit_stats SET stats='[0,2,0]'")
        self.assert_stops("DAILY_STATS_FORMAT")

    def test_daily_array_cannot_contain_identifiers(self):
        values = [0] * 24
        values[11] = "SyntheticVisitorID"
        self.mutate(
            "UPDATE hit_stats SET stats=?", (json.dumps(values),)
        )
        self.assert_stops("DAILY_STATS_FORMAT")

    def test_daily_array_rejects_boolean_counts(self):
        values = [0] * 24
        values[11] = True
        self.mutate(
            "UPDATE hit_stats SET stats=?", (json.dumps(values),)
        )
        self.assert_stops("DAILY_STATS_FORMAT")

    def test_daily_array_cannot_disagree_with_hourly_total(self):
        values = [0] * 24
        values[10] = 2
        self.mutate(
            "UPDATE hit_stats SET stats=?", (json.dumps(values),)
        )
        self.assert_stops("DAILY_COUNTS_MISMATCH")

    def test_missing_daily_aggregation_rejected(self):
        self.mutate("DELETE FROM hit_stats")
        self.assert_stops("NO_DAILY_STATS")

    def test_duplicate_daily_aggregation_rejected(self):
        self.mutate(
            "INSERT INTO hit_stats SELECT * FROM hit_stats"
        )
        self.assert_stops("DAILY_ROW_DUPLICATE")

    def test_duplicate_hourly_aggregation_rejected(self):
        self.mutate(
            "INSERT INTO hit_counts VALUES(1, 9, '2026-10-25 11:00:00', 2)"
        )
        self.assert_stops("AGGREGATE_DUPLICATE_HOUR")

    def test_arbitrary_or_unpublished_page_rejected(self):
        self.mutate(
            "UPDATE paths SET path='/coloring-page/extra?ip=203.0.113.1'"
        )
        self.assert_stops("PATH_ALLOWLIST")

    def test_aggregate_count_mismatch_rejected(self):
        self.mutate("UPDATE hit_counts SET total=3")
        self.assert_stops("PAGEVIEW_TOTAL_MISMATCH")

    def test_other_page_in_hourly_aggregate_rejected(self):
        self.mutate("UPDATE hit_counts SET path_id=123")
        self.assert_stops("AGGREGATE_ROW_INVALID")

    def test_bad_hour_boundary_rejected(self):
        self.mutate("UPDATE hit_counts SET hour='2026-10-25 11:02:00'")
        self.assert_stops("AGGREGATE_ROW_INVALID")

    def test_missing_upstream_version_migration_rejected(self):
        self.mutate("DELETE FROM version")
        self.assert_stops("VERSION_MIGRATION_IDENTITY")

    def test_fake_version_name_rejected(self):
        self.mutate("INSERT INTO version VALUES(?)", ("visitor:203.0.113.7",))
        self.assert_stops("VERSION_MIGRATION_IDENTITY")

    def test_unknown_schema_table_rejected(self):
        self.mutate("CREATE TABLE visitor_ids (ip text)")
        self.assert_stops("SCHEMA_IDENTITY")

    def test_uncheckpointed_wal_rejected(self):
        (self.root / (probe.DB_NAME + "-wal")).write_bytes(b"synthetic")
        self.assert_stops("UNCHECKPOINTED_SQLITE")

    def test_missing_fixture_marker_rejected(self):
        (self.root / probe.MARKER).unlink()
        self.assert_stops("SYNTHETIC_FIXTURE_MARKER")

    def test_other_path_outside_isolated_temp_rejected(self):
        with self.assertRaisesRegex(
            probe.ProbeStop, "^NOT_ISOLATED_TEMP_ROOT$"
        ):
            probe.inspect_fixture(
                ROOT, page_id=self.id, expected_views=self.views
            )

    def test_disallowed_test_id_type_rejected(self):
        with self.assertRaisesRegex(probe.ProbeStop, "^EXPECTED_PUBLIC_ID$"):
            probe.inspect_fixture(self.root, page_id=427183, expected_views=2)

    def test_cli_stop_output_discloses_no_raw_database_data(self):
        self.mutate(
            "INSERT INTO bots VALUES(1, ?, 20, ?, '2026-10-25 11:05:00')",
            ("/coloring-page/0427183", "PrivateSyntheticAgent/123"),
        )
        stream = io.StringIO()
        with mock.patch(
            "sys.argv",
            ["probe", "--synthetic-test-root", str(self.root),
             "--expected-page-id", self.id, "--expected-views", "2"],
        ), contextlib.redirect_stdout(stream):
            status = probe.main()
        self.assertEqual(status, 2)
        self.assertEqual(
            stream.getvalue().strip(),
            "GOATCOUNTER_OFFLINE=STOP CODE=FORBIDDEN_ROWS_BOTS",
        )


if __name__ == "__main__":
    unittest.main()
