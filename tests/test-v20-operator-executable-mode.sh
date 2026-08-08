#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"

fail() {
  echo "V20 production operator executable-mode test: FAIL: $*" >&2
  exit 1
}

operators=(
  ops/bin/hermes-tech-http-policy-v20
  ops/bin/hermes-tech-http-policy-v20-retry
  ops/bin/hermes-tech-http-policy-v20-retry-safe
  ops/bin/rpi5-main-git-index-owner-repair
  ops/bin/rpi5-main-git-index-owner-bootstrap
)

for path in "${operators[@]}"; do
  [[ -f "$path" ]] || fail "missing operator: $path"
  [[ "$(head -n1 "$path")" == '#!/usr/bin/env bash' ]] || fail "unexpected shebang: $path"
  mode="$(git ls-files --stage -- "$path" | awk 'NR == 1 { print $1 }')"
  [[ "$mode" == "100755" ]] || fail "$path mode=$mode expected=100755"
done

echo "V20 production operator executable-mode test: PASS"
