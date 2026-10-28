#!/usr/bin/env python3
"""Ausmalwiese first-party GoatCounter pageview adapter source (#1224).

SOURCE ONLY. The runtime binds loopback only and accepts exactly one public
pageview shape. It never forwards client headers or caller JSON to GoatCounter,
never logs requests, and performs at most one backend transmission per request.
Installation, credentials, ingress and LIVE execution remain separately gated.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PUBLIC_ROUTE = "/api/pageview"
PUBLIC_HOSTS = frozenset({"ausmalwiese.de", "www.ausmalwiese.de"})
CATALOG_PATH = Path("/srv/coloring-pages-content/public/catalog.json")
MAX_CATALOG_BYTES = 8 * 1024 * 1024
MAX_BODY_BYTES = 128
PAGE_ID_RE = re.compile(r"[0-9]{7}\Z")

ADAPTER_HOST = "127.0.0.1"
ADAPTER_PORT = 9193
GOATCOUNTER_HOST = "goatcounter.ausmalwiese.invalid"
GOATCOUNTER_URL = "http://127.0.0.1:9194/api/v0/count"
CREDENTIAL_NAME = "goatcounter-token"

CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "ops/contracts/ausmalwiese-goatcounter-pageview-v1.json"
)


class AdapterStop(ValueError):
    """Stable non-sensitive failure code."""


def stop(code: str) -> None:
    raise AdapterStop(code)


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            stop("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def valid_content_type(value: str) -> bool:
    if not isinstance(value, str):
        return False
    parts = [part.strip() for part in value.split(";")]
    if not parts or parts[0].casefold() != "application/json":
        return False
    if len(parts) == 1:
        return True
    if len(parts) != 2 or "=" not in parts[1]:
        return False
    key, raw = (piece.strip() for piece in parts[1].split("=", 1))
    return key.casefold() == "charset" and raw.strip('"').casefold() == "utf-8"


def renderable(entry: dict[str, Any]) -> bool:
    if entry.get("hidden") is True or entry.get("visible") is False:
        return False
    pages = entry.get("pages")
    if isinstance(pages, list) and pages:
        for page in pages:
            if not isinstance(page, dict):
                return False
            if not (
                isinstance(page.get("preview"), str) and page["preview"]
                and isinstance(page.get("print"), str) and page["print"]
            ):
                return False
        return True
    return (
        isinstance(entry.get("preview"), str) and bool(entry["preview"])
        and isinstance(entry.get("print"), str) and bool(entry["print"])
    )


def published_page_ids(catalog: object) -> frozenset[str]:
    if not isinstance(catalog, list):
        stop("CATALOG_SHAPE")
    seen: set[str] = set()
    allowed: set[str] = set()
    for entry in catalog:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            stop("CATALOG_SHAPE")
        page_id = entry["id"]
        if page_id in seen:
            stop("CATALOG_DUPLICATE_ID")
        seen.add(page_id)
        if PAGE_ID_RE.fullmatch(page_id) and renderable(entry):
            allowed.add(page_id)
    return frozenset(allowed)


def load_catalog(path: Path = CATALOG_PATH) -> object:
    if not isinstance(path, Path) or not path.is_absolute():
        stop("CATALOG_PATH")
    try:
        stat = path.lstat()
    except OSError:
        stop("CATALOG_UNAVAILABLE")
    if path.is_symlink() or not path.is_file() or not 1 <= stat.st_size <= MAX_CATALOG_BYTES:
        stop("CATALOG_UNAVAILABLE")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=strict_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        stop("CATALOG_INVALID")


def accept_event(
    *,
    method: str,
    request_target: str,
    host: str,
    origin: str,
    content_type: str,
    raw_body: bytes,
    catalog: object,
) -> str:
    if method != "POST" or request_target != PUBLIC_ROUTE:
        stop("CLIENT_ROUTE_OR_METHOD")
    if host not in PUBLIC_HOSTS:
        stop("CLIENT_HOST")
    if origin != "https://" + host:
        stop("CLIENT_ORIGIN")
    if not valid_content_type(content_type):
        stop("CLIENT_CONTENT_TYPE")
    if not isinstance(raw_body, bytes) or not 1 <= len(raw_body) <= MAX_BODY_BYTES:
        stop("CLIENT_BODY_SIZE")
    try:
        body = json.loads(
            raw_body.decode("utf-8"),
            object_pairs_hook=strict_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        stop("CLIENT_JSON")
    if not isinstance(body, dict) or set(body) != {"page_id"}:
        stop("CLIENT_SCHEMA")
    page_id = body["page_id"]
    if not isinstance(page_id, str) or PAGE_ID_RE.fullmatch(page_id) is None:
        stop("CLIENT_PAGE_ID")
    if page_id not in published_page_ids(catalog):
        stop("CLIENT_PAGE_NOT_PUBLISHED")
    return page_id


def backend_body(page_id: str) -> bytes:
    if not isinstance(page_id, str) or PAGE_ID_RE.fullmatch(page_id) is None:
        stop("BACKEND_PAGE_ID")
    return json.dumps(
        {
            "no_sessions": True,
            "hits": [{"path": "/coloring-page/" + page_id}],
        },
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def credential_token() -> str:
    root = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if not root or not os.path.isabs(root):
        stop("CREDENTIAL_DIRECTORY")
    path = Path(root) / CREDENTIAL_NAME
    try:
        stat = path.lstat()
        raw = path.read_bytes()
    except OSError:
        stop("CREDENTIAL_UNAVAILABLE")
    if path.is_symlink() or not path.is_file() or stat.st_size > 512:
        stop("CREDENTIAL_UNAVAILABLE")
    try:
        token = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        stop("CREDENTIAL_INVALID")
    if not 16 <= len(token) <= 256 or any(ch.isspace() for ch in token):
        stop("CREDENTIAL_INVALID")
    return token


def dispatch_once(page_id: str, token: str, opener=None) -> None:
    if not isinstance(token, str) or not 16 <= len(token) <= 256:
        stop("CREDENTIAL_INVALID")
    request = urllib.request.Request(
        GOATCOUNTER_URL,
        data=backend_body(page_id),
        method="POST",
        headers={
            "Host": GOATCOUNTER_HOST,
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
    )
    if opener is None:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            RejectRedirects(),
        )
        opener.addheaders = []
    try:
        with opener.open(request, timeout=5) as response:
            if response.status != 202:
                stop("BACKEND_NOT_ACCEPTED")
            response.read(1024)
    except AdapterStop:
        raise
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, ValueError):
        stop("BACKEND_RESPONSE_UNCERTAIN")


def expected_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": "SOURCE_ONLY_NOT_INSTALLED",
        "repository": "rozkalnsandris/RPi5_main",
        "issue": 1224,
        "public": {
            "route": PUBLIC_ROUTE,
            "hosts": sorted(PUBLIC_HOSTS),
            "max_body_bytes": MAX_BODY_BYTES,
            "catalog": str(CATALOG_PATH),
        },
        "adapter": {
            "listen": f"{ADAPTER_HOST}:{ADAPTER_PORT}",
            "backend": GOATCOUNTER_URL,
            "backend_host": GOATCOUNTER_HOST,
            "credential_name": CREDENTIAL_NAME,
        },
        "goatcounter": {
            "version": "v2.7.0",
            "source_commit": "7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4",
            "arm64_asset": "goatcounter-v2.7.0-linux-arm64.gz",
            "arm64_bytes": 12770791,
            "arm64_sha256": "ff5b2670b858bbe48802dfdc74130b6dcde2de9f5c1229b838eb9132769307dd",
            "listen": "127.0.0.1:9194",
        },
        "boundaries": {
            "allow_live": False,
            "allow_install": False,
            "allow_ingress_change": False,
            "allow_database_mutation": False,
            "allow_secret_access_from_checkout": False,
            "allow_retry": False,
            "allow_rollback": False,
            "allow_cleanup": False,
            "request_logging": False,
            "forward_client_headers": False,
        },
    }


def check_contract(path: Path | None = None) -> None:
    if path is None:
        path = CONTRACT_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stop("CONTRACT_UNAVAILABLE")
    if data != expected_contract():
        stop("CONTRACT_DRIFT")


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Never emit raw request details or tracebacks to service logs.
        return


class Handler(BaseHTTPRequestHandler):
    server_version = "AusmalwiesePageview/1"
    sys_version = ""

    def log_message(self, format, *args):
        # BaseHTTPRequestHandler otherwise logs client address + request line.
        return

    def _reply(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        try:
            if self.headers.get("Transfer-Encoding"):
                stop("CLIENT_TRANSFER_ENCODING")
            raw_length = self.headers.get("Content-Length", "")
            if re.fullmatch(r"[1-9][0-9]{0,3}", raw_length) is None:
                stop("CLIENT_BODY_SIZE")
            size = int(raw_length)
            if size > MAX_BODY_BYTES:
                stop("CLIENT_BODY_SIZE")
            raw = self.rfile.read(size)
            if len(raw) != size:
                stop("CLIENT_BODY_SIZE")
            page_id = accept_event(
                method="POST",
                request_target=self.path,
                host=self.headers.get("Host", ""),
                origin=self.headers.get("Origin", ""),
                content_type=self.headers.get("Content-Type", ""),
                raw_body=raw,
                catalog=load_catalog(),
            )
            token = credential_token()
            dispatch_once(page_id, token)
            token = ""
            self._reply(202)
        except AdapterStop as exc:
            code = str(exc)
            if code in {"CLIENT_HOST", "CLIENT_ORIGIN"}:
                self._reply(403)
            elif code == "CLIENT_CONTENT_TYPE":
                self._reply(415)
            elif code.startswith("BACKEND_") or code.startswith("CREDENTIAL_"):
                self._reply(503)
            else:
                self._reply(400)
        except Exception:
            self._reply(503)

    def do_GET(self):
        self._reply(405)

    do_HEAD = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET
    do_PATCH = do_GET


def serve(contract_path: Path | None = None) -> None:
    check_contract(contract_path)
    server = QuietThreadingHTTPServer((ADAPTER_HOST, ADAPTER_PORT), Handler)
    server.serve_forever(poll_interval=0.5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-contract", action="store_true")
    mode.add_argument("--serve", action="store_true")
    parser.add_argument(
        "--contract", type=Path,
        help="Non-secret source contract file; defaults to the checkout contract",
    )
    args = parser.parse_args(argv)
    try:
        if args.check_contract:
            check_contract(args.contract)
            print("AUSMALWIESE_GOATCOUNTER_PAGEVIEW=SOURCE_OK_NOT_LIVE")
        else:
            serve(args.contract)
        return 0
    except AdapterStop as exc:
        print("AUSMALWIESE_GOATCOUNTER_PAGEVIEW=STOP CODE=" + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
