#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077
PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
export PATH

readonly OWNER='andris'
readonly RPI_REPOSITORY='rozkalnsandris/RPi5_main'
readonly CV_REPOSITORY='rozkalnsandris/rozkalns-cv'
readonly TARGET_CV_SHA='4a0069a97022841da07a687a197ea8cfacc56cd6'
readonly EXPECTED_PRODUCTION_SHA='f5431265232f356fa27f6204f0cba56e1e730928'
readonly OLD_CLASSIFIER_BLOB='e9020c00328122a1a028c9734002f0ea1c956f2f'
readonly TARGET_CLASSIFIER_BLOB='7fb09d469eaeb574b2bba39474cc7a6bb55504da'
readonly TARGET_PREFLIGHT_BLOB='2592e4e38e933f01409d5816c05defd22e661f6c'
readonly TARGET_PULL_LIBRARY_BLOB='ade60abbfea3cf56b1a56bbc1b2e0669b1a1b983'
readonly TARGET_PULL_WRAPPER_BLOB='ddaa8c7f8c0776e77be18b2cd5ea8a9489900e70'
readonly BROKER='/usr/local/sbin/rozkalns-github-app-read-token'
readonly CLASSIFIER='/usr/local/libexec/rozkalns-cv/classify-deploy-impact'
readonly PREFLIGHT='/usr/local/sbin/rozkalns-cv-pull-deploy-preflight'
readonly PULL_LIBRARY='/usr/local/libexec/rozkalns-cv/rozkalns-cv-deploy-library'
readonly PULL_WRAPPER='/usr/local/sbin/rozkalns-cv-pull-deploy-main'
readonly LEGACY_HELPER='/usr/local/sbin/rozkalns-cv-deploy-main'
readonly PRODUCTION_STATE='/var/lib/rozkalns-cv-deploy/current-sha'
readonly TIMER_UNIT='rozkalns-cv-pull-deploy.timer'
readonly SERVICE_UNIT='rozkalns-cv-pull-deploy.service'
readonly CLASSIFIER_REL='runner/pull-deploy/classify_deploy_impact.py'
readonly PREFLIGHT_REL='runner/pull-deploy/rozkalns-cv-pull-deploy-preflight'
readonly PULL_LIBRARY_REL='runner/release/rozkalns-cv-deploy-main'
readonly PULL_WRAPPER_REL='runner/release/rozkalns-cv-pull-deploy-main'
readonly LOCAL_URL='http://127.0.0.1:8088/'
readonly PUBLIC_URL='https://rozkalns.net/'

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail 'run classifier alignment operator as root'

for command_name in awk cp curl flock getent gh git id install mktemp python3 rm runuser stat systemctl tr; do
    command -v "$command_name" >/dev/null 2>&1 \
        || fail "required command is missing: $command_name"
done

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
owner_home="$(getent passwd "$OWNER" | awk -F: 'NR == 1 {print $6}')"
[[ "$owner_home" == /* && -d "$owner_home" && ! -L "$owner_home" ]] \
    || fail 'owner home directory is missing or unsafe'
readonly repo owner_home
readonly cv_source="$owner_home/rozkalns-cv-worktrees/release-control"

owner_git_rpi() {
    runuser -u "$OWNER" -- env HOME="$owner_home" PATH='/usr/local/bin:/usr/bin:/bin' \
        git -C "$repo" "$@"
}

owner_git_cv() {
    runuser -u "$OWNER" -- env HOME="$owner_home" PATH='/usr/local/bin:/usr/bin:/bin' \
        git -C "$cv_source" "$@"
}

unit_enabled() {
    systemctl is-enabled "$1" 2>/dev/null || true
}

unit_active() {
    systemctl is-active "$1" 2>/dev/null || true
}

hash_blob() {
    git hash-object "$1"
}

extract_field() {
    local key="$1"
    local payload="$2"
    printf '%s\n' "$payload" \
        | awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}'
}

require_exact_main_ci() {
    local repository="$1"
    local sha="$2"
    local mode="$3"
    local workflow="$4"
    local token runs_json run_id jobs_json

    unset GH_TOKEN GITHUB_TOKEN
    token="$("$BROKER" --repository "$repository")" \
        || fail "GitHub App token unavailable for $repository"
    [[ ${#token} -ge 20 && "$token" != *[[:space:]]* ]] \
        || fail "GitHub App token malformed for $repository"

    runs_json="$(GH_TOKEN="$token" gh api \
        "repos/$repository/actions/workflows/$workflow/runs?branch=main&head_sha=$sha&status=completed&per_page=100")"
    run_id="$(printf '%s' "$runs_json" | python3 -c '
import json
import sys
sha = sys.argv[1]
runs = json.load(sys.stdin).get("workflow_runs", [])
ok = [
    row for row in runs
    if row.get("event") == "push"
    and row.get("head_branch") == "main"
    and row.get("head_sha") == sha
    and row.get("status") == "completed"
    and row.get("conclusion") == "success"
]
print(max((int(row["id"]) for row in ok), default=""))
' "$sha")"
    [[ "$run_id" =~ ^[1-9][0-9]*$ ]] \
        || fail "no successful exact-main CI run for $repository@$sha"

    jobs_json="$(GH_TOKEN="$token" gh api \
        "repos/$repository/actions/runs/$run_id/jobs?filter=latest&per_page=100")"
    printf '%s' "$jobs_json" | python3 -c '
import json
import sys
mode = sys.argv[1]
jobs = json.load(sys.stdin).get("jobs", [])
passed = {
    row.get("name")
    for row in jobs
    if row.get("status") == "completed"
    and row.get("conclusion") == "success"
}
required = (
    {"validate", "gitleaks", "public-automation-baseline / public automation policy"}
    if mode == "rpi"
    else {"validate"}
)
missing = required - passed
if missing:
    raise SystemExit("missing exact-main jobs: " + ",".join(sorted(missing)))
' "$mode"

    unset token runs_json jobs_json GH_TOKEN GITHUB_TOKEN
    printf '%s\n' "$run_id"
}

assert_installed_artifact() {
    local path="$1"
    local expected_blob="$2"
    [[ -f "$path" && -x "$path" && ! -L "$path" ]] \
        || fail "installed artifact is missing or unsafe: $path"
    [[ "$(stat -c '%U:%G:%a' "$path")" == 'root:root:755' ]] \
        || fail "installed artifact ownership/mode is unexpected: $path"
    [[ "$(hash_blob "$path")" == "$expected_blob" ]] \
        || fail "installed artifact blob mismatch: $path"
}

http_ok() {
    local url="$1"
    curl --fail --silent --show-error --max-time 20 "$url" >/dev/null
}

exec 9>/run/lock/rozkalns-cv-classifier-alignment.lock
flock -n 9 || fail 'another classifier alignment is already running'

[[ -d "$repo/.git" ]] || fail 'operator must run from the RPi5_main checkout'
[[ "$(owner_git_rpi branch --show-current)" == main ]] || fail 'RPi5_main checkout is not on main'
[[ -z "$(owner_git_rpi status --porcelain=v1 --untracked-files=all)" ]] \
    || fail 'RPi5_main checkout is not clean'
owner_git_rpi fetch --prune origin main
rpi_head="$(owner_git_rpi rev-parse HEAD)"
rpi_remote="$(owner_git_rpi rev-parse refs/remotes/origin/main)"
[[ "$rpi_head" == "$rpi_remote" ]] || fail 'RPi5_main checkout is not exact current origin/main'
rpi_ci_run_id="$(require_exact_main_ci "$RPI_REPOSITORY" "$rpi_head" rpi validate.yml)"
printf 'RPI5_MAIN_EXACT_SHA=%s\n' "$rpi_head"
printf 'RPI5_MAIN_EXACT_SHA_CI=PASS run=%s\n' "$rpi_ci_run_id"

[[ -d "$cv_source" && ! -L "$cv_source" ]] || fail 'CV release-control worktree is missing or unsafe'
[[ -z "$(owner_git_cv branch --show-current)" ]] || fail 'CV release-control worktree must remain detached'
[[ -z "$(owner_git_cv status --porcelain=v1 --untracked-files=all)" ]] \
    || fail 'CV release-control worktree is not clean'
owner_git_cv fetch --prune origin main
cv_main="$(owner_git_cv rev-parse refs/remotes/origin/main)"
[[ "$cv_main" == "$TARGET_CV_SHA" ]] \
    || fail "CV origin/main moved from reviewed target: $cv_main"
cv_ci_run_id="$(require_exact_main_ci "$CV_REPOSITORY" "$TARGET_CV_SHA" cv ci.yml)"
printf 'CV_EXACT_MAIN_CI=PASS run=%s\n' "$cv_ci_run_id"

[[ -f "$PRODUCTION_STATE" && ! -L "$PRODUCTION_STATE" ]] \
    || fail 'CV production state file is missing or unsafe'
production_before="$(tr -d '[:space:]' < "$PRODUCTION_STATE")"
[[ "$production_before" == "$EXPECTED_PRODUCTION_SHA" ]] \
    || fail "CV production baseline changed: $production_before"

for spec in \
    "$CLASSIFIER_REL:$TARGET_CLASSIFIER_BLOB" \
    "$PREFLIGHT_REL:$TARGET_PREFLIGHT_BLOB" \
    "$PULL_LIBRARY_REL:$TARGET_PULL_LIBRARY_BLOB" \
    "$PULL_WRAPPER_REL:$TARGET_PULL_WRAPPER_BLOB"
do
    rel="${spec%%:*}"
    expected="${spec#*:}"
    actual="$(owner_git_cv rev-parse "$TARGET_CV_SHA:$rel")"
    [[ "$actual" == "$expected" ]] || fail "reviewed CV source blob changed: $rel"
done
printf 'CV_TARGET_OBJECT_IDENTITY=PASS\n'

assert_installed_artifact "$PREFLIGHT" "$TARGET_PREFLIGHT_BLOB"
assert_installed_artifact "$PULL_LIBRARY" "$TARGET_PULL_LIBRARY_BLOB"
assert_installed_artifact "$PULL_WRAPPER" "$TARGET_PULL_WRAPPER_BLOB"
assert_installed_artifact "$CLASSIFIER" "$OLD_CLASSIFIER_BLOB"
[[ -f "$LEGACY_HELPER" && -x "$LEGACY_HELPER" && ! -L "$LEGACY_HELPER" ]] \
    || fail 'legacy CV helper is missing or unsafe'
[[ "$(stat -c '%U:%G:%a' "$LEGACY_HELPER")" == 'root:root:755' ]] \
    || fail 'legacy CV helper ownership/mode is unexpected'
legacy_before="$(hash_blob "$LEGACY_HELPER")"
printf 'CV_INSTALLED_BASELINE_IDENTITY=PASS\n'

pre_timer_enabled="$(unit_enabled "$TIMER_UNIT")"
pre_timer_active="$(unit_active "$TIMER_UNIT")"
pre_service_active="$(unit_active "$SERVICE_UNIT")"
[[ "$pre_timer_enabled" != enabled ]] || fail 'CV pull timer is enabled'
[[ "$pre_timer_active" != active ]] || fail 'CV pull timer is active'
[[ "$pre_service_active" != active ]] || fail 'CV pull service is active'
[[ "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' cvbot 2>/dev/null || true)" == healthy ]] \
    || fail 'cvbot is not healthy before classifier alignment'
http_ok "$LOCAL_URL" || fail 'local CV health check failed before classifier alignment'
http_ok "$PUBLIC_URL" || fail 'public CV health check failed before classifier alignment'
printf 'PRE_ALIGNMENT_RUNTIME_HEALTH=PASS\n'

candidate="$(mktemp /run/rozkalns-cv-classifier-target.XXXXXXXX)"
backup="$(mktemp /run/rozkalns-cv-classifier-backup.XXXXXXXX)"
installed=false
rollback_status='NOT_REQUIRED'

cleanup() {
    local rc=$?
    trap - EXIT
    if (( rc != 0 )) && [[ "$installed" == true ]]; then
        if install -o root -g root -m 0755 "$backup" "$CLASSIFIER" \
           && [[ "$(hash_blob "$CLASSIFIER")" == "$OLD_CLASSIFIER_BLOB" ]]; then
            rollback_status='PASS'
            printf 'CV_CLASSIFIER_ALIGNMENT_ROLLBACK=PASS\n' >&2
        else
            rollback_status='FAIL'
            printf 'CV_CLASSIFIER_ALIGNMENT_ROLLBACK=FAIL\n' >&2
        fi
    fi
    rm -f -- "$candidate" "$backup"
    if (( rc != 0 )) && [[ "$rollback_status" == FAIL ]]; then
        exit 2
    fi
    exit "$rc"
}
trap cleanup EXIT

cp -- "$CLASSIFIER" "$backup"
[[ "$(hash_blob "$backup")" == "$OLD_CLASSIFIER_BLOB" ]] \
    || fail 'classifier rollback copy does not match approved old baseline'
owner_git_cv show "$TARGET_CV_SHA:$CLASSIFIER_REL" >"$candidate"
[[ "$(hash_blob "$candidate")" == "$TARGET_CLASSIFIER_BLOB" ]] \
    || fail 'staged target classifier blob mismatch'
python3 "$candidate" --help >/dev/null

install -o root -g root -m 0755 "$candidate" "$CLASSIFIER"
installed=true
assert_installed_artifact "$CLASSIFIER" "$TARGET_CLASSIFIER_BLOB"
printf 'CV_CLASSIFIER_ARTIFACT_INSTALL=PASS blob=%s\n' "$TARGET_CLASSIFIER_BLOB"

preflight_output="$(runuser -u "$OWNER" -- env \
    HOME="$owner_home" \
    PATH='/home/andris/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
    "$PREFLIGHT")" || fail 'post-install App-authenticated preflight failed'
preflight_result="$(extract_field PULL_DEPLOY_PREFLIGHT_RESULT "$preflight_output")"
preflight_target="$(extract_field TARGET_SHA "$preflight_output")"
preflight_production="$(extract_field PRODUCTION_SHA "$preflight_output")"
deploy_impact="$(extract_field DEPLOY_IMPACT "$preflight_output")"
control_changed="$(extract_field CONTROL_PLANE_CHANGED "$preflight_output")"
preflight_ci="$(extract_field CI_RUN_ID "$preflight_output")"
mutation_authorized="$(extract_field PRODUCTION_MUTATION_AUTHORIZED "$preflight_output")"

[[ "$preflight_result" == MANUAL_ROLLOUT_REQUIRED ]] \
    || fail "unexpected preflight result after classifier alignment: $preflight_result"
[[ "$preflight_target" == "$TARGET_CV_SHA" ]] || fail 'preflight target changed'
[[ "$preflight_production" == "$EXPECTED_PRODUCTION_SHA" ]] || fail 'preflight production baseline changed'
[[ "$deploy_impact" == MANUAL_ROLLOUT_REQUIRED ]] || fail 'preflight impact is not manual rollout'
[[ "$control_changed" == true ]] || fail 'preflight did not report control-plane change'
[[ "$preflight_ci" == "$cv_ci_run_id" ]] || fail 'preflight CI run does not match exact-main proof'
[[ "$mutation_authorized" == false ]] || fail 'preflight unexpectedly authorized production mutation'
printf 'POST_ALIGNMENT_PREFLIGHT=MANUAL_ROLLOUT_REQUIRED\n'
printf 'CONTROL_PLANE_CHANGED=true\n'
printf 'PRODUCTION_MUTATION_AUTHORIZED=false\n'

assert_installed_artifact "$PREFLIGHT" "$TARGET_PREFLIGHT_BLOB"
assert_installed_artifact "$PULL_LIBRARY" "$TARGET_PULL_LIBRARY_BLOB"
assert_installed_artifact "$PULL_WRAPPER" "$TARGET_PULL_WRAPPER_BLOB"
assert_installed_artifact "$CLASSIFIER" "$TARGET_CLASSIFIER_BLOB"
[[ "$(hash_blob "$LEGACY_HELPER")" == "$legacy_before" ]] || fail 'legacy CV helper changed during classifier alignment'
production_after="$(tr -d '[:space:]' < "$PRODUCTION_STATE")"
[[ "$production_after" == "$production_before" ]] || fail 'CV production state changed during classifier alignment'
[[ "$(unit_enabled "$TIMER_UNIT")" == "$pre_timer_enabled" ]] || fail 'CV pull timer enabled state changed'
[[ "$(unit_active "$TIMER_UNIT")" == "$pre_timer_active" ]] || fail 'CV pull timer active state changed'
[[ "$(unit_active "$SERVICE_UNIT")" == "$pre_service_active" ]] || fail 'CV pull service state changed'
[[ "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' cvbot 2>/dev/null || true)" == healthy ]] \
    || fail 'cvbot is not healthy after classifier alignment'
http_ok "$LOCAL_URL" || fail 'local CV health check failed after classifier alignment'
http_ok "$PUBLIC_URL" || fail 'public CV health check failed after classifier alignment'

printf 'CV_PRODUCTION_CHANGED=false\n'
printf 'LEGACY_CV_HELPER_MODIFIED=false\n'
printf 'PULL_TRANSPORT_MODIFIED=false\n'
printf 'CV_PULL_TIMER_ENABLED=%s\n' "$pre_timer_enabled"
printf 'CV_PULL_TIMER_ACTIVE=%s\n' "$pre_timer_active"
printf 'CV_PULL_SERVICE_ACTIVE=%s\n' "$pre_service_active"
printf 'CVBOT_HEALTH=healthy\n'
printf 'LOCAL_SITE=PASS\n'
printf 'PUBLIC_SITE=PASS\n'
printf 'PHASE3_163_CLASSIFIER_HOST_ALIGNMENT=PASS\n'

installed=false
