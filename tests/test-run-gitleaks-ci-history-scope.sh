#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/run-gitleaks-ci.sh"

[[ "$(gitleaks_history_revision)" == "HEAD" ]] || {
  echo "Gitleaks history scope test: FAIL: revision is not HEAD" >&2
  exit 1
}

grep -Fq 'fetch-depth: 0' "$ROOT/.github/workflows/validate.yml" || {
  echo "Gitleaks history scope test: FAIL: full checkout is not preserved" >&2
  exit 1
}

if grep -Fq -- '--all' "$ROOT/scripts/run-gitleaks-ci.sh"; then
  echo "Gitleaks history scope test: FAIL: all-refs history scope remains" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

repo="$tmp/repo"
git init -q "$repo"
(
  cd "$repo"
  git config user.name "Scope Test"
  git config user.email "scope-test@example.invalid"

  printf '%s\n' "root-marker" > root.txt
  git add root.txt
  git commit -q -m "root"
  root_sha="$(git rev-parse HEAD)"
  main_branch="$(git branch --show-current)"

  printf '%s\n' "head-marker" > head.txt
  git add head.txt
  git commit -q -m "head"
  head_sha="$(git rev-parse HEAD)"

  git switch -q -c divergent "$root_sha"
  printf '%s\n' "divergent-marker" > divergent.txt
  git add divergent.txt
  git commit -q -m "divergent"
  divergent_sha="$(git rev-parse HEAD)"

  git switch -q "$main_branch"

  require_complete_head_history || {
    echo "Gitleaks history scope test: FAIL: full repository rejected" >&2
    exit 1
  }

  history_commits="$(git log --format='%H' "$(gitleaks_history_revision)")"
  grep -Fqx "$head_sha" <<<"$history_commits" || {
    echo "Gitleaks history scope test: FAIL: HEAD commit missing" >&2
    exit 1
  }
  grep -Fqx "$root_sha" <<<"$history_commits" || {
    echo "Gitleaks history scope test: FAIL: HEAD ancestor missing" >&2
    exit 1
  }
  if grep -Fqx "$divergent_sha" <<<"$history_commits"; then
    echo "Gitleaks history scope test: FAIL: divergent ref entered HEAD history" >&2
    exit 1
  fi

  patch_stream="$(git log -p "$(gitleaks_history_revision)" --no-ext-diff --no-textconv -- .)"
  grep -Fq "head-marker" <<<"$patch_stream" || {
    echo "Gitleaks history scope test: FAIL: HEAD patch missing" >&2
    exit 1
  }
  grep -Fq "root-marker" <<<"$patch_stream" || {
    echo "Gitleaks history scope test: FAIL: ancestor patch missing" >&2
    exit 1
  }
  if grep -Fq "divergent-marker" <<<"$patch_stream"; then
    echo "Gitleaks history scope test: FAIL: divergent patch entered HEAD history" >&2
    exit 1
  fi
)

git clone -q --depth 1 "file://$repo" "$tmp/shallow"
if (
  cd "$tmp/shallow"
  require_complete_head_history
); then
  echo "Gitleaks history scope test: FAIL: shallow repository accepted" >&2
  exit 1
fi

echo "Gitleaks history scope test: PASS"
