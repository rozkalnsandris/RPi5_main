# Ausmalwiese #996 — simplified owner cutover

This runbook simplifies the owner-visible cutover flow without weakening the
existing RPi5_main safety boundaries.

## Owner-visible model

Normal FAST-LANE delivery for #996 should converge to only two owner decisions:

1. **MERGE** the final reviewed source PR at an exact HEAD.
2. **COMPOSITE LIVE** for the bounded cutover operation.

Read-only discovery, preflight, post-verify, exact-head checks and public
acceptance checks are technical automation steps. They are not separate owner
gates.

Google Search Console Change of Address remains a separate owner action after
the production cutover is proven complete.

## One COMPOSITE LIVE sequence

A single composite authorization may cover the following tightly coupled,
predeclared stages only when every stage already has a reviewed installed
executor and a fresh exact baseline:

1. **Stats Gate A**
   - internal read-only preflight;
   - execute the exact reviewed D1 migration once, only if the frozen pre-state
     matches;
   - exact post-schema verification.

2. **Stats Worker**
   - internal read-only identity/config/version preflight;
   - activate only the exact reviewed Worker version through the reviewed
     bounded deployment path;
   - verify Stats health, `/q` destination and Instagram attribution marker.

3. **Sitemap**
   - internal writer/quiescence and source-identity preflight;
   - publish only the already-reviewed sitemap candidate;
   - verify new-domain sitemap URLs and public HTTP acceptance.

4. **Legacy 301**
   - internal read-only Redirect Rules inventory/order/hostname preflight;
   - apply only the exact hostname-scoped permanent redirect for
     `coloring.rozkalns.net`, preserving path and query;
   - verify one-hop 301 behavior and that the new site, health endpoints and
     unrelated hosts remain healthy.

The stages are ordered. Later stages must not run before earlier acceptance
checks pass.

## Fail-closed rules

Before the first mutation, any drift, missing executor, missing permission,
unexpected provider state or ambiguous evidence is **STOP before write**.

The first live mutation consumes the composite authorization. After that point,
any error or ambiguity is **STOP** with evidence preserved. No retry, rollback,
cleanup, fallback, alternate provider path, widened target or ad-hoc repair is
implicit.

The composite authorization must bind at minimum:

- exact RPi5_main Git SHA;
- exact host and application checkout identity where relevant;
- exact installed runtime/operator identities;
- exact D1 migration blob and frozen pre-state evidence;
- exact Stats Worker source/version target;
- exact sitemap candidate identity;
- exact legacy hostname redirect target and preservation rules;
- explicit exclusions for unrelated Cloudflare/DNS/WAF/Access, secrets,
  permissions, services and other hosts.

If any required mutation class is not covered by the authorization, that stage
is out of scope and the operation stops before entering it.

## What this document does not authorize

This runbook is source documentation only. It does not merge source, install or
upgrade runtimes, access credentials, mutate D1, deploy Workers, publish a
sitemap, edit Cloudflare rules, change DNS, or perform Search Console actions.

A current exact reviewed implementation and explicit owner authorization are
still required before any LIVE mutation.

## External references

- Cloudflare D1 Wrangler commands:
  https://developers.cloudflare.com/d1/wrangler-commands/
- Cloudflare Workers versions/deployments:
  https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Cloudflare Single Redirects:
  https://developers.cloudflare.com/rules/url-forwarding/single-redirects/
- Google site move with URL changes:
  https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes
