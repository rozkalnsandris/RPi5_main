#!/usr/bin/env bash

gitleaks_container_version() {
  printf '%s\n' "8.18.4"
}

gitleaks_container_image() {
  printf '%s\n' "ghcr.io/gitleaks/gitleaks@sha256:75bdb2b2f4db213cde0b8295f13a88d6b333091bbfbf3012a4e083d00d31caba"
}

gitleaks_history_revision() {
  printf '%s\n' "HEAD"
}

require_complete_head_history() {
  local shallow
  shallow="$(git rev-parse --is-shallow-repository 2>/dev/null)" || return 1
  [[ "$shallow" == "false" ]] || return 1
  git rev-parse --verify 'HEAD^{commit}' >/dev/null 2>&1
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

set -Eeuo pipefail

cd "$(git rev-parse --show-toplevel)"

if ! require_complete_head_history; then
  echo "Gitleaks CI: FAIL: complete HEAD history is required" >&2
  exit 1
fi
history_revision="$(gitleaks_history_revision)"

GITLEAKS_CONFIG=".gitleaks.toml"
[[ -f "$GITLEAKS_CONFIG" && ! -L "$GITLEAKS_CONFIG" ]] || {
  echo "Gitleaks CI: FAIL: missing regular policy file $GITLEAKS_CONFIG" >&2
  exit 1
}

# v8.18.4 remains the known-good control: the upstream v8.30.1 regression
# report demonstrates this release detects the same canonical GitHub PAT shape
# that v8.30.1 missed. Pull the official multi-arch GHCR image by immutable
# digest rather than downloading a release asset during every CI run.
GITLEAKS_VERSION="$(gitleaks_container_version)"
GITLEAKS_IMAGE="$(gitleaks_container_image)"

command -v docker >/dev/null 2>&1 || {
  echo "Gitleaks CI: FAIL: docker is required on this GitHub-hosted Ubuntu job" >&2
  exit 1
}

docker pull "$GITLEAKS_IMAGE" >/dev/null

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

run_gitleaks() {
  docker run --rm --network=none \
    --env GIT_CONFIG_COUNT=1 \
    --env GIT_CONFIG_KEY_0=safe.directory \
    --env GIT_CONFIG_VALUE_0=/repo \
    --mount "type=bind,source=$PWD,target=/repo,readonly" \
    --mount "type=bind,source=$tmp,target=/work,readonly" \
    --workdir /repo \
    "$GITLEAKS_IMAGE" "$@"
}

version="$(docker run --rm --network=none "$GITLEAKS_IMAGE" version)"
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
run_gitleaks detect \
  --no-git \
  --source /work/canary \
  --config /repo/$GITLEAKS_CONFIG \
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
run_gitleaks detect \
  --no-git \
  --source /work/runtime-image \
  --config /repo/$GITLEAKS_CONFIG \
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
# asking this known-good scanner to execute its own equivalent git-log scan.
git log -p "$history_revision" --no-ext-diff --no-textconv -- . >/dev/null

run_gitleaks detect \
  --source /repo \
  --config /repo/$GITLEAKS_CONFIG \
  --log-opts="$history_revision --no-ext-diff --no-textconv" \
  --redact \
  --no-banner \
  --no-color

echo "Gitleaks CI: history scan PASS"
