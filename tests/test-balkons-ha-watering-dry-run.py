#!/usr/bin/env python3
"""Render the actual staged Jinja with synthetic HA inputs; no HA/network."""
import ast
import math
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ops/homeassistant/balkons-watering-dry-run.yaml'
WEATHER = 'weather.forecast_home'
MARKER = 'input_datetime.balkons_last_watering_attempt'
PUMP = 'switch.balkona_laistisana_suknis'
TZ = ZoneInfo('Europe/Berlin')
NOW = datetime(2026, 11, 24, 11, tzinfo=TZ)


def checked_template(text):
    script = yaml.safe_load(text)
    assert list(script) == ['balkons_watering_dry_run']
    script = script['balkons_watering_dry_run']
    assert set(script) == {'alias', 'mode', 'sequence'} and script['mode'] == 'single'
    read, variables, stop = script['sequence']
    assert read == {'action': 'weather.get_forecasts', 'target': {'entity_id': WEATHER},
                    'data': {'type': 'daily'}, 'response_variable': 'forecast_response',
                    'continue_on_error': True}
    assert stop == {'stop': 'Dry-run decision only', 'response_variable': 'result'}
    assert list(variables) == ['variables'] and list(variables['variables']) == ['result']
    return variables['variables']['result']


def parse_datetime(value, default=None):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        return datetime.fromisoformat(value)
    except (TypeError, ValueError, OverflowError):
        return default


def parse_date(value, fmt, default=None):
    try:
        return datetime.strptime(value, fmt)
    except (TypeError, ValueError):
        return default


def is_number(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError, OverflowError):
        return False


class DryRun(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding='utf-8')
        self.template = checked_template(self.source)
        self.clock = NOW
        self.states = {f'sensor.balkona_laistisana_puke_{i}': 'sauss'
                       for i in (1, 3, 4, 5, 6, 7, 8, 9, 10, 12)}
        self.states.update({WEATHER: 'sunny', MARKER: '2026-11-23', PUMP: 'off'})
        self.attrs = {WEATHER: {'temperature': 6, 'temperature_unit': '°C'},
                      MARKER: {'has_date': True, 'has_time': False}}
        self.forecast = {WEATHER: {'forecast': [
            {'datetime': '2026-11-24T12:00:00+01:00', 'templow': 4},
            {'datetime': '2026-11-25T12:00:00+01:00', 'templow': 3}]}}

    def evaluate(self, reason):
        env = Environment(undefined=StrictUndefined)
        get_state = lambda entity: self.states.get(entity, 'unknown')
        env.globals.update(now=lambda: self.clock, timedelta=timedelta,
                           as_datetime=parse_datetime, as_timestamp=lambda dt: dt.timestamp(),
                           as_local=lambda dt: dt.astimezone(TZ), strptime=parse_date,
                           states=get_state, has_value=lambda entity: get_state(entity) not in
                           ('unknown', 'unavailable'), is_number=is_number,
                           state_attr=lambda entity, attr: self.attrs.get(entity, {}).get(attr))
        response = ast.literal_eval(env.from_string(self.template).render(
            forecast_response=self.forecast, true=True, false=False).strip())
        self.assertEqual(response['decision'], reason)
        self.assertIs(response['dry_run'], True)
        self.assertIs(response['live_authorized'], False)
        self.assertEqual(response['candidate_seconds'], 45)
        return response

    def test_mild_dry(self):
        self.assertEqual(self.evaluate('would_water')['minimum_c'], 3)

    def test_retired_sensors_ignored(self):
        for i in (2, 11, 13, 14, 15):
            self.states[f'sensor.balkona_laistisana_puke_{i}'] = 'bad'
        self.evaluate('would_water')

    def test_degraded_boundary(self):
        for i in (5, 6):
            del self.states[f'sensor.balkona_laistisana_puke_{i}']
        self.assertEqual(self.evaluate('would_water')['assumed_moist'], [5, 6])
        self.states['sensor.balkona_laistisana_puke_7'] = 'unavailable'
        self.evaluate('block_sensor_coverage')

    def test_invalid_values(self):
        for value in ('unexpected', 'videjs'):
            self.states['sensor.balkona_laistisana_puke_5'] = value
            self.evaluate('block_sensor_value')

    def test_dry_quorum(self):
        for i in (3, 4, 5, 6, 7, 8, 9, 10, 12):
            self.states[f'sensor.balkona_laistisana_puke_{i}'] = 'mitrs'
        self.evaluate('skip_dry_quorum')

    def test_moist_guard_with_assumed(self):
        for i in (4, 6, 7, 8, 9, 10, 12):
            self.states[f'sensor.balkona_laistisana_puke_{i}'] = 'mitrs'
        self.states['sensor.balkona_laistisana_puke_5'] = 'unavailable'
        result = self.evaluate('skip_moist')
        self.assertEqual(result['measured_moist'], 7)
        self.assertEqual(result['assumed_moist'], [5])

    def test_frost_boundaries(self):
        self.attrs[WEATHER]['temperature'] = 2
        self.evaluate('block_frost')
        self.attrs[WEATHER]['temperature'] = 6
        self.forecast[WEATHER]['forecast'][1]['templow'] = 2
        self.evaluate('block_frost')

    def test_invalid_forecast(self):
        original = self.forecast
        rows = original[WEATHER]['forecast']
        for fixture in (None, {}, {WEATHER: {'forecast': []}},
                        {WEATHER: {'forecast': rows[:1]}},
                        {WEATHER: {'forecast': rows + rows}},
                        {WEATHER: {'forecast': [rows[0], dict(rows[1], templow='NaN')]}},
                        {WEATHER: {'forecast': [rows[0], dict(rows[1], templow=True)]}},
                        {WEATHER: {'forecast': [rows[0], {'datetime': rows[1]['datetime'], 'temperature': 5}]}},
                        {WEATHER: {'forecast': [rows[0], dict(rows[1], datetime='2026-11-25T12:00:00')]}}):
            self.forecast = fixture
            self.evaluate('block_forecast')
        self.forecast = original
        self.attrs[WEATHER]['temperature_unit'] = '°F'
        self.evaluate('block_forecast')
        self.attrs[WEATHER]['temperature_unit'] = '°C'
        self.states[WEATHER] = 'unavailable'
        self.evaluate('block_forecast')

    def test_day_and_pump(self):
        for value in ('unknown', '2026-11-25', '2026-11-2', '2026-02-30'):
            self.states[MARKER] = value
            self.evaluate('block_day_state')
        self.states[MARKER] = '2026-11-24'
        self.evaluate('block_already_attempted')
        self.states[MARKER] = '2026-11-23'
        for value in ('on', 'unavailable', 'unknown'):
            self.states[PUMP] = value
            self.evaluate('block_pump_state')
        self.states[PUMP] = 'off'
        self.clock = NOW.astimezone(timezone.utc)
        self.evaluate('block_timezone')

    def test_no_additional_action(self):
        for changed in (self.source.replace('weather.get_forecasts', 'switch.turn_on'),
                        self.source + '    - action: mqtt.publish\n',
                        self.source.replace('mode: single', 'mode: parallel')):
            with self.assertRaises((AssertionError, ValueError)):
                checked_template(changed)


if __name__ == '__main__':
    unittest.main()
