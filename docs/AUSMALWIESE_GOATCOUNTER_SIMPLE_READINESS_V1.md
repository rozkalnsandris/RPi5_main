# GoatCounter SIMPLE: sanitized /count readiness preflight (#1352)

**Source-only, disconnected evaluator.** This file and
`scripts/ausmalwiese_goatcounter_simple_readiness_v1.py` never contact a host or
Cloudflare, read databases, credentials or protected configuration, send
`/count` hits, or authorize an ingress/app change. `PASS_SOURCE_ONLY`
means only a supplied synthetic/sanitized summary satisfies the expected
contract; it does **not** prove that LIVE is safe.

## Pinned upstream source review (v2.7.0)

Pin `arp242/goatcounter@7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4`,
released 2025-12-15. Direct, read-only GitHub file inspection:

- [`handlers/count.go`](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/handlers/count.go):
  `/count` puts `r.RemoteAddr` in `Hit.RemoteAddr`, and uses that value for
  location lookup if the setting is on. A `CF-Connecting-IP` header by itself
  is **not** proof that `r.RemoteAddr` holds the true client address.
- [`memstore.go`](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/memstore.go):
  `CollectSession` gates session grouping and `m.session(..., UserAgentHeader,
  RemoteAddr)` uses the forwarded/resolved address. Wrong proxy-only IPs
  collapse visitors. The actual middleware/proxy trust boundary is **not
  established** by these two files. Require independent, authorized proof
  including a synthetic spoof-negative test before activating public counts.
- [`cmd/goatcounter/help.go`](https://github.com/arp242/goatcounter/blob/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4/cmd/goatcounter/help.go):
  expected reverse-proxy `X-Forwarded-For`/`X-Real-Ip` and
  `X-Forwarded-Proto: https` are documented, but are *requirements*,
  not LIVE findings. Validate the concrete cloudflared/GoatCounter request
  path, proxy header sanitization and spoof resistance; do not trust
  unverified visitor-supplied headers.
- [v2.7.0 `Collect` constants](https://pkg.go.dev/zgo.at/goatcounter/v2@v2.7.0):
  `Nothing=1`, `Referrer=2`, `UserAgent=4`, `ScreenSize=8`,
  `Location=16`, `LocationRegion=32`, `Language=64`, `Session=128`,
  `Hits=256`. `SiteSettings.Collect` is stored as JSON in the database.
  Historical [#1258](https://github.com/rozkalnsandris/RPi5_main/issues/1258)
  confirms aggregate counts may work without detailed hit storage.
  **Proposed minimal** sessions+referrer mask = `130`. It excludes
  country/location, UA persistence, individual hits and any other flag.
  This is a **review candidate**, not the live setting and not an owner
  privacy approval. If location or another collection category is required,
  stop and seek a distinct privacy/implementation decision.

## Input contract: sanitized summary only

The pure `evaluate(evidence)` accepts an exact, closed schema:

- `schema_version=1`;
- `service`: pinned version, active service, exact
  `127.0.0.1:9194`, private GoatCounter vhost and numeric
  `collect=130` from **separately authorized sanitized readback**;
- `edge`: fully verified remotely managed Tunnel configuration; both
  public-host `/count` routes **absent but safe to add before the single
  app catch-all** (the prior source transformer [#1350](https://github.com/rozkalnsandris/RPi5_main/issues/1350)
  classifies these); Worker routes and Custom Domains independently checked
  for interception, including the observed Worker subrequest behavior;
- `ip`: proven loopback-only peer, pinned Host header, no untrusted
  `CF-Connecting-IP`/`X-Forwarded-For` override, actual pinned-v2.7.0
  `r.RemoteAddr` behavior, negative spoof test and HTTPS scheme;
- `privacy`: **separately** approved exact mask `130`,
  German notice reviewed against actual flow, app switch still `off`.

Any unknown, missing/extra field or unexpected value returns a short
`STOP_*` code, not raw input. Synthetic tests verify fail-closed cases.
The positive test is a **synthetic illustration**, not a real evidence
receipt or an authorization.

## Future bounded operator gates (not part of #1352)

1. Separately owner-authorize a **protected read-only** metadata producer:
   exact non-secret service/loopback/vhost metadata, a trusted sanitized
   `Collect` readback (requires a new specific database/settings permission,
   absent from the previous one-shot authorization), and the version-pinned
   origin/proxy header interpretation. Do not print or commit raw config,
   visitor IPs, database rows or credentials. If that safe producer is not
   available, STOP rather than widen access.
2. Separately authorize least-privilege Cloudflare **read-only**
   `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`,
   `GET /zones/{zone_id}/workers/routes` and Worker Custom Domain/route
   discovery. A trusted, reviewed sanitizer should emit only allowlisted
   statuses. The existing `/api/pageview` writer is NOT suitable for
   `/count`; no writer is introduced here.
3. Independently review and approve the German Datenschutzerklärung (see
   `coloring-pages` Draft PR #158) and exact `Collect` privacy mode.
   Only with all gates and fresh LIVE evidence may the owner authorize a
   **separate one-shot** Cloudflare configuration mutation. App enable,
   publication and any persisted site-settings update need their own
   separately reviewed authorization. NO retry/rollback/cleanup implied.

Official Cloudflare references:
- [Tunnel configuration GET](https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/methods/get/)
- [Worker routes GET](https://developers.cloudflare.com/api/resources/workers/subresources/routes/methods/list/)
- [Worker routes](https://developers.cloudflare.com/workers/configuration/routing/routes/)
- [Worker Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/)
- [Visitor headers](https://developers.cloudflare.com/fundamentals/reference/http-headers/)

Verification: `python3 tests/test-ausmalwiese-goatcounter-simple-readiness-v1.py`.
No LIVE/Cloudflare/app mutation, no protected access, no public hit, no merge.
