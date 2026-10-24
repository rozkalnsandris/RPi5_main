# Ausmalwiese Stats Worker installed deploy boundary (#1118)

**Status: SOURCE UPDATE ONLY · predecessor runtime evidence exists, but this revision is not installed and grants no LIVE authority.**

This outcome closes the remaining trusted-execution gap for parent #996's
Stats Worker stage. The public Worker source is already correct; the stale LIVE
deployment is what still sends `/q` to the legacy host.

## Frozen application provenance

- repository: `rozkalnsandris/coloring-pages`
- immutable Worker/config provenance commit: `97741638b4cb52a3241533f30485c0e7529fdd82`
- operational installer checkout commit: `97741638b4cb52a3241533f30485c0e7529fdd82`
- Worker: `cloudflare/stats-worker.js`
- Worker Git blob: `ccb68d7bbf12474f32e0f94d574ead1b02cd9c7e`
- Wrangler config Git blob:
  `3733263a391274f2b6b0f2023c8656565bde8e1a`
- target Worker: `coloring-pages-stats-v1`
- QR destination in the reviewed Worker:
  `https://ausmalwiese.de/`

The exact deploy core in
`scripts/ausmalwiese_stats_worker_exact_deploy.py` is repinned to this
provenance. It remains a pure protocol core; only the separately installed
runtime below may provide authenticated transport.

## #1200 Cloudflare-only Traffic source repin (not installed)

- Application commit: `97741638b4cb52a3241533f30485c0e7529fdd82`, Worker Git blob `ccb68d7bbf12474f32e0f94d574ead1b02cd9c7e`; unchanged Wrangler config `3733263a391274f2b6b0f2023c8656565bde8e1a`.
- New source verifier requires exact `ausmalwiese.de` host, HTTP-host filter, guarded 7/30-day ranges, `cloudflare_traffic_version:1`, HTTP Requests and its Cloudflare HTTP basis. Requests are not unique visitors or browser page views.
- Historical predecessor remains app `e6c1a4a4fa9f8a9c82dc73babd6b4a2a1bdd4d63`, Worker blob `c2ac9da6e0701103e0041b30db7dfbea4298f96c`, and original old-release SHA-256. These are immutable predecessor evidence.
- Existing `--upgrade-from` is launcher/release-only and rejects changed Worker or core via `upgrade_scope_drift`. Existing `--apply` rejects occupied root-owned targets. This repin cannot replace an installed package. A separately reviewed full-release replacement plus explicit LIVE authorization is required; neither is granted here.
- Open upstream PR #369 lacks merged #368 Traffic fields. A subsequent Worker change invalidates this repin, requiring new source review. Production zone and code-byte verification remain separate protected preflight gates.
## Fixed installed layout

A future separately authorized installation may create only:

- `/usr/local/sbin/rpi5-ausmalwiese-stats-worker-deploy` — root:root 0500;
- `/usr/local/sbin/rpi5-ausmalwiese-stats-worker-deploy-provision` — root:root 0500;
- `/usr/local/libexec/rpi5-ausmalwiese-stats-worker-deploy/` — root:root 0700;
- `core.py`, `stats-worker.js`, `wrangler.stats-worker.jsonc`,
  `release.json` — root:root 0400.

The source-only installer requires exact clean `RPi5_main/main`. It also
requires the application checkout to be branch `main` at the exact operational
checkout commit `97741638b4cb52a3241533f30485c0e7529fdd82`, while the Worker/config bytes must still
match the immutable provenance blobs from `97741638b4cb52a3241533f30485c0e7529fdd82`. The pinned checkout
does not change Worker/config content or widen deploy semantics; unrelated
application working-tree changes do not widen the install scope.

The release manifest binds:

- exact `RPi5_main` source SHA;
- exact application commit;
- Worker/config Git blobs;
- SHA-256 of the launcher, provisioner, core, Worker and config bytes.

No credential or provider request is used by the installer.

The bounded upgrade path is repinned to the exact currently installed
predecessor package after the application-main reconcile: RPi5_main
`78e3e3aee5ef32386acc8031a955b7ddee803304`, launcher blob
`d64b2f330da67d9f95927d06bd1984f4aac4a343`, and release SHA-256
`e65d7b909482fe67629e1da0b42bc5a1b78f255397c01a789941240035b9b066`.
Upgrade preflight reconstructs that historical package from immutable Git
objects, verifies every installed package file as a non-symlink root-owned
single-link file with exact mode and SHA-256, and permits replacement of only
the launcher plus `release.json`. The provisioner, core, Worker and config must
remain byte-identical or the upgrade stops before mutation. A future upgrade
still requires separate owner LIVE authority and has no retry, rollback or
cleanup path.

## #1202 distinct full-release replacement (SOURCE ONLY — NOT INSTALLED)

`--replace-from=<exact previous release SHA-256>` is separate from `--upgrade-from`.
The only accepted predecessor is `e65d7b909482fe67629e1da0b42bc5a1b78f255397c01a789941240035b9b066`.
A future preflight requires exact clean source checkout `main`, reviewed app checkout, verified
historical previous release, fixed root-owned directory metadata, a *names-only* inventory
of exactly `core.py`, `stats-worker.js`, `wrangler.stats-worker.jsonc` and `release.json`,
and for each of six installed package files: no symlink, single link, exact root:root
mode and SHA-256 equal to the proven historical predecessor. It also requires
the exact sudo allowlist for each read and all six fixed `install -T` commands.
Missing rights, missing predecessor files, partial previous upgrades, unknown extra files,
unreviewed Worker source or configuration drift cause **STOP BEFORE FIRST WRITE**.

The full replacement is **six sequential, non-atomic privileged writes**:
provisioner, core, Worker source, Wrangler config, launcher, then release.json last.
It never creates a new directory and cannot change the credentials, Cloudflare settings,
permissions outside these six fixed package files or any provider state.
After the first write, ANY error or ambiguous result terminates in
`post_dispatch_unknown_state` with NO retry, rollback, cleanup or alternative executor.
A partial installation can leave the installed runtime unusable; no automatic recovery
or resumable apply is provided. A future owner must explicitly decide whether this
non-atomic write risk and already-authorized sudo allowlist are acceptable, and inspect
the exact protected host baseline under a separate read/installation authorization.
**Do not execute `--apply` from this GitHub-only source approval.**
The legacy launcher/release-only `--upgrade-from` remains unchanged.

Source CI demonstrates only offline synthetic behavior, not actual root permissions,
host readiness, active Worker version, Cloudflare bindings, or authorization.
Upstream `coloring-pages` PR #369 still conflicts with #368's Worker code;
the pinned source is only the current merged `coloring-pages/main` and must be
reconciled before a future LIVE candidate is approved.
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
- compatibility date/flags and bounded non-handler runtime settings fingerprint;
- exact source-derived handler proof for every provider version whose code
  SHA-256 equals the reviewed candidate: sorted handlers must be exactly
  `fetch` and `scheduled`;
- version-specific provider-declared `main_module` bytes from Cloudflare's
  Worker Versions API with `include=modules`; the selected main-module
  SHA-256 must match the reviewed local Worker source bytes.

The preflight output is sanitized: fixed target/provenance labels, active/latest
version IDs, candidate code SHA-256, a canonical snapshot SHA-256, and whether
the deployed code differs from the reviewed candidate. It never emits account
ID, zone IDs, token, raw provider responses, raw routes, secret values or
plaintext variable values.

### Worker list consumed-invariant contract (#1126)

The provider list parsers deliberately validate only fields used by the trusted
deploy protocol. HTTP transport already requires status 200, bounded parseable
JSON, fixed endpoints, HTTPS and the existing request budget. Unused provider
schema decoration is not a runtime safety boundary.

For List Versions, `result.items` must be a non-empty list. Cloudflare
documents the first item as latest, so only `result.items[0].id` is consumed
and it must be a full UUID. `errors`, `messages`, `metadata`, `number`,
author/source data, later history entries and unknown unused fields are ignored.
If `result_info.page` is present it must be integer page 1; unrelated
pagination counters are not cross-validated because selecting the first latest
item does not require complete history.

For List Worker Deployments, `result.deployments` must be a non-empty list.
Cloudflare documents the first deployment as the latest deployment actively
serving traffic. Only its deployment UUID plus exactly one version UUID at
numeric 100 percent traffic are consumed. Timestamps, source, strategy,
annotations, author data, later historical deployments and unknown unused
fields are ignored. Optional `result_info.page`, when present, must be integer
page 1.

The deploy-critical gates remain unchanged: latest must equal active before
upload, four routes across two zones, seven binding kinds, D1/rate-limit
identity, secret-name-only proof, plaintext fingerprints, compatibility/runtime
settings, version-detail/module SHA-256 proof, double-read snapshot equality,
one upload and one deploy maximum, and no retry/rollback/cleanup.

### Provider-declared main-module proof (#1130)

Cloudflare defines `main_module` as the name of the main module in the
`modules` array. Code proof therefore follows that provider-declared name
instead of assuming a literal filename. The runtime requires one bounded,
non-empty `main_module` string, selects exactly one module whose `name`
matches it, accepts only the existing JavaScript content types, base64-decodes
that module, and SHA-256 hashes the exact bytes. Missing or duplicate matches
fail closed. No fallback to `stats-worker.js` or any other module is allowed.

### Source-derived handler proof

Cloudflare's version metadata reports default-export handler names in
`resources.script.handlers`. Those names are derived from the Worker source,
so they are not part of the preserved runtime-settings fingerprint. For the
exact reviewed Worker blob
`ccb68d7bbf12474f32e0f94d574ead1b02cd9c7e`, every provider version whose
main-module SHA-256 equals the reviewed candidate must report exactly the
sorted handler set `fetch`, `scheduled`.

The bounded non-handler settings fingerprint still includes
`script.named_handlers` plus runtime `exports`, `limits`,
`migration_tag` and `usage_model`. Bindings, compatibility date/flags and
those non-handler settings remain preservation gates.

The 2026-10-23 sanitized recovery differential observed the exact reviewed
candidate code with stable routes/bindings/date/flags. Only the source-derived
`handlers` component differed; active settings SHA-256 was
`d7e1df0e65ea784513f332e42409f3e80e1f6421aa1a15484c82b922b4282fd8` and
latest settings SHA-256 was
`16863f353cb7348990baf3c1cd6a448abba008304a95fb891ff61df3f22ebe77`.
No provider write occurred.

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
latest, routes/bindings/non-handler configuration must remain unchanged, the
reviewed candidate's source-derived handler set must be exact, and the beta Worker
Versions `include=modules` response must prove the provider-declared main
module SHA-256 equals the reviewed local `stats-worker.js` source bytes.

After deployment, the new UUID must be both latest and 100%-active, the
deployment ID must change, all preserved configuration must still match, and
the same exact code SHA-256 proof must pass again.

Upload and deployment budgets are consumed before dispatch. Any transport
error, timeout, unexpected response or ambiguous provider state after either
dispatch is terminal. There is no retry, rollback, cleanup, fallback transport
or second write.

## Deploy-existing recovery (#1138)

The recovery lane exists only for the fail-closed state where the reviewed
candidate version is already the latest uploaded version but the prior active
version still serves 100% traffic. It never repeats Version Upload.

Read-only recovery preflight requires:

`OWNER-AUTHORIZED-STATS-WORKER-RECOVERY-PREFLIGHT`

It double-reads a snapshot that may have `latest != active`, verifies the
latest code SHA-256 equals the exact reviewed candidate while the active code
does not, requires the latest candidate's source-derived handlers to be exact,
and requires routes, bindings and all non-handler runtime configuration to be
preserved across the active/latest versions. Output is limited to the recovery
snapshot SHA-256, candidate code SHA-256, fixed provenance labels,
`recovery_required` and status. Provider version/deployment IDs and raw
provider data are not emitted.

Deploy-existing requires:

`OWNER-AUTHORIZED-STATS-WORKER-DEPLOY-EXISTING`

plus the exact recovery snapshot SHA-256. The runtime re-runs the same
double-read recovery proof before mutation. Any drift stops before a write.
The transport then permits exactly one deployment write with zero upload
writes, assigning the already-uploaded proven latest candidate to 100% traffic.

After dispatch, the runtime requires active and latest to converge on that
candidate, both code proofs to equal the reviewed candidate SHA-256, both
candidate versions to expose exactly `fetch` and `scheduled`, the deployment
identity to change, and routes/bindings/non-handler configuration to remain
preserved. Any dispatch ambiguity or failed post-verification is terminal.
There is no retry, rollback, cleanup or fallback path.

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
- Worker Versions list:
  https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/list/
- Worker Deployments list:
  https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/
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
