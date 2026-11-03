# GoatCounter SIMPLE — exact /count ingress source (#1350)

Purpose: reuse the existing private self-hosted GoatCounter v2.7.0 for pageviews, estimated sessions and referrers. **No public tracking, Cloudflare change, backend setting change or IP logging is authorized or executed by this source change.**

## One path-only route, no new service

Cloudflare's remotely managed rpi5 Tunnel should eventually have one new rule for **each** hostname, inserted immediately before that hostname's existing public-site fallback:

```json
{"hostname":"ausmalwiese.de","path":"^/count$","service":"http://127.0.0.1:9194","originRequest":{"httpHostHeader":"goatcounter.ausmalwiese.invalid"}}
```

Repeat with `hostname` set to `www.ausmalwiese.de`. This is **only a proposed configuration**, not an applied Cloudflare configuration. Tunnel path matching does not strip or rewrite `/count`. Do not add a public GoatCounter hostname, wildcard, `/api/*`, `/status`, `/admin`, root, or direct service port exposure.

`scripts/ausmalwiese_goatcounter_simple_route_v1.py` offers only `prepare(config)` and `entry(host)`: a pure offline transformer, no Cloudflare API client, credentials, network, privileged CLI, or file reads. It rejects global inherited origin settings, overlapping wildcard hosts, alternate target-host paths, duplicate/unsafe fallbacks, partial installation and mismatched existing routes. Existing rules remain in their prior order, and the exact already-applied state is an idempotent no-op. Synthetic tests are wired to `make test`. The historical `/api/pageview` operator is **not** a fallback for this new plan.

## Critical separate checks before public collection

1. Fresh **separately authorized sanitized** RPi5/Cloudflare read-only preflight: the actual v2.7.0 service/site `Host` identity and collection setting; `127.0.0.1:9194` listener/health; exact remotely managed tunnel rule order, hostname ownership and Worker route interception. Historical host evidence confirmed an active loopback service on 2026-11-03, not current Cloudflare/public readiness. Never read or output raw protected config, database, visitor data or credentials without a separate exact owner gate.
2. Validate **real visitor IP and trust chain**. GoatCounter may use client IP transiently for estimated sessions and country; ensure trusted `CF-Connecting-IP` / `X-Forwarded-For` behavior with the actual cloudflared → GoatCounter v2.7.0 connection. Reject header spoofing and proxy-IP-only session grouping. Confirm `X-Forwarded-Proto`, browser count.js method/query handling, cache and `/count` path normalization, with approved synthetic probes; do not send real public counts under this source task.
3. Confirm the v2.7.0 site's collection setting is enabled by its authorized owner **before** any public ingestion. Historical private-install receipts recorded `CollectNothing=1`, which is a blocker until separately verified/changed under a specific database/runtime authority. Do not infer a current value from dated source evidence.
4. Reconcile actual data flow and the German Datenschutzerklärung via `coloring-pages` Draft PR #158. Raw visitor IP persistence is **not** part of stock SIMPLE and is not enabled here.
5. Only after exact owner approval: perform one bounded Cloudflare Tunnel configuration mutation under a verified single-writer window. The existing reviewed Cloudflare writer has a different hard-coded `/api/pageview → 9193` contract; do **not** call it for `/count` or patch a protected live config ad hoc. Future operator may reuse reviewed credential/HTTP machinery with the pure `prepare` function after a separate source/security review. STOP on drift/error, no retry, rollback or cleanup.
6. Separately authorize and review the exact `coloring-pages` app change from `data-goatcounter-simple="off"` to `enabled` on public pages after route/legal clearance. Ensure protected reporting remains private and site browsing, catalog, Like and Print are unaffected. A source merge here does not flip that switch.

## Source proof

`python3 tests/test-ausmalwiese-goatcounter-simple-route-v1.py` runs fully offline on synthetic configuration. It verifies exact matching, preserved routes, host/header isolation, no wildcard/admin exposure through this new rule, conflict and partial-state STOP, and idempotence.

Official references: [GoatCounter JavaScript API](https://www.goatcounter.com/help/js), [GoatCounter sessions](https://www.goatcounter.com/help/sessions), [Cloudflare Tunnel path matching](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/), [Cloudflare visitor-IP restoration](https://developers.cloudflare.com/support/troubleshooting/restoring-visitor-ips/restoring-original-visitor-ips/).
