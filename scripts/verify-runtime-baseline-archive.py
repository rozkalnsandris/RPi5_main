#!/usr/bin/env python3
"""Verify the tracked V04 runtime baseline archive and index."""
from __future__ import annotations
import importlib.util, json, pathlib, re, sys
HERE=pathlib.Path(__file__).resolve().parent
def mod(name,file):
    s=importlib.util.spec_from_file_location(name,HERE/file); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
V=mod('v04','runtime-baseline-review-schema.py')
ENTRY_FILES={'baseline.json','baseline.md','review.json','runtime-diff.json','runtime-diff.md','decision.json','transition.json','SHA256SUMS'}
def fail(): print('Runtime baseline archive verification: FAIL',file=sys.stderr); raise SystemExit(1)
def _keys(v,k):
    if not isinstance(v,dict) or set(v)!=set(k): raise ValueError
def verify(root=None):
    repo=V.repo_root(); archive=pathlib.Path(root) if root else repo/'baselines/runtime/archive'; archive=archive.resolve(strict=True); archive.relative_to(repo)
    if archive.is_symlink() or not archive.is_dir(): raise ValueError
    allowed={'README.md','index.json'}|{p.name for p in archive.iterdir() if p.is_dir()}; actual={p.name for p in archive.iterdir()}
    if actual!=allowed: raise ValueError
    index=json.loads((archive/'index.json').read_text()); _keys(index,{'schema','entries'})
    if index['schema']!='rpi5.runtime-baseline-archive-index.v1' or not isinstance(index['entries'],list): raise ValueError
    if index['entries']!=sorted(index['entries'],key=lambda x:(x['old_collection_utc'],x['entry_id'])): raise ValueError
    dirs={p.name:p for p in archive.iterdir() if p.is_dir()}; seen=set()
    for entry in index['entries']:
        _keys(entry,{'entry_id','old_collection_utc','old_sha256','new_collection_utc','new_sha256','review_id','decision','review_level','transition_sha256'})
        if entry['entry_id'] in seen or entry['entry_id'] not in dirs: raise ValueError
        seen.add(entry['entry_id'])
        if entry['decision']!='accepted' or entry['review_level'] not in {'none','informational','attention'} or not V.UTC_RE.fullmatch(entry['old_collection_utc']) or not V.UTC_RE.fullmatch(entry['new_collection_utc']) or entry['new_collection_utc']<=entry['old_collection_utc']: raise ValueError
        for k in ('old_sha256','new_sha256','transition_sha256'):
            if not V.SHA_RE.fullmatch(entry[k]): raise ValueError
        d=dirs[entry['entry_id']]
        if d.is_symlink() or {p.name for p in d.iterdir()}!=ENTRY_FILES: raise ValueError
        for p in d.iterdir():
            if not p.is_file() or p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>2_000_000: raise ValueError
        sums={}
        for line in (d/'SHA256SUMS').read_text().splitlines():
            m=re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9._-]+)',line)
            if not m or m.group(2) in sums: raise ValueError
            sums[m.group(2)]=m.group(1)
        if set(sums)!=ENTRY_FILES-{'SHA256SUMS'}: raise ValueError
        for n,h in sums.items():
            if V.sha_file(d/n)!=h: raise ValueError
        baseline=V.load_canonical(d/'baseline.json')
        if V.sha_file(d/'baseline.json')!=entry['old_sha256'] or (d/'baseline.md').read_text()!=V.DOC.render(baseline): raise ValueError
        review=json.loads((d/'review.json').read_text()); decision=json.loads((d/'decision.json').read_text()); transition=json.loads((d/'transition.json').read_text())
        diff=json.loads((d/'runtime-diff.json').read_text())
        V.DIFF.validate_report(diff)
        if (d/'runtime-diff.md').read_text()!=V.DIFF.markdown(diff): raise ValueError
        _keys(transition,{'schema','entry_id','old','new','review_id','decision','review_level','diff_json_sha256','diff_markdown_sha256','archive_checksums'})
        if transition['schema']!='rpi5.runtime-baseline-transition.v1' or transition['entry_id']!=entry['entry_id'] or transition['review_id']!=entry['review_id'] or transition['decision']!='accepted' or transition['review_level']!=entry['review_level']: raise ValueError
        if transition['old']['sha256']!=entry['old_sha256'] or transition['new']['sha256']!=entry['new_sha256'] or V.sha_file(d/'transition.json')!=entry['transition_sha256']: raise ValueError
        if decision.get('decision')!='accepted' or decision.get('review_id')!=entry['review_id'] or review.get('review_id')!=entry['review_id']: raise ValueError
        expected={n:sums[n] for n in ('baseline.json','baseline.md','review.json','runtime-diff.json','runtime-diff.md','decision.json')}
        if transition['archive_checksums']!=expected: raise ValueError
    if set(dirs)!=seen: raise ValueError
    return index
def main():
    try:
        root=sys.argv[1] if len(sys.argv)==2 else None
        if len(sys.argv)>2: raise ValueError
        verify(root)
    except Exception: fail()
    print('Runtime baseline archive verification: PASS')
if __name__=='__main__': main()
