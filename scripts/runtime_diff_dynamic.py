#!/usr/bin/env python3
"""Dynamic socket and interface semantics for runtime diffs."""
from __future__ import annotations
import collections
import re

HIGH_PORT_FLOOR=32768
HIGH_PORT_BUCKET_DELTA_TOLERANCE=2
VETH_PATTERN=r"^veth[0-9a-f]{7,15}$"
VETH_RE=re.compile(VETH_PATTERN)

def socket_identity(item):
    return item["protocol"],item["address_scope"],item["port"]

def is_dynamic_socket(item):
    return item["port"]>=HIGH_PORT_FLOOR

def _socket_bucket(item):
    return item["protocol"],item["address_scope"]

def socket_bucket_rows(before,after):
    old=collections.Counter(_socket_bucket(item) for item in before)
    new=collections.Counter(_socket_bucket(item) for item in after)
    rows=[]
    for protocol,scope in sorted(old.keys()|new.keys()):
        before_count=old[(protocol,scope)]
        after_count=new[(protocol,scope)]
        rows.append({"protocol":protocol,"address_scope":scope,"before_count":before_count,"after_count":after_count,"delta":after_count-before_count})
    return rows

def dynamic_socket_classification(buckets,changed):
    if not changed:
        return "none"
    for bucket in buckets:
        if bucket["delta"]==0:
            continue
        if bucket["before_count"]==0 or bucket["after_count"]==0:
            return "attention"
        if abs(bucket["delta"])>HIGH_PORT_BUCKET_DELTA_TOLERANCE:
            return "attention"
    return "informational"

def socket_semantics(before,after):
    stable_before=[item for item in before if not is_dynamic_socket(item)]
    stable_after=[item for item in after if not is_dynamic_socket(item)]
    old_stable={socket_identity(item):item for item in stable_before}
    new_stable={socket_identity(item):item for item in stable_after}
    stable={
        "added":[new_stable[key] for key in sorted(new_stable.keys()-old_stable.keys())],
        "removed":[old_stable[key] for key in sorted(old_stable.keys()-new_stable.keys())],
    }
    dynamic_before=[item for item in before if is_dynamic_socket(item)]
    dynamic_after=[item for item in after if is_dynamic_socket(item)]
    old_dynamic={socket_identity(item):item for item in dynamic_before}
    new_dynamic={socket_identity(item):item for item in dynamic_after}
    raw_added=[new_dynamic[key] for key in sorted(new_dynamic.keys()-old_dynamic.keys())]
    raw_removed=[old_dynamic[key] for key in sorted(old_dynamic.keys()-new_dynamic.keys())]
    buckets=socket_bucket_rows(dynamic_before,dynamic_after)
    return {
        "stable":stable,
        "dynamic_high_port":{
            "classification":dynamic_socket_classification(buckets,bool(raw_added or raw_removed)),
            "port_floor":HIGH_PORT_FLOOR,
            "bucket_delta_tolerance":HIGH_PORT_BUCKET_DELTA_TOLERANCE,
            "before_count":len(dynamic_before),
            "after_count":len(dynamic_after),
            "added_count":len(raw_added),
            "removed_count":len(raw_removed),
            "buckets":buckets,
            "raw_added":raw_added,
            "raw_removed":raw_removed,
        },
    }

def is_veth(item):
    return bool(VETH_RE.fullmatch(item["name"]))

def interface_profile(item):
    scopes=item["scope_counts"]
    return (
        item["operstate"],item["link_type"],item["loopback"],item["ipv4_count"],item["ipv6_count"],
        scopes["host"],scopes["link"],scopes["global"],scopes["other"],
    )

def profile_object(profile):
    return {
        "operstate":profile[0],
        "link_type":profile[1],
        "loopback":profile[2],
        "ipv4_count":profile[3],
        "ipv6_count":profile[4],
        "scope_counts":{"host":profile[5],"link":profile[6],"global":profile[7],"other":profile[8]},
    }

def interface_semantics(before,after,mapdiff):
    stable_before=[item for item in before if not is_veth(item)]
    stable_after=[item for item in after if not is_veth(item)]
    stable=mapdiff(stable_before,stable_after,"name",("operstate","link_type","loopback","ipv4_count","ipv6_count","scope_counts"))
    dynamic_before=[item for item in before if is_veth(item)]
    dynamic_after=[item for item in after if is_veth(item)]
    old={item["name"]:item for item in dynamic_before}
    new={item["name"]:item for item in dynamic_after}
    raw_added=[new[name] for name in sorted(new.keys()-old.keys())]
    raw_removed=[old[name] for name in sorted(old.keys()-new.keys())]
    raw_changed=[
        {"name":name,"before":old[name],"after":new[name]}
        for name in sorted(old.keys()&new.keys())
        if interface_profile(old[name])!=interface_profile(new[name])
    ]
    old_profiles=collections.Counter(interface_profile(item) for item in dynamic_before)
    new_profiles=collections.Counter(interface_profile(item) for item in dynamic_after)
    profiles=[]
    for profile in sorted(old_profiles.keys()|new_profiles.keys()):
        before_count=old_profiles[profile]
        after_count=new_profiles[profile]
        profiles.append({"profile":profile_object(profile),"before_count":before_count,"after_count":after_count,"delta":after_count-before_count})
    changed=bool(raw_added or raw_removed or raw_changed)
    classification="none" if not changed else ("informational" if all(row["delta"]==0 for row in profiles) else "attention")
    return {
        "stable":stable,
        "dynamic_veth":{
            "classification":classification,
            "name_pattern":VETH_PATTERN,
            "before_count":len(dynamic_before),
            "after_count":len(dynamic_after),
            "added_count":len(raw_added),
            "removed_count":len(raw_removed),
            "changed_count":len(raw_changed),
            "profiles":profiles,
            "raw_added":raw_added,
            "raw_removed":raw_removed,
            "raw_changed":raw_changed,
        },
    }
