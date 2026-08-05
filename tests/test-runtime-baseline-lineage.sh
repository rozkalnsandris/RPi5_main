#!/usr/bin/env bash
set -Eeuo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
verify="${repo}/scripts/verify-runtime-baseline-lineage.py"
fixtures="${repo}/tests/fixtures/runtime-review"
root="$(mktemp -d "${repo}/evidence/test-runtime-lineage.XXXXXX")"
real_out=""
trap 'rm -rf -- "$root" ${real_out:+"$real_out"}' EXIT

fail() {
  printf 'test-runtime-baseline-lineage: FAIL: %s\n' "$1" >&2
  exit 1
}

mkdir -p "$root"/{baselines/runtime/archive,docs,evidence,fixtures}
cp "$fixtures"/*.json "$root/fixtures/"
cp "$root/fixtures/current.json" "$root/baselines/runtime/current.json"
printf '# Runtime baseline archive\n' > "$root/baselines/runtime/archive/README.md"
printf '%s\n' '{"entries":[],"schema":"rpi5.runtime-baseline-archive-index.v1"}' \
  | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin),sort_keys=True,indent=2))' \
  > "$root/baselines/runtime/archive/index.json"
RPI5_REVIEW_TEST_ROOT="$root" python3 "$repo/scripts/runtime-baseline-document.py" \
  "$root/baselines/runtime/current.json" > "$root/docs/CURRENT_RUNTIME_BASELINE.md"

export RPI5_REVIEW_TEST_ROOT="$root"
python3 "$verify" \
  --json-out "$root/evidence/empty-one.json" \
  --markdown-out "$root/evidence/empty-one.md" >/dev/null
python3 "$verify" \
  --json-out "$root/evidence/empty-two.json" \
  --markdown-out "$root/evidence/empty-two.md" >/dev/null
cmp "$root/evidence/empty-one.json" "$root/evidence/empty-two.json" || fail 'empty lineage JSON is non-deterministic'
cmp "$root/evidence/empty-one.md" "$root/evidence/empty-two.md" || fail 'empty lineage Markdown is non-deterministic'
python3 - "$root/evidence/empty-one.json" <<'PY'
import json,sys
report=json.load(open(sys.argv[1]))
assert report['schema']=='rpi5.runtime-baseline-lineage.v1'
assert report['entry_count']==0
assert report['root']==report['head']
assert report['transitions']==[]
assert all(report['checks'].values())
PY

review="$({
  python3 "$repo/scripts/prepare-runtime-baseline-review.py" \
    --current "$root/baselines/runtime/current.json" \
    --candidate "$root/fixtures/candidate-attention.json" \
    --output "$root/evidence/review"
} | head -n1)"
python3 "$repo/scripts/record-runtime-baseline-decision.py" \
  --review "$review" \
  --decision accepted \
  --reason expected_change \
  --reviewer tester \
  --decided-at 2099-04-02T00:00:00Z >/dev/null
current_sha="$(sha256sum "$root/baselines/runtime/current.json" | awk '{print $1}')"
python3 "$repo/scripts/apply-runtime-baseline-promotion.py" \
  --review "$review" \
  --candidate "$root/fixtures/candidate-attention.json" \
  --expected-current-sha256 "$current_sha" >/dev/null
python3 "$verify" \
  --json-out "$root/evidence/promoted.json" \
  --markdown-out "$root/evidence/promoted.md" >/dev/null
python3 - "$root/evidence/promoted.json" "$root/baselines/runtime/current.json" <<'PY'
import hashlib,json,pathlib,sys
report=json.load(open(sys.argv[1]))
current=pathlib.Path(sys.argv[2])
assert report['entry_count']==1
assert len(report['transitions'])==1
assert report['head']['sha256']==hashlib.sha256(current.read_bytes()).hexdigest()
assert report['root']['sha256']==report['transitions'][0]['old']['sha256']
assert report['head']==report['transitions'][0]['new']
PY

python3 - "$repo/scripts/runtime_baseline_lineage.py" <<'PY'
import importlib.util,sys
spec=importlib.util.spec_from_file_location('lineage',sys.argv[1]); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

def binding(char,utc):
    return {
        'sha256':char*64,
        'collection_utc':utc,
        'source_commit':char*40,
        'evidence_manifest_sha256':char*64,
        'context':'fixture',
    }

def pair(old,new,number):
    entry={
        'entry_id':f'entry-{number}',
        'old_collection_utc':old['collection_utc'],
        'old_sha256':old['sha256'],
        'new_collection_utc':new['collection_utc'],
        'new_sha256':new['sha256'],
        'review_id':f'review-{number}',
        'decision':'accepted',
        'review_level':'informational',
        'transition_sha256':str(number)*64,
    }
    transition={
        'schema':'rpi5.runtime-baseline-transition.v1',
        'entry_id':entry['entry_id'],
        'old':old,
        'new':new,
        'review_id':entry['review_id'],
        'decision':'accepted',
        'review_level':'informational',
        'diff_json_sha256':'d'*64,
        'diff_markdown_sha256':'e'*64,
        'archive_checksums':{},
    }
    return entry,transition

a=binding('a','2099-01-01T00:00:00Z')
b=binding('b','2099-01-02T00:00:00Z')
c=binding('c','2099-01-03T00:00:00Z')
e1,t1=pair(a,b,1); e2,t2=pair(b,c,2)
result=module.validate_chain([e1,e2],[t1,t2],c)
assert result['root']==a and result['head']==c and len(result['transitions'])==2

cases=[]
gap=dict(t2); gap['old']=dict(a); cases.append(([e1,e2],[t1,gap],c))
timegap=dict(t2); timegap['old']=dict(b); timegap['old']['collection_utc']='2099-01-01T12:00:00Z'; cases.append(([e1,e2],[t1,timegap],c))
metagap=dict(t2); metagap['old']=dict(b); metagap['old']['source_commit']='f'*40; cases.append(([e1,e2],[t1,metagap],c))
cycle_entry,cycle_transition=pair(b,a,3); cases.append(([e1,cycle_entry],[t1,cycle_transition],a))
dup_entry=dict(e2); dup_entry['review_id']=e1['review_id']; dup_transition=dict(t2); dup_transition['review_id']=e1['review_id']; cases.append(([e1,dup_entry],[t1,dup_transition],c))
cases.append(([e1],[t1],a))
for entries,transitions,head in cases:
    try:
        module.validate_chain(entries,transitions,head)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid lineage accepted')
PY

cp "$root/baselines/runtime/current.json" "$root/current.saved"
cp "$root/docs/CURRENT_RUNTIME_BASELINE.md" "$root/current-md.saved"
cp "$root/fixtures/current.json" "$root/baselines/runtime/current.json"
RPI5_REVIEW_TEST_ROOT="$root" python3 "$repo/scripts/runtime-baseline-document.py" \
  "$root/baselines/runtime/current.json" > "$root/docs/CURRENT_RUNTIME_BASELINE.md"
if python3 "$verify" >/dev/null 2>&1; then fail 'lineage head mismatch accepted'; fi
mv "$root/current.saved" "$root/baselines/runtime/current.json"
mv "$root/current-md.saved" "$root/docs/CURRENT_RUNTIME_BASELINE.md"

printf '\n' >> "$root/docs/CURRENT_RUNTIME_BASELINE.md"
if python3 "$verify" >/dev/null 2>&1; then fail 'current Markdown mismatch accepted'; fi
RPI5_REVIEW_TEST_ROOT="$root" python3 "$repo/scripts/runtime-baseline-document.py" \
  "$root/baselines/runtime/current.json" > "$root/docs/CURRENT_RUNTIME_BASELINE.md"

if python3 "$verify" --json-out /tmp/v07-lineage.json --markdown-out /tmp/v07-lineage.md >/dev/null 2>&1; then
  fail 'outside lineage outputs accepted'
fi
if python3 "$verify" --json-out "$root/evidence/only.json" >/dev/null 2>&1; then
  fail 'single lineage output accepted'
fi
mkdir -p "$root/evidence/real"
ln -s "$root/evidence/real" "$root/evidence/link"
if python3 "$verify" --json-out "$root/evidence/link/x.json" --markdown-out "$root/evidence/link/x.md" >/dev/null 2>&1; then
  fail 'symlink lineage output accepted'
fi

unset RPI5_REVIEW_TEST_ROOT
if [[ -f "$repo/baselines/runtime/current.json" ]]; then
  real_out="$repo/evidence/v07-lineage-test-$$"
  mkdir -p "$real_out"
  rmdir "$real_out"
  python3 "$verify" \
    --json-out "$real_out/lineage.json" \
    --markdown-out "$real_out/lineage.md" >/dev/null
  python3 - "$real_out/lineage.json" "$repo/baselines/runtime/current.json" <<'PY'
import hashlib,json,pathlib,sys
report=json.load(open(sys.argv[1])); current=pathlib.Path(sys.argv[2])
assert report['entry_count']>=1
assert report['head']['sha256']==hashlib.sha256(current.read_bytes()).hexdigest()
assert all(report['checks'].values())
PY
fi

printf '%s\n' 'Runtime baseline lineage tests: PASS'
