#!/usr/bin/env python3
"""Strict internal validation for runtime diff reports."""
from __future__ import annotations
import collections
import re
import runtime_diff_core as core
import runtime_diff_dynamic as dynamic

SHA_RE=re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE=re.compile(r"^[0-9a-f]{40}$")
UTC_RE=re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

def _exact_keys(value: object, keys: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('invalid report object')

def _validate_binding(value: object) -> None:
    _exact_keys(value, {'sha256', 'baseline_schema', 'collection_utc', 'source_commit', 'evidence_manifest_sha256', 'context'})
    assert isinstance(value, dict)
    if not SHA_RE.fullmatch(value['sha256']) or value['baseline_schema'] != 'v02b.0.0' or (not UTC_RE.fullmatch(value['collection_utc'])) or (not COMMIT_RE.fullmatch(value['source_commit'])) or (not SHA_RE.fullmatch(value['evidence_manifest_sha256'])) or (not isinstance(value['context'], str)):
        raise ValueError('invalid binding')

def _ensure_sorted_unique(items: list[dict], key) -> None:
    if not isinstance(items, list):
        raise ValueError('invalid list')
    identities = [key(item) for item in items]
    if identities != sorted(identities) or len(set(identities)) != len(identities):
        raise ValueError('unsorted or duplicate report identity')

def _validate_socket_item(item: object, expected_dynamic: bool | None=None) -> None:
    _exact_keys(item, {'protocol', 'address_scope', 'port'})
    assert isinstance(item, dict)
    identity = dynamic.socket_identity(item)
    if identity[0] not in {'tcp', 'tcp6', 'udp', 'udp6'} or identity[1] not in {'wildcard', 'loopback', 'private_or_local', 'specific_other', 'unknown'} or (not isinstance(identity[2], int)) or (not 1 <= identity[2] <= 65535):
        raise ValueError('invalid socket observation')
    if expected_dynamic is True and (not dynamic.is_dynamic_socket(item)):
        raise ValueError('non-dynamic socket in dynamic group')
    if expected_dynamic is False and dynamic.is_dynamic_socket(item):
        raise ValueError('dynamic socket in stable group')

def _validate_socket_semantics(value: object) -> None:
    _exact_keys(value, {'stable', 'dynamic_high_port'})
    assert isinstance(value, dict)
    stable = value['stable']
    _exact_keys(stable, {'added', 'removed'})
    for key in ('added', 'removed'):
        _ensure_sorted_unique(stable[key], dynamic.socket_identity)
        for item in stable[key]:
            _validate_socket_item(item, False)
    group = value['dynamic_high_port']
    _exact_keys(group, {'classification', 'port_floor', 'bucket_delta_tolerance', 'before_count', 'after_count', 'added_count', 'removed_count', 'buckets', 'raw_added', 'raw_removed'})
    if group['port_floor'] != dynamic.HIGH_PORT_FLOOR or group['bucket_delta_tolerance'] != dynamic.HIGH_PORT_BUCKET_DELTA_TOLERANCE or group['classification'] not in {'none', 'informational', 'attention'}:
        raise ValueError('invalid dynamic socket policy')
    for key in ('before_count', 'after_count', 'added_count', 'removed_count'):
        if not isinstance(group[key], int) or group[key] < 0:
            raise ValueError('invalid dynamic socket count')
    for key in ('raw_added', 'raw_removed'):
        _ensure_sorted_unique(group[key], dynamic.socket_identity)
        for item in group[key]:
            _validate_socket_item(item, True)
    if group['added_count'] != len(group['raw_added']) or group['removed_count'] != len(group['raw_removed']):
        raise ValueError('dynamic socket count mismatch')
    if group['after_count'] - group['before_count'] != group['added_count'] - group['removed_count']:
        raise ValueError('dynamic socket aggregate mismatch')
    buckets = group['buckets']
    if not isinstance(buckets, list):
        raise ValueError('invalid socket buckets')
    identities = []
    added_counts = collections.Counter((dynamic._socket_bucket(item) for item in group['raw_added']))
    removed_counts = collections.Counter((dynamic._socket_bucket(item) for item in group['raw_removed']))
    before_total = after_total = 0
    for row in buckets:
        _exact_keys(row, {'protocol', 'address_scope', 'before_count', 'after_count', 'delta'})
        identity = (row['protocol'], row['address_scope'])
        identities.append(identity)
        if not all((isinstance(row[key], int) and row[key] >= 0 for key in ('before_count', 'after_count'))) or row['delta'] != row['after_count'] - row['before_count'] or row['delta'] != added_counts[identity] - removed_counts[identity]:
            raise ValueError('invalid socket bucket')
        before_total += row['before_count']
        after_total += row['after_count']
    if identities != sorted(identities) or len(set(identities)) != len(identities):
        raise ValueError('invalid socket bucket ordering')
    if before_total != group['before_count'] or after_total != group['after_count']:
        raise ValueError('invalid socket bucket totals')
    expected = dynamic.dynamic_socket_classification(buckets, bool(group['raw_added'] or group['raw_removed']))
    if group['classification'] != expected:
        raise ValueError('invalid dynamic socket classification')

def _validate_interface_object(item: object, expected_veth: bool | None=None) -> None:
    _exact_keys(item, {'name', 'operstate', 'link_type', 'loopback', 'ipv4_count', 'ipv6_count', 'scope_counts'})
    assert isinstance(item, dict)
    _exact_keys(item['scope_counts'], {'host', 'link', 'global', 'other'})
    if not isinstance(item['name'], str) or not isinstance(item['operstate'], str) or (not isinstance(item['link_type'], str)) or (not isinstance(item['loopback'], bool)) or (not all((isinstance(item[key], int) and item[key] >= 0 for key in ('ipv4_count', 'ipv6_count')))) or (not all((isinstance(count, int) and count >= 0 for count in item['scope_counts'].values()))):
        raise ValueError('invalid interface object')
    if expected_veth is True and (not dynamic.is_veth(item)):
        raise ValueError('non-veth in dynamic interface group')
    if expected_veth is False and dynamic.is_veth(item):
        raise ValueError('veth in stable interface group')

def _validate_stable_interface_diff(value: object) -> None:
    _exact_keys(value, {'added', 'removed', 'changed'})
    assert isinstance(value, dict)
    for key in ('added', 'removed'):
        _ensure_sorted_unique(value[key], lambda item: item['name'])
        for item in value[key]:
            _validate_interface_object(item, False)
    if not isinstance(value['changed'], list):
        raise ValueError('invalid stable interface changes')
    names = []
    for item in value['changed']:
        _exact_keys(item, {'name', 'fields', 'classification'})
        names.append(item['name'])
        if item['classification'] != 'attention' or not item['fields']:
            raise ValueError('invalid stable interface change')
    if names != sorted(names) or len(set(names)) != len(names):
        raise ValueError('invalid stable interface change ordering')

def _validate_interface_semantics(value: object) -> None:
    _exact_keys(value, {'stable', 'dynamic_veth'})
    assert isinstance(value, dict)
    _validate_stable_interface_diff(value['stable'])
    group = value['dynamic_veth']
    _exact_keys(group, {'classification', 'name_pattern', 'before_count', 'after_count', 'added_count', 'removed_count', 'changed_count', 'profiles', 'raw_added', 'raw_removed', 'raw_changed'})
    if group['name_pattern'] != '^veth[0-9a-f]{7,15}$' or group['classification'] not in {'none', 'informational', 'attention'}:
        raise ValueError('invalid dynamic interface policy')
    for key in ('before_count', 'after_count', 'added_count', 'removed_count', 'changed_count'):
        if not isinstance(group[key], int) or group[key] < 0:
            raise ValueError('invalid dynamic interface count')
    for key in ('raw_added', 'raw_removed'):
        _ensure_sorted_unique(group[key], lambda item: item['name'])
        for item in group[key]:
            _validate_interface_object(item, True)
    changed_names = []
    for item in group['raw_changed']:
        _exact_keys(item, {'name', 'before', 'after'})
        changed_names.append(item['name'])
        _validate_interface_object(item['before'], True)
        _validate_interface_object(item['after'], True)
        if item['before']['name'] != item['name'] or item['after']['name'] != item['name'] or dynamic.interface_profile(item['before']) == dynamic.interface_profile(item['after']):
            raise ValueError('invalid dynamic interface change')
    if changed_names != sorted(changed_names) or len(set(changed_names)) != len(changed_names):
        raise ValueError('invalid dynamic interface change ordering')
    if group['added_count'] != len(group['raw_added']) or group['removed_count'] != len(group['raw_removed']) or group['changed_count'] != len(group['raw_changed']):
        raise ValueError('dynamic interface raw count mismatch')
    if group['after_count'] - group['before_count'] != group['added_count'] - group['removed_count']:
        raise ValueError('dynamic interface aggregate mismatch')
    before_deltas = collections.Counter()
    after_deltas = collections.Counter()
    for item in group['raw_removed']:
        before_deltas[dynamic.interface_profile(item)] += 1
    for item in group['raw_added']:
        after_deltas[dynamic.interface_profile(item)] += 1
    for item in group['raw_changed']:
        before_deltas[dynamic.interface_profile(item['before'])] += 1
        after_deltas[dynamic.interface_profile(item['after'])] += 1
    profile_keys = []
    before_total = after_total = 0
    for row in group['profiles']:
        _exact_keys(row, {'profile', 'before_count', 'after_count', 'delta'})
        _validate_interface_object({'name': 'profile', **row['profile']})
        profile = dynamic.interface_profile({'name': 'profile', **row['profile']})
        profile_keys.append(profile)
        if not isinstance(row['before_count'], int) or row['before_count'] < 0 or (not isinstance(row['after_count'], int)) or (row['after_count'] < 0) or (row['delta'] != row['after_count'] - row['before_count']) or (row['delta'] != after_deltas[profile] - before_deltas[profile]):
            raise ValueError('invalid dynamic interface profile')
        before_total += row['before_count']
        after_total += row['after_count']
    if profile_keys != sorted(profile_keys) or len(set(profile_keys)) != len(profile_keys):
        raise ValueError('invalid interface profile ordering')
    if before_total != group['before_count'] or after_total != group['after_count']:
        raise ValueError('invalid interface profile totals')
    changed = bool(group['raw_added'] or group['raw_removed'] or group['raw_changed'])
    expected = 'none' if not changed else 'informational' if all((row['delta'] == 0 for row in group['profiles'])) else 'attention'
    if group['classification'] != expected:
        raise ValueError('invalid dynamic interface classification')

def _validate_scalar_change(item: object, *, identity_key: str, allowed_fields: set[str], classification: str) -> str:
    _exact_keys(item, {identity_key, 'fields', 'classification'})
    assert isinstance(item, dict)
    identity = item[identity_key]
    if not isinstance(identity, str) or not identity:
        raise ValueError('invalid change identity')
    if item['classification'] != classification:
        raise ValueError('invalid change classification')
    fields = item['fields']
    if not isinstance(fields, dict) or not fields or (not set(fields) <= allowed_fields):
        raise ValueError('invalid changed fields')
    for value in fields.values():
        _exact_keys(value, {'before', 'after'})
        if value['before'] == value['after']:
            raise ValueError('unchanged field emitted')
    return identity

def _validate_mapdiff(value: object, *, identity_key: str, object_fields: set[str], change_fields: set[str]) -> None:
    _exact_keys(value, {'added', 'removed', 'changed'})
    assert isinstance(value, dict)
    for key in ('added', 'removed'):
        items = value[key]
        if not isinstance(items, list):
            raise ValueError('invalid mapdiff list')
        identities = []
        for item in items:
            _exact_keys(item, object_fields)
            identity = item[identity_key]
            if not isinstance(identity, str) or not identity:
                raise ValueError('invalid mapdiff identity')
            identities.append(identity)
        if identities != sorted(identities) or len(set(identities)) != len(identities):
            raise ValueError('unsorted or duplicate mapdiff identities')
    if not isinstance(value['changed'], list):
        raise ValueError('invalid mapdiff changes')
    changed_identities = [_validate_scalar_change(item, identity_key=identity_key, allowed_fields=change_fields, classification='attention') for item in value['changed']]
    if changed_identities != sorted(changed_identities) or len(set(changed_identities)) != len(changed_identities):
        raise ValueError('unsorted or duplicate changed identities')

def _validate_regular_domains(changes: dict) -> None:
    docker_versions = changes['docker_versions']
    _exact_keys(docker_versions, {'changed'})
    if not isinstance(docker_versions['changed'], list):
        raise ValueError('invalid version changes')
    version_fields = []
    for item in docker_versions['changed']:
        _exact_keys(item, {'field', 'before', 'after', 'classification'})
        if item['field'] not in {'engine_version', 'compose_version'} or item['classification'] != 'informational' or item['before'] == item['after']:
            raise ValueError('invalid version change')
        version_fields.append(item['field'])
    version_order = {'engine_version': 0, 'compose_version': 1}
    if version_fields != sorted(version_fields, key=version_order.__getitem__) or len(set(version_fields)) != len(version_fields):
        raise ValueError('invalid version ordering')
    _validate_mapdiff(changes['containers'], identity_key='name', object_fields={'name', 'image', 'state', 'health'}, change_fields={'image', 'state', 'health'})
    _validate_mapdiff(changes['compose_projects'], identity_key='name', object_fields={'name', 'status'}, change_fields={'status'})
    _validate_mapdiff(changes['networks'], identity_key='name', object_fields={'name', 'driver', 'scope'}, change_fields={'driver', 'scope'})
    _validate_mapdiff(changes['enabled_units'], identity_key='name', object_fields={'name', 'state'}, change_fields={'state'})
    _validate_mapdiff(changes['failed_units'], identity_key='name', object_fields={'name', 'load', 'active', 'sub'}, change_fields={'load', 'active', 'sub'})
    systemd_state = changes['systemd_state']
    _exact_keys(systemd_state, {'changed'})
    if not isinstance(systemd_state['changed'], list) or len(systemd_state['changed']) > 1:
        raise ValueError('invalid systemd state changes')
    for item in systemd_state['changed']:
        _exact_keys(item, {'field', 'before', 'after', 'classification'})
        if item['field'] != 'system_state' or item['classification'] != 'attention' or item['before'] == item['after']:
            raise ValueError('invalid systemd state change')
    timers = changes['timers']
    _exact_keys(timers, {'structural_changes', 'temporal_changes'})
    _validate_mapdiff(timers['structural_changes'], identity_key='id', object_fields={'id', 'load', 'active', 'sub', 'activates', 'next', 'last'}, change_fields={'load', 'active', 'sub', 'activates'})
    if not isinstance(timers['temporal_changes'], list):
        raise ValueError('invalid temporal timer changes')
    timer_ids = [_validate_scalar_change(item, identity_key='id', allowed_fields={'next', 'last'}, classification='informational') for item in timers['temporal_changes']]
    if timer_ids != sorted(timer_ids) or len(set(timer_ids)) != len(timer_ids):
        raise ValueError('invalid temporal timer ordering')
    limitations = changes['limitations']
    _exact_keys(limitations, {'added', 'removed', 'classification'})
    if limitations['classification'] != 'informational':
        raise ValueError('invalid limitation classification')
    for key in ('added', 'removed'):
        if not isinstance(limitations[key], list) or limitations[key] != sorted(set(limitations[key])) or (not all((isinstance(item, str) for item in limitations[key]))):
            raise ValueError('invalid limitations')

def _validate_v2_domains(changes: object) -> None:
    if not isinstance(changes, dict) or set(changes) != set(core.DOMAINS):
        raise ValueError('invalid change domains')
    _validate_regular_domains(changes)
    _validate_socket_semantics(changes['sockets'])
    _validate_interface_semantics(changes['interfaces'])

def validate_report(report_data: object) -> dict:
    _exact_keys(report_data, {'schema', 'inputs', 'summary', 'changes'})
    assert isinstance(report_data, dict)
    if report_data['schema'] == core.SCHEMA_V1:
        summary = report_data['summary']
        _exact_keys(summary, {'material_changes', 'informational_changes', 'added', 'removed', 'changed', 'per_domain', 'review_level'})
        if report_data['schema'] != core.SCHEMA_V1 or set(report_data['changes']) != set(core.DOMAINS) or set(summary['per_domain']) != set(core.DOMAINS) or (summary['review_level'] not in {'none', 'informational', 'attention'}):
            raise ValueError('invalid v1 report')
        expected = 'attention' if summary['material_changes'] else 'informational' if summary['informational_changes'] else 'none'
        if expected != summary['review_level']:
            raise ValueError('invalid v1 review level')
        return report_data
    if report_data['schema'] != core.SCHEMA_V2:
        raise ValueError('unsupported report schema')
    _exact_keys(report_data['inputs'], {'before', 'after'})
    _validate_binding(report_data['inputs']['before'])
    _validate_binding(report_data['inputs']['after'])
    _validate_v2_domains(report_data['changes'])
    expected_summary = core.summarize_v2(report_data['changes'])
    if report_data['summary'] != expected_summary:
        raise ValueError('runtime diff summary mismatch')
    return report_data
