#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(git rev-parse --show-toplevel)"

# v8.18.4 is used as a known-good control: the upstream v8.30.1 regression
# report demonstrates this release detects the same canonical GitHub PAT shape
# that v8.30.1 missed. Our runtime canary remains the final trust gate.
GITLEAKS_VERSION="8.18.4"
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

# Canary: deliberately assembled at runtime so no rule-matching token-shaped
# literal is committed to the repository. A healthy scanner must reject it.
canary_dir="$tmp/canary"
mkdir -p "$canary_dir"
canary="ghp_""7Nq4Xv2Za9Lm5Rt8Pk3Hy6Wc1Bd0Fs9Gj4Ku"
printf 'token = "%s"\n' "$canary" >"$canary_dir/canary.txt"

set +e
"$tmp/gitleaks" detect --no-git --source "$canary_dir" --redact --no-banner --no-color >"$tmp/canary.log" 2>&1
canary_rc=$?
set -e

[[ "$canary_rc" -eq 1 ]] || {
  echo "Gitleaks CI: FAIL: scanner canary was not detected" >&2
  exit 1
}
if grep -Fq "$canary" "$tmp/canary.log"; then
  echo "Gitleaks CI: FAIL: scanner canary was not redacted" >&2
  exit 1
fi

echo "Gitleaks CI: canary PASS"

# Independently prove the complete history stream can be generated before
# asking this older known-good scanner to execute its own equivalent git-log
# scan. This prevents a broken repository/history invocation from being treated
# as a clean result.
git log -p --all --no-ext-diff --no-textconv -- . >/dev/null

"$tmp/gitleaks" detect \
  --source . \
  --log-opts="--all --no-ext-diff --no-textconv" \
  --redact \
  --no-banner \
  --no-color

echo "Gitleaks CI: history scan PASS"
