#!/usr/bin/env python3
"""Offline structural and actual Jinja predicate tests, never execute HA actions."""
import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import yaml
from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ops/homeassistant/balkons-watering-bounded-reference.yaml'
START = 'balkons_watering_bounded_reference'
STOP = 'balkons_watering_stop_reference'
ARM = 'input_boolean.balkons_watering_arm_reference'
PENDING = 'input_boolean.balkons_watering_pending_reference'
MARKER = 'input_datetime.balkons_last_watering_attempt'
PUMP = 'switch.balkona_laistisana_suknis'
MAIL = 'sensor.balkons_ha45_reply_reference'
WEATHER = 'weather.forecast_home'
TOPIC = 'balkons/sukna/komanda'
TZ = ZoneInfo('Europe/Berlin')
SENSORS = [1, 3, 4, 5, 6, 7, 8, 9, 10, 12]
RID = '0123456789abcdef'
TICKET = '0123456789abcdef00000001'
OFFER = f'offer:{RID}:{TICKET}'
GUARD = {'condition': 'template', 'value_template': '{{ false }}'}


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def guarded(step):
    return {k: v for k, v in step.items() if k != 'alias'} == GUARD


class Reference(unittest.TestCase):
    def setUp(self):
        self.package = yaml.safe_load(SOURCE.read_text(encoding='utf-8'))
        self.seq = self.package['script'][START]['sequence']
        self.stop = self.package['script'][STOP]['sequence']
        self.clock = datetime(2026, 11, 24, 11, tzinfo=TZ)
        self.states = {ARM: 'on', PENDING: 'on', PUMP: 'off', MARKER: '2026-11-24',
                       MAIL: OFFER, WEATHER: 'sunny'}
        self.states.update({f'sensor.balkona_laistisana_puke_{i}': 'sauss'
                            for i in SENSORS})
        self.attrs = {MARKER: {'has_date': True, 'has_time': False},
                      WEATHER: {'temperature': 8, 'temperature_unit': '°C'}}
        self.env = NativeEnvironment(undefined=StrictUndefined)
        self.env.filters['regex_match'] = lambda value, pattern: re.match(pattern, value) is not None
        self.env.globals.update(
            now=lambda: self.clock, as_timestamp=lambda dt: dt.timestamp(),
            states=lambda key: self.states.get(key, 'unknown'),
            state_attr=lambda key, attr: self.attrs.get(key, {}).get(attr),
            is_state=lambda key, value: self.states.get(key, 'unknown') == value)
        self.v = dict(marker=MARKER, pump=PUMP, arm=ARM, pending=PENDING, mailbox=MAIL,
                      day='2026-11-24', old_date='2026-11-23', sensor_ids=SENSORS,
                      request_id=RID, offer=OFFER, ticket=TICKET,
                      request_at=self.clock.timestamp(), dispatch_at=self.clock.timestamp(),
                      wait=SimpleNamespace(completed=True), on_seen=True, off_seen=True)
        snap = next(s['variables']['snapshot'] for s in self.seq
                    if 'snapshot' in s.get('variables', {}))
        self.v['snapshot'] = self.render(snap)

    def render(self, template, **changes):
        return self.env.from_string(template).render(**(self.v | changes))

    def test_inert_and_single_entry(self):
        self.assertEqual(set(self.package), {'input_boolean', 'mqtt', 'script', 'automation'})
        self.assertEqual(set(self.package['script']), {START, STOP})
        self.assertEqual(self.package['script'][START]['mode'], 'single')
        self.assertTrue(guarded(self.seq[0]))
        self.assertTrue(guarded(self.stop[0]))
        self.assertEqual(sum(guarded(s) for s in self.seq), 3)
        for s in self.seq:
            if guarded(s):
                self.assertIs(self.render(s['value_template']), False)
        helpers = self.package['input_boolean']
        self.assertIs(helpers[ARM.split('.')[1]]['initial'], False)
        self.assertIs(helpers[PENDING.split('.')[1]]['initial'], True)
        self.assertEqual(len(self.package['automation']), 1)
        schedule = self.package['automation'][0]
        self.assertIs(schedule['initial_state'], False)
        self.assertEqual(schedule['conditions'], [GUARD])
        self.assertEqual(schedule['triggers'], [{'trigger': 'time', 'at': '11:00:00'}])
        self.assertEqual(schedule['actions'], [{'action': 'script.' + START}])
        self.assertEqual(self.package['mqtt']['sensor'][0]['state_topic'], 'balkons/ha45/reply')

    def test_exact_action_order_and_no_retry(self):
        all_actions = [x for x in nodes(self.package) if 'action' in x]
        pubs = [x['data'] for x in all_actions if x['action'] == 'mqtt.publish']
        self.assertEqual(len(pubs), 4)
        self.assertEqual([p['payload'] for p in pubs],
                         ["{{ 'ticket45:' ~ request_id }}", "{{ 'start45:' ~ ticket }}", 'OFF', 'OFF'])
        for p in pubs:
            self.assertEqual(set(p), {'topic', 'payload', 'qos', 'retain'})
            self.assertEqual(p['topic'], TOPIC)
            self.assertEqual(p['qos'], 1)
            self.assertIs(p['retain'], False)
        self.assertEqual([x['target']['entity_id'] for x in all_actions
                          if x['action'] == 'input_boolean.turn_on'], [PENDING])
        self.assertEqual([x['target']['entity_id'] for x in all_actions
                          if x['action'] == 'input_datetime.set_datetime'], [MARKER])
        actions = [s.get('action') for s in self.seq]
        self.assertLess(actions.index('script.balkons_watering_dry_run'), actions.index('mqtt.publish'))
        self.assertLess(actions.index('input_boolean.turn_on'), actions.index('mqtt.publish'))
        self.assertLess(actions.index('input_datetime.set_datetime'),
                        max(i for i, s in enumerate(self.seq) if s.get('action') == 'mqtt.publish'))
        self.assertEqual([s.get('action') for s in self.stop[1:]],
                         ['input_boolean.turn_off', 'script.turn_off', 'mqtt.publish'])
        repeat = [n['repeat'] for n in nodes(self.seq) if 'repeat' in n]
        self.assertEqual(len(repeat), 1)
        self.assertEqual(repeat[0]['sequence'][0]['data']['payload'], 'OFF')
        self.assertEqual(repeat[0]['sequence'][1]['timeout'], '00:00:05')
        limit = repeat[0]['until'][0]['value_template']
        for i, expected in [(1, False), (2, False), (3, True)]:
            self.assertIs(self.render(limit, repeat=SimpleNamespace(index=i),
                                      wait=SimpleNamespace(completed=False)), expected)

    def test_preview_is_only_negative_filter(self):
        pred = next(s['value_template'] for s in self.seq if 'preview is mapping' in s.get('value_template', ''))
        good = dict(dry_run=True, live_authorized=False, decision='would_water', candidate_seconds=45)
        self.assertIs(self.render(pred, preview=good), True)
        for preview in (None, {}, good | {'decision': 'block_frost'},
                        good | {'live_authorized': True}, good | {'candidate_seconds': 180}):
            self.assertIs(self.render(pred, preview=preview), False)

    def test_offer_freeze_cancellation_expiry(self):
        pred = next(s['value_template'] for s in self.seq
                    if 'offer | length' in s.get('value_template', ''))
        self.assertIs(self.render(pred), True)
        for bad in (OFFER + '\n', OFFER.upper(), 'offer:ffffffffffffffff:' + TICKET,
                    OFFER[:-1], OFFER[:-1] + 'g', 'on:' + TICKET):
            self.assertIs(self.render(pred, offer=bad), False)
        self.states[ARM] = 'off'
        self.assertIs(self.render(pred), False)
        self.states[ARM] = 'on'
        self.states[PENDING] = 'unknown'
        self.assertIs(self.render(pred), False)
        self.states[PENDING] = 'on'
        self.assertIs(self.render(pred, wait=SimpleNamespace(completed=False)), False)
        self.clock += timedelta(seconds=8)
        self.assertIs(self.render(pred), False)
        self.clock -= timedelta(seconds=9)
        self.assertIs(self.render(pred), False)

    def test_pre_dispatch_requires_readback_and_unchanged_inputs(self):
        pred = next(s['value_template'] for s in self.seq if
                    s.get('alias', '').startswith('Recheck snapshot'))
        self.assertIs(self.render(pred), True)
        for key, value in ((ARM, 'off'), (PENDING, 'off'), (PUMP, 'on'),
                           (MARKER, '2026-11-23'), (MAIL, OFFER[:-1]+'2'),
                           ('sensor.balkona_laistisana_puke_5', 'mitrs'), (WEATHER, 'unknown')):
            original = self.states[key]
            self.states[key] = value
            self.assertIs(self.render(pred), False, key)
            self.states[key] = original
        self.attrs[MARKER]['has_time'] = True
        self.assertIs(self.render(pred), False)
        self.attrs[MARKER]['has_time'] = False
        self.clock += timedelta(days=1)
        self.assertIs(self.render(pred), False)

    def test_ack_correlation_and_deadline(self):
        on = next(s['variables']['on_seen'] for s in self.seq
                  if isinstance(s.get('variables', {}).get('on_seen'), str))
        off = next(n['variables']['off_seen'] for n in nodes(self.seq)
                   if isinstance(n.get('variables', {}).get('off_seen'), str))
        self.states[MAIL] = 'on:' + TICKET
        self.assertIs(self.render(on), True)
        self.states[MAIL] = 'on:' + TICKET[:-1] + '2'
        self.assertIs(self.render(on), False)
        self.states[MAIL] = 'on:' + TICKET
        self.clock += timedelta(seconds=6)
        self.assertIs(self.render(on), False)
        self.states[MAIL] = 'off:' + TICKET
        self.assertIs(self.render(off), True)
        self.states[PUMP] = 'on'
        self.assertIs(self.render(off), False)
        self.states[PUMP] = 'off'
        self.states[ARM] = 'off'
        self.assertIs(self.render(off), False)
        self.states[ARM] = 'on'
        self.clock += timedelta(seconds=40)
        self.assertIs(self.render(off), False)


if __name__ == '__main__':
    unittest.main()
