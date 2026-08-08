#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(git rev-parse --show-toplevel)"

fail=0
base="${PUBLIC_SAFETY_BASE:-}"

if [[ -n "$base" && "$base" =~ ^0+$ ]]; then
  base=""
fi

if [[ -n "$base" ]]; then
  git cat-file -e "$base^{commit}" 2>/dev/null || {
    echo "Public safety guard: FAIL: base commit is unavailable" >&2
    exit 2
  }
  diff_cmd=(git diff --no-color --unified=0 "$base...HEAD" -- .)
else
  diff_cmd=(git diff --no-color --unified=0 HEAD -- .)
fi

home_literal='/home/'"andris"'/'
lan_host_literal='192.168.'"0.180"
lan_cidr_literal='192.168.'"0.0/24"
bridge_literal='172.19.'"0.10"
tunnel_credential_literal='/etc/cloudflared/'"rpi5-tunnel.token"

report() {
  local path="$1" category="$2"
  printf 'Public safety guard: BLOCKED: %s [%s]\n' "$path" "$category" >&2
  fail=1
}

current_path=""
while IFS= read -r line; do
  case "$line" in
    '+++ b/'*)
      current_path="${line#+++ b/}"
      ;;
    '+++ /dev/null')
      current_path=""
      ;;
    +*)
      [[ "$line" == '+++'* ]] && continue
      [[ -n "$current_path" ]] || continue
      added="${line#+}"

      [[ "$added" == *"$home_literal"* ]] && report "$current_path" "user-home-path"
      [[ "$added" == *"$lan_host_literal"* ]] && report "$current_path" "private-lan-host"
      [[ "$added" == *"$lan_cidr_literal"* ]] && report "$current_path" "private-lan-cidr"
      [[ "$added" == *"$bridge_literal"* ]] && report "$current_path" "private-bridge-origin"
      [[ "$added" == *"$tunnel_credential_literal"* ]] && report "$current_path" "credential-path"

      if [[ "$added" =~ [A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,} ]]; then
        email="${BASH_REMATCH[0]}"
        case "$email" in
          *@users.noreply.github.com|*@example.com|*@example.org|*@example.net)
            ;;
          *)
            report "$current_path" "email-address"
            ;;
        esac
      fi
      ;;
  esac
done < <("${diff_cmd[@]}")

if (( fail != 0 )); then
  echo "Public safety guard: FAIL: remove the private value or use a neutral placeholder." >&2
  echo "Public safety guard never prints the matched value." >&2
  exit 1
fi

echo "Public safety guard: PASS"
