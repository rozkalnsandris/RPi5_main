# Ausmalwiese Worker script-settings — fixed trusted GET executor source

**SOURCE ONLY — NOT INSTALLED — NO CREDENTIAL PROVISIONING — NO LIVE GET.**

Cloudflare official endpoint: https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/
Least privilege is a future dedicated account-scoped **Workers Scripts Read** API token. The existing Wrangler OAuth cache is NOT used.

## Exact components and source-only implementation

- `scripts/ausmalwiese_worker_settings_executor.py`: standalone, pinned GET transport for the one named Worker `coloring-pages-stats-v1`. The only HTTP operation is one HTTPS GET to `/client/v4/accounts/{pinned_id}/workers/scripts/coloring-pages-stats-v1/script-settings`.
- `scripts/ausmalwiese_worker_settings_get.py`: previously reviewed sanitizer. Its installed copy must be pinned and root-owned before execution.
- `ops/contracts/ausmalwiese-worker-settings-executor-v1.json`: source paths, limits, install preflight and unapproved mutation boundaries.
- `tests/test-ausmalwiese-worker-settings-executor-v1.py`: offline tests with fake HTTP and fake credentials; never reads secrets or calls Cloudflare.

The executor rejects execution outside `/usr/local/sbin/rpi5-ausmalwiese-worker-settings-get` and without root privileges. It accepts only `--expected-main <exact-40-hex-SHA>` and `--confirm OWNER-AUTHORIZED-ONE-SETTINGS-GET`; command confirmation is *not* independent proof of owner authorization. A future protected operator boundary must separately enforce the single-use owner decision.

## Fixed protected installation contract — preflight only

The future, separately authorized installer must verify the exact GitHub merged main SHA, reviewed source bytes, clean checkout, root-owned nonwritable parent directories, absence of every installation target (including symlinks), no conflicting maintenance operation, trusted `sudo`/root execution and no existing credential replacement. It must not run repository Python as root or alter sudoers. No install script or privileged mutation is included.

The proposed root-owned files are:

- `/usr/local/sbin/rpi5-ausmalwiese-worker-settings-get` — mode `0500`, root:root, no symlink/hardlink.
- `/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get/sanitizer.py` — mode `0400`, root:root, no symlink/hardlink.
- `/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get/release.json` — mode `0400`, root:root, no symlink/hardlink.
- `/etc/rpi5-secrets/cloudflare/ausmalwiese-worker-settings-read.json` — separate future owner-provisioned dedicated credential; mode `0600`, root:root, no symlink/hardlink, never committed or returned.

Release metadata must contain exactly `schema_version=1`, repository, exact `source_sha`, fixed Worker, `executor_sha256`, `sanitizer_sha256`, and `account_sha256`. Both installed source files are read with `O_NOFOLLOW`, checked for mode/owner/length and SHA-256. The credential is read only *after* installed release and source identity pass; it must contain exactly `worker`, `account_id`, `api_token`, and its account must match the release's pinned SHA-256. No fallback to Wrangler OAuth, process environment, another secret, or global Cloudflare API key.

## Request/output limits

Use Python standard library `http.client.HTTPSConnection` with certificate/hostname validation, timeout 10 seconds, GET-only, one request, no redirect, no retry, `Accept-Encoding: identity`, JSON content-type validation, bounded 32 KiB raw reply and fail-closed JSON parsing. Do not print upstream status bodies, HTTP exception details, account ID or token. Only the **pinned sanitizer's allowlisted** booleans, finite sampling rates and destination counts may reach stdout; errors are static STOP codes.

Run a future approved installed executor with Python isolated mode (`/usr/bin/python3 -I -B`) to avoid untrusted `PYTHONPATH` and bytecode writes. An installed runtime path and release hash are only necessary checks; they do not by themselves grant permission to call Cloudflare. A future installer and dedicated credential provisioning must be independently security-reviewed and owner-authorized. Any failure/ambiguity after a runtime dispatch means STOP, never retry or alternate transport.

## Offline verification

`python3 tests/test-ausmalwiese-worker-settings-executor-v1.py` performs mocked unit tests; `make test` includes it. The source's only authorization in this PR is to create/review GitHub source/tests/docs. Neither the source code nor the offline fixtures are LIVE evidence.

Explicit exclusions: no credential reads in this work cycle, no OAuth refresh, no host install, no Cloudflare API request, no D1 read/write, no deploy, no settings changes, no merge, and no LIVE.
