#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(git rev-parse --show-toplevel)"

bad_names="$(
  git ls-files |
  grep -E '(^|/)(\.env(\..*)?|secrets?([._-].*)?|credentials?([._-].*)?|id_rsa(\..*)?|id_ed25519(\..*)?|cert\.json)$|(\.pem|\.key|\.p12|\.pfx)$' ||
  true
)"

if [[ -n "${bad_names}" ]]; then
  echo "Blocked secret-like tracked file names:" >&2
  printf '%s\n' "${bad_names}" >&2
  exit 1
fi

patterns='(BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|CLOUDFLARE_API_TOKEN[[:space:]]*=|POSTGRES_PASSWORD[[:space:]]*=|GRAFANA_ADMIN_PASSWORD[[:space:]]*=|password[[:space:]]*[:=][[:space:]]*[^<][^[:space:]]+)'

if git grep -nEI "${patterns}" -- . \
  ':(exclude)scripts/check-no-secrets.sh' \
  ':(exclude).github/workflows/validate.yml'
then
  echo "Potential secret content found. Review before commit." >&2
  exit 1
fi

echo "Secret guard: PASS"
