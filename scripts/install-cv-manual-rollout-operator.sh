#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077
PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
export PATH

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail 'run manual rollout operator installer with sudo'

OWNER='andris'
OPERATOR_REL='ops/bin/rozkalns-cv-manual-rollout-operator'
DEST_OPERATOR='/usr/local/sbin/rozkalns-cv-manual-rollout-operator'
CANARY_REL='ops/bin/rozkalns-cv-pull-deploy-canary'
CONTROLLER_REL='ops/bin/rozkalns-cv-pull-deploy'
TIMER_REL='ops/systemd/rozkalns-cv-pull-deploy.timer'
SERVICE_REL='ops/systemd/rozkalns-cv-pull-deploy.service'
CANARY='/usr/local/sbin/rozkalns-cv-pull-deploy-canary'
CONTROLLER='/usr/local/sbin/rozkalns-cv-pull-deploy'
TIMER_FILE='/etc/systemd/system/rozkalns-cv-pull-deploy.timer'
SERVICE_FILE='/etc/systemd/system/rozkalns-cv-pull-deploy.service'
TIMER_UNIT='rozkalns-cv-pull-deploy.timer'

for command_name in awk bash getent git grep id install runuser stat systemctl; do
    command -v "$command_name" >/dev/null 2>&1 \
        || fail "required command is missing: $command_name"
done
id "$OWNER" >/dev/null 2>&1 || fail 'owner user is missing'
OWNER_HOME="$(getent passwd "$OWNER" | awk -F: 'NR == 1 {print $6}')"
[[ "$OWNER_HOME" == /* && -d "$OWNER_HOME" && ! -L "$OWNER_HOME" ]] \
    || fail 'owner home directory is missing or unsafe'
SOURCE_ROOT="${1:-$OWNER_HOME/RPi5_main}"
[[ -d "$SOURCE_ROOT" && ! -L "$SOURCE_ROOT" ]] \
    || fail 'RPi5_main source root is missing or unsafe'

owner_git() {
    runuser -u "$OWNER" -- env \
        HOME="$OWNER_HOME" \
        PATH='/usr/local/bin:/usr/bin:/bin' \
        git -C "$SOURCE_ROOT" "$@"
}

owner_git fetch --prune origin main
HEAD_SHA="$(owner_git rev-parse HEAD)"
REMOTE_SHA="$(owner_git rev-parse refs/remotes/origin/main)"
[[ "$HEAD_SHA" == "$REMOTE_SHA" ]] || fail 'RPi5_main checkout is not exact origin/main'
[[ "$(owner_git branch --show-current)" == main ]] || fail 'RPi5_main checkout must remain on main'
[[ -z "$(owner_git status --porcelain=v1 --untracked-files=all)" ]] \
    || fail 'RPi5_main checkout is not clean'

for rel in "$OPERATOR_REL" "$CANARY_REL" "$CONTROLLER_REL" "$TIMER_REL" "$SERVICE_REL"; do
    owner_git ls-files --error-unmatch "$rel" >/dev/null \
        || fail "required source is not tracked: $rel"
    [[ -f "$SOURCE_ROOT/$rel" && ! -L "$SOURCE_ROOT/$rel" ]] \
        || fail "required source is missing or unsafe: $rel"
done
bash -n "$SOURCE_ROOT/$OPERATOR_REL"

CANARY_BLOB="$(owner_git rev-parse "HEAD:$CANARY_REL")"
CONTROLLER_BLOB="$(owner_git rev-parse "HEAD:$CONTROLLER_REL")"
TIMER_BLOB="$(owner_git rev-parse "HEAD:$TIMER_REL")"
SERVICE_BLOB="$(owner_git rev-parse "HEAD:$SERVICE_REL")"

for contract in \
    "EXPECTED_CANARY_BLOB='$CANARY_BLOB'" \
    "EXPECTED_CONTROLLER_BLOB='$CONTROLLER_BLOB'" \
    "EXPECTED_TIMER_BLOB='$TIMER_BLOB'" \
    "EXPECTED_SERVICE_BLOB='$SERVICE_BLOB'"
do
    grep -Fqx "$contract" "$SOURCE_ROOT/$OPERATOR_REL" \
        || fail "manual rollout operator artifact contract is stale: $contract"
done

check_installed_blob() {
    local path=$1
    local expected_mode=$2
    local expected_blob=$3
    local label=$4
    local actual_blob

    [[ -f "$path" && ! -L "$path" ]] || fail "$label is missing or unsafe"
    [[ "$(stat -c '%U:%G:%a' "$path")" == "root:root:$expected_mode" ]] \
        || fail "$label ownership/mode is unexpected"
    actual_blob="$(git hash-object "$path")"
    [[ "$actual_blob" == "$expected_blob" ]] || fail "$label identity does not match exact main"
}

check_installed_blob "$CANARY" 755 "$CANARY_BLOB" 'installed production canary'
check_installed_blob "$CONTROLLER" 755 "$CONTROLLER_BLOB" 'installed pull-deploy controller'
check_installed_blob "$TIMER_FILE" 644 "$TIMER_BLOB" 'installed pull-deploy timer unit'
check_installed_blob "$SERVICE_FILE" 644 "$SERVICE_BLOB" 'installed pull-deploy service unit'

TIMER_ENABLED="$(systemctl is-enabled "$TIMER_UNIT" 2>/dev/null || true)"
TIMER_ACTIVE="$(systemctl is-active "$TIMER_UNIT" 2>/dev/null || true)"

install -o root -g root -m 0755 "$SOURCE_ROOT/$OPERATOR_REL" "$DEST_OPERATOR"
[[ "$(stat -c '%U:%G:%a' "$DEST_OPERATOR")" == 'root:root:755' ]] \
    || fail 'installed manual rollout operator ownership/mode is unexpected'
[[ "$(git hash-object "$DEST_OPERATOR")" == "$(owner_git rev-parse "HEAD:$OPERATOR_REL")" ]] \
    || fail 'installed manual rollout operator identity mismatch'

printf 'CV_MANUAL_ROLLOUT_OPERATOR_INSTALL=PASS\n'
printf 'SOURCE_SHA=%s\n' "$HEAD_SHA"
printf 'TIMER_ENABLED=%s\n' "$TIMER_ENABLED"
printf 'TIMER_ACTIVE=%s\n' "$TIMER_ACTIVE"
printf 'TIMER_STATE_CHANGED=false\n'
printf 'PRODUCTION_CHANGED=false\n'
printf 'SUDOERS_CHANGED=false\n'
printf 'DEPLOY_EXECUTED=false\n'
