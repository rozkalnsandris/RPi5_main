# Private GoatCounter reporting in ADMIN

Outcome issue: #1326. Source-only; this document is not LIVE authority.

## Visible outcome

The protected ADMIN has a separate **Origin requests** view at `#origin` with
UTC today/7/30/365-day totals, daily rows and a ranking of seven-digit page IDs.
Historical IDs remain visible even if a page is no longer in the catalogue.
Cloudflare Traffic and the existing Like/Print/QR/campaign data are unchanged.

These are recorded detail requests, not people or successfully displayed pages.
Cache hits do not reach the origin; repeats, bots, 304s and requests failing
after the mirror may count. Collector/backend delivery failures may lose counts.
Every range includes the incomplete current UTC day. Retention is 365 days;
there is no all-time claim and no reconstruction of periods before activation.
An empty report does not establish that public counting is enabled.

## Reader and trust boundary

`ops/bin/coloring-pages-admin-publish` serves exactly
`GET /api/analytics/origin?days=1|7|30|365`. Extra/repeated/unknown parameters
return 404. The ADMIN marker and same-origin/Fetch Metadata checks reject browser
cross-site use. The marker is **not authentication**: the existing protected
ADMIN ingress/Cloudflare Access policy and loopback listener remain the actual
access boundary. No public route or new ingress is introduced here.

The reader uses only `127.0.0.1:9194`, Host
`goatcounter.ausmalwiese.invalid`, and these GoatCounter 2.7.0 GETs:

1. `/api/v0/me`: require permissions exactly 64 (Stats), a single explicit site
   equal to the user site, and user timezone UTC or Etc/UTC. This response includes
   account metadata, which is discarded and never sent to ADMIN or logs.
2. `/api/v0/paths?limit=200&after=<cursor>`: discover up to 2,000 path records.
   Select only non-event `/origin-detail-request/<seven-digit-id>` names.
3. `/api/v0/stats/hits`: batches of 25 selected numeric path IDs, limit 100,
   `daily=true`, UTC start 00:00 and end 23:00 (inclusive hourly API boundary).
   Empty selection performs **no** stats request: an empty filter means all paths
   in GoatCounter. Never include the old browser-count namespace.

Daily and hourly sums, page totals, batch totals, IDs, dates, pagination and safe
integer bounds are validated before any result is returned. Only counts, dates,
the metric identity and page IDs leave the reader. Titles, account details,
credentials, referrals, visitor data and individual hits do not. No SQL, exports,
arbitrary URLs, redirects, inherited proxies or client headers are used.

Resource limits: one in-flight report, <=51 GETs, 0.35 seconds between request
starts (below the upstream four-per-second read limit), <=1,000 selected IDs,
4 MiB per response, 32 MiB total, 45-second aggregate deadline with <=4 seconds
for a socket operation. A large report exceeding a bound fails in full; it is
never represented as a truncated successful total. Successful in-memory results
are cached for 60 seconds, keyed by UTC date, range and credential fingerprint.
Recent events may still await GoatCounter processing. Failures clear cached
results and impose a five-second cooldown. No on-disk report cache is created.
Batches are read sequentially, not in a database snapshot transaction; new counts
or paths arriving during a report appear on a later refresh.

The UI loads lazily and uses safe text nodes. It clears displayed data while
refreshing and on failure, rejects stale responses, and distinguishes not
connected, temporarily busy, unavailable and a genuine successful zero. Ranking
rows are shown 25 at a time; all daily rows are in an expandable scrollable table.

**Authenticated GETs can update GoatCounter token last-used metadata.** This is
an aggregate reader with no count/settings methods, not a promise of a byte-for-
byte read-only database. Future production verification must authorize that
existing-credential use and protected account metadata, even without events.

## Installation and separate credential opt-in

The existing full ADMIN installer deploys the updated executable and HTML. No
new Python dependency is required. UI-only mode now requires capability
`origin_report_version: 1` before writing HTML, so an old backend must first be
updated under the normal separate ADMIN installation authorization.

The ordinary installer does **not** install the reporting drop-in, provision a
token or read the private GoatCounter DB. With no systemd credential, the report
returns 503 `not_configured` and makes no upstream request. Existing default unit
and public collector configuration are unchanged.

Opt-in source: `ops/systemd/coloring-pages-admin-origin-report.conf`. Its exact
future destination is
`/etc/systemd/system/coloring-pages-admin-publish.service.d/origin-report.conf`.
It loads `/etc/ausmalwiese-goatcounter/stats-token` as `goatcounter-stats`, which
the application reads only at
`/run/credentials/coloring-pages-admin-publish.service/goatcounter-stats`.
The credential must be a regular, private file with no group/world access;
the persistent source should be root-owned 0600. It is never an environment
variable, command-line bearer token, HTML field or GitHub secret/artifact.
Installing this opt-in before provisioning the credential makes systemd fail
startup; do not install it prematurely.

The existing `/etc/ausmalwiese-goatcounter/pageview-token` stays count-only and
must not be reused or have its permissions widened. The report token must have
only Stats (64), one explicit site, and a UTC reader user. A stats token can read
all site statistics at the upstream API; prefix restriction is enforced by this
adapter, not by a fictitious prefix-level token permission.

## Future bounded rollout preparation

After source merge, prepare one exact-main Composite LIVE plan before requesting
owner authorization. This PR does not supply a ready runtime baseline or consume
an older authorization. The plan must bind:

- Fresh protected ADMIN/GoatCounter unit and account metadata, app version and
  credential presence/permissions, without printing token or raw config.
- Separate stats-only token provisioning for the correct site/UTC user; use a
  dedicated UTC reader user if needed rather than silently changing the owner's
  timezone. Freeze exact account/database mutation limits and capture the new
  token directly into the protected file with no token in terminal output.
- Full ADMIN source installation if needed, then the one opt-in drop-in and one
  explicitly authorized ADMIN service restart. Provision the credential before
  enabling the drop-in. Do not invoke the installer under source-only authority.
- Bounded authenticated GET verification: `/me` permission/timezone booleans,
  the actual ADMIN report shape/totals, no credential in responses, and existing
  unauthenticated ADMIN ingress denial. Do not generate public pageviews as a
  test. Record only sanitized counts/statuses/hashes; raw account/API responses
  and the new token are protected.
- Stop on any failure; no implicit retry, rollback, credential deletion,
  permission widening or alternate deployment path.

Reporting deployment alone never enables public counting. Public app origin
variant deployment still needs trusted SIMPLE-DEPLOY/reconciler integration,
fresh authorized runtime evidence, legal/notice completion and explicit
activation authority. Coloring-pages #440 merged at
`8d0de541e03f2db1196fb89569d549fb2294abfb`; its source proof is not deployment
evidence. Private collector evidence remains the dated verification receipt on
RPi5_main #1275. No fresh LIVE observation is claimed here.

## Validation and provenance

- `python3 tests/test-ausmalwiese-goatcounter-report-v1.py`: aggregate filtering,
  pagination, UTC windows, totals, failure/cache/credential/HTTP boundaries.
- `node tests/test-coloring-pages-admin-origin.cjs`: actual inline renderer,
  period changes, safe DOM, empty/error states, stale-response rejection.
- Existing ADMIN publication, navigation, categories and analytics regressions.
- `tests/goatcounter-report-isolated-v27.py`: automatic PR CI with official
  v2.7.0 amd64 archive size 13,935,060 and SHA-256
  `98d221cb9c8ef2bf76d8daa9cca647839f8d8b0bb5bc7400ff9337c5da834511`.
  Only a non-root, network-none, read-only-root container and new temporary
  synthetic SQLite fixture are used. Exercise empty paths, >25 origin paths,
  old namespace exclusion, real UTC/day totals and count-token rejection. Fixture
  setup SQL never exists in the production reader and is not an operational
  provisioning recipe. No production credential or public counting endpoint.

API contract reviewed against [official API documentation](https://www.goatcounter.com/help/api)
and pinned [handlers/api.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/handlers/api.go),
[hit_list.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/hit_list.go),
[api_token.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/api_token.go)
and [site.go](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/site.go).
The upstream v0 API may change; an upgrade requires renewed compatibility proof.
