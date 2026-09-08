#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'scripts/auto-run-lane-eligibility.py'
spec=importlib.util.spec_from_file_location('auto_run_lane_eligibility',P); assert spec and spec.loader
m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)
SHA='1'*40

def lane(repo,issue,cls='SOURCE_INDEPENDENT',state='WORKING',keys=None,deps=None,live=False,receipt=None,head=SHA,ready=False,blocked=False):
 return {'repository':repo,'issue_number':issue,'lane_class':cls,'state':state,'conflict_keys':keys or [f'project:{issue}'],'explicit_dependencies':deps or [],'activation_receipt_issue':issue if receipt is None else receipt,'runtime_live_authority':live,'head_sha':head,'merge_ready':ready,'program_order_blocked':blocked}
class T(unittest.TestCase):
 def test_weather_plus_dashboard(self): self.assertEqual(m.classify(lane('x/rpi',2),[lane('x/rpi',1,keys=['project:weather'])])['decision'],'ELIGIBLE')
 def test_weather_plus_control(self): self.assertEqual(m.classify(lane('x/rpi',3),[lane('x/rpi',1,keys=['project:weather'])])['decision'],'ELIGIBLE')
 def test_waiting_ci_does_not_consume_slot(self): self.assertEqual(m.classify(lane('x/rpi',5),[lane('x/rpi',i,state='WAITING_CI',keys=[f'k:{i}']) for i in range(10,15)])['decision'],'ELIGIBLE')
 def test_waiting_review_does_not_consume_slot(self): self.assertEqual(m.classify(lane('x/rpi',5),[lane('x/rpi',10,state='WAITING_REVIEW',keys=['other'])])['decision'],'ELIGIBLE')
 def test_shared_control_surface_serializes(self): self.assertEqual(m.classify(lane('x/rpi',2,'SOURCE_EXCLUSIVE',keys=['canonical:auto-run']),[lane('x/rpi',1,'SOURCE_EXCLUSIVE',keys=['canonical:auto-run'])])['decision'],'QUEUED_CONFLICT')
 def test_live_is_globally_exclusive(self): self.assertEqual(m.classify(lane('x/rpi',2,'LIVE_EXCLUSIVE',keys=['runtime:b'],live=True),[lane('x/rpi',1,'LIVE_EXCLUSIVE',keys=['runtime:a'],live=True)])['decision'],'QUEUED_LIVE_EXCLUSIVE')
 def test_source_cannot_inherit_live_authority(self):
  with self.assertRaises(m.LanePolicyError): m.classify(lane('x/rpi',2,live=True),[])
 def test_receipt_cannot_authorize_another_issue(self):
  with self.assertRaises(m.LanePolicyError): m.classify(lane('x/rpi',2,receipt=1),[])
 def test_changed_head_is_lane_local(self): self.assertEqual(m.classify(lane('x/rpi',2,head='3'*40,ready=True),[lane('x/rpi',1,head='2'*40,ready=False,keys=['other'])])['decision'],'ELIGIBLE')
 def test_restart_reconstructs_all_lanes(self): self.assertEqual([x['issue_number'] for x in m.reconstruct_active_lanes([lane('x/rpi',2),lane('x/rpi',1)])],[1,2])
 def test_legacy_singleton_migrates_or_fails_closed(self):
  self.assertEqual(m.migrate_legacy_controller({'schema':'rozkalns.auto-run-control.v1','active_issue':1},lane('x/rpi',1))[0]['issue_number'],1)
  with self.assertRaises(m.LanePolicyError): m.migrate_legacy_controller({'schema':'rozkalns.auto-run-control.v1','active_issue':1},lane('x/rpi',2))
 def test_real_program_order_stays_blocked(self): self.assertEqual(m.classify(lane('x/rpi',2,blocked=True),[])['decision'],'QUEUED_PROGRAM_ORDER')
 def test_capacity_queues_not_cancels(self): self.assertEqual(m.classify(lane('x/rpi',9),[lane('x/rpi',i,keys=[f'k:{i}']) for i in range(1,5)])['decision'],'QUEUED_CAPACITY')
 def test_unknown_class_fails_closed(self):
  with self.assertRaises(m.LanePolicyError): m.classify(lane('x/rpi',2,'UNKNOWN'),[])
if __name__=='__main__': unittest.main(verbosity=2)
