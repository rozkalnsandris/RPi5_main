#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,stat,subprocess,sys
from pathlib import Path

R=Path(__file__).resolve().parent.parent
BASE=Path('/var/lib/rozkalns-dashboard-handoff-exec'); BOOT=BASE/'.bundle-materializer-v1.py'; SELF=BASE/'.bundle-remediator-v1.py'
OLD_BOOT_Q=BASE/'.bundle-materializer-v1.py.stale-78dcf901-112f272e'; OLD_ROOT_Q=BASE/'.v1.stale-112f272e-92036c09-bytecode-5b1e05af'
PART=BASE/'.v1.execution-bundle-remediation-partial'; BOOT_PART=BASE/'.bundle-materializer-v1.py.remediation-partial'
ENTRY='dashboard-rpi5-preverified-handoff-materializer.py'; CORE='dashboard-rpi5-preverified-handoff-materializer-core.py'; MAN='execution-manifest.json'; CACHE='__pycache__'; PYC='dashboard-rpi5-preverified-handoff-materializer-core.cpython-311.pyc'
MAT_PATH='scripts/dashboard-rpi5-handoff-execution-bundle-materializer.py'; REM_PATH='scripts/dashboard-rpi5-handoff-execution-bundle-remediator.py'; PROOF_PATH=R/'scripts/dashboard-rpi5-handoff-execution-bundle-proof.py'
OLD_BOOT_BLOB='78dcf901b6c48db11024909946e47cd62b558c10'; OLD_BOOT_SHA256='94610eaf208c81b165a48636458150811f12e3579bc8b28994e575d08069dd4d'; OLD_ENTRY_BLOB='da6b3756ec49436de3855a8c13f273954a919d22'; OLD_ENTRY_SHA256='3e3a6da124980e3aa464ba92fe5020deee61cd81cedcfa2a057d890a5de933b0'; OLD_CORE_BLOB='409ea15dcb72e7361278dfd4065228c99fa840d2'; OLD_CORE_SHA256='26c5474358fab1005b1092d6c83c2319c82f7d3b51ee9e30f493eb13a577c53f'; OLD_MAN_SHA256='0850a5e3efdea8a5ec5eec30e8b17bc9041eef0eb49565e0143832f26e7f0e1c'; OLD_PYC_SHA256='5b1e05afbd99bf03ce1bc277b4242dd79f8fc26e61bc8f5e7d36cebbe185bc95'
class Stop(RuntimeError): pass

def git(*a):
 p=subprocess.run(['git','-C',str(R),*a],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={'PATH':'/usr/bin:/bin','HOME':str(Path.home()),'LANG':'C','LC_ALL':'C'});
 if p.returncode: raise Stop('git proof failed')
 return p.stdout.strip()
def blob(b): return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def readall(fd,maxn,label):
 out=b''
 while True:
  c=os.read(fd,min(65536,maxn+1-len(out)))
  if not c: return out
  out+=c
  if len(out)>maxn: raise Stop(label+' too large')
def read_file(p,m,label):
 f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  st=os.fstat(f)
  if not stat.S_ISREG(st.st_mode) or st.st_uid or st.st_gid or stat.S_IMODE(st.st_mode)!=m: raise Stop(label+' metadata mismatch')
  out=b''
  while True:
   c=os.read(f,65536)
   if not c: return out
   out+=c
 finally: os.close(f)
def verify_old_root():
 fd=os.open(OLD_ROOT_Q,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  st=os.fstat(fd)
  if not stat.S_ISDIR(st.st_mode) or st.st_uid or st.st_gid or stat.S_IMODE(st.st_mode)!=0o555: raise Stop('old bundle quarantine metadata mismatch')
  if sorted(os.listdir(fd))!=sorted([ENTRY,CORE,MAN,CACHE]): raise Stop('old bundle quarantine tree mismatch')
  def rd(n,m):
   f=os.open(n,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
   try:
    s=os.fstat(f)
    if not stat.S_ISREG(s.st_mode) or s.st_uid or s.st_gid or stat.S_IMODE(s.st_mode)!=m: raise Stop(n+' metadata mismatch')
    return readall(f,1048576,n)
   finally: os.close(f)
  e,c,r=rd(ENTRY,0o444),rd(CORE,0o444),rd(MAN,0o444)
  q=os.open(CACHE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
  try:
   s=os.fstat(q)
   if not stat.S_ISDIR(s.st_mode) or s.st_uid or s.st_gid or stat.S_IMODE(s.st_mode)!=0o755 or os.listdir(q)!=[PYC]: raise Stop('old bytecode quarantine mismatch')
   f=os.open(PYC,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=q)
   try:
    s=os.fstat(f)
    if not stat.S_ISREG(s.st_mode) or s.st_uid or s.st_gid or stat.S_IMODE(s.st_mode)!=0o644: raise Stop('old bytecode file metadata mismatch')
    pyc=readall(f,1048576,'old bytecode file')
   finally: os.close(f)
  finally: os.close(q)
 finally: os.close(fd)
 if blob(e)!=OLD_ENTRY_BLOB or hashlib.sha256(e).hexdigest()!=OLD_ENTRY_SHA256 or blob(c)!=OLD_CORE_BLOB or hashlib.sha256(c).hexdigest()!=OLD_CORE_SHA256 or hashlib.sha256(r).hexdigest()!=OLD_MAN_SHA256 or hashlib.sha256(pyc).hexdigest()!=OLD_PYC_SHA256: raise Stop('old bundle quarantine identity mismatch')
def main():
 if os.geteuid()==0: raise Stop('remediation proof must run unprivileged')
 if git('symbolic-ref','--short','-q','HEAD')!='main' or git('status','--porcelain=v1'): raise Stop('clean main required')
 p=subprocess.run([sys.executable,str(PROOF_PATH)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={'PATH':'/usr/bin:/bin','HOME':str(Path.home()),'LANG':'C','LC_ALL':'C'})
 if p.returncode or 'DASHBOARD_HANDOFF_EXECUTION_BUNDLE_PROOF=PASS' not in p.stdout: raise Stop('current execution bundle proof failed')
 mat_blob=git('rev-parse','HEAD:'+MAT_PATH); rem_blob=git('rev-parse','HEAD:'+REM_PATH)
 b=read_file(BOOT,0o444,'current bootstrap'); s=read_file(SELF,0o444,'remediator'); old=read_file(OLD_BOOT_Q,0o444,'old bootstrap quarantine')
 if blob(b)!=mat_blob or blob(s)!=rem_blob: raise Stop('current bootstrap/remediator source binding mismatch')
 if blob(old)!=OLD_BOOT_BLOB or hashlib.sha256(old).hexdigest()!=OLD_BOOT_SHA256: raise Stop('old bootstrap quarantine identity mismatch')
 verify_old_root()
 for x in [PART,BOOT_PART]:
  if x.exists() or x.is_symlink(): raise Stop('remediation partial remains')
 print('DASHBOARD_HANDOFF_EXECUTION_BUNDLE_BYTECODE_REMEDIATION_PROOF=PASS'); print('sourceMainSha='+git('rev-parse','HEAD')); print('sourceTreeSha='+git('rev-parse','HEAD^{tree}')); print('bundleMaterializerGitBlobSha='+mat_blob); print('remediatorGitBlobSha='+rem_blob); print('oldBootstrapQuarantine='+str(OLD_BOOT_Q)); print('oldBundleQuarantine='+str(OLD_ROOT_Q)); print('rootMutation=0')
 return 0
if __name__=='__main__':
 try: raise SystemExit(main())
 except Exception as e: print(f'P10_DASHBOARD_HANDOFF_EXEC_BUNDLE_REMEDIATION_PROOF=STOP reason={type(e).__name__}:{e}',file=sys.stderr); raise SystemExit(1)
