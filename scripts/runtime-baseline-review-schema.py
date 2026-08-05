#!/usr/bin/env python3
"""Shared schemas and safe helpers for V04 runtime baseline review."""
from __future__ import annotations
import hashlib, importlib.util, json, os, pathlib, re, tempfile
HERE=pathlib.Path(__file__).resolve().parent
def _load_module(name, filename):
    spec=importlib.util.spec_from_file_location(name,HERE/filename); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
BASE=_load_module('v04_baseline_schema','runtime-baseline-schema.py')
DIFF=_load_module('v04_runtime_diff','compare-runtime-baselines.py')
DOC=_load_module('v04_runtime_doc','runtime-baseline-document.py')
SHA_RE=re.compile(r'^[0-9a-f]{64}$'); COMMIT_RE=re.compile(r'^[0-9a-f]{40}$'); UTC_RE=re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
USER_RE=re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$')
REASONS={'expected_change','approved_maintenance','inventory_refresh','no_change_refresh','needs_investigation','unexpected_change','incomplete_evidence','no_second_snapshot','other_review_required'}
DECISIONS={'accepted','rejected','deferred'}
def repo_root():
    value=os.environ.get('RPI5_REVIEW_TEST_ROOT')
    return pathlib.Path(value).resolve() if value else HERE.parent
def canonical_bytes(data): return (json.dumps(data,sort_keys=True,indent=2)+'\n').encode()
def sha_bytes(data): return hashlib.sha256(data).hexdigest()
def sha_file(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def safe_artifact(path, *, root=None, max_size=2_000_000):
    p=pathlib.Path(path); q=p.resolve(strict=True); allowed=(root or repo_root()).resolve(); q.relative_to(allowed)
    if not p.is_file() or p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>max_size: raise ValueError('invalid artifact')
    for x in (p,*p.parents):
        if x.is_symlink(): raise ValueError('symlink path')
    return q
def load_canonical(path):
    p=safe_artifact(path); data=BASE.load(p)
    if p.read_bytes()!=canonical_bytes(data): raise ValueError('baseline is not canonical JSON')
    return data
def review_id(current_sha,candidate_sha,candidate_utc):
    return hashlib.sha256(f'{current_sha}\n{candidate_sha}\n{candidate_utc}\n'.encode()).hexdigest()[:32]
def write_atomic(path, content: bytes, mode=0o600):
    path=pathlib.Path(path); path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.v04-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as h: h.write(content); h.flush(); os.fsync(h.fileno())
        os.chmod(tmp,mode); os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def ensure_output_base(value):
    root=repo_root(); p=pathlib.Path(value); q=(p if p.is_absolute() else pathlib.Path.cwd()/p).resolve(strict=False)
    if not os.environ.get('RPI5_REVIEW_TEST_ROOT'):
        if not any(str(q).startswith(str(root/x)+os.sep) for x in ('evidence','exports')): raise ValueError('output outside evidence/exports')
    else: q.relative_to(root)
    if any(x.is_symlink() for x in (q,*q.parents)): raise ValueError('symlink output')
    return q
def slug_utc(value): return value.replace(':','-')
