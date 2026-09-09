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
