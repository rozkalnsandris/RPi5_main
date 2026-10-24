# Ausmalwiese Stats Worker — protected HTTP transport source (#1038)

**SOURCE ONLY · CODE PROOF BLOCKED · NO MERGE OR LIVE.** The reviewed protocol core from [RPi5_main#1032](https://github.com/rozkalnsandris/RPi5_main/issues/1032) remains intact. This source adds a fixed authenticated-GET transport **design**, typed Cloudflare inventory verifiers, future trust-boundary requirements and synthetic adversarial tests. It does not install a launcher, issue a Cloudflare API call, obtain an API token or authorize an upload.

## Frozen target

- Only `coloring-pages-stats-v1`, Production, independently pinned Cloudflare account fingerprint from `ops/contracts/ausmalwiese-worker-settings-account-binding-v1.json`.
- Existing canonical Worker source: `rozkalnsandris/coloring-pages@9590be4276ac1781eafe38cf662b8d224653c9aa:cloudflare/stats-worker.js`; Git blob `dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4`.
- Exactly seven Production binding names/kinds: `DB:d1`, `RATE_LIMITER:ratelimit`, `PUBLIC_ORIGIN:plain_text`, `CF_ANALYTICS_HOST:plain_text`, `CF_ZONE_TAG:plain_text`, `VISITOR_HMAC_KEY:secret_text`, `CF_ANALYTICS_API_TOKEN:secret_text`. The two secrets cannot be read or hashed.
- Four unchanged routes: `coloring.rozkalns.net/api/stats/*` (zone `rozkalns.net`), plus `ausmalwiese.de/api/stats/*`, `www.ausmalwiese.de/api/stats/*` and `ausmalwiese.de/q` (zone `ausmalwiese.de`).
- Do not confuse the separate `coloring-pages-report-v1` protocol (#1036) with this Worker.

## Source components

- `scripts/ausmalwiese_stats_worker_transport_v1.py`: fixed GET endpoint allowlist, pinned account fingerprint, strict TLS HTTPS GET source, 10s timeout, 64 KiB maximum JSON response, disabled redirects/retries and bounded calls. The `FixedHTTPS` class deliberately cannot be instantiated from this Git checkout: `verified_installed_release()` requires a protected path, root identity and then **unconditionally STOPs until a separately reviewed fixed launcher and release proof are actually supplied**. No credential reader, root installer, `sudo`, OAuth cache, generic CLI or Worker write path is delivered.
- `ops/contracts/ausmalwiese-stats-worker-transport-v1.json`: frozen target and `SOURCE_ONLY_CODE_PROOF_BLOCKED` gate.
- `tests/test-ausmalwiese-stats-worker-transport-v1.py`: all-synthetic, no network/credentials; duplicate JSON, malformed results, version numbers/order, 100% deployments, four routes, seven bindings, denied secrets, disabled writes and code-proof failure.
- `Makefile`: wires these regressions into `make test`, therefore `make validate`.
- Offline probe: `python3 scripts/ausmalwiese_stats_worker_transport_v1.py --check-contract` -> `SOURCE_CONTRACT_OK_CODE_PROOF_BLOCKED_NO_LIVE`. All other CLI arguments STOP.

## Current independent Cloudflare API findings

The documented script-version upload API is a *different operation from creating a Worker deployment*:

1. `GET /accounts/{account}/workers/scripts/coloring-pages-stats-v1/versions?page=1&per_page=100` returns `result.items`, each including a full version `id` and sequential `number`. The parser rejects missing/duplicate numbers, invalid UUIDs, page uncertainty and potentially truncated 100-item results. It does **not** trust JSON list ordering; the largest version number wins.
2. `GET /accounts/{account}/workers/scripts/coloring-pages-stats-v1/deployments` returns a list of deployments and each `versions:[{version_id, percentage}]`. The parser requires one unambiguous newest deployment and exactly 100% to a single full UUID. Anything else is STOP.
3. `GET /zones/{id}` must independently prove the two known zone names are active. `GET /zones/{id}/workers/routes` must enumerate all Worker routes and reject any unexpected route assigned to `coloring-pages-stats-v1`. Incomplete pagination is STOP.
4. Active version must **equal** newest uploaded version immediately before future inheritance. Only the protected, version-specific Worker metadata may establish bindings/config; raw secret contents are rejected. In the synthetic parser, exposed nonsecret identity fingerprints must be produced by a future protected sanitizer, not accepted as independently authenticated simply because they have a 64-hex shape.
5. `bindings_inherit=strict` causes Version Upload to fail when any inherited binding is missing; inheritance for the **script version** endpoint uses `latest`, which need not be deployed. Neither flag nor equality proves the future upload preserves compatibility/runtime flags, routes or all other settings. Those remain separate pre/post gates.

**Source and API references:** [List Versions](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/list/), [Get Version](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/), [Upload Version](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/), [List Deployments](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/) and [Create Deployment](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/create/).

## Mandatory version-specific code proof: BLOCKED

`Get Worker Script Version` documents `resources.script.etag` as **hashed script content**, but does not publicly define it as `SHA-256` of the raw originally uploaded `stats-worker.js` module. A general Worker Script download does not automatically prove the bytes for an arbitrary historical version. **Never claim the etag matches the canonical source SHA-256 simply because it looks like 64 hexadecimal characters.**

The source method `version_code_proof()` **always raises `VERSION_SPECIFIC_BYTES_PROOF_UNAVAILABLE`** even if the metadata contains a plausible `etag`. `plan_live_mutations()` always raises `SOURCE_ONLY_NO_MUTATION_CODE_PROOF_UNAVAILABLE`. These are deliberate barriers; no GitHub source check, browser observation or authenticated version metadata can remove them.

To unblock later, a new explicitly owner-approved review must establish a provider-supported version-specific code byte retrieval or equally trustworthy exact code-level proof, show how to normalize/compare bytes for the reviewed JavaScript module without altering source, bind the fresh full version ID, and test this against synthetic and independently authenticated evidence. Until then **STOP BEFORE WORKER VERSION UPLOAD**, not after a partial mutation. Do not weaken the #1032 SHA-256 proof condition by treating Worker API etag, HTTP ETag or arbitrary source annotations as verified code bytes.

## Protected installation and permission gates (not executed)

This repository copy is not a root-owned runtime. A future reviewed fixed launcher may install an immutable, hash-pinned, root-owned, no-symlink/no-hardlink implementation under `/usr/local/libexec/rpi5-ausmalwiese-stats-worker-transport`, with a fixed `/usr/local/sbin` entrypoint, pinned `RPi5_main` merge SHA and Worker source blob, account SHA, protected file ownership/modes and root-only parent chain. A separately authorized TTY provisioner must populate dedicated least-privilege Cloudflare read/write credentials **outside Git**; do not reuse the existing Worker-settings READ token for writes. The transport must never read ambient environment, credentials from checkout, process/container environment, `wrangler` OAuth cache or arbitrary host settings. Credential scope, access rights and all actual actions require fresh owner approval and technical permission.

After this source PR is explicitly merged (not authorized under #1038), later independent gates are:

1. Review/authorize **protected runtime operator implementation and installation**.
2. Review/authorize dedicated token provisioning (never paste or print token), least privilege for exactly one Worker and required zone read scopes.
3. Review/authorize **authenticated read-only** Cloudflare inventory of full version IDs, account and two zones, seven binding identities, 4 routes and compatibility configuration; source tests are not LIVE evidence.
4. After independent code proof and exact preflight, separately approve one `POST .../versions?bindings_inherit=strict` **Version Upload** and one `POST .../deployments` **100%-traffic promotion**, in a fresh immutable two-stage LIVE envelope. Both operations are writes. Verify the uploaded code identity and all bindings/routes/config before promotion, then 302 canonical `HEAD /q` and Stats read-only GETs. Any error/ambiguity after first write: **STOP without retry, rollback, cleanup or another provider path**.

No D1 data write, `GET /q` counting test, sitemap publication, old-host redirect, service restart, Cloudflare settings change, secrets operation or content import follows automatically.

## Source acceptance

Run `python3 tests/test-ausmalwiese-stats-worker-transport-v1.py` and `make validate`. Exact-head CI PASS means **SOURCE CONTRACT CHECK PASSED, LIVE STOP**. This outcome remains intentionally limited by Cloudflare version-specific byte proof and the missing installed protected trust boundary.
