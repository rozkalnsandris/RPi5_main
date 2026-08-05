#!/usr/bin/env python3
"""Apply an accepted V04 candidate to the tracked baseline with archive rollback."""
from __future__ import annotations
import argparse, importlib.util, json, os, pathlib, shutil, sys, tempfile
HERE=pathlib.Path(__file__).resolve().parent
def mod(name,file):
    s=importlib.util.spec_from_file_location(name,HERE/file); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
V=mod('v04','runtime-baseline-review-schema.py'); VER=mod('v04verify','verify-runtime-baseline-review.py'); ARCH=mod('v04archive','verify-runtime-baseline-archive.py')
def fail(m): print(f'apply-runtime-baseline-promotion: {m}',file=sys.stderr); raise SystemExit(1)
def main():
    p=argparse.ArgumentParser(); p.add_argument('--review',required=True); p.add_argument('--candidate',required=True); p.add_argument('--expected-current-sha256',required=True); a=p.parse_args()
    repo=V.repo_root(); current=repo/'baselines/runtime/current.json'; current_md=repo/'docs/CURRENT_RUNTIME_BASELINE.md'; archive=repo/'baselines/runtime/archive'; backup=None; entry_dir=None
    try:
        if not V.SHA_RE.fullmatch(a.expected_current_sha256): raise ValueError('invalid expected current digest')
        review,decision=VER.verify(a.review)
        if not decision or decision['decision']!='accepted': raise ValueError('accepted decision required')
        candidate_path=V.safe_artifact(a.candidate,root=repo); candidate=V.load_canonical(candidate_path); candidate_sha=V.sha_file(candidate_path)
        current_data=V.load_canonical(current); current_sha=V.sha_file(current)
        if current_sha!=a.expected_current_sha256 or current_sha!=review['current']['sha256']: raise ValueError('current baseline binding mismatch')
        if candidate_sha!=review['candidate']['sha256'] or candidate_sha==current_sha: raise ValueError('candidate binding mismatch')
        if candidate['metadata']['collection_utc']<=current_data['metadata']['collection_utc'] or not review['candidate_newer']: raise ValueError('candidate is not newer')
        if current_md.read_text()!=V.DOC.render(current_data): raise ValueError('current markdown mismatch')
        ARCH.verify(archive)
        entry_id=f"{V.slug_utc(current_data['metadata']['collection_utc'])}--{current_sha[:12]}"; entry_dir=archive/entry_id
        if entry_dir.exists(): raise ValueError('archive entry already exists')
        txbase=repo/'evidence/v04-transaction'; txbase.mkdir(parents=True,exist_ok=True); tx=pathlib.Path(tempfile.mkdtemp(prefix='promotion-',dir=txbase)); entry=tx/'entry'; entry.mkdir()
        shutil.copyfile(current,entry/'baseline.json'); shutil.copyfile(current_md,entry/'baseline.md'); rd=pathlib.Path(a.review)
        for n in ('review.json','runtime-diff.json','runtime-diff.md','decision.json'): shutil.copyfile(rd/n,entry/n)
        checks={n:V.sha_file(entry/n) for n in ('baseline.json','baseline.md','review.json','runtime-diff.json','runtime-diff.md','decision.json')}
        transition={'schema':'rpi5.runtime-baseline-transition.v1','entry_id':entry_id,'old':{'sha256':current_sha,'collection_utc':current_data['metadata']['collection_utc'],'source_commit':current_data['metadata']['source_commit'],'evidence_manifest_sha256':current_data['metadata']['evidence_manifest_sha256'],'context':current_data['metadata']['context']},'new':{'sha256':candidate_sha,'collection_utc':candidate['metadata']['collection_utc'],'source_commit':candidate['metadata']['source_commit'],'evidence_manifest_sha256':candidate['metadata']['evidence_manifest_sha256'],'context':candidate['metadata']['context']},'review_id':review['review_id'],'decision':'accepted','review_level':review['diff']['review_level'],'diff_json_sha256':review['diff']['json_sha256'],'diff_markdown_sha256':review['diff']['markdown_sha256'],'archive_checksums':checks}
        V.write_atomic(entry/'transition.json',V.canonical_bytes(transition)); names=['baseline.json','baseline.md','decision.json','review.json','runtime-diff.json','runtime-diff.md','transition.json']; V.write_atomic(entry/'SHA256SUMS',''.join(f"{V.sha_file(entry/n)}  {n}\n" for n in names).encode())
        index=json.loads((archive/'index.json').read_text()); index['entries'].append({'entry_id':entry_id,'old_collection_utc':current_data['metadata']['collection_utc'],'old_sha256':current_sha,'new_collection_utc':candidate['metadata']['collection_utc'],'new_sha256':candidate_sha,'review_id':review['review_id'],'decision':'accepted','review_level':review['diff']['review_level'],'transition_sha256':V.sha_file(entry/'transition.json')}); index['entries']=sorted(index['entries'],key=lambda x:(x['old_collection_utc'],x['entry_id']))
        V.write_atomic(tx/'index.json',V.canonical_bytes(index)); V.write_atomic(tx/'current.json',candidate_path.read_bytes()); V.write_atomic(tx/'current.md',V.DOC.render(candidate).encode())
        backup=tx/'backup'; backup.mkdir(); shutil.copyfile(current,backup/'current.json'); shutil.copyfile(current_md,backup/'current.md'); shutil.copyfile(archive/'index.json',backup/'index.json')
        shutil.move(str(entry),str(entry_dir))
        if os.environ.get('V04_FAIL_AFTER_ARCHIVE')=='1': raise RuntimeError('injected failure')
        os.replace(tx/'current.json',current); os.replace(tx/'current.md',current_md); os.replace(tx/'index.json',archive/'index.json'); ARCH.verify(archive)
        if V.sha_file(current)!=candidate_sha or current_md.read_text()!=V.DOC.render(candidate): raise ValueError('post-apply verification failed')
        shutil.rmtree(tx,ignore_errors=True); print(f'baselines/runtime/archive/{entry_id}/'); print('baselines/runtime/current.json'); print('docs/CURRENT_RUNTIME_BASELINE.md'); print('baselines/runtime/archive/index.json')
    except Exception as e:
        try:
            if backup and backup.exists():
                shutil.copyfile(backup/'current.json',current); shutil.copyfile(backup/'current.md',current_md); shutil.copyfile(backup/'index.json',archive/'index.json')
            if entry_dir and entry_dir.exists(): shutil.rmtree(entry_dir)
        except Exception: pass
        fail(str(e))
if __name__=='__main__': main()
