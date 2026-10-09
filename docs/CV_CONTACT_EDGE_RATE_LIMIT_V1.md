# CV contact edge rate limiting v1 — source-only (#946)

**Status: source-only proposal / no LIVE, not activated.** Companion issue: `rozkalnsandris/rozkalns-cv#522`. This is a Cloudflare edge policy proposal owned by `RPi5_main`, not an instruction to modify a Cloudflare account. Machine-readable contract: [`ops/contracts/cv-contact-edge-rate-limit-v1.json`](../ops/contracts/cv-contact-edge-rate-limit-v1.json).

## Provenance and trust boundary

The 2026-10-09 scoped read-only RPi5 observation showed the CV Docker bridge gateway differed from the previously hard-coded trusted peer in Nginx. Changing to the observed gateway is **not** a security fix: a gateway carries both trusted tunnel traffic and possible local loopback clients. Neither `CF-Connecting-IP` nor `X-Forwarded-For` nor `X-Real-IP` sent to that gateway authenticates the source of a request; local clients can spoof headers.

The CV consumer source correction stops trusting those headers, strips forwarded client-IP claims before Gunicorn, and keeps a **single global Nginx** `60r/m`, `burst=15` in-memory contact backstop keyed by `$server_name` on exact `/api/contact-reveal`. It cannot deliver independent per-visitor client-IP quotas behind Docker NAT. Direct localhost requests can reach this loopback origin but remain subject to Nginx global limit and server-side Turnstile. Siteverify omits the optional remoteip parameter in public mode rather than falsely claiming gateway IP is the visitor.

The only proposed authoritative **per-client IP** quota runs at Cloudflare edge with native `ip.src`, never a forwarded header. Cloudflare's counter characteristics include mandatory `cf.colo.id` and `ip.src`; counters are **per-colo**, not exact worldwide shared counters, and can have enforcement propagation delays. This complements, rather than replaces, Turnstile and the independent origin backstop.

## Proposed rule — NOT applied

| Field | Source-only value |
|---|---|
| Phase | `http_ratelimit` |
| Expression | `(http.host eq "rozkalns.net" and http.request.uri.path eq "/api/contact-reveal")` |
| Characteristics | `cf.colo.id`, `ip.src` |
| Threshold | 6 requests per 60 seconds per IP per Cloudflare colo |
| Action | `block`, mitigation 60 seconds |
| Enabled in proposal | `false` |

The exact hostname prevents unrelated `*.rozkalns.net` applications from being matched. Rate limiting the exact endpoint path also blocks GET attempts; there is intentionally no narrower POST-only assumption. Cloudflare's plan matrix matters: `http.host` is not listed for the Free plan, so **do not silently downgrade** to path-only rules that may affect unrelated hosts. A zone/plan capability failure means **BLOCKED** pending a separate owner decision.

## Owner-gated rollout eligibility

Before any separate LIVE change, the operator must obtain fresh, appropriately authorized **sanitized read-only** evidence for all of the following, and stop on uncertainty:

1. The Cloudflare zone supports this exact hostname expression, `ip.src` characteristic, limit, phase and rule action; preexisting `http_ratelimit` rules/order do not conflict. No credentials, zone/account IDs or protected ruleset payloads in public GitHub.
2. A separately authorized Cloudflare LIVE operation has installed/enabled precisely the reviewed rule and a new read-only check proves **exact** rule identity and active status; no wider wildcard, other hostname or other rule is changed.
3. The remotely managed `cloudflared` public hostname continues to forward to the CV loopback-only `127.0.0.1:8088` origin. This ingress class is documented source policy, **not live evidence**. No direct LAN/public container port, backend Gunicorn exposure, or alternate path may bypass the Nginx global quota or Turnstile.
4. The CV image at the exact final consumer SHA has a verified Nginx syntax/endpoint/headers contract and retains private contact disclosure only after Siteverify success. The new RPi5 installed executor/timer and digest/receipt also require their own separate owner-gated readiness decisions.
5. The authorized edge test confirms client separation and spoof-resistance: two visitors with distinct public IPs, a repeated client crossing limit, forged `CF-Connecting-IP` and `X-Forwarded-For` on an origin-only local probe (no personal response bodies), and fail-closed responses. Do not publish real IPs, request bodies, secrets or raw configs. The origin fallback should still bound traffic even if edge protection is absent.
6. `production_ready` and similar policy assertions remain **false** in source until fresh evidence and a separate exact owner LIVE authority. An issue/PR/merge and this JSON proposal alone cannot authorize or execute Cloudflare or host mutations.

## Official references

- https://developers.cloudflare.com/waf/rate-limiting-rules/
- https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/
- https://developers.cloudflare.com/waf/rate-limiting-rules/request-rate/
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://nginx.org/en/docs/http/ngx_http_realip_module.html
- https://nginx.org/en/docs/http/ngx_http_limit_req_module.html

**No LIVE, no merge, no secret/credential change, no runtime change, no production database operation.**
