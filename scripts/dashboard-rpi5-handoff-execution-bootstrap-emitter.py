#!/usr/bin/env python3
from __future__ import annotations
import hashlib,os,stat,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
PATH='scripts/dashboard-rpi5-handoff-execution-bundle-materializer.py'
FILE=ROOT/PATH
ACK='RPi5_main#349:EMIT-DASHBOARD-HANDOFF-EXECUTION-BUNDLE-MATERIALIZER-V1'
class Stop(RuntimeError): pass

def git(*a):
    p=subprocess.run(['git','-C',str(ROOT),*a],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={'PATH':'/usr/bin:/bin','HOME':str(Path.home()),'LANG':'C','LC_ALL':'C'})
    if p.returncode: raise Stop('git proof failed')
    return p.stdout.strip()
def blob(b): return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def main():
    if os.geteuid()==0 or os.geteuid()!=os.getuid(): raise Stop('must run unprivileged')
    if sys.argv[1:]!=['--emit','--ack',ACK]: raise Stop('authorization arguments mismatch')
    if git('symbolic-ref','--short','-q','HEAD')!='main' or git('status','--porcelain=v1'): raise Stop('clean main required')
    expected=git('rev-parse','HEAD:'+PATH)
    fd=os.open(FILE,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid(): raise Stop('materializer source metadata mismatch')
        data=b''
        while True:
            c=os.read(fd,65536)
            if not c: break
            data+=c
            if len(data)>65536: raise Stop('materializer source too large')
    finally: os.close(fd)
    if blob(data)!=expected: raise Stop('materializer bytes differ from committed Git blob')
    sys.stdout.buffer.write(data); sys.stdout.buffer.flush()
if __name__=='__main__':
    try: main()
    except Exception as e: print(f'P10_DASHBOARD_HANDOFF_EXEC_BOOTSTRAP_EMITTER=STOP reason={type(e).__name__}:{e}',file=sys.stderr); raise SystemExit(1)
