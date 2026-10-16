# Ausmalwiese Fehler melden — report Worker activation preflight (#1030)

**SOURCE ONLY. No merge, credentials, Cloudflare mutation or LIVE approval.**

Canonical application code is in rozkalnsandris/coloring-pages, merged PR #244:
cloudflare/report-worker.mjs and docs/REPORT_ERRORS_V1.md. This RPi5_main
outcome owns only the nonsecret operations plan and offline source validator,
not a duplicate Worker implementation. The exact candidate revision, Git blob,
SHA-256 and previously independently verified Cloudflare account fingerprint
are pinned in ops/contracts/ausmalwiese-report-worker-activation-v1.json.
An operator must independently verify those *exact bytes* and current main
before any future LIVE authorization. Never derive identity from a token.

## Observed read-only baseline (2026-10-16; not LIVE authority)

- Cloudflare Workers & Pages listed only coloring-pages-stats-v1. Existing
  zone routes: ausmalwiese.de/api/stats/* and
  www.ausmalwiese.de/api/stats/*. No dedicated report Worker/route was listed.
- GET https://ausmalwiese.de/api/report/config returned HTTP 404.
- One unrelated Turnstile widget was listed; no widget verified for the
  Ausmalwiese hostnames and action. Brevo transactional readiness and
  the report binding inventory were not verified.
- The existing RPi5 script-settings GET executor is fixed to
  coloring-pages-stats-v1. **Do not** use it for this separate Worker
  or widen its trust boundary.

## Static source preflight

Run, without privilege or credentials, from this source checkout:

    python3 scripts/ausmalwiese_report_worker_preflight.py --check-contract
    python3 tests/test-ausmalwiese-report-worker-preflight-v1.py

The first command validates ONLY the checked-in source contract and returns
SOURCE_CONTRACT_OK_NOT_LIVE_PROOF. Synthetic unit-test candidate metadata does
not prove anything about Cloudflare, Brevo or the live site. The validator has
no generic plan-file loader, API transport, apply mode, protected-data reader,
credential interface, secret printout or runtime mutation.

## Fixed future account, Worker and routing gates

1. Fixed intended Worker: coloring-pages-report-v1; account fingerprint and
   zone name ausmalwiese.de are pinned in the contract. Require independent
   Cloudflare account and zone identity confirmation; a digest is not authority.
   Stats Worker script, bindings and routes are excluded.
2. Routes are *exact paths*, not HTTP-method restrictions:
   - ausmalwiese.de/api/report
   - ausmalwiese.de/api/report/config
   - www.ausmalwiese.de/api/report
   - www.ausmalwiese.de/api/report/config
   Verify Cloudflare permits these patterns as written. Check apex/www
   redirect policy, order, overlap and route baseline independently. Worker
   source enforces POST on /api/report and GET on /api/report/config and
   validates Origin and Turnstile hostname/action. Do not use /api/report*,
   other wildcard catchalls or route rules that capture /api/stats/*,
   /catalog.json, /health, /ready, site detail/print/home or other hostnames.
3. Require correctly scoped public TURNSTILE_SITE_KEY and private
   TURNSTILE_SECRET, with hostnames ausmalwiese.de and www.ausmalwiese.de
   if both receive traffic, action=report and matching siteverify hostname.
   Do not silently reuse an unrelated widget.
4. Require private BREVO_API_KEY and REPORT_TO, never a personal recipient
   in source, GitHub, chat, args or logs. Verify provider transactional API
   eligibility and sender fixed in the canonical coloring-pages report Worker source. The email recipient remains
   a secret under a separately authorized protected provisioning flow.
5. Require REPORT_RATE (12 requests/60 s) and REPORT_DUP (1 request/60 s)
   as distinct Cloudflare Workers Rate Limiting bindings with distinct
   namespace IDs (positive 32-bit integers), plus current Free-plan support.
   The limiter is distributed/approximate and can affect shared Kita networks.
   Enforce exact binding names and kinds, never secret values.
6. Review German Datenschutz purpose, notice, processor arrangements,
   cross-border transfers if applicable, tracking and Brevo retention,
   mailbox deletion policy, Turnstile and sending evidence with the operator.
   This source-only issue is not legal or runtime approval.

## Future single-dispatch activation sequence (NOT AUTHORIZED)

- BEFORE any mutation, prebuild an immutable, exact source/route/settings
  proposal. Verify independent source bytes/revision, account and zone,
  exact pre-existing route inventory, availability and permissions, genuine
  Turnstile and private binding readiness and legal/operator review.
  An unknown or unavailable gate means STOP BEFORE MUTATION.
- Obtain a separately explicit owner-authorized composite LIVE command
  freezing exact operator, target, source digest, ordered mutation classes,
  allowed operations, credentials/permissions gate and recovery semantics.
  Cloudflare Worker creation, secret provisioning, binding deployment and
  route additions are not assumed atomic. No generic shell or OAuth fallback.
- Dispatch ONLY the first frozen mutation. Authority is consumed then.
  Continue later fixed steps only if they are **already** within that same
  authorization and prior results are unambiguous. Any error, drift or
  uncertainty after the first mutation means STOP with minimum sanitized
  evidence, no retry, rollback, cleanup or alternate route.
- Read-only post-verification must prove the intended Worker source and only
  exact routes/binding NAMES and KINDS, two different namespace IDs and
  unchanged Stats routes. Never read or output a secret. Expected HTTP:
  GET /api/report/config -> 200 with public siteKey when configured, 503
  when incomplete, 404 if wrong Worker/not routed; GET /api/report -> 405.
  Existing /api/stats/* must remain unaffected.
- An additional explicitly authorized SINGLE test POST may confirm that
  Brevo returns 201 plus nonempty messageId (accepted, **not delivered**).
  Actual mailbox delivery must be independently checked privately. Avoid
  duplicate send tests or logging tokens, message IDs or email content.
  This source issue authorizes no POST or mail delivery.

## Ownership / immutable boundary

Application: https://github.com/rozkalnsandris/coloring-pages/issues/240
and https://github.com/rozkalnsandris/coloring-pages/pull/244 .
RPi5 source-only gate: https://github.com/rozkalnsandris/RPi5_main/issues/1030 .
Pre-existing stats-only operator:
docs/AUSMALWIESE_WORKER_SETTINGS_EXECUTOR_V1.md and issue #1002.

No GitHub source merge, route change or deployment under this issue can be
interpreted as authorization to change Cloudflare, credentials or LIVE.
