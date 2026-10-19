# Ausmalwiese Stats Worker installed deploy boundary (#1118)

**Status: SOURCE ONLY · not installed · no credential access · no Cloudflare request · no LIVE authority.**

This outcome closes the remaining trusted-execution gap for parent #996's
Stats Worker stage. The public Worker source is already correct; the stale LIVE
deployment is what still sends `/q` to the legacy host.

## Frozen application provenance

- repository: `rozkalnsandris/coloring-pages`
- commit: `e6c1a4a4fa9f8a9c82dc73babd6b4a2a1bdd4d63`
- Worker: `cloudflare/stats-worker.js`
- Worker Git blob: `c2ac9da6e0701103e0041b30db7dfbea4298f96c`
- Wrangler config Git blob:
  `3733263a391274f2b6b0f2023c8656565bde8e1a`
- target Worker: `coloring-pages-stats-v1`
- QR destination in the reviewed Worker:
  `https://ausmalwiese.de/`

The exact deploy core in
`scripts/ausmalwiese_stats_worker_exact_deploy.py` is repinned to this
provenance. It remains a pure protocol core; only the separately installed
runtime below may provide authenticated transport.

## Fixed installed layout

A future separately authorized installation may create only:

- `/usr/local/sbin/rpi5-ausmalwiese-stats-worker-deploy` — root:root 0500;
- `/usr/local/sbin/rpi5-ausmalwiese-stats-worker-deploy-provision` — root:root 0500;
- `/usr/local/libexec/rpi5-ausmalwiese-stats-worker-deploy/` — root:root 0700;
- `core.py`, `stats-worker.js`, `wrangler.stats-worker.jsonc`,
  `release.json` — root:root 0400.

The source-only installer requires exact clean `RPi5_main/main`. It also
requires the application checkout at the exact frozen commit and exact clean
bytes for only the Worker/config paths; unrelated application working-tree
changes do not widen the install scope.

The release manifest binds:

- exact `RPi5_main` source SHA;
- exact application commit;
- Worker/config Git blobs;
- SHA-256 of the launcher, provisioner, core, Worker and config bytes.

No credential or provider request is used by the installer.

## Protected credential

The only write credential path is:

`/etc/rpi5-secrets/cloudflare/ausmalwiese-stats-worker-write.json`

Expected metadata is root:root 0600 under the existing root-owned 0700
Cloudflare secrets directory. Exact fields are:

- `worker = coloring-pages-stats-v1`;
- account ID whose SHA-256 equals the reviewed account fingerprint;
- API token;
- exact zone IDs for `ausmalwiese.de` and `rozkalns.net`.

The provisioner accepts all four values only from the controlling
`/dev/tty` with echo disabled. It accepts no credential material through
argv, environment, stdin, GitHub, chat or logs and never creates/rotates a
Cloudflare token or changes its permissions. The credential file is an
exclusive single create with no overwrite.

A future operator must provision a token scoped only as narrowly as Cloudflare
permits for this Worker plus the read-only zone/route proofs required by the
runtime. This source does not create or widen that permission.

## Read-only preflight

The installed runtime first proves every installed byte and fixed source
identity before opening the credential.

Preflight requires exact confirmation:

`OWNER-AUTHORIZED-STATS-WORKER-PREFLIGHT`

and the exact Worker/config blob arguments.

It then performs two independently fresh, identical snapshots. Each snapshot
proves:

- one latest uploaded full Worker version;
- one 100%-active full Worker version;
- exact four Worker routes across the two expected zones;
- exactly seven binding names/kinds;
- exact D1 and Rate Limiter identities/policy;
- secret names without secret values;
- fingerprints only for three existing plaintext bindings;
- compatibility date/flags and bounded runtime settings fingerprint;
- version-specific `stats-worker.js` bytes from Cloudflare's Worker Versions
  API with `include=modules`.

The preflight output is sanitized: fixed target/provenance labels, active/latest
version IDs, candidate code SHA-256, a canonical snapshot SHA-256, and whether
the deployed code differs from the reviewed candidate. It never emits account
ID, zone IDs, token, raw provider responses, raw routes, secret values or
plaintext variable values.

## Exact apply

Apply requires exact confirmation:

`OWNER-AUTHORIZED-STATS-WORKER-APPLY`

plus the frozen Worker/config blobs and the exact snapshot SHA-256 returned by
the immediately preceding preflight.

The deploy core re-reads the snapshot twice before the first write and rejects
any drift from the owner-bound digest.

Only two ordered provider writes are possible:

1. one Version Upload to
   `coloring-pages-stats-v1/versions?bindings_inherit=strict`, containing only
   the exact reviewed `stats-worker.js`, exact compatibility configuration,
   seven inherited bindings and fixed source annotations;
2. after post-upload proof, one deployment assigning the exact returned new
   version UUID to 100% traffic.

After upload, the old deployment must remain active while the new version is
latest, routes/bindings/config must remain unchanged, and the beta Worker
Versions `include=modules` response must prove the new
`stats-worker.js` SHA-256 equals the reviewed local source.

After deployment, the new UUID must be both latest and 100%-active, the
deployment ID must change, all preserved configuration must still match, and
the same exact code SHA-256 proof must pass again.

Upload and deployment budgets are consumed before dispatch. Any transport
error, timeout, unexpected response or ambiguous provider state after either
dispatch is terminal. There is no retry, rollback, cleanup, fallback transport
or second write.

## Parent #996 flow

The owner-visible flow remains:

`MERGE -> one COMPOSITE LIVE`

Inside that future LIVE envelope:

1. Stats Gate A;
2. install/provision this Stats Worker runtime if needed;
3. sanitized Worker preflight -> exact upload/deploy -> public `HEAD /q`
   acceptance;
4. sitemap/public acceptance if still required by fresh state;
5. final legacy-host redirect verification/write only if still required.

Fresh public evidence may show later stages already complete. The Composite
must always re-read actual state and skip already-satisfied mutation stages
rather than replay them.

## Cloudflare references

- Worker Script Version Upload:
  https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/
- Worker Deployments:
  https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/create/
- Worker Versions with module content (`include=modules`):
  https://developers.cloudflare.com/api/typescript/resources/workers/subresources/beta/subresources/workers/subresources/versions/methods/get/
- Single Worker routes:
  https://developers.cloudflare.com/workers/configuration/routing/routes/

Machine contract:
`ops/contracts/ausmalwiese-stats-worker-runtime-v1.json`.

Offline regression:
`python3 tests/test-ausmalwiese-stats-worker-runtime-v1.py`.

This source grants no host install, credential read/provisioning, Cloudflare
request/upload/deploy, token/permission change, D1 write, sitemap publication,
legacy redirect write, DNS/WAF/Access/Tunnel/settings mutation, LIVE, retry,
rollback or cleanup authority.
