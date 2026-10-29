#!/usr/bin/env python3
"""Synthetic source/Unix transport tests. Never access production paths."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "origin", ROOT / "scripts/ausmalwiese_goatcounter_origin_v1.py")
origin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(origin)
CATALOG = [{"id": "0123456", "preview": "a.webp", "print": "a.png"},
           {"id": "1234567", "hidden": True, "preview": "b", "print": "b"}]
BODY = b'{"page_id":"0123456"}'
WIRE = (b"POST /internal/origin-count HTTP/1.0\r\nHost: origin-counter.invalid\r\n"
        b"Content-Type: application/json\r\nContent-Length: 21\r\nConnection: close\r\n\r\n" + BODY)


class ContractTests(unittest.TestCase):
    def test_exact_minimized_body_and_separate_prefix(self):
        self.assertEqual(json.loads(origin.payload("0123456")),
                         {"no_sessions": True, "hits": [{"path": "/origin-detail-request/0123456"}]})
        for value in ("123", "01234567", "１２３４５６７", "0123456?x=y", 1234567):
            with self.assertRaises(origin.Stop):
                origin.payload(value)

    def test_peer_binding_requires_explicit_nonroot_integer_ids(self):
        base = {"schema": "ausmalwiese.origin-peer.v1", "uid": 101, "gid": 101}
        self.assertEqual(origin.parse_peer(json.dumps(base).encode()), (101, 101))
        for value in (0, -1, True, "101", None, 2**32 - 1):
            with self.assertRaises(origin.Stop):
                origin.parse_peer(json.dumps(dict(base, uid=value)).encode())

    def test_catalog_shape_visibility_duplicates_and_multipage(self):
        self.assertEqual(origin.visible_ids(CATALOG), frozenset({"0123456"}))
        with self.assertRaises(origin.Stop):
            origin.visible_ids(CATALOG * 2)
        entry = {"id": "0123456", "pages": [{"preview": "x", "print": "y"}]}
        self.assertIn("0123456", origin.visible_ids([entry]))
        entry["pages"].append({"preview": "broken"})
        self.assertFalse(origin.visible_ids([entry]))

    def test_source_contract_and_drift(self):
        path = ROOT / "ops/contracts/ausmalwiese-goatcounter-origin-v1.json"
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(origin.main(["--check-contract", "--contract", str(path)]), 0)
        self.assertIn("SOURCE_OK_NOT_LIVE", output.getvalue())
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / "contract.json"
            bad.write_text('{"secret": "do-not-print"}')
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(origin.main(["--check-contract", "--contract", str(bad)]), 2)
            self.assertEqual(output.getvalue(), "GOATCOUNTER_ORIGIN=STOP\n")

    def test_file_symlink_and_fifo_are_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "file").write_text("synthetic")
            (root / "link").symlink_to(root / "file")
            os.mkfifo(root / "fifo")
            for path in (root / "link", root / "fifo"):
                with self.assertRaises((origin.Stop, OSError)):
                    origin.read_regular(path, 256)


class UnixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="origin-test-")
        self.root = Path(self.temp.name)
        self.catalog_path = self.root / "catalog.json"
        self.catalog_path.write_text(json.dumps(CATALOG))
        self.catalog = origin.Catalog(self.catalog_path)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.path = self.root / "origin.sock"
        self.listener.bind(str(self.path))
        self.listener.listen(8)
        self.sent = []
        self.collector = origin.Collector(self.listener, (os.getuid(), os.getgid()),
                                          self.catalog, lambda page: self.sent.append(page))
        self.thread = threading.Thread(target=self.collector.serve)
        self.thread.start()

    def tearDown(self):
        self.collector.stop.set()
        self.thread.join(timeout=1)
        self.listener.close()
        self.temp.cleanup()

    def request(self, data=WIRE):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(1)
            conn.connect(str(self.path))
            try:
                conn.sendall(data)
                conn.shutdown(socket.SHUT_WR)
                return conn.recv(1024)
            except (ConnectionResetError, BrokenPipeError):
                return b""

    def test_repeated_requests_each_have_one_attempt(self):
        for _ in range(3):
            self.assertTrue(self.request().startswith(b"HTTP/1.0 202"))
        self.assertEqual(self.sent, ["0123456"] * 3)

    def test_peer_uid_and_gid_are_checked_before_request(self):
        for peer in [(os.getuid() + 1, os.getgid()), (os.getuid(), os.getgid() + 1)]:
            self.collector.peer = peer
            self.assertEqual(self.request(), b"")
        self.assertFalse(self.sent)

    def test_headers_method_query_body_and_pipeline_rejected(self):
        variants = [WIRE.replace(b"POST ", b"GET ", 1), WIRE.replace(b"HTTP/1.0", b"HTTP/1.1"),
                    WIRE.replace(b"origin-count ", b"origin-count?x=y "),
                    WIRE.replace(b"Host:", b"Cookie: synthetic\r\nHost:"),
                    WIRE.replace(b"Host:", b"Host: origin-counter.invalid\r\nHost:"),
                    WIRE.replace(b"Content-Length: 21", b"Transfer-Encoding: chunked"),
                    WIRE.replace(BODY, b'{"page_id":"abcdefg"}'), WIRE[:-1], WIRE + WIRE,
                    WIRE.replace(b"Connection: close", b"Connection: " + b"a" * 600)]
        for data in variants:
            with self.subTest(size=len(data)):
                self.assertEqual(self.request(data), b"")
        self.assertFalse(self.sent)

    def test_current_catalog_atomic_replacement_and_no_stale_fallback(self):
        self.assertTrue(self.request())
        other = self.root / "replacement.json"
        other.write_text("[]")
        other.replace(self.catalog_path)
        self.assertFalse(self.request())
        self.catalog_path.write_text("{")
        self.assertFalse(self.request())
        self.catalog_path.unlink()
        self.assertFalse(self.request())
        self.assertEqual(self.sent, ["0123456"])

    def test_hidden_and_unknown_ids_drop(self):
        for page in (b"1234567", b"9999999"):
            self.assertFalse(self.request(WIRE.replace(b"0123456", page)))
        self.assertFalse(self.sent)

    def test_partial_headers_have_total_deadline(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(1)
            conn.connect(str(self.path))
            conn.sendall(b"POST ")
            start = time.monotonic()
            self.assertEqual(conn.recv(1024), b"")
            self.assertLess(time.monotonic() - start, 0.8)
        self.assertFalse(self.sent)

    def test_saturation_drops_without_queue_and_recovers(self):
        # Reserve all slots to model occupied workers without timing races.
        for _ in range(origin.MAX_ACTIVE):
            self.assertTrue(self.collector.slots.acquire(False))
        self.assertFalse(self.request())
        self.assertFalse(self.sent)
        for _ in range(origin.MAX_ACTIVE):
            self.collector.slots.release()
        self.assertTrue(self.request())

    def test_uncertain_backend_failure_never_retries_or_logs(self):
        sender = mock.Mock(side_effect=OSError("synthetic-sensitive-text"))
        self.collector.sender = sender
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertFalse(self.request())
        sender.assert_called_once_with("0123456")
        self.assertEqual(out.getvalue() + err.getvalue(), "")


class BackendTests(unittest.TestCase):
    def exchange(self, response, delay=0):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        got = []

        def receiver():
            with listener.accept()[0] as conn:
                conn.settimeout(1)
                head, body = origin.read_headers(conn, time.monotonic() + 1, 1024)
                length = int(next(x.split(b":", 1)[1] for x in head.split(b"\r\n")
                                  if x.startswith(b"Content-Length:")))
                while len(body) < length:
                    body += conn.recv(length - len(body))
                got.append((head, body))
                time.sleep(delay)
                try:
                    conn.sendall(response)
                except OSError:
                    pass

        thread = threading.Thread(target=receiver)
        thread.start()
        error = None
        try:
            with mock.patch.object(origin, "BACKEND", listener.getsockname()), mock.patch.dict(
                    os.environ, {"HTTP_PROXY": "http://127.0.0.1:1"}):
                try:
                    origin.send_once("0123456", b"synthetic-count-token")
                except Exception as exc:
                    error = exc
        finally:
            thread.join(timeout=1)
            listener.close()
        self.assertEqual(len(got), 1)
        head, body = got[0]
        self.assertIn(b"Host: goatcounter.ausmalwiese.invalid", head)
        self.assertNotIn(b"User-Agent", head)
        self.assertNotIn(b"Referer", head)
        self.assertEqual(body, origin.payload("0123456"))
        return error

    def test_exact_202_and_fixed_headers(self):
        self.assertIsNone(self.exchange(b"HTTP/1.1 202 Accepted\r\nContent-Length: 0\r\n\r\n"))

    def test_redirect_failure_and_timeout_are_one_attempt(self):
        self.assertIsNotNone(self.exchange(b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:1/\r\n\r\n"))
        self.assertIsNotNone(self.exchange(b"HTTP/1.1 500 Error\r\n\r\n"))
        self.assertIsNotNone(self.exchange(b"HTTP/1.1 202 Accepted\r\n\r\n", delay=0.3))

    def test_token_injection_stops_before_socket(self):
        with mock.patch.object(origin.socket, "socket") as sock:
            with self.assertRaises(origin.Stop):
                origin.send_once("0123456", b"synthetic\r\nInjected: secret")
            sock.assert_not_called()


class UnitTests(unittest.TestCase):
    def test_activation_rejects_wrong_process_fd_count_and_name(self):
        with mock.patch.dict(os.environ, {"LISTEN_PID": "wrong", "LISTEN_FDS": "1",
                                          "LISTEN_FDNAMES": "origin"}), mock.patch.object(origin.socket, "socket") as sock:
            with self.assertRaises(origin.Stop):
                origin.activated_socket()
            sock.assert_not_called()

    def test_activation_validates_type_path_and_socket_permissions(self):
        listener = mock.Mock(family=socket.AF_UNIX, type=socket.SOCK_STREAM)
        listener.getsockname.return_value = origin.SOCKET_PATH
        listener.getsockopt.return_value = 1
        file_info = SimpleNamespace(st_mode=stat.S_IFSOCK | 0o660,
                                    st_uid=os.geteuid(), st_gid=os.getegid())
        parent_info = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        with mock.patch.dict(os.environ, {"LISTEN_PID": str(os.getpid()), "LISTEN_FDS": "1",
                                          "LISTEN_FDNAMES": "origin"}), mock.patch.object(
                origin.socket, "socket", return_value=listener), mock.patch.object(
                origin.os, "set_inheritable"), mock.patch.object(
                origin.os, "lstat", side_effect=lambda p: file_info if str(p) == origin.SOCKET_PATH else parent_info):
            self.assertIs(origin.activated_socket(), listener)
            listener.getsockname.return_value = "/tmp/wrong.sock"
            with self.assertRaises(origin.Stop):
                origin.activated_socket()
            listener.getsockname.return_value = origin.SOCKET_PATH
            file_info.st_mode = stat.S_IFSOCK | 0o666
            with self.assertRaises(origin.Stop):
                origin.activated_socket()

    @unittest.skipUnless(shutil.which("systemd-analyze"), "systemd parser unavailable")
    def test_systemd_parses_units_without_starting_services(self):
        with tempfile.TemporaryDirectory(prefix="origin-units-") as temp:
            root = Path(temp)
            service = (ROOT / "ops/systemd/ausmalwiese-goatcounter-origin.service").read_text()
            # Only replace the not-yet-installed executable for offline parsing.
            lines = ["ExecStart=/usr/bin/true" if line.startswith("ExecStart=") else line
                     for line in service.splitlines()]
            (root / "ausmalwiese-goatcounter-origin.service").write_text("\n".join(lines) + "\n")
            shutil.copyfile(ROOT / "ops/systemd/ausmalwiese-goatcounter-origin.socket",
                            root / "ausmalwiese-goatcounter-origin.socket")
            (root / "ausmalwiese-goatcounter.service").write_text(
                "[Unit]\nDescription=Synthetic backend dependency\n[Service]\nExecStart=/usr/bin/true\n")
            result = subprocess.run(["systemd-analyze", "--man=no", "verify",
                                     str(root / "ausmalwiese-goatcounter-origin.service"),
                                     str(root / "ausmalwiese-goatcounter-origin.socket")],
                                    env=dict(os.environ, SYSTEMD_UNIT_PATH=str(root) + ":"),
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_socket_and_service_form_one_bounded_source_unit(self):
        service = (ROOT / "ops/systemd/ausmalwiese-goatcounter-origin.service").read_text()
        sock = (ROOT / "ops/systemd/ausmalwiese-goatcounter-origin.socket").read_text()
        for item in ("Type=notify", "Restart=no", "TasksMax=12", "TimeoutStopSec=2",
                     "ReadOnlyPaths=/srv/coloring-pages-content/public\n", "StandardError=null"):
            self.assertIn(item, service)
        for item in ("ListenStream=" + origin.SOCKET_PATH, "SocketMode=0660", "Backlog=8",
                     "FileDescriptorName=origin", "RemoveOnStop=yes", "Accept=no"):
            self.assertIn(item, sock)
        self.assertNotIn("ReadOnlyPaths=" + str(origin.CATALOG_PATH), service)


if __name__ == "__main__":
    unittest.main()
