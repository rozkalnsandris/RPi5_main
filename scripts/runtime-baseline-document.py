#!/usr/bin/env python3
"""Deterministically render approved V02B baseline JSON as Markdown."""
from __future__ import annotations
import argparse, importlib.util, pathlib
_spec=importlib.util.spec_from_file_location('runtime_schema',pathlib.Path(__file__).with_name('runtime-baseline-schema.py'))
_schema=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_schema)

def render(payload: dict) -> str:
    _schema.validate(payload)
    containers=payload['docker']['containers']; projects=payload['docker']['compose_projects']; networks=payload['docker']['networks']
    enabled=payload['systemd']['enabled_units']; failed=payload['systemd']['failed_units']; timers=payload['systemd']['timers']
    lines=[
        '# Current runtime baseline','',
        'This is a verified, read-only runtime snapshot, not deployment configuration.','',
        '## Evidence binding','',
        f"- Collection UTC: `{payload['metadata']['collection_utc']}`",
        f"- Source commit: `{payload['metadata']['source_commit']}`",
        f"- Evidence manifest SHA-256: `{payload['metadata']['evidence_manifest_sha256']}`",
        f"- Collection context: `{payload['metadata']['context']}`",'',
        '## Docker','',
        f"- Engine version: `{payload['docker']['engine_version'] or 'unavailable'}`",
        f"- Compose version: `{payload['docker']['compose_version'] or 'unavailable'}`",
        f"- Containers: {len(containers)}; Compose projects: {len(projects)}; networks: {len(networks)}."
    ]
    for item in containers: lines.append(f"- Container `{item['name']}`: image `{item['image']}`, state `{item['state']}`, health `{item['health']}`.")
    for item in projects: lines.append(f"- Compose project `{item['name']}`: status `{item['status']}`.")
    for item in networks: lines.append(f"- Network `{item['name']}`: driver `{item['driver']}`, scope `{item['scope']}`.")
    lines += ['', '## systemd', '', f"- System state: `{payload['systemd']['system_state'] or 'unavailable'}`.", f"- Enabled units: {len(enabled)}; failed units: {len(failed)}; timers: {len(timers)}."]
    for item in enabled: lines.append(f"- Enabled `{item['name']}`: `{item['state']}`.")
    for item in failed: lines.append(f"- Failed `{item['name']}`: load `{item['load']}`, active `{item['active']}`, sub `{item['sub']}`.")
    for item in timers: lines.append(f"- Timer `{item['id']}`: load `{item['load']}`, active `{item['active']}`, sub `{item['sub']}`, activates `{item['activates']}`, next `{item['next']}`, last `{item['last']}`.")
    lines += ['', '## Listening ports', '']
    lines.extend(f"- `{item['protocol']}` `{item['address_scope']}` port `{item['port']}`." for item in payload['sockets'])
    lines += ['', '## Interfaces', '']
    for item in payload['interfaces']:
        scopes=', '.join(f'{key}={value}' for key,value in sorted(item['scope_counts'].items()))
        lines.append(f"- `{item['name']}`: operstate `{item['operstate']}`, link type `{item['link_type']}`, loopback `{str(item['loopback']).lower()}`, IPv4={item['ipv4_count']}, IPv6={item['ipv6_count']}; scopes {scopes}.")
    lines += ['', '## Limitations and interpretation', '', 'The entries above are direct, sanitized observations. They do not establish causation or serve as deployment configuration.']
    if payload['limitations']:
        lines.append('Unavailable or informational sections:')
        lines.extend(f"- `{item}`." for item in payload['limitations'])
    else:
        lines.append('- No command-capability limitations were recorded.')
    return '\n'.join(lines)+'\n'

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('baseline'); p.add_argument('--output')
    a=p.parse_args(); data=_schema.load(a.baseline); text=render(data)
    if a.output: pathlib.Path(a.output).write_text(text,encoding='utf-8')
    else: print(text,end='')
    return 0
if __name__=='__main__': raise SystemExit(main())
