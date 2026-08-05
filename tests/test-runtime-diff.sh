#!/usr/bin/env bash
set -Eeuo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
compare="${repo_root}/scripts/compare-runtime-baselines.py"
verify="${repo_root}/scripts/verify-runtime-diff.py"
fixtures="${repo_root}/tests/fixtures/runtime-diff"
root="$(mktemp -d "${repo_root}/evidence/test-runtime-diff.XXXXXX")"
trap 'rm -rf -- "${root}"' EXIT
fail(){ printf 'test-runtime-diff: FAIL: %s\n' "$1" >&2; exit 1; }
run(){ python3 "${compare}" --before "$1" --after "$2" --json-out "$3" --markdown-out "$4"; }

run "${fixtures}/no-change.json" "${fixtures}/no-change.json" "${root}/one.json" "${root}/one.md"
python3 "${verify}" "${root}/one.json" "${root}/one.md" >/dev/null
grep -q 'No runtime drift detected' "${root}/one.md" || fail 'missing no-change statement'
python3 - "${root}/one.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['schema']=='rpi5.runtime-diff.v2'
assert x['summary']['review_level']=='none'
assert x['summary']['raw_observations']=={
  'interfaces':{'added':0,'changed':0,'removed':0},
  'sockets':{'added':0,'removed':0},
}
PY

run "${fixtures}/no-change.json" "${fixtures}/no-change.json" "${root}/two.json" "${root}/two.md"
cmp "${root}/one.json" "${root}/two.json" || fail 'non-deterministic JSON'
cmp "${root}/one.md" "${root}/two.md" || fail 'non-deterministic Markdown'

run "${fixtures}/before.json" "${fixtures}/after.json" "${root}/full.json" "${root}/full.md"
python3 "${verify}" "${root}/full.json" "${root}/full.md" >/dev/null
python3 - "${root}/full.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['schema']=='rpi5.runtime-diff.v2'
assert x['summary']['review_level']=='attention'
assert x['summary']['material_changes']>0
assert x['summary']['informational_changes']>0
assert x['changes']['containers']['added']
assert x['changes']['containers']['removed']
assert x['changes']['containers']['changed']
assert x['changes']['timers']['structural_changes']
assert x['changes']['timers']['temporal_changes']
assert x['changes']['sockets']['stable']['added']
assert x['changes']['sockets']['stable']['removed']
PY

run "${fixtures}/dynamic-before.json" "${fixtures}/dynamic-after.json" "${root}/dynamic.json" "${root}/dynamic.md"
python3 "${verify}" "${root}/dynamic.json" "${root}/dynamic.md" >/dev/null
python3 - "${root}/dynamic.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
s=x['summary']; c=x['changes']
assert s['material_changes']==1
assert s['informational_changes']==2
assert s['added']==1 and s['removed']==0 and s['changed']==2
assert s['raw_observations']['sockets']=={'added':4,'removed':4}
assert s['raw_observations']['interfaces']=={'added':2,'removed':2,'changed':0}
assert c['sockets']['stable']['added']==[{'protocol':'udp','address_scope':'specific_other','port':5353}]
assert c['sockets']['dynamic_high_port']['classification']=='informational'
assert c['interfaces']['dynamic_veth']['classification']=='informational'
assert len(c['sockets']['dynamic_high_port']['raw_added'])==4
assert len(c['interfaces']['dynamic_veth']['raw_removed'])==2
PY
grep -q 'dynamic high-port churn: informational' "${root}/dynamic.md" || fail 'missing socket semantic summary'
grep -q 'dynamic veth churn: informational' "${root}/dynamic.md" || fail 'missing veth semantic summary'

cp "${fixtures}/dynamic-after.json" "${root}/dynamic-attention.json"
python3 - "${root}/dynamic-attention.json" <<'PY'
import json,sys
p=sys.argv[1]; x=json.load(open(p))
x['sockets']=[s for s in x['sockets'] if not (s['protocol']=='tcp' and s['port']>=32768)]
x['interfaces']=[i for i in x['interfaces'] if i['name']!='vethddddddd']
open(p,'w').write(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n')
PY
run "${fixtures}/dynamic-before.json" "${root}/dynamic-attention.json" "${root}/attention.json" "${root}/attention.md"
python3 "${verify}" "${root}/attention.json" "${root}/attention.md" >/dev/null
python3 - "${root}/attention.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['changes']['sockets']['dynamic_high_port']['classification']=='attention'
assert x['changes']['interfaces']['dynamic_veth']['classification']=='attention'
assert x['summary']['review_level']=='attention'
PY

cp "${root}/dynamic.json" "${root}/tampered.json"
cp "${root}/dynamic.md" "${root}/tampered.md"
python3 - "${root}/tampered.json" <<'PY'
import json,sys
p=sys.argv[1]; x=json.load(open(p))
x['changes']['sockets']['dynamic_high_port']['classification']='attention'
x['summary']['review_level']='attention'
open(p,'w').write(json.dumps(x,sort_keys=True,indent=2)+'\n')
PY
if python3 "${verify}" "${root}/tampered.json" "${root}/tampered.md" >/dev/null 2>&1; then
  fail 'dynamic classification tampering accepted'
fi

cp "${root}/dynamic.json" "${root}/unknown.json"
cp "${root}/dynamic.md" "${root}/unknown.md"
python3 - "${root}/unknown.json" <<'PY'
import json,sys
p=sys.argv[1]; x=json.load(open(p))
x['changes']['sockets']['dynamic_high_port']['unexpected']=True
open(p,'w').write(json.dumps(x,sort_keys=True,indent=2)+'\n')
PY
if python3 "${verify}" "${root}/unknown.json" "${root}/unknown.md" >/dev/null 2>&1; then
  fail 'unknown v2 field accepted'
fi

cp "${fixtures}/before.json" "${root}/bad.json"
python3 - "${root}/bad.json" <<'PY'
import json,sys
p=sys.argv[1]; x=json.load(open(p)); x['docker']['containers'].append(x['docker']['containers'][0]); open(p,'w').write(json.dumps(x))
PY
if run "${root}/bad.json" "${fixtures}/after.json" "${root}/badout.json" "${root}/badout.md" >/dev/null 2>&1; then fail 'duplicate baseline accepted'; fi
ln "${fixtures}/no-change.json" "${root}/unsafe.json"
if run "${root}/unsafe.json" "${fixtures}/no-change.json" "${root}/unsafeout.json" "${root}/unsafeout.md" >/dev/null 2>&1; then fail 'hard-linked input accepted'; fi
if run "${fixtures}/no-change.json" "${fixtures}/no-change.json" /tmp/out.json /tmp/out.md >/dev/null 2>&1; then fail 'outside output accepted'; fi
ln -s "${root}" "${root}/link"
if run "${fixtures}/no-change.json" "${fixtures}/no-change.json" "${root}/link/x.json" "${root}/link/x.md" >/dev/null 2>&1; then fail 'symlink output accepted'; fi

v05_before="${repo_root}/baselines/runtime/archive/2026-08-04T22-52-46Z--db222c2d6696/baseline.json"
v05_target_sha="2db82cc46d840aced4e57431195c821ead8f916bf9adfb707f2ac60c3bf371bc"
v05_after=""
if [[ "$(sha256sum "${repo_root}/baselines/runtime/current.json" | awk '{print $1}')" == "${v05_target_sha}" ]]; then
  v05_after="${repo_root}/baselines/runtime/current.json"
else
  while IFS= read -r candidate; do
    if [[ "$(sha256sum "${candidate}" | awk '{print $1}')" == "${v05_target_sha}" ]]; then
      v05_after="${candidate}"
      break
    fi
  done < <(find "${repo_root}/baselines/runtime/archive" -mindepth 2 -maxdepth 2 -name baseline.json -type f | LC_ALL=C sort)
fi
[[ -n "${v05_after}" ]] || fail 'V05 candidate baseline not found for replay'
run "${v05_before}" "${v05_after}" "${root}/v05-replay.json" "${root}/v05-replay.md"
python3 "${verify}" "${root}/v05-replay.json" "${root}/v05-replay.md" >/dev/null
python3 - "${root}/v05-replay.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
s=x['summary']; c=x['changes']
assert s['material_changes']==2
assert s['informational_changes']==12
assert s['added']==1 and s['removed']==1 and s['changed']==12
assert s['raw_observations']['sockets']=={'added':33,'removed':35}
assert s['raw_observations']['interfaces']=={'added':16,'removed':16,'changed':0}
assert c['sockets']['dynamic_high_port']['classification']=='informational'
assert c['interfaces']['dynamic_veth']['classification']=='informational'
assert c['sockets']['stable']['added']==[
  {'protocol':'udp','address_scope':'specific_other','port':5353}
]
assert c['systemd_state']['changed'][0]['before']=='degraded'
assert c['systemd_state']['changed'][0]['after']=='running'
PY

archive="${repo_root}/baselines/runtime/archive/2026-08-04T22-52-46Z--db222c2d6696"
python3 "${verify}" "${archive}/runtime-diff.json" "${archive}/runtime-diff.md" >/dev/null ||
  fail 'archived v1 report is no longer valid'

printf '%s\n' 'Runtime diff tests: PASS'
