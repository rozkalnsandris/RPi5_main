from __future__ import annotations
import importlib.util,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; P=ROOT/'ops/lib/deploy_executor/control_phase5_production_visibility.py'; F=ROOT/'tests/fixtures/control_phase5_production_visibility_cases.json'
spec=importlib.util.spec_from_file_location('control_phase5_visibility',P); assert spec and spec.loader; m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)
CASES=json.loads(F.read_text()); PROV={'consumer_repository':m.CONTROL_CONSUMER_REPOSITORY,'consumer_main_sha':m.CONTROL_CONSUMER_MAIN_SHA,'consumer_path':m.CONTROL_CONSUMER_PATH,'consumer_blob_sha':m.CONTROL_CONSUMER_BLOB_SHA,'contract_mode':'SOURCE_ONLY_NO_OBSERVATION_AUTHORITY'}
def norm(name,**kw): return m.normalize_production_visibility(CASES[name],expected_project_id='rpi5-main',expected_repository='rozkalnsandris/RPi5_main',expected_main_sha='504239fb8f98b6785c4aeb6d55681a6c4fdf1399',now_iso='2026-09-08T18:04:00.000Z',provenance=kw.get('provenance',PROV))
class T(unittest.TestCase):
 def test_valid_exact_sanitized_evidence(self): self.assertEqual(norm('valid'),CASES['valid'])
 def test_extra_rejected(self):
  with self.assertRaises(m.ProductionVisibilityContractError) as c: norm('extra_field')
  self.assertEqual(c.exception.code,'UNEXPECTED_FIELD')
 def test_stale_rejected(self):
  with self.assertRaises(m.ProductionVisibilityContractError) as c: norm('stale')
  self.assertEqual(c.exception.code,'STALE_EVIDENCE')
 def test_wrong_project_rejected(self):
  with self.assertRaises(m.ProductionVisibilityContractError) as c: norm('wrong_project')
  self.assertEqual(c.exception.code,'IDENTITY_MISMATCH')
 def test_wrong_sha_rejected(self):
  with self.assertRaises(m.ProductionVisibilityContractError) as c: norm('wrong_sha')
  self.assertEqual(c.exception.code,'MAIN_SHA_MISMATCH')
 def test_malformed_rejected(self):
  with self.assertRaises(m.ProductionVisibilityContractError) as c: norm('malformed')
  self.assertEqual(c.exception.code,'INVALID_INPUT')
 def test_wrong_consumer_provenance_rejected(self):
  bad=dict(PROV); bad['consumer_blob_sha']='0'*40
  with self.assertRaises(m.ProductionVisibilityContractError) as c: norm('valid',provenance=bad)
  self.assertEqual(c.exception.code,'PROVENANCE_MISMATCH')
 def test_source_contract_exposes_no_transport_or_mutation_bridge(self):
  s=P.read_text();
  for forbidden in ('subprocess','os.system(','requests','urllib','socket','paramiko','sudo','docker','cloudflare'): self.assertNotIn(forbidden,s.lower())
if __name__=='__main__': unittest.main(verbosity=2)
