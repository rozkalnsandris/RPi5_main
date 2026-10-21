#!/usr/bin/env bash
set -euo pipefail
EXPECTED_MAIN="${1:-}"
CONFIRM="${2:-}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
BALOO_NAME="baloo2-latin-vf-26fb4610d4bc976d.woff2"
NUNITO_NAME="nunito-latin-vf-ba344451eab25b21.woff2"
BALOO_SHA256="26fb4610d4bc976d2584ca15e66c11465dbc1f267a10dca668fcb3080dfe59c1"
NUNITO_SHA256="ba344451eab25b217a165363b1982048a5e5830a0daf36577973955a04cac793"
FONT_ORIGIN="https://ausmalwiese.de/assets/fonts"
if [[ ! "$EXPECTED_MAIN" =~ ^[0-9a-f]{40}$ ]]; then echo "EXPECTED_MAIN_REQUIRED" >&2; exit 2; fi
if [[ "$CONFIRM" != "OWNER-AUTHORIZED-AUSMALWIESE-ADMIN-ZIP-PUBLISHER-INSTALL" ]]; then echo "CONFIRMATION_REQUIRED" >&2; exit 2; fi
[[ "$(id -u)" -eq 0 ]] || { echo "ROOT_REQUIRED" >&2; exit 2; }
git -C "$REPO" diff --quiet && git -C "$REPO" diff --cached --quiet || { echo "CHECKOUT_NOT_CLEAN" >&2; exit 2; }
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$EXPECTED_MAIN" ]] || { echo "MAIN_MISMATCH" >&2; exit 2; }
[[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == "main" ]] || { echo "MAIN_BRANCH_REQUIRED" >&2; exit 2; }

BALOO_TMP="$(mktemp)"
NUNITO_TMP="$(mktemp)"
curl --fail --silent --show-error --max-time 10 "$FONT_ORIGIN/$BALOO_NAME" -o "$BALOO_TMP"
curl --fail --silent --show-error --max-time 10 "$FONT_ORIGIN/$NUNITO_NAME" -o "$NUNITO_TMP"
[[ "$(sha256sum "$BALOO_TMP" | awk '{print $1}')" == "$BALOO_SHA256" ]] || { echo "BALOO_FONT_HASH_MISMATCH" >&2; exit 2; }
[[ "$(sha256sum "$NUNITO_TMP" | awk '{print $1}')" == "$NUNITO_SHA256" ]] || { echo "NUNITO_FONT_HASH_MISMATCH" >&2; exit 2; }

install -o root -g root -m 0755 "$REPO/ops/bin/coloring-pages-admin-publish" /usr/local/bin/coloring-pages-admin-publish
install -d -o root -g root -m 0755 /usr/local/share/coloring-pages-admin
install -o root -g root -m 0644 "$REPO/ops/admin/coloring-pages/index.html" /usr/local/share/coloring-pages-admin/index.html
install -d -o root -g root -m 0755 /usr/local/share/coloring-pages-admin/fonts
install -o root -g root -m 0644 "$BALOO_TMP" "/usr/local/share/coloring-pages-admin/fonts/$BALOO_NAME"
install -o root -g root -m 0644 "$NUNITO_TMP" "/usr/local/share/coloring-pages-admin/fonts/$NUNITO_NAME"
install -o root -g root -m 0644 "$REPO/ops/systemd/coloring-pages-admin-publish.service" /etc/systemd/system/coloring-pages-admin-publish.service
install -d -o andris -g andris -m 0700 /srv/coloring-pages-content/state/admin-publish
install -d -o andris -g andris -m 0700 /srv/coloring-pages-content/state/admin-publish/uploads
install -d -o andris -g andris -m 0700 /srv/coloring-pages-content/state/admin-publish/jobs
test -f /srv/coloring-pages-content/state/drive-ingest/.lock
[[ "$(stat -c '%U:%G:%a' /srv/coloring-pages-content/state/drive-ingest/.lock)" == "andris:andris:600" ]] || { echo "SHARED_LOCK_INVALID" >&2; exit 2; }
systemctl daemon-reload
systemctl enable --now coloring-pages-admin-publish.service
systemctl is-active --quiet coloring-pages-admin-publish.service
curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8765/ >/dev/null
curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$BALOO_NAME" | sha256sum | grep -F "$BALOO_SHA256  -" >/dev/null
curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$NUNITO_NAME" | sha256sum | grep -F "$NUNITO_SHA256  -" >/dev/null
echo "AUSMALWIESE_ADMIN_ZIP_PUBLISHER_INSTALL=PASS"
