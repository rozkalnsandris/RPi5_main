#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git rev-parse --show-toplevel)"
guard="$repo_root/scripts/check-public-safety.sh"

fail() {
  echo "Public safety guard test: FAIL: $*" >&2
  exit 1
}

[[ -f "$guard" ]] || fail "guard missing"
bash -n "$guard" || fail "guard syntax invalid"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
git -C "$tmp" config user.name test
git -C "$tmp" config user.email test@example.com
printf 'safe\n' >"$tmp/note.txt"
git -C "$tmp" add note.txt
git -C "$tmp" commit -qm base
base="$(git -C "$tmp" rev-parse HEAD)"

commit_value() {
  local value="$1"
  printf '%s\n' "$value" >"$tmp/leak.txt"
  git -C "$tmp" add leak.txt
  git -C "$tmp" commit -qm test
}

reset_case() {
  git -C "$tmp" reset --hard -q "$base"
  rm -f "$tmp/leak.txt"
}

lan_value="192.168.""0.180"
commit_value "$lan_value"
set +e
output="$(cd "$tmp" && PUBLIC_SAFETY_BASE="$base" "$guard" 2>&1)"
rc=$?
set -e
[[ "$rc" -ne 0 ]] || fail "private LAN host was accepted"
[[ "$output" == *'leak.txt [private-lan-host]'* ]] || fail "LAN category/path missing"
[[ "$output" != *"$lan_value"* ]] || fail "LAN value leaked in guard output"
reset_case

home_value="/home/""andris""/private/file"
commit_value "$home_value"
set +e
output="$(cd "$tmp" && PUBLIC_SAFETY_BASE="$base" "$guard" 2>&1)"
rc=$?
set -e
[[ "$rc" -ne 0 ]] || fail "user home path was accepted"
[[ "$output" == *'leak.txt [user-home-path]'* ]] || fail "home-path category/path missing"
[[ "$output" != *"$home_value"* ]] || fail "home path leaked in guard output"
reset_case

email_value="person@""private.invalid"
commit_value "$email_value"
set +e
output="$(cd "$tmp" && PUBLIC_SAFETY_BASE="$base" "$guard" 2>&1)"
rc=$?
set -e
[[ "$rc" -ne 0 ]] || fail "email address was accepted"
[[ "$output" == *'leak.txt [email-address]'* ]] || fail "email category/path missing"
[[ "$output" != *"$email_value"* ]] || fail "email value leaked in guard output"
reset_case

printf '%s\n' '$LAN_IP $LAN_CIDR $TECH_PUBLIC_DIR $ORIGIN_PORT' >"$tmp/note.txt"
git -C "$tmp" add note.txt
git -C "$tmp" commit -qm placeholders
(cd "$tmp" && PUBLIC_SAFETY_BASE="$base" "$guard") >/dev/null || fail "neutral placeholders were rejected"

echo "Public safety guard test: PASS"
