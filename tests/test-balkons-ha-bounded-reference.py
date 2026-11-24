#!/usr/bin/env python3
"""Offline structural and actual Jinja predicate tests, never execute HA actions."""
import re
import math
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
REVISION = '65309e8902c31f561e4a20bbc2c415544cfd6933'
REQUEST = f'ticket45:{RID}'
OFFER = f'offer2:{RID}:{TICKET}:{REVISION}:DDDWWWWWWU:off'
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


class StateView:
    """Minimal HA state-object and callable interface for offline rendering."""
    def __init__(self, values, changed, updated, contexts):
        self.values = values
        self.changed = changed
        self.updated = updated
        self.contexts = contexts

    def __call__(self, key):
        return self.values.get(key, 'unknown')

    def __getitem__(self, key):
        if key not in self.values:
            return None
        return SimpleNamespace(state=self.values[key],
                               last_changed=self.changed[key],
                               last_updated=self.updated[key],
                               context=SimpleNamespace(id=self.contexts[key]))


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
        self.changed = {key: self.clock - timedelta(seconds=2) for key in self.states}
        self.updated = {key: self.clock - timedelta(milliseconds=500) for key in self.states}
        self.contexts = {key: 'initial-context' for key in self.states}
        self.env = NativeEnvironment(undefined=StrictUndefined)
        self.env.filters['regex_match'] = lambda value, pattern: re.match(pattern, value) is not None
        self.env.globals.update(
            now=lambda: self.clock, as_timestamp=lambda dt: dt.timestamp(),
            is_number=lambda v: isinstance(v, (int, float)) and math.isfinite(v),
            states=StateView(self.states, self.changed, self.updated, self.contexts),
            state_attr=lambda key, attr: self.attrs.get(key, {}).get(attr),
            is_state=lambda key, value: self.states.get(key, 'unknown') == value)
        self.v = dict(marker=MARKER, pump=PUMP, arm=ARM, pending=PENDING, mailbox=MAIL,
                      day='2026-11-24', old_date='2026-11-23',
                      request_payload=REQUEST, expected_revision=REVISION, offer=OFFER,
                      start_payload='start45:' + TICKET, on_ack='on:' + TICKET,
                      off_ack='off:' + TICKET,
                      request_at=self.clock.timestamp() - 1, dispatch_at=self.clock.timestamp() - 1,
                      offer_updated=self.updated[MAIL].timestamp(),
                      wait=SimpleNamespace(completed=True), on_seen=True, off_seen=True)
        snap = next(s['variables']['snapshot'] for s in self.seq
                    if 'snapshot' in s.get('variables', {}))
        self.v['snapshot'] = self.render(snap)
        for name in ('arm_generation', 'pending_generation'):
            template = next(s['variables'][name] for s in self.seq if name in s.get('variables', {}))
            self.v[name] = self.render(template)

    def render(self, template, **changes):
        return self.env.from_string(template).render(**(self.v | changes))

    def test_inert_and_single_entry(self):
        self.assertEqual(set(self.package), {'input_boolean', 'mqtt', 'script', 'automation'})
        self.assertEqual(set(self.package['script']), {START, STOP})
        self.assertEqual(self.package['script'][START]['mode'], 'single')
        self.assertTrue(guarded(self.seq[0]))
        self.assertTrue(guarded(self.stop[0]))
        self.assertEqual(sum(guarded(s) for s in self.seq), 3)
        self.assertEqual(next(s['variables']['expected_revision'] for s in self.seq
                              if 'expected_revision' in s.get('variables', {})), REVISION)
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
                         ["{{ request_payload }}", "{{ start_payload }}", 'OFF', 'OFF'])
        for p in pubs:
            self.assertEqual(set(p), {'topic', 'payload', 'qos', 'retain'})
            self.assertEqual(p['topic'], TOPIC)
            self.assertEqual(p['qos'], 1)
            self.assertIs(p['retain'], False)
        self.assertEqual([x['target']['entity_id'] for x in all_actions
                          if x['action'] == 'input_boolean.turn_on'], [PENDING, PENDING])
        self.assertEqual([x['target']['entity_id'] for x in all_actions
                          if x['action'] == 'input_datetime.set_datetime'], [MARKER])
        actions = [s.get('action') for s in self.seq]
        self.assertLess(actions.index('script.balkons_watering_dry_run'), actions.index('mqtt.publish'))
        self.assertLess(actions.index('input_boolean.turn_on'), actions.index('mqtt.publish'))
        self.assertLess(actions.index('input_datetime.set_datetime'),
                        max(i for i, s in enumerate(self.seq) if s.get('action') == 'mqtt.publish'))
        self.assertEqual([s.get('action') for s in self.stop[1:5]],
                         ['input_boolean.turn_off', 'script.turn_off',
                          'input_boolean.turn_on', 'mqtt.publish'])
        self.assertEqual(self.stop[3]['target']['entity_id'], PENDING)
        self.assertTrue(all(s['continue_on_error'] for s in self.stop[1:4]))
        self.assertEqual(self.stop[4]['data']['payload'], 'OFF')
        self.assertEqual(len(self.stop), 6)
        self.assertIs(self.stop[5]['then'][0]['error'], True)
        dispatch = max(i for i, s in enumerate(self.seq) if s.get('action') == 'mqtt.publish')
        self.assertTrue(self.seq[dispatch - 1]['alias'].startswith('Recheck snapshot'))
        self.assertIn('dispatch_at', self.seq[dispatch - 2]['variables'])
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
        good = dict(dry_run=True, live_authorized=False, decision='would_water',
                    candidate_seconds=45, minimum_c=8)
        self.assertIs(self.render(pred, preview=good), True)
        for decision in ('block_sensor_value', 'block_sensor_coverage', 'skip_dry_quorum', 'skip_moist'):
            self.assertIs(self.render(pred, preview=good | {'decision': decision}), True)
        for preview in (None, {}, good | {'decision': 'block_frost'},
                        good | {'decision': 'block_day'}, good | {'decision': 'block_pump'},
                        good | {'live_authorized': True}, good | {'candidate_seconds': 180},
                        *(good | {'minimum_c': v} for v in (None, 2, 1, True, '8', float('inf'), float('nan')))):
            self.assertIs(self.render(pred, preview=preview), False)

    def test_offer_freeze_cancellation_expiry(self):
        pred = next(s['value_template'] for s in self.seq
                    if 'offer | length' in s.get('value_template', ''))
        self.assertIs(self.render(pred), True)
        for bad in (OFFER + '\n', OFFER.upper(), f'offer:{RID}:{TICKET}',
                    OFFER.replace(RID, 'ffffffffffffffff'), OFFER.replace(REVISION, '0' * 40),
                    OFFER.replace(TICKET, TICKET.upper()), OFFER.replace('DDDWWWWWWU', 'DDDWWWWWXX'),
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
        self.clock -= timedelta(seconds=10)
        self.assertIs(self.render(pred), False)

    def test_pre_dispatch_requires_readback_and_unchanged_inputs(self):
        pred = next(s['value_template'] for s in self.seq if
                    s.get('alias', '').startswith('Recheck snapshot'))
        self.assertIs(self.render(pred), True)
        for key, value in ((ARM, 'off'), (PENDING, 'off'), (PUMP, 'on'),
                           (MARKER, '2026-11-23'), (MAIL, OFFER[:-1]+'2'),
                           (WEATHER, 'unknown')):
            original = self.states[key]
            self.states[key] = value
            self.assertIs(self.render(pred), False, key)
            self.states[key] = original
        self.states['sensor.balkona_laistisana_puke_5'] = 'mitrs'
        self.assertIs(self.render(pred), True)
        self.attrs[MARKER]['has_time'] = True
        self.assertIs(self.render(pred), False)
        self.attrs[MARKER]['has_time'] = False
        self.clock += timedelta(days=1)
        self.assertIs(self.render(pred), False)

    def test_fresh_moisture_policy_and_opaque_hex(self):
        pred = next(s['value_template'] for s in self.seq
                    if s.get('alias', '').startswith('Evaluate only the ten fresh'))
        for codes in ('DDDWWWWWWU', 'DDDDWWWWUU', 'DDDDDDDDDD'):
            self.assertIs(self.render(pred, offer=OFFER[:90] + codes + ':off'), True, codes)
        for codes in ('DDWWWWWWWW', 'DWWWWWWWWW', 'DDDDWWWUUU', 'DDDDWWWWWM',
                      'DDDWWWWWWX', 'DDDWWWWWW'):
            self.assertIs(self.render(pred, offer=OFFER[:90] + codes + ':off'), False, codes)
        variables = next(s['variables'] for s in self.seq
                         if 'start_payload' in s.get('variables', {}))
        for opaque in ('123456789012345678901234', '000000000000000000000001',
                       '1234567890123456789012e3'):
            offer = OFFER[:24] + opaque + OFFER[48:]
            self.assertEqual(self.render(variables['start_payload'], offer=offer), 'start45:' + opaque)
            self.assertEqual(self.render(variables['on_ack'], offer=offer), 'on:' + opaque)
            self.assertEqual(self.render(variables['off_ack'], offer=offer), 'off:' + opaque)
        req = next(s['variables']['request_payload'] for s in self.seq
                   if 'request_payload' in s.get('variables', {}))
        self.env.filters['random'] = lambda _seq: 0x1234
        self.assertEqual(self.render(req), 'ticket45:1234123412341234')
        guard = next(s['value_template'] for s in self.seq
                     if 'request_payload | length' in s.get('value_template', ''))
        self.assertIs(self.render(guard), False)
        self.states[MAIL] = 'unknown'
        self.assertIs(self.render(guard), True)

    def test_generation_cancellation_at_checked_boundaries(self):
        gates = [n['value_template'] for n in nodes(self.seq)
                 if 'arm_generation' in n.get('value_template', '')
                 and 'pending_generation' in n.get('value_template', '')]
        self.assertGreaterEqual(len(gates), 5)
        waits = [n['wait_template'] for n in nodes(self.seq)
                 if 'arm_generation' in n.get('wait_template', '')]
        self.assertEqual(len(waits), 3)
        for key in (ARM, PENDING):
            # OFF then ON is not the original generation, despite the same value.
            original = self.changed[key]
            self.changed[key] += timedelta(milliseconds=1)
            for gate in gates:
                self.assertIs(self.render(gate), False, gate)
            for wait in waits:
                self.assertIs(self.render(wait), True, wait)
            self.changed[key] = original
            original_context = self.contexts[key]
            self.contexts[key] = 'different-context'
            for gate in gates:
                self.assertIs(self.render(gate), False, gate)
            self.contexts[key] = original_context

    def test_offer_record_requires_post_request_update_and_no_rewrite(self):
        record = next(s['variables']['offer_record'] for s in self.seq
                      if 'offer_record' in s.get('variables', {}))
        self.assertEqual(self.render(record),
                         {'payload': OFFER, 'updated': self.v['offer_updated']})
        accept = next(s['value_template'] for s in self.seq
                      if 'offer | length' in s.get('value_template', ''))
        dispatch = next(s['value_template'] for s in self.seq
                        if s.get('alias', '').startswith('Recheck snapshot'))
        self.assertIs(self.render(accept), True)
        for timestamp in (self.v['request_at'] - 1, self.v['request_at'],
                          self.clock.timestamp() + 1, self.v['request_at'] + 6):
            self.assertIs(self.render(accept, offer_updated=timestamp), False)
        self.assertIs(self.render(dispatch), True)
        self.updated[MAIL] += timedelta(milliseconds=100)
        self.assertIs(self.render(dispatch), False)  # same payload, new event
        self.states.pop(MAIL)
        self.assertEqual(self.render(record), {'payload': '', 'updated': 0})
        self.assertIs(self.render(dispatch), False)

    def test_ack_correlation_and_deadline(self):
        on = next(s['variables']['on_seen'] for s in self.seq
                  if isinstance(s.get('variables', {}).get('on_seen'), str))
        off = next(n['variables']['off_seen'] for n in nodes(self.seq)
                   if isinstance(n.get('variables', {}).get('off_seen'), str))
        self.states[MAIL] = 'on:' + TICKET
        self.assertIs(self.render(on), True)
        updated = self.updated[MAIL]
        self.updated[MAIL] = self.clock - timedelta(seconds=2)
        self.assertIs(self.render(on), False)
        self.updated[MAIL] = updated
        self.states[MAIL] = 'on:' + TICKET[:-1] + '2'
        self.assertIs(self.render(on), False)
        self.states[MAIL] = 'on:' + TICKET
        self.clock += timedelta(seconds=6)
        self.assertIs(self.render(on), False)
        self.states[MAIL] = 'off:' + TICKET
        self.assertIs(self.render(off), True)
        self.updated[MAIL] = self.clock - timedelta(seconds=10)
        self.assertIs(self.render(off), False)
        self.updated[MAIL] = updated
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
