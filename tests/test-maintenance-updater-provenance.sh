#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="$repo/ops/maintenance/updater-source-provenance.json"
source_file="$repo/ops/bin/rpi5-update"

[[ -f "$manifest" && ! -L "$manifest" ]]
[[ -f "$source_file" && ! -L "$source_file" ]]

python3 - "$manifest" "$source_file" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
source_bytes = Path(sys.argv[2]).read_bytes()

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

v24 = by_stage["v24-cleanup-ownership-public-safe-final"]
assert v24["sha256"] == "2f44d0b256e28450dd94ab7a6d1f5b5d2cb4a198adc44a11ae6932a3877a6b3c"
assert v24["git_blob_sha1"] == "5cbccfc5468cbb089e7cf7b9c4c78603eb542367"
assert v24["size_bytes"] == 50297
assert v24["helper_root"] == "/usr/local/lib/rpi5-maintenance"

v25 = by_stage["v25-shared-maintenance-lock-public-safe"]
assert v25["sha256"] == "8701b3f8b21ccafb0d02fdd2d162aeb9400a57beb58572800dfe901bfc4bd02a"
assert v25["git_blob_sha1"] == "049d9a040efb4be4c2ff861d46a7e0e302b1c5e8"
assert v25["size_bytes"] == 49860
assert v25["helper_root"] == "/usr/local/lib/rpi5-maintenance"

v26 = by_stage["v26-cached-apt-check-public-safe"]
assert v26["sha256"] == "df1b41f128cee6b014ad0ff43a5365699a055ff99ff26e2ad5dba6f5f60fc19e"
assert v26["git_blob_sha1"] == "595b4752e1f40a961230daab188187bf79e63be8"
assert v26["size_bytes"] == 51089
assert v26["helper_root"] == "/usr/local/lib/rpi5-maintenance"

candidate = data["candidate"]
assert candidate["stage"] == "v27-hermes-manual-update-check-only-public-safe"
assert candidate["path"] == "ops/bin/rpi5-update"
assert candidate["sha256"] == "f9c83acdd72131d6b696900972aa11d24978645b931846ff4ea8e6a8ed80bdc2"
assert candidate["git_blob_sha1"] == "744192e2acb7105d90a93e1cf3426433c09cb26d"
assert candidate["size_bytes"] == 46805
assert re.fullmatch(r"[0-9a-f]{64}", candidate["sha256"])
assert re.fullmatch(r"[0-9a-f]{40}", candidate["git_blob_sha1"])
assert candidate["helper_root"] == "/usr/local/lib/rpi5-maintenance"
assert candidate["derived_from_sha256"] == v26["sha256"]

actual_sha256 = hashlib.sha256(source_bytes).hexdigest()
blob_header = f"blob {len(source_bytes)}\0".encode("ascii")
actual_blob_sha1 = hashlib.sha1(blob_header + source_bytes).hexdigest()
assert actual_sha256 == candidate["sha256"]
assert actual_blob_sha1 == candidate["git_blob_sha1"]
assert len(source_bytes) == candidate["size_bytes"]

assert candidate["public_runtime_literals_removed"] is True
assert candidate["cleanup_home_scan_removed"] is True
assert candidate["cleanup_only_compose_preflight_removed"] is True
assert candidate["cleanup_custom_paths_allowlisted"] is True
assert candidate["cleanup_only_docker_command_optional"] is True
assert candidate["shared_maintenance_lock"] is True
assert candidate["backup_private_probe_removed"] is True
assert candidate["explicit_lock_conflict_code"] == 200
assert candidate["apt_check_cached_metadata"] is True
assert candidate["apt_check_metadata_refresh"] is False
assert candidate["apt_check_cache_freshness_reported"] is True
assert candidate["run_apt_metadata_refresh"] is True
assert candidate["hermes_unattended_update"] is False
assert candidate["hermes_update_check_only"] is True
assert candidate["hermes_update_check_after_health"] is True
assert candidate["hermes_update_check_advisory"] is True
assert candidate["hermes_update_check_blocks_reboot"] is False

backup = data["backup_ownership_snapshot"]
assert backup["label"] == "V10 ownership snapshot"
assert backup["runtime_version"] == 12
assert backup["path"] == "ops/bin/rpi5-backup"
assert backup["sha256"] == "5ca85ae53bdf4fa3b99e21e1a30ddaa077d9e1791505b1e8389ee8587d011735"
assert backup["identity_authority"] == "sha256"

policy = data["candidate_policy"]
assert policy["claim_byte_identical_import"] is False
assert policy["unexpected_live_diff_blocks_install"] is True
assert policy["production_install_requires_explicit_approval"] is True
assert policy["private_runtime_values_live_outside_git"] is True
print("Maintenance updater provenance manifest: PASS")
PY
