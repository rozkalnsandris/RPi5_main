#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

operator="ops/bin/hermes-tech-http-policy-v20"
doc="docs/V20_HERMES_TECH_HTTP_POLICY_ACTIVATION.md"

fail() {
  echo "Hermes Tech V20 activation operator test: FAIL: $*" >&2
  exit 1
}

[[ -f "$operator" ]] || fail "missing operator"
[[ -f "$doc" ]] || fail "missing activation contract"
bash -n "$operator" || fail "operator syntax"

for mode in check install canary verify rollback; do
  grep -Eq "^[[:space:]]*${mode}\)" "$operator" || fail "missing mode: $mode"
done

grep -Fq -- '--expected-sha' "$operator" || fail "missing exact-SHA CLI gate"
grep -Fq 'refs/remotes/origin/main' "$operator" || fail "missing origin/main equality gate"
grep -Fq 'status --porcelain=v1 --untracked-files=all' "$operator" || fail "missing clean-checkout gate"
grep -Fq 'f873a9dff27a6954f02739a55aa7031a26d56267' "$operator" || fail "missing merged V20 ancestry pin"

image='sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa'
grep -Fq "$image" "$operator" || fail "pinned image missing"
grep -Fq -- '--pull=never' "$operator" || fail "pull=never missing"
grep -Fq '127.0.0.1:8089' "$operator" || fail "loopback port contract missing"
grep -Fq '/home/andris/hermes-tech/site/public|/usr/share/nginx/html|false' "$operator" || fail "read-only public mount contract missing"
grep -Fq '/etc/rpi5-hermes-tech-nginx.conf|/etc/nginx/conf.d/default.conf|false' "$operator" || fail "read-only config mount contract missing"
grep -Fq 'a3cda6ca497de0b4594a974114ca99109946ff1097341d3c1606f800cb3c85c6' "$operator" || fail "pre-V20 unit checksum missing"

python3 - "$operator" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")

def case_body(name: str, next_name: str | None) -> str:
    start = text.index(f"  {name})")
    if next_name:
        end = text.index(f"  {next_name})", start)
    else:
        end = text.index("esac", start)
    return text[start:end]

install = case_body("install", "canary")
canary = case_body("canary", "verify")
verify = case_body("verify", "rollback")

if 'systemctl daemon-reload' not in install:
    raise SystemExit("install mode lacks daemon-reload")
if 'systemctl restart "$SERVICE"' in install or 'systemctl stop "$SERVICE"' in install or 'systemctl start "$SERVICE"' in install:
    raise SystemExit("install-only mode contains web service lifecycle mutation")
if 'systemctl restart "$SERVICE"' not in canary:
    raise SystemExit("canary mode lacks bounded web service restart")
if 'systemctl restart "$SERVICE"' in verify:
    raise SystemExit("verify mode mutates web service")
PY

if grep -Eiq 'docker[[:space:]]+(pull|rmi|image[[:space:]]+(rm|prune)|system[[:space:]]+prune)' "$operator"; then
  fail "forbidden Docker image lifecycle mutation present"
fi
grep -Fq 'docker run --rm --pull=never --network none' "$operator" || fail "bounded nginx syntax test missing"

if grep -Eiq 'systemctl[[:space:]]+(restart|stop|start|reload|try-restart)[[:space:]]+cloudflared' "$operator"; then
  fail "cloudflared lifecycle mutation present"
fi
if grep -Eiq '(^|[;&|[:space:]])ufw[[:space:]]+(allow|deny|delete|insert|reset|disable|enable)' "$operator"; then
  fail "UFW mutation present"
fi
if grep -Eiq '\b(reboot|shutdown|poweroff)\b' "$operator"; then
  fail "host power mutation present"
fi
if grep -Eiq 'cloudflare.*(PUT|POST|PATCH|DELETE)|api\.cloudflare\.com' "$operator"; then
  fail "Cloudflare control-plane mutation present"
fi
if grep -Eiq 'run_digests|digest\.py|publish(_core)?\.sh|hermes_db|sqlite3' "$operator"; then
  fail "Hermes content/database mutation present"
fi
if grep -Eiq 'git[[:space:]].*(push|rebase|reset[[:space:]]+--hard)' "$operator"; then
  fail "Git history mutation present"
fi

grep -Fq 'HERMES_TECH_V20_AUTOMATIC_ROLLBACK=PASS' "$operator" || fail "automatic canary rollback evidence missing"
grep -Fq 'HERMES_TECH_V20_ACTIVATION_INSTALL=PASS' "$operator" || fail "install success marker missing"
grep -Fq 'HERMES_TECH_V20_ACTIVATION_CANARY=PASS' "$operator" || fail "canary success marker missing"
grep -Fq 'HERMES_TECH_V20_ACTIVATION_VERIFY=PASS' "$operator" || fail "verify success marker missing"

grep -Fq 'public, max-age=31536000, immutable' "$operator" || fail "immutable CSS assertion missing"
grep -Fq 'no-cache' "$operator" || fail "stable URL revalidation assertion missing"
grep -Fq 'X-Content-Type-Options' "$operator" || fail "nosniff assertion missing"
grep -Fq 'Content-Security-Policy' "$operator" || fail "CSP assertion missing"
grep -Fq 'Permissions-Policy' "$operator" || fail "Permissions-Policy assertion missing"
grep -Fq 'Referrer-Policy' "$operator" || fail "Referrer-Policy assertion missing"

grep -Fq 'Merging the operator performs no production mutation.' "$doc" || fail "merge/no-mutation boundary missing"
grep -Fq 'install-only' "$doc" || fail "install-only phase missing in doc"
grep -Fq 'separate' "$doc" || fail "separate canary boundary missing in doc"
grep -Fq 'cloudflared.service' "$doc" || fail "shared tunnel boundary missing in doc"
grep -Fq 'f873a9dff27a6954f02739a55aa7031a26d56267' "$doc" || fail "V20 source pin missing in doc"

echo "Hermes Tech V20 activation operator test: PASS"
