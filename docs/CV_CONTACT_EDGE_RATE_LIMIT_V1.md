# CV contact edge protection v1 — Free-plan source decision (#946, #948)

**Selected: source-only baseline; no LIVE; not production-verified.** RPi5_main issue #948 supersedes the Free-plan deployment interpretation of the merged #946 proposal. Consumer issue `rozkalnsandris/rozkalns-cv#522` remains a separate OPEN production/installed-image reconciliation gate. Machine contract: [`ops/contracts/cv-contact-edge-rate-limit-v1.json`](../ops/contracts/cv-contact-edge-rate-limit-v1.json).

## Provenance and IP trust boundary

Scoped read-only RPi5 evidence showed that the Docker bridge gateway was not the address previously assumed by CV Nginx. Replacing the address with the current gateway is **not** secure: untrusted loopback/host callers could forge `CF-Connecting-IP`, `X-Forwarded-For`, and `X-Real-IP` headers. Neither a Docker gateway nor raw origin HTTP headers authenticates visitor IP. The CV consumer source design instead strips untrusted forwarded client identity and uses an independent exact-path Nginx **global** `60r/m`, `burst=15` backstop keyed on `$server_name`. It does **not** enforce per-client quotas behind NAT. Public Turnstile Siteverify must remain server-side and fail-closed; optional remoteip is omitted rather than treating the gateway as a verified visitor IP.

True WAF rate limiting at the Cloudflare edge uses native `ip.src`, not an origin-provided client-IP header. Cloudflare WAF counters are per-colo and not exact global totals. The historical host-scoped `http_ratelimit` proposal remains disabled and is retained for provenance, **not** as a Free-plan deploy candidate.

## Selected Free-plan baseline — source policy only

1. Keep public Turnstile and fail-closed Siteverify for `/api/contact-reveal`; retain Nginx exact-location **global** `60r/m`, `burst=15` origin cap. These are complementary controls, not an independent IP-specific numeric quota. Deployment/effective runtime state is not established by this source decision.
2. **Preserve the existing Cloudflare WAF rate-limit rule unchanged.** Do not create, replace, reorder, disable, delete, repurpose, or silently consume its slot. No existing rule identifiers or private rule payloads are stored here.
3. Cloudflare WAF Free documents **one** rate-limiting rule, a **10-second** period and a rule-expression field set limited to Path and Verified Bot. The historical `http_ratelimit` proposal's exact `http.host` predicate and **6 requests / 60 seconds** therefore are **not Free eligible**, independently of the occupied rule slot. Do not downgrade the predicate to path-only: it could match unrelated hostnames.

The source proposal originally defined `http.host eq "rozkalns.net" and http.request.uri.path eq "/api/contact-reveal"` with `cf.colo.id` and `ip.src`, block after 6/60, 60-second mitigation and `enabled=false`. Those settings remain in the machine-readable historical proposal solely to make the supersession auditable.

## Optional enhancements — both deferred and disabled

**Free WAF Custom Rule + Managed Challenge:** The feature is generally available to Free zones but it is **not** numeric per-IP rate limiting. A challenge on a fetch/JSON contact API may replace the expected response with interactive HTML, prevent legitimate requests from completing, or collide with Turnstile. Do not enable without route and client behavior proof, available custom-rule capacity, verified expression precision and separate owner LIVE authority. It must never alter the existing rate-limit rule.

**Cloudflare Worker + Rate Limiting API:** A *candidate*, not active, not proven compatible with the current Free account. A Worker rate-limit binding can express **6 calls in 60 seconds** with a per-request key. Its counts are cached asynchronously **per Cloudflare location** (per-colo), not globally exact; different legitimate visitors can also share public IPs. An IP-derived key is therefore a pragmatic abuse-control tradeoff, not an authenticated user identity or billing-grade meter. Do not use origin-trusted `CF-Connecting-IP`/forwarded headers. A future implementation must obtain and validate the incoming Cloudflare edge client-IP provenance under the exact Worker route, reject absent/ambiguous provenance instead of bypassing, and guard same-zone/Worker-subrequest spoofing.

Route-specific Worker source and routing remain out of scope for this delivery. Before any separate implementation or LIVE activation, independently prove **all** of:

- Workers Free runtime and Rate Limiting binding are actually available for the target account, with remaining capacity and a sustainable **100,000 requests/day shared Workers Free account budget**.
- An exact apex `rozkalns.net` / `/api/contact-reveal` route matches intended methods only, preserves other sites and endpoints, has no existing Worker route precedence/conflicts, and forwards to the same intended application and loopback-only Tunnel origin. A Workers **Route cannot be a same-zone fetch target**; inspect any Custom Domain/other-Worker topology and ensure no recursive Worker/subrequest loop or bypass.
- Explicit Worker route **fail-closed** behavior is selected for exceeding the daily budget: Cloudflare error `1027`, not fail-open bypass. Model user-visible availability consequences; no claim that 1027 is a desirable contact UX.
- Request method, path, query, body, Siteverify token and response status/headers/body remain intact through the Worker and Tunnel. Do not emit IPs, contact values, Turnstile tokens, request bodies or protected headers to public source, logs, analytics or evidence.
- Synthetic distinct-client and repeated-client behavior, Cloudflare-managed incoming IP provenance, spoofed headers, exact-route noninterference and **429** enforcement are verified without logging visitor IP values. Siteverify fail-closed and the independent origin global Nginx backstop still work if the edge layer is absent or rejects traffic.

No Worker script, binding, route or Cloudflare API writer is added by #948.

## Owner gates and evidence classification

- **SOURCE:** this decision and its tests only; `source_ready_only=true` never implies `production_ready`.
- **ACCOUNT/EDGE READ-ONLY:** verify plan, any rule and Worker route compatibility, ingress precedence, Tunnel origin routing `127.0.0.1:8088`, loopback-only exposure and no bypass. Record sanitized conclusions only, not IDs, secrets, real IPs, protected rule payloads or configs.
- **APPLICATION/RUNTIME READ-ONLY:** independently establish exact final CV consumer SHA, installed image digest and deploy receipt/executor/timer status. `rozkalns-cv#522` remains open until its separate production mismatch is resolved with evidence. GitHub source/GHCR success does not prove installed runtime.
- **OWNER LIVE:** any Cloudflare rules, Worker route/binding/script, DNS/Tunnel, host image, deploy, service or production configuration mutation needs its own exact bounded owner authorization; merge does not authorize LIVE. Source tests must not claim deployment, Free account eligibility, active edge quotas or production remediation.

## Official references

- https://developers.cloudflare.com/waf/rate-limiting-rules/
- https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/
- https://developers.cloudflare.com/waf/custom-rules/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/configuration/routing/routes/
- https://developers.cloudflare.com/fundamentals/reference/http-headers/
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://nginx.org/en/docs/http/ngx_http_limit_req_module.html

**No LIVE, no merge, no host/Cloudflare/production/permissions mutation, and no new personal-data publication.**
