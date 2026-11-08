#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(git rev-parse --show-toplevel)"
source ./scripts/run-gitleaks-ci.sh

expected_version="8.18.4"
expected_image="ghcr.io/gitleaks/gitleaks@sha256:75bdb2b2f4db213cde0b8295f13a88d6b333091bbfbf3012a4e083d00d31caba"

[[ "$(gitleaks_container_version)" == "$expected_version" ]] || {
  echo "Gitleaks container pin test: FAIL: version pin mismatch" >&2
  exit 1
}
[[ "$(gitleaks_container_image)" == "$expected_image" ]] || {
  echo "Gitleaks container pin test: FAIL: image digest pin mismatch" >&2
  exit 1
}

grep -Fq 'docker pull "$GITLEAKS_IMAGE"' ./scripts/run-gitleaks-ci.sh || {
  echo "Gitleaks container pin test: FAIL: pinned image pull missing" >&2
  exit 1
}
grep -Fq -- '--network=none' ./scripts/run-gitleaks-ci.sh || {
  echo "Gitleaks container pin test: FAIL: scanner container network isolation missing" >&2
  exit 1
}
grep -Fq 'target=/repo,readonly' ./scripts/run-gitleaks-ci.sh || {
  echo "Gitleaks container pin test: FAIL: repository mount is not read-only" >&2
  exit 1
}
grep -Fq 'GIT_CONFIG_KEY_0=safe.directory' ./scripts/run-gitleaks-ci.sh || {
  echo "Gitleaks container pin test: FAIL: safe.directory binding missing" >&2
  exit 1
}

for forbidden in   'github.com/gitleaks/gitleaks/releases/download'   'curl_common='   'tar -xzf'   'gitleaks_release_archive_sha256'   'resolve_gitleaks_release_arch'
do
  if grep -Fq "$forbidden" ./scripts/run-gitleaks-ci.sh; then
    echo "Gitleaks container pin test: FAIL: legacy release-asset path remains: $forbidden" >&2
    exit 1
  fi
done

echo "Gitleaks container pin test: PASS ($expected_version / immutable GHCR digest)"
