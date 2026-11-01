#!/usr/bin/env bash
set -euo pipefail
EXPECTED_MAIN="${1:-}"
CONFIRM="${2:-}"
MODE="${3:-full}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
SERVICE="coloring-pages-admin-publish.service"
PUBLISH_LOCK="/srv/coloring-pages-content/state/drive-ingest/.lock"
LINKS_REGISTRY="/srv/coloring-pages-content/state/admin-publish/category-topic-links.json"
BALOO_NAME="baloo2-latin-vf-26fb4610d4bc976d.woff2"
NUNITO_NAME="nunito-latin-vf-ba344451eab25b21.woff2"
BALOO_SHA256="26fb4610d4bc976d2584ca15e66c11465dbc1f267a10dca668fcb3080dfe59c1"
NUNITO_SHA256="ba344451eab25b217a165363b1982048a5e5830a0daf36577973955a04cac793"
FONT_ORIGIN="https://ausmalwiese.de/assets/fonts"
# Same upstream revision as the public site's Latin subsets; downloads are hash-pinned.
EXT_FONT_ORIGIN="https://raw.githubusercontent.com/fontsource/font-files/c3f4e3e5a664d2c3002e800050ce809a790d7281/fonts/variable"
BALOO_EXT_NAME="baloo2-latin-ext-vf-dfd52ee2e67ff597.woff2"
BALOO_EXT_SHA256="dfd52ee2e67ff597c9a47238d59adcee2b27d8adf9245e2d53a46dd73db99dde"
NUNITO_EXT_NAME="nunito-latin-ext-vf-2c8d792869818ecb.woff2"
NUNITO_EXT_SHA256="2c8d792869818ecb253a46bc3c63c7013df7aac2f69291c3c85e5cdc94160960"
READINESS_ATTEMPTS=10
READINESS_CURL_SECONDS=0.25
READINESS_INTERVAL_SECONDS=0.25

if [[ ! "$EXPECTED_MAIN" =~ ^[0-9a-f]{40}$ ]]; then echo "EXPECTED_MAIN_REQUIRED" >&2; exit 2; fi
case "$MODE" in
  full)
    [[ "$CONFIRM" == "OWNER-AUTHORIZED-AUSMALWIESE-ADMIN-ZIP-PUBLISHER-INSTALL" ]] || { echo "CONFIRMATION_REQUIRED" >&2; exit 2; }
    ;;
  ui-only)
    [[ "$CONFIRM" == "OWNER-AUTHORIZED-AUSMALWIESE-ADMIN-UI-UPDATE" ]] || { echo "CONFIRMATION_REQUIRED" >&2; exit 2; }
    ;;
  *)
    echo "MODE_INVALID" >&2
    exit 2
    ;;
esac

[[ "$(id -u)" -eq 0 ]] || { echo "ROOT_REQUIRED" >&2; exit 2; }
GIT=(git -c "safe.directory=$REPO" -C "$REPO")
"${GIT[@]}" diff --quiet && "${GIT[@]}" diff --cached --quiet || { echo "CHECKOUT_NOT_CLEAN" >&2; exit 2; }
[[ "$("${GIT[@]}" rev-parse HEAD)" == "$EXPECTED_MAIN" ]] || { echo "MAIN_MISMATCH" >&2; exit 2; }
[[ "$("${GIT[@]}" rev-parse --abbrev-ref HEAD)" == "main" ]] || { echo "MAIN_BRANCH_REQUIRED" >&2; exit 2; }

SERVICE_ACTIVE=0
if systemctl is-active --quiet "$SERVICE"; then
  SERVICE_ACTIVE=1
fi

if [[ "$MODE" == "ui-only" ]]; then
  [[ "$SERVICE_ACTIVE" -eq 1 ]] || { echo "ADMIN_SERVICE_MUST_BE_ACTIVE_FOR_UI_ONLY" >&2; exit 2; }
  # Integrated dashboards require the read-only adapter. Reject an older backend before writing HTML.
  curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8765/api/analytics/capabilities | python3 -c 'import json,sys; p=json.load(sys.stdin); assert p.get("version") == 1 and p.get("read_only") is True and p.get("origin_report_version") == 1'
  # A UI-only update cannot introduce Category ↔ Topic controls against an
  # older backend. This GET must not create or repair a registry.
  curl --fail --silent --show-error --max-time 3 -H 'X-Ausmalwiese-Admin: 1' \
    http://127.0.0.1:8765/api/category-topics/manage |
    python3 -c 'import json,sys; p=json.load(sys.stdin); assert isinstance(p.get("enabled"),bool) and isinstance(p.get("links"),list) and "category_sha256" in p and "topic_sha256" in p'
  [[ -f "/usr/local/share/coloring-pages-admin/fonts/$BALOO_NAME" ]] || { echo "BALOO_FONT_MISSING" >&2; exit 2; }
  [[ -f "/usr/local/share/coloring-pages-admin/fonts/$NUNITO_NAME" ]] || { echo "NUNITO_FONT_MISSING" >&2; exit 2; }
  [[ "$(sha256sum "/usr/local/share/coloring-pages-admin/fonts/$BALOO_NAME" | awk '{print $1}')" == "$BALOO_SHA256" ]] || { echo "BALOO_FONT_HASH_MISMATCH" >&2; exit 2; }
  [[ "$(sha256sum "/usr/local/share/coloring-pages-admin/fonts/$NUNITO_NAME" | awk '{print $1}')" == "$NUNITO_SHA256" ]] || { echo "NUNITO_FONT_HASH_MISMATCH" >&2; exit 2; }

  [[ -f "/usr/local/share/coloring-pages-admin/fonts/$BALOO_EXT_NAME" ]] || { echo "BALOO_EXT_FONT_MISSING" >&2; exit 2; }
  [[ "$(sha256sum "/usr/local/share/coloring-pages-admin/fonts/$BALOO_EXT_NAME" | awk '{print $1}')" == "$BALOO_EXT_SHA256" ]] || { echo "BALOO_EXT_FONT_HASH_MISMATCH" >&2; exit 2; }
  curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$BALOO_EXT_NAME" | sha256sum | grep -F "$BALOO_EXT_SHA256  -" >/dev/null
  [[ -f "/usr/local/share/coloring-pages-admin/fonts/$NUNITO_EXT_NAME" ]] || { echo "NUNITO_EXT_FONT_MISSING" >&2; exit 2; }
  [[ "$(sha256sum "/usr/local/share/coloring-pages-admin/fonts/$NUNITO_EXT_NAME" | awk '{print $1}')" == "$NUNITO_EXT_SHA256" ]] || { echo "NUNITO_EXT_FONT_HASH_MISMATCH" >&2; exit 2; }
  curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$NUNITO_EXT_NAME" | sha256sum | grep -F "$NUNITO_EXT_SHA256  -" >/dev/null

  install -o root -g root -m 0644 "$REPO/ops/admin/coloring-pages/index.html" /usr/local/share/coloring-pages-admin/index.html
  curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8765/ >/dev/null
  curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$BALOO_NAME" | sha256sum | grep -F "$BALOO_SHA256  -" >/dev/null
  curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$NUNITO_NAME" | sha256sum | grep -F "$NUNITO_SHA256  -" >/dev/null
  echo "AUSMALWIESE_ADMIN_UI_UPDATE=PASS"
  exit 0
fi

# Before any full installer mutation, require an explicitly owner-seeded private
# association registry. The installer never creates or repairs this file.
if [[ -L "$LINKS_REGISTRY" || ! -f "$LINKS_REGISTRY" ]]; then
  echo "CATEGORY_TOPIC_LINKS_OWNER_SEED_REQUIRED" >&2; exit 2
fi
[[ "$(stat -c '%U:%G:%a:%h' "$LINKS_REGISTRY")" == "andris:andris:600:1" ]] || {
  echo "CATEGORY_TOPIC_LINKS_UNSAFE_IDENTITY" >&2; exit 2;
}
python3 - "$LINKS_REGISTRY" <<'PY'
import json
import os
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
with os.fdopen(fd, "rb") as stream:
    identity = os.fstat(stream.fileno())
    if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1 or identity.st_size > 65536:
        raise SystemExit("CATEGORY_TOPIC_LINKS_UNSAFE_FILE")
    raw = stream.read(65537)
if not raw or len(raw) > 65536:
    raise SystemExit("CATEGORY_TOPIC_LINKS_UNSAFE_SIZE")
try:
    data = json.loads(raw)
    links = data["links"]
    assert (type(data) is dict and set(data) == {"schema", "revision", "links"}
            and data["schema"] == "rozkalns.rpi5-main.category-topic-links.v1"
            and type(data["revision"]) is int and 1 <= data["revision"] <= 2147483647
            and type(links) is list and len(links) <= 512)
    keys = []
    for pair in links:
        assert type(pair) is dict and set(pair) == {"category", "topic"}
        c, t = pair["category"], pair["topic"]
        assert (type(c) is str and type(t) is str
                and all(x.isascii() and (x.islower() or x.isdigit() or x == "-") for x in c + t))
        keys.append((c, t))
    assert keys == sorted(set(keys))
    assert raw == (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
except (ValueError, KeyError, TypeError, AssertionError):
    raise SystemExit("CATEGORY_TOPIC_LINKS_INVALID_SEED")
PY

test -f "$PUBLISH_LOCK"
[[ "$(stat -c '%U:%G:%a' "$PUBLISH_LOCK")" == "andris:andris:600" ]] || { echo "SHARED_LOCK_INVALID" >&2; exit 2; }

if [[ "$SERVICE_ACTIVE" -eq 1 ]]; then
  exec 9<>"$PUBLISH_LOCK"
  flock -n 9 || { echo "ACTIVE_PUBLICATION_REFUSES_ADMIN_UPDATE" >&2; exit 2; }
  if ! ACTIVE_STATE="$(curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8765/api/jobs/active | python3 -c 'import json,sys; p=json.load(sys.stdin); active=p.get("active"); job=p.get("job"); assert isinstance(active,bool); assert (job is None) == (not active); print("active" if active else "idle")')"; then
    echo "ADMIN_ACTIVE_JOB_CHECK_FAILED" >&2
    exit 2
  fi
  [[ "$ACTIVE_STATE" == "idle" ]] || { echo "ACTIVE_PUBLICATION_REFUSES_ADMIN_UPDATE" >&2; exit 2; }
fi

BALOO_TMP="$(mktemp)"
NUNITO_TMP="$(mktemp)"
BALOO_EXT_TMP="$(mktemp)"
NUNITO_EXT_TMP="$(mktemp)"
trap 'rm -f "$BALOO_TMP" "$NUNITO_TMP" "$BALOO_EXT_TMP" "$NUNITO_EXT_TMP"' EXIT
curl --fail --silent --show-error --max-time 10 "$FONT_ORIGIN/$BALOO_NAME" -o "$BALOO_TMP"
curl --fail --silent --show-error --max-time 10 "$FONT_ORIGIN/$NUNITO_NAME" -o "$NUNITO_TMP"
[[ "$(sha256sum "$BALOO_TMP" | awk '{print $1}')" == "$BALOO_SHA256" ]] || { echo "BALOO_FONT_HASH_MISMATCH" >&2; exit 2; }
[[ "$(sha256sum "$NUNITO_TMP" | awk '{print $1}')" == "$NUNITO_SHA256" ]] || { echo "NUNITO_FONT_HASH_MISMATCH" >&2; exit 2; }

curl --fail --silent --show-error --max-time 10 "$EXT_FONT_ORIGIN/baloo-2/files/baloo-2-latin-ext-wght-normal.woff2" -o "$BALOO_EXT_TMP"
[[ "$(sha256sum "$BALOO_EXT_TMP" | awk '{print $1}')" == "$BALOO_EXT_SHA256" ]] || { echo "BALOO_EXT_FONT_HASH_MISMATCH" >&2; exit 2; }
curl --fail --silent --show-error --max-time 10 "$EXT_FONT_ORIGIN/nunito/files/nunito-latin-ext-wght-normal.woff2" -o "$NUNITO_EXT_TMP"
[[ "$(sha256sum "$NUNITO_EXT_TMP" | awk '{print $1}')" == "$NUNITO_EXT_SHA256" ]] || { echo "NUNITO_EXT_FONT_HASH_MISMATCH" >&2; exit 2; }

install -o root -g root -m 0755 "$REPO/ops/bin/coloring-pages-admin-publish" /usr/local/bin/coloring-pages-admin-publish
install -d -o root -g root -m 0755 /usr/local/share/coloring-pages-admin
install -o root -g root -m 0644 "$REPO/ops/admin/coloring-pages/index.html" /usr/local/share/coloring-pages-admin/index.html
install -d -o root -g root -m 0755 /usr/local/share/coloring-pages-admin/fonts
install -o root -g root -m 0644 "$BALOO_TMP" "/usr/local/share/coloring-pages-admin/fonts/$BALOO_NAME"
install -o root -g root -m 0644 "$NUNITO_TMP" "/usr/local/share/coloring-pages-admin/fonts/$NUNITO_NAME"
install -o root -g root -m 0644 "$BALOO_EXT_TMP" "/usr/local/share/coloring-pages-admin/fonts/$BALOO_EXT_NAME"
install -o root -g root -m 0644 "$NUNITO_EXT_TMP" "/usr/local/share/coloring-pages-admin/fonts/$NUNITO_EXT_NAME"
install -o root -g root -m 0644 "$REPO/ops/systemd/coloring-pages-admin-publish.service" /etc/systemd/system/coloring-pages-admin-publish.service
install -d -o andris -g andris -m 0700 /srv/coloring-pages-content/state/admin-publish
install -d -o andris -g andris -m 0700 /srv/coloring-pages-content/state/admin-publish/uploads
install -d -o andris -g andris -m 0700 /srv/coloring-pages-content/state/admin-publish/jobs
install -d -o andris -g andris -m 0700 /srv/coloring-pages-content/state/admin-publish/logs

systemctl daemon-reload
if [[ "$SERVICE_ACTIVE" -eq 1 ]]; then
  systemctl enable "$SERVICE"
  systemctl restart "$SERVICE"
else
  systemctl enable --now "$SERVICE"
fi
systemctl is-active --quiet "$SERVICE"

READY=0
for ((attempt=1; attempt<=READINESS_ATTEMPTS; attempt++)); do
  if curl --fail --silent --show-error --connect-timeout "$READINESS_CURL_SECONDS" --max-time "$READINESS_CURL_SECONDS" http://127.0.0.1:8765/ >/dev/null 2>&1; then
    READY=1
    break
  fi
  if [[ "$attempt" -lt "$READINESS_ATTEMPTS" ]]; then
    sleep "$READINESS_INTERVAL_SECONDS"
  fi
done
[[ "$READY" -eq 1 ]] || { echo "ADMIN_SERVICE_HTTP_NOT_READY" >&2; exit 7; }

curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$BALOO_NAME" | sha256sum | grep -F "$BALOO_SHA256  -" >/dev/null
curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$NUNITO_NAME" | sha256sum | grep -F "$NUNITO_SHA256  -" >/dev/null
curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$BALOO_EXT_NAME" | sha256sum | grep -F "$BALOO_EXT_SHA256  -" >/dev/null
curl --fail --silent --show-error --max-time 3 "http://127.0.0.1:8765/assets/fonts/$NUNITO_EXT_NAME" | sha256sum | grep -F "$NUNITO_EXT_SHA256  -" >/dev/null
echo "AUSMALWIESE_ADMIN_ZIP_PUBLISHER_INSTALL=PASS"
