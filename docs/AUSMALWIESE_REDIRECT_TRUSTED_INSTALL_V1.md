# #996 Ausmalwiese fixed Redirect Rules GET installer and trusted launcher

**Status: SOURCE-ONLY, NOT INSTALLED.** Authorization:
`AUTHORIZE SOURCE RPi5_main #996 MAIN=6746dace26a9a0130f5ded8558bed5ae47ce6a32 ALLOW=FIXED-REDIRECT-GET-INSTALLER+TRUSTED-LAUNCHER-SOURCE+OFFLINE-TESTS+PR+CI-REVIEW SOURCE-ONLY NO-CREDENTIAL-ACCESS NO-PERMISSIONS NO-MERGE NO-LIVE`.

The predecessor PR #999 supplies the fixed read-only Cloudflare adapter and
sanitized Rulesets inventory core. This change supplies a separately
reviewable fixed-file installer and **importable** trusted launcher.
It supplies no credential accessor, API token, role or permission, no runtime
Cloudflare API execution, and no LIVE change.

## Exact installation design (future, separate authorization)

Installer: `scripts/install-ausmalwiese-redirect-get.py` with
`--expected-main <40-hex-SHA>` for preflight only by default.
Its optional `--apply --confirm INSTALL-AUSMALWIESE-REDIRECT-GET` code
is NOT authorized for use by this source operation, merge or START.
A future owner LIVE command must freeze the reviewed exact merged SHA,
source paths, RPi5 target, baseline, permissions and one-shot recovery semantics
BEFORE the first privileged action. Do not run it without that command.

Installer rejects root-running checkout commands, non-main or dirty checkout,
incorrect HEAD SHA/origin, mismatched Git-tracked source bytes, symlinked
source, absent/unsafe parent ownership, and pre-existing target files.
It checks only fixed allowlisted sudo paths and commands. The bounded
five-step host mutation is one private directory create followed by four
root-owned no-overwrite source/release installs. After dispatch failure,
uncertainty or unexpected post-verify evidence: STOP, never retry or cleanup.
It does not create credentials or sudoers permissions.

Proposed trusted destinations:
- `/usr/local/sbin/rpi5-ausmalwiese-redirect-get` — root:root 0500
- `/usr/local/libexec/rpi5-ausmalwiese-redirect-get` — root:root 0700
- `/usr/local/libexec/rpi5-ausmalwiese-redirect-get/inventory.py` — 0400
- `/usr/local/libexec/rpi5-ausmalwiese-redirect-get/adapter.py` — 0400
- `/usr/local/libexec/rpi5-ausmalwiese-redirect-get/release.json` — 0400

The root-owned release manifest binds exact main SHA and SHA-256 hashes
of the launcher, adapter and inventory. No credential path is present.
Installed launcher verifies its absolute entry path, effective root UID,
non-symlink root-owned file and parent identities, strict file modes,
release metadata and all hashes before loading modules.

## Invocation design and remaining gate

The source launcher has **no CLI or __main__**. An executable installed
file alone cannot issue a Cloudflare request; it intentionally has no
credential source and no way for an unreviewed shell to pass one through
argv/env/stdin. A **future independently reviewed privileged caller**
must be source-reviewed and owner-authorized separately to invoke
`run_once(expected_main, zone_id, in_memory_read_token)`. That caller
must prove an independently authorized zone-scoped **Dynamic URL Redirects
Read** token, a verified fixed `rozkalns.net` zone binding, non-exposure
in logs/argv/env/chat, and a fresh owner REVIEW command. This
implementation does **not** provide that caller or credential.

The verified adapter allows only three GETs:
1. `GET /zones/{zone_id}`
2. `GET /zones/{zone_id}/rulesets`
3. `GET /zones/{zone_id}/rulesets/phases/http_request_dynamic_redirect/entrypoint`

It rejects non-GET, foreign zones, invalid API envelopes, incomplete list
pagination, and ambiguous errors. The inventory output only reports
sanitized counts/positions/hash and always has `safe_to_apply=false`.
Account-level rules and destination LIVE readiness are not proven.

## Independent acceptance gates

Do NOT activate the old-host 301 until `coloring-pages` issue #213 /
PR #214 has independently completed, new-host LIVE sitemap and canonical
SEO are verified, Worker `/q`, legacy API POST callers, health monitoring,
media, print and campaign paths are accepted, and the current Cloudflare
ruleset order/overlap has been verified with separate read-only rights.
A redirect edit needs a NEW exact owner LIVE authorization and is
not implemented by this installer or launcher.

Offline checks:
`python3 tests/test-ausmalwiese-redirect-trusted-install-source.py`
No credential files, Cloudflare GET, host sudo, or RPi5 service changes
occur in these tests.

Authoritative machine contract:
`ops/contracts/ausmalwiese-redirect-get-install-v1.json`.

Cloudflare reference:
https://developers.cloudflare.com/ruleset-engine/rulesets-api/view/
