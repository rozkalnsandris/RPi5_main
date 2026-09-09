#!/usr/bin/env python3
from __future__ import annotations
import base64,ctypes,errno,hashlib,json,os,re,stat,sys
from pathlib import Path

BASE=Path('/var/lib/rozkalns-dashboard-handoff-exec'); ROOT=BASE/'v1'; PART=BASE/'.v1.execution-bundle-remediation-partial'
BOOT=BASE/'.bundle-materializer-v1.py'; BOOT_PART=BASE/'.bundle-materializer-v1.py.remediation-partial'; SELF=BASE/'.bundle-remediator-v1.py'
OLD_BOOT_Q=BASE/'.bundle-materializer-v1.py.stale-78dcf901-112f272e'; OLD_ROOT_Q=BASE/'.v1.stale-112f272e-92036c09-bytecode-5b1e05af'
ENTRY='dashboard-rpi5-preverified-handoff-materializer.py'; CORE='dashboard-rpi5-preverified-handoff-materializer-core.py'; MAN='execution-manifest.json'; CACHE='__pycache__'; PYC='dashboard-rpi5-preverified-handoff-materializer-core.cpython-311.pyc'
NEW_MAT_BLOB='f4e90e26b3e9fbd89b5da74c23c778678ad4da5b'; NEW_ENTRY_BLOB='d2463e61fade6a3fa0a60f9d09a52c1a479b3f86'; NEW_CORE_BLOB='409ea15dcb72e7361278dfd4065228c99fa840d2'
OLD_BOOT_BLOB='78dcf901b6c48db11024909946e47cd62b558c10'; OLD_BOOT_SHA256='94610eaf208c81b165a48636458150811f12e3579bc8b28994e575d08069dd4d'
OLD_ENTRY_BLOB='da6b3756ec49436de3855a8c13f273954a919d22'; OLD_ENTRY_SHA256='3e3a6da124980e3aa464ba92fe5020deee61cd81cedcfa2a057d890a5de933b0'
OLD_CORE_BLOB='409ea15dcb72e7361278dfd4065228c99fa840d2'; OLD_CORE_SHA256='26c5474358fab1005b1092d6c83c2319c82f7d3b51ee9e30f493eb13a577c53f'
OLD_MAN_SHA256='0850a5e3efdea8a5ec5eec30e8b17bc9041eef0eb49565e0143832f26e7f0e1c'; OLD_PYC_SHA256='5b1e05afbd99bf03ce1bc277b4242dd79f8fc26e61bc8f5e7d36cebbe185bc95'
OLD_MAIN='112f272ebcbce1f4a20bae32d4bf37d2927ee603'; OLD_TREE='92036c09964f79bdc36ec2a0a1175d1ef0bddf51'
ACK='RPi5_main:DASHBOARD-HANDOFF-EXECUTION-BUNDLE-BYTECODE-REMEDIATE-V1'; MAX=3*1024*1024; SHA40=re.compile(r'^[0-9a-f]{40}$')
class Stop(RuntimeError): pass

def blob(b): return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def mode(st): return stat.S_IMODE(st.st_mode)
def meta(st,m,d,label):
    if (d and not stat.S_ISDIR(st.st_mode)) or (not d and not stat.S_ISREG(st.st_mode)) or st.st_uid or st.st_gid or mode(st)!=m: raise Stop(label+' metadata mismatch')
def strict(raw):
    def hook(pairs):
        d={}
        for k,v in pairs:
            if k in d: raise Stop('duplicate JSON key')
            d[k]=v
        return d
    try: v=json.loads(raw.decode(),object_pairs_hook=hook)
    except Stop: raise
    except Exception as e: raise Stop('invalid JSON') from e
    if type(v) is not dict: raise Stop('JSON root mismatch')
    return v
def b64(v,label):
    try: b=base64.b64decode(v,validate=True)
    except Exception as e: raise Stop(label+' base64 invalid') from e
    if len(b)>1024*1024: raise Stop(label+' too large')
    return b
def readall(fd,maxn,label):
    out=b''
    while True:
        c=os.read(fd,min(65536,maxn+1-len(out)))
        if not c: return out
        out+=c
        if len(out)>maxn: raise Stop(label+' too large')
def read_path(p,m,label,maxn=1048576):
    f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try: meta(os.fstat(f),m,False,label); return readall(f,maxn,label)
    finally: os.close(f)
def read_at(fd,n,m,label,maxn=1048576):
    f=os.open(n,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try: meta(os.fstat(f),m,False,label); return readall(f,maxn,label)
    finally: os.close(f)
def open_dir(p,m,label):
    fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW); meta(os.fstat(fd),m,True,label); return fd
def absent(fd,n):
    try: os.stat(n,dir_fd=fd,follow_symlinks=False)
    except FileNotFoundError:return
    raise Stop(n+' already exists')
def write(fd,n,b):
    f=os.open(n,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400,dir_fd=fd)
    try:
        v=memoryview(b)
        while v:
            w=os.write(f,v)
            if w<=0: raise Stop('short write')
            v=v[w:]
        os.fchown(f,0,0); os.fchmod(f,0o444); os.fsync(f)
    finally: os.close(f)
def rename(fd,a,b):
    f=ctypes.CDLL(None,use_errno=True).renameat2; f.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]; f.restype=ctypes.c_int
    if f(fd,os.fsencode(a),fd,os.fsencode(b),1):
        e=ctypes.get_errno()
        if e==errno.EEXIST: raise Stop(b+' appeared before rename')
        raise OSError(e,os.strerror(e))
def parse(raw):
    p=strict(raw); req={'schema','bundle_materializer_b64','entrypoint_b64','core_b64','manifest_b64'}
    if set(p)!=req or p['schema']!='dashboard-rpi5.handoff-execution-bytecode-remediation-payload.v1': raise Stop('payload shape mismatch')
    bm,e,c,r=b64(p['bundle_materializer_b64'],'bundle materializer'),b64(p['entrypoint_b64'],'entrypoint'),b64(p['core_b64'],'core'),b64(p['manifest_b64'],'manifest')
    if blob(bm)!=NEW_MAT_BLOB or blob(e)!=NEW_ENTRY_BLOB or blob(c)!=NEW_CORE_BLOB: raise Stop('payload Git blob mismatch')
    m=strict(r); reqm={'schema','capability','source_repository','source_main_sha','source_tree_sha','entrypoint','core'}
    if set(m)!=reqm or m['schema']!='dashboard-rpi5.handoff-execution-bundle.v1' or m['capability']!='dashboard-rpi5.preverified-handoff-materializer.v1' or m['source_repository']!='rozkalnsandris/RPi5_main': raise Stop('manifest identity mismatch')
    if type(m['source_main_sha']) is not str or type(m['source_tree_sha']) is not str or not SHA40.fullmatch(m['source_main_sha']) or not SHA40.fullmatch(m['source_tree_sha']): raise Stop('manifest source hash shape mismatch')
    for k,path,h,data in [('entrypoint','scripts/dashboard-rpi5-preverified-handoff-materializer.py',NEW_ENTRY_BLOB,e),('core','scripts/dashboard-rpi5-preverified-handoff-materializer-core.py',NEW_CORE_BLOB,c)]:
        x=m[k]
        if type(x) is not dict or set(x)!={'repo_path','git_blob_sha','sha256'} or x['repo_path']!=path or x['git_blob_sha']!=h or x['sha256']!=hashlib.sha256(data).hexdigest(): raise Stop(k+' binding mismatch')
    return bm,e,c,r,m
def verify_new_bundle(p,expected):
    fd=open_dir(p,0o555,'new bundle')
    try:
        if sorted(os.listdir(fd))!=sorted([ENTRY,CORE,MAN]): raise Stop('new bundle tree mismatch')
        got=(read_at(fd,ENTRY,0o444,ENTRY),read_at(fd,CORE,0o444,CORE),read_at(fd,MAN,0o444,MAN,65536))
    finally: os.close(fd)
    if got!=expected: raise Stop('new bundle bytes mismatch')
def verify_old_boot(p):
    b=read_path(p,0o444,'old bootstrap')
    if blob(b)!=OLD_BOOT_BLOB or hashlib.sha256(b).hexdigest()!=OLD_BOOT_SHA256: raise Stop('old bootstrap identity mismatch')
def verify_old_root(p):
    fd=open_dir(p,0o555,'old bundle')
    try:
        if sorted(os.listdir(fd))!=sorted([ENTRY,CORE,MAN,CACHE]): raise Stop('old bundle tree mismatch')
        e=read_at(fd,ENTRY,0o444,'old entrypoint'); c=read_at(fd,CORE,0o444,'old core'); r=read_at(fd,MAN,0o444,'old manifest',65536)
        q=os.open(CACHE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
        try:
            meta(os.fstat(q),0o755,True,'old bytecode cache')
            if os.listdir(q)!=[PYC]: raise Stop('old bytecode cache tree mismatch')
            pyc=read_at(q,PYC,0o644,'old bytecode file')
        finally: os.close(q)
    finally: os.close(fd)
    if blob(e)!=OLD_ENTRY_BLOB or hashlib.sha256(e).hexdigest()!=OLD_ENTRY_SHA256: raise Stop('old entrypoint identity mismatch')
    if blob(c)!=OLD_CORE_BLOB or hashlib.sha256(c).hexdigest()!=OLD_CORE_SHA256: raise Stop('old core identity mismatch')
    if hashlib.sha256(r).hexdigest()!=OLD_MAN_SHA256 or hashlib.sha256(pyc).hexdigest()!=OLD_PYC_SHA256: raise Stop('old manifest/bytecode identity mismatch')
    m=strict(r)
    if m.get('source_main_sha')!=OLD_MAIN or m.get('source_tree_sha')!=OLD_TREE or m.get('source_repository')!='rozkalnsandris/RPi5_main': raise Stop('old manifest source identity mismatch')
def verify_new_boot(p,b):
    got=read_path(p,0o444,'new bootstrap')
    if got!=b or blob(got)!=NEW_MAT_BLOB: raise Stop('new bootstrap identity mismatch')
def main():
    if os.geteuid()!=0 or Path(os.path.abspath(__file__))!=SELF: raise Stop('fixed root-owned remediator required')
    if sys.argv[1:]!=['--apply','--ack',ACK]: raise Stop('authorization arguments mismatch')
    read_path(SELF,0o444,'remediator')
    raw=sys.stdin.buffer.read(MAX+1)
    if len(raw)>MAX: raise Stop('payload too large')
    bm,e,c,r,m=parse(raw)
    p=open_dir(BASE.parent,0o755,'parent'); os.close(p)
    b=open_dir(BASE,0o755,'base')
    try:
        for n in [PART.name,BOOT_PART.name,OLD_BOOT_Q.name,OLD_ROOT_Q.name]: absent(b,n)
        verify_old_boot(BOOT); verify_old_root(ROOT)
        write(b,BOOT_PART.name,bm)
        os.mkdir(PART.name,0o700,dir_fd=b); os.fsync(b)
        d=os.open(PART.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=b)
        try: write(d,ENTRY,e); write(d,CORE,c); write(d,MAN,r); os.fchmod(d,0o555); os.fsync(d)
        finally: os.close(d)
        verify_new_boot(BOOT_PART,bm); verify_new_bundle(PART,(e,c,r))
        rename(b,BOOT.name,OLD_BOOT_Q.name); rename(b,ROOT.name,OLD_ROOT_Q.name)
        rename(b,BOOT_PART.name,BOOT.name); rename(b,PART.name,ROOT.name); os.fsync(b)
    finally: os.close(b)
    verify_new_boot(BOOT,bm); verify_new_bundle(ROOT,(e,c,r)); verify_old_boot(OLD_BOOT_Q); verify_old_root(OLD_ROOT_Q)
    print('DASHBOARD_HANDOFF_EXECUTION_BUNDLE_BYTECODE_REMEDIATION=PASS'); print('sourceMainSha='+m['source_main_sha']); print('sourceTreeSha='+m['source_tree_sha']); print('oldBootstrapQuarantine='+str(OLD_BOOT_Q)); print('oldBundleQuarantine='+str(OLD_ROOT_Q)); print('deletions=0'); print('handoffMaterializations=0')
if __name__=='__main__':
    try: main()
    except Exception as e: print(f'P10_DASHBOARD_HANDOFF_EXEC_BUNDLE_REMEDIATOR=STOP reason={type(e).__name__}:{e}',file=sys.stderr); raise SystemExit(1)
