#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
manifest="$repo/ops/maintenance/updater-source-provenance.json"

[[ -f "$manifest" && ! -L "$manifest" ]]

python3 - "$manifest" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
assert data["schema"] == "rpi5-maintenance-updater-provenance-v1"
assert data["issue"] == 95
assert data["status"] == "reviewed-successor-source-imported"
assert data["installed_target"] == "/usr/local/sbin/rpi5-update"

lineage = data["historical_lineage"]
assert [item["stage"] for item in lineage] == [
    "v16b-pre-healthcheck-fix",
    "v16b-post-healthcheck-fix",
    "v17-hardening",
    "2026-08-09-live-incident-fix",
]
assert lineage[0]["sha256"] == "3371fd692e41907721af70c11cb91217c3ade4bef11b9925565a2a5789b06a29"
assert lineage[1]["sha256"] == "01e6952b25f2e63e8d838a004b98cdf3571452b08ae093b04046fff2e3179b18"
assert lineage[1]["size_bytes"] == 45550
assert lineage[2]["sha256"] is None
assert lineage[3]["sha256"] == "bd0afe74dea18742a002c852d59fc67ec848a032116d2adc314c24848895e24c"
assert lineage[3]["size_bytes"] == 47190

candidate = data["candidate"]
assert candidate == {
    "stage": "v21-reviewed-successor-public-safe",
    "path": "ops/bin/rpi5-update",
    "sha256": "860b2dd0be0d7f32f2648742a356bccabb20f0c9f8e7073ba2b1c998aa212851",
    "git_blob_sha1": "67cd5b443dfdb8a48fd08aaa4015dc0f6b26e9ec",
    "size_bytes": 50076,
    "derived_from_sha256": "bd0afe74dea18742a002c852d59fc67ec848a032116d2adc314c24848895e24c",
    "public_runtime_literals_removed": True,
}

policy = data["candidate_policy"]
assert policy == {
    "claim_byte_identical_import": False,
    "unexpected_live_diff_blocks_install": True,
    "production_install_requires_explicit_approval": True,
    "private_runtime_values_live_outside_git": True,
}
print("Maintenance updater provenance manifest: PASS")
PY
