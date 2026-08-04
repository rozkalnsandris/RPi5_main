#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

count=0
while IFS= read -r -d '' file; do
  bash -n "${file}"
  count=$((count + 1))
done < <(find scripts tests -type f -name '*.sh' -print0 | sort -z)

echo "Shell syntax: PASS (${count} files)"
