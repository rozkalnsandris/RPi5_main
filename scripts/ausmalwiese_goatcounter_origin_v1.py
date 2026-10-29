#!/usr/bin/env python3
"""Private, socket-activated origin-request collector. No public/TCP listener.

Runtime requires separately authorized installation, a verified peer binding and
the existing systemd count-only credential. Check mode reads public source only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import pwd
import re
import signal
import socket
import stat
import struct
import threading
import time

SOCKET_PATH = "/run/ausmalwiese-pageview/origin.sock"
INSTALL_ROOT = Path("/usr/local/libexec/ausmalwiese-goatcounter-v1")
PEER_PATH = INSTALL_ROOT / "origin-peer.json"
CATALOG_PATH = Path("/srv/coloring-pages-content/public/catalog.json")
SERVICE_USER = "ausmalwiese-pageview"
MAX_HEADER = 512
MAX_CATALOG = 8 * 1024 * 1024
MAX_ACTIVE = 4
REQUEST_SECONDS = 0.2
BACKEND_SECONDS = 0.15
BACKEND = ("127.0.0.1", 9194)
ID_RE = re.compile(r"[0-9]{7}\Z")
BODY_RE = re.compile(rb'\{"page_id":"([0-9]{7})"\}\Z')
EXPECTED_HEADERS = {b"host": b"origin-counter.invalid", b"content-type": b"application/json",
                    b"content-length": b"21", b"connection": b"close"}


class Stop(ValueError):
    """Fixed error class only; never include source request or secret text."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Stop("DUPLICATE_KEY")
        result[key] = value
    return result


def read_regular(path: Path, maximum: int, *, root_owned=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise Stop("FILE_SHAPE")
        if root_owned and (info.st_uid != 0 or info.st_mode & 0o022):
            raise Stop("FILE_OWNER_MODE")
        data = handle.read(maximum + 1)
        if len(data) != info.st_size:
            raise Stop("FILE_CHANGED")
        return data


def parse_peer(data: bytes):
    obj = json.loads(data, object_pairs_hook=unique_object)
    if not isinstance(obj, dict) or set(obj) != {"schema", "uid", "gid"}:
        raise Stop("PEER_SCHEMA")
    if obj["schema"] != "ausmalwiese.origin-peer.v1":
        raise Stop("PEER_SCHEMA")
    for key in ("uid", "gid"):
        if type(obj[key]) is not int or not 1 <= obj[key] < 2**32 - 1:
            raise Stop("PEER_ID")
    return obj["uid"], obj["gid"]


def visible_ids(catalog):
    if not isinstance(catalog, list):
        raise Stop("CATALOG_SHAPE")
    seen, allowed = set(), set()
    for entry in catalog:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise Stop("CATALOG_SHAPE")
        page_id = entry["id"]
        if page_id in seen:
            raise Stop("CATALOG_DUPLICATE")
        seen.add(page_id)
        if not ID_RE.fullmatch(page_id) or entry.get("hidden") is True or entry.get("visible") is False:
            continue
        pages = entry.get("pages")
        pages = pages if isinstance(pages, list) and pages else [entry]
        if all(isinstance(p, dict) and isinstance(p.get("preview"), str) and p["preview"]
               and isinstance(p.get("print"), str) and p["print"] for p in pages):
            allowed.add(page_id)
    return frozenset(allowed)


class Catalog:
    """Serialized bounded parse; atomic catalogue replacement invalidates cache.

    No stale fallback when current metadata/read/validation fails. The directory,
    not an individual inode, must remain visible through the service sandbox.
    """
    def __init__(self, path=CATALOG_PATH):
        self.path = path
        self.lock = threading.Lock()
        self.key = None
        self.ids = frozenset()

    def get(self):
        with self.lock:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_CATALOG:
                    raise Stop("CATALOG_FILE")
                key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                if key != self.key:
                    self.key = None
                    self.ids = frozenset()
                    raw = handle.read(MAX_CATALOG + 1)
                    after = os.fstat(handle.fileno())
                    if (len(raw) != info.st_size or after.st_mtime_ns != info.st_mtime_ns
                            or after.st_ctime_ns != info.st_ctime_ns):
                        raise Stop("CATALOG_CHANGED")
                    ids = visible_ids(json.loads(raw, object_pairs_hook=unique_object))
                    self.ids, self.key = ids, key
                return self.ids


def remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise Stop("DEADLINE")
    return value


def read_headers(conn, deadline, limit):
    data = b""
    while b"\r\n\r\n" not in data:
        conn.settimeout(remaining(deadline))
        chunk = conn.recv(min(256, limit + 4 + 21 - len(data)))
        if not chunk:
            raise Stop("TRUNCATED")
        data += chunk
        if len(data.split(b"\r\n\r\n", 1)[0]) > limit:
            raise Stop("HEADER_LIMIT")
    head, body = data.split(b"\r\n\r\n", 1)
    return head, body


def read_message(conn):
    deadline = time.monotonic() + REQUEST_SECONDS
    head, body = read_headers(conn, deadline, MAX_HEADER)
    lines = head.split(b"\r\n")
    if lines[0] != b"POST /internal/origin-count HTTP/1.0" or len(lines) != 5:
        raise Stop("WIRE_REQUEST")
    headers = {}
    for line in lines[1:]:
        key, sep, value = line.partition(b":")
        key = key.lower()
        if not sep or key in headers or key not in EXPECTED_HEADERS:
            raise Stop("WIRE_HEADERS")
        headers[key] = value.strip(b" \t")
    if headers != EXPECTED_HEADERS:
        raise Stop("WIRE_HEADERS")
    while len(body) < 21:
        conn.settimeout(remaining(deadline))
        chunk = conn.recv(22 - len(body))
        if not chunk:
            raise Stop("WIRE_BODY")
        body += chunk
    match = BODY_RE.fullmatch(body)
    if not match:
        raise Stop("WIRE_BODY")
    return match[1].decode("ascii")


def payload(page_id):
    if not isinstance(page_id, str) or not ID_RE.fullmatch(page_id):
        raise Stop("PAGE_ID")
    return json.dumps({"no_sessions": True,
                       "hits": [{"path": "/origin-detail-request/" + page_id}]},
                      separators=(",", ":")).encode("ascii")


def validate_token(raw):
    token = raw.strip()
    if not 16 <= len(token) <= 256 or any(b < 33 or b > 126 for b in token):
        raise Stop("CREDENTIAL_INVALID")
    return token


def send_once(page_id, token):
    token = validate_token(token)
    body = payload(page_id)
    request = (b"POST /api/v0/count HTTP/1.1\r\nHost: goatcounter.ausmalwiese.invalid\r\n"
               b"Authorization: Bearer " + token + b"\r\nContent-Type: application/json\r\n"
               b"Connection: close\r\nContent-Length: " + str(len(body)).encode()
               + b"\r\n\r\n" + body)
    deadline = time.monotonic() + BACKEND_SECONDS
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
        conn.settimeout(remaining(deadline))
        conn.connect(BACKEND)
        conn.settimeout(remaining(deadline))
        conn.sendall(request)
        head, _ = read_headers(conn, deadline, 4096)
        status = head.split(b"\r\n", 1)[0].split(b" ", 2)
        if len(status) < 2 or status[0] not in (b"HTTP/1.0", b"HTTP/1.1") or status[1] != b"202":
            raise Stop("BACKEND_NOT_ACCEPTED")
    # No redirects, retries, response-body buffering, proxy environment or logs.


class Collector:
    def __init__(self, listener, peer, catalog, sender):
        self.listener, self.peer = listener, peer
        self.catalog, self.sender = catalog, sender
        self.slots = threading.BoundedSemaphore(MAX_ACTIVE)
        self.stop = threading.Event()

    def handle(self, conn):
        try:
            page_id = read_message(conn)
            if page_id not in self.catalog.get():
                raise Stop("UNPUBLISHED")
            self.sender(page_id)
            conn.settimeout(0.05)
            conn.sendall(b"HTTP/1.0 202 Accepted\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        except Exception:
            # Includes uncertain backend delivery. Drop once; never log raw data.
            pass
        finally:
            conn.close()
            self.slots.release()

    def serve(self):
        self.listener.settimeout(0.1)
        while not self.stop.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            try:
                _, uid, gid = struct.unpack("iII", conn.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("iII")))
                if (uid, gid) != self.peer or not self.slots.acquire(blocking=False):
                    conn.close()
                    continue
                try:
                    threading.Thread(target=self.handle, args=(conn,), daemon=True).start()
                except Exception:
                    self.slots.release()
                    raise
            except Exception:
                conn.close()
        # Do not shutdown()/unlink the socket owned by systemd.


def activated_socket():
    if (os.environ.get("LISTEN_PID") != str(os.getpid())
            or os.environ.get("LISTEN_FDS") != "1"
            or os.environ.get("LISTEN_FDNAMES") != "origin"):
        raise Stop("ACTIVATION_FDS")
    conn = socket.socket(fileno=3)
    os.set_inheritable(3, False)
    if (conn.family != socket.AF_UNIX or conn.type != socket.SOCK_STREAM
            or conn.getsockname() != SOCKET_PATH
            or conn.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1):
        raise Stop("ACTIVATION_SOCKET")
    info = os.lstat(SOCKET_PATH)
    if (not stat.S_ISSOCK(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o660
            or info.st_uid != os.geteuid() or info.st_gid != os.getegid()):
        raise Stop("SOCKET_OWNER_MODE")
    parent = os.lstat(Path(SOCKET_PATH).parent)
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022:
        raise Stop("SOCKET_DIRECTORY")
    return conn


def expected_contract():
    return {"schema": "ausmalwiese.origin-collector.v1", "issue": 1274,
            "socket": SOCKET_PATH, "socket_mode": "0660", "fd_name": "origin",
            "route": "/internal/origin-count", "method": "POST", "body_bytes": 21,
            "prefix": "/origin-detail-request/", "max_active": MAX_ACTIVE,
            "max_header": MAX_HEADER, "request_seconds": REQUEST_SECONDS,
            "backend_seconds": BACKEND_SECONDS, "retries": 0,
            "request_logs": False, "public_listener": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-contract", action="store_true")
    modes.add_argument("--serve", action="store_true")
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if json.loads(args.contract.read_text()) != expected_contract():
            raise Stop("CONTRACT_DRIFT")
        if args.check_contract:
            print("GOATCOUNTER_ORIGIN=SOURCE_OK_NOT_LIVE")
            return 0
        if (platform.system() != "Linux" or platform.node() != "rpi5"
                or platform.machine() not in ("aarch64", "arm64")
                or os.geteuid() == 0 or pwd.getpwuid(os.geteuid()).pw_name != SERVICE_USER):
            raise Stop("RUNTIME_IDENTITY")
        peer = parse_peer(read_regular(PEER_PATH, 256, root_owned=True))
        root = os.environ.get("CREDENTIALS_DIRECTORY", "")
        if not os.path.isabs(root):
            raise Stop("CREDENTIAL_DIRECTORY")
        token = validate_token(read_regular(Path(root) / "goatcounter-token", 512))
        catalog = Catalog()
        catalog.get()
        listener = activated_socket()
        collector = Collector(listener, peer, catalog, lambda page: send_once(page, token))
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: collector.stop.set())
        notify = os.environ.get("NOTIFY_SOCKET", "")
        if not notify.startswith(("/", "@")):
            raise Stop("NOTIFY_SOCKET")
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
            channel.settimeout(0.2)
            channel.sendto(b"READY=1", "\0" + notify[1:] if notify.startswith("@") else notify)
        try:
            collector.serve()
        finally:
            listener.close()
        return 0
    except Exception:
        # No exception text: config/request/token values never become log output.
        print("GOATCOUNTER_ORIGIN=STOP")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
