#!/usr/bin/env python3
from __future__ import annotations
import base64,hashlib,json,os,pwd,grp,stat,subprocess,sys
from pathlib import Path

REPO=Path(__file__).resolve().parent.parent
ING=Path(pwd.getpwnam('andris').pw_dir)/'.cache/rozkalns-dashboard-handoff-exec-ingress/v1'
ENTRY='dashboard-rpi5-preverified-handoff-materializer.py'; CORE='dashboard-rpi5-preverified-handoff-materializer-core.py'; MAN='execution-manifest.json'
EPATH='scripts/dashboard-rpi5-preverified-handoff-materializer.py'; CPATH='scripts/dashboard-rpi5-preverified-handoff-materializer-core.py'
ACK='RPi5_main#349:EMIT-DASHBOARD-HANDOFF-EXECUTION-BUNDLE-PAYLOAD-V1'
class Stop(RuntimeError): pass

def git(*a):
    p=subprocess.run(['git','-C',str(REPO),*a],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={'PATH':'/usr/bin:/bin','HOME':str(Path.home()),'LANG':'C','LC_ALL':'C'})
    if p.returncode: raise Stop('git proof failed')
    return p.stdout.strip()
def blob(b): return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def read(fd,n,uid,gid,maxn):
    f=os.open(n,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try:
        st=os.fstat(f)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=uid or st.st_gid!=gid or stat.S_IMODE(st.st_mode)!=0o444 or st.st_size>maxn: raise Stop(n+' metadata mismatch')
        b=b''
        while True:
            c=os.read(f,65536)
            if not c: break
            b+=c
            if len(b)>maxn: raise Stop(n+' too large')
        return b
    finally: os.close(f)
def main():
    uid=pwd.getpwnam('andris').pw_uid; gid=grp.getgrnam('andris').gr_gid
    if os.geteuid()==0 or (os.geteuid(),os.getegid())!=(uid,gid): raise Stop('must run as exact andris:andris')
    if sys.argv[1:]!=['--emit','--ack',ACK]: raise Stop('authorization arguments mismatch')
    if git('symbolic-ref','--short','-q','HEAD')!='main' or git('status','--porcelain=v1'): raise Stop('clean main required')
    head,tree=git('rev-parse','HEAD'),git('rev-parse','HEAD^{tree}')
    eb,cb=git('rev-parse','HEAD:'+EPATH),git('rev-parse','HEAD:'+CPATH)
    fd=os.open(ING,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid!=uid or st.st_gid!=gid or stat.S_IMODE(st.st_mode)!=0o555: raise Stop('ingress root metadata mismatch')
        if sorted(os.listdir(fd))!=sorted([ENTRY,CORE,MAN]): raise Stop('ingress tree mismatch')
        e,c,r=read(fd,ENTRY,uid,gid,1048576),read(fd,CORE,uid,gid,1048576),read(fd,MAN,uid,gid,65536)
    finally: os.close(fd)
    try: m=json.loads(r.decode())
    except Exception as x: raise Stop('manifest JSON invalid') from x
    if m.get('source_main_sha')!=head or m.get('source_tree_sha')!=tree or m.get('source_repository')!='rozkalnsandris/RPi5_main': raise Stop('manifest source identity mismatch')
    for k,path,b,data in [('entrypoint',EPATH,eb,e),('core',CPATH,cb,c)]:
        x=m.get(k)
        if type(x) is not dict or x.get('repo_path')!=path or x.get('git_blob_sha')!=b or blob(data)!=b or x.get('sha256')!=hashlib.sha256(data).hexdigest(): raise Stop(k+' binding mismatch')
    p={'schema':'dashboard-rpi5.handoff-execution-payload.v1','entrypoint_b64':base64.b64encode(e).decode(),'core_b64':base64.b64encode(c).decode(),'manifest_b64':base64.b64encode(r).decode()}
    sys.stdout.write(json.dumps(p,sort_keys=True,separators=(',',':'))+'\n')
if __name__=='__main__':
    try: main()
    except Exception as e: print(f'P10_DASHBOARD_HANDOFF_EXEC_PAYLOAD_EMITTER=STOP reason={type(e).__name__}:{e}',file=sys.stderr); raise SystemExit(1)
