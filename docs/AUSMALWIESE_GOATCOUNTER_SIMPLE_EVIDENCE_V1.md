# GoatCounter SIMPLE — trusted injected evidence producer (#1354)

**SOURCE ONLY, NO LIVE.** This outcome reuses the existing
`scripts/ausmalwiese_goatcounter_simple_readiness_v1.py` schema/evaluator
(#1352) and `scripts/ausmalwiese_goatcounter_simple_route_v1.py` pure
transformer (#1350). No API calls, credentials, database, shell commands,
listeners, public requests, file writes or CLI in the new module.
All test evidence is **synthetic**, never observed LIVE readiness.

## Why this is fail-closed

Call `produce(service=..., tunnel=..., worker_routes=..., worker_domains=...,
ip=..., privacy=...)` **only from an independently reviewed and separately
owner-authorized trusted reader** in a future scope. It returns
`(STOP_*, None)` on unknown, incomplete, conflicting or untrusted metadata.
Only a positive synthetic fixture yields `(PASS_SOURCE_ONLY, summary)`;
the summary is hardcoded from validated constants, never copies raw private
input strings, IDs, URLs, headers, database rows, or credentials.

The `source`, `complete`, `owned_hosts_verified` and IP proof status fields
are **assertions supplied by the future trusted reader**, not cryptographic
proofs or authority created by this module. Feeding arbitrary user-authored
JSON with forged status fields would invalidate all security conclusions.
Do not expose this as a public endpoint, CLI consuming arbitrary files, or
as an automated LIVE gate without an independent provenance and permission
boundary. **A source PASS never authorizes LIVE collection or Tunnel mutation.**

## Provenance and minimal input boundaries

1. `service`: narrow allowlisted, authorized nonsecret host metadata:
   exactly active pinned `v2.7.0`, private site Host,
   `127.0.0.1:9194`. **Current `SiteSettings.Collect` is UNKNOWN**;
   reading/attesting the numeric value needs separate exact owner authority
   for a trusted *sanitized* protected settings reader. Proposed only:
   `CollectReferrer=2 | CollectSession=128` -> `130`, **not approved**.
   Any other flags, including persistent per-hit storage, fail closed.
2. `tunnel`: trusted sanitized outer identity (exact `rpi5-tunnel`, remote
   `config_src=cloudflare`, integer version, independently verified approved
   hostname ownership), plus a **transient injected in-memory** config.
   Existing `prepare(config)` rejects global origin inheritance, wildcard
   ambiguity, conflicting path rules, unsafe fallback and partial state;
   `absent=True` is required because `/count` has not been authorized.
   Neither the copied proposed configuration nor the raw ingress is returned
   or printed. The reviewed legacy `/api/pageview -> :9193` operator
   (`scripts/ausmalwiese_goatcounter_tunnel_v1.py`) already has bounded
   `GET` and a different **PUT** contract. **Do not reuse its apply/PUT
   for `/count`.** No credentials/client are added here.
3. `worker_routes`: injected normalized `pattern` and `script` fields
   only, with separately proven complete zone pagination. Any pattern
   matching either public hostname `/count`, including bare `*`,
   a broad host route, or a route exclusion, is rejected. Unknown pattern
   grammar/upper-case routes also STOP; results here are conservative and
   **not a general Cloudflare route engine**. Future trusted adapter must
   confirm complete Worker subrequest/route precedence separately.
4. `worker_domains`: injected normalized canonical hostnames only,
   independently complete; exact `ausmalwiese.de` or
   `www.ausmalwiese.de` is rejected, as is unknown/ambiguous syntax.
5. `ip`: **independently authorized negative spoof test attestation**
   for the exact Go v2.7.0 `r.RemoteAddr`, trusted loopback-only peer,
   overwritten untrusted forwarded headers, pinned private Host,
   HTTPS scheme and non-proxy visitor grouping. A mere
   `CF-Connecting-IP` / `X-Forwarded-For` presence does **not** count.
   No raw visitor address or header is consumed/stored by the producer.
   The test must be done via a separately approved, synthetic bounded
   read-only proof; **not** by sending public count hits in this issue.
6. `privacy`: independent exact owner-approved processing scope, German
   Datenschutzerklärung review, collection mask `130`, and frontend
   still OFF. The existing `coloring-pages` legal PR #158 remained Draft
   when this issue was prepared. No approval is inferred.

## Future gates — not part of #1354

- **RPi5/site read-only:** exact host, listener, vhost/version and
  separately authorized sanitized protected `Collect` readback.
- **Cloudflare read-only:** use
  `GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`
  (`Cloudflare Tunnel Read`) and
  `GET /zones/{zone_id}/workers/routes` (`Workers Routes Read`),
  plus independently read Worker Custom Domains. All raw Cloudflare
  responses must remain in a separately authorized trusted reader.
- **Trust-chain synthetic gate:** reviewed request processing proving
  `r.RemoteAddr` is a real nonspoofed visitor (not loopback proxy),
  authoritative Host, HTTPS and rejected forged headers. Cloudflare
  documents that same-zone Worker `CF-Connecting-IP` can follow mutable
  `x-real-ip`, so zone Worker presence is not adequate evidence.
- **Privacy decision:** legal notice and exact data flags approved before
  collection; **never** silently change site settings or frontend switch.
- **Activation:** separate exact owner Cloudflare/host/app decisions after
  actual evidence, no retries/rollback/cleanup from a source PR.

Reference documentation:
- https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/configurations/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/routes/methods/list/
- https://developers.cloudflare.com/fundamentals/reference/http-headers/
- https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
- https://www.goatcounter.com/help/sessions
- Pinned v2.7.0 source: https://github.com/arp242/goatcounter/tree/7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4

Test (offline): `python3 tests/test-ausmalwiese-goatcounter-simple-evidence-v1.py`.
