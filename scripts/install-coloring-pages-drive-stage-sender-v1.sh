#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077
PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
export PATH

fail() {
    printf 'COLORING_PAGES_DRIVE_STAGE_INSTALL=FAIL error=%s\n' "$*" >&2
    exit 1
}

usage() {
    cat >&2 <<'USAGE'
Usage: sudo bash scripts/install-coloring-pages-drive-stage-sender-v1.sh \
  --expected-rpi5-main-sha <40-hex-sha> \
  [--source-root <absolute-rpi5-main-path>]
USAGE
    exit 2
}

EXPECTED_SHA=''
SOURCE_ROOT=''
while (( $# > 0 )); do
    case "$1" in
        --expected-rpi5-main-sha)
            (( $# >= 2 )) || usage
            EXPECTED_SHA="$2"
            shift 2
            ;;
        --source-root)
            (( $# >= 2 )) || usage
            SOURCE_ROOT="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || fail 'expected RPi5_main SHA is invalid'
[[ ${EUID:-$(id -u)} -eq 0 ]] || fail 'installer must run as root via sudo'

OWNER='andris'
SENDER_REL='ops/bin/coloring-pages-drive-stage-sender'
WRAPPER_REL='ops/libexec/coloring-pages-drive-stage-rcat'
SUDOERS_REL='ops/sudoers/coloring-pages-drive-stage-sender'
CONTRACT_REL='ops/contracts/coloring-pages-drive-stage-sender-v1.json'
SENDER_DEST='/usr/local/bin/coloring-pages-drive-stage-sender'
WRAPPER_DEST='/usr/local/libexec/coloring-pages-drive-stage-rcat'
SUDOERS_DEST='/etc/sudoers.d/coloring-pages-drive-stage-sender'
CONTENT_STATE='/srv/coloring-pages-content/state'
STAGE_STATE="$CONTENT_STATE/drive-stage"
LOCK_PATH="$STAGE_STATE/.lock"

for command_name in awk getent git id install python3 runuser stat visudo; do
    command -v "$command_name" >/dev/null 2>&1 \
        || fail "required command is missing: $command_name"
done

id "$OWNER" >/dev/null 2>&1 || fail 'operator owner user is missing'
OWNER_HOME="$(getent passwd "$OWNER" | awk -F: 'NR == 1 {print $6}')"
[[ "$OWNER_HOME" == /* && -d "$OWNER_HOME" && ! -L "$OWNER_HOME" ]] \
    || fail 'operator owner home is missing or unsafe'
if [[ -z "$SOURCE_ROOT" ]]; then
    SOURCE_ROOT="$OWNER_HOME/RPi5_main"
fi
[[ "$SOURCE_ROOT" == /* && -d "$SOURCE_ROOT" && ! -L "$SOURCE_ROOT" ]] \
    || fail 'RPi5_main source root is missing or unsafe'

owner_git() {
    runuser -u "$OWNER" -- env \
        HOME="$OWNER_HOME" \
        PATH='/usr/local/bin:/usr/bin:/bin' \
        git -C "$SOURCE_ROOT" "$@"
}

HEAD_SHA="$(owner_git rev-parse HEAD)"
[[ "$HEAD_SHA" == "$EXPECTED_SHA" ]] || fail 'RPi5_main checkout does not match authorized SHA'
[[ "$(owner_git branch --show-current)" == main ]] || fail 'RPi5_main checkout must be on main'
[[ -z "$(owner_git status --porcelain=v1 --untracked-files=all)" ]] \
    || fail 'RPi5_main checkout must be clean'

for rel in "$SENDER_REL" "$WRAPPER_REL" "$SUDOERS_REL" "$CONTRACT_REL"; do
    owner_git ls-files --error-unmatch "$rel" >/dev/null \
        || fail "required source is not tracked: $rel"
    [[ -f "$SOURCE_ROOT/$rel" && ! -L "$SOURCE_ROOT/$rel" ]] \
        || fail "required source is missing or unsafe: $rel"
done

python3 - "$SOURCE_ROOT/$SENDER_REL" "$SOURCE_ROOT/$WRAPPER_REL" "$SOURCE_ROOT/$CONTRACT_REL" <<'PY'
import json
from pathlib import Path
import sys

sender, wrapper, contract = map(Path, sys.argv[1:])
compile(sender.read_text(encoding="utf-8"), str(sender), "exec")
compile(wrapper.read_text(encoding="utf-8"), str(wrapper), "exec")
raw = json.loads(contract.read_text(encoding="utf-8"))
assert raw["schema"] == "rozkalns.rpi5-main.coloring-pages-drive-stage-sender.v1"
assert raw["status"] == "source-defined-not-installed"
PY

visudo -cf "$SOURCE_ROOT/$SUDOERS_REL" >/dev/null \
    || fail 'sudoers source validation failed'

[[ -d "$CONTENT_STATE" && ! -L "$CONTENT_STATE" ]] \
    || fail 'content state directory is missing or unsafe'
[[ "$(stat -c '%U:%G:%a' "$CONTENT_STATE")" == 'andris:andris:755' ]] \
    || fail 'content state directory metadata drifted'

STATE_CREATED=false
LOCK_CREATED=false
if [[ -e "$STAGE_STATE" || -L "$STAGE_STATE" ]]; then
    [[ -d "$STAGE_STATE" && ! -L "$STAGE_STATE" ]] \
        || fail 'Drive stage state path is unsafe'
    [[ "$(stat -c '%U:%G:%a' "$STAGE_STATE")" == 'andris:andris:755' ]] \
        || fail 'Drive stage state directory metadata drifted'
else
    install -d -o andris -g andris -m 0755 "$STAGE_STATE"
    STATE_CREATED=true
fi

if [[ -e "$LOCK_PATH" || -L "$LOCK_PATH" ]]; then
    [[ -f "$LOCK_PATH" && ! -L "$LOCK_PATH" ]] \
        || fail 'Drive stage lock path is unsafe'
    [[ "$(stat -c '%U:%G:%a' "$LOCK_PATH")" == 'andris:andris:600' ]] \
        || fail 'Drive stage lock metadata drifted'
else
    install -o andris -g andris -m 0600 /dev/null "$LOCK_PATH"
    LOCK_CREATED=true
fi

install -d -o root -g root -m 0755 /usr/local/libexec
install -o root -g root -m 0755 "$SOURCE_ROOT/$SENDER_REL" "$SENDER_DEST"
install -o root -g root -m 0755 "$SOURCE_ROOT/$WRAPPER_REL" "$WRAPPER_DEST"
install -o root -g root -m 0440 "$SOURCE_ROOT/$SUDOERS_REL" "$SUDOERS_DEST"
visudo -cf "$SUDOERS_DEST" >/dev/null || fail 'installed sudoers validation failed'

for pair in \
    "$SENDER_REL:$SENDER_DEST" \
    "$WRAPPER_REL:$WRAPPER_DEST"; do
    rel="${pair%%:*}"
    dest="${pair#*:}"
    expected_blob="$(owner_git rev-parse "HEAD:$rel")"
    [[ "$(git hash-object "$dest")" == "$expected_blob" ]] \
        || fail "installed source identity mismatch: $rel"
done

[[ "$(stat -c '%U:%G:%a' "$SENDER_DEST")" == 'root:root:755' ]] \
    || fail 'installed sender metadata mismatch'
[[ "$(stat -c '%U:%G:%a' "$WRAPPER_DEST")" == 'root:root:755' ]] \
    || fail 'installed wrapper metadata mismatch'
[[ "$(stat -c '%U:%G:%a' "$SUDOERS_DEST")" == 'root:root:440' ]] \
    || fail 'installed sudoers metadata mismatch'

printf 'COLORING_PAGES_DRIVE_STAGE_INSTALL=PASS\n'
printf 'SOURCE_SHA=%s\n' "$HEAD_SHA"
printf 'STATE_CREATED=%s\n' "$STATE_CREATED"
printf 'LOCK_CREATED=%s\n' "$LOCK_CREATED"
printf 'RCLONE_EXECUTED=false\n'
printf 'DRIVE_WRITE=false\n'
printf 'CREDENTIAL_CONTENT_READ=false\n'
printf 'RCLONE_CONFIG_CHANGED=false\n'
printf 'INGEST_EXECUTED=false\n'
printf 'SYSTEMD_CHANGED=false\n'
