#!/usr/bin/env python3
"""Strict, standard-library validation for sanitized V02B baseline JSON."""
from __future__ import annotations
import hashlib, ipaddress, json, pathlib, re

class SchemaError(ValueError): pass
_sha=re.compile(r"^[0-9a-f]{64}$"); _commit=re.compile(r"^[0-9a-f]{40}$"); _time=re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
_name=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,254}$"); _unit=re.compile(r"^[A-Za-z0-9@_.:-]{1,128}\.(?:service|timer)$"); _timer=re.compile(r"^[A-Za-z0-9@_.:-]{1,128}\.timer$")
_atom=re.compile(r"^[a-z][a-z_-]{0,31}$"); _mac=re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")

def _bad(v):
    for x in re.findall(r"[0-9A-Fa-f:.%]+", str(v)):
        try: ipaddress.ip_address(x.split('%',1)[0]); return True
        except ValueError: pass
    return bool(_mac.search(str(v)))
def _keys(v, keys):
    if not isinstance(v,dict) or set(v)!=set(keys): raise SchemaError('unknown or missing field')
def _text(v, pattern=_name):
    if not isinstance(v,str) or not pattern.fullmatch(v) or _bad(v): raise SchemaError('unsafe scalar')
def _sorted(items, key):
    if items != sorted(items,key=key) or len({key(x) for x in items}) != len(items): raise SchemaError('unsorted or duplicate identity')
def _list(v):
    if not isinstance(v,list): raise SchemaError('expected list')

def validate(data):
    _keys(data,('metadata','docker','systemd','sockets','interfaces','limitations'))
    m=data['metadata']; _keys(m,('schema_version','collection_utc','source_commit','evidence_manifest_sha256','context'))
    if m['schema_version']!='v02b.0.0' or not _time.fullmatch(m['collection_utc']) or not _commit.fullmatch(m['source_commit']) or not _sha.fullmatch(m['evidence_manifest_sha256']): raise SchemaError('invalid metadata')
    _text(m['context'],re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$'))
    d=data['docker']; _keys(d,('engine_version','compose_version','containers','compose_projects','networks'))
    for x in ('engine_version','compose_version'):
        if d[x] is not None: _text(d[x],re.compile(r'^[vV]?[0-9][A-Za-z0-9.+:_-]{0,63}$'))
    _list(d['containers'])
    for x in d['containers']:
        _keys(x,('name','image','state','health')); _text(x['name']); _text(x['image']); _text(x['state'],_atom)
        if x['health'] not in {'healthy','unhealthy','starting','none','unknown'}: raise SchemaError('invalid health')
    _sorted(d['containers'],lambda x:x['name'])
    for key,fields in (('compose_projects',('name','status')),('networks',('name','driver','scope'))):
        _list(d[key])
        for x in d[key]:
            _keys(x,fields); [_text(x[f]) for f in fields]
        _sorted(d[key],lambda x:x['name'])
    s=data['systemd']; _keys(s,('system_state','enabled_units','failed_units','timers'))
    if s['system_state'] is not None and s['system_state'] not in {'running','degraded','maintenance','starting','stopping','initializing','offline','unknown'}: raise SchemaError('invalid system state')
    for key,fields,identity in (('enabled_units',('name','state'),'name'),('failed_units',('name','load','active','sub'),'name')):
        _list(s[key])
        for x in s[key]:
            _keys(x,fields); _text(x['name'],_unit); [_text(x[f],_atom) for f in fields[1:]]
        _sorted(s[key],lambda x:x[identity])
    _list(s['timers'])
    for x in s['timers']:
        _keys(x,('id','load','active','sub','activates','next','last')); _text(x['id'],_timer); [_text(x[f],_atom) for f in ('load','active','sub')]
        if x['activates']!='n/a': _text(x['activates'],_unit)
        for f in ('next','last'):
            if not isinstance(x[f],str) or len(x[f])>96 or _bad(x[f]): raise SchemaError('unsafe timer time')
    _sorted(s['timers'],lambda x:x['id'])
    _list(data['sockets'])
    for x in data['sockets']:
        _keys(x,('protocol','address_scope','port'))
        if x['protocol'] not in {'tcp','tcp6','udp','udp6'} or x['address_scope'] not in {'wildcard','loopback','private_or_local','specific_other','unknown'} or not isinstance(x['port'],int) or not 1<=x['port']<=65535: raise SchemaError('invalid socket')
    _sorted(data['sockets'],lambda x:(x['protocol'],x['address_scope'],x['port']))
    _list(data['interfaces'])
    for x in data['interfaces']:
        _keys(x,('name','operstate','link_type','loopback','ipv4_count','ipv6_count','scope_counts')); _text(x['name'],re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}$')); _text(x['operstate'],_atom); _text(x['link_type'],_atom)
        if not isinstance(x['loopback'],bool) or not all(isinstance(x[f],int) and x[f]>=0 for f in ('ipv4_count','ipv6_count')): raise SchemaError('invalid interface')
        _keys(x['scope_counts'],('host','link','global','other'))
        if not all(isinstance(v,int) and v>=0 for v in x['scope_counts'].values()): raise SchemaError('invalid scope counts')
    _sorted(data['interfaces'],lambda x:x['name'])
    _list(data['limitations'])
    if data['limitations'] != sorted(set(data['limitations'])) or not all(isinstance(x,str) and len(x)<160 and not _bad(x) for x in data['limitations']): raise SchemaError('invalid limitations')
    raw=json.dumps(data,sort_keys=True)
    if re.search(r'(token|secret|private.key|authorization|environment|execstart|fragmentpath|configfiles|mount|label|command)',raw,re.I): raise SchemaError('forbidden field')
    return data

def load(path):
    p=pathlib.Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>2_000_000: raise SchemaError('invalid input artifact')
    for x in [p,*p.parents]:
        if x.is_symlink(): raise SchemaError('symlink path')
    try: return validate(json.loads(p.read_text(encoding='utf-8')))
    except (OSError,json.JSONDecodeError) as e: raise SchemaError('malformed input') from e
def digest(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
