#!/usr/bin/env python3
"""Dormant owner-gated GET-only GoatCounter SIMPLE Cloudflare operator (#1358).

SOURCE ONLY. No credentials, calls or root installation are performed here.
A future separately owner-authorized root-owned release and caller must
supply a CloudflareClient; unsafe/uninstalled execution fails BEFORE GET.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from cloudflare_rdc_operator import CloudflareClient
import ausmalwiese_goatcounter_simple_cloudflare_readback_v1 as readback

ROOT = Path("/usr/local/libexec/rpi5-goatcounter-simple-cloudflare-readonly")
ENTRY = ROOT / "operator.py"
RELEASE = ROOT / "release.json"
REPOSITORY = "rozkalnsandris/RPi5_main"
SCOPE = "GOATCOUNTER_SIMPLE_CLOUDFLARE_READONLY"
MODULES = {
    "operator.py": None,
    "cloudflare_rdc_operator.py": "cloudflare_rdc_operator",
    "ausmalwiese_goatcounter_tunnel_v1.py": "ausmalwiese_goatcounter_tunnel_v1",
    "ausmalwiese_goatcounter_simple_route_v1.py": "ausmalwiese_goatcounter_simple_route_v1",
    "ausmalwiese_goatcounter_simple_readiness_v1.py": "ausmalwiese_goatcounter_simple_readiness_v1",
    "ausmalwiese_goatcounter_simple_evidence_v1.py": "ausmalwiese_goatcounter_simple_evidence_v1",
    "ausmalwiese_goatcounter_simple_cloudflare_readback_v1.py":
        "ausmalwiese_goatcounter_simple_cloudflare_readback_v1",
}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
UUID = readback.UUID


class Blocked(Exception):
    def __init__(self, code):
        self.code = code


def require(ok, code):
    if not ok:
        raise Blocked(code)


def safe_regular(path, mode, size_max):
    """Read only a root-owned, non-symlinked bounded regular file."""
    p = path.parent
    while True:
        s = os.lstat(p)
        require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0
                and s.st_gid == 0 and not (s.st_mode & 0o022),
                "STOP_RELEASE")
        if p == p.parent:
            break
        p = p.parent
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == 0
                and s.st_gid == 0 and stat.S_IMODE(s.st_mode) == mode
                and s.st_nlink == 1 and 0 < s.st_size <= size_max,
                "STOP_RELEASE")
        data = os.read(fd, size_max + 1)
        require(len(data) == s.st_size, "STOP_RELEASE")
        return data
    finally:
        os.close(fd)


def verified_release(expected_main):
    """Real OS and content identity only; never a caller-provided proof."""
    require(type(expected_main) is str and SHA40.fullmatch(expected_main),
            "STOP_RELEASE")
    require(os.geteuid() == 0 and Path(__file__).absolute() == ENTRY,
            "STOP_TRUSTED_INSTALL")
    raw = safe_regular(RELEASE, 0o400, 8192)
    try:
        meta = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise Blocked("STOP_RELEASE") from None
    require(type(meta) is dict
            and set(meta) == {"schema", "repository", "source_sha",
                              "scope", "sha256"}
            and meta["schema"] == 1 and meta["repository"] == REPOSITORY
            and meta["source_sha"] == expected_main
            and meta["scope"] == SCOPE
            and type(meta["sha256"]) is dict
            and set(meta["sha256"]) == set(MODULES),
            "STOP_RELEASE")
    for name, imported in MODULES.items():
        wanted = meta["sha256"][name]
        require(type(wanted) is str and SHA64.fullmatch(wanted),
                "STOP_RELEASE")
        binary = safe_regular(ROOT / name, 0o400, 196608)
        require(hashlib.sha256(binary).hexdigest() == wanted,
                "STOP_RELEASE")
        if imported is not None:
            loaded = sys.modules.get(imported)
            require(loaded is not None
                    and getattr(loaded, "__file__", None) is not None
                    and Path(loaded.__file__).absolute() == ROOT / name,
                    "STOP_RELEASE")
    # Source provenance verified; caller MUST independently prove that
    # its owner permission, capability token, opener and CLI are trusted.


class GETOnly:
    """Never expose other CloudflareClient verbs to the readback parser."""
    def __init__(self, client, account, zone):
        require(type(client) is CloudflareClient, "STOP_CLIENT")
        self.client = client
        self.account = account
        self.zone = zone
        self.seen = set()

    def allowed(self, path):
        root = "/accounts/" + self.account
        zone = "/zones/" + self.zone
        return path in {
            zone,
            zone + "/workers/routes",
            root + "/cfd_tunnel?name=rpi5-tunnel&is_deleted=false&per_page=100",
            *{
                root + "/workers/domains?hostname=" + hostname
                for hostname in readback.HOSTS
            },
        } or (
            type(path) is str
            and re.fullmatch(
                re.escape(root) + r"/cfd_tunnel/([a-f0-9-]{36})/configurations",
                path,
            ) is not None
            and UUID.fullmatch(path.split("/")[-2]) is not None
        )

    def __call__(self, path):
        require(type(path) is str and self.allowed(path)
                and path not in self.seen and len(self.seen) < 6,
                "STOP_ENDPOINT")
        self.seen.add(path)  # consume the one-shot GET budget pre-dispatch
        try:
            return self.client._request("GET", path)
        except Exception:
            raise Blocked("STOP_TRANSPORT") from None


def run_guarded(*, client, account_id, zone_id, expected_source_sha):
    """Return ONLY fixed status/safe edge. Not proof of LIVE approval.

    Required future caller: separately owner-authorized, -I isolated
    root-owned trusted runner, verified read-only Cloudflare token/opener.
    There is deliberately NO CLI, token loader, installer or LIVE runner.
    """
    try:
        # No caller-supplied status can bypass this real filesystem gate.
        verified_release(expected_source_sha)
        require(type(account_id) is str and readback.ID.fullmatch(account_id)
                and hashlib.sha256(account_id.encode("ascii")).hexdigest()
                == readback.ACCOUNT_SHA256
                and type(zone_id) is str and readback.ID.fullmatch(zone_id),
                "STOP_IDENTITY")
        getter = GETOnly(client, account_id, zone_id)
        return readback.collect_once(trusted_get=getter,
                                     account_id=account_id, zone_id=zone_id)
    except Blocked as exc:
        return exc.code, None
    except (OSError, TypeError, ValueError, OverflowError, KeyError,
            AttributeError):
        return "STOP_RELEASE", None


if __name__ == "__main__":
    raise SystemExit("SOURCE_ONLY: not installed or authorized; no CLI GET")
