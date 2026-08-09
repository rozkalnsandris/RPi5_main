#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="$repo/ops/maintenance/updater-source-provenance.json"

[[ -f "$manifest" && ! -L "$manifest" ]]

python3 - "$manifest" <<'PY'
import json
import re
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert data["schema"] == "rpi5-maintenance-updater-provenance-v1"
assert data["issue"] == 95
assert data["status"] == "reviewed-successor-source-imported"
assert data["installed_target"] == "/usr/local/sbin/rpi5-update"

lineage = data["historical_lineage"]
by_stage = {item["stage"]: item for item in lineage}
assert by_stage["v16b-pre-healthcheck-fix"]["sha256"] == "3371fd692e41907721af70c11cb91217c3ade4bef11b9925565a2a5789b06a29"
assert by_stage["v16b-post-healthcheck-fix"]["sha256"] == "01e6952b25f2e63e8d838a004b98cdf3571452b08ae093b04046fff2e3179b18"
assert by_stage["v16b-post-healthcheck-fix"]["size_bytes"] == 45550
assert by_stage["v17-hardening"]["sha256"] is None
assert by_stage["2026-08-09-live-incident-fix"]["sha256"] == "bd0afe74dea18742a002c852d59fc67ec848a032116d2adc314c24848895e24c"
assert by_stage["2026-08-09-live-incident-fix"]["size_bytes"] == 47190

v21 = by_stage["v21-reviewed-successor-public-safe-fhs"]
assert v21["sha256"] == "b1678732e8e33b1d5b479167bae23f7efb8a2f5390fe635a91cb19792d706860"
assert v21["git_blob_sha1"] == "105b00e81d5629f35cf6050137db31d5f400f957"
assert v21["size_bytes"] == 50072
assert v21["helper_root"] == "/usr/local/lib/rpi5-maintenance"

candidate = data["candidate"]
assert candidate["stage"] == "v24-cleanup-ownership-public-safe-final"
assert candidate["path"] == "ops/bin/rpi5-update"
assert re.fullmatch(r"[0-9a-f]{64}", candidate["sha256"])
assert re.fullmatch(r"[0-9a-f]{40}", candidate["git_blob_sha1"])
assert isinstance(candidate["size_bytes"], int) and candidate["size_bytes"] > 40000
assert candidate["helper_root"] == "/usr/local/lib/rpi5-maintenance"
assert candidate["derived_from_sha256"] == v21["sha256"]
assert candidate["public_runtime_literals_removed"] is True
assert candidate["cleanup_home_scan_removed"] is True
assert candidate["cleanup_only_compose_preflight_removed"] is True
assert candidate["cleanup_custom_paths_allowlisted"] is True
assert candidate["cleanup_only_docker_command_optional"] is True

policy = data["candidate_policy"]
assert policy["claim_byte_identical_import"] is False
assert policy["unexpected_live_diff_blocks_install"] is True
assert policy["production_install_requires_explicit_approval"] is True
assert policy["private_runtime_values_live_outside_git"] is True
print("Maintenance updater provenance manifest: PASS")
PY
