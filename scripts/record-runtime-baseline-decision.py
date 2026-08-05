#!/usr/bin/env python3
"""Record a deterministic human decision for a verified V04 review."""
from __future__ import annotations
import argparse, importlib.util, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent
def mod(name,file):
    s=importlib.util.spec_from_file_location(name,HERE/file); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
V=mod('v04','runtime-baseline-review-schema.py'); VER=mod('v04verify','verify-runtime-baseline-review.py')
def fail(m): print(f'record-runtime-baseline-decision: {m}',file=sys.stderr); raise SystemExit(1)
def main():
    p=argparse.ArgumentParser(); p.add_argument('--review',required=True); p.add_argument('--decision',required=True,choices=sorted(V.DECISIONS)); p.add_argument('--reason',required=True); p.add_argument('--reviewer',required=True); p.add_argument('--decided-at',required=True); a=p.parse_args()
    try:
        review,existing=VER.verify(a.review); d=pathlib.Path(a.review)
        if existing or (d/'decision.json').exists() or (d/'DECISION_SHA256').exists(): raise ValueError('decision already exists')
        if a.reason not in V.REASONS or not V.USER_RE.fullmatch(a.reviewer) or not V.UTC_RE.fullmatch(a.decided_at): raise ValueError('invalid decision metadata')
        if a.decision=='accepted' and (not review['candidate_newer'] or review['current']['sha256']==review['candidate']['sha256']): raise ValueError('candidate is not promotable')
        data={'schema':'rpi5.runtime-baseline-decision.v1','review_id':review['review_id'],'current_sha256':review['current']['sha256'],'candidate_sha256':review['candidate']['sha256'],'diff_json_sha256':review['diff']['json_sha256'],'diff_markdown_sha256':review['diff']['markdown_sha256'],'review_level':review['diff']['review_level'],'decision':a.decision,'reason':a.reason,'reviewer':a.reviewer,'decided_at':a.decided_at}
        V.write_atomic(d/'decision.json',V.canonical_bytes(data)); V.write_atomic(d/'DECISION_SHA256',(V.sha_file(d/'decision.json')+'\n').encode()); VER.verify(d)
        print(f"decision={a.decision}"); print(f"review_id={review['review_id']}")
    except Exception as e: fail(str(e))
if __name__=='__main__': main()
