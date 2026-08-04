#!/usr/bin/env python3
"""Strict offline verifier for deterministic V03 reports."""
from __future__ import annotations
import importlib.util,json,pathlib,sys
_spec=importlib.util.spec_from_file_location('runtime_diff',pathlib.Path(__file__).with_name('compare-runtime-baselines.py'))
_module=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_module)
DOMAINS,markdown=_module.DOMAINS,_module.markdown
def fail(): print('Runtime diff verification: FAIL',file=sys.stderr); raise SystemExit(1)
def main():
    if len(sys.argv)!=3: fail()
    repo=pathlib.Path(__file__).resolve().parent.parent; ps=[pathlib.Path(x) for x in sys.argv[1:]]
    for p in ps:
        q=p.resolve(strict=True)
        if not p.is_file() or p.is_symlink() or p.stat().st_size>1_000_000 or not any(str(q).startswith(str(repo/x)+'/') for x in ('evidence','exports')): fail()
    try: r=json.loads(ps[0].read_text(encoding='utf-8'))
    except Exception: fail()
    if set(r)!={'schema','inputs','summary','changes'} or r['schema']!='rpi5.runtime-diff.v1' or set(r['changes'])!=set(DOMAINS): fail()
    s=r['summary'];
    if set(s)!={'material_changes','informational_changes','added','removed','changed','per_domain','review_level'} or s['review_level'] not in {'none','informational','attention'}: fail()
    # Renderer equality plus lightweight no-unknown-object validation is the stable report contract.
    if ps[1].read_text(encoding='utf-8')!=markdown(r): fail()
    if any(not isinstance(v,dict) for v in r['changes'].values()) or set(s['per_domain'])!=set(DOMAINS): fail()
    expected='attention' if s['material_changes'] else ('informational' if s['informational_changes'] else 'none')
    if expected!=s['review_level'] or any(not isinstance(s[k],int) or s[k]<0 for k in ('material_changes','informational_changes','added','removed','changed')): fail()
    raw=ps[0].read_text(encoding='utf-8')+ps[1].read_text(encoding='utf-8')
    if any(x in raw.lower() for x in ('configfiles','environment=','execstart=','authorization:','private key','token=')): fail()
    print('Runtime diff verification: PASS')
if __name__=='__main__': main()
