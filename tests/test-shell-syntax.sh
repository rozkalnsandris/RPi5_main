#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

count=0
while IFS= read -r -d '' file; do
  bash -n "${file}"
  count=$((count + 1))
done < <(find scripts tests -type f -name '*.sh' -print0 | sort -z)

bash ./tests/test-dashboard-issue226-trusted-read-bridge.sh
python3 ./tests/test-hermes-source-app-credential-provisioner.py

echo "Shell syntax: PASS (${count} files)"
