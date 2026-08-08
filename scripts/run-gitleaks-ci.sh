#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(git rev-parse --show-toplevel)"

GITLEAKS_VERSION="8.30.0"
archive="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
release_base="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl_common=(--fail --location --silent --show-error --retry 3 --proto '=https' --tlsv1.2)

curl "${curl_common[@]}" "$release_base/$archive" -o "$tmp/$archive"
curl "${curl_common[@]}" "$release_base/gitleaks_${GITLEAKS_VERSION}_checksums.txt" -o "$tmp/checksums.txt"

grep -E "[[:space:]]${archive}$" "$tmp/checksums.txt" >"$tmp/checksum-one.txt" || {
  echo "Gitleaks CI: FAIL: pinned release checksum entry missing" >&2
  exit 1
}
(
  cd "$tmp"
  sha256sum -c checksum-one.txt >/dev/null
) || {
  echo "Gitleaks CI: FAIL: pinned release checksum mismatch" >&2
  exit 1
}

tar -xzf "$tmp/$archive" -C "$tmp" gitleaks
chmod 0700 "$tmp/gitleaks"

version="$($tmp/gitleaks version)"
[[ "$version" == "$GITLEAKS_VERSION" || "$version" == "v$GITLEAKS_VERSION" ]] || {
  echo "Gitleaks CI: FAIL: unexpected scanner version" >&2
  exit 1
}

# Canary: this value is deliberately assembled at runtime so the repository does
# not contain a rule-matching credential-shaped literal. A healthy scanner must
# reject it before the real history scan is trusted.
canary_dir="$tmp/canary"
mkdir -p "$canary_dir"
canary="ghp_""aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
printf 'token = "%s"\n' "$canary" >"$canary_dir/canary.txt"

set +e
"$tmp/gitleaks" dir --redact=100 --no-banner --no-color "$canary_dir" >"$tmp/canary.log" 2>&1
canary_rc=$?
set -e

[[ "$canary_rc" -eq 1 ]] || {
  echo "Gitleaks CI: FAIL: scanner canary was not detected" >&2
  exit 1
}
if grep -Fq "$canary" "$tmp/canary.log"; then
  echo "Gitleaks CI: FAIL: scanner canary was not fully redacted" >&2
  exit 1
fi

echo "Gitleaks CI: canary PASS"

# Stream the complete reachable history ourselves instead of trusting the
# scanner's internal git invocation. This also fails the pipeline if git log
# itself cannot produce the history stream.
git log -p --all --no-ext-diff --no-textconv -- . |
  "$tmp/gitleaks" stdin --redact=100 --no-banner --no-color

echo "Gitleaks CI: history scan PASS"
