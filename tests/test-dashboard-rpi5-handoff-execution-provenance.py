from __future__ import annotations
import hashlib,json,re
from pathlib import Path
import unittest

R=Path(__file__).resolve().parents[1]
P=lambda x:R/x
WRAP=P('scripts/dashboard-rpi5-preverified-handoff-materializer.py')
CORE=P('scripts/dashboard-rpi5-preverified-handoff-materializer-core.py')
PREP=P('scripts/dashboard-rpi5-handoff-execution-ingress-preparer.py')
BOOT=P('scripts/dashboard-rpi5-handoff-execution-bootstrap-emitter.py')
EMIT=P('scripts/dashboard-rpi5-handoff-execution-payload-emitter.py')
MAT=P('scripts/dashboard-rpi5-handoff-execution-bundle-materializer.py')
PROOF=P('scripts/dashboard-rpi5-handoff-execution-bundle-proof.py')
CON=P('ops/deploy/dashboard-handoff-execution-bundle-v1.json')
HAND=P('ops/deploy/dashboard-preverified-handoff-materializer-v1.json')
def blob(p):
 b=p.read_bytes();return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()

class T(unittest.TestCase):
 def test_source_binding(self):
  c=json.loads(CON.read_text())['source_binding']
  for k,p in [('entrypoint',WRAP),('core',CORE),('ingress_preparer',PREP),('bootstrap_emitter',BOOT),('payload_emitter',EMIT),('bundle_materializer',MAT),('proof',PROOF)]: self.assertEqual(c[k]['git_blob_sha'],blob(p))
  self.assertFalse(c['caller_selectable_source'])
 def test_no_root_user_path(self):
  c=json.loads(CON.read_text());self.assertFalse(c['unprivileged_execution_ingress']['root_may_open_ingress_paths']);self.assertFalse(c['bootstrap']['root_opens_user_source_path']);self.assertFalse(c['materialization']['root_reads_user_controlled_path'])
  s=MAT.read_text();self.assertIn('sys.stdin.buffer',s);self.assertIn('renameat2',s);self.assertIn('O_NOFOLLOW',s);self.assertIn("Path('/var/lib/rozkalns-dashboard-handoff-exec')",s)
  self.assertIsNone(re.search(r'/home/[A-Za-z0-9._-]+',s))
  for x in ['subprocess','os.system(','shell=True','Popen(','execv(','--source','--path','--command']: self.assertNotIn(x,s)
 def test_root_receiver_binds_reviewed_code(self):
  s=MAT.read_text();self.assertIn("ENTRY_BLOB='9c462cec02d89ab2cd77278c4cf1421b6beda998'",s);self.assertIn("CORE_BLOB='e697b00121e2baa83df77782b1a2a504811d6316'",s);self.assertIn('handoffMaterializations=0',s)
  c=json.loads(CON.read_text())['materialization'];self.assertTrue(c['runtime_manifest_is_not_sufficient_code_authority'])
 def test_fixed_emitters(self):
  c=json.loads(CON.read_text())['unprivileged_execution_ingress'];self.assertEqual(c['owner_home_source'],'passwd-db');self.assertEqual(c['root_relative'],'.cache/rozkalns-dashboard-handoff-exec-ingress/v1')
  p=PREP.read_text();b=BOOT.read_text();e=EMIT.read_text();self.assertIn('materializer bytes differ from committed Git blob',b);self.assertIn('Path(pwd.getpwnam(OWNER).pw_dir)',p);self.assertIn("ING=Path(pwd.getpwnam('andris').pw_dir)/'.cache/rozkalns-dashboard-handoff-exec-ingress/v1'",e)
  for s in (b,e):
   for x in ['--source','--path','--command','--script','--env','sudo']:self.assertNotIn(x,s)
 def test_gate_and_failure(self):
  c=json.loads(CON.read_text());seq=c['gate_sequence'];want=['unprivileged-execution-ingress-preparation','separate-execution-bundle-materialization-live-root-gate','read-only-execution-bundle-proof','fresh-handoff-materialization-live-root-gate'];self.assertEqual([seq.index(x) for x in want],sorted(seq.index(x) for x in want));p=c['failure_policy'];self.assertEqual((p['automatic_retry'],p['automatic_cleanup'],p['automatic_rollback'],p['deletion_budget']),(False,False,False,0))
 def test_wrapper_before_import_and_old_auth_invalid(self):
  s=WRAP.read_text();m=s[s.index('def main('):];self.assertLess(m.index('_verify_execution_bundle()'),m.index('_load_core_from_trusted_bundle()'))
  h=json.loads(HAND.read_text());self.assertTrue(h['privileged_execution']['root_owned_bundle_required']);self.assertFalse(h['privileged_execution']['direct_git_checkout_execution_allowed']);self.assertTrue(h['source_state']['invalidates_pre_issue_349_repaired_handoff_live_authority'])
if __name__=='__main__':unittest.main(verbosity=2)
