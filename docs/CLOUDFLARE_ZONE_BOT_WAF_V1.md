# `rozkalns.net` named AI crawler WAF — source-only v1

## Decision and boundary

Owner requested bot protection for the **entire `rozkalns.net` zone**, including the public CV apex and `coloring.rozkalns.net`, while preserving ordinary human access and search engine indexing. This is a source-only rule/operator/test proposal. **No Cloudflare change, deployment, token provisioning, root install, or merge is included.** This source proposal does not claim to protect private data: use Cloudflare Access, application authentication, API authorization, and server-side access control on sensitive services.

Cloudflare `Wrangler` handles Workers; the correct API for WAF rules is the **Rulesets API**. The only source-level action proposed is one `block` custom WAF rule in the existing/new **zone** `http_request_firewall_custom` phase entrypoint. The host expression covers precisely `rozkalns.net` and `.rozkalns.net` subdomains. It does not touch DNS, tunnels, Access, existing rules or workers. All paths (including public CV and Coloring Pages media) are included **only when the named bot User-Agent matches**.

`cf.bot_management.score` is Enterprise-only; this proposal uses Free-plan-compatible `http.user_agent`, `lower()`, `ends_with()` with an enumerated set of known AI crawlers/agents. Googlebot/Bingbot and search-purpose bots such as OAI-SearchBot, Claude-SearchBot, and PerplexityBot are not targeted. No blanket managed challenge, zone-wide Bot Fight Mode, search-engine `skip`, IP-based bypass, rate-limit slot consumption or rewriting of existing WAF rules. This preserves existing M2M/Webhook traffic unless its User-Agent happens to match one of the forbidden agents; that edge case must be checked before any LIVE activation.

## Limits and why it is not a privacy boundary

**User-Agent is client-controlled and spoofable.** A scraper can impersonate Chrome, and a human can save any publicly downloadable PNG or CV. This source rule does not identify all malicious bots, provide rate limiting or prevent mass fetching with forged User-Agents. Prefer Cloudflare managed AI bot policies (`Training=Block`, `Agent=Block`, `Search=Allow`) where supported, as a separately owner-gated product-setting action. The managed setting is not the WAF Rulesets API and cannot be pretended to be activated by this PR. For public PNG anti-harvesting, separately review per-path rate limiting based on observed traffic, plan limits and verified SEO/printing behavior. Private content should not be public in the first place.

Historical `RPi5_main#206` records an actual GitHub-runner outage caused by Cloudflare Free zone-wide Bot Fight Mode on `control.rozkalns.net`, and the owner's decision to retire that global heuristic. We do **not** turn it back on, or apply a blanket challenge that would break Cloudflare Access service tokens, webhooks, Home Assistant clients, or other machine integrations. The existing `ops/contracts/cloudflare-hostname-policy.yaml` controls PUBLIC/ADMIN/FAMILY_PRIVATE trust classes, unchanged by this work.

## Source operator

- Script: `scripts/cloudflare_zone_bot_waf.py`.
- Offline preview (no network/secret): `python3 scripts/cloudflare_zone_bot_waf.py --plan`.
- Proposed future installed path: `/usr/local/sbin/rpi5-cloudflare-zone-bot-waf`, `root:root 0500`.
- Proposed future exact-release metadata: `/usr/local/libexec/rpi5-cloudflare-zone-bot-waf/release.json`, `root:root 0400`, fields `source_sha` and `operator_sha256`.
- **Separate dedicated** root-owned `0600` credential source: `/etc/rpi5-secrets/cloudflare/zone-waf-writer.json`, containing only `zone_id`, `zone_name=rozkalns.net`, and `api_token`. Credential must have zone-scoped `Zone WAF: Edit`; never reuse Access/Tunnel credentials. No secret value is committed, displayed or read in this source-only work.
- Future read-only preflight (requires installed exact-release, root and dedicated credential): `rpi5-cloudflare-zone-bot-waf --preflight --expected-main <exact-40-char-sha>`.
- Future **separately** authorized, root-installed one-time apply: `rpi5-cloudflare-zone-bot-waf --apply --expected-main <exact-40-char-sha> --confirm CREATE-ROZKALNS-BOT-WAF-RULE`.

No installation/provisioning helper is included in this PR; therefore merging it cannot enable the executable privileged path. The operator rejects executing a LIVE preflight/apply from a checkout. A later exact owner-gated install/provisioning path requires its own reviewed source contract and authorization.

## Fail-closed Cloudflare preflight and one-write boundary

1. Verify installed exact source identity/hash and dedicated root-only secret file metadata (no symlink); check actual `GET /zones/{zone_id}` returns the expected zone name.
2. `GET /zones/{zone_id}/rulesets/phases/http_request_firewall_custom/entrypoint`: only `200` (validate kind/phase/rules) or `404` (absent entrypoint) is an allowed branch. Reject existing matching `ref`/expression or invalid metadata. Preserve existing rule count and order.
3. If entrypoint exists, exactly one `POST /zones/{zone_id}/rulesets/{entrypoint_id}/rules`; if absent, exactly one `POST /zones/{zone_id}/rulesets` creates a zone-phase entrypoint with the single target rule. **No PUT, PATCH, DELETE, retry or fallback.** If no Free custom rule capacity, reject the provider error; do not replace an unrelated rule.
4. `GET` the entrypoint after the POST. Verify exactly one new target rule (`ref`, expression, block/enabled) was added and all prior rules are semantically unchanged and in order. Any drift or API ambiguity after mutation => STOP, minimum sanitized evidence only, new owner decision.
5. Prior to owner authorization for LIVE: verify real existing rule inventory/quota, provider expression acceptance, other services' webhooks/Access flows, and public Googlebot/Bingbot/Coloring Pages/CV behavior. Define separate rollback authority if needed; it is **not** contained in the create authorization.

The operator is no substitute for server-side access control; its goal is only to block *identifiable* non-beneficial crawlers at the edge.

Official documentation:
- https://developers.cloudflare.com/waf/custom-rules/create-api/
- https://developers.cloudflare.com/ruleset-engine/rulesets-api/add-rule/
- https://developers.cloudflare.com/ruleset-engine/rules-language/functions/
- https://developers.cloudflare.com/bots/additional-configurations/block-ai-bots/
- https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/
