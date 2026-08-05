#!/usr/bin/env python3
"""Prepare an immutable V04 runtime-baseline review bundle."""
from __future__ import annotations
import argparse, importlib.util, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v04',HERE/'runtime-baseline-review-schema.py')
V=importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
def fail(message): print(f'prepare-runtime-baseline-review: {message}',file=sys.stderr); raise SystemExit(1)
def main():
    p=argparse.ArgumentParser(); p.add_argument('--current',required=True); p.add_argument('--candidate',required=True); p.add_argument('--output',required=True); a=p.parse_args()
    try:
        root=V.repo_root(); current_path=pathlib.Path(a.current).resolve(strict=True); candidate_path=pathlib.Path(a.candidate).resolve(strict=True)
        if not __import__('os').environ.get('RPI5_REVIEW_TEST_ROOT') and current_path != (root/'baselines/runtime/current.json').resolve(strict=True): raise ValueError('invalid current path')
        current=V.load_canonical(current_path); candidate=V.load_canonical(candidate_path); current_sha=V.sha_file(current_path); candidate_sha=V.sha_file(candidate_path)
        rid=V.review_id(current_sha,candidate_sha,candidate['metadata']['collection_utc']); review_dir=V.ensure_output_base(a.output)/f'review-{rid}'
        if review_dir.exists(): raise ValueError('review already exists')
        review_dir.mkdir(parents=True,mode=0o700)
        diff=V.DIFF.report(current_path,candidate_path,current,candidate); diff_json=V.canonical_bytes(diff); diff_md=V.DIFF.markdown(diff).encode()
        review={'schema':'rpi5.runtime-baseline-review.v1','review_id':rid,'status':'awaiting_decision','current':{'sha256':current_sha,'baseline_schema':current['metadata']['schema_version'],'collection_utc':current['metadata']['collection_utc'],'source_commit':current['metadata']['source_commit'],'evidence_manifest_sha256':current['metadata']['evidence_manifest_sha256'],'context':current['metadata']['context']},'candidate':{'sha256':candidate_sha,'baseline_schema':candidate['metadata']['schema_version'],'collection_utc':candidate['metadata']['collection_utc'],'source_commit':candidate['metadata']['source_commit'],'evidence_manifest_sha256':candidate['metadata']['evidence_manifest_sha256'],'context':candidate['metadata']['context']},'diff':{'json_sha256':V.sha_bytes(diff_json),'markdown_sha256':V.sha_bytes(diff_md),'review_level':diff['summary']['review_level'],'summary':diff['summary']},'candidate_newer':candidate['metadata']['collection_utc']>current['metadata']['collection_utc']}
        V.write_atomic(review_dir/'runtime-diff.json',diff_json); V.write_atomic(review_dir/'runtime-diff.md',diff_md); V.write_atomic(review_dir/'review.json',V.canonical_bytes(review))
        V.write_atomic(review_dir/'file-inventory.txt',b'review.json\nruntime-diff.json\nruntime-diff.md\n')
        names=['file-inventory.txt','review.json','runtime-diff.json','runtime-diff.md']; V.write_atomic(review_dir/'SHA256SUMS',''.join(f"{V.sha_file(review_dir/n)}  {n}\n" for n in names).encode())
        print(str(review_dir)); print(f"review_level={diff['summary']['review_level']}")
    except Exception as e: fail(str(e))
if __name__=='__main__': main()
