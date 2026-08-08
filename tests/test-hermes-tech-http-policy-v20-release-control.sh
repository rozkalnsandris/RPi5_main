#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

bootstrap="ops/bin/hermes-tech-http-policy-v20-release-control"
fail() {
  echo "Hermes Tech V20 release-control test: FAIL: $*" >&2
  exit 1
}

[[ -f "$bootstrap" ]] || fail "missing release-control bootstrap"
bash -n "$bootstrap" || fail "bootstrap syntax"

for mode in check apply verify; do
  grep -Eq "(^|[|[:space:]])${mode}([|)])" "$bootstrap" || fail "missing mode: $mode"
done

grep -Fq -- '--expected-sha' "$bootstrap" || fail "missing exact-SHA CLI gate"
grep -Fq "REPOSITORY='rozkalnsandris/RPi5_main'" "$bootstrap" || fail "repository identity drift"
grep -Fq "VALIDATE_WORKFLOW='validate.yml'" "$bootstrap" || fail "Validate workflow gate missing"
grep -Fq "row.get(\"event\") == \"push\"" "$bootstrap" || fail "exact main push gate missing"
grep -Fq 'row.get("head_branch") == "main"' "$bootstrap" || fail "main branch CI gate missing"
grep -Fq 'row.get("head_sha") == sha' "$bootstrap" || fail "exact CI SHA gate missing"
grep -Fq 'row.get("conclusion") == "success"' "$bootstrap" || fail "successful CI gate missing"
grep -Fq 'row.get("name") == "validate"' "$bootstrap" || fail "validate job identity gate missing"

grep -Fq 'git ls-remote --exit-code "$REMOTE_URL" refs/heads/main' "$bootstrap" || fail "remote-main preflight missing"
grep -Fq 'git clone --quiet --no-tags --single-branch --branch main' "$bootstrap" || fail "fresh main clone missing"
grep -Fq 'refs/remotes/origin/main' "$bootstrap" || fail "ephemeral origin/main equality gate missing"
grep -Fq 'status --porcelain=v1 --untracked-files=all' "$bootstrap" || fail "ephemeral clean-checkout gate missing"
grep -Fq "RETRY_MERGE_SHA='cef02401b54f8cc8ce7f3957d95ea82fb859477f'" "$bootstrap" || fail "reviewed retry merge pin missing"
grep -Fq "RETRY_OPERATOR_BLOB='97a880d4e196d160bb57b8bd6128bc511c2e2597'" "$bootstrap" || fail "reviewed retry operator blob pin missing"
grep -Fq 'merge-base --is-ancestor "$RETRY_MERGE_SHA" "$EXPECTED_SHA"' "$bootstrap" || fail "retry ancestry gate missing"
grep -Fq 'rev-parse "$EXPECTED_SHA:$RETRY_OPERATOR_PATH"' "$bootstrap" || fail "retry blob identity gate missing"

grep -Fq 'mktemp -d -p "$TMP_PARENT" rpi5-v20-release-control.XXXXXX' "$bootstrap" || fail "ephemeral checkout root missing"
grep -Fq 'trap cleanup EXIT HUP INT TERM' "$bootstrap" || fail "cleanup trap missing"
grep -Fq 'rm -rf --one-file-system -- "$RELEASE_ROOT"' "$bootstrap" || fail "bounded cleanup missing"
grep -Fq 'normal_checkout_mutated=false' "$bootstrap" || fail "normal-checkout evidence missing"
grep -Fq '"$operator" "$MODE" --expected-sha "$EXPECTED_SHA"' "$bootstrap" || fail "reviewed retry delegation missing"

if grep -Eiq '(^|[;&|[:space:]])chown([[:space:]]|$)|sudo[[:space:]]+git|git[[:space:]].*(push|rebase|reset[[:space:]]+--hard)' "$bootstrap"; then
  fail "bootstrap contains forbidden normal-checkout/history mutation"
fi
if grep -Eiq 'systemctl|docker[[:space:]]|cloudflared|(^|[;&|[:space:]])ufw[[:space:]]' "$bootstrap"; then
  fail "bootstrap duplicates runtime mutation instead of delegating"
fi
if grep -Eiq 'self-hosted|pull_request_target|Authorization:[[:space:]]|GH_TOKEN|GITHUB_TOKEN' "$bootstrap"; then
  fail "bootstrap introduces runner or credential surface"
fi

# The release-control layer may fetch reviewed public source and GitHub status only.
# Runtime mutation stays entirely inside the separately reviewed retry operator.
grep -Fq 'HERMES_TECH_V20_RELEASE_CONTROL=PASS' "$bootstrap" || fail "success marker missing"

echo "Hermes Tech V20 release-control test: PASS"
