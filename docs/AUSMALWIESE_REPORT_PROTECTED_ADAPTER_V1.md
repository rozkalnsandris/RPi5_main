# Ausmalwiese Report Worker — protected adapter and installer source (#1039)

**SOURCE ONLY. NOT INSTALLED. NO AUTHENTICATED CLOUDFlARE TRANSPORT OR LIVE AUTHORITY.**

Frozen base: ea411dd3a9d6d697ef9a234c2ea4a8d396dfaa59.
Owner scope: REPORT-ONLY-ADAPTER-AND-INSTALLER-SOURCE, OFFLINE-TESTS, PR, CI, REVIEW; NO-MERGE NO-LIVE NO-CREDENTIAL-ACCESS NO-SETTINGS NO-RETRY.

## What was built

- scripts/ausmalwiese_report_protected_adapter.py: immutable REST method/path blueprints, six-binding name/kind policy, namespace collision detection, strict response sanitizer and offline one-shot order ledger. It has NO HTTP transport and NO credential reader; an in-memory ledger is not an owner-authorized durable stop barrier.
- scripts/ausmalwiese_report_protected_installer.py: pure pinned-blob installation plan plus strict validation of externally supplied sanitized root ownership, path/mode/hash/symlink parent metadata. It has NO install, write, sudo or privileged entrypoint command.
- ops/contracts/ausmalwiese-report-protected-adapter-v1.json: frozen machine-readable scope. Tests validate exact source contract and forbid scope expansion.
- tests/test-ausmalwiese-report-protected-adapter-v1.py: offline-only negative tests and malformed response/namespace/route/source/install checks; no real Cloudflare access.

This source does not install an executable operator. A separately reviewed protected transport, private binding provisioner and root-owned installer remain mandatory and need distinct owner authorization. A synthetic snapshot, root metadata dict or fixed URL cannot establish live account identity or user authority.

## Fixed target and exact four routes

Production Worker: coloring-pages-report-v1; zone: ausmalwiese.de; pinned account fingerprint SHA-256 3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34. Real account and zone IDs must be independently authenticated by a trusted collector and must not be entered in repository source.

Worker bytes pinned from coloring-pages at a90c6a6a7ccca2941d99e9edddd5cfa31ac9ed18, cloudflare/report-worker.mjs:
Git blob 6d2359752d12f4a40847008fc7fdcc457124e893
SHA-256 26d4e597d8c2c961c3a637957ea566654c97c5657a4b2595129c410e9fae22a1.

Exact routes only:
- ausmalwiese.de/api/report
- ausmalwiese.de/api/report/config
- www.ausmalwiese.de/api/report
- www.ausmalwiese.de/api/report/config

Query strings do not match exact route patterns. No wildcard fallback, Stats routes, /q, DNS or Cloudflare account settings. Existing coloring-pages-stats-v1 and all its bindings/routes are excluded.

## Six binding NAMES and API kinds only

- TURNSTILE_SITE_KEY: plain_text
- TURNSTILE_SECRET: secret_text
- BREVO_API_KEY: secret_text
- REPORT_TO: secret_text
- REPORT_RATE: ratelimit, 12 requests per 60 seconds
- REPORT_DUP: ratelimit, 1 request per 60 seconds

Two different positive decimal namespace IDs must be selected and independently checked for account-wide collisions. Real values of public/secret bindings and private mailbox addresses are not in GitHub, tests, API request blueprints, process arguments or logs.

## Future Cloudflare method restrictions (NO CURRENT SEND)

- POST /client/v4/accounts/{account_id}/workers/scripts/coloring-pages-report-v1/versions
- POST /client/v4/accounts/{account_id}/workers/scripts/coloring-pages-report-v1/deployments
- POST /client/v4/zones/{zone_id}/workers/routes

Upload is SEALED_MULTIPART_PRIVATE_PROVISIONER_REQUIRED, not a constructed request body. Cloudflare Version Upload requires private text for secret_text bindings. Therefore this adapter CANNOT upload a usable Worker by itself. A separately approved protected provisioner must prepare all SIX bindings atomically and prove account permissions before the first request; otherwise STOP BEFORE MUTATION.

The legacy PUT script API is forbidden because it may activate code immediately. Actual future Cloudflare API responses must be checked by a trusted read-only independent collector for source digest, exactly six bindings, two namespaces and unchanged unrelated Worker/route state. A returned version ID or successful unit test does NOT establish deployment.

For future operator transport, a durable owner-authenticated single-use receipt must be consumed BEFORE the first mutation, with exact HEAD and target/baseline binding. The source in-memory ledger is a test-only order guard; it cannot prevent retries across processes. Any ambiguity or failure after first mutation is STOP, no retry, rollback, cleanup or workaround.

## Installer plan and release trust

Proposed immutable targets only:
- /usr/local/libexec/rpi5-ausmalwiese-report-protected/adapter.py
- /usr/local/libexec/rpi5-ausmalwiese-report-protected/contract.json
- /usr/local/libexec/rpi5-ausmalwiese-report-protected/release.json
- /usr/local/sbin/rpi5-ausmalwiese-report-protected

All directory ancestry must be root-owned, without symlinks and writable only by root. Files must be root-owned, exact pinned digests and fixed modes; no hardlinks or overwrite. This source DOES NOT install these targets. A future approved privileged installer must separately prove trusted source bytes, parent checks, atomic copy safety, authority, and post-install hash checks. The offline metadata checker is not runtime evidence.

## Offline verification

    python3 scripts/ausmalwiese_report_protected_adapter.py --check-contract
    python3 scripts/ausmalwiese_report_protected_installer.py --check-contract
    python3 tests/test-ausmalwiese-report-protected-adapter-v1.py

Any other CLI argument is rejected. These tests cannot call Cloudflare, read secrets, install software or send email.

## Additional required gates

Separate exact-head MERGE; security-reviewed protected transport/provisioner/installer; independently verified Cloudflare Worker Scripts Write and Routes Write capabilities, account and zone; Turnstile/Brevo provider readiness; German Datenschutz/retention review; separate Composite LIVE authorization and sanitized post-verification. This source-only PR supplies none of those approvals.

Related: RPi5_main issues #1030, #1036 and #1039; coloring-pages #240, PR #244.

Official Cloudflare docs:
https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/
https://developers.cloudflare.com/api/resources/workers/subresources/routes/methods/create/
https://developers.cloudflare.com/workers/configuration/multipart-upload-metadata/
