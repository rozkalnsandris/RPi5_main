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

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail 'run canary installer with sudo'

OWNER='andris'
CANARY_REL='ops/bin/rozkalns-cv-pull-deploy-canary'
DEST_CANARY='/usr/local/sbin/rozkalns-cv-pull-deploy-canary'
CONTROLLER='/usr/local/sbin/rozkalns-cv-pull-deploy'
READINESS='/usr/local/libexec/rozkalns-cv/deploy-readiness'
PREFLIGHT='/usr/local/sbin/rozkalns-cv-pull-deploy-preflight'
CLASSIFIER='/usr/local/libexec/rozkalns-cv/classify-deploy-impact'
BROKER='/usr/local/sbin/rozkalns-github-app-read-token'
TIMER_UNIT='rozkalns-cv-pull-deploy.timer'

for command_name in awk bash getent git id install runuser sha256sum stat systemctl; do
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

owner_git ls-files --error-unmatch "$CANARY_REL" >/dev/null \
    || fail 'production canary source is not tracked'
[[ -f "$SOURCE_ROOT/$CANARY_REL" && ! -L "$SOURCE_ROOT/$CANARY_REL" ]] \
    || fail 'production canary source is missing or unsafe'
bash -n "$SOURCE_ROOT/$CANARY_REL"

for installed in "$CONTROLLER" "$READINESS" "$PREFLIGHT" "$CLASSIFIER" "$BROKER"; do
    [[ -x "$installed" && ! -L "$installed" ]] \
        || fail "required installed CV control artifact is missing or unsafe: $installed"
    [[ "$(stat -c '%U:%G:%a' "$installed")" == 'root:root:755' ]] \
        || fail "required installed CV control artifact ownership/mode is unexpected: $installed"
done

TIMER_ENABLED="$(systemctl is-enabled "$TIMER_UNIT" 2>/dev/null || true)"
TIMER_ACTIVE="$(systemctl is-active "$TIMER_UNIT" 2>/dev/null || true)"
[[ "$TIMER_ENABLED" != enabled ]] || fail 'CV pull-deploy timer must remain disabled for canary installation'
[[ "$TIMER_ACTIVE" != active ]] || fail 'CV pull-deploy timer must remain inactive for canary installation'

install -o root -g root -m 0755 "$SOURCE_ROOT/$CANARY_REL" "$DEST_CANARY"
[[ "$(stat -c '%U:%G:%a' "$DEST_CANARY")" == 'root:root:755' ]] \
    || fail 'installed production canary ownership/mode is unexpected'

printf 'CV_PULL_DEPLOY_CANARY_INSTALL=PASS\n'
printf 'SOURCE_SHA=%s\n' "$HEAD_SHA"
printf 'CANARY_SHA256=%s\n' "$(sha256sum "$DEST_CANARY" | awk '{print $1}')"
printf 'TIMER_ENABLED=%s\n' "$TIMER_ENABLED"
printf 'TIMER_ACTIVE=%s\n' "$TIMER_ACTIVE"
printf 'PRODUCTION_CHANGED=false\n'
printf 'DEPLOY_TRANSPORT_CHANGED=false\n'
printf 'LEGACY_RUNNER_CHANGED=false\n'