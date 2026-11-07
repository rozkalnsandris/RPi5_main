#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(git rev-parse --show-toplevel)"
source ./scripts/run-gitleaks-ci.sh

assert_arch() {
  local machine="$1"
  local expected="$2"
  local actual
  actual="$(resolve_gitleaks_release_arch "$machine")"
  [[ "$actual" == "$expected" ]] || {
    echo "Gitleaks architecture test: FAIL: $machine resolved to $actual, expected $expected" >&2
    exit 1
  }
}

assert_arch x86_64 x64
assert_arch amd64 x64
assert_arch aarch64 arm64
assert_arch arm64 arm64

[[ "$(gitleaks_release_archive_sha256 x64)" == "ba6dbb656933921c775ee5a2d1c13a91046e7952e9d919f9bac4cec61d628e7d" ]] || {
  echo "Gitleaks architecture test: FAIL: x64 checksum pin mismatch" >&2
  exit 1
}
[[ "$(gitleaks_release_archive_sha256 arm64)" == "bf5f7f466ebfade1296c8bd32cf7d3f592c2aa78836aa9980ffbe2cadca7a861" ]] || {
  echo "Gitleaks architecture test: FAIL: arm64 checksum pin mismatch" >&2
  exit 1
}
if gitleaks_release_archive_sha256 riscv64 >/dev/null 2>&1; then
  echo "Gitleaks architecture test: FAIL: unsupported checksum architecture accepted" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf '%s' 'checksum-canary' >"$tmp/archive"
expected="$(sha256sum "$tmp/archive" | awk '{print $1}')"
verify_sha256_file "$tmp/archive" "$expected" || {
  echo "Gitleaks architecture test: FAIL: valid checksum rejected" >&2
  exit 1
}
if verify_sha256_file "$tmp/archive" "0000000000000000000000000000000000000000000000000000000000000000" >/dev/null 2>&1; then
  echo "Gitleaks architecture test: FAIL: wrong checksum accepted" >&2
  exit 1
fi
printf '%s' '-modified' >>"$tmp/archive"
if verify_sha256_file "$tmp/archive" "$expected" >/dev/null 2>&1; then
  echo "Gitleaks architecture test: FAIL: modified archive accepted" >&2
  exit 1
fi

for machine in '' armv7l riscv64 ppc64le; do
  if resolve_gitleaks_release_arch "$machine" >/dev/null 2>&1; then
    echo "Gitleaks architecture test: FAIL: unsupported architecture accepted: ${machine:-<empty>}" >&2
    exit 1
  fi
done

current="$(resolve_gitleaks_release_arch "$(uname -m)")"
[[ "$current" == "x64" || "$current" == "arm64" ]] || {
  echo "Gitleaks architecture test: FAIL: current machine did not resolve to a supported release asset" >&2
  exit 1
}

grep -Fq 'archive="gitleaks_${GITLEAKS_VERSION}_linux_${gitleaks_arch}.tar.gz"' ./scripts/run-gitleaks-ci.sh
if grep -Fq 'linux_x64.tar.gz' ./scripts/run-gitleaks-ci.sh; then
  echo "Gitleaks architecture test: FAIL: fixed x64 archive remains" >&2
  exit 1
fi

echo "Gitleaks architecture mapping test: PASS ($(uname -m) -> $current)"
