#!/usr/bin/env python3
from __future__ import annotations
import base64,ctypes,errno,hashlib,json,os,stat,sys
from pathlib import Path

BASE=Path('/var/lib/rozkalns-dashboard-handoff-exec'); ROOT=BASE/'v1'; PART=BASE/'.v1.execution-bundle-partial'; SELF=BASE/'.bundle-materializer-v1.py'
ENTRY='dashboard-rpi5-preverified-handoff-materializer.py'; CORE='dashboard-rpi5-preverified-handoff-materializer-core.py'; MAN='execution-manifest.json'
ENTRY_BLOB='9c462cec02d89ab2cd77278c4cf1421b6beda998'; CORE_BLOB='e697b00121e2baa83df77782b1a2a504811d6316'
ACK='RPi5_main#349:MATERIALIZE-DASHBOARD-HANDOFF-EXECUTION-BUNDLE-V1'; MAX=2*1024*1024

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
def manifest(raw):
    m=strict(raw); req={'schema','capability','source_repository','source_main_sha','source_tree_sha','entrypoint','core'}
    if set(m)!=req or m['schema']!='dashboard-rpi5.handoff-execution-bundle.v1' or m['capability']!='dashboard-rpi5.preverified-handoff-materializer.v1' or m['source_repository']!='rozkalnsandris/RPi5_main': raise Stop('manifest identity mismatch')
    for k,path,h in [('entrypoint','scripts/dashboard-rpi5-preverified-handoff-materializer.py',ENTRY_BLOB),('core','scripts/dashboard-rpi5-preverified-handoff-materializer-core.py',CORE_BLOB)]:
        x=m[k]
        if type(x) is not dict or set(x)!={'repo_path','git_blob_sha','sha256'} or x['repo_path']!=path or x['git_blob_sha']!=h: raise Stop(k+' binding mismatch')
    return m
def readstdin():
    b=sys.stdin.buffer.read(MAX+1)
    if len(b)>MAX: raise Stop('payload too large')
    return b
def parse(raw):
    p=strict(raw)
    if set(p)!={'schema','entrypoint_b64','core_b64','manifest_b64'} or p['schema']!='dashboard-rpi5.handoff-execution-payload.v1': raise Stop('payload shape mismatch')
    e,c,r=b64(p['entrypoint_b64'],'entrypoint'),b64(p['core_b64'],'core'),b64(p['manifest_b64'],'manifest'); m=manifest(r)
    if blob(e)!=ENTRY_BLOB or blob(c)!=CORE_BLOB: raise Stop('payload Git blob mismatch')
    if hashlib.sha256(e).hexdigest()!=m['entrypoint']['sha256'] or hashlib.sha256(c).hexdigest()!=m['core']['sha256']: raise Stop('payload SHA-256 mismatch')
    return e,c,r,m
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
def read(fd,n):
    f=os.open(n,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try: meta(os.fstat(f),0o444,False,n); return os.read(f,1024*1024+1)
    finally: os.close(f)
def verify(p,expected):
    fd=open_dir(p,0o555,'bundle')
    try:
        if sorted(os.listdir(fd))!=sorted([ENTRY,CORE,MAN]): raise Stop('bundle tree mismatch')
        got=(read(fd,ENTRY),read(fd,CORE),read(fd,MAN))
    finally: os.close(fd)
    if got!=expected: raise Stop('bundle bytes mismatch')
    manifest(got[2]); return got
def rename(fd,a,b):
    f=ctypes.CDLL(None,use_errno=True).renameat2; f.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]; f.restype=ctypes.c_int
    if f(fd,os.fsencode(a),fd,os.fsencode(b),1):
        e=ctypes.get_errno()
        if e==errno.EEXIST: raise Stop('target appeared before publish')
        raise OSError(e,os.strerror(e))

def main():
    if os.geteuid()!=0 or Path(os.path.abspath(__file__))!=SELF: raise Stop('fixed root-owned bootstrap required')
    if sys.argv[1:]!=['--apply','--ack',ACK]: raise Stop('authorization arguments mismatch')
    f=os.open(SELF,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try: meta(os.fstat(f),0o444,False,'bootstrap')
    finally: os.close(f)
    e,c,r,m=parse(readstdin())
    p=open_dir(BASE.parent,0o755,'parent'); os.close(p)
    b=open_dir(BASE,0o755,'base')
    try:
        absent(b,ROOT.name); absent(b,PART.name); os.mkdir(PART.name,0o700,dir_fd=b); os.fsync(b)
        d=os.open(PART.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=b)
        try: write(d,ENTRY,e); write(d,CORE,c); write(d,MAN,r); os.fchmod(d,0o555); os.fsync(d)
        finally: os.close(d)
        verify(PART,(e,c,r)); rename(b,PART.name,ROOT.name); os.fsync(b)
    finally: os.close(b)
    verify(ROOT,(e,c,r))
    print('DASHBOARD_HANDOFF_EXECUTION_BUNDLE_MATERIALIZATION=PASS'); print('sourceMainSha='+m['source_main_sha']); print('sourceTreeSha='+m['source_tree_sha']); print('handoffMaterializations=0')

if __name__=='__main__':
    try: main()
    except Exception as e: print(f'P10_DASHBOARD_HANDOFF_EXEC_BUNDLE_MATERIALIZER=STOP reason={type(e).__name__}:{e}',file=sys.stderr); raise SystemExit(1)
