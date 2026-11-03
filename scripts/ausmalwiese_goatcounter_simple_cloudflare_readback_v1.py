#!/usr/bin/env python3
"""Offline-only injected Cloudflare GET sanitizer for GoatCounter SIMPLE (#1356).

A separately authorized trusted GET transport must be injected. NO network,
credentials, files, runtime launcher, CLI or public tracking here.
"""
import hashlib
import re
from ausmalwiese_goatcounter_tunnel_v1 import ACCOUNT_SHA256
from ausmalwiese_goatcounter_simple_route_v1 import HOSTS, RouteError, prepare
from ausmalwiese_goatcounter_simple_evidence_v1 import _worker_route_matches

ID = re.compile(r"[0-9a-f]{32}\Z")
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
ZONE = "ausmalwiese.de"
TUNNEL = "rpi5-tunnel"
PER_PAGE = 20
MAX_PAGES = 5

class Stop(Exception):
    def __init__(self, code):
        self.code = code

def require(ok, code):
    if not ok:
        raise Stop(code)

def unpack(payload, what):
    require(type(payload) is dict
            and set(payload) <= {"success","errors","messages","result","result_info"}
            and payload.get("success") is True
            and payload.get("errors",[]) == []
            and type(payload.get("result")) in (list,dict), "STOP_"+what)
    return payload["result"]

def page_one(raw, rows, what, mandatory=False):
    info = raw.get("result_info")
    if info is None:
        require(not mandatory, "STOP_"+what+"_PAGINATION")
        return
    require(type(info) is dict
            and type(info.get("page")) is int and info["page"] == 1
            and type(info.get("total_pages")) is int and info["total_pages"] == 1
            and (info.get("count") is None or
                 (type(info["count"]) is int and info["count"] == len(rows)))
            and (info.get("total_count") is None or
                 (type(info["total_count"]) is int and info["total_count"] == len(rows))),
            "STOP_"+what+"_PAGINATION")

def get(getter, path, seen):
    require(callable(getter) and path not in seen and len(seen) < 12,
            "STOP_TRANSPORT")
    seen.add(path)  # one-shot budget before dispatch; no retry
    try:
        return getter(path)
    except Exception:
        raise Stop("STOP_TRANSPORT") from None

def inspect_zone(getter, account, zone, seen):
    row = unpack(get(getter, "/zones/"+zone, seen), "ZONE")
    require(type(row) is dict and row.get("id") == zone
            and row.get("name") == ZONE and row.get("status") == "active"
            and type(row.get("account")) is dict
            and row["account"].get("id") == account, "STOP_ZONE")

def inspect_tunnel(getter, account, seen):
    url = ("/accounts/"+account+"/cfd_tunnel?name="+TUNNEL
           +"&is_deleted=false&per_page=100")
    raw = get(getter,url,seen)
    rows = unpack(raw,"TUNNEL")
    require(type(rows) is list and len(rows)==1, "STOP_TUNNEL")
    page_one(raw,rows,"TUNNEL",mandatory=True)
    tunnel = rows[0]
    require(type(tunnel) is dict and tunnel.get("name") == TUNNEL
            and tunnel.get("config_src") == "cloudflare"
            and tunnel.get("deleted_at") is None
            and type(tunnel.get("id")) is str
            and UUID.fullmatch(tunnel["id"]) is not None
            and (tunnel.get("account_id") is None
                 or tunnel["account_id"] == account), "STOP_TUNNEL")
    url = ("/accounts/"+account+"/cfd_tunnel/"+tunnel["id"]+"/configurations")
    obj = unpack(get(getter,url,seen), "TUNNEL")
    require(type(obj) is dict and type(obj.get("version")) is int
            and obj["version"] >= 0 and type(obj.get("config")) is dict
            and (obj.get("account_id") is None or obj["account_id"] == account)
            and (obj.get("tunnel_id") is None or obj["tunnel_id"] == tunnel["id"]),
            "STOP_TUNNEL")
    try:
        _, absent = prepare(obj["config"])
    except (RouteError, ValueError, TypeError, AttributeError):
        raise Stop("STOP_ROUTE") from None
    require(absent is True, "STOP_ROUTE")

def inspect_routes(getter, zone, seen):
    raw = get(getter,"/zones/"+zone+"/workers/routes",seen)
    rows = unpack(raw,"WORKER")
    require(type(rows) is list and len(rows) < 1000, "STOP_WORKER")
    # This API documents one list (not a paginated endpoint). If unexpected
    # pagination metadata appears, it must prove a complete one-page list.
    page_one(raw,rows,"WORKER")
    ids=set()
    for row in rows:
        require(type(row) is dict and type(row.get("id")) is str
                and ID.fullmatch(row["id"]) is not None
                and row["id"] not in ids and type(row.get("pattern")) is str
                and (row.get("script") is None
                     or (type(row["script"]) is str and bool(row["script"]))),
                "STOP_WORKER")
        ids.add(row["id"])
        # Script-less exclusions are not reliable clearance.
        require(_worker_route_matches(row["pattern"]) is False, "STOP_WORKER")

def inspect_domains(getter, account, zone, seen):
    ids=set()
    total=None
    pages=None
    for page in range(1,MAX_PAGES+1):
        url=("/accounts/"+account+"/workers/domains?page="+str(page)
             +"&per_page="+str(PER_PAGE))
        raw=get(getter,url,seen)
        rows=unpack(raw,"DOMAIN")
        info=raw.get("result_info")
        require(type(rows) is list and len(rows)<=PER_PAGE
                and type(info) is dict
                and all(type(info.get(k)) is int for k in
                        ("page","count","per_page","total_count","total_pages"))
                and info["page"] == page and info["count"] == len(rows)
                and info["per_page"] == PER_PAGE
                and 0<=info["total_count"]<=PER_PAGE*MAX_PAGES
                and 1<=info["total_pages"]<=MAX_PAGES,
                "STOP_DOMAIN_PAGINATION")
        if total is None:
            total,pages=info["total_count"],info["total_pages"]
            require(pages==max(1,(total+PER_PAGE-1)//PER_PAGE),
                    "STOP_DOMAIN_PAGINATION")
        require(info["total_count"]==total and info["total_pages"]==pages
                and len(rows)==(PER_PAGE if page<pages
                                else total-PER_PAGE*(pages-1)),
                "STOP_DOMAIN_PAGINATION")
        for row in rows:
            require(type(row) is dict and type(row.get("id")) is str
                    and ID.fullmatch(row["id"]) is not None and row["id"] not in ids
                    and type(row.get("hostname")) is str
                    and type(row.get("zone_id")) is str
                    and ID.fullmatch(row["zone_id"]) is not None
                    and type(row.get("zone_name")) is str
                    and type(row.get("enabled")) is bool
                    and type(row.get("previews_enabled")) is bool
                    and type(row.get("service")) is str and bool(row["service"]),
                    "STOP_DOMAIN")
            ids.add(row["id"])
            hostname=row["hostname"]
            require(hostname==hostname.lower().rstrip(".")
                    and re.fullmatch(r"[a-z0-9.-]{1,253}",hostname) is not None,
                    "STOP_DOMAIN")
            if row["zone_id"]==zone:
                require(row["zone_name"]==ZONE,"STOP_DOMAIN")
                for host in HOSTS:
                    # Enabled, disabled and preview-only states are rejected
                    # at target/parent hosts: incomplete precedence proof.
                    require(host!=hostname and not host.endswith("."+hostname),
                            "STOP_DOMAIN_INTERCEPTION")
            elif hostname in HOSTS or hostname.endswith("."+ZONE):
                raise Stop("STOP_DOMAIN_ZONE")
        if page==pages:
            require(len(ids)==total,"STOP_DOMAIN_PAGINATION")
            return
    raise Stop("STOP_DOMAIN_PAGINATION")

def collect_once(*, trusted_get, account_id, zone_id):
    """Only allowlisted status codes and reconstructed safe constants escape."""
    try:
        require(type(account_id) is str and ID.fullmatch(account_id) is not None
                and hashlib.sha256(account_id.encode("ascii")).hexdigest()
                == ACCOUNT_SHA256
                and type(zone_id) is str and ID.fullmatch(zone_id) is not None,
                "STOP_IDENTITY")
        seen=set()
        inspect_zone(trusted_get,account_id,zone_id,seen)
        inspect_tunnel(trusted_get,account_id,seen)
        inspect_routes(trusted_get,zone_id,seen)
        inspect_domains(trusted_get,account_id,zone_id,seen)
        edge={
            "remote_tunnel":"verified_exact_config",
            "routes":{host:"absent_safe_before_app_catchall" for host in HOSTS},
            "worker_routes":"verified_no_count_interception",
            "worker_custom_domains":"verified_no_count_interception",
        }
        return "PASS_EDGE_SOURCE_ONLY",edge
    except Stop as exc:
        return exc.code,None
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError,
            RecursionError):
        return "STOP_UNVERIFIED",None

if __name__ == "__main__":
    raise SystemExit("SOURCE_ONLY: no standalone credential, GET or deploy")
