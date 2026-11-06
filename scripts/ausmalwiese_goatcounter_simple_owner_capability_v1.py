#!/usr/bin/env python3
"""GitHub-owner authenticated, single-use approval capability for #1372.

SOURCE ONLY until installed inside the exact hash-pinned GoatCounter release.
No Cloudflare credential is read here. The only network action is one bounded
unauthenticated GET to a fixed public GitHub issue-comment endpoint. GitHub's
authenticated repository-owner identity is the approval provenance; a local
file, callback, CLI boolean or caller-provided opener is never authority.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import urllib.error
import urllib.request

REPOSITORY = "rozkalnsandris/RPi5_main"
OWNER_LOGIN = "rozkalnsandris"
OWNER_ID = 277435981
ISSUE = 1372
SCOPE = "CLOUDFLARE_GET"
HOST = "rpi5"
TUNNEL = "rpi5-tunnel"
ZONE = "ausmalwiese.de"
ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
RELEASE_PREFIX = "rpi5-goatcounter-simple-cloudflare-readonly-"
ROOT = Path(__file__).absolute().parent
ENTRY = ROOT / "owner_capability.py"
STATE_ROOT = Path("/var/lib/rpi5-goatcounter-simple-owner-consumed")
CA_FILE = Path("/etc/ssl/certs/ca-certificates.crt")
API_PREFIX = (
    "https://api.github.com/repos/rozkalnsandris/RPi5_main/issues/comments/"
)
ISSUE_API = "https://api.github.com/repos/rozkalnsandris/RPi5_main/issues/1372"
ISSUE_HTML = "https://github.com/rozkalnsandris/RPi5_main/issues/1372"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ID32 = re.compile(r"[0-9a-f]{32}\Z")
MAX_RESPONSE = 32768
MAX_BODY = 4096
MAX_LIFETIME_SECONDS = 900
CLOCK_SKEW_SECONDS = 60


class Stop(Exception):
    pass


def require(ok):
    if not ok:
        raise Stop()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )


def parse_time(value):
    require(
        type(value) is str
        and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            value,
        )
        is not None
    )
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError:
        raise Stop() from None


def approval_document(*, expected_source_sha, account_id, expires_at):
    require(type(expected_source_sha) is str and SHA40.fullmatch(expected_source_sha))
    require(type(account_id) is str and ID32.fullmatch(account_id))
    require(
        hashlib.sha256(account_id.encode("ascii")).hexdigest() == ACCOUNT_SHA256
    )
    parse_time(expires_at)
    return {
        "schema": 1,
        "repository": REPOSITORY,
        "issue": ISSUE,
        "source_sha": expected_source_sha,
        "scope": SCOPE,
        "host": HOST,
        "tunnel": TUNNEL,
        "zone": ZONE,
        "account_sha256": ACCOUNT_SHA256,
        "one_shot": True,
        "expires_at": expires_at,
    }


def verify_context(expected_source_sha):
    require(type(expected_source_sha) is str and SHA40.fullmatch(expected_source_sha))
    require(
        ROOT.parent == Path("/usr/local/libexec")
        and ROOT.name == RELEASE_PREFIX + expected_source_sha
        and Path(__file__).absolute() == ENTRY
        and os.geteuid() == 0
        and sys.flags.isolated == 1
        and sys.flags.dont_write_bytecode == 1
    )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(CA_FILE))
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
        NoRedirect(),
    )


def fetch_comment(comment_id):
    require(type(comment_id) is int and comment_id > 0)
    url = API_PREFIX + str(comment_id)
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "rpi5-goatcounter-owner-capability-v1",
        },
    )
    try:
        with _opener().open(request, timeout=10) as response:
            require(response.getcode() == 200 and response.geturl() == url)
            raw = response.read(MAX_RESPONSE + 1)
            require(0 < len(raw) <= MAX_RESPONSE)
        value = json.loads(raw.decode("utf-8"))
        require(type(value) is dict)
        return value
    except Stop:
        raise
    except (
        OSError,
        UnicodeError,
        ValueError,
        ssl.SSLError,
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
    ):
        raise Stop() from None


def _now():
    return dt.datetime.now(dt.timezone.utc)


def validate_comment(payload, *, comment_id, expected_source_sha, account_id):
    require(type(payload) is dict)
    require(type(comment_id) is int and comment_id > 0)
    user = payload.get("user")
    require(
        payload.get("id") == comment_id
        and payload.get("url") == API_PREFIX + str(comment_id)
        and payload.get("issue_url") == ISSUE_API
        and payload.get("html_url")
        == ISSUE_HTML + "#issuecomment-" + str(comment_id)
        and payload.get("author_association") == "OWNER"
        and type(user) is dict
        and user.get("login") == OWNER_LOGIN
        and user.get("id") == OWNER_ID
        and user.get("type") == "User"
    )
    created_raw = payload.get("created_at")
    updated_raw = payload.get("updated_at")
    require(type(created_raw) is str and created_raw == updated_raw)
    created = parse_time(created_raw)

    body = payload.get("body")
    require(type(body) is str and 0 < len(body.encode("utf-8")) <= MAX_BODY)
    try:
        document = json.loads(body)
    except (TypeError, ValueError):
        raise Stop() from None
    require(type(document) is dict and body == canonical(document))
    require(
        set(document)
        == {
            "schema",
            "repository",
            "issue",
            "source_sha",
            "scope",
            "host",
            "tunnel",
            "zone",
            "account_sha256",
            "one_shot",
            "expires_at",
        }
    )
    expected = approval_document(
        expected_source_sha=expected_source_sha,
        account_id=account_id,
        expires_at=document.get("expires_at"),
    )
    require(document == expected)

    expires = parse_time(document["expires_at"])
    now = _now()
    require(
        created <= expires
        and (expires - created).total_seconds() <= MAX_LIFETIME_SECONDS
        and now >= created - dt.timedelta(seconds=CLOCK_SKEW_SECONDS)
        and now <= expires
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def open_state_root():
    for parent in reversed(STATE_ROOT.parents):
        st = os.lstat(parent)
        require(
            stat.S_ISDIR(st.st_mode)
            and st.st_uid == 0
            and st.st_gid == 0
            and not (st.st_mode & 0o022)
        )
    before = os.lstat(STATE_ROOT)
    require(
        stat.S_ISDIR(before.st_mode)
        and before.st_uid == 0
        and before.st_gid == 0
        and stat.S_IMODE(before.st_mode) == 0o700
    )
    fd = os.open(
        STATE_ROOT,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    after = os.fstat(fd)
    require(
        stat.S_ISDIR(after.st_mode)
        and after.st_uid == 0
        and after.st_gid == 0
        and stat.S_IMODE(after.st_mode) == 0o700
        and after.st_dev == before.st_dev
        and after.st_ino == before.st_ino
    )
    return fd


def consume_once(*, comment_id, body_sha256, expected_source_sha):
    require(
        type(comment_id) is int
        and comment_id > 0
        and type(body_sha256) is str
        and re.fullmatch(r"[0-9a-f]{64}", body_sha256) is not None
        and type(expected_source_sha) is str
        and SHA40.fullmatch(expected_source_sha)
    )
    rootfd = None
    filefd = None
    try:
        rootfd = open_state_root()
        name = "github-comment-" + str(comment_id) + ".json"
        record = canonical(
            {
                "schema": 1,
                "comment_id": comment_id,
                "body_sha256": body_sha256,
                "source_sha": expected_source_sha,
                "scope": SCOPE,
            }
        ).encode("ascii")
        old_umask = os.umask(0o077)
        try:
            filefd = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_NOFOLLOW
                | os.O_CLOEXEC,
                0o600,
                dir_fd=rootfd,
            )
        finally:
            os.umask(old_umask)
        st = os.fstat(filefd)
        require(
            stat.S_ISREG(st.st_mode)
            and st.st_uid == 0
            and st.st_gid == 0
            and st.st_nlink == 1
            and stat.S_IMODE(st.st_mode) == 0o600
        )
        view = memoryview(record)
        while view:
            written = os.write(filefd, view)
            require(written > 0)
            view = view[written:]
        os.fsync(filefd)
        os.fsync(rootfd)
        return True
    except Stop:
        raise
    except OSError:
        raise Stop() from None
    finally:
        if filefd is not None:
            os.close(filefd)
        if rootfd is not None:
            os.close(rootfd)


def authorize_once(*, expected_source_sha, comment_id, account_id, zone_id):
    """Authenticate GitHub owner approval, then burn it before Cloudflare I/O."""
    verify_context(expected_source_sha)
    require(type(zone_id) is str and ID32.fullmatch(zone_id))
    require(
        type(account_id) is str
        and ID32.fullmatch(account_id)
        and hashlib.sha256(account_id.encode("ascii")).hexdigest() == ACCOUNT_SHA256
    )
    payload = fetch_comment(comment_id)
    body_sha256 = validate_comment(
        payload,
        comment_id=comment_id,
        expected_source_sha=expected_source_sha,
        account_id=account_id,
    )
    require(
        consume_once(
            comment_id=comment_id,
            body_sha256=body_sha256,
            expected_source_sha=expected_source_sha,
        )
        is True
    )
    return True


if __name__ == "__main__":
    raise SystemExit("SOURCE_ONLY: no standalone owner approval or Cloudflare call")
