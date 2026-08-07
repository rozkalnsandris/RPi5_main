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
    "backup-cron",
    "backup-logrotate",
]
assert {item["target"] for item in data["targets"]} == {
    "/usr/local/sbin/rpi5-backup",
    "/etc/cron.d/rpi5-backup",
    "/etc/logrotate.d/rpi5-backup",
}
assert all(item["target"] != "/etc/rpi5-backup.conf" for item in data["targets"])
assert data["reference_only"] == [{
    "source": "ops/backup/rpi5-backup.conf.example",
    "production_target": "/etc/rpi5-backup.conf",
    "reason": "The production file contains private host configuration and must never be replaced by the example.",
}]
print("V12 manifest contract: PASS")
PY

grep -Fq 'automatic rollback starting' "$tx"
grep -Fq 'refusing rollback over later target drift' "$tx"
grep -Fq 'confirmation must equal the exact 12-character planned commit' "$python"
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
    echo "V12: a production preflight bypass variable is present" >&2
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
    "$fake_repo/ops/cron.d" \
    "$fake_repo/ops/logrotate.d" \
    "$fake_repo/ops/backup" \
    "$fake_repo/baselines/runtime" \
    "$fake_root/usr/local/sbin" \
    "$fake_root/etc/cron.d" \
    "$fake_root/etc/logrotate.d"
cp "$script" "$fake_repo/scripts/rpi5-deploy"
cp "$python" "$fake_repo/scripts/rpi5_deploy.py"
cp "$lib" "$fake_repo/scripts/rpi5_deploy_lib.py"
cp "$tx" "$fake_repo/scripts/rpi5_deploy_tx.py"
cp "$manifest" "$fake_repo/ops/deploy/targets.json"
cat > "$fake_repo/ops/bin/rpi5-backup" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' 'synthetic backup runner'
SH
chmod 0755 "$fake_repo/ops/bin/rpi5-backup"
cat > "$fake_repo/ops/cron.d/rpi5-backup" <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
MAILTO=""
# RPi5 šifrētais backup katru nakti 02:00.
0 2 * * * root /usr/local/sbin/rpi5-backup
CRON
cat > "$fake_repo/ops/logrotate.d/rpi5-backup" <<'ROTATE'
/var/log/rpi5-backup.log {
    daily
    rotate 14
    missingok
    notifempty
    compress
    delaycompress
    dateext
    create 0600 root root
}
ROTATE
printf '%s\n' '# reference only' > "$fake_repo/ops/backup/rpi5-backup.conf.example"
printf '%s\n' '{"docker":{"containers":[]}}' > "$fake_repo/baselines/runtime/current.json"

printf '%s\n' 'old runner' > "$fake_root/usr/local/sbin/rpi5-backup"
printf '%s\n' 'old cron' > "$fake_root/etc/cron.d/rpi5-backup"
printf '%s\n' 'old rotate' > "$fake_root/etc/logrotate.d/rpi5-backup"
chmod 0700 "$fake_root/usr/local/sbin/rpi5-backup"
chmod 0644 "$fake_root/etc/cron.d/rpi5-backup" "$fake_root/etc/logrotate.d/rpi5-backup"
old_runner_sha="$(sha256sum "$fake_root/usr/local/sbin/rpi5-backup" | awk '{print $1}')"
old_cron_sha="$(sha256sum "$fake_root/etc/cron.d/rpi5-backup" | awk '{print $1}')"
old_rotate_sha="$(sha256sum "$fake_root/etc/logrotate.d/rpi5-backup" | awk '{print $1}')"

(
    cd "$fake_repo"
    git init -q -b main
    git config user.name test
    git config user.email test@example.invalid
    git add scripts/rpi5-deploy scripts/rpi5_deploy.py scripts/rpi5_deploy_lib.py scripts/rpi5_deploy_tx.py ops/deploy/targets.json \
        ops/bin/rpi5-backup ops/cron.d/rpi5-backup ops/logrotate.d/rpi5-backup \
        ops/backup/rpi5-backup.conf.example baselines/runtime/current.json
    git commit -q -m test
)

if RPI5_DEPLOY_TEST_MODE=1 \
   RPI5_DEPLOY_TEST_SANDBOX="$work" \
   RPI5_DEPLOY_ROOT=/ \
   RPI5_DEPLOY_STATE_DIR="$state" \
   RPI5_DEPLOY_LOG="$log" \
   bash "$fake_repo/scripts/rpi5-deploy" status >"$work/unsafe-test.out" 2>&1; then
    echo "V12: test mode accepted the real root filesystem" >&2
    exit 1
fi
grep -Fq 'test mode may never target the real root filesystem' "$work/unsafe-test.out"
echo "V12 sandbox boundary: PASS"

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
metadata_path, wrapper_path = deploy.stage_engine_release(
    stage, release, commit, source_hashes
)
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
assert metadata["schema"] == deploy.ENGINE_SCHEMA
assert metadata["installed_from_commit"] == commit
assert set(metadata["source_files"]) == set(deploy.ENGINE_SOURCE_FILES)
assert set(metadata["installed_files"]) == set(deploy.ENGINE_INSTALLED_FILES)
assert metadata["wrapper_sha256"] == deploy.sha256_file(wrapper_path)
for name, relative in {
    "rpi5_deploy.py": "scripts/rpi5_deploy.py",
    "rpi5_deploy_lib.py": "scripts/rpi5_deploy_lib.py",
    "rpi5_deploy_tx.py": "scripts/rpi5_deploy_tx.py",
}.items():
    assert metadata["installed_files"][name]["sha256"] == source_hashes[relative]
wrapper = wrapper_path.read_text(encoding="utf-8")
assert "exec /usr/bin/env -i" in wrapper
assert str(release / "rpi5_deploy.py") in wrapper
print("V12 engine release staging: PASS")
PY

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
assert [item["action"] for item in plan["targets"]] == ["replace", "replace", "replace"]
assert all(item["desired"]["exists"] for item in plan["targets"])
assert plan["host_preflight"]["skipped"] is True
print("V12 synthetic plan: PASS")
PY

if bash "$fake_repo/scripts/rpi5-deploy" deploy --confirm deadbeefdead >"$work/wrong.out" 2>&1; then
    echo "V12: wrong commit confirmation unexpectedly succeeded" >&2
    exit 1
fi
grep -Fq 'confirmation must equal' "$work/wrong.out"

export RPI5_DEPLOY_TEST_FAIL_AFTER=backup-cron
if bash "$fake_repo/scripts/rpi5-deploy" deploy --confirm "$short_sha" >"$work/fail.out" 2>&1; then
    echo "V12: synthetic post-write failure unexpectedly succeeded" >&2
    exit 1
fi
unset RPI5_DEPLOY_TEST_FAIL_AFTER
grep -Fq 'all changed targets were rolled back' "$work/fail.out"
[[ "$(sha256sum "$fake_root/usr/local/sbin/rpi5-backup" | awk '{print $1}')" == "$old_runner_sha" ]]
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
assert changed
assert all(item["phase"] == "restored" for item in changed)
print("V12 rollback audit metadata: PASS")
PY
echo "V12 automatic rollback simulation: PASS"

bash "$fake_repo/scripts/rpi5-deploy" plan >/dev/null
bash "$fake_repo/scripts/rpi5-deploy" deploy --confirm "$short_sha" > "$work/deploy.out"
grep -Fq 'DEPLOY PASS' "$work/deploy.out"
[[ "$(sha256sum "$fake_root/usr/local/sbin/rpi5-backup" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/bin/rpi5-backup" | awk '{print $1}')" ]]
[[ "$(sha256sum "$fake_root/etc/cron.d/rpi5-backup" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/cron.d/rpi5-backup" | awk '{print $1}')" ]]
[[ "$(sha256sum "$fake_root/etc/logrotate.d/rpi5-backup" | awk '{print $1}')" == "$(sha256sum "$fake_repo/ops/logrotate.d/rpi5-backup" | awk '{print $1}')" ]]
bash "$fake_repo/scripts/rpi5-deploy" status > "$work/status.out"
grep -Fq 'MATCH  backup-runner' "$work/status.out"
grep -Fq 'status=success' "$work/status.out"
echo "V12 synthetic deploy: PASS"

chmod 0600 "$fake_root/etc/cron.d/rpi5-backup"
if bash "$fake_repo/scripts/rpi5-deploy" rollback --latest --confirm ROLLBACK >"$work/drift.out" 2>&1; then
    echo "V12: rollback overwrote later metadata drift" >&2
    exit 1
fi
grep -Fq 'refusing rollback over later target drift' "$work/drift.out"
chmod 0644 "$fake_root/etc/cron.d/rpi5-backup"
bash "$fake_repo/scripts/rpi5-deploy" rollback --latest --confirm ROLLBACK > "$work/rollback.out"
grep -Fq 'ROLLBACK PASS' "$work/rollback.out"
[[ "$(sha256sum "$fake_root/usr/local/sbin/rpi5-backup" | awk '{print $1}')" == "$old_runner_sha" ]]
[[ "$(sha256sum "$fake_root/etc/cron.d/rpi5-backup" | awk '{print $1}')" == "$old_cron_sha" ]]
[[ "$(sha256sum "$fake_root/etc/logrotate.d/rpi5-backup" | awk '{print $1}')" == "$old_rotate_sha" ]]
echo "V12 guarded manual rollback: PASS"

grep -Fq 'PLAN PASS' "$log"
grep -Fq 'DEPLOY PASS' "$log"
grep -Fq 'ROLLBACK PASS' "$log"
printf '%s\n' 'V12 controlled deploy tests: PASS'
