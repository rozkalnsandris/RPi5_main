# ausmalwiese.de — Google Search-only crawler-control runbook (source-only)

Scope: [RPi5_main #988](https://github.com/rozkalnsandris/RPi5_main/issues/988); downstream [coloring-pages #184](https://github.com/rozkalnsandris/coloring-pages/issues/184). The policy is frozen in `ops/contracts/ausmalwiese-crawler-policy-v1.json`. **Nothing in this document authorizes Cloudflare LIVE changes, credentials, root access, a merge or a deploy.**

## Decision

Use **Cloudflare Free > AI Crawl Control > Security > Crawlers**, not a new host operator or blanket Bot Fight Mode. In the current interface, each crawler's `Block Crawler` control changes its enforcement. Cloudflare documents that **all AI Crawl Control Block choices share one WAF custom rule**, rather than consuming one WAF rule per bot.

Keep **Googlebot** permitted; check that **Googlebot-Image** remains indexable even though it did *not* appear as a separate AI Crawl Control row. Preserve Search Console `Google-InspectionTool` fetches for diagnostics. Deliberately block Bingbot, AI search bots, AI training bots, assistant agents and other **identifiable non-Google crawlers**, including `Claude-SearchBot`. Google-Extended is for Google's non-Search use; it is *not* an exemption just because its name begins with Google.

Do **not** create a broad `cf.client.bot` allow/skip rule: Verified Bots includes many non-Google crawlers. Do not treat `http.user_agent contains "Googlebot"` alone as proof of Google ownership; User-Agent can be spoofed. Do not block all verified bots, because verified monitoring/health clients could break. Do not enable Bot Fight Mode: historical [#206](https://github.com/rozkalnsandris/RPi5_main/issues/206) records legitimate machine traffic being challenged.

**Important limitation:** AI Crawl Control on Free identifies bots primarily from self-declared User-Agent strings. It cannot reliably identify scrapers impersonating browsers. "Google only" applies to **recognizable crawler traffic**, not a provable deny-by-default filter for every automated client. Search indexing outside Google and third-party link previews may degrade by owner choice.

## Observed baseline (2026-10-12; historical, NOT reusable LIVE preflight)

| Surface | Read-only observation |
| --- | --- |
| Cloudflare zone | `ausmalwiese.de` (apex and `www`) — separate from `rozkalns.net` |
| Security > Security rules | 0/5 custom WAF rules; 0/1 rate-limiting rules; 0 managed rules |
| Security > Settings | Bot Fight Mode **OFF**; Super Bot Fight Mode not shown on Free |
| AI > Security > Crawlers | Controls visible; `Block Crawler` **OFF** for Claude-SearchBot, ClaudeBot, Googlebot, Bingbot, OAI-SearchBot; other displayed AI crawlers also OFF |
| Googlebot-Image | Not separately listed — effective Search image crawling remains unverified |
| Security > Settings > Configure AI bot policies | Summary displayed "4 configurations"; their effective Search/Agent/Training actions were not established |
| Existing managed robots.txt | Cloudflare prepends managed directives to origin; origin's `robots.txt` is shared with `coloring.rozkalns.net` |

This read was performed via owner-provided TinyFish Cloudflare browser access, read-only. The existing RPi5 Cloudflare zone-bot-WAF operator is **pinned to rozkalns.net** and must not be pointed at this new zone.

## Required read-only preflight BEFORE seeking LIVE authorization

1. Open Cloudflare and select the exact **`ausmalwiese.de` zone**. Confirm Free plan, apex/`www` routing and the operator's current session rights. Do not copy account IDs, credentials or screenshots of sensitive configuration into issues.
2. Read **Security > Security rules** (all custom rules, actions, ordering, full capacity) and **Security > Settings** (Bot Fight Mode, managed robots, "Configure AI bot policies": Search / Agent / Training). Check for drift from the historical 0/5 baseline; if any new or overlapping rules exist, **STOP and redesign**, not override.
3. Read **AI Crawl Control > Security > Crawlers** and enumerate every currently displayed crawler **name, category, existing Block state**. Explicitly capture Googlebot, Claude-SearchBot, ClaudeBot, Bingbot, OAI-SearchBot and any other non-Google row. Check whether Googlebot-Image is recognized separately, and ensure Google's image/user-triggered Search requests would not be blocked. Confirm the authoritative Cloudflare help labels before determining the final mutations.
4. Freeze the **exact final list of off→on `Block Crawler` switches**, the number/order of intended UI writes, affected one shared WAF rule, preserved Google rows and post-change checks. **No unspecified "all bots" mutation**; new/unrecognized names or impossible Google/monitor exceptions require a new review.
5. Confirm that managed `robots.txt` contains no Googlebot or Googlebot-Image `Disallow: /`; re-evaluate Content-Signals/robots merging. A `Disallow` expresses preference, not an enforced edge block. Avoid modifying source `coloring-pages/robots.txt`, shared with another live hostname.

### Named inventory to prioritize (not proof of every live row)

- **Always block if displayed and currently allowed:** `Claude-SearchBot`, `ClaudeBot`, `Bingbot`, `OAI-SearchBot`, `GPTBot`, `ChatGPT-User`, `PerplexityBot`, `Applebot`, `Amazonbot`, `archive.org_bot`, `Baidu`, `FacebookBot`.
- **Also block:** any *other* displayed non-Google crawler, including Google-Extended/GoogleOther when present and unambiguously unrelated to Google Search. Do **not** infer availability from this list; the exact row names and settings must be confirmed by a fresh UI inventory.
- **Preserve:** Googlebot (including its normal Search desktop/smartphone crawling) and Googlebot-Image. Preserve Google-InspectionTool access for Search Console diagnostic requests. Where Google image/inspection traffic is not visible in the AI table, it is **not** automatically covered by a speculative WAF rule.
- **Do not silently touch:** custom WAF settings, rate limits, zone-wide generic bot controls, Traffic/DNS/Tunnel/Access settings, or any `rozkalns.net` zone.

## Proposed bounded LIVE path — NOT AUTHORIZED

After exact preflight, obtain **one separate owner LIVE authorization** naming `ausmalwiese.de`, observed WAF/AI baseline, *enumerated* crawler names and current state, fixed per-crawler change order, maximum UI writes and a no-retry/no-rollback policy. An authorization with an open-ended crawler set is not sufficient.

The approved executor may make only those named `Block Crawler` changes through the already-established Cloudflare browser session, in the frozen order. Before the *first* click, confirm exact zone and no drift. **The first change consumes the authorization**. On any timeout, unexpected toggle state, Cloudflare WAF rule collision, changed zone, Google false positive, or uncertain save, stop; collect minimum non-secret GET/UI-only evidence. No automatic retry, rollback or cleanup. Any follow-up change needs new owner authority.

AI Crawl Control Block creates/updates **one shared zone WAF custom rule**. It takes precedence over Bot Fight Mode and Pay Per Crawl; avoid stacking another overlapping custom WAF rule. With the historical 0/5 free quota, a single shared rule would occupy **1/5** if current capacity remains unchanged. Confirm exact post-change count and that no pre-existing WAF rule was modified. Never click `Save`, `Block`, or a toggle as a read-only preflight.

## Read-only verification and rejection criteria

| Case | Expected after separately authorized LIVE |
| --- | --- |
| Claude-SearchBot and each specifically frozen non-Google crawler | Block control ON and corresponding security event / blocked response; do not spoof a User-Agent and claim bot identity verified |
| Googlebot + Googlebot-Image | No new block; Search Console live URL test and image fetch/index visibility where available; independently validate genuine Google crawler provenance |
| Chrome Android + desktop; privacy browsers | Homepage/detail load; no CAPTCHA/challenge/403 caused by the change |
| A4 print and PNG download | Print view and original-resolution PNG accessible; do not change media bytes |
| `/robots.txt`, `/sitemap.xml`, `/detail.html?id=...` | Public GET succeeds for normal users and verified Google crawlers |
| `/api/stats/*`, `/q`, existing monitored health clients | Baseline behavior preserved (GET diagnostics only; do not generate artificial likes, prints or QR counts) |
| Cloudflare WAF inventory | Only expected AI Crawl Control shared rule changed; zero unrelated changes, no other hostname impact |
| False positives and measurements | Review Cloudflare Security Events and before/after bot-request rates; STOP and request owner decision on legitimate-client block |

Security Events may be sampled; Cloudflare crawler classifications are not by themselves proof of the actual requester. After initial verification, repeat read-only checks as indexing reports catch up. There is **no authorization** here for a testing POST, host config edit, DNS/route change, cleanup or automatic rollback.

## Official references

- [Cloudflare: Manage AI crawlers](https://developers.cloudflare.com/ai-crawl-control/features/manage-ai-crawlers/)
- [Cloudflare: AI Crawl Control with WAF](https://developers.cloudflare.com/ai-crawl-control/configuration/ai-crawl-control-with-waf/)
- [Cloudflare: managed robots.txt](https://developers.cloudflare.com/bots/additional-configurations/managed-robots-txt/)
- [Cloudflare: verified bots](https://developers.cloudflare.com/bots/concepts/bot/verified-bots/)
- [Google: Googlebot](https://developers.google.com/search/docs/crawling-indexing/googlebot)
- [Google: verify genuine Google requests](https://developers.google.com/crawling/docs/crawlers-fetchers/verify-google-requests)
