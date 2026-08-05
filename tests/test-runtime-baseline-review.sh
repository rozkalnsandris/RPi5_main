#!/usr/bin/env bash
set -Eeuo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
tmp="$(mktemp -d)"; real_out=""
trap 'rm -rf -- "$tmp" ${real_out:+"$real_out"}' EXIT

new_root() {
  local r="$1"
  mkdir -p "$r"/{baselines/runtime/archive,docs,evidence,fixtures}
  cp "$repo"/tests/fixtures/runtime-review/*.json "$r/fixtures/"
  cp "$r/fixtures/current.json" "$r/baselines/runtime/current.json"
  printf '# Runtime baseline archive\n' > "$r/baselines/runtime/archive/README.md"
  printf '%s\n' '{"entries":[],"schema":"rpi5.runtime-baseline-archive-index.v1"}' | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin),sort_keys=True,indent=2))' > "$r/baselines/runtime/archive/index.json"
  RPI5_REVIEW_TEST_ROOT="$r" python3 "$repo/scripts/runtime-baseline-document.py" "$r/baselines/runtime/current.json" > "$r/docs/CURRENT_RUNTIME_BASELINE.md"
}
prepare() {
  local r="$1" candidate="$2" output="$3"
  RPI5_REVIEW_TEST_ROOT="$r" python3 "$repo/scripts/prepare-runtime-baseline-review.py" --current "$r/baselines/runtime/current.json" --candidate "$candidate" --output "$output" | head -n1
}

python3 "$repo/scripts/runtime-baseline-document.py" "$repo/baselines/runtime/current.json" > "$tmp/current.md"
cmp "$tmp/current.md" "$repo/docs/CURRENT_RUNTIME_BASELINE.md"
echo "V04 current JSON SHA256=$(sha256sum "$repo/baselines/runtime/current.json" | awk '{print $1}')"
echo "V04 current Markdown SHA256=$(sha256sum "$repo/docs/CURRENT_RUNTIME_BASELINE.md" | awk '{print $1}')"

r="$tmp/repo"; new_root "$r"; export RPI5_REVIEW_TEST_ROOT="$r"
none="$(prepare "$r" "$r/fixtures/candidate-none.json" "$r/evidence/none")"
info="$(prepare "$r" "$r/fixtures/candidate-informational.json" "$r/evidence/info")"
attention="$(prepare "$r" "$r/fixtures/candidate-attention.json" "$r/evidence/attention")"
for pair in "$none:none" "$info:informational" "$attention:attention"; do
  dir="${pair%:*}"; level="${pair##*:}"
  python3 "$repo/scripts/verify-runtime-baseline-review.py" "$dir"
  python3 - "$dir/review.json" "$level" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['diff']['review_level']==sys.argv[2]
PY
done

python3 "$repo/scripts/record-runtime-baseline-decision.py" --review "$none" --decision deferred --reason no_second_snapshot --reviewer tester --decided-at 2099-02-02T00:00:00Z
sha="$(sha256sum "$r/baselines/runtime/current.json" | awk '{print $1}')"
! python3 "$repo/scripts/apply-runtime-baseline-promotion.py" --review "$none" --candidate "$r/fixtures/candidate-none.json" --expected-current-sha256 "$sha"
test "$(sha256sum "$r/baselines/runtime/current.json" | awk '{print $1}')" = "$sha"

python3 "$repo/scripts/record-runtime-baseline-decision.py" --review "$attention" --decision accepted --reason expected_change --reviewer tester --decided-at 2099-04-02T00:00:00Z
python3 "$repo/scripts/apply-runtime-baseline-promotion.py" --review "$attention" --candidate "$r/fixtures/candidate-attention.json" --expected-current-sha256 "$sha"
cmp "$r/baselines/runtime/current.json" "$r/fixtures/candidate-attention.json"
python3 "$repo/scripts/verify-runtime-baseline-archive.py"

cp "$r/fixtures/candidate-attention.json" "$r/fixtures/noncanonical.json"
python3 - "$r/fixtures/noncanonical.json" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p)); open(p,'w').write(json.dumps(d))
PY
! python3 "$repo/scripts/prepare-runtime-baseline-review.py" --current "$r/baselines/runtime/current.json" --candidate "$r/fixtures/noncanonical.json" --output "$r/evidence/bad"
cp "$info/review.json" "$tmp/review.backup"; printf '\n' >> "$info/review.json"
! python3 "$repo/scripts/verify-runtime-baseline-review.py" "$info" >"$tmp/out" 2>"$tmp/err"
grep -q FAIL "$tmp/err"; mv "$tmp/review.backup" "$info/review.json"

unset RPI5_REVIEW_TEST_ROOT
real_out="$repo/evidence/v04-test-$$"
real_review="$(python3 "$repo/scripts/prepare-runtime-baseline-review.py" --current "$repo/baselines/runtime/current.json" --candidate "$repo/baselines/runtime/current.json" --output "$real_out" | head -n1)"
python3 "$repo/scripts/record-runtime-baseline-decision.py" --review "$real_review" --decision deferred --reason no_second_snapshot --reviewer rozkalnsandris --decided-at 2026-08-05T00:00:00Z
python3 "$repo/scripts/verify-runtime-baseline-review.py" "$real_review"
real_sha="$(sha256sum "$repo/baselines/runtime/current.json" | awk '{print $1}')"
! python3 "$repo/scripts/apply-runtime-baseline-promotion.py" --review "$real_review" --candidate "$repo/baselines/runtime/current.json" --expected-current-sha256 "$real_sha"
test "$(sha256sum "$repo/baselines/runtime/current.json" | awk '{print $1}')" = "$real_sha"

echo "V04 runtime baseline review tests: PASS"
