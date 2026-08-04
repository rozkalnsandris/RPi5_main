#!/usr/bin/env python3
"""Deterministic, offline comparison of two validated V02B baselines."""
from __future__ import annotations
import argparse, importlib.util, json, os, pathlib, tempfile
_spec=importlib.util.spec_from_file_location('runtime_schema',pathlib.Path(__file__).with_name('runtime-baseline-schema.py'))
_module=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_module)
SchemaError,digest,load=_module.SchemaError,_module.digest,_module.load

DOMAINS=('docker_versions','containers','compose_projects','networks','systemd_state','enabled_units','failed_units','timers','sockets','interfaces','limitations')
def die(m,code=1): raise SystemExit(code)
def binding(path,data):
    m=data['metadata']; return {'sha256':digest(path),'baseline_schema':m['schema_version'],'collection_utc':m['collection_utc'],'source_commit':m['source_commit'],'evidence_manifest_sha256':m['evidence_manifest_sha256'],'context':m['context']}
def mapdiff(a,b,key,fields,cls='attention'):
    ident=(lambda x:x[key]) if isinstance(key,str) else key; label=key if isinstance(key,str) else 'identity'
    aa={ident(x):x for x in a}; bb={ident(x):x for x in b}; add=[bb[x] for x in sorted(bb.keys()-aa.keys())]; rem=[aa[x] for x in sorted(aa.keys()-bb.keys())]; ch=[]
    for name in sorted(aa.keys()&bb.keys()):
        vals={f:{'before':aa[name][f],'after':bb[name][f]} for f in fields if aa[name][f]!=bb[name][f]}
        if vals: ch.append({label:name,'fields':vals,'classification':cls})
    return {'added':add,'removed':rem,'changed':ch}
def report(before_path,after_path,before,after):
    changes={}
    changes['docker_versions']={'changed':[{'field':f,'before':before['docker'][f],'after':after['docker'][f],'classification':'informational'} for f in ('engine_version','compose_version') if before['docker'][f]!=after['docker'][f]]}
    changes['containers']=mapdiff(before['docker']['containers'],after['docker']['containers'],'name',('image','state','health'))
    changes['compose_projects']=mapdiff(before['docker']['compose_projects'],after['docker']['compose_projects'],'name',('status',))
    changes['networks']=mapdiff(before['docker']['networks'],after['docker']['networks'],'name',('driver','scope'))
    changes['systemd_state']={'changed':([] if before['systemd']['system_state']==after['systemd']['system_state'] else [{'field':'system_state','before':before['systemd']['system_state'],'after':after['systemd']['system_state'],'classification':'attention'}])}
    changes['enabled_units']=mapdiff(before['systemd']['enabled_units'],after['systemd']['enabled_units'],'name',('state',))
    changes['failed_units']=mapdiff(before['systemd']['failed_units'],after['systemd']['failed_units'],'name',('load','active','sub'))
    structural=mapdiff(before['systemd']['timers'],after['systemd']['timers'],'id',('load','active','sub','activates'))
    temporal=[]
    aa={x['id']:x for x in before['systemd']['timers']}; bb={x['id']:x for x in after['systemd']['timers']}
    for name in sorted(aa.keys()&bb.keys()):
        vals={f:{'before':aa[name][f],'after':bb[name][f]} for f in ('next','last') if aa[name][f]!=bb[name][f]}
        if vals: temporal.append({'id':name,'fields':vals,'classification':'informational'})
    changes['timers']={'structural_changes':structural,'temporal_changes':temporal}
    changes['sockets']=mapdiff(before['sockets'],after['sockets'],lambda x:(x['protocol'],x['address_scope'],x['port']),())
    # normalize tuple identities into approved objects only
    changes['sockets']={'added':changes['sockets']['added'],'removed':changes['sockets']['removed']}
    changes['interfaces']=mapdiff(before['interfaces'],after['interfaces'],'name',('operstate','link_type','loopback','ipv4_count','ipv6_count','scope_counts'))
    changes['limitations']={'added':sorted(set(after['limitations'])-set(before['limitations'])),'removed':sorted(set(before['limitations'])-set(after['limitations'])),'classification':'informational'}
    material=info=added=removed=changed=0; per={}
    for d,c in changes.items():
        mats=infos=0
        if d=='timers':
            g=c['structural_changes']; mats+=len(g['added'])+len(g['removed'])+len(g['changed']); added+=len(g['added']); removed+=len(g['removed']); changed+=len(g['changed'])
            infos+=len(c['temporal_changes']); changed+=len(c['temporal_changes'])
        elif d=='limitations':
            infos+=len(c['added'])+len(c['removed']); added+=len(c['added']); removed+=len(c['removed'])
        else:
            for k in ('added','removed','changed'):
                for x in c.get(k,[]):
                    informational=x.get('classification')=='informational'
                    if informational: infos+=1
                    else: mats+=1
                    if k=='added': added+=1
                    elif k=='removed': removed+=1
                    else: changed+=1
        material+=mats; info+=infos; per[d]={'material':mats,'informational':infos}
    level='attention' if material else ('informational' if info else 'none')
    return {'schema':'rpi5.runtime-diff.v1','inputs':{'before':binding(before_path,before),'after':binding(after_path,after)},'summary':{'material_changes':material,'informational_changes':info,'added':added,'removed':removed,'changed':changed,'per_domain':per,'review_level':level},'changes':changes}
def markdown(r):
    s=r['summary']; lines=['# Runtime baseline diff','',f"Schema: `{r['schema']}`",'',f"Review level: `{s['review_level']}`.",f"Material changes: {s['material_changes']}; informational changes: {s['informational_changes']}.",'','This is an offline metadata comparison. No host collection or mutation occurred. Differences are facts, not a causal diagnosis.','']
    if s['review_level']=='none': lines+=['No runtime drift detected.','']
    for d in DOMAINS:
        c=r['changes'][d]; lines+=['## '+d,'']
        for k in sorted(c):
            if isinstance(c[k],list) and c[k]: lines.append(f'- {k}: {len(c[k])}.')
            elif isinstance(c[k],dict) and c[k]: lines.append(f"- {k}: {sum(len(v) for v in c[k].values() if isinstance(v,list))}.")
    lines+=['','Timer structural changes are attention; next/last timestamp movement is informational.']
    return '\n'.join(lines)+'\n'
def atomic(path,text):
    path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.v03-',dir=path.parent,text=True)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as h: h.write(text); h.flush(); os.fsync(h.fileno())
        os.chmod(tmp,0o600); os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def allowed(repo,p):
    q=p.resolve(strict=False)
    if not any(str(q).startswith(str(repo/x)+'/') for x in ('evidence','exports')): die('output outside evidence/exports')
    if q.exists(): die('refusing overwrite')
    if any(x.is_symlink() for x in [q,*q.parents]): die('symlink output')
    return q
def main():
    p=argparse.ArgumentParser(); p.add_argument('--before',required=True);p.add_argument('--after',required=True);p.add_argument('--json-out',required=True);p.add_argument('--markdown-out',required=True);a=p.parse_args()
    if len({a.before,a.after,a.json_out,a.markdown_out})<2: die('invalid paths',2)
    repo=pathlib.Path(__file__).resolve().parent.parent
    try: b=load(a.before); c=load(a.after)
    except SchemaError: die('invalid baseline input')
    jo=allowed(repo,pathlib.Path(a.json_out)); mo=allowed(repo,pathlib.Path(a.markdown_out)); r=report(a.before,a.after,b,c); atomic(jo,json.dumps(r,sort_keys=True,indent=2)+'\n'); atomic(mo,markdown(r))
if __name__=='__main__': main()
