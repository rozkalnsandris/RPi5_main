#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
OP="$ROOT/ops/bin/rpi5-main-git-index-owner-bootstrap"

fail() {
  echo "RPi5_main Git index bootstrap test: FAIL: $*" >&2
  exit 1
}

[[ -f "$OP" ]] || fail "bootstrap operator missing"
bash -n "$OP" || fail "bootstrap operator syntax"

text="$(cat "$OP")"

for required in \
  '--repo <absolute-checkout-path>' \
  'SUDO_UID' \
  'SUDO_GID' \
  'ref: refs/heads/main' \
  'index.lock exists; refuse repair' \
  'index must be a regular non-symlink file' \
  'repository owner does not match sudo caller' \
  'chown --no-dereference --from=' \
  'index mode changed' \
  'index size changed' \
  'index content changed' \
  'RPI5_MAIN_GIT_INDEX_BOOTSTRAP=PASS'
do
  grep -Fq -- "$required" <<<"$text" || fail "required contract missing: $required"
done

for forbidden in \
  'chown -R' \
  'chown --recursive' \
  'git status' \
  'git fetch' \
  'git merge' \
  'git reset' \
  'git push' \
  'git rebase' \
  'systemctl ' \
  'docker ' \
  'cloudflared' \
  'sqlite3 ' \
  'run_digests.sh'
do
  if grep -Fq -- "$forbidden" <<<"$text"; then
    fail "forbidden operation present: $forbidden"
  fi
done

# Guard the documented single-file scope: the only chown command must target INDEX.
chown_lines="$(grep -Ec '^[[:space:]]*chown[[:space:]]' "$OP")"
[[ "$chown_lines" -eq 1 ]] || fail "expected exactly one chown invocation"
grep -Eq 'chown .* -- "\$INDEX"$' "$OP" || fail "chown target is not exact index file"

# Hash, mode and size must be captured before chown and rechecked after it.
chown_line="$(grep -nE '^[[:space:]]*chown[[:space:]]' "$OP" | cut -d: -f1)"
first_hash_line="$(grep -n 'index_sha="' "$OP" | head -n1 | cut -d: -f1)"
post_hash_line="$(grep -n 'index content changed' "$OP" | cut -d: -f1)"
[[ "$first_hash_line" -lt "$chown_line" && "$post_hash_line" -gt "$chown_line" ]] || fail "hash preservation ordering is wrong"

echo "RPi5_main Git index bootstrap test: PASS"
