#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
REPAIR="$ROOT/ops/bin/rpi5-main-git-index-owner-repair"
SAFE="$ROOT/ops/bin/hermes-tech-http-policy-v20-retry-safe"
RETRY="$ROOT/ops/bin/hermes-tech-http-policy-v20-retry"

fail() {
  echo "Hermes Tech V20 Git ownership regression: FAIL: $*" >&2
  exit 1
}

for f in "$REPAIR" "$SAFE" "$RETRY"; do
  [[ -f "$f" ]] || fail "missing file: $f"
  bash -n "$f" || fail "syntax failure: $f"
done

repair_text="$(cat "$REPAIR")"
safe_text="$(cat "$SAFE")"

for required in \
  'REPO="$(cd "$(dirname "$SCRIPT_PATH")/../.." && pwd -P)"' \
  'INDEX="$GIT_DIR/index"' \
  '[[ ! -e "$LOCK" ]]' \
  '[[ "$index_uid" -eq 0 ]]' \
  'chown --no-dereference "$repo_uid:$repo_gid" "$INDEX"' \
  '"$(stat -c '\''%a'\'' "$INDEX")" == "$index_mode"' \
  '"$(sha_of "$INDEX")" == "$index_sha"' \
  'RPI5_MAIN_GIT_INDEX_OWNER_REPAIR=PASS'
do
  grep -Fq -- "$required" <<<"$repair_text" || fail "repair contract missing: $required"
done

for forbidden in \
  'chown -R' \
  'chown --recursive' \
  'git fetch' \
  'git merge' \
  'git reset' \
  'git push' \
  'git rebase' \
  'systemctl restart' \
  'docker '
do
  if grep -Fq -- "$forbidden" <<<"$repair_text"; then
    fail "repair script contains forbidden mutation: $forbidden"
  fi
done

for required in \
  'runuser -u "$repo_owner" -- /usr/bin/git' \
  'export GIT_OPTIONAL_LOCKS=0' \
  'export PATH="$shim_dir:$PATH"' \
  'Git index ownership is not repaired' \
  'bash "$RETRY" "$MODE" --expected-sha "$EXPECTED_SHA"'
do
  grep -Fq -- "$required" <<<"$safe_text" || fail "safe retry contract missing: $required"
done

if grep -Fq 'git -c "safe.directory=$REPO"' <<<"$safe_text"; then
  fail "safe wrapper must not inspect checkout as root"
fi
if grep -Eq '(^|[;&|[:space:]])chown[[:space:]]' <<<"$safe_text"; then
  fail "safe retry wrapper must not repair ownership implicitly"
fi
if grep -Eiq 'systemctl[[:space:]]+(restart|reload|stop|start)[[:space:]]+cloudflared' <<<"$safe_text"; then
  fail "safe wrapper contains cloudflared lifecycle mutation"
fi

echo "Hermes Tech V20 Git ownership regression: PASS"
