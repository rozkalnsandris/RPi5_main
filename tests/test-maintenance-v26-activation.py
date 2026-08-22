#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "ops/bin/rpi5-maintenance-v26-activate"
MAKEFILE = ROOT / "Makefile"

text = OPERATOR.read_text(encoding="utf-8")
subprocess.run(["bash", "-n", str(OPERATOR)], check=True)

for marker in (
    "EXPECTED_V25_SHA256='8701b3f8b21ccafb0d02fdd2d162aeb9400a57beb58572800dfe901bfc4bd02a'",
    "EXPECTED_V26_SHA256='df1b41f128cee6b014ad0ff43a5365699a055ff99ff26e2ad5dba6f5f60fc19e'",
    "EXPECTED_V26_BLOB='595b4752e1f40a961230daab188187bf79e63be8'",
    "EXPECTED_APT_POLICY_BLOB='9350483fd6e40af13f62f7a51fba575e53eeaf70'",
    "LOCK_LIB_REL='ops/lib/rpi5-maintenance-locks.sh'",
    "v26-cached-apt-check-public-safe",
    "no successful exact-main RPi5_main push CI run is available",
    "/run/lock/rpi5-update.lock",
    "/run/lock/rpi5-backup.lock",
    "/run/lock/rpi5-maintenance-exclusive.lock",
    "V26_EXACT_INSTALL=PASS",
    "V26_NON_MUTATING_APT_CHECK=PASS",
    "MAINTENANCE_BOUNDARIES_UNCHANGED=PASS",
    "V26_HOST_ACTIVATION=PASS",
):
    assert marker in text, marker

assert 'if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi' in text
assert 'require_root_dir "$MAINTENANCE_LIB"' in text
assert 'require_root_dir "$(dirname -- "$UPDATER_DEST")"' in text
assert 'install -d -o root -g root -m 0755 "$MAINTENANCE_LIB"' not in text

for marker in (
    "atomic_stage_copy()",
    "atomic_replace_stage()",
    'mktemp "${destination}.v26-stage.XXXXXX"',
    'mv -Tf -- "$stage" "$destination"',
    'atomic_stage_copy "$updater_source" "$UPDATER_DEST" 0750 updater_stage root root',
    'atomic_stage_copy "$apt_policy_source" "$APT_POLICY_DEST" 0644 policy_stage root root',
    'atomic_replace_stage "$policy_stage" "$APT_POLICY_DEST"',
    'atomic_replace_stage "$updater_stage" "$UPDATER_DEST"',
):
    assert marker in text, marker

for forbidden in (
    'install -o root -g root -m 0750 "$updater_source" "$UPDATER_DEST"',
    'install -o root -g root -m 0644 "$apt_policy_source" "$APT_POLICY_DEST"',
    'cp "$updater_source" "$UPDATER_DEST"',
    'cp "$apt_policy_source" "$APT_POLICY_DEST"',
):
    assert forbidden not in text, forbidden

for marker in (
    "rpi5_try_exclusive_lock",
    "RPI5_LOCK_CONFLICT_RC",
    "activation contention",
    "lock acquisition error",
    "acquire_quiescent_window",
    "release_fd_var QUIESCENT_UPDATE_FD",
    'acquire_quiescent_one updater "$UPDATE_LOCK" QUIESCENT_UPDATE_FD',
):
    assert marker in text, marker

main = text[text.index("main() {"):]
policy_replace = 'atomic_replace_stage "$policy_stage" "$APT_POLICY_DEST"'
release_update = "release_fd_var QUIESCENT_UPDATE_FD"
staged_check = 'verify_v26_check "$updater_stage" "$check_log" /var/lib/apt/lists'
reacquire_update = 'acquire_quiescent_one updater "$UPDATE_LOCK" QUIESCENT_UPDATE_FD'
updater_replace = 'atomic_replace_stage "$updater_stage" "$UPDATER_DEST"'
assert main.index(policy_replace) < main.index(release_update) < main.index(staged_check) < main.index(reacquire_update) < main.index(updater_replace)

check = text[text.index("verify_v26_check() {"):text.index("\nacquire_quiescent_one() {")]
for marker in (
    'before="$(apt_lists_fingerprint "$apt_root")"',
    '"$staged_updater" --check >"$check_log" 2>&1',
    'after="$(apt_lists_fingerprint "$apt_root")"',
    '[[ "$before" == "$after" ]]',
    "EXPECTED_CHECK_MARKER",
    "FORBIDDEN_REFRESH_MARKER",
):
    assert marker in check, marker

for marker in (
    "restore_activation_state()",
    "atomic_restore_snapshot()",
    '"$state_dir/rpi5-update.before"',
    '"$state_dir/rpi5-update-apt-policy.before"',
    "rollback refused because backup/shared quiescent locks are not held",
    "ROLLBACK PASS: restored pre-activation updater and APT-policy state atomically.",
    "trap on_exit EXIT",
):
    assert marker in text, marker

for forbidden in (
    "systemctl start ", "systemctl restart ", "systemctl enable ", "systemctl disable ",
    "systemctl stop ", "systemctl daemon-reload", "docker compose ", "apt-get update",
    "shutdown ", " reboot ", '"$UPDATER_DEST" --', '"$BACKUP_DEST" --',
):
    assert forbidden not in text, forbidden

index = subprocess.check_output(
    ["git", "-C", str(ROOT), "ls-files", "-s", "--", "ops/bin/rpi5-maintenance-v26-activate"],
    text=True,
).strip()
assert index and index.split()[0] == "100755", f"operator mode: {index}"

makefile = MAKEFILE.read_text(encoding="utf-8")
assert "python3 ./tests/test-maintenance-v26-activation.py" in makefile
assert "python3 ./tests/test-maintenance-v26-activation-transaction.py" in makefile

print("Maintenance V26 host activation source contract: PASS")
