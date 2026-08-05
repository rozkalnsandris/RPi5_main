#!/usr/bin/env bash
set -Eeuo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
troot="$tmp/repo"
mkdir -p "$troot"/{baselines/runtime/archive,docs,evidence,fixtures}
cp "$repo"/tests/fixtures/runtime-review/*.json "$troot/fixtures/"
cp "$troot/fixtures/current.json" "$troot/baselines/runtime/current.json"
printf '# Runtime baseline archive\n\nAccepted prior baselines are stored here only through the V04 review workflow.\n' > "$troot/baselines/runtime/archive/README.md"
printf '%s\n' '{"entries":[],"schema":"rpi5.runtime-baseline-archive-index.v1"}' | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin),sort_keys=True,indent=2))' > "$troot/baselines/runtime/archive/index.json"
export RPI5_REVIEW_TEST_ROOT="$troot"
python3 "$repo/scripts/runtime-baseline-document.py" "$troot/baselines/runtime/current.json" > "$troot/docs/CURRENT_RUNTIME_BASELINE.md"

rendered="$tmp/current.md"
python3 "$repo/scripts/runtime-baseline-document.py" "$repo/baselines/runtime/current.json" > "$rendered"
cmp "$rendered" "$repo/docs/CURRENT_RUNTIME_BASELINE.md"
echo "V04 current JSON SHA256=$(sha256sum "$repo/baselines/runtime/current.json" | awk '{print $1}')"
echo "V04 current Markdown SHA256=$(sha256sum "$repo/docs/CURRENT_RUNTIME_BASELINE.md" | awk '{print $1}')"

out="$(python3 "$repo/scripts/prepare-runtime-baseline-review.py" --current "$troot/baselines/runtime/current.json" --candidate "$troot/fixtures/candidate-none.json" --output "$troot/evidence/none")"
review_none="$(printf '%s\n' "$out" | head -n1)"
python3 "$repo/scripts/verify-runtime-baseline-review.py" "$review_none"
python3 - "$review_none/review.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r["diff"]["review_level"]=="none"
assert r["candidate_newer"] is True
PY
python3 "$repo/scripts/record-runtime-baseline-decision.py" --review "$review_none" --decision deferred --reason no_second_snapshot --reviewer tester --decided-at 2099-02-02T00:00:00Z
python3 "$repo/scripts/verify-runtime-baseline-review.py" "$review_none"
sha="$(sha256sum "$troot/baselines/runtime/current.json" | awk '{print $1}')"
if python3 "$repo/scripts/apply-runtime-baseline-promotion.py" --review "$review_none" --candidate "$troot/fixtures/candidate-none.json" --expected-current-sha256 "$sha"; then
  echo "deferred promotion unexpectedly succeeded" >&2; exit 1
fi
test "$(sha256sum "$troot/baselines/runtime/current.json" | awk '{print $1}')" = "$sha"

out="$(python3 "$repo/scripts/prepare-runtime-baseline-review.py" --current "$troot/baselines/runtime/current.json" --candidate "$troot/fixtures/candidate-informational.json" --output "$troot/evidence/info")"
review_info="$(printf '%s\n' "$out" | head -n1)"
python3 "$repo/scripts/verify-runtime-baseline-review.py" "$review_info"
python3 - "$review_info/review.json" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))["diff"]["review_level"]=="informational"
PY
out="$(python3 "$repo/scripts/prepare-runtime-baseline-review.py" --current "$troot/baselines/runtime/current.json" --candidate "$troot/fixtures/candidate-attention.json" --output "$troot/evidence/attention")"
review_attention="$(printf '%s\n' "$out" | head -n1)"
python3 "$repo/scripts/verify-runtime-baseline-review.py" "$review_attention"
python3 "$repo/scripts/record-runtime-baseline-decision.py" --review "$review_attention" --decision accepted --reason expected_change --reviewer tester --decided-at 2099-04-02T00:00:00Z
python3 "$repo/scripts/apply-runtime-baseline-promotion.py" --review "$review_attention" --candidate "$troot/fixtures/candidate-attention.json" --expected-current-sha256 "$sha"
cmp "$troot/baselines/runtime/current.json" "$troot/fixtures/candidate-attention.json"
python3 "$repo/scripts/runtime-baseline-document.py" "$troot/baselines/runtime/current.json" > "$tmp/promoted.md"
cmp "$tmp/promoted.md" "$troot/docs/CURRENT_RUNTIME_BASELINE.md"
python3 "$repo/scripts/verify-runtime-baseline-archive.py"

cp "$troot/fixtures/candidate-attention.json" "$tmp/noncanonical.json"
python3 - "$tmp/noncanonical.json" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p)); open(p,"w").write(json.dumps(d))
PY
if python3 "$repo/scripts/prepare-runtime-baseline-review.py" --current "$troot/baselines/runtime/current.json" --candidate "$tmp/noncanonical.json" --output "$troot/evidence/bad"; then
  echo "noncanonical candidate unexpectedly accepted" >&2; exit 1
fi

troot2="$tmp/repo2"
mkdir -p "$troot2"/{baselines/runtime/archive,docs,evidence}
cp "$repo/tests/fixtures/runtime-review/current.json" "$troot2/baselines/runtime/current.json"
cp "$troot/baselines/runtime/archive/README.md" "$troot2/baselines/runtime/archive/README.md"
printf '%s\n' '{"entries":[],"schema":"rpi5.runtime-baseline-archive-index.v1"}' | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin),sort_keys=True,indent=2))' > "$troot2/baselines/runtime/archive/index.json"
RPI5_REVIEW_TEST_ROOT="$troot2" python3 "$repo/scripts/runtime-baseline-document.py" "$troot2/baselines/runtime/current.json" > "$troot2/docs/CURRENT_RUNTIME_BASELINE.md"
out="$(RPI5_REVIEW_TEST_ROOT="$troot2" python3 "$repo/scripts/prepare-runtime-baseline-review.py" --current "$troot2/baselines/runtime/current.json" --candidate "$troot2/baselines/runtime/current.json" --output "$troot2/evidence/self")"
self_review="$(printf '%s\n' "$out" | head -n1)"
if RPI5_REVIEW_TEST_ROOT="$troot2" python3 "$repo/scripts/record-runtime-baseline-decision.py" --review "$self_review" --decision accepted --reason no_change_refresh --reviewer tester --decided-at 2099-01-02T00:00:00Z; then
  echo "identical accepted decision unexpectedly succeeded" >&2; exit 1
fi
RPI5_REVIEW_TEST_ROOT="$troot2" python3 "$repo/scripts/verify-runtime-baseline-archive.py"

cp "$review_info/review.json" "$tmp/review.backup"
printf '\n' >> "$review_info/review.json"
if python3 "$repo/scripts/verify-runtime-baseline-review.py" "$review_info" >"$tmp/out" 2>"$tmp/err"; then
  echo "tampered review unexpectedly verified" >&2; exit 1
fi
grep -q 'FAIL' "$tmp/err"
mv "$tmp/review.backup" "$review_info/review.json"

unset RPI5_REVIEW_TEST_ROOT
real_out="$repo/evidence/v04-test-$$"
trap 'rm -rf -- "$tmp" "$real_out"' EXIT
out="$(python3 "$repo/scripts/prepare-runtime-baseline-review.py" --current "$repo/baselines/runtime/current.json" --candidate "$repo/baselines/runtime/current.json" --output "$real_out")"
real_review="$(printf '%s\n' "$out" | head -n1)"
python3 "$repo/scripts/verify-runtime-baseline-review.py" "$real_review"
python3 "$repo/scripts/record-runtime-baseline-decision.py" --review "$real_review" --decision deferred --reason no_second_snapshot --reviewer rozkalnsandris --decided-at 2026-08-05T00:00:00Z
python3 "$repo/scripts/verify-runtime-baseline-review.py" "$real_review"
real_sha="$(sha256sum "$repo/baselines/runtime/current.json" | awk '{print $1}')"
if python3 "$repo/scripts/apply-runtime-baseline-promotion.py" --review "$real_review" --candidate "$repo/baselines/runtime/current.json" --expected-current-sha256 "$real_sha"; then
  echo "real deferred self-review unexpectedly promoted" >&2; exit 1
fi
test "$(sha256sum "$repo/baselines/runtime/current.json" | awk '{print $1}')" = "$real_sha"
rm -rf -- "$real_out"

echo "V04 runtime baseline review tests: PASS"
