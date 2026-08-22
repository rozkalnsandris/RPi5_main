#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

export PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'

readonly OWNER='andris'
readonly REPOSITORY='rozkalnsandris/RPi5_main'
readonly WORKFLOW='validate.yml'
readonly BROKER='/usr/local/sbin/rozkalns-github-app-read-token'

readonly CHECKER_REL='ops/bin/rpi5-tmp-headroom'
readonly SERVICE_REL='ops/systemd/rpi5-tmp-headroom.service'
readonly TIMER_REL='ops/systemd/rpi5-tmp-headroom.timer'
readonly OPERATOR_REL='scripts/activate-tmp-headroom-monitor.sh'

readonly CHECKER_BLOB='e342b3eabdcabb87d1201c7568458fd2bb76cfe6'
readonly SERVICE_BLOB='deec01cca3f0599b58fd421bb3b5d7b4bfa1aec7'
readonly TIMER_BLOB='6898909484485f3db7fd6967c687b192319b6e28'

readonly CHECKER_DEST='/usr/local/sbin/rpi5-tmp-headroom'
readonly SERVICE_DEST='/etc/systemd/system/rpi5-tmp-headroom.service'
readonly TIMER_DEST='/etc/systemd/system/rpi5-tmp-headroom.timer'
readonly SERVICE_UNIT='rpi5-tmp-headroom.service'
readonly TIMER_UNIT='rpi5-tmp-headroom.timer'
readonly EXPECTED_TMP_MOUNT_FRAGMENT='/run/systemd/generator/tmp.mount'

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

unit_enabled() {
    systemctl is-enabled "$1" 2>/dev/null || true
}

unit_active() {
    systemctl is-active "$1" 2>/dev/null || true
}

unit_fragment() {
    systemctl show -p FragmentPath --value "$1" 2>/dev/null || true
}

hash_blob() {
    git hash-object "$1"
}

assert_installed_file() {
    local path="$1"
    local expected_blob="$2"
    local expected_meta="$3"

    [[ -f "$path" && ! -L "$path" ]] || fail "installed artifact is missing or unsafe: $path"
    [[ "$(stat -c '%U:%G:%a' "$path")" == "$expected_meta" ]] \
        || fail "installed artifact ownership/mode is unexpected: $path"
    [[ "$(hash_blob "$path")" == "$expected_blob" ]] \
        || fail "installed artifact blob mismatch: $path"
}

require_remote_main_and_ci() {
    local token remote_json remote_sha runs_json run_id jobs_json

    unset GH_TOKEN GITHUB_TOKEN
    token="$("$BROKER" --repository "$REPOSITORY")" \
        || fail 'GitHub App read token is unavailable'
    [[ ${#token} -ge 20 && "$token" != *[[:space:]]* ]] \
        || fail 'GitHub App read token is malformed'

    remote_json="$(GH_TOKEN="$token" gh api "repos/$REPOSITORY/branches/main")"
    remote_sha="$(printf '%s' "$remote_json" | python3 -c '
import json
import sys
print(json.load(sys.stdin)["commit"]["sha"])
')"
    [[ "$remote_sha" =~ ^[0-9a-f]{40}$ ]] || fail 'remote main SHA is malformed'

    runs_json="$(GH_TOKEN="$token" gh api \
        "repos/$REPOSITORY/actions/workflows/$WORKFLOW/runs?branch=main&head_sha=$remote_sha&status=completed&per_page=100")"
    run_id="$(printf '%s' "$runs_json" | python3 -c '
import json
import sys
sha = sys.argv[1]
runs = json.load(sys.stdin).get("workflow_runs", [])
valid = [
    row for row in runs
    if row.get("event") == "push"
    and row.get("head_branch") == "main"
    and row.get("head_sha") == sha
    and row.get("status") == "completed"
    and row.get("conclusion") == "success"
]
print(max((int(row["id"]) for row in valid), default=""))
' "$remote_sha")"
    [[ "$run_id" =~ ^[1-9][0-9]*$ ]] || fail 'exact-main push Validate is not successful'

    jobs_json="$(GH_TOKEN="$token" gh api \
        "repos/$REPOSITORY/actions/runs/$run_id/jobs?filter=latest&per_page=100")"
    printf '%s' "$jobs_json" | python3 -c '
import json
import sys
jobs = json.load(sys.stdin).get("jobs", [])
passed = {
    row.get("name")
    for row in jobs
    if row.get("status") == "completed"
    and row.get("conclusion") == "success"
}
required = {
    "validate",
    "gitleaks",
    "public-automation-baseline / public automation policy",
}
missing = required - passed
if missing:
    raise SystemExit("missing exact-main jobs: " + ",".join(sorted(missing)))
'

    unset token remote_json runs_json jobs_json GH_TOKEN GITHUB_TOKEN
    printf '%s %s\n' "$remote_sha" "$run_id"
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail 'run the /tmp monitor activation operator as root'

for command_name in gh git getent id install python3 rm runuser stat systemctl systemd-analyze; do
    command -v "$command_name" >/dev/null 2>&1 \
        || fail "required command is missing: $command_name"
done
[[ -x "$BROKER" && ! -L "$BROKER" ]] || fail 'GitHub App read-token broker is missing or unsafe'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
owner_home="$(getent passwd "$OWNER" | awk -F: 'NR == 1 {print $6}')"
[[ "$owner_home" == /* && -d "$owner_home" && ! -L "$owner_home" ]] \
    || fail 'owner home directory is missing or unsafe'
readonly repo owner_home

owner_git() {
    runuser -u "$OWNER" -- env \
        HOME="$owner_home" \
        PATH='/usr/local/bin:/usr/bin:/bin' \
        git -C "$repo" "$@"
}

[[ -e "$repo/.git" && ! -L "$repo/.git" ]] || fail 'operator must run from an RPi5_main checkout'
[[ "$(owner_git branch --show-current)" == main ]] || fail 'RPi5_main checkout is not on main'
[[ -z "$(owner_git status --porcelain=v1 --untracked-files=all)" ]] \
    || fail 'RPi5_main checkout is not clean'

read -r remote_main ci_run_id < <(require_remote_main_and_ci)
local_head="$(owner_git rev-parse HEAD)"
[[ "$local_head" == "$remote_main" ]] || fail 'local checkout is not exact current GitHub main'

operator_blob="$(owner_git rev-parse "HEAD:$OPERATOR_REL")"
[[ "$(hash_blob "$0")" == "$operator_blob" ]] || fail 'executed operator bytes do not match current main'

for spec in \
    "$CHECKER_REL:$CHECKER_BLOB" \
    "$SERVICE_REL:$SERVICE_BLOB" \
    "$TIMER_REL:$TIMER_BLOB"
do
    rel="${spec%%:*}"
    expected="${spec#*:}"
    [[ "$(owner_git rev-parse "HEAD:$rel")" == "$expected" ]] \
        || fail "reviewed source blob changed: $rel"
done

printf 'RPI5_MAIN_EXACT_SHA=%s\n' "$local_head"
printf 'RPI5_MAIN_EXACT_SHA_CI=PASS run=%s\n' "$ci_run_id"
printf 'MONITOR_SOURCE_BLOBS=PASS\n'

systemd_version="$(systemctl --version | awk 'NR == 1 {print $2}')"
[[ "$systemd_version" == '252' ]] || fail "unexpected systemd major version: $systemd_version"
tmp_mount_fragment="$(unit_fragment tmp.mount)"
[[ "$tmp_mount_fragment" == "$EXPECTED_TMP_MOUNT_FRAGMENT" ]] \
    || fail "unexpected tmp.mount fragment: ${tmp_mount_fragment:-none}"

for path in "$CHECKER_DEST" "$SERVICE_DEST" "$TIMER_DEST"; do
    [[ ! -e "$path" && ! -L "$path" ]] || fail "activation baseline is not absent: $path"
done
[[ -z "$(unit_fragment "$SERVICE_UNIT")" ]] || fail 'monitor service already has a loaded fragment'
[[ -z "$(unit_fragment "$TIMER_UNIT")" ]] || fail 'monitor timer already has a loaded fragment'
[[ "$(unit_active "$SERVICE_UNIT")" != active ]] || fail 'monitor service is already active'
[[ "$(unit_active "$TIMER_UNIT")" != active ]] || fail 'monitor timer is already active'
case "$(unit_enabled "$TIMER_UNIT")" in
    enabled|enabled-runtime|linked|linked-runtime|alias)
        fail 'monitor timer is already enabled or linked'
        ;;
esac

runuser -u "$OWNER" -- env \
    HOME="$owner_home" \
    PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
    "$repo/$CHECKER_REL"
printf 'PRE_ACTIVATION_TMP_POLICY=PASS\n'
printf 'PRE_ACTIVATION_BASELINE=ABSENT_INACTIVE\n'

mutation_started=false
activation_complete=false
rollback_status='NOT_REQUIRED'

rollback() {
    local ok=true
    set +e

    systemctl disable --now "$TIMER_UNIT" >/dev/null 2>&1 || true
    systemctl stop "$SERVICE_UNIT" >/dev/null 2>&1 || true
    rm -f -- "$TIMER_DEST" "$SERVICE_DEST" "$CHECKER_DEST"
    systemctl daemon-reload
    systemctl reset-failed "$SERVICE_UNIT" "$TIMER_UNIT" >/dev/null 2>&1 || true

    for path in "$CHECKER_DEST" "$SERVICE_DEST" "$TIMER_DEST"; do
        if [[ -e "$path" || -L "$path" ]]; then
            ok=false
        fi
    done
    if [[ "$(unit_active "$SERVICE_UNIT")" == active || "$(unit_active "$TIMER_UNIT")" == active ]]; then
        ok=false
    fi
    case "$(unit_enabled "$TIMER_UNIT")" in
        enabled|enabled-runtime|linked|linked-runtime|alias)
            ok=false
            ;;
    esac

    if [[ "$ok" == true ]]; then
        rollback_status='PASS'
        printf 'TMP_MONITOR_ACTIVATION_ROLLBACK=PASS\n' >&2
        return 0
    fi

    rollback_status='FAIL'
    printf 'TMP_MONITOR_ACTIVATION_ROLLBACK=FAIL\n' >&2
    return 1
}

on_exit() {
    local rc=$?
    trap - EXIT

    if (( rc != 0 )) && [[ "$mutation_started" == true ]] && [[ "$activation_complete" != true ]]; then
        if ! rollback; then
            exit 2
        fi
    fi
    exit "$rc"
}
trap on_exit EXIT

mutation_started=true

install -o root -g root -m 0755 "$repo/$CHECKER_REL" "$CHECKER_DEST"
install -o root -g root -m 0644 "$repo/$SERVICE_REL" "$SERVICE_DEST"
install -o root -g root -m 0644 "$repo/$TIMER_REL" "$TIMER_DEST"

assert_installed_file "$CHECKER_DEST" "$CHECKER_BLOB" 'root:root:755'
assert_installed_file "$SERVICE_DEST" "$SERVICE_BLOB" 'root:root:644'
assert_installed_file "$TIMER_DEST" "$TIMER_BLOB" 'root:root:644'
printf 'MONITOR_ARTIFACT_INSTALL=PASS\n'

systemctl daemon-reload
systemd-analyze verify "$SERVICE_DEST" "$TIMER_DEST"
printf 'MONITOR_SYSTEMD_VERIFY=PASS\n'

"$CHECKER_DEST"
printf 'MONITOR_DIRECT_CANARY=PASS\n'

systemctl start "$SERVICE_UNIT"
[[ "$(systemctl show -p Result --value "$SERVICE_UNIT")" == success ]] \
    || fail 'monitor service canary result is not success'
[[ "$(systemctl show -p ExecMainStatus --value "$SERVICE_UNIT")" == 0 ]] \
    || fail 'monitor service canary exit status is not zero'
printf 'MONITOR_SERVICE_CANARY=PASS\n'

systemctl enable --now "$TIMER_UNIT"
[[ "$(unit_enabled "$TIMER_UNIT")" == enabled ]] || fail 'monitor timer is not enabled'
[[ "$(unit_active "$TIMER_UNIT")" == active ]] || fail 'monitor timer is not active'
printf 'MONITOR_TIMER_ACTIVATION=PASS\n'

"$CHECKER_DEST"
printf 'POST_ACTIVATION_TMP_POLICY=PASS\n'

activation_complete=true
printf 'RESULT=PASS\n'
printf 'RPI5_MAIN_EXACT_SHA=%s\n' "$local_head"
printf 'RPI5_MAIN_EXACT_SHA_CI_RUN=%s\n' "$ci_run_id"
printf 'ROLLBACK=%s\n' "$rollback_status"
