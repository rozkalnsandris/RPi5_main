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
        self.me = {"user": {"site": 1, "email": "PRIVATE_EMAIL", "settings": {"timezone": "UTC"}},
                   "token": {"permissions": 64, "sites": [1]}}
        self.paths = [{"id": 1, "path": "/old-browser-counter/0123456", "event": False},
                      {"id": 2, "path": "/origin-detail-request/0123456", "event": False},
                      {"id": 3, "path": "/origin-detail-request/7654321", "event": False},
                      {"id": 4, "path": "/origin-detail-request/9999999", "event": True},
                      {"id": 5, "path": "/origin-detail-request/0123456?private=x", "event": False}]
        self.payload = {"more": False, "total": 5, "hits": [self.hit(2, 3), self.hit(3, 2)]}

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
        assert q["include_paths"] == ["2,3"]
        assert q["start"] == [(NOW.date() - timedelta(days=self.days - 1)).isoformat() + "T00:00:00Z"]
        assert q["end"] == ["2026-11-02T23:00:00Z"]
        return copy.deepcopy(self.payload)


class ReportTests(unittest.TestCase):
    def collect(self, fixture):
        reader = admin.OriginReportReader()
        reader.get = fixture.get
        return reader.collect(fixture.days, NOW, TOKEN)

    def test_all_ranges_only_origin_namespace_and_safe_output(self):
        for days in (1, 7, 30, 365):
            with self.subTest(days=days):
                fixture = Fixture(days)
                result = self.collect(fixture)
                self.assertEqual(result["total"], 5)
                self.assertEqual(result["pages"], [{"page_id": "0123456", "requests": 3},
                                                   {"page_id": "7654321", "requests": 2}])
                self.assertEqual(len(result["daily"]), days)
                self.assertEqual(sum(row["requests"] for row in result["daily"]), 5)
                self.assertNotIn("PRIVATE", json.dumps(result))
                self.assertEqual(len(fixture.calls), 5)

    def test_empty_namespace_never_requests_unfiltered_stats(self):
        fixture = Fixture()
        fixture.paths = fixture.paths[:1]
        result = self.collect(fixture)
        self.assertEqual(result["total"], 0)
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
        fixture = Fixture()
        fixture.me["user"]["settings"]["timezone"] = "Europe/Berlin"
        with self.assertRaises(ValueError):
            self.collect(fixture)

    def test_reject_incomplete_inconsistent_or_unrelated_aggregates(self):
        mutations = [lambda p: p.update(more=True), lambda p: p.update(total=6),
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
