#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077
PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
export PATH

fail() {
    printf 'COLORING_PAGES_PUBLISH_REQUEST_BRIDGE_INSTALL=FAIL error=%s\n' "$*" >&2
    exit 1
}

usage() {
    cat >&2 <<'USAGE'
Usage: sudo bash scripts/install-coloring-pages-publish-request-bridge-v1.sh \
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
DISPATCHER_REL='ops/bin/coloring-pages-publish-request-dispatcher'
CONTRACT_REL='ops/contracts/coloring-pages-publish-request-bridge-v1.json'
PATH_REL='ops/systemd/coloring-pages-publish-request-bridge.path'
SERVICE_REL='ops/systemd/coloring-pages-publish-request-bridge.service'
INGEST_REL='ops/bin/coloring-pages-drive-ingest'

DISPATCHER_DEST='/usr/local/bin/coloring-pages-publish-request-dispatcher'
PATH_DEST='/etc/systemd/system/coloring-pages-publish-request-bridge.path'
SERVICE_DEST='/etc/systemd/system/coloring-pages-publish-request-bridge.service'
INGEST_DEST='/usr/local/bin/coloring-pages-drive-ingest'

CONTENT_STATE='/srv/coloring-pages-content/state'
BRIDGE_STATE="$CONTENT_STATE/publish-request-bridge"
INCOMING="$BRIDGE_STATE/incoming"
CLAIMED="$BRIDGE_STATE/claimed"
RESULTS="$BRIDGE_STATE/results"
LOCK="$BRIDGE_STATE/.lock"

for command_name in awk find getent git id install python3 runuser stat systemctl; do
    command -v "$command_name" >/dev/null 2>&1 \
        || fail "required command is missing: $command_name"
done

id "$OWNER" >/dev/null 2>&1 || fail 'bridge owner user is missing'
OWNER_HOME="$(getent passwd "$OWNER" | awk -F: 'NR == 1 {print $6}')"
[[ "$OWNER_HOME" == /* && -d "$OWNER_HOME" && ! -L "$OWNER_HOME" ]] \
    || fail 'bridge owner home is missing or unsafe'
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

for rel in "$DISPATCHER_REL" "$CONTRACT_REL" "$PATH_REL" "$SERVICE_REL" "$INGEST_REL"; do
    owner_git ls-files --error-unmatch "$rel" >/dev/null \
        || fail "required source is not tracked: $rel"
    [[ -f "$SOURCE_ROOT/$rel" && ! -L "$SOURCE_ROOT/$rel" ]] \
        || fail "required source is missing or unsafe: $rel"
done

python3 - "$SOURCE_ROOT/$DISPATCHER_REL" "$SOURCE_ROOT/$CONTRACT_REL" <<'PY'
from pathlib import Path
import json
import sys

dispatcher = Path(sys.argv[1])
contract = Path(sys.argv[2])
compile(dispatcher.read_text(encoding="utf-8"), str(dispatcher), "exec")
data = json.loads(contract.read_text(encoding="utf-8"))
if data.get("schema") != "rozkalns.rpi5-main.coloring-pages-publish-request-bridge.v1":
    raise SystemExit("bridge contract schema mismatch")
PY

[[ -f "$INGEST_DEST" && ! -L "$INGEST_DEST" ]] \
    || fail 'installed Drive ingest operator is missing or unsafe'
[[ "$(stat -c '%U:%G:%a' "$INGEST_DEST")" == 'root:root:755' ]] \
    || fail 'installed Drive ingest operator metadata mismatch'
EXPECTED_INGEST_BLOB="$(owner_git rev-parse "HEAD:$INGEST_REL")"
[[ "$(git hash-object "$INGEST_DEST")" == "$EXPECTED_INGEST_BLOB" ]] \
    || fail 'installed Drive ingest operator identity mismatch'

[[ -d "$CONTENT_STATE" && ! -L "$CONTENT_STATE" ]] \
    || fail 'content state directory is missing or unsafe'
[[ "$(stat -c '%U:%G:%a' "$CONTENT_STATE")" == 'andris:andris:755' ]] \
    || fail 'content state directory metadata drifted'

ensure_dir() {
    local path="$1"
    if [[ -e "$path" || -L "$path" ]]; then
        [[ -d "$path" && ! -L "$path" ]] || fail "unsafe bridge directory: $path"
        [[ "$(stat -c '%U:%G:%a' "$path")" == 'andris:andris:755' ]] \
            || fail "bridge directory metadata drifted: $path"
    else
        install -d -o andris -g andris -m 0755 "$path"
    fi
}

ensure_dir "$BRIDGE_STATE"
ensure_dir "$INCOMING"
ensure_dir "$CLAIMED"
ensure_dir "$RESULTS"

if [[ -e "$LOCK" || -L "$LOCK" ]]; then
    [[ -f "$LOCK" && ! -L "$LOCK" ]] || fail 'bridge lock path is unsafe'
    [[ "$(stat -c '%U:%G:%a' "$LOCK")" == 'andris:andris:600' ]] \
        || fail 'bridge lock metadata drifted'
else
    install -o andris -g andris -m 0600 /dev/null "$LOCK"
fi

if [[ -n "$(find "$INCOMING" -maxdepth 1 -type f -name 'batch-*.ready' -print -quit)" ]]; then
    fail 'ready marker exists before bridge activation'
fi

EXPECTED_DISPATCHER_BLOB="$(owner_git rev-parse "HEAD:$DISPATCHER_REL")"
install -o root -g root -m 0755 "$SOURCE_ROOT/$DISPATCHER_REL" "$DISPATCHER_DEST"
[[ "$(git hash-object "$DISPATCHER_DEST")" == "$EXPECTED_DISPATCHER_BLOB" ]] \
    || fail 'installed dispatcher identity mismatch'

install -o root -g root -m 0644 "$SOURCE_ROOT/$PATH_REL" "$PATH_DEST"
install -o root -g root -m 0644 "$SOURCE_ROOT/$SERVICE_REL" "$SERVICE_DEST"

systemctl daemon-reload
systemctl enable --now coloring-pages-publish-request-bridge.path >/dev/null
[[ "$(systemctl is-enabled coloring-pages-publish-request-bridge.path)" == enabled ]] \
    || fail 'bridge path unit is not enabled'
[[ "$(systemctl is-active coloring-pages-publish-request-bridge.path)" == active ]] \
    || fail 'bridge path unit is not active'

printf 'COLORING_PAGES_PUBLISH_REQUEST_BRIDGE_INSTALL=PASS\n'
printf 'SOURCE_SHA=%s\n' "$HEAD_SHA"
printf 'DISPATCHER_BLOB=%s\n' "$EXPECTED_DISPATCHER_BLOB"
printf 'INGEST_OPERATOR_BLOB=%s\n' "$EXPECTED_INGEST_BLOB"
printf 'PATH_UNIT=enabled-active\n'
printf 'CREDENTIALS_CHANGED=false\n'
printf 'SUDOERS_CHANGED=false\n'
printf 'DRIVE_MUTATED=false\n'
printf 'INGEST_EXECUTED=false\n'
printf 'DOCKER_EXECUTED=false\n'
printf 'NETWORK_CHANGED=false\n'
