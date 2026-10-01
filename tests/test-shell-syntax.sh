#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

count=0
while IFS= read -r -d '' file; do
  bash -n "${file}"
  count=$((count + 1))
done < <(find scripts tests -type f -name '*.sh' -print0 | sort -z)

bash ./tests/test-dashboard-issue226-trusted-read-bridge.sh
python3 ./tests/test-deploy-executor-weather-public-privileged-install.py
python3 ./tests/test-deploy-executor-weather-public-operator-install.py
python3 ./tests/test-cloudflare-p1d04-prelive-prep.py
python3 ./tests/test-browser-lifecycle.py
python3 ./tests/test-ui-proof-guarded.py
python3 ./tests/test-adguard-dns-hardening.py
python3 ./tests/test-adguard-resolver-phase2.py
python3 ./tests/test-adguard-resolver-phase2-recovery.py
python3 ./tests/test-adguard-dhcpv4-migration.py

echo "Shell syntax: PASS (${count} files)"
