#!/usr/bin/env python3
"""Synthetic aggregate/API boundary tests; never contact production."""
import copy
from datetime import datetime, timedelta, timezone
from email.message import Message
from importlib.machinery import SourceFileLoader
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
loader = SourceFileLoader("origin_admin", str(ROOT / "ops/bin/coloring-pages-admin-publish"))
spec = importlib.util.spec_from_loader(loader.name, loader)
admin = importlib.util.module_from_spec(spec)
loader.exec_module(admin)
NOW = datetime(2026, 11, 2, 10, 30, tzinfo=timezone.utc)
TOKEN = "synthetic-credential-00000000000000"


class Fixture:
    def __init__(self, days=7):
        self.days = days
        self.calls = []
        self.me = {"user": {"site": 1, "email": "PRIVATE_EMAIL", "settings": {"timezone": ".UTC"}},
                   "token": {"permissions": 64, "sites": [1]}}
        self.paths = [{"id": 1, "path": "/old-browser-counter/0123456", "event": False},
                      {"id": 2, "path": "/", "event": False},
                      {"id": 3, "path": "/ausmalbild/0123456", "event": False},
                      {"id": 4, "path": "/ausmalbild/7654321", "event": False},
                      {"id": 5, "path": "/ausmalbild/9999999", "event": True},
                      {"id": 6, "path": "/ausmalbild/0123456?private=x", "event": False},
                      {"id": 7, "path": "/origin-detail-request/0123456", "event": False}]
        self.payload = {"more": False, "total": 6,
                        "hits": [self.hit(2, 1), self.hit(3, 3), self.hit(4, 2)]}
        self.dimensions = {
            "toprefs": {"more": False, "stats": [
                {"id": "1", "name": "https://example.org/private/path?x=1", "count": 3, "ref_scheme": "h"},
                {"id": "2", "name": "", "count": 1, "ref_scheme": "o"},
                {"id": "3", "name": "profile", "count": 2, "ref_scheme": "c"}]},
            "campaigns": {"more": False, "stats": [{"id": "1", "name": "profile", "count": 2}]},
            "locations": {"more": False, "stats": [{"id": "DE", "name": "Germany", "count": 5}]},
            "browsers": {"more": False, "stats": [{"id": "1", "name": "Firefox", "count": 4}]},
            "systems": {"more": False, "stats": [{"id": "1", "name": "Android", "count": 3}]},
            "sizes": {"more": False, "stats": [{"id": "390", "name": "390", "count": 3}]},
        }

    def hit(self, ident, count):
        date = NOW.date() - timedelta(days=self.days - 1)
        stats = [{"day": (date + timedelta(days=i)).isoformat(), "hourly": [0] * 24, "daily": 0}
                 for i in range(self.days)]
        stats[-1].update(hourly=[count] + [0] * 23, daily=count)
        return {"path_id": ident, "path": next(p["path"] for p in self.paths if p["id"] == ident),
                "title": "PRIVATE_TITLE", "event": False, "count": count, "stats": stats}

    def get(self, target, token, budget):
        self.calls.append(target)
        if target == "/api/v0/me":
            return copy.deepcopy(self.me)
        if target.startswith("/api/v0/paths?"):
            q = parse_qs(urlsplit(target).query)
            after = int(q["after"][0])
            remaining = [p for p in self.paths if p["id"] > after]
            # Deliberately paginate sooner than the requested limit.
            return {"paths": remaining[:2], "more": len(remaining) > 2}
        q = parse_qs(urlsplit(target).query)
        assert q["include_paths"] == ["2,3,4"]
        assert q["start"] == [(NOW.date() - timedelta(days=self.days - 1)).isoformat() + "T00:00:00Z"]
        assert q["end"] == ["2026-11-02T23:00:00Z"]
        if target.startswith("/api/v0/stats/hits?"):
            return copy.deepcopy(self.payload)
        page = target.split("/api/v0/stats/", 1)[1].split("?", 1)[0]
        return copy.deepcopy(self.dimensions[page])


class KitaFixture:
    def __init__(self, days=7):
        self.days = days
        self.calls = []
        self.me = {"user": {"site": 1, "email": "PRIVATE_EMAIL",
                            "settings": {"timezone": ".UTC"}},
                   "token": {"permissions": 64, "sites": [1]}}
        self.paths = [
            {"id": 1, "path": "/other", "event": False},
            {"id": 2, "path": "/kita", "event": False},
            {"id": 3, "path": "/kita/herbst", "event": False},
            {"id": 4, "path": "/kita?private=x", "event": False},
            {"id": 5, "path": "/kita/private", "event": False},
            {"id": 6, "path": "/kita", "event": True},
        ]
        self.payload = {"more": False, "total": 6,
                        "hits": [self.hit(2, 4), self.hit(3, 2)]}

    def hit(self, ident, count):
        date = NOW.date() - timedelta(days=self.days - 1)
        stats = [{"day": (date + timedelta(days=i)).isoformat(),
                  "hourly": [0] * 24, "daily": 0}
                 for i in range(self.days)]
        stats[-1].update(hourly=[count] + [0] * 23, daily=count)
        return {"path_id": ident,
                "path": next(p["path"] for p in self.paths if p["id"] == ident),
                "title": "PRIVATE_TITLE", "event": False,
                "count": count, "stats": stats}

    def get(self, target, token, budget):
        self.calls.append(target)
        if target == "/api/v0/me":
            return copy.deepcopy(self.me)
        if target.startswith("/api/v0/paths?"):
            q = parse_qs(urlsplit(target).query)
            after = int(q["after"][0])
            remaining = [p for p in self.paths if p["id"] > after]
            return {"paths": copy.deepcopy(remaining[:2]),
                    "more": len(remaining) > 2}
        q = parse_qs(urlsplit(target).query)
        expected_ids = [str(p["id"]) for p in self.paths
                        if p["event"] is False
                        and p["path"] in admin.KITA_PUBLIC_PATHS]
        assert q["include_paths"] == [",".join(expected_ids)]
        assert q["start"] == [
            (NOW.date() - timedelta(days=self.days - 1)).isoformat()
            + "T00:00:00Z"
        ]
        assert q["end"] == ["2026-11-02T23:00:00Z"]
        assert target.startswith("/api/v0/stats/hits?")
        return copy.deepcopy(self.payload)


class ReportTests(unittest.TestCase):
    def collect(self, fixture):
        reader = admin.OriginReportReader()
        reader.get = fixture.get
        return reader.collect(fixture.days, NOW, TOKEN)

    def collect_kita(self, fixture):
        reader = admin.KitaReportReader()
        reader.get = fixture.get
        return reader.collect(fixture.days, NOW, TOKEN)

    def test_kita_report_all_ranges_are_fixed_sanitized_aggregates(self):
        expected = [
            {"path": "/kita", "visits": 4},
            {"path": "/kita/herbst", "visits": 2},
        ]
        for days in (1, 7, 30, 365):
            with self.subTest(days=days):
                fixture = KitaFixture(days)
                result = self.collect_kita(fixture)
                self.assertEqual((result["version"], result["metric"]),
                                 (1, "goatcounter_visits"))
                self.assertEqual(result["range_days"], days)
                self.assertEqual(result["paths"], expected)
                self.assertEqual(set(result), {
                    "version", "status", "metric", "range_days", "timezone",
                    "start_day", "end_day", "today_partial", "generated_at",
                    "cache_seconds", "paths",
                })
                serialized = json.dumps(result)
                self.assertNotIn("PRIVATE", serialized)
                self.assertNotIn("?private=", serialized)
                self.assertNotIn("/kita/private", serialized)

    def test_kita_report_absent_allowlisted_path_is_valid_zero(self):
        fixture = KitaFixture()
        fixture.paths = [p for p in fixture.paths
                         if p["path"] != "/kita/herbst"]
        fixture.payload = {"more": False, "total": 4,
                           "hits": [fixture.hit(2, 4)]}
        self.assertEqual(self.collect_kita(fixture)["paths"], [
            {"path": "/kita", "visits": 4},
            {"path": "/kita/herbst", "visits": 0},
        ])

    def test_kita_report_no_allowlisted_paths_avoids_unfiltered_stats(self):
        fixture = KitaFixture()
        fixture.paths = [
            {"id": 1, "path": "/other", "event": False},
            {"id": 2, "path": "/kita?private=x", "event": False},
        ]
        result = self.collect_kita(fixture)
        self.assertEqual(result["paths"], [
            {"path": "/kita", "visits": 0},
            {"path": "/kita/herbst", "visits": 0},
        ])
        self.assertFalse(any("/stats/" in call for call in fixture.calls))

    def test_kita_report_rejects_duplicate_or_inconsistent_stats(self):
        duplicate = KitaFixture()
        duplicate.paths.append({"id": 7, "path": "/kita", "event": False})
        duplicate.paths.sort(key=lambda row: row["id"])
        with self.assertRaises(ValueError):
            self.collect_kita(duplicate)

        wrong = KitaFixture()
        wrong.payload["hits"][0]["path"] = "/kita/private"
        with self.assertRaises(ValueError):
            self.collect_kita(wrong)

        inconsistent = KitaFixture()
        inconsistent.payload["total"] = 7
        with self.assertRaises(ValueError):
            self.collect_kita(inconsistent)

    def test_kita_endpoint_is_exact_admin_only_and_has_no_path_filter(self):
        for target, headers, expected in (
            ("/api/analytics/kita?days=7", {}, 403),
            ("/api/analytics/kita?days=7",
             {"X-Ausmalwiese-Admin": "1", "Sec-Fetch-Site": "cross-site"}, 403),
            ("/api/analytics/kita?days=7",
             {"X-Ausmalwiese-Admin": "1", "Origin": "https://other.invalid"}, 403),
            ("/api/analytics/kita?days=7&paths=%2Fkita",
             {"X-Ausmalwiese-Admin": "1"}, 404),
            ("/api/analytics/kita?days=8",
             {"X-Ausmalwiese-Admin": "1"}, 404),
            ("/api/analytics/kita?days=7",
             {"X-Ausmalwiese-Admin": "1"}, 200),
        ):
            with self.subTest(target=target):
                handler = object.__new__(admin.Handler)
                handler.path, handler.headers = target, headers
                handler.send_json = Mock()
                handler.send_error_json = lambda status, _message: handler.send_json(status, {})
                with patch.object(admin.KITA_REPORT_READER, "snapshot",
                                  return_value={"paths": []}) as snapshot:
                    handler.do_GET()
                    self.assertEqual(handler.send_json.call_args.args[0], expected)
                    self.assertEqual(snapshot.call_count, int(expected == 200))

        handler = object.__new__(admin.Handler)
        handler.path = "/api/analytics/kita?days=7"
        handler.headers = {"X-Ausmalwiese-Admin": "1"}
        handler.send_json = Mock()
        with patch.object(admin.KITA_REPORT_READER, "snapshot",
                          side_effect=admin.OriginReportUnavailable()):
            handler.do_GET()
            self.assertEqual(handler.send_json.call_args.args,
                             (503, {"version": 1, "status": "unavailable"}))

    def test_all_ranges_only_consent_namespace_and_safe_output(self):
        for days in (1, 7, 30, 365):
            with self.subTest(days=days):
                fixture = Fixture(days)
                result = self.collect(fixture)
                self.assertEqual((result["version"], result["metric"]), (3, "goatcounter_visits"))
                self.assertEqual(result["total"], 6)
                self.assertEqual(result["homepage_visits"], 1)
                self.assertEqual(result["ausmalbild_visits"], 5)
                self.assertEqual(result["pages"], [{"page_id": "0123456", "visits": 3},
                                                   {"page_id": "7654321", "visits": 2}])
                self.assertEqual(len(result["daily"]), days)
                self.assertEqual(sum(row["visits"] for row in result["daily"]), 6)
                self.assertEqual(result["referrers"], [
                    {"label": "https://example.org", "visits": 3},
                    {"label": "Direct / no referrer", "visits": 1},
                ])
                self.assertEqual(result["campaigns"], [{"label": "profile", "visits": 2}])
                self.assertEqual(result["locations"], [{"label": "Germany", "visits": 5}])
                self.assertEqual(result["browsers"], [{"label": "Firefox", "visits": 4}])
                self.assertEqual(result["systems"], [{"label": "Android", "visits": 3}])
                self.assertEqual(result["sizes"], [{"label": "390", "visits": 3}])
                self.assertNotIn("PRIVATE", json.dumps(result))
                self.assertNotIn("/private/path", json.dumps(result))
                self.assertEqual(len(fixture.calls), 12)

    def test_365_day_stats_use_bounded_path_batches(self):
        fixture = Fixture(365)
        fixture.paths = [{"id": 1, "path": "/", "event": False}] + [
            {"id": i + 1, "path": "/ausmalbild/" + str(2000000 + i), "event": False}
            for i in range(1, 13)
        ]
        queried = []
        def get(target, token, budget):
            if target == "/api/v0/me":
                return copy.deepcopy(fixture.me)
            if target.startswith("/api/v0/paths?"):
                return {"paths": copy.deepcopy(fixture.paths), "more": False}
            self.assertTrue(target.startswith("/api/v0/stats/hits?"))
            selected = parse_qs(urlsplit(target).query)["include_paths"][0].split(",")
            self.assertGreater(len(selected), 0)
            self.assertLessEqual(len(selected), 20)
            queried.extend(selected)
            return {"hits": [], "more": False, "total": 0}
        original_get = get
        def get_with_dimensions(target, token, budget):
            if target.startswith("/api/v0/stats/") and not target.startswith("/api/v0/stats/hits?"):
                return {"stats": [], "more": False}
            return original_get(target, token, budget)
        reader = admin.OriginReportReader()
        reader.get = get_with_dimensions
        report = reader.collect(365, NOW, TOKEN)
        self.assertEqual(report["total"], 0)
        self.assertEqual(report["pages"], [])
        self.assertEqual(len(report["daily"]), 365)
        self.assertEqual(queried, [str(i) for i in range(1, 14)])

    def test_unrelated_namespaces_never_request_unfiltered_stats(self):
        fixture = Fixture()
        fixture.paths = [fixture.paths[0], fixture.paths[-1]]
        result = self.collect(fixture)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["homepage_visits"], 0)
        self.assertEqual(result["ausmalbild_visits"], 0)
        self.assertEqual(result["pages"], [])
        self.assertFalse(any("/stats/" in target for target in fixture.calls))

    def test_known_paths_without_activity_are_empty_not_missing_capability(self):
        fixture = Fixture()
        fixture.payload = {"more": False, "hits": [], "total": 0}
        self.assertEqual(self.collect(fixture)["total"], 0)

    def test_wrong_token_permissions_site_or_timezone_rejected_before_paths(self):
        for key, value in (("permissions", 2), ("permissions", 66), ("sites", ["all"]), ("sites", [1, 2])):
            fixture = Fixture()
            fixture.me["token"][key] = value
            with self.assertRaises(ValueError):
                self.collect(fixture)
            self.assertEqual(fixture.calls, ["/api/v0/me"])
        for zone in ("Europe/Berlin", "DE.Europe/Berlin", "UTC+01:00", "", None):
            fixture = Fixture()
            fixture.me["user"]["settings"]["timezone"] = zone
            with self.assertRaises(ValueError):
                self.collect(fixture)
            self.assertEqual(fixture.calls, ["/api/v0/me"])

    def test_serialized_utc_and_plain_utc_names(self):
        for zone in (".UTC", "UTC", "Etc/UTC"):
            fixture = Fixture()
            fixture.me["user"]["settings"]["timezone"] = zone
            self.assertEqual(self.collect(fixture)["total"], 6)

    def test_reject_incomplete_inconsistent_or_unrelated_aggregates(self):
        mutations = [lambda p: p.update(more=True), lambda p: p.update(total=7),
                     lambda p: p["hits"][0].update(path="/unrelated"),
                     lambda p: p["hits"][0].update(event=True),
                     lambda p: p["hits"][0].update(count=-1),
                     lambda p: p["hits"][0].update(count=True),
                     lambda p: p["hits"][0].update(count=2**53),
                     lambda p: p["hits"][0].update(stats=p["hits"][0]["stats"][:-1]),
                     lambda p: p["hits"][0]["stats"][0].update(day="2025-01-01"),
                     lambda p: p["hits"][0]["stats"][0].update(hourly=[1] * 24),
                     lambda p: p["hits"][0].update(path_id=True),
                     lambda p: p["hits"].__setitem__(1, p["hits"][0])]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                fixture = Fixture()
                mutation(fixture.payload)
                with self.assertRaises(ValueError):
                    self.collect(fixture)

    def test_pagination_limit_and_cursor_reject_without_partial_result(self):
        reader = admin.OriginReportReader()
        calls = []
        def get(target, token, budget):
            calls.append(target)
            if target == "/api/v0/me":
                return Fixture().me
            after = int(parse_qs(urlsplit(target).query)["after"][0])
            return {"more": True, "paths": [{"id": after + 1, "path": "/other", "event": False}]}
        reader.get = get
        with self.assertRaises(ValueError):
            reader.collect(7, NOW, TOKEN)
        self.assertEqual(len(calls), 11)
        reader.get = lambda target, token, budget: Fixture().me if target == "/api/v0/me" else {
            "more": True, "paths": [{"id": 0, "path": "/other", "event": False}]}
        with self.assertRaises(ValueError):
            reader.collect(7, NOW, TOKEN)

    def test_cache_busy_failure_and_not_configured_are_not_zero(self):
        reader = admin.OriginReportReader()
        reader.collect = Mock(return_value={"total": 5})
        with patch.object(admin, "origin_credential", return_value=TOKEN):
            self.assertEqual(reader.snapshot(7), {"total": 5})
            reader.snapshot(7)
            self.assertEqual(reader.collect.call_count, 1)
            reader.lock.acquire()
            with self.assertRaises(admin.OriginReportUnavailable) as raised:
                reader.snapshot(7)
            self.assertEqual(raised.exception.status, "busy")
            reader.lock.release()
            reader.cache.clear()
            reader.collect.side_effect = ValueError("PRIVATE upstream message")
            with self.assertRaises(admin.OriginReportUnavailable) as raised:
                reader.snapshot(7)
            self.assertEqual(raised.exception.status, "unavailable")
            self.assertFalse(reader.cache)
        with patch.object(admin, "origin_credential", side_effect=admin.OriginReportUnavailable("not_configured")):
            with self.assertRaises(admin.OriginReportUnavailable) as raised:
                reader.snapshot(7)
            self.assertEqual(raised.exception.status, "not_configured")

    def test_only_systemd_credential_regular_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stats"
            with patch.object(admin, "ORIGIN_REPORT_CREDENTIAL", path):
                with self.assertRaises(admin.OriginReportUnavailable):
                    admin.origin_credential()
                path.write_text(TOKEN + "\n")
                path.chmod(0o400)
                self.assertEqual(admin.origin_credential(), TOKEN)
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    admin.origin_credential()
                path.unlink()
                path.symlink_to(Path(directory) / "absent")
                with self.assertRaises(OSError):
                    admin.origin_credential()

    def test_http_transport_is_fixed_get_no_redirect_or_proxy(self):
        reader = admin.OriginReportReader()
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.getheader.side_effect = lambda name, default=None: "application/json" if name == "Content-Type" else default
        response.read1.side_effect = [b'{"ok":true}', b'']
        with patch.object(admin.http.client, "HTTPConnection", return_value=connection) as factory:
            budget = {"deadline": time.monotonic() + 10, "requests": 0, "bytes": 0}
            self.assertEqual(reader.get("/api/v0/me", TOKEN, budget), {"ok": True})
            self.assertEqual(factory.call_args.args, ("127.0.0.1", 9194))
            self.assertEqual(connection.request.call_args.args, ("GET", "/api/v0/me"))
            headers = connection.request.call_args.kwargs["headers"]
            self.assertEqual(headers["Host"], "goatcounter.ausmalwiese.invalid")
            self.assertEqual(set(headers), {"Host", "Authorization", "Accept", "Connection"})
            reader.next_request = 0
            response.status = 302
            with self.assertRaises(ValueError):
                reader.get("/api/v0/me", TOKEN, budget)
            self.assertEqual(factory.call_count, 2)
            self.assertEqual(connection.close.call_count, 2)

    def test_endpoint_allowlist_and_admin_boundary(self):
        for target, headers, expected in (
            ("/api/analytics/origin?days=7", {}, 403),
            ("/api/analytics/origin?days=7", {"X-Ausmalwiese-Admin": "1", "Sec-Fetch-Site": "cross-site"}, 403),
            ("/api/analytics/origin?days=7", {"X-Ausmalwiese-Admin": "1", "Origin": "https://other.invalid"}, 403),
            ("/api/analytics/origin?days=7&url=http://other", {"X-Ausmalwiese-Admin": "1"}, 404),
            ("/api/analytics/origin?days=8", {"X-Ausmalwiese-Admin": "1"}, 404),
            ("/api/analytics/origin?days=7", {"X-Ausmalwiese-Admin": "1"}, 200),
        ):
            with self.subTest(target=target, headers=headers):
                handler = object.__new__(admin.Handler)
                handler.path, handler.headers = target, headers
                handler.send_json = Mock()
                with patch.object(admin.ORIGIN_REPORT_READER, "snapshot", return_value={"total": 5}) as snapshot:
                    handler.do_GET()
                    self.assertEqual(handler.send_json.call_args.args[0], expected)
                    self.assertEqual(snapshot.call_count, int(expected == 200))
        handler.headers = {"X-Ausmalwiese-Admin": "1"}
        with patch.object(admin.ORIGIN_REPORT_READER, "snapshot", side_effect=admin.OriginReportUnavailable()):
            handler.do_GET()
            self.assertEqual(handler.send_json.call_args.args, (503, {"version": 1, "status": "unavailable"}))


if __name__ == "__main__":
    unittest.main()
