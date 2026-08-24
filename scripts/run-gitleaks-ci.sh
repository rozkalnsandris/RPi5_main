#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(git rev-parse --show-toplevel)"

GITLEAKS_CONFIG=".gitleaks.toml"
[[ -f "$GITLEAKS_CONFIG" && ! -L "$GITLEAKS_CONFIG" ]] || {
  echo "Gitleaks CI: FAIL: missing regular policy file $GITLEAKS_CONFIG" >&2
  exit 1
}

# v8.18.4 is used as a known-good control: the upstream v8.30.1 regression
# report demonstrates this release detects the same canonical GitHub PAT shape
# that v8.30.1 missed. Our runtime canaries remain the final trust gate.
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

# Positive canary: deliberately assembled at runtime so no rule-matching
# token-shaped literal is committed. The repository policy must still detect it.
canary_dir="$tmp/canary"
mkdir -p "$canary_dir"
canary="ghp_""7Nq4Xv2Za9Lm5Rt8Pk3Hy6Wc1Bd0Fs9Gj4Ku"
printf 'token = "%s"\n' "$canary" >"$canary_dir/canary.txt"

set +e
"$tmp/gitleaks" detect \
  --no-git \
  --source "$canary_dir" \
  --config "$GITLEAKS_CONFIG" \
  --redact \
  --no-banner \
  --no-color \
  >"$tmp/canary.log" 2>&1
canary_rc=$?
set -e

[[ "$canary_rc" -eq 1 ]] || {
  echo "Gitleaks CI: FAIL: secret canary was not detected with repository policy" >&2
  exit 1
}
if grep -Fq "$canary" "$tmp/canary.log"; then
  echo "Gitleaks CI: FAIL: secret canary was not redacted" >&2
  exit 1
fi

echo "Gitleaks CI: secret canary PASS"

# Negative canary: this exact runtime metadata class is non-secret and must not
# make sanitized baseline evidence fail the history scan. Assemble the tag at
# runtime so the test itself does not create a committed scanner finding.
runtime_image_dir="$tmp/runtime-image"
mkdir -p "$runtime_image_dir"
runtime_image="hermes-deals-api:main-""a1b2c3d4e5f6"
printf 'image = "%s"\n' "$runtime_image" >"$runtime_image_dir/image.txt"

set +e
"$tmp/gitleaks" detect \
  --no-git \
  --source "$runtime_image_dir" \
  --config "$GITLEAKS_CONFIG" \
  --redact \
  --no-banner \
  --no-color \
  >"$tmp/runtime-image.log" 2>&1
runtime_image_rc=$?
set -e

[[ "$runtime_image_rc" -eq 0 ]] || {
  echo "Gitleaks CI: FAIL: runtime image false-positive canary was not allowlisted" >&2
  exit 1
}

echo "Gitleaks CI: runtime image false-positive canary PASS"

# Independently prove the complete history stream can be generated before
# asking this older known-good scanner to execute its own equivalent git-log
# scan. This prevents a broken repository/history invocation from being treated
# as a clean result.
git log -p --all --no-ext-diff --no-textconv -- . >/dev/null

"$tmp/gitleaks" detect \
  --source . \
  --config "$GITLEAKS_CONFIG" \
  --log-opts="--all --no-ext-diff --no-textconv" \
  --redact \
  --no-banner \
  --no-color

echo "Gitleaks CI: history scan PASS"
