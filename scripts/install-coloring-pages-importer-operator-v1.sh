#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077
PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
export PATH

fail() {
    printf 'COLORING_PAGES_IMPORTER_INSTALL=FAIL error=%s\n' "$*" >&2
    exit 1
}

usage() {
    cat >&2 <<'USAGE'
Usage: sudo bash scripts/install-coloring-pages-importer-operator-v1.sh \
  --expected-rpi5-main-sha <40-hex-sha> \
  [--source-root /home/andris/RPi5_main]
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
OPERATOR_REL='ops/bin/coloring-pages-import'
DEST='/usr/local/bin/coloring-pages-import'

for command_name in bash getent git id install runuser stat; do
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
    || fail 'operator source is not tracked'
[[ -f "$SOURCE_ROOT/$OPERATOR_REL" && ! -L "$SOURCE_ROOT/$OPERATOR_REL" ]] \
    || fail 'operator source is missing or unsafe'
bash -n "$SOURCE_ROOT/$OPERATOR_REL"

EXPECTED_BLOB="$(owner_git rev-parse "HEAD:$OPERATOR_REL")"
install -o root -g root -m 0755 "$SOURCE_ROOT/$OPERATOR_REL" "$DEST"
[[ -f "$DEST" && ! -L "$DEST" ]] || fail 'installed operator is missing or unsafe'
[[ "$(stat -c '%U:%G:%a' "$DEST")" == 'root:root:755' ]] \
    || fail 'installed operator metadata mismatch'
[[ "$(git hash-object "$DEST")" == "$EXPECTED_BLOB" ]] \
    || fail 'installed operator identity mismatch'

printf 'COLORING_PAGES_IMPORTER_INSTALL=PASS\n'
printf 'SOURCE_SHA=%s\n' "$HEAD_SHA"
printf 'OPERATOR_BLOB=%s\n' "$EXPECTED_BLOB"
printf 'DESTINATION=%s\n' "$DEST"
printf 'DOCKER_EXECUTED=false\n'
printf 'CONTENT_MUTATED=false\n'
printf 'SYSTEMD_CHANGED=false\n'
