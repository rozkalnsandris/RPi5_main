# Ausmalwiese legacy domain 301 — source-only redirect plan (#996)

**Status: SOURCE REVIEW ONLY; no Cloudflare Rulesets permission, no API/token access,
no LIVE change and no owner permission/merge inferred.**

## Frozen outcome

After `coloring-pages` completes the destination move, the old host
`coloring.rozkalns.net` should do only a single **301** to
`https://ausmalwiese.de` preserving path and query. Do not collapse details,
print pages, media or campaigns to the homepage. Other `rozkalns.net` hosts
are outside this rule. The exact candidate contract is
`ops/contracts/ausmalwiese-legacy-redirect-v1.json`.

Cloudflare dashboard on the **rozkalns.net** zone → Rules → Redirect Rules,
one Single Redirect with **Wildcard pattern**:

| Property | Value |
| --- | --- |
| Request URL | `http*://coloring.rozkalns.net/*` |
| Target URL | `https://ausmalwiese.de/${2}` |
| Status | `301` |
| Preserve query string | **Enabled** |

Cloudflare's documented API expression equivalent is
`wildcard_replace(http.request.full_uri, r"http*://coloring.rozkalns.net/*", r"https://ausmalwiese.de/${2}")`
with `action=redirect`, `status_code=301` and
`preserve_query_string=true` at zone `http_request_dynamic_redirect`.
**Candidate only**: not a live API body and not a right to add a rule. Confirm
actual Cloudflare version, phase, rule order, conflict/duplicate, Free quota,
correct zone and proxying through fresh zone-level read-only evidence first.
If Cloudflare Rulesets permissions/trust have not been separately authorized,
STOP rather than repurposing the existing Access/Tunnel/DNS/WAF credentials.
A dashboard route, if deliberately selected by the owner, still needs explicit
owner LIVE authorization for the exact action.

## Destination acceptance — must be completed BEFORE old-host redirect

1. `coloring-pages#213` / PR #214 remains a **separate repo**.
   Its `canonical`/robots/static sitemap/catalogue generator/QR source must
   be reviewed, merged by a separate owner command, auto-LIVE reconciled and
   publicly verified at the new hostname. `RPi5_main#996` cannot merge it.
2. The RPi5 `/sitemap.xml` route **prioritizes the runtime content-store XML**
   over the image-bundled sitemap. The new catalogue generator requires a
   separate reviewed blob repin, catalogue-writer exclusion, exact-binary
   validation, an owner-approved sitemap publication and read-only checks of
   the full LIVE ID set. New `robots.txt` must link to the new sitemap.
3. Independently deploy the reviewed Stats Worker `/q` new-home destination,
   with its own explicit Cloudflare authority. Verify a no-store 302 directly
   to `https://ausmalwiese.de/`, no unintended counter increments for HEAD,
   prefetch or verified bots, and no open redirect from query parameters.
   Never infer that a changed Worker source is deployed by app-image merge.
4. Validate `/api/stats/*` on the new host, including relevant **POST** calls
   by an approved test path. Cloudflare documents that a 301 can change POST
   to GET when followed. Consequently **do not assume** an existing legacy
   POST caller will survive a 301; migrate or retire these clients first.
   Confirm actual /health and /ready monitoring target migration; this wildcard
   also redirects those old-host endpoints unless the owner explicitly agrees
   to a more limited rule. Do not silently exclude them.
5. Confirm both old/new HTTPS certificates, path mapping for campaign links,
   media and print URLs; handle any old-only endpoint without dropping functionality.
   Do not infer Google Search Console domain verification merely from the
   existence of a TXT DNS record.

## Read-only preflight, no request credentials

- Inspect the **rozkalns.net** zone's current `http_request_dynamic_redirect`
  entry point and ordering through an independently owner-authorized read-only
  method, or an authorized Cloudflare owner dashboard session. Do not dump any
  raw ruleset configuration or protected credentials into logs/chat; report
  only tightly allowlisted rule presence, conflict, order, zone and quota.
- Ensure the exact hostname is proxied by Cloudflare and already has valid TLS.
  Verify no existing overlapping redirect, no higher-priority incompatible
  rule, no accidental other-host impact, and new destination health.
- Freeze exact rule candidate, zone, current baseline, one-action budget,
  no retry/rollback policy, pre/post-evidence and explicit owner LIVE decision
  before **any** Cloudflare mutation. A source PR merge never permits LIVE.

## Post-cutover public verification matrix

With **unforced** HTTP requests (no DNS override, no automatic redirect-follow
while checking status/Location), verify:

| Old request | Expected Location | Status |
| --- | --- | --- |
| `/` | `https://ausmalwiese.de/` | 301 |
| `/?campaign=kita-01` | `https://ausmalwiese.de/?campaign=kita-01` | 301 |
| `/kita` | `https://ausmalwiese.de/kita` | 301 |
| `/detail.html?id=1234567` | same path and query on new host | 301 |
| `/print.html?id=1234567` | same path and query on new host | 301 |
| `/media/1234567/print.png` | same path on new host | 301 |
| `/api/stats/rankings`, `/q` | same path; verify new-host endpoint behavior | 301 |
| `/health`, `/ready` | same path **only after monitoring migration** | 301 |

The values above are *examples*, not fabricated LIVE catalogue IDs or active
rules. Test unrelated hosts remain unaffected, no loops/chains, and that
the new host returns 200 and self-canonical HTML with an entirely new-origin
runtime sitemap. Verify retained original print quality. Search Console
Change of Address remains an owner-only follow-up after verification.

## Evidence / authority

At 2026-10-13 discovery, `RPi5_main/main` was
`0005ef498fd40352901e2ac7f95d4a96e8937caa`, and `coloring-pages`
PR #214 had passed source CI but had **not** merged. Read-only public
`GET /api/stats/rankings` was HTTP 200 on the three hosts then; automated
`HEAD /q` returned 403 and is **not proof** of Worker route compatibility.
These are historical observations, not preflight authority.

No existing Rulesets read/credential or live edit is authorized by
`AUTO-RUN FULL RPi5_main #996`. New Rulesets permission/credential, production
redirect activation or changes to `coloring-pages` require explicit distinct
owner permission and current evidence. No retry/rollback/cleanup on ambiguity.

Cloudflare docs:
https://developers.cloudflare.com/rules/url-forwarding/examples/redirect-all-different-hostname/
https://developers.cloudflare.com/rules/url-forwarding/single-redirects/create-api/
Google migration:
https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes
