#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
script="$repo/scripts/rpi5-deploy"
python="$repo/scripts/rpi5_deploy.py"
lib="$repo/scripts/rpi5_deploy_lib.py"
tx="$repo/scripts/rpi5_deploy_tx.py"
manifest="$repo/ops/deploy/targets.json"

bash -n "$script"
python3 -m py_compile "$python" "$lib" "$tx"
python3 - "$manifest" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
assert data["schema"] == "rpi5.controlled-deploy-targets.v1"
assert [item["id"] for item in data["targets"]] == [
    "backup-runner",
    "backup-core",
    "maintenance-lock-lib",
    "backup-cron",
    "backup-logrotate",
]
assert {item["target"] for item in data["targets"]} == {
    "/usr/local/sbin/rpi5-backup",
    "/usr/local/lib/rpi5-maintenance/rpi5-backup-v10-core",
    "/usr/local/lib/rpi5-maintenance/rpi5-maintenance-locks.sh",
    "/etc/cron.d/rpi5-backup",
    "/etc/logrotate.d/rpi5-backup",
}
by_id = {item["id"]: item for item in data["targets"]}
assert by_id["backup-runner"]["source"] == "ops/bin/rpi5-backup-serialized"
assert by_id["backup-runner"]["mode"] == "0750"
assert by_id["backup-core"]["source"] == "ops/bin/rpi5-backup"
assert by_id["backup-core"]["mode"] == "0750"
assert by_id["maintenance-lock-lib"]["source"] == "ops/lib/rpi5-maintenance-locks.sh"
assert by_id["maintenance-lock-lib"]["mode"] == "0644"
assert all(item["target"] != "/etc/rpi5-backup.conf" for item in data["targets"])
assert data["reference_only"] == [{
    "source": "ops/backup/rpi5-backup.conf.example",
    "production_target": "/etc/rpi5-backup.conf",
    "reason": "The production file contains private host configuration and must never be replaced by the example.",
}]
print("controlled deploy V25 target manifest: PASS")
PY

grep -Fq 'automatic rollback starting' "$tx"
grep -Fq 'refusing rollback over later target drift' "$tx"
grep -Fq 'confirmation must equal the exact 12-character planned commit' "$python"
grep -Fq 'attestation-only target drift:' "$lib"
grep -Fq 'attestation-only target is not unchanged in plan:' "$lib"
grep -Fq 'last successful encrypted backup is too old' "$lib"
grep -Fq 'exact-commit GitHub checks are not all successful' "$lib"
grep -Fq 'runtime baseline mismatch' "$lib"
grep -Fq 'cron.service is not active' "$lib"
grep -Fq 'RPi throttling flag is not clear' "$lib"
grep -Fq 'test mode may never target the real root filesystem' "$lib"
grep -Fq 'root commands require the installed root-owned deploy engine' "$lib"
grep -Fq 'exec sudo -- /usr/local/sbin/rpi5-deploy' "$script"
grep -Fq 'exec /usr/bin/env -i' "$python"
if grep -R -Fq 'RPI5_DEPLOY_SKIP_' "$python" "$lib" "$tx"; then
    echo "controlled deploy: a production preflight bypass variable is present" >&2
    exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
fake_repo="$work/repo"
fake_root="$work/root"
state="$work/state"
log="$work/deploy.log"
mkdir -p \
    "$fake_repo/scripts" \
    "$fake_repo/ops/deploy" \
    "$fake_repo/ops/bin" \
    "$fake_repo/ops/lib" \
    "$fake_repo/ops/cron.d" \
    "$fake_repo/ops/logrotate.d" \
    "$fake_repo/ops/backup" \
    "$fake_repo/baselines/runtime" \
    "$fake_root/usr/local/sbin" \
    "$fake_root/usr/local/lib/rpi5-maintenance" \
    "$fake_root/etc/cron.d" \
    "$fake_root/etc/logrotate.d"

for relative in \
    scripts/rpi5-deploy \
    scripts/rpi5_deploy.py \
    scripts/rpi5_deploy_lib.py \
    scripts/rpi5_deploy_tx.py \
    ops/deploy/targets.json \
    ops/bin/rpi5-backup \
    ops/bin/rpi5-backup-serialized \
    ops/lib/rpi5-maintenance-locks.sh \
    ops/cron.d/rpi5-backup \
    ops/logrotate.d/rpi5-backup \
    ops/backup/rpi5-backup.conf.example \
    baselines/runtime/current.json; do
    cp "$repo/$relative" "$fake_repo/$relative"
done

# The V25 maintenance bundle is already live and must only be attested by the
# generic controlled-deploy engine. Cron and logrotate remain writable targets.
cp "$fake_repo/ops/bin/rpi5-backup-serialized" "$fake_root/usr/local/sbin/rpi5-backup"
cp "$fake_repo/ops/bin/rpi5-backup" "$fake_root/usr/local/lib/rpi5-maintenance/rpi5-backup-v10-core"
cp "$fake_repo/ops/lib/rpi5-maintenance-locks.sh" "$fake_root/usr/local/lib/rpi5-maintenance/rpi5-maintenance-locks.sh"
printf '%s\n' 'old cron' > "$fake_root/etc/cron.d/rpi5-backup"
printf '%s\n' 'old rotate' > "$fake_root/etc/logrotate.d/rpi5-backup"
chmod 0750 \
    "$fake_root/usr/local/sbin/rpi5-backup" \
    "$fake_root/usr/local/lib/rpi5-maintenance/rpi5-backup-v10-core"
chmod 0644 \
    "$fake_root/usr/local/lib/rpi5-maintenance/rpi5-maintenance-locks.sh" \
    "$fake_root/etc/cron.d/rpi5-backup" \
    "$fake_root/etc/logrotate.d/rpi5-backup"

old_cron_sha="$(sha256sum "$fake_root/etc/cron.d/rpi5-backup" | awk '{print $1}')"
old_rotate_sha="$(sha256sum "$fake_root/etc/logrotate.d/rpi5-backup" | awk '{print $1}')"

(
    cd "$fake_repo"
    git init -q -b main
    git config user.name test
    git config user.email test@example.invalid
    git add \
        scripts/rpi5-deploy scripts/rpi5_deploy.py scripts/rpi5_deploy_lib.py scripts/rpi5_deploy_tx.py \
        ops/deploy/targets.json ops/bin/rpi5-backup ops/bin/rpi5-backup-serialized \
        ops/lib/rpi5-maintenance-locks.sh ops/cron.d/rpi5-backup ops/logrotate.d/rpi5-backup \
        ops/backup/rpi5-backup.conf.example baselines/runtime/current.json
    git commit -q -m test
)

if RPI5_DEPLOY_TEST_MODE=1 \
   RPI5_DEPLOY_TEST_SANDBOX="$work" \
   RPI5_DEPLOY_ROOT=/ \
   RPI5_DEPLOY_STATE_DIR="$state" \
   RPI5_DEPLOY_LOG="$log" \
   bash "$fake_repo/scripts/rpi5-deploy" status >"$work/unsafe-test.out" 2>&1; then
    echo "controlled deploy: test mode accepted the real root filesystem" >&2
    exit 1
fi
grep -Fq 'test mode may never target the real root filesystem' "$work/unsafe-test.out"
echo "controlled deploy sandbox boundary: PASS"

export RPI5_DEPLOY_TEST_MODE=1
export RPI5_DEPLOY_TEST_SANDBOX="$work"
export RPI5_DEPLOY_ROOT="$fake_root"
export RPI5_DEPLOY_STATE_DIR="$state"
export RPI5_DEPLOY_LOG="$log"
export RPI5_DEPLOY_MAX_PLAN_AGE=300

python3 - "$fake_repo" "$work/engine-stage" <<'PY'
import json
import pathlib
import subprocess
import sys

repo = pathlib.Path(sys.argv[1])
stage = pathlib.Path(sys.argv[2])
sys.path.insert(0, str(repo / "scripts"))
import rpi5_deploy as deploy

commit = subprocess.run(
    ["git", "-C", str(repo), "rev-parse", "HEAD"],
    check=True,
    text=True,
    stdout=subprocess.PIPE,
).stdout.strip()
release = deploy.ENGINE_RELEASES / commit
source_hashes = deploy.engine_source_hashes()
metadata_path, wrapper_path = deploy.stage_engine_release(stage, release, commit, source_hashes)
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
assert metadata["schema"] == deploy.ENGINE_SCHEMA
assert metadata["installed_from_commit"] == commit
assert set(metadata["source_files"]) == set(deploy.ENGINE_SOURCE_FILES)
assert set(metadata["installed_files"]) == set(deploy.ENGINE_INSTALLED_FILES)
assert metadata["wrapper_sha256"] == deploy.sha256_file(wrapper_path)
assert "exec /usr/bin/env -i" in wrapper_path.read_text(encoding="utf-8")
print("controlled deploy engine release staging: PASS")
PY

# V25 control-plane drift is never repaired by the generic deploy engine.
printf '%s\n' '# synthetic drift' >> "$fake_root/usr/local/sbin/rpi5-backup"
if bash "$fake_repo/scripts/rpi5-deploy" plan >"$work/attest-drift.out" 2>&1; then
    echo "controlled deploy: V25 wrapper drift was accepted" >&2
    exit 1
fi
grep -Fq 'attestation-only target drift: backup-runner' "$work/attest-drift.out"
[[ ! -e "$state/plans/latest.json" ]]
cp "$fake_repo/ops/bin/rpi5-backup-serialized" "$fake_root/usr/local/sbin/rpi5-backup"
chmod 0750 "$fake_root/usr/local/sbin/rpi5-backup"
echo "controlled deploy V25 drift refusal: PASS"

bash "$fake_repo/scripts/rpi5-deploy" plan > "$work/plan.out"
short_sha="$(git -C "$fake_repo" rev-parse --short=12 HEAD)"
grep -Fq "CONFIRMATION FOR DEPLOY: $short_sha" "$work/plan.out"
python3 - "$state/plans/latest.json" "$short_sha" <<'PY'
import json
import sys
from pathlib import Path

plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert plan["schema"] == "rpi5.controlled-deploy-plan.v1"
assert plan["short_commit"] == sys.argv[2]
assert [item["action"] for item in plan["targets"]] == [
    "unchanged", "unchanged", "unchanged", "replace", "replace"
]
assert all(item["desired"]["exists"] for item in plan["targets"])
assert all(
    item["before"] == item["desired"]
    for item in plan["targets"][:3]
)
assert plan["host_preflight"]["skipped"] is True
print("controlled deploy V25-aware plan: PASS")
PY

if bash "$fake_repo/scripts/rpi5-deploy" deploy --confirm deadbeefdead >"$work/wrong.out" 2>&1; then
    echo "controlled deploy: wrong commit confirmation unexpectedly succeeded" >&2
    exit 1
fi
grep -Fq 'confirmation must equal' "$work/wrong.out"

export RPI5_DEPLOY_TEST_FAIL_AFTER=backup-cron
if bash "$fake_repo/scripts/rpi5-deploy" deploy --confirm "$short_sha" >"$work/fail.out" 2>&1; then
    echo "controlled deploy: synthetic post-write failure unexpectedly succeeded" >&2
    exit 1
fi
unset RPI5_DEPLOY_TEST_FAIL_AFTER
grep -Fq 'all changed targets were rolled back' "$work/fail.out"
[[ "$(sha256sum "$fake_root/usr/local/sbin/rpi5-backup" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/bin/rpi5-backup-serialized" | awk '{print $1}')" ]]
[[ "$(sha256sum "$fake_root/usr/local/lib/rpi5-maintenance/rpi5-backup-v10-core" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/bin/rpi5-backup" | awk '{print $1}')" ]]
[[ "$(sha256sum "$fake_root/usr/local/lib/rpi5-maintenance/rpi5-maintenance-locks.sh" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/lib/rpi5-maintenance-locks.sh" | awk '{print $1}')" ]]
[[ "$(sha256sum "$fake_root/etc/cron.d/rpi5-backup" | awk '{print $1}')" == "$old_cron_sha" ]]
[[ "$(sha256sum "$fake_root/etc/logrotate.d/rpi5-backup" | awk '{print $1}')" == "$old_rotate_sha" ]]
failed_tx="$(find "$state/transactions" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)"
python3 - "$failed_tx/transaction.json" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert data["status"] == "rolled_back"
changed = [item for item in data["targets"] if item.get("changed")]
assert [item["id"] for item in changed] == ["backup-cron"]
assert changed[0]["phase"] == "restored"
print("controlled deploy rollback audit metadata: PASS")
PY
echo "controlled deploy automatic rollback simulation: PASS"

bash "$fake_repo/scripts/rpi5-deploy" plan >/dev/null
bash "$fake_repo/scripts/rpi5-deploy" deploy --confirm "$short_sha" > "$work/deploy.out"
grep -Fq 'DEPLOY PASS' "$work/deploy.out"
[[ "$(sha256sum "$fake_root/usr/local/sbin/rpi5-backup" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/bin/rpi5-backup-serialized" | awk '{print $1}')" ]]
[[ "$(sha256sum "$fake_root/usr/local/lib/rpi5-maintenance/rpi5-backup-v10-core" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/bin/rpi5-backup" | awk '{print $1}')" ]]
[[ "$(sha256sum "$fake_root/usr/local/lib/rpi5-maintenance/rpi5-maintenance-locks.sh" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/lib/rpi5-maintenance-locks.sh" | awk '{print $1}')" ]]
[[ "$(sha256sum "$fake_root/etc/cron.d/rpi5-backup" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/cron.d/rpi5-backup" | awk '{print $1}')" ]]
[[ "$(sha256sum "$fake_root/etc/logrotate.d/rpi5-backup" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/logrotate.d/rpi5-backup" | awk '{print $1}')" ]]
bash "$fake_repo/scripts/rpi5-deploy" status > "$work/status.out"
for id in backup-runner backup-core maintenance-lock-lib backup-cron backup-logrotate; do
    grep -Eq "^MATCH +${id} +" "$work/status.out"
done
grep -Fq 'status=success' "$work/status.out"
echo "controlled deploy V25-aware synthetic deploy: PASS"

chmod 0600 "$fake_root/etc/cron.d/rpi5-backup"
if bash "$fake_repo/scripts/rpi5-deploy" rollback --latest --confirm ROLLBACK >"$work/drift.out" 2>&1; then
    echo "controlled deploy: rollback overwrote later metadata drift" >&2
    exit 1
fi
grep -Fq 'refusing rollback over later target drift' "$work/drift.out"
chmod 0644 "$fake_root/etc/cron.d/rpi5-backup"
bash "$fake_repo/scripts/rpi5-deploy" rollback --latest --confirm ROLLBACK > "$work/rollback.out"
grep -Fq 'ROLLBACK PASS' "$work/rollback.out"
[[ "$(sha256sum "$fake_root/etc/cron.d/rpi5-backup" | awk '{print $1}')" == "$old_cron_sha" ]]
[[ "$(sha256sum "$fake_root/etc/logrotate.d/rpi5-backup" | awk '{print $1}')" == "$old_rotate_sha" ]]
[[ "$(sha256sum "$fake_root/usr/local/sbin/rpi5-backup" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/bin/rpi5-backup-serialized" | awk '{print $1}')" ]]
echo "controlled deploy guarded manual rollback: PASS"

grep -Fq 'PLAN PASS' "$log"
grep -Fq 'DEPLOY PASS' "$log"
grep -Fq 'ROLLBACK PASS' "$log"
printf '%s\n' 'controlled deploy tests: PASS'
