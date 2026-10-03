#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077
PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
export PATH

fail() {
    printf 'COLORING_PAGES_DRIVE_INGEST_INSTALL=FAIL error=%s\n' "$*" >&2
    exit 1
}

usage() {
    cat >&2 <<'USAGE'
Usage: sudo bash scripts/install-coloring-pages-drive-ingest-operator-v1.sh \
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
OPERATOR_REL='ops/bin/coloring-pages-drive-ingest'
DEST='/usr/local/bin/coloring-pages-drive-ingest'
CONTENT_STATE='/srv/coloring-pages-content/state'
INGEST_STATE="$CONTENT_STATE/drive-ingest"
LOCK_PATH="$INGEST_STATE/.lock"

for command_name in awk getent git id install python3 runuser stat; do
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
owner_git ls-files --error-unmatch "$OPERATOR_REL" >/dev/null \
    || fail 'Drive ingest operator source is not tracked'
[[ -f "$SOURCE_ROOT/$OPERATOR_REL" && ! -L "$SOURCE_ROOT/$OPERATOR_REL" ]] \
    || fail 'Drive ingest operator source is missing or unsafe'

python3 - "$SOURCE_ROOT/$OPERATOR_REL" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
compile(path.read_text(encoding="utf-8"), str(path), "exec")
PY

[[ -d "$CONTENT_STATE" && ! -L "$CONTENT_STATE" ]] \
    || fail 'content state directory is missing or unsafe'
[[ "$(stat -c '%U:%G:%a' "$CONTENT_STATE")" == 'andris:andris:755' ]] \
    || fail 'content state directory metadata drifted'

STATE_CREATED=false
LOCK_CREATED=false
if [[ -e "$INGEST_STATE" || -L "$INGEST_STATE" ]]; then
    [[ -d "$INGEST_STATE" && ! -L "$INGEST_STATE" ]] \
        || fail 'Drive ingest state path is unsafe'
    [[ "$(stat -c '%U:%G:%a' "$INGEST_STATE")" == 'andris:andris:755' ]] \
        || fail 'Drive ingest state directory metadata drifted'
else
    install -d -o andris -g andris -m 0755 "$INGEST_STATE"
    STATE_CREATED=true
fi

if [[ -e "$LOCK_PATH" || -L "$LOCK_PATH" ]]; then
    [[ -f "$LOCK_PATH" && ! -L "$LOCK_PATH" ]] \
        || fail 'Drive ingest lock path is unsafe'
    [[ "$(stat -c '%U:%G:%a' "$LOCK_PATH")" == 'andris:andris:600' ]] \
        || fail 'Drive ingest lock metadata drifted'
else
    install -o andris -g andris -m 0600 /dev/null "$LOCK_PATH"
    LOCK_CREATED=true
fi

EXPECTED_BLOB="$(owner_git rev-parse "HEAD:$OPERATOR_REL")"
install -o root -g root -m 0755 "$SOURCE_ROOT/$OPERATOR_REL" "$DEST"
[[ -f "$DEST" && ! -L "$DEST" ]] || fail 'installed Drive ingest operator is missing or unsafe'
[[ "$(stat -c '%U:%G:%a' "$DEST")" == 'root:root:755' ]] \
    || fail 'installed Drive ingest operator metadata mismatch'
[[ "$(git hash-object "$DEST")" == "$EXPECTED_BLOB" ]] \
    || fail 'installed Drive ingest operator identity mismatch'

printf 'COLORING_PAGES_DRIVE_INGEST_INSTALL=PASS\n'
printf 'SOURCE_SHA=%s\n' "$HEAD_SHA"
printf 'OPERATOR_BLOB=%s\n' "$EXPECTED_BLOB"
printf 'DESTINATION=%s\n' "$DEST"
printf 'STATE_CREATED=%s\n' "$STATE_CREATED"
printf 'LOCK_CREATED=%s\n' "$LOCK_CREATED"
printf 'RCLONE_CONFIG_CHANGED=false\n'
printf 'SUDOERS_CHANGED=false\n'
printf 'RCLONE_EXECUTED=false\n'
printf 'CONTENT_IMPORTED=false\n'
printf 'SYSTEMD_CHANGED=false\n'
