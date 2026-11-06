# Private GoatCounter consent-visit reporting in ADMIN

Outcome issue: #1376. Source-only; this document is not LIVE authority.

## Visible outcome

The protected ADMIN keeps the existing `#origin` route, but the view now reports the
consent-gated GoatCounter pageviews actually emitted by the public Ausmalwiese app.
The navigation/title is **GoatCounter visits**.

UTC today/7/30/365-day reports include:

- total consent pageviews;
- homepage (`/`) visits;
- coloring-page (`/ausmalbild/<seven-digit-id>`) visits;
- count of coloring-page IDs with visits;
- daily totals;
- per-coloring-page ranking.

These are pageviews, not unique people. Visitors who do not choose optional analytics
are intentionally absent. Cloudflare Traffic and Like/Print/QR statistics remain
separate.

## Reader and trust boundary

`ops/bin/coloring-pages-admin-publish` continues to serve exactly
`GET /api/analytics/origin?days=1|7|30|365`. The endpoint name is retained for
stable ADMIN routing; the response contract is version 2 with metric
`consent_pageviews`.

The reader uses only `127.0.0.1:9194`, Host
`goatcounter.ausmalwiese.invalid`, and the existing stats-only GoatCounter 2.7.0
credential. It performs only bounded authenticated GETs:

1. `/api/v0/me`: require Stats permission exactly 64, one explicit site, UTC timezone.
2. `/api/v0/paths?limit=200&after=<cursor>`: select only non-event `/` and
   `/ausmalbild/<seven-digit-id>` records. Old `/origin-detail-request/...`,
   browser-counter namespaces, query variants and every other path are ignored.
3. `/api/v0/stats/hits`: request only selected numeric path IDs, with UTC daily
   aggregates and the existing response/request/time bounds.

An empty selection performs no stats request because an empty GoatCounter path filter
would mean all paths.

Only sanitized aggregate counts, UTC dates and seven-digit coloring-page IDs leave the
reader. No raw hit, IP address, referrer, User-Agent, title, account metadata, token,
arbitrary path or upstream error body is returned or logged.

The version-2 response has:

```json
{
  "version": 2,
  "status": "ok",
  "metric": "consent_pageviews",
  "total": 0,
  "homepage_visits": 0,
  "ausmalbild_visits": 0,
  "daily": [{"day": "YYYY-MM-DD", "visits": 0}],
  "pages": [{"page_id": "1234567", "visits": 0}]
}
```

The adapter validates that homepage + coloring-page visits equals total, the per-page
ranking sums to coloring-page visits, and daily totals sum to total.

## Resource and failure behavior

The existing bounded reader semantics remain: one in-flight report, <=51 GETs,
0.35 seconds between request starts, <=1,000 coloring-page IDs plus the homepage,
4 MiB per response, 32 MiB aggregate response budget and 45-second deadline.
The 365-day report uses batches of at most five paths; shorter windows use at most 25.

Successful reports are cached in memory for 60 seconds. Failures clear cached results
and return a sanitized unavailable/busy/not-configured state. There is no report file,
SQL access, export, redirect, arbitrary URL or direct production database read.

Authenticated GETs can update GoatCounter token last-used metadata. The credential
remains the dedicated Stats-only systemd credential and must never be replaced by the
count token.

## UI/backend compatibility

`/api/analytics/capabilities` now advertises `origin_report_version: 2`.
The UI-only installer requires version 2 before writing the new HTML, preventing a new
GoatCounter-visits UI from silently running against the old origin-detail-request
backend contract.

The `#origin` hash and `/api/analytics/origin` endpoint remain stable to avoid
breaking bookmarks or ingress rules.

## Installation and LIVE boundary

The ordinary ADMIN source/install boundary is unchanged. This source change does not
provision credentials, change GoatCounter settings, mutate the database, restart a
service, alter Cloudflare/Tunnel routes or generate synthetic public visits.

A future LIVE rollout must separately authorize the exact merged `RPi5_main` SHA and
the existing ADMIN deployment/service lifecycle required to install the updated backend
and HTML. Verification should use only sanitized aggregate response fields and must not
print the credential or raw GoatCounter API responses.

## Validation

Focused tests:

- `python3 tests/test-ausmalwiese-goatcounter-report-v1.py` — path allowlist,
  aggregate split/totals, UTC windows, pagination, credential and HTTP boundaries.
- `node tests/test-coloring-pages-admin-origin.cjs` — version-2 UI validation,
  KPI/ranking/daily rendering, safe DOM, error states and stale-response rejection.
- `tests/goatcounter-report-isolated-v27.py` — pinned GoatCounter v2.7.0 isolated
  synthetic proof with homepage + coloring-page hits and exclusion of old namespaces.
- `tests/test-coloring-pages-admin-publish-v1.py` — UI-only installer requires
  `origin_report_version: 2`.

The upstream API remains pinned to GoatCounter v2.7.0; an upstream upgrade requires
renewed compatibility proof.
