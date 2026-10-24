# Ausmalwiese legacy redirect — GET-only trusted adapter (source-only, #996)

## Status and exact scope

**Not installed; no Cloudflare request made.** Only reviewable source, an
offline install-preflight policy, and tests on Draft PR #999 are approved.
There is NO authority for reading credentials, creating tokens, changing
permissions/sudoers, installing, merging or creating Cloudflare redirect rules.

Files:
- scripts/ausmalwiese_redirect_inventory.py: existing sanitized zone inventory.
- scripts/ausmalwiese_redirect_get_adapter.py: narrow GET-only transport.
- ops/contracts/ausmalwiese-redirect-get-adapter-preflight-v1.json: offline
  installation policy, not an installer or host action.
- tests/test-ausmalwiese-redirect-adapter-source.py: mocked offline proof.

## Cloudflare API and trust boundary

The adapter is restricted to three exact GET paths on
https://api.cloudflare.com/client/v4, with a validated 32-character zone ID
for rozkalns.net:

1. GET /zones/{zone_id}
2. GET /zones/{zone_id}/rulesets
3. GET /zones/{zone_id}/rulesets/phases/http_request_dynamic_redirect/entrypoint

A future, separately owner-authorized root-owned trusted caller must validate
source/release identity and supply an independently authorized, zone-scoped
Dynamic URL Redirects Read token IN MEMORY. The proposed adapter does not
obtain credentials or include a caller, CLI, argv/env/stdin token source,
logging or executable __main__.

It uses HTTPS/TLS verification, no inherited HTTP proxy, no HTTP redirects,
8-second time limit, 1 MB response cap, no retries and duplicate-key JSON
rejection. Provider errors do not emit raw body/error text. HTTP 404 is
admitted only for the phase entrypoint after independent zone list consistency;
pagination continuation is rejected as incomplete.

Only sanitized fields (zone/phase labels, counts, enabled order/overlap
positions, snapshot digest) are returned. Never rule IDs, targets, raw
expressions, descriptions, zone ID or token. Safe-to-apply is always false;
account-level rules, other phases, quota, proxy mode and health monitors are
not proven by this limited source.

## Install preflight — future separate owner gate, NOT performed

The JSON contract defines strict checks before any future install:
- Owner-approved exact merged SHA and reviewed Git blob hashes.
- Clean trusted source/packaging; root-owned binary/release metadata and
  parent, correct permissions, no symlink/unreviewed overwrite/staging.
- A separate reviewed launcher/installer, no assumed sudoers capability.
- Offline preflight only: no Cloudflare HTTP call or protected credential read.
- Any independently approved zone-scoped Read token delivered only to an
  installed verified binary by an approved in-memory trusted interface.
- No tokens in arguments, environment, stdin, GitHub, logs, issue or chat.
- No automatic retry, rollback, Cloudflare write or host mutation.

No installed destination paths, release identities or credential access rights
are claimed. Before actual zone GET inventory, revalidate this exact source
and get a new owner REVIEW authorization for the installed trusted caller.
Before eventual old-host 301, independently verify coloring-pages PR #214
canonical + LIVE sitemap, Worker /q, API clients, health monitoring, and
get separate explicit owner LIVE authorization. A successful inventory alone
never permits redirect creation.

References:
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/view/
- https://developers.cloudflare.com/api/resources/rulesets/methods/list/
- https://developers.cloudflare.com/api/resources/rulesets/subresources/phases/methods/get/
- docs/AUSMALWIESE_LEGACY_REDIRECT_V1.md
