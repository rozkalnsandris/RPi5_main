#!/usr/bin/env bash
set -euo pipefail
EXPECTED_MAIN="${1:-}"
CONFIRM="${2:-}"
REPO="/home/andris/RPi5_main"
if [[ ! "$EXPECTED_MAIN" =~ ^[0-9a-f]{40}$ ]]; then echo "EXPECTED_MAIN_REQUIRED" >&2; exit 2; fi
if [[ "$CONFIRM" != "OWNER-AUTHORIZED-AUSMALWIESE-ADMIN-ZIP-PUBLISHER-INSTALL" ]]; then echo "CONFIRMATION_REQUIRED" >&2; exit 2; fi
[[ "$(id -u)" -eq 0 ]] || { echo "ROOT_REQUIRED" >&2; exit 2; }
git -C "$REPO" diff --quiet && git -C "$REPO" diff --cached --quiet || { echo "CHECKOUT_NOT_CLEAN" >&2; exit 2; }
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$EXPECTED_MAIN" ]] || { echo "MAIN_MISMATCH" >&2; exit 2; }
[[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == "main" ]] || { echo "MAIN_BRANCH_REQUIRED" >&2; exit 2; }
install -o root -g root -m 0755 "$REPO/ops/bin/coloring-pages-admin-publish" /usr/local/bin/coloring-pages-admin-publish
install -d -o root -g root -m 0755 /usr/local/share/coloring-pages-admin
install -o root -g root -m 0644 "$REPO/ops/admin/coloring-pages/index.html" /usr/local/share/coloring-pages-admin/index.html
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
echo "AUSMALWIESE_ADMIN_ZIP_PUBLISHER_INSTALL=PASS"
