#!/usr/bin/env bash
set -Eeuo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
compare="${repo_root}/scripts/compare-runtime-baselines.py"; verify="${repo_root}/scripts/verify-runtime-diff.py"; fixtures="${repo_root}/tests/fixtures/runtime-diff"
root="$(mktemp -d "${repo_root}/evidence/test-runtime-diff.XXXXXX")"; trap 'rm -rf -- "${root}"' EXIT
fail(){ printf 'test-runtime-diff: FAIL: %s\n' "$1" >&2; exit 1; }
run(){ python3 "${compare}" --before "$1" --after "$2" --json-out "$3" --markdown-out "$4"; }
run "${fixtures}/no-change.json" "${fixtures}/no-change.json" "${root}/one.json" "${root}/one.md"
python3 "${verify}" "${root}/one.json" "${root}/one.md" >/dev/null
grep -q 'No runtime drift detected' "${root}/one.md" || fail 'missing no-change statement'
run "${fixtures}/no-change.json" "${fixtures}/no-change.json" "${root}/two.json" "${root}/two.md"
cmp "${root}/one.json" "${root}/two.json" || fail 'non-deterministic JSON'
cmp "${root}/one.md" "${root}/two.md" || fail 'non-deterministic Markdown'
run "${fixtures}/before.json" "${fixtures}/after.json" "${root}/full.json" "${root}/full.md"
python3 "${verify}" "${root}/full.json" "${root}/full.md" >/dev/null
python3 - "${root}/full.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x['schema']=='rpi5.runtime-diff.v1'; assert x['summary']['review_level']=='attention'; assert x['summary']['material_changes']>0; assert x['summary']['informational_changes']>0
assert x['changes']['containers']['added'] and x['changes']['containers']['removed'] and x['changes']['containers']['changed']
assert x['changes']['timers']['structural_changes'] and x['changes']['timers']['temporal_changes']
assert x['changes']['sockets']['added'] and x['changes']['sockets']['removed']
PY
cp "${fixtures}/before.json" "${root}/bad.json"; python3 - "${root}/bad.json" <<'PY'
import json,sys
p=sys.argv[1]; x=json.load(open(p)); x['docker']['containers'].append(x['docker']['containers'][0]); open(p,'w').write(json.dumps(x))
PY
if run "${root}/bad.json" "${fixtures}/after.json" "${root}/badout.json" "${root}/badout.md" >/dev/null 2>&1; then fail 'duplicate baseline accepted'; fi
ln "${fixtures}/no-change.json" "${root}/unsafe.json"
if run "${root}/unsafe.json" "${fixtures}/no-change.json" "${root}/unsafeout.json" "${root}/unsafeout.md" >/dev/null 2>&1; then fail 'hard-linked input accepted'; fi
if run "${fixtures}/no-change.json" "${fixtures}/no-change.json" /tmp/out.json /tmp/out.md >/dev/null 2>&1; then fail 'outside output accepted'; fi
ln -s "${root}" "${root}/link"
if run "${fixtures}/no-change.json" "${fixtures}/no-change.json" "${root}/link/x.json" "${root}/link/x.md" >/dev/null 2>&1; then fail 'symlink output accepted'; fi
cp "${root}/full.json" "${root}/tampered.json"; cp "${root}/full.md" "${root}/tampered.md"; python3 - "${root}/tampered.json" <<'PY'
import json,sys
p=sys.argv[1]; x=json.load(open(p)); x['summary']['review_level']='none'; open(p,'w').write(json.dumps(x,sort_keys=True,indent=2)+'\n')
PY
if python3 "${verify}" "${root}/tampered.json" "${root}/tampered.md" >/dev/null 2>&1; then fail 'review level tampering accepted'; fi
printf '%s\n' 'Runtime diff tests: PASS'
