# Private GoatCounter Traffic dashboard

Outcome issue: #1401. Source/tests/docs only; this document is not LIVE authority.

## Data-source boundary

The protected ADMIN Traffic page uses only the documented GoatCounter v2.7.0 JSON API through the existing loopback-only Stats credential. No Cloudflare Traffic/crawler metric, export, database read, raw hit feed or new analytics service is part of this dashboard.

The v3 report uses:

- \`GET /api/v0/me\` for the exact Stats-only, one-site, UTC credential check;
- \`GET /api/v0/paths\` to select only \`/\` and \`/ausmalbild/<7-digit-id>\`;
- \`GET /api/v0/stats/hits\` for per-path visits and the UTC daily trend;
- \`GET /api/v0/stats/toprefs\` and \`campaigns\` for acquisition;
- \`GET /api/v0/stats/locations\`, \`browsers\`, \`systems\` and \`sizes\` for aggregate technical context.

These endpoints are documented at https://www.goatcounter.com/help/api and https://www.goatcounter.com/api.html. The dashboard deliberately does not invent unique-person, conversion, bounce-rate, Cloudflare-request or crawler metrics.

## V3 browser contract

\`GET /api/analytics/origin?days=1|7|30|365\` returns only sanitized aggregates. The base fields remain the selected UTC range, total/homepage/coloring-page visits, daily totals and seven-digit page rankings. It additionally returns six top-ten arrays:

\`referrers\`, \`campaigns\`, \`locations\`, \`browsers\`, \`systems\`, \`sizes\`

Each item is exactly \`{"label": "...", "visits": N}\`. HTTP referrers are reduced to scheme + host (+ non-default port); URL path/query/fragment is never returned. Campaign-like raw query strings are rejected. GoatCounter IDs, account/site metadata, raw API bodies, IP addresses, User-Agent strings and arbitrary page paths are never returned to the browser.

The metric is \`goatcounter_visits\`. GoatCounter documents visits as the first visit to a path in its in-memory session window; this is not a count of unique natural people. Visitors who decline Ausmalwiese optional analytics are absent.

## Resource and failure boundary

The reader remains single-flight with a 45-second deadline, 4 MiB per response, 32 MiB aggregate budget, <=64 GETs and 0.35 seconds between request starts. Stats/hits batches are <=20 paths for 365 days and <=50 for shorter periods. Aggregate dimensions use <=100 selected path IDs per request and GoatCounter's documented maximum stats result limit of 100. Browser-visible lists are capped to the top ten sanitized labels.

Successful reports are cached for 60 seconds. Empty data is valid zero; missing credential, busy state, malformed API data, budget exhaustion or upstream failure remain unavailable and are never converted to zero. No retry, export, redirect, arbitrary URL, database access or public test event is introduced.

## Deployment boundary

The backend capability becomes \`origin_report_version: 3\`. The UI-only installer must refuse v3 HTML against an older backend. Merge does not authorize LIVE; a later exact owner gate is required for deployment.
