#!/usr/bin/env python3
"""Core report construction and rendering for runtime diffs."""
from __future__ import annotations
import importlib.util
import pathlib
import runtime_diff_dynamic as dynamic

_here=pathlib.Path(__file__).resolve().parent
_spec=importlib.util.spec_from_file_location("runtime_schema",_here/"runtime-baseline-schema.py")
_schema=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_schema)
digest=_schema.digest

SCHEMA_V1="rpi5.runtime-diff.v1"
SCHEMA_V2="rpi5.runtime-diff.v2"
DOMAINS=("docker_versions","containers","compose_projects","networks","systemd_state","enabled_units","failed_units","timers","sockets","interfaces","limitations")

def binding(path,data):
    metadata=data["metadata"]
    return {
        "sha256":digest(path),
        "baseline_schema":metadata["schema_version"],
        "collection_utc":metadata["collection_utc"],
        "source_commit":metadata["source_commit"],
        "evidence_manifest_sha256":metadata["evidence_manifest_sha256"],
        "context":metadata["context"],
    }

def mapdiff(before,after,key,fields,classification="attention"):
    old={item[key]:item for item in before}
    new={item[key]:item for item in after}
    added=[new[name] for name in sorted(new.keys()-old.keys())]
    removed=[old[name] for name in sorted(old.keys()-new.keys())]
    changed=[]
    for name in sorted(old.keys()&new.keys()):
        values={field:{"before":old[name][field],"after":new[name][field]} for field in fields if old[name][field]!=new[name][field]}
        if values:
            changed.append({key:name,"fields":values,"classification":classification})
    return {"added":added,"removed":removed,"changed":changed}

def summarize_v2(changes):
    material=informational=added=removed=changed_count=0
    per_domain={}
    for domain in DOMAINS:
        value=changes[domain]
        domain_material=domain_info=0
        if domain=="timers":
            structural=value["structural_changes"]
            domain_material+=sum(len(structural[key]) for key in ("added","removed","changed"))
            added+=len(structural["added"])
            removed+=len(structural["removed"])
            changed_count+=len(structural["changed"])
            domain_info+=len(value["temporal_changes"])
            changed_count+=len(value["temporal_changes"])
        elif domain=="limitations":
            domain_info+=len(value["added"])+len(value["removed"])
            added+=len(value["added"])
            removed+=len(value["removed"])
        elif domain=="sockets":
            stable=value["stable"]
            domain_material+=len(stable["added"])+len(stable["removed"])
            added+=len(stable["added"])
            removed+=len(stable["removed"])
            classification=value["dynamic_high_port"]["classification"]
            if classification=="attention":
                domain_material+=1
                changed_count+=1
            elif classification=="informational":
                domain_info+=1
                changed_count+=1
        elif domain=="interfaces":
            stable=value["stable"]
            domain_material+=sum(len(stable[key]) for key in ("added","removed","changed"))
            added+=len(stable["added"])
            removed+=len(stable["removed"])
            changed_count+=len(stable["changed"])
            classification=value["dynamic_veth"]["classification"]
            if classification=="attention":
                domain_material+=1
                changed_count+=1
            elif classification=="informational":
                domain_info+=1
                changed_count+=1
        else:
            for key in ("added","removed","changed"):
                for item in value.get(key,[]):
                    if item.get("classification")=="informational":
                        domain_info+=1
                    else:
                        domain_material+=1
                    if key=="added":
                        added+=1
                    elif key=="removed":
                        removed+=1
                    else:
                        changed_count+=1
        material+=domain_material
        informational+=domain_info
        per_domain[domain]={"material":domain_material,"informational":domain_info}
    socket_dynamic=changes["sockets"]["dynamic_high_port"]
    interface_dynamic=changes["interfaces"]["dynamic_veth"]
    level="attention" if material else ("informational" if informational else "none")
    return {
        "material_changes":material,
        "informational_changes":informational,
        "added":added,
        "removed":removed,
        "changed":changed_count,
        "per_domain":per_domain,
        "raw_observations":{
            "sockets":{"added":socket_dynamic["added_count"],"removed":socket_dynamic["removed_count"]},
            "interfaces":{"added":interface_dynamic["added_count"],"removed":interface_dynamic["removed_count"],"changed":interface_dynamic["changed_count"]},
        },
        "review_level":level,
    }

def report(before_path,after_path,before,after):
    changes={}
    changes["docker_versions"]={"changed":[
        {"field":field,"before":before["docker"][field],"after":after["docker"][field],"classification":"informational"}
        for field in ("engine_version","compose_version")
        if before["docker"][field]!=after["docker"][field]
    ]}
    changes["containers"]=mapdiff(before["docker"]["containers"],after["docker"]["containers"],"name",("image","state","health"))
    changes["compose_projects"]=mapdiff(before["docker"]["compose_projects"],after["docker"]["compose_projects"],"name",("status",))
    changes["networks"]=mapdiff(before["docker"]["networks"],after["docker"]["networks"],"name",("driver","scope"))
    changes["systemd_state"]={"changed":[] if before["systemd"]["system_state"]==after["systemd"]["system_state"] else [
        {"field":"system_state","before":before["systemd"]["system_state"],"after":after["systemd"]["system_state"],"classification":"attention"}
    ]}
    changes["enabled_units"]=mapdiff(before["systemd"]["enabled_units"],after["systemd"]["enabled_units"],"name",("state",))
    changes["failed_units"]=mapdiff(before["systemd"]["failed_units"],after["systemd"]["failed_units"],"name",("load","active","sub"))
    structural=mapdiff(before["systemd"]["timers"],after["systemd"]["timers"],"id",("load","active","sub","activates"))
    old_timers={item["id"]:item for item in before["systemd"]["timers"]}
    new_timers={item["id"]:item for item in after["systemd"]["timers"]}
    temporal=[]
    for name in sorted(old_timers.keys()&new_timers.keys()):
        values={field:{"before":old_timers[name][field],"after":new_timers[name][field]} for field in ("next","last") if old_timers[name][field]!=new_timers[name][field]}
        if values:
            temporal.append({"id":name,"fields":values,"classification":"informational"})
    changes["timers"]={"structural_changes":structural,"temporal_changes":temporal}
    changes["sockets"]=dynamic.socket_semantics(before["sockets"],after["sockets"])
    changes["interfaces"]=dynamic.interface_semantics(before["interfaces"],after["interfaces"],mapdiff)
    changes["limitations"]={
        "added":sorted(set(after["limitations"])-set(before["limitations"])),
        "removed":sorted(set(before["limitations"])-set(after["limitations"])),
        "classification":"informational",
    }
    return {
        "schema":SCHEMA_V2,
        "inputs":{"before":binding(before_path,before),"after":binding(after_path,after)},
        "summary":summarize_v2(changes),
        "changes":changes,
    }

def markdown_v1(data):
    summary=data["summary"]
    lines=[
        "# Runtime baseline diff","",f"Schema: `{data['schema']}`","",
        f"Review level: `{summary['review_level']}`.",
        f"Material changes: {summary['material_changes']}; informational changes: {summary['informational_changes']}.","",
        "This is an offline metadata comparison. No host collection or mutation occurred. Differences are facts, not a causal diagnosis.","",
    ]
    if summary["review_level"]=="none":
        lines+=["No runtime drift detected.",""]
    for domain in DOMAINS:
        value=data["changes"][domain]
        lines+=["## "+domain,""]
        for key in sorted(value):
            if isinstance(value[key],list) and value[key]:
                lines.append(f"- {key}: {len(value[key])}.")
            elif isinstance(value[key],dict) and value[key]:
                lines.append(f"- {key}: {sum(len(item) for item in value[key].values() if isinstance(item,list))}.")
    lines+=["","Timer structural changes are attention; next/last timestamp movement is informational."]
    return "\n".join(lines)+"\n"

def markdown_v2(data):
    summary=data["summary"]
    raw=summary["raw_observations"]
    lines=[
        "# Runtime baseline diff","",f"Schema: `{data['schema']}`","",
        f"Review level: `{summary['review_level']}`.",
        f"Semantic material changes: {summary['material_changes']}; semantic informational changes: {summary['informational_changes']}.",
        f"Raw dynamic observations retained: sockets +{raw['sockets']['added']}/-{raw['sockets']['removed']}; interfaces +{raw['interfaces']['added']}/-{raw['interfaces']['removed']}/~{raw['interfaces']['changed']}.","",
        "This is an offline metadata comparison. No host collection or mutation occurred. Differences are facts, not a causal diagnosis.","",
    ]
    if summary["review_level"]=="none":
        lines+=["No runtime drift detected.",""]
    for domain in DOMAINS:
        value=data["changes"][domain]
        lines+=["## "+domain,""]
        if domain=="sockets":
            stable=value["stable"]
            group=value["dynamic_high_port"]
            if stable["added"]:
                lines.append(f"- stable added: {len(stable['added'])}.")
            if stable["removed"]:
                lines.append(f"- stable removed: {len(stable['removed'])}.")
            if group["classification"]!="none":
                lines.append(f"- dynamic high-port churn: {group['classification']}; raw +{group['added_count']}/-{group['removed_count']}; aggregate {group['before_count']} -> {group['after_count']}.")
        elif domain=="interfaces":
            stable=value["stable"]
            group=value["dynamic_veth"]
            for key in ("added","removed","changed"):
                if stable[key]:
                    lines.append(f"- stable {key}: {len(stable[key])}.")
            if group["classification"]!="none":
                lines.append(f"- dynamic veth churn: {group['classification']}; raw +{group['added_count']}/-{group['removed_count']}/~{group['changed_count']}; aggregate {group['before_count']} -> {group['after_count']}.")
        else:
            for key in sorted(value):
                if isinstance(value[key],list) and value[key]:
                    lines.append(f"- {key}: {len(value[key])}.")
                elif isinstance(value[key],dict) and value[key]:
                    lines.append(f"- {key}: {sum(len(item) for item in value[key].values() if isinstance(item,list))}.")
    lines+=["",
        f"Ports below {dynamic.HIGH_PORT_FLOOR} remain exact material identities. High-numbered socket observations remain raw in JSON but are grouped; bucket emergence/disappearance or a per-bucket count delta above {dynamic.HIGH_PORT_BUCKET_DELTA_TOLERANCE} is attention.",
        "Dynamically named veth observations remain raw in JSON but are grouped by profile. Pure name rotation with an unchanged profile multiset is informational; count or profile changes are attention.",
        "Timer structural changes are attention; next/last timestamp movement is informational.",
    ]
    return "\n".join(lines)+"\n"

def markdown(data):
    if data.get("schema")==SCHEMA_V1:
        return markdown_v1(data)
    if data.get("schema")==SCHEMA_V2:
        return markdown_v2(data)
    raise ValueError("unsupported runtime diff schema")
