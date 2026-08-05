#!/usr/bin/env python3
"""Verify V04 review bundles and optional human decisions."""
from __future__ import annotations
import importlib.util, json, pathlib, re, sys
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v04',HERE/'runtime-baseline-review-schema.py')
V=importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
BASE_FILES={'review.json','runtime-diff.json','runtime-diff.md','file-inventory.txt','SHA256SUMS'}
DECISION_FILES={'decision.json','DECISION_SHA256'}
FORBIDDEN=re.compile(r'(configfiles|environment=|execstart=|authorization:|private key|token=|(?:[0-9a-f]{2}:){5}[0-9a-f]{2})',re.I)
def fail(): print('Runtime baseline review verification: FAIL',file=sys.stderr); raise SystemExit(1)
def _exact_keys(v,keys):
    if not isinstance(v,dict) or set(v)!=set(keys): raise ValueError
def verify(review_dir):
    d=pathlib.Path(review_dir); q=d.resolve(strict=True); q.relative_to(V.repo_root())
    if not d.is_dir() or d.is_symlink(): raise ValueError
    for x in (d,*d.parents):
        if x.is_symlink(): raise ValueError
    files={p.name for p in d.iterdir()}
    if files not in (BASE_FILES,BASE_FILES|DECISION_FILES): raise ValueError
    for p in d.iterdir():
        if not p.is_file() or p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>1_000_000: raise ValueError
    expected={}
    for line in (d/'SHA256SUMS').read_text().splitlines():
        m=re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9._-]+)',line)
        if not m or m.group(2) in expected: raise ValueError
        expected[m.group(2)]=m.group(1)
    if set(expected)!=BASE_FILES-{'SHA256SUMS'}: raise ValueError
    for name,h in expected.items():
        if V.sha_file(d/name)!=h: raise ValueError
    if (d/'file-inventory.txt').read_text()!='review.json\nruntime-diff.json\nruntime-diff.md\n': raise ValueError
    review=json.loads((d/'review.json').read_text()); _exact_keys(review,{'schema','review_id','status','current','candidate','diff','candidate_newer'})
    if review['schema']!='rpi5.runtime-baseline-review.v1' or review['status']!='awaiting_decision' or not isinstance(review['candidate_newer'],bool): raise ValueError
    binding={'sha256','baseline_schema','collection_utc','source_commit','evidence_manifest_sha256','context'}
    for k in ('current','candidate'):
        _exact_keys(review[k],binding); b=review[k]
        if not V.SHA_RE.fullmatch(b['sha256']) or b['baseline_schema']!='v02b.0.0' or not V.UTC_RE.fullmatch(b['collection_utc']) or not V.COMMIT_RE.fullmatch(b['source_commit']) or not V.SHA_RE.fullmatch(b['evidence_manifest_sha256']): raise ValueError
    if review['review_id']!=V.review_id(review['current']['sha256'],review['candidate']['sha256'],review['candidate']['collection_utc']): raise ValueError
    _exact_keys(review['diff'],{'json_sha256','markdown_sha256','review_level','summary'})
    if review['diff']['review_level'] not in {'none','informational','attention'}: raise ValueError
    if V.sha_file(d/'runtime-diff.json')!=review['diff']['json_sha256'] or V.sha_file(d/'runtime-diff.md')!=review['diff']['markdown_sha256']: raise ValueError
    diff=json.loads((d/'runtime-diff.json').read_text())
    if (d/'runtime-diff.md').read_text()!=V.DIFF.markdown(diff): raise ValueError
    if diff.get('schema')!='rpi5.runtime-diff.v1' or diff.get('summary')!=review['diff']['summary'] or diff['summary']['review_level']!=review['diff']['review_level']: raise ValueError
    if diff['inputs']['before']['sha256']!=review['current']['sha256'] or diff['inputs']['after']['sha256']!=review['candidate']['sha256']: raise ValueError
    raw=''.join(p.read_text(errors='ignore') for p in d.iterdir())
    if FORBIDDEN.search(raw): raise ValueError
    decision=None
    if DECISION_FILES <= files:
        decision=json.loads((d/'decision.json').read_text()); _exact_keys(decision,{'schema','review_id','current_sha256','candidate_sha256','diff_json_sha256','diff_markdown_sha256','review_level','decision','reason','reviewer','decided_at'})
        if decision['schema']!='rpi5.runtime-baseline-decision.v1' or decision['review_id']!=review['review_id'] or decision['current_sha256']!=review['current']['sha256'] or decision['candidate_sha256']!=review['candidate']['sha256'] or decision['diff_json_sha256']!=review['diff']['json_sha256'] or decision['diff_markdown_sha256']!=review['diff']['markdown_sha256'] or decision['review_level']!=review['diff']['review_level']: raise ValueError
        if decision['decision'] not in V.DECISIONS or decision['reason'] not in V.REASONS or not V.USER_RE.fullmatch(decision['reviewer']) or not V.UTC_RE.fullmatch(decision['decided_at']): raise ValueError
        digest=(d/'DECISION_SHA256').read_text().strip()
        if not V.SHA_RE.fullmatch(digest) or digest!=V.sha_file(d/'decision.json'): raise ValueError
        if decision['decision']=='accepted' and (not review['candidate_newer'] or review['current']['sha256']==review['candidate']['sha256']): raise ValueError
    return review,decision
def main():
    if len(sys.argv)!=2: fail()
    try: verify(sys.argv[1])
    except Exception: fail()
    print('Runtime baseline review verification: PASS')
if __name__=='__main__': main()
