# Ausmalwiese Stats Worker: exact-version operator source (#1032)

**SOURCE ONLY · not installed · no authenticated transport · no LIVE mutation · no MERGE permission.**

This is the RPi5_main protocol core for one future owner-gated update of Cloudflare Production Worker `coloring-pages-stats-v1`, to use the already-merged `https://ausmalwiese.de/` QR redirect destination. Its trust boundary ends at the pure fixed-protocol Python module. **It is not an executable Cloudflare deployment tool in its current state** and does not claim to prove the live deployment. A separately security-reviewed, installed and explicitly owner-authorized protected adapter, credential provision and exact LIVE permission remain prerequisites.

## Frozen source & account

- GitHub issue: `RPi5_main#1032`, single outcome; no changes to redirect issue `RPi5_main#996`.
- Source: `rozkalnsandris/coloring-pages@9590be4276ac1781eafe38cf662b8d224653c9aa`, `cloudflare/stats-worker.js`, exact Git blob `dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4`.
- Existing app-side contract merged in `coloring-pages#248`: `deploy/stats-worker-exact-source-v1.json`. This RPi5 contract deliberately repeats and pins the exact Worker, routes and seven bindings.
- Independently reviewed Cloudflare account SHA-256 fingerprint: `3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34` from `ops/contracts/ausmalwiese-worker-settings-account-binding-v1.json`; fingerprint is not an account ID or authority to use credentials.
- RPi5 contract: `ops/contracts/ausmalwiese-stats-worker-exact-deploy-v1.json`.
- Static offline check: `python3 scripts/ausmalwiese_stats_worker_exact_deploy.py --check-contract` returns `SOURCE_CONTRACT_OK_NOT_LIVE_PROOF`. Any other CLI argument returns STOP. `python3 tests/test-ausmalwiese-stats-worker-exact-deploy-v1.py` mocks both mutations with no network. The normal `make validate` test suite must pass on the PR head.

## Seven preserved Production bindings

Cloudflare *API* types are `d1` and `ratelimit` (the Dashboard displays them as D1 database / Rate limiter). The other API types are `plain_text` and `secret_text`. Existing fixed bindings:

| Binding | API type | Future verified target |
| --- | --- | --- |
| `DB` | `d1` | Same independently pinned D1 database |
| `RATE_LIMITER` | `ratelimit` | Same namespace, limit/period and policy |
| `PUBLIC_ORIGIN` | `plain_text` | Same legacy value |
| `CF_ANALYTICS_HOST` | `plain_text` | Same value |
| `CF_ZONE_TAG` | `plain_text` | Same value |
| `VISITOR_HMAC_KEY` | `secret_text` | Existing secret, neither read nor hashed |
| `CF_ANALYTICS_API_TOKEN` | `secret_text` | Existing secret, neither read nor hashed |

All seven are included in the future upload metadata as *exactly seven* `{"type":"inherit","name":"…","version_id":"latest"}` entries. The multipart upload **must** use `bindings_inherit=strict`, fixed `main_module=stats-worker.js` and exact reviewed code bytes. Secrets are never included in their original form. **No arbitrary Wrangler deploy / absent D1 or rate-limiter binding / raw vars / OAuth-cache fallback.**

Cloudflare's Workers **Script Version Upload** inheritance is from the most recently uploaded Worker version, *not necessarily the deployed one*. Only if a freshly confirmed full `latest_uploaded_version == active_version` and active traffic is exactly 100% can inheritance be proposed. A newer draft or split deployment is **STOP BEFORE MUTATION**. The upload's `inherit` default to `latest` is never interpreted as a pinned UUID; a separately verified equality gate is required.

## Four Routes (both zones, never mutate routing)

- `coloring.rozkalns.net/api/stats/*` in zone `rozkalns.net`
- `ausmalwiese.de/api/stats/*` in zone `ausmalwiese.de`
- `www.ausmalwiese.de/api/stats/*` in zone `ausmalwiese.de`
- `ausmalwiese.de/q` in zone `ausmalwiese.de`

Route owners and the complete route inventory must remain exactly unchanged. No route/DNS/Access/WAF change is part of this job.

## Trusted snapshot required from future protected adapter

`validate_snapshot()` expects sanitized, bounded exact fields (complete active/latest version UUIDs, 100% traffic, deployment UUID, account fingerprint, seven binding names/API kinds, four zone-owned routes, and active/latest compatibility config). Three nonsecret variables and D1/rate-limit identities are checked as **SHA-256 fingerprints** computed inside the trusted reader; secret fingerprints must be `null`. An overall fingerprint of other settings and compatibility flags/date is retained and compared. It must be possible to independently prove the candidate has **no other bindings/routes/settings**; unknown/extra fields, unknown configuration, pagination or split traffic are STOP.

**These Python dicts do not establish authenticity.** The trusted reader must independently authenticate Cloudflare's account/zone/Worker identity, prove its list responses complete (including pagination and version ordering), fetch the full deployed and newest uploaded UUID and associated version metadata, and produce typed sanitized evidence. Browser screenshots, supplied JSON, local fixtures, old SHA or CLI option names cannot substitute for that evidence. The future transport implementation and credential installation need separate technical/security review and explicit owner authorization; neither is delivered here.

## Frozen future two-stage mutation protocol (not authorized)

1. Before first write, verify exact source blob, RPi5 checkout/release identity, trusted account fingerprint, all routes/bindings/config and **twice** read the identical active/latest 100% full version. Bind an immutable operator receipt and owner-signed exact permission for this Worker/source/config/version; the pure `approved` dict in mocked tests is **not owner authorization**.
2. **First mutation:** one Version Upload for the fixed JS source with `bindings_inherit=strict` and all seven `inherit` declarations. On dispatch uncertainty, timeout or error: STOP, no retry or alternate upload, rollback or cleanup.
3. Read back the new full UUID as latest uploaded. Confirm the originally deployed UUID/deployment has *not changed*, all seven inherited bindings and all four routes are unchanged, the compatibility date/flags and overall settings fingerprints are unchanged, and the new version has exactly the reviewed source bytes (the transport must supply a provider-supported code/etag proof). Missing exact code proof is **STOP AFTER UPLOAD**.
4. **Second mutation**, only inside an explicitly preapproved composite LIVE envelope: one `POST /accounts/{account}/workers/scripts/coloring-pages-stats-v1/deployments` with `strategy=percentage` and exactly `[{"version_id": "<NEW-FULL-UUID>", "percentage": 100}]`, never `force=true`.
5. Read back the new 100%-active full UUID and changed deployment ID; preserve all seven binding kinds and targets and four zone-owned routes, and verify public `HEAD /q` gives HTTP 302 to `https://ausmalwiese.de/`, no-store, plus Stats GET endpoints. `GET /q` may increment D1 and must NOT be invoked without separately authorized production analytics write/testing approval. No PUBLISH/import/sitemap/legacy-301 or resumed writers.

The source core defines `future_run_once(trusted, approved, worker_bytes)` for **offline unit simulation**. It has **no source-checkout runnable deployment command**, no credential reader, no direct Cloudflare HTTP client, no installer, no token refresh and no unsafe fallback. A separately installed protected execution boundary must ensure the operator's production calls bind to exactly the reviewed endpoints and are authorized, enforce no HTTP redirects, TLS verification, bounded response sizes/timeouts, and no implicit transport retries. It must independently prove source identity and comprehensive provider metadata before dispatching either write; the current source does not establish LIVE readiness. Any post-mutation mismatch requires STOP with minimum read-only evidence, never rollback or cleanup.

**Important:** two API writes (Version Upload, then Create Deployment) are not atomic. An exact future composite LIVE decision must explicitly permit both in order and describe partial failure handling; do not conceal upload as a read-only prepare step. One code/metadata upload is itself a LIVE mutation and consumes the authorization. This source scope neither installs nor provisions the trusted transport, requests/reads credentials, changes permissions, nor grants any authorization.

## Official references

- [List Worker Versions](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/list/) — first version is latest uploaded.
- [Get Worker Script Version](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/) — version resources and bindings.
- [Upload Worker Version](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/) — `bindings_inherit=strict` and `inherit` behavior.
- [List Worker Deployments](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/) — active traffic splits.
- [Create Worker Deployment](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/create/) — exact version and 100% traffic.
- [Multipart upload metadata](https://developers.cloudflare.com/workers/configuration/multipart-upload-metadata/).

## Gate summary

`#1032` ends at GitHub branch/PR, offline tests, CI and Ready review. **No MERGE, credentials, Cloudflare LIVE, RPi5 host operations or settings changes** occur in this issue. Any operator install, credential provision, API read/write, secret preservation proof, or LIVE deployment requires a fresh exact owner decision and actual access rights. If that trust boundary cannot be completed, status is `SOURCE READY / LIVE STOP`.
