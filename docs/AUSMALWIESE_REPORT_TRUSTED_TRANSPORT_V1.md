# Ausmalwiese report Worker — sealed HTTPS transport source (#1042)

**SOURCE ONLY / NOT INSTALLED / NO CLOUDflare SEND / NO SECRET READ / NO LIVE.**

Owner command freezes RPi5_main base ca027eb96287a996b3b28ff292860b4f933296e6, issue #1042, one branch + Draft PR + CI/review. No merge, credentials, settings, RPi5 or Cloudflare mutations, retry, rollback or cleanup.

## Outcome and boundaries

The source-only module scripts/ausmalwiese_report_trusted_transport.py adds four independently testable pieces:

1. **HTTPS transport description and strict response decoder.** Fixed api.cloudflare.com:443, HTTPS with certificate verification, proxy=null, redirects=false, retries=0; only POST for a report Worker version upload, deployment and four exact report routes. Account ID is checked against a pinned SHA-256 digest and zone ID has strict hex format; future independently authenticated zone-name proof remains mandatory. It emits blueprints, not requests. No socket, HTTP client, credentials, generic URL, token, retry, or send CLI is wired. The prior adapter in scripts/ausmalwiese_report_protected_adapter.py remains source-only.
2. **Private six-binding provisioning policy.** Exact binding kinds: TURNSTILE_SITE_KEY:plain_text, TURNSTILE_SECRET:secret_text, BREVO_API_KEY:secret_text, REPORT_TO:secret_text, REPORT_RATE:ratelimit and REPORT_DUP:ratelimit. Limits are 12/60 and 1/60 with two different positive decimal namespace IDs. The module validates a sanitized future protected-provider attestation, not secret values. It requires Turnstile hostnames ausmalwiese.de and www.ausmalwiese.de and action report. The user must never paste keys/recipients in source, messages, CI, arguments or logs.
3. **Independent version/code verification shape.** Read-only evidence must prove exact pinned Worker code SHA-256 26d4e597d8c2c961c3a637957ea566654c97c5657a4b2595129c410e9fae22a1 and original Git blob 6d2359752d12f4a40847008fc7fdcc457124e893, exact active version, six bindings and rates, distinct namespaces, only report routes and stable unrelated Stats-route inventory digest. A string claiming independent collector origin can be forged; the separately reviewed protected adapter must authenticate the evidence source and prove actual code bytes, version and recipient provisioning using trusted Cloudflare reads.
4. **Persistent one-shot journal semantics for offline tests only.** OfflineDurableGate writes fixed step-N.reserved files with O_NOFOLLOW + O_EXCL, 0600 permissions and fsync(file)+fsync(directory) BEFORE a future send. A second process cannot reserve the same step after a simulated crash. Advancement needs a separate step-N.verified digest from independently validated evidence. Six ordered steps only: upload, deploy, four routes. No retry, rollback, delete or cleanup. This class refuses use outside explicit synthetic_test_only; it is not a hardened root-owned installed authorization gate, and does not prove the real collector or ownership authority. A future protected journal needs stricter root-ancestor checks, immutable owner gate, atomic trust storage and reviewed installer.

## Exact target

- Cloudflare Worker: coloring-pages-report-v1, zone ausmalwiese.de, account pinned by hash. Never touch coloring-pages-stats-v1.
- Canonical Worker bytes: coloring-pages@a90c6a6a7ccca2941d99e9edddd5cfa31ac9ed18/cloudflare/report-worker.mjs, exact SHA-256 and blob above.
- Four routes: ausmalwiese.de/api/report, ausmalwiese.de/api/report/config, www.ausmalwiese.de/api/report, www.ausmalwiese.de/api/report/config. No wildcard /api/report*, /api/stats/*, DNS, any other hostname or query string routes.
- Fixed provider endpoints from the prior source-only contract: POST /client/v4/accounts/{account_id}/workers/scripts/coloring-pages-report-v1/versions, POST /client/v4/accounts/{account_id}/workers/scripts/coloring-pages-report-v1/deployments and POST /client/v4/zones/{zone_id}/workers/routes. No legacy script PUT.

## STOP before any future LIVE

All conditions below remain outside this scope and must be independently proven before separately authorized LIVE work:

- Root-owned protected installer, verified trusted release digest and owner-authenticated durable one-shot authorization; no execution of source checkout.
- Actual HTTPS/TLS transport with a separately scoped Cloudflare credential, no ambient proxy, no redirects, bounded bodies, explicit API errors with sanitized stop, no retries.
- Private in-memory six-binding multipart upload provisioner. Cloudflare secret_text entries require protected values. This source cannot form a usable upload and must not use dummy values; a real provisioner requires separate authorization.
- Read-only trusted account and zone identity, route conflict/precedence and API capability evidence, exact version/content GET proof. Never accept fabricated attestation JSON as proof.
- Reviewed Germany Datenschutz basis, Brevo sender/transactional eligibility and privacy/retention, Turnstile configuration and source-contract account identity; no assumed legal sign-off.
- Explicit separate owner composite LIVE command identifying target, exact immutable source and installed adapter, individual allowed operations and immutable baselines, and no-retry/rollback failure semantics.

The source module CLI accepts ONLY --check-contract. It never sends an API call, connects to a provider or reads private data. This issue adds neither an authenticated network channel nor a private-provisioning implementation. It is a bounded source interface and offline safety model, NOT a ready-to-deploy operator.

## Offline tests

    python3 scripts/ausmalwiese_report_trusted_transport.py --check-contract
    python3 tests/test-ausmalwiese-report-trusted-transport-v1.py

The tests use synthetic identifiers/proofs and temporary local directories only, with no production runtime access. Makefile includes the suite.

Dependencies: RPi5_main #1030, #1036, #1039; merged PRs #1031, #1037, #1041. App: coloring-pages #240, PR #244.
Official references:
https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/
https://developers.cloudflare.com/api/resources/workers/subresources/routes/methods/create/
https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
