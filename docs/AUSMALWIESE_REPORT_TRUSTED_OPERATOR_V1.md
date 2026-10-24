# Ausmalwiese report Worker trusted operator protocol (#1036)

SOURCE ONLY — NOT INSTALLED — NO AUTHENTICATED TRANSPORT — NO LIVE AUTHORITY.

## Frozen scope

The owner explicitly authorized only SOURCE/TESTS/DOCS, a single issue, Draft PR, CI and review at RPi5_main main c0b5037db3ef885d2b97ba70b2ce51f9c0918447. Merge, LIVE, credentials, secrets, Cloudflare settings, retries, rollback and cleanup are excluded.

This source-only Python protocol is not an executable Cloudflare deployment operator. It has no authenticated HTTP transport, credential reader, secret provisioner, installer or privileged CLI. Future runtime work requires an independently reviewed protected adapter, exact target permissions and a fresh, separately explicit owner LIVE approval. This issue does not create that adapter.

Canonical report Worker: coloring-pages/cloudflare/report-worker.mjs at application commit a90c6a6a7ccca2941d99e9edddd5cfa31ac9ed18, blob 6d2359752d12f4a40847008fc7fdcc457124e893, SHA-256 26d4e597d8c2c961c3a637957ea566654c97c5657a4b2595129c410e9fae22a1. The protected future adapter must verify exact original bytes independently. Never trust a filename, synthetic snapshot, or caller assertion.

The target is only coloring-pages-report-v1 / production / ausmalwiese.de / the previously independently verified account fingerprint. Existing coloring-pages-stats-v1 script, routes and all seven existing bindings MUST remain unchanged.

## Exact routes and bindings

Only four narrowly pinned routes:
- ausmalwiese.de/api/report
- ausmalwiese.de/api/report/config
- www.ausmalwiese.de/api/report
- www.ausmalwiese.de/api/report/config

Cloudflare routes match the whole URL, including query strings; an exact route without a terminal wildcard does not match query-bearing requests. Confirm the site's clean API paths before runtime work. No wildcard widening, no /api/stats/*, no catchalls, no DNS changes.

Exactly six Worker binding NAMES and API kinds:
- TURNSTILE_SITE_KEY: plain_text
- TURNSTILE_SECRET: secret_text
- BREVO_API_KEY: secret_text
- REPORT_TO: secret_text
- REPORT_RATE: ratelimit (12 requests per 60 seconds)
- REPORT_DUP: ratelimit (1 request per 60 seconds)

The namespace IDs for REPORT_RATE and REPORT_DUP must be distinct positive decimal strings (32-bit range) and verified account-wide. The source contract contains NO real namespace IDs, secret values, private recipient, session data or token. Private provisioning is a separate future owner-approved protected operation; the source never transports secrets. A public site key is not license to print private binding configuration.

## Future six-dispatch handshake — not authorized now

A later protected adapter is responsible for independently verifying current account/zone identity, exact source bytes, existing routes, separate worker, supported version upload capability, Turnstile hostname and action, Brevo account eligibility and IP policy, six binding names/kinds and private ready provisioning, legal/Datenschutz requirements, and a valid owner LIVE envelope. Unknown preflight => STOP BEFORE MUTATION.

Synthetic future_protocol models exactly:
1. Two independent, identical, sanitized read-only snapshots. Report Worker MUST be absent, the target routes free and unrelated route digest pinned.
2. One report-only version upload with separately protected six-binding provisioning; verify the version, exact code digest, six names/kinds, and two distinct rate namespace IDs.
3. One 100%-traffic version deployment; verify source/active version and no unintended early activation.
4. One exact route addition per route (four total), with read-only full verification after each, preserving unrelated routes.

Six total future mutation dispatches, each within a separately approved composite LIVE envelope. The approval dictionary in source is a SHAPE ASSERTION, not owner identity, authorization, credential access or an install mechanism. The protected adapter must authenticate the owner gate and account independently. Cloudflare script PUT routes which could automatically deploy or bypass six-binding security are NOT a fallback. Missing capability => STOP before any write.

After the first mutation, ANY error, ambiguity, drift, network uncertainty or incomplete result means STOP with minimum non-sensitive evidence. No retry, rollback, cleanup, unreviewed alternate transport, service deployment or manual workaround.

## Still required before LIVE

- Exact-head CI/reviews and separate MERGE approval for #1036.
- A new separately scoped security-reviewed protected adapter/installer, credentials and Cloudflare permissions. This issue adds neither one.
- Fresh route/binding inventory, provider/Turnstile readiness and official Cloudflare API semantics.
- Owner legal/privacy review for German families/Kitas, Brevo processor/retention and operator mailbox deletion policy; none is signed off by this issue.
- New exact LIVE authorization bound to immutable source and protected operator, with explicit ordered mutation categories, limits and STOP semantics.
- Read-only post-deploy Worker/version/routes/binding NAMES and KINDS evidence, unchanged Stats Worker, config endpoint 200/503; no live claims from synthetic tests.
- A separately authorized SINGLE real report POST and privately verified mailbox arrival. Brevo 201 plus messageId means accepted, NOT delivered.

## Offline validation

Run from RPi5_main source checkout:

    python3 scripts/ausmalwiese_report_worker_trusted_operator.py --check-contract
    python3 tests/test-ausmalwiese-report-trusted-operator-v1.py

Only --check-contract is an exposed CLI option; it emits SOURCE_CONTRACT_OK_NOT_LIVE_PROOF. Unit tests use memory-only synthetic snapshots and a test-specific mocked byte validator, never real Cloudflare, tokens or messages. Makefile runs the suite.

Dependencies: RPi5_main #1030 / PR #1031; RPi5_main #1032 / PR #1033 (Stats-only reference, not reused); coloring-pages #240 / PR #244.
Documentation: https://developers.cloudflare.com/workers/configuration/routing/routes/
https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
https://developers.brevo.com/reference/send-transac-email
