from __future__ import annotations
import sys, unittest
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops/lib'))
from deploy_executor import weather_private_bigquery_execution_bridge as bridge
from deploy_executor.weather_private_bigquery_contract import *

def baseline(**kw):
    v=dict(application_staged=False,runtime_present=False,auth_binding_present=False,project_binding_present=False,linked_dataset_present=False);v.update(kw);return bridge.PrivateExecutionBaseline(**v)
def envelope(**kw):
    v=dict(authorization_issue_number=700,rpi5_main_source_sha='1'*40,weather_source_sha='2'*40,baseline=baseline());v.update(kw);return bridge.PrivateExecutionEnvelope(**v)
class R:
    def __init__(self,e):self.e=e
    def prepare_private_execution(self,n):return self.e
class C:
    def __init__(self):self.calls=[]
    def consume_once(self,n,*,first_stage):self.calls.append((n,first_stage))
class B:
    def __init__(self,fail=None):self.calls=[];self.fail=fail
    def x(self,s):
        self.calls.append(s)
        if s==self.fail:raise bridge.WeatherNextPrivateExecutionBridgeError('fixture failure')
        return bridge.StageReceipt(stage=s,status='completed',mutation_performed=True)
    def stage_application(self,e):return self.x(bridge.PRIVATE_APPLICATION_STAGING)
    def materialize_runtime(self,e):return self.x(PRIVATE_RUNTIME_MATERIALIZATION)
    def bind_google_auth(self,e):return self.x(GOOGLE_AUTH_BINDING)
    def bind_google_project(self,e):return self.x(GOOGLE_PROJECT_BINDING)
    def create_analytics_hub_link(self,e):return self.x(ANALYTICS_HUB_LINK_CREATE)
    def run_read_only_first_access(self,e):return self.x(READ_ONLY_PRIVATE_BIGQUERY)
class T(unittest.TestCase):
    def test_order(self):
        c=C();b=B();out=bridge.execute_private_execution_for_authorization(700,canonical_revalidator=R(envelope()),authorization_consumer=c,backend=b)
        self.assertEqual(tuple(b.calls),bridge.AUTHORIZED_STAGE_SEQUENCE);self.assertEqual(c.calls,[(700,bridge.PRIVATE_APPLICATION_STAGING)]);self.assertFalse(out['sqlite_write_performed'])
    def test_skip(self):
        e=envelope(baseline=baseline(application_staged=True,runtime_present=True,auth_binding_present=True,project_binding_present=True,linked_dataset_present=True));c=C();b=B();out=bridge.execute_private_execution_for_authorization(700,canonical_revalidator=R(e),authorization_consumer=c,backend=b)
        self.assertEqual(b.calls,[READ_ONLY_PRIVATE_BIGQUERY]);self.assertEqual(c.calls,[(700,READ_ONLY_PRIVATE_BIGQUERY)]);self.assertTrue(all(r.status=='already_present' for r in out['stage_receipts'][:5]))
    def test_invalid(self):
        e=envelope()
        for bad in (replace(e,contract_id=PUBLIC_RUNTIME_OPERATION_ID),replace(e,target_alias='x'),replace(e,rpi5_main_source_sha='bad'),replace(e,weather_source_sha='bad'),replace(e,forecast_hours=7),replace(e,home_scope_enabled=True),replace(e,sqlite_write_enabled=True),replace(e,authorized_stages=tuple(reversed(bridge.AUTHORIZED_STAGE_SEQUENCE))):
            with self.assertRaises(Exception):bridge.validate_private_execution_envelope(bad)
    def test_failure_stops(self):
        b=B(GOOGLE_PROJECT_BINDING);c=C()
        with self.assertRaises(bridge.WeatherNextPrivateExecutionBridgeError):bridge.execute_private_execution_for_authorization(700,canonical_revalidator=R(envelope()),authorization_consumer=c,backend=b)
        self.assertEqual(b.calls,[bridge.PRIVATE_APPLICATION_STAGING,PRIVATE_RUNTIME_MATERIALIZATION,GOOGLE_AUTH_BINDING,GOOGLE_PROJECT_BINDING]);self.assertEqual(len(c.calls),1)
    def test_source_surface(self):
        s=(ROOT/'ops/lib/deploy_executor/weather_private_bigquery_execution_bridge.py').read_text()
        for token in ('subprocess','os.environ','Popen(','shell=True','sudo ','pip install','apt ','GOOGLE_APPLICATION_CREDENTIALS','HOME_LAT','HOME_LON','.env'):self.assertNotIn(token,s)
        r=bridge.source_readiness();self.assertTrue(r['bridge_source_implemented']);self.assertFalse(r['external_entrypoint_enabled']);self.assertFalse(r['source_merge_authorizes_live'])
if __name__=='__main__':unittest.main()
