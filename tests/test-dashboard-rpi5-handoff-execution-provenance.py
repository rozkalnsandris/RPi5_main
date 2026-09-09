from __future__ import annotations
import ast,hashlib,json,re,sys,tempfile
from pathlib import Path
import unittest

R=Path(__file__).resolve().parents[1]
P=lambda x:R/x
WRAP=P('scripts/dashboard-rpi5-preverified-handoff-materializer.py'); CORE=P('scripts/dashboard-rpi5-preverified-handoff-materializer-core.py'); PREP=P('scripts/dashboard-rpi5-handoff-execution-ingress-preparer.py'); BOOT=P('scripts/dashboard-rpi5-handoff-execution-bootstrap-emitter.py'); EMIT=P('scripts/dashboard-rpi5-handoff-execution-payload-emitter.py'); MAT=P('scripts/dashboard-rpi5-handoff-execution-bundle-materializer.py'); PROOF=P('scripts/dashboard-rpi5-handoff-execution-bundle-proof.py')
RBOOT=P('scripts/dashboard-rpi5-handoff-execution-remediation-bootstrap-emitter.py'); REMIT=P('scripts/dashboard-rpi5-handoff-execution-remediation-payload-emitter.py'); REM=P('scripts/dashboard-rpi5-handoff-execution-bundle-remediator.py'); RPROOF=P('scripts/dashboard-rpi5-handoff-execution-bytecode-remediation-proof.py')
CON=P('ops/deploy/dashboard-handoff-execution-bundle-v1.json'); HAND=P('ops/deploy/dashboard-preverified-handoff-materializer-v1.json')
def blob(p):
 b=p.read_bytes();return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
class T(unittest.TestCase):
 def test_source_binding(self):
  c=json.loads(CON.read_text())['source_binding']
  for k,p in [('entrypoint',WRAP),('core',CORE),('ingress_preparer',PREP),('bootstrap_emitter',BOOT),('payload_emitter',EMIT),('bundle_materializer',MAT),('proof',PROOF),('remediation_bootstrap_emitter',RBOOT),('remediation_payload_emitter',REMIT),('bundle_remediator',REM),('remediation_proof',RPROOF)]: self.assertEqual(c[k]['git_blob_sha'],blob(p))
  self.assertFalse(c['caller_selectable_source'])
 def test_no_root_user_path(self):
  c=json.loads(CON.read_text());self.assertFalse(c['unprivileged_execution_ingress']['root_may_open_ingress_paths']);self.assertFalse(c['bootstrap']['root_opens_user_source_path']);self.assertFalse(c['materialization']['root_reads_user_controlled_path'])
  for s in (MAT.read_text(),REM.read_text()):
   self.assertIn('sys.stdin.buffer',s);self.assertIn('renameat2',s);self.assertIn("Path('/var/lib/rozkalns-dashboard-handoff-exec')",s);self.assertIsNone(re.search(r'/home/[A-Za-z0-9._-]+',s))
   for x in ['subprocess','os.system(','shell=True','Popen(','execv(','--source','--path','--command','--script','--env','unlink(','rmtree(','remove(']: self.assertNotIn(x,s)
 def test_root_receiver_binds_reviewed_code(self):
  s=MAT.read_text();self.assertIn(f"ENTRY_BLOB='{blob(WRAP)}'",s);self.assertIn(f"CORE_BLOB='{blob(CORE)}'",s);self.assertIn('handoffMaterializations=0',s);c=json.loads(CON.read_text())['materialization'];self.assertTrue(c['runtime_manifest_is_not_sufficient_code_authority'])
 def test_fixed_emitters(self):
  c=json.loads(CON.read_text())['unprivileged_execution_ingress'];self.assertEqual(c['owner_home_source'],'passwd-db');self.assertEqual(c['root_relative'],'.cache/rozkalns-dashboard-handoff-exec-ingress/v1')
  p=PREP.read_text();b=BOOT.read_text();e=EMIT.read_text();rb=RBOOT.read_text();re_=REMIT.read_text();self.assertIn('materializer bytes differ from committed Git blob',b);self.assertIn('remediator bytes differ from committed Git blob',rb);self.assertIn('bundle materializer bytes differ from committed Git blob',re_);self.assertIn('Path(pwd.getpwnam(OWNER).pw_dir)',p)
  for s in (b,e,rb,re_):
   for x in ['--source','--path','--command','--script','--env','sudo']:self.assertNotIn(x,s)
 def test_remediation_payload_emitter_writes_json_whitespace_newline(self):
  tree=ast.parse(REMIT.read_text());writes=[]
  for node in ast.walk(tree):
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='write' and isinstance(node.func.value,ast.Attribute) and node.func.value.attr=='stdout': writes.append(node)
  self.assertEqual(len(writes),1);arg=writes[0].args[0];self.assertIsInstance(arg,ast.BinOp);self.assertIsInstance(arg.right,ast.Constant);self.assertEqual(arg.right.value,'\n')
 def test_gate_and_failure(self):
  c=json.loads(CON.read_text());seq=c['gate_sequence'];want=['unprivileged-execution-ingress-preparation','separate-execution-bundle-materialization-live-root-gate','read-only-execution-bundle-proof','fresh-handoff-materialization-live-root-gate'];self.assertEqual([seq.index(x) for x in want],sorted(seq.index(x) for x in want));p=c['failure_policy'];self.assertEqual((p['automatic_retry'],p['automatic_cleanup'],p['automatic_rollback'],p['deletion_budget']),(False,False,False,0))
 def test_wrapper_before_import_and_old_auth_invalid(self):
  s=WRAP.read_text();m=s[s.index('def main('):];self.assertLess(m.index('_verify_execution_bundle()'),m.index('_load_core_from_trusted_bundle()'));h=json.loads(HAND.read_text());self.assertTrue(h['privileged_execution']['root_owned_bundle_required']);self.assertFalse(h['privileged_execution']['direct_git_checkout_execution_allowed']);self.assertTrue(h['source_state']['invalidates_pre_issue_349_repaired_handoff_live_authority'])
 def test_trusted_core_import_does_not_write_bytecode(self):
  s=WRAP.read_text();self.assertLess(s.index('sys.dont_write_bytecode = True'),s.index('loader.exec_module(core)'));c=json.loads(CON.read_text())['runtime_execution'];self.assertFalse(c['bytecode_cache_writes_allowed']);self.assertFalse(c['bundle_tree_mutation_by_core_import_allowed'])
  old_flag=sys.dont_write_bytecode;module_name='dashboard_handoff_materializer_core'
  try:
   with tempfile.TemporaryDirectory() as d:
    root=Path(d);wrapper=root/WRAP.name;core=root/CORE.name;wrapper.write_bytes(WRAP.read_bytes());core.write_bytes(CORE.read_bytes());ns={'__file__':str(wrapper),'__name__':'test_dashboard_handoff_wrapper'};exec(compile(wrapper.read_text(),str(wrapper),'exec'),ns);sys.dont_write_bytecode=False;ns['TRUSTED_CORE']=core;ns['_load_core_from_trusted_bundle']();self.assertFalse((root/'__pycache__').exists())
  finally:
   sys.dont_write_bytecode=old_flag;sys.modules.pop(module_name,None)
 def test_bytecode_incident_remediator_is_exact_and_no_delete(self):
  c=json.loads(CON.read_text())['bytecode_incident_remediation'];s=REM.read_text();pre=c['exact_prestate'];q=c['fixed_quarantine'];budget=c['mutation_budget']
  self.assertFalse(c['ordinary_live_all_eligible']);self.assertTrue(c['separate_live_root_gate_required']);self.assertEqual(budget['deletions'],0);self.assertEqual(budget['automatic_retry'],0);self.assertEqual(budget['automatic_cleanup'],0);self.assertEqual(budget['automatic_rollback'],0)
  for value in [pre['bootstrap_git_blob_sha'],pre['bootstrap_sha256'],pre['source_main_sha'],pre['source_tree_sha'],pre['entrypoint_git_blob_sha'],pre['core_git_blob_sha'],pre['manifest_sha256'],pre['bytecode_sha256'],Path(q['bootstrap']).name,Path(q['bundle']).name,blob(MAT),blob(WRAP),blob(CORE)]: self.assertIn(value,s)
  self.assertIn("os.listdir(q)!=[PYC]",s);self.assertIn('verify_old_boot(BOOT); verify_old_root(ROOT)',s);self.assertIn('verify_new_boot(BOOT_PART,bm); verify_new_bundle(PART,(e,c,r))',s);self.assertLess(s.index('verify_old_boot(BOOT); verify_old_root(ROOT)'),s.index('write(b,BOOT_PART.name,bm)'))
 def test_remediation_proof_is_read_only_and_binds_current_source(self):
  s=RPROOF.read_text();self.assertIn("if os.geteuid()==0",s);self.assertIn("git('rev-parse','HEAD:'+MAT_PATH)",s);self.assertIn("git('rev-parse','HEAD:'+REM_PATH)",s);self.assertIn('DASHBOARD_HANDOFF_EXECUTION_BUNDLE_BYTECODE_REMEDIATION_PROOF=PASS',s)
  for x in ['O_WRONLY','O_CREAT','renameat2','unlink(','rmtree(','remove(']: self.assertNotIn(x,s)
if __name__=='__main__':unittest.main(verbosity=2)
