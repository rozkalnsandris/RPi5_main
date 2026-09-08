from __future__ import annotations
import importlib.machinery, importlib.util, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WRAP=ROOT/'scripts/dashboard-rpi5-preverified-handoff-materializer.py'; CORE=ROOT/'scripts/dashboard-rpi5-preverified-handoff-materializer-core.py'; CONTRACT=ROOT/'ops/deploy/dashboard-preverified-handoff-materializer-v1.json'
def load(name,path):
 loader=importlib.machinery.SourceFileLoader(name,str(path)); spec=importlib.util.spec_from_loader(name,loader); assert spec; mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; loader.exec_module(mod); return mod
wrapper=load('dashboard_handoff_wrapper_tested',WRAP); core=load('dashboard_handoff_core_tested',CORE); wrapper._configure_core(core)
NEW='343366427441811a22739b05b04d069c10905805'; OLD='066b9a24008dd57439f9e66eae198416c4dfc590'; TREE='76d69ef0fee15deceb26eb00a479e912312a241f'; PARENT='066b9a24008dd57439f9e66eae198416c4dfc590'; DIGEST='076db053e5dc83016168a1e6cecb291e063587c7a977fc3683c2b4bf9dc861db'; PRODUCER='bea0f30602d119ae53b81e70ce2d4c283d369ce8'
class T(unittest.TestCase):
 def test_exact_new_candidate_binding_accepted(self): core.require_reviewed_candidate_binding(source_sha=NEW,tree_sha=TREE,parent_sha=PARENT,candidate_sha256=DIGEST,file_count=72,total_bytes=6897167,producer_blob_sha=PRODUCER)
 def test_old_candidate_rejected(self):
  with self.assertRaisesRegex(core.HandoffMaterializerError,'exact-provenance'): core.require_reviewed_candidate_binding(source_sha=OLD,tree_sha=TREE,parent_sha=PARENT,candidate_sha256=DIGEST,file_count=72,total_bytes=6897167,producer_blob_sha=PRODUCER)
 def test_contract_and_source_match_and_stay_disabled(self):
  c=json.loads(CONTRACT.read_text()); self.assertFalse(c['execution_enabled']); self.assertEqual(c['reviewed_source_sha'],NEW); self.assertEqual(c['reviewed_source_tree_sha'],TREE); self.assertEqual(c['reviewed_parent_sha'],PARENT); self.assertEqual(c['preverification_binding']['candidate_sha256'],DIGEST); self.assertEqual(c['preverification_binding']['file_count'],72); self.assertEqual(c['preverification_binding']['total_bytes'],6897167); self.assertEqual(core.REVIEWED_SOURCE_SHA,NEW); self.assertEqual(wrapper.REVIEWED_SOURCE_SHA,NEW)
 def test_root_owned_namespace_and_execution_boundary_preserved(self):
  self.assertEqual(core.HANDOFF_OWNER,'root'); self.assertEqual(core.HANDOFF_GROUP,'root'); self.assertEqual(str(wrapper.HANDOFF_BASE),'/var/lib/rozkalns-dashboard-candidate-input'); self.assertFalse(json.loads(CONTRACT.read_text())['source_state']['live_authority'])
 def test_no_generic_command_authority(self):
  for source in (WRAP.read_text(),CORE.read_text()):
   for forbidden in ('subprocess','os.system(','shell=True','Popen(','execv(','curl ','wget '): self.assertNotIn(forbidden,source)
if __name__=='__main__': unittest.main(verbosity=2)
