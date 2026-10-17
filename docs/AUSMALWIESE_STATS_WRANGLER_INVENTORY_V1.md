# Ausmalwiese Stats Wrangler normalized inventory collector (#1054)

SOURCE ONLY / NO MERGE / NO LIVE / NO CLOUDFLARE REQUEST.

## Purpose

This outcome supplies the missing trusted normalized inventory shape required by
the one-time takeover planner in issue #1052. It does not authenticate, contact
Cloudflare, install anything on RPi5, or execute Wrangler.

The source consumes only already-received bounded JSON objects from a future,
separately reviewed protected GET-only transport. It emits exactly the
ausmalwiese.stats-wrangler-conflict-inventory.v1 snapshot plus its deterministic
inventory_sha256.

## Frozen target

- Worker: coloring-pages-stats-v1
- Account identity: existing SHA-256 fingerprint only
  3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34
- Wrangler: 4.135.0
- coloring-pages commit:
  180368f3b81abddde3df94637512436ca50c358f
- Worker blob:
  dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4
- config blob:
  3733263a391274f2b6b0f2023c8656565bde8e1a
- pre-takeover baseline version:
  e47f145f-1851-4917-be5c-387f96549539

No raw account ID, credential, secret value or protected runtime configuration is
stored in source, fixtures or output.

## Official provider read model

Cloudflare documents three GET surfaces used by the future transport:

1. /accounts/{account_id}/workers/scripts/{script_name}/versions
   - first version is the latest version;
2. /accounts/{account_id}/workers/scripts/{script_name}/deployments
   - first deployment is the latest deployment actively serving traffic;
3. /accounts/{account_id}/workers/scripts/{script_name}/versions/{version_id}
   - returns exact version metadata, bindings, script metadata and runtime
     compatibility information.

References reviewed 2026-10-17:

- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/list/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/
- https://developers.cloudflare.com/workers/versions-and-deployments/

The source request plan fixes api.cloudflare.com, GET only, page=1,
per_page=2 for the two list calls, one exact version detail call, 64 KiB maximum
response size per call, 10 second timeout, zero redirects and zero retries.
There is no generic URL or arbitrary path interface.

## Fail-closed normalization

Before takeover, the source requires:

- one valid latest full version UUID;
- deterministic first/second version ordering when a second entry is returned;
- one current active deployment;
- exactly one active version at exactly 100 percent;
- latest version equals active version and both equal the frozen baseline;
- exact version detail ID equals latest;
- list/detail provider source agrees;
- provider source api plus script last_deployed_from api maps to script_api;
- provider source wrangler plus script last_deployed_from wrangler maps to
  wrangler_versions_upload;
- every other or ambiguous source is rejected.

The exact binding set must be:

- DB, type d1, exact database ID;
- RATE_LIMITER, type ratelimit, exact namespace and 100 / 60s policy;
- CF_ANALYTICS_API_TOKEN and VISITOR_HMAC_KEY as secret_text names only;
- CF_ANALYTICS_HOST, CF_ZONE_TAG and PUBLIC_ORIGIN as plain_text.

Secret descriptors are accepted only when they contain name and type. Any secret
text field is rejected. Plain-text values are used only in memory to compute
SHA-256 fingerprints and are never emitted.

The D1 database name in the normalized snapshot comes from the frozen reviewed
application config; provider detail independently proves the exact database ID.

## Settings fingerprint

compatibility_date is normalized to YYYY-MM-DD, including Cloudflare's documented
midnight-UTC timestamp representation. compatibility_flags are sorted and
bounded.

settings_sha256 covers only an allowlisted remainder:

- script handlers and named handlers;
- script runtime exports, limits, migration tag and usage model.

It intentionally excludes source classification and script etag so that source
classification can change from api to wrangler during takeover without silently
changing the preservation gate.

## Pre and post upload use

The collector supports the two evidence stages already defined by #1052:

- before: latest=active=frozen baseline and source_class=script_api;
- after_upload: latest=the exact newly returned UUID, old baseline still active
  at 100 percent, source_class=wrangler_versions_upload.

The resulting snapshot is revalidated by the actual #1052 planner source before
inventory_sha256 is emitted.

## Remaining gates

This repository source has no network executor. A later separately reviewed
protected runtime must:

- be root-owned/pinned if installed;
- use the existing Stats account fingerprint boundary;
- use a dedicated read-class credential;
- execute only the three fixed GET stages;
- sanitize before any stdout/log output;
- never print account ID, token, author email, raw binding values or raw provider
  payloads.

Credential provisioning, authenticated GET execution, host installation, merge
and the one-time takeover remain separate owner decisions. No route, D1, secret,
Worker, deployment or setting mutation is authorized by this issue.


## Cloudflare V4 list-envelope correction — Issue #1058

A protected read-only collection on 2026-10-17 stopped fail-closed before a
usable inventory was produced. No retry was performed. Source review against
the current official Cloudflare API reference found that this parser's original
synthetic fixture did not match the documented V4 list envelopes.

The corrected source contract is:

- versions: `result` is exactly an object containing `items`; the first item
  is the latest version. `result_info` is not required or accepted because it
  is not part of the documented response shape for this endpoint;
- deployments: `result` is exactly an object containing `deployments`; the
  first deployment is the latest one actively serving traffic.
  `result_info` is optional; if supplied it is validated strictly;
- exact-version detail remains non-paginated.

The parser still requests at most two list entries, verifies sequential version
ordering when two are returned, requires one 100% active version, and preserves
all existing identity/binding/settings/leakage checks. This correction changes
provider-envelope parsing only; it grants no credential, Cloudflare or LIVE
authority.
