#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"

config="ops/nginx/hermes-tech.conf"
unit="ops/systemd/hermes-tech-web.service"
policy_doc="docs/V20_HERMES_TECH_HTTP_POLICY_CONTRACT.md"
image="sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa"

fail() {
  echo "Hermes Tech HTTP policy test: FAIL: $*" >&2
  exit 1
}

for path in "$config" "$unit" "$policy_doc"; do
  [[ -f "$path" ]] || fail "missing $path"
done

# Cache policy is selected at http scope with one variable-backed server header.
grep -Fq 'map $uri $hermes_cache_control {' "$config" || fail "missing cache policy map"
grep -Fq 'default "no-cache";' "$config" || fail "missing default revalidation policy"
grep -Fq '~^/css/site\.min\.[0-9a-f]+\.css$ "public, max-age=31536000, immutable";' "$config" || fail "missing immutable fingerprinted CSS policy"
[[ "$(grep -Fc 'add_header Cache-Control $hermes_cache_control always;' "$config")" -eq 1 ]] || fail "Cache-Control header must be defined exactly once"

# Security policy must match the application-owned Hermes Tech contract.
grep -Fq 'add_header X-Content-Type-Options "nosniff" always;' "$config" || fail "missing nosniff"
grep -Fq 'add_header Referrer-Policy "strict-origin-when-cross-origin" always;' "$config" || fail "missing Referrer-Policy"
grep -Fq 'add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=()" always;' "$config" || fail "missing Permissions-Policy"
csp="default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; img-src 'self'; style-src 'self'; script-src 'none'; font-src 'none'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; manifest-src 'self'"
grep -Fq "add_header Content-Security-Policy \"$csp\" always;" "$config" || fail "CSP drift"
if grep -Eq "unsafe-inline|unsafe-eval|script-src[[:space:]]+'self'" "$config"; then
  fail "CSP permits forbidden script/style escape hatch"
fi

# Static origin behavior: no proxying, no PHP/application runtime, deterministic Hugo path lookup.
grep -Fq 'root /usr/share/nginx/html;' "$config" || fail "static root drift"
grep -Fq 'index index.html;' "$config" || fail "index contract drift"
grep -Fq 'try_files $uri $uri/ =404;' "$config" || fail "try_files contract drift"
if grep -Eiq 'proxy_pass|fastcgi_pass|uwsgi_pass|scgi_pass' "$config"; then
  fail "application proxy/runtime directive is forbidden"
fi
if grep -Eq '^[[:space:]]*location[^\{]*\{[[:space:]]*$' "$config"; then
  # All add_header directives must stay at server scope to avoid legacy inheritance surprises.
  python3 - "$config" <<'PY'
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
depth = 0
in_location = False
location_depth = None
for raw in text.splitlines():
    line = raw.split("#", 1)[0].strip()
    if not line:
        continue
    if line.startswith("location ") and line.endswith("{"):
        in_location = True
        location_depth = depth + 1
    depth += line.count("{") - line.count("}")
    if in_location and "add_header " in line:
        raise SystemExit("location-level add_header is forbidden")
    if in_location and location_depth is not None and depth < location_depth:
        in_location = False
        location_depth = None
if depth != 0:
    raise SystemExit("unbalanced nginx braces")
PY
fi

# V14 runtime identity and isolation remain intact while adding one reviewed config mount.
grep -Fq -- '--pull=never' "$unit" || fail "missing --pull=never"
grep -Fq -- "$image" "$unit" || fail "pinned image drift"
grep -Fq -- '--publish 127.0.0.1:8089:80' "$unit" || fail "loopback publish drift"
grep -Fq -- '--mount type=bind,src=/home/andris/hermes-tech/site/public,dst=/usr/share/nginx/html,readonly' "$unit" || fail "public bind drift"
grep -Fq -- '--mount type=bind,src=/etc/rpi5-hermes-tech-nginx.conf,dst=/etc/nginx/conf.d/default.conf,readonly' "$unit" || fail "reviewed nginx config mount missing"
grep -Fqx 'ConditionPathExists=/etc/rpi5-hermes-tech-nginx.conf' "$unit" || fail "config existence guard missing"
if grep -Fq -- 'src=/home/andris/RPi5_main' "$unit"; then
  fail "unit must not bind a user-writable repository config into nginx"
fi
grep -Fq -- '--restart=no' "$unit" || fail "Docker restart policy drift"
grep -Fqx 'Restart=on-failure' "$unit" || fail "systemd supervisor drift"

# CI validates unit syntax without requiring Docker or production host paths.
command -v systemd-analyze >/dev/null 2>&1 || fail "systemd-analyze is required"
tmp_unit="$(mktemp --suffix=.service)"
trap 'rm -f "$tmp_unit"' EXIT
sed \
  -e 's#Requires=docker.service#Requires=#' \
  -e 's#After=docker.service network-online.target#After=network-online.target#' \
  -e 's#ConditionPathExists=/home/andris/hermes-tech/site/public#ConditionPathExists=/etc/hosts#' \
  -e 's#ConditionPathExists=/etc/rpi5-hermes-tech-nginx.conf#ConditionPathExists=/etc/hosts#' \
  -e 's#/usr/bin/docker#/usr/bin/true#g' \
  "$unit" > "$tmp_unit"
systemd-analyze verify "$tmp_unit" >/dev/null || fail "systemd-analyze verify rejected unit"

# Ownership and non-authorization remain explicit.
grep -Fq 'Merging V20 performs no production mutation.' "$policy_doc" || fail "missing merge/no-mutation boundary"
grep -Fq 'cloudflared.service' "$policy_doc" || fail "missing shared Tunnel boundary"
grep -Fq '/etc/rpi5-hermes-tech-nginx.conf' "$policy_doc" || fail "missing installed config target"
grep -Fq 'sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa' "$policy_doc" || fail "missing pinned-image boundary"

echo "Hermes Tech HTTP policy test: PASS"
