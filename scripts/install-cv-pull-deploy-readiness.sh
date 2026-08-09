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

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail 'run installer with sudo'

SOURCE_ROOT="${1:-/home/andris/RPi5_main}"
OWNER='andris'
OWNER_HOME='/home/andris'
CONTROLLER_REL='ops/bin/rozkalns-cv-pull-deploy'
READINESS_REL='scripts/cv-deploy-readiness.py'
SERVICE_REL='ops/systemd/rozkalns-cv-pull-deploy.service'
TIMER_REL='ops/systemd/rozkalns-cv-pull-deploy.timer'
DEST_CONTROLLER='/usr/local/sbin/rozkalns-cv-pull-deploy'
DEST_LIBEXEC='/usr/local/libexec/rozkalns-cv'
DEST_READINESS="$DEST_LIBEXEC/deploy-readiness"
DEST_SERVICE='/etc/systemd/system/rozkalns-cv-pull-deploy.service'
DEST_TIMER='/etc/systemd/system/rozkalns-cv-pull-deploy.timer'
STATE_ROOT='/home/andris/.local/state/rozkalns-cv-main-deploy'
PREFLIGHT='/usr/local/sbin/rozkalns-cv-pull-deploy-preflight'
CLASSIFIER='/usr/local/libexec/rozkalns-cv/classify-deploy-impact'
BROKER='/usr/local/sbin/rozkalns-github-app-read-token'

for command_name in bash git id install python3 runuser sha256sum stat systemctl; do
    command -v "$command_name" >/dev/null 2>&1 \
        || fail "required command is missing: $command_name"
done
id "$OWNER" >/dev/null 2>&1 || fail 'owner user is missing'
[[ -d "$SOURCE_ROOT" && ! -L "$SOURCE_ROOT" ]] || fail 'RPi5_main source root is missing or unsafe'

owner_git() {
    runuser -u "$OWNER" -- env \
        HOME="$OWNER_HOME" \
        PATH='/home/andris/.local/bin:/usr/local/bin:/usr/bin:/bin' \
        git -C "$SOURCE_ROOT" "$@"
}

owner_git fetch --prune origin main
HEAD_SHA="$(owner_git rev-parse HEAD)"
REMOTE_SHA="$(owner_git rev-parse refs/remotes/origin/main)"
[[ "$HEAD_SHA" == "$REMOTE_SHA" ]] || fail 'RPi5_main checkout is not exact origin/main'
[[ "$(owner_git branch --show-current)" == 'main' ]] || fail 'RPi5_main checkout must remain on main'
[[ -z "$(owner_git status --porcelain=v1 --untracked-files=all)" ]] \
    || fail 'RPi5_main checkout is not clean'

for relative in "$CONTROLLER_REL" "$READINESS_REL" "$SERVICE_REL" "$TIMER_REL"; do
    owner_git ls-files --error-unmatch "$relative" >/dev/null \
        || fail "source is not tracked: $relative"
    [[ -f "$SOURCE_ROOT/$relative" && ! -L "$SOURCE_ROOT/$relative" ]] \
        || fail "source is missing or unsafe: $relative"
done

bash -n "$SOURCE_ROOT/$CONTROLLER_REL"
python3 "$SOURCE_ROOT/$READINESS_REL" --help >/dev/null

for existing in "$PREFLIGHT" "$CLASSIFIER" "$BROKER"; do
    [[ -x "$existing" && ! -L "$existing" ]] \
        || fail "required installed CV control-plane dependency is missing or unsafe: $existing"
    [[ "$(stat -c '%U:%G:%a' "$existing")" == 'root:root:755' ]] \
        || fail "required installed CV dependency ownership/mode is unexpected: $existing"
done

# Source installation is allowed, but recurring execution remains disabled until
# the separate Phase 3 one-shot canary and later activation gate are complete.
systemctl disable --now rozkalns-cv-pull-deploy.timer >/dev/null 2>&1 || true

install -d -o "$OWNER" -g "$OWNER" -m 0700 "$STATE_ROOT"
install -d -o root -g root -m 0755 "$DEST_LIBEXEC"
install -o root -g root -m 0755 "$SOURCE_ROOT/$CONTROLLER_REL" "$DEST_CONTROLLER"
install -o root -g root -m 0755 "$SOURCE_ROOT/$READINESS_REL" "$DEST_READINESS"
install -o root -g root -m 0644 "$SOURCE_ROOT/$SERVICE_REL" "$DEST_SERVICE"
install -o root -g root -m 0644 "$SOURCE_ROOT/$TIMER_REL" "$DEST_TIMER"
systemctl daemon-reload

[[ "$(systemctl is-enabled rozkalns-cv-pull-deploy.timer 2>/dev/null || true)" != 'enabled' ]] \
    || fail 'CV pull-deploy timer unexpectedly enabled during readiness install'
[[ "$(systemctl is-active rozkalns-cv-pull-deploy.timer 2>/dev/null || true)" != 'active' ]] \
    || fail 'CV pull-deploy timer unexpectedly active during readiness install'

printf 'CV_PULL_DEPLOY_READINESS_INSTALL=PASS\n'
printf 'SOURCE_SHA=%s\n' "$HEAD_SHA"
printf 'CONTROLLER_SHA256=%s\n' "$(sha256sum "$DEST_CONTROLLER" | awk '{print $1}')"
printf 'READINESS_SHA256=%s\n' "$(sha256sum "$DEST_READINESS" | awk '{print $1}')"
printf 'TIMER_ENABLED=%s\n' "$(systemctl is-enabled rozkalns-cv-pull-deploy.timer 2>/dev/null || true)"
printf 'TIMER_ACTIVE=%s\n' "$(systemctl is-active rozkalns-cv-pull-deploy.timer 2>/dev/null || true)"
printf 'DEPLOY_HELPER_MODIFIED=false\n'
printf 'PRODUCTION_CHANGED=false\n'
