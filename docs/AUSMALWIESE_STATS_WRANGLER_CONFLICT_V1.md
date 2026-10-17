# Ausmalwiese Stats Worker — one-time Wrangler strict-conflict takeover (#1052)

**SOURCE ONLY / NO MERGE / NO LIVE.**

## Why this exists

The reviewed Stats Worker workflow pins Wrangler `4.135.0`, the exact
`coloring-pages` commit, Worker blob and Wrangler config blob. Its normal upload
uses `--strict`.

On 2026-10-17, one separately authorized LIVE upload attempt stopped safely
before creating a version because Wrangler reported that the Worker had last
been updated through the script API and strict mode detected a conflicting
remote source.

The latest and active version remained:

`e47f145f-1851-4917-be5c-387f96549539`

This source change does **not** retry that upload.

Cloudflare documents that `wrangler versions upload` creates a version without
deploying it, and that `--strict` prevents uploads when conflicting remote
changes would be overridden. Cloudflare also recommends treating Wrangler
configuration as the source of truth. Therefore the resolution is a deliberate
one-time source-of-truth takeover, not a permanent removal of `--strict`.

References:

- https://developers.cloudflare.com/workers/wrangler/commands/workers/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://developers.cloudflare.com/workers/versions-and-deployments/deployment-management/
- https://developers.cloudflare.com/workers/observability/errors/

## Frozen application inputs

- Worker: `coloring-pages-stats-v1`
- Wrangler: `4.135.0`
- `coloring-pages`: `180368f3b81abddde3df94637512436ca50c358f`
- Worker blob: `dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4`
- config blob: `3733263a391274f2b6b0f2023c8656565bde8e1a`
- conflict baseline version:
  `e47f145f-1851-4917-be5c-387f96549539`

The existing steady-state planner remains unchanged and keeps `--strict`.

## Trusted normalized snapshot

The source-only takeover planner never accepts raw Cloudflare responses and
never accepts secret values. A future separately reviewed read-only collector
must normalize authenticated provider evidence into the bounded snapshot schema.

Before takeover, the normalized snapshot must prove:

1. exact Worker, Wrangler and application provenance pins;
2. source class is the expected script/API conflict;
3. latest uploaded version is exactly the baseline UUID above;
4. there is exactly one active version and it receives exactly 100% traffic;
5. latest uploaded version equals that active version;
6. compatibility date is exactly `2026-10-06` and flags are empty;
7. D1 is exactly `DB` -> `coloring-pages-stats-v1` with database ID
   `f8ac8f1d-a230-4bc4-af13-557c1b91b273`;
8. Rate Limiter is exactly `RATE_LIMITER`, namespace `1152026106`, `100 / 60s`;
9. secret names are exactly `CF_ANALYTICS_API_TOKEN` and `VISITOR_HMAC_KEY`,
   without values;
10. the plain-text variable set is exactly `CF_ANALYTICS_HOST`,
    `CF_ZONE_TAG`, `PUBLIC_ORIGIN`, represented only by trusted SHA-256
    fingerprints;
11. one trusted `settings_sha256` fingerprints the remaining normalized
    version settings.

The planner hashes the complete normalized snapshot. A future owner LIVE gate
must bind that `inventory_sha256`; a caller-provided snapshot alone is not
authority.

## One-time takeover command

Only after the exact preconditions and owner-gate digest match does the planner
return a command array equivalent to:

    npx --yes wrangler@4.135.0 versions upload cloudflare/stats-worker.js \
      --config cloudflare/wrangler.stats-worker.jsonc \
      --name coloring-pages-stats-v1 \
      --no-bundle --keep-vars \
      --tag git:180368f3b81abddde3df94637512436ca50c358f \
      --message source-blob:dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4,config-blob:3733263a391274f2b6b0f2023c8656565bde8e1a,takeover-from:e47f145f-1851-4917-be5c-387f96549539

`--strict` is deliberately absent **only from this one-time takeover command**.
All other guards remain. There is no routes/triggers command, no
`--secrets-file`, and no D1 mutation.

## Post-upload gate before deploy

A successful upload is not enough to deploy.

A future trusted read-only collector must return a new normalized snapshot. The
planner requires:

- the returned full UUID is now the latest uploaded version;
- the old baseline UUID remains the only active version at 100%;
- source class for the new latest version is Wrangler `versions upload`;
- compatibility settings, D1, Rate Limiter, secret names, plain-text variable
  fingerprints and `settings_sha256` are preserved exactly.

Only then may the planner return:

    npx --yes wrangler@4.135.0 versions deploy <NEW-FULL-UUID>@100% \
      --config cloudflare/wrangler.stats-worker.jsonc \
      --name coloring-pages-stats-v1 -y

Post-deploy behavior verification remains:

    curl --fail-with-body --silent --show-error --head https://ausmalwiese.de/q

## Steady state

After a successful one-time takeover, the reviewed normal upload path remains
the #1050 planner and includes `--strict`. Any later conflict is new evidence
and must fail closed; this issue does not create a standing permission to
remove strict mode.

## Future owner gate

A later LIVE authorization must bind at minimum:

- exact merged `RPi5_main` SHA containing this design;
- exact frozen `coloring-pages` commit/source/config pins;
- Wrangler `4.135.0`;
- target `coloring-pages-stats-v1`;
- baseline version `e47f145f-1851-4917-be5c-387f96549539`;
- the fresh trusted normalized `inventory_sha256`;
- one non-strict takeover upload only;
- capture of the exact returned full UUID;
- read-only post-upload preservation proof;
- deploy only that exact UUID at 100%;
- HEAD `/q` verification.

Any mutation ambiguity or error after dispatch remains STOP without retry,
rollback or cleanup unless separately authorized.
